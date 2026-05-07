import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import JUDGEMENT_MODEL, gemini_client
from app.models.signal import RssBusinessImpactRun, RssSignal
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "business_impact_v1.txt"
PROMPT_TEMPLATE: Optional[str] = None
COST_PER_1K_INPUT_TOKENS = 1.25 / 1000
COST_PER_1K_OUTPUT_TOKENS = 10.0 / 1000
DEFAULT_MIN_SCORE = 60


def _load_prompt() -> str:
    global PROMPT_TEMPLATE
    if PROMPT_TEMPLATE is None:
        PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT_TEMPLATE


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"impact_{ts}_{uuid.uuid4().hex[:8]}"


def _render_prompt(signal: RssSignal) -> str:
    template = _load_prompt()
    return template.format(
        title=signal.representative_title or "(no title)",
        summary=(signal.representative_summary or "")[:500],
        importance_score=signal.importance_score or 0,
        impact_type=signal.impact_type or "unknown",
        cluster_status=signal.cluster_status or "unknown",
        representative_publisher=signal.representative_publisher or "(unknown)",
        key_entities=", ".join(signal.key_entities or []),
        regions=", ".join(signal.regions or []),
    )


def _validate_payload(payload: dict) -> dict:
    def _list(field: str, max_len: int = 5) -> list[str]:
        v = payload.get(field) or []
        if not isinstance(v, list):
            raise ValueError(f"{field} must be list")
        return [str(x) for x in v][:max_len]

    return {
        "impacted_sectors": _list("impacted_sectors"),
        "impacted_assets": _list("impacted_assets"),
        "impacted_regions": _list("impacted_regions"),
        "watch_points": _list("watch_points"),
        "counterfactual": str(payload.get("counterfactual") or "").strip()[:200],
        "gap_note": str(payload.get("gap_note") or "").strip()[:200],
    }


def _analyze_one(signal: RssSignal) -> dict[str, object]:
    prompt = _render_prompt(signal)
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            payload, input_tokens, output_tokens = gemini_client.generate_json(prompt)
            validated = _validate_payload(payload)
            return {
                "signal_id": signal.signal_id,
                "ok": True,
                "payload": validated,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_exc = exc
            logger.warning(
                "Impact parse failed for %s attempt %d: %s",
                signal.signal_id,
                attempt + 1,
                exc,
            )
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Impact call failed for %s attempt %d: %s",
                signal.signal_id,
                attempt + 1,
                exc,
            )
    return {"signal_id": signal.signal_id, "ok": False, "error": str(last_exc) if last_exc else "unknown"}


def analyze_business_impact(
    since_hours: int = 24,
    min_score: int = DEFAULT_MIN_SCORE,
    max_workers: int = 5,
    force: bool = False,
    max_signals_per_run: int = 100,
) -> dict[str, object]:
    started = time.monotonic()
    run_id = _generate_run_id()
    generated_at = utc_now_iso()
    since_iso = _since_iso(since_hours)

    candidates = firestore_client.list_signals_for_impact(
        since_iso, min_score=min_score, limit=max_signals_per_run * 2, force=force
    )
    if max_signals_per_run > 0:
        candidates = candidates[:max_signals_per_run]

    analyzed = 0
    failed = 0
    total_input_tokens = 0
    total_output_tokens = 0
    errors: list[dict[str, str]] = []
    updated: list[RssSignal] = []

    if candidates:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_analyze_one, s): s for s in candidates}
            for future in as_completed(futures):
                signal = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    failed += 1
                    errors.append({"signal_id": signal.signal_id, "error": str(exc)})
                    continue
                if not result["ok"]:
                    failed += 1
                    errors.append({"signal_id": result["signal_id"], "error": str(result.get("error"))})
                    continue
                payload = result["payload"]
                signal.impacted_sectors = payload["impacted_sectors"]
                signal.impacted_assets = payload["impacted_assets"]
                signal.impacted_regions = payload["impacted_regions"]
                signal.watch_points = payload["watch_points"]
                signal.counterfactual = payload["counterfactual"]
                signal.gap_note = payload["gap_note"]
                signal.impact_judged_at = utc_now_iso()
                signal.impact_judge_model = JUDGEMENT_MODEL
                signal.impact_input_tokens = result["input_tokens"]
                signal.impact_output_tokens = result["output_tokens"]
                updated.append(signal)
                analyzed += 1
                total_input_tokens += result["input_tokens"]
                total_output_tokens += result["output_tokens"]

        firestore_client.upsert_rss_signals(updated)

    cost_usd = (
        total_input_tokens / 1000 * COST_PER_1K_INPUT_TOKENS
        + total_output_tokens / 1000 * COST_PER_1K_OUTPUT_TOKENS
    )
    run = RssBusinessImpactRun(
        run_id=run_id,
        generated_at=generated_at,
        since_hours=since_hours,
        candidate_signal_count=len(candidates),
        analyzed_signal_count=analyzed,
        skipped_already_analyzed_count=0,
        skipped_low_score_count=0,
        failed_signal_count=failed,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost_usd=round(cost_usd, 6),
        duration_ms=int((time.monotonic() - started) * 1000),
        impact_model=JUDGEMENT_MODEL,
        errors=errors[:10],
    )
    firestore_client.create_business_impact_run(run)
    return run.model_dump()
