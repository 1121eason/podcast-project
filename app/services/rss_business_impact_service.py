import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import gemini_client
from app.clients.openai_client import openai_client
from app.core.config import settings
from app.models.signal import RssBusinessImpactRun, RssSignal
from app.services.llm_cost_utils import compute_llm_cost
from app.services.log_summary_utils import (
    add_duplicate_log_summary,
    add_log_summary,
    cost_text,
    seconds_text,
    tagged,
    token_text,
)
from app.services.model_routing_service import (
    default_model_route,
    effective_model_routes,
    resolve_model_route,
    validate_model_overrides,
)
from app.services.rss_source_service import utc_now_iso
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "business_impact_v1.txt"
PROMPT_TEMPLATE: Optional[str] = None

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
    """Render impact prompt with descriptive context only.

    W5 三原則延伸：W6 是 explainer，不該被 Judge 的 importance_score 或 Verify 的
    cluster_status 影響分析深度。只餵「event 是什麼」（title/summary/category/entities）
    跟「來源是誰」（publisher），不餵「多重要」或「有多少人報」。
    """
    template = _load_prompt()
    return template.format(
        title=signal.representative_title or "(no title)",
        summary=(signal.representative_summary or "")[:500],
        impact_type=signal.impact_type or "unknown",
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


def _call_impact_model(
    prompt: str,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, int, int, str]:
    """Returns (payload, input_tokens, output_tokens, model_used)."""
    route = resolve_model_route("w6_business_impact", model_overrides)
    if route.provider == "openai" and openai_client.is_ready:
        model = route.model
        payload, in_tok, out_tok = openai_client.generate_json(
            prompt,
            model=model,
            reasoning_effort=route.reasoning_effort or settings.IMPACT_REASONING_EFFORT,
        )
        return payload, in_tok, out_tok, model
    model = route.model if route.provider == "gemini" else default_model_route("w6_business_impact", "gemini").model
    payload, in_tok, out_tok = gemini_client.generate_json(prompt, model=model)
    return payload, in_tok, out_tok, model


def _analyze_one(
    signal: RssSignal,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    prompt = _render_prompt(signal)
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            payload, input_tokens, output_tokens, model_used = _call_impact_model(prompt, model_overrides)
            validated = _validate_payload(payload)
            return {
                "signal_id": signal.signal_id,
                "ok": True,
                "payload": validated,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "model_used": model_used,
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
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    run_id = _generate_run_id()
    generated_at = utc_now_iso()
    since_iso = _since_iso(since_hours)
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "business_impact",
        run_bucket,
        {
            "since_hours": since_hours,
            "min_score": min_score,
            "max_workers": max_workers,
            "force": force,
            "max_signals_per_run": max_signals_per_run,
            "run_bucket": run_bucket,
            "model_overrides": validate_model_overrides(model_overrides),
        },
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W6 Business Impact", run_bucket)
        return out

    try:
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
        tokens_by_model: dict[str, dict[str, int]] = {}
        # W6 health-check tallies — observe LLM output quality run by run.
        sectors_sum = 0
        assets_sum = 0
        regions_sum = 0
        watch_points_sum = 0
        empty_counterfactual = 0
        empty_gap_note = 0
        counterfactual_chars_sum = 0
        gap_note_chars_sum = 0

        if candidates:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_analyze_one, s, model_overrides): s for s in candidates}
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
                    signal.impact_judge_model = result.get("model_used", "unknown")
                    signal.impact_input_tokens = result["input_tokens"]
                    signal.impact_output_tokens = result["output_tokens"]
                    updated.append(signal)
                    analyzed += 1
                    total_input_tokens += result["input_tokens"]
                    total_output_tokens += result["output_tokens"]
                    m = result.get("model_used", "unknown")
                    m_bucket = tokens_by_model.setdefault(m, {"input": 0, "output": 0})
                    m_bucket["input"] += result["input_tokens"]
                    m_bucket["output"] += result["output_tokens"]
                    # W6 monitoring: accumulate output-quality stats
                    sectors_sum += len(payload["impacted_sectors"])
                    assets_sum += len(payload["impacted_assets"])
                    regions_sum += len(payload["impacted_regions"])
                    watch_points_sum += len(payload["watch_points"])
                    cf = payload["counterfactual"]
                    gn = payload["gap_note"]
                    if not cf:
                        empty_counterfactual += 1
                    if not gn:
                        empty_gap_note += 1
                    counterfactual_chars_sum += len(cf)
                    gap_note_chars_sum += len(gn)

            firestore_client.upsert_rss_signals(updated)

        # P0 fix: pricing computed per actual model used
        cost_usd = sum(
            compute_llm_cost(model, tok["input"], tok["output"])
            for model, tok in tokens_by_model.items()
        )
        if tokens_by_model:
            impact_model = max(tokens_by_model.items(), key=lambda kv: kv[1]["input"] + kv[1]["output"])[0]
        else:
            impact_model = resolve_model_route("w6_business_impact", model_overrides).model
        # W6 monitoring averages — use analyzed (non-failed) as denominator
        denom = max(1, analyzed)
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
            impact_model=impact_model,
            avg_sectors_per_signal=round(sectors_sum / denom, 2),
            avg_assets_per_signal=round(assets_sum / denom, 2),
            avg_regions_per_signal=round(regions_sum / denom, 2),
            avg_watch_points_per_signal=round(watch_points_sum / denom, 2),
            empty_counterfactual_count=empty_counterfactual,
            empty_gap_note_count=empty_gap_note,
            avg_counterfactual_chars=round(counterfactual_chars_sum / denom, 1),
            avg_gap_note_chars=round(gap_note_chars_sum / denom, 1),
            errors=errors[:10],
        )
        firestore_client.create_business_impact_run(run)
        result = run.model_dump()
        result["run_bucket"] = run_bucket
        result["workflow_run_id"] = workflow_run_id
        result["skipped_duplicate"] = False
        result["model_routing"] = effective_model_routes(model_overrides, ["w6_business_impact"])
        add_log_summary(result, _compose_business_impact_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _compose_business_impact_log_summary(result: dict[str, object]) -> list[str]:
    lines = [
        tagged(
            "ok",
            (
                f"W6 影響分析候選 {result.get('candidate_signal_count', 0)} 個，"
                f"成功 {result.get('analyzed_signal_count', 0)} 個，失敗 {result.get('failed_signal_count', 0)} 個。"
            ),
        ),
        tagged(
            "ok",
            (
                f"平均輸出：sectors {result.get('avg_sectors_per_signal', 0)}、"
                f"assets {result.get('avg_assets_per_signal', 0)}、regions {result.get('avg_regions_per_signal', 0)}、"
                f"watch_points {result.get('avg_watch_points_per_signal', 0)}。"
            ),
        ),
    ]
    empty_cf = int(result.get("empty_counterfactual_count") or 0)
    empty_gap = int(result.get("empty_gap_note_count") or 0)
    if empty_cf or empty_gap:
        lines.append(tagged("warn", f"空 counterfactual {empty_cf}、空 gap_note {empty_gap}，需抽查 W6 輸出品質。"))
    lines.append(
        tagged(
            "cost",
            (
                f"LLM 成本 {cost_text(result.get('total_cost_usd'))}，"
                f"{token_text(result.get('total_input_tokens'), result.get('total_output_tokens'))}，"
                f"model={result.get('impact_model') or 'unknown'}。"
            ),
        )
    )
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines
