import hashlib
import json
import logging
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import JUDGEMENT_MODEL, gemini_client
from app.models.signal import BriefingSection, RssBriefing, RssSignal
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "editorial_briefing_v2.txt"
PROMPT_TEMPLATE: Optional[str] = None
COST_PER_1K_INPUT_TOKENS = 1.25 / 1000
COST_PER_1K_OUTPUT_TOKENS = 10.0 / 1000

DEFAULT_SCORE_THRESHOLD = 70
DEFAULT_MAX_SIGNALS_INPUT = 60
DEFAULT_MAX_SECTIONS = 8


def _load_prompt() -> str:
    global PROMPT_TEMPLATE
    if PROMPT_TEMPLATE is None:
        PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT_TEMPLATE


def _today_date_str(briefing_date: Optional[str] = None) -> str:
    if briefing_date:
        return briefing_date
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _generate_briefing_id(briefing_date: str) -> str:
    digest = hashlib.sha256(f"{briefing_date}_{utc_now_iso()}".encode()).hexdigest()[:6]
    return f"brief_{briefing_date.replace('-','')}_{digest}"


def _signal_to_compact(signal: RssSignal) -> dict:
    return {
        "signal_id": signal.signal_id,
        "title": signal.representative_title,
        "url": signal.representative_url,
        "publisher": signal.representative_publisher,
        "score": signal.importance_score,
        "impact_type": signal.impact_type,
        "cluster_status": signal.cluster_status,
        "topic_heat": signal.topic_heat,
        "key_entities": signal.key_entities or [],
        "regions": signal.regions or [],
        "publishers": signal.publishers,
        "source_count": signal.source_count,
        "summary_excerpt": (signal.representative_summary or "")[:300],
        "reasoning": signal.reasoning,
        "impacted_sectors": signal.impacted_sectors or [],
        "impacted_assets": signal.impacted_assets or [],
        "watch_points": signal.watch_points or [],
        "counterfactual": signal.counterfactual,
        "gap_note": signal.gap_note,
    }


def _render_prompt(signals: list[RssSignal], total_judged: int) -> str:
    template = _load_prompt()
    compact = [_signal_to_compact(s) for s in signals]
    desks = Counter()
    for s in signals:
        for d in s.desks or []:
            desks[d] += 1
    high_count = sum(1 for s in signals if (s.importance_score or 0) >= 70)
    return template.format(
        signals_json=json.dumps(compact, ensure_ascii=False, indent=2),
        total_judged=total_judged,
        high_importance_count=high_count,
        desk_distribution=", ".join(f"{k}:{v}" for k, v in desks.most_common(5)),
    )


def _validate_briefing_payload(payload: dict, candidate_signals: list[RssSignal], max_sections: int) -> dict:
    overview = str(payload.get("overview") or "").strip()
    if not overview:
        raise ValueError("missing overview")

    raw_sections = payload.get("sections") or []
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("missing sections")

    valid_signal_ids = {s.signal_id for s in candidate_signals}
    sections: list[dict] = []
    for idx, raw in enumerate(raw_sections[:max_sections]):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        if not title or not summary:
            continue
        ref_ids = [str(x) for x in (raw.get("referenced_signal_ids") or []) if str(x) in valid_signal_ids]
        ref_urls = [str(x) for x in (raw.get("referenced_urls") or [])][:10]
        if not ref_urls and ref_ids:
            ref_urls = []
            for s in candidate_signals:
                if s.signal_id in ref_ids and s.representative_url:
                    ref_urls.append(s.representative_url)
        sections.append({
            "section_id": f"sec_{idx+1:02d}",
            "title": title[:60],
            "summary": summary[:1200],
            "importance_score": int(raw.get("importance_score") or 0),
            "impact_type": str(raw.get("impact_type") or ""),
            "impacted_sectors": [str(x) for x in (raw.get("impacted_sectors") or [])][:5],
            "watch_points": [str(x) for x in (raw.get("watch_points") or [])][:5],
            "referenced_signal_ids": ref_ids[:10],
            "referenced_urls": ref_urls[:10],
        })

    pool_health = payload.get("signal_pool_health") or {}
    if not isinstance(pool_health, dict):
        pool_health = {}

    return {
        "overview": overview[:1000],
        "sections": sections,
        "signal_pool_health": pool_health,
    }


def generate_daily_briefing(
    briefing_date: Optional[str] = None,
    score_threshold: int = DEFAULT_SCORE_THRESHOLD,
    max_sections: int = DEFAULT_MAX_SECTIONS,
    max_signals_input: int = DEFAULT_MAX_SIGNALS_INPUT,
    write_google_doc: bool = True,
) -> dict[str, object]:
    started = time.monotonic()
    briefing_date = _today_date_str(briefing_date)
    briefing_id = _generate_briefing_id(briefing_date)
    generated_at = utc_now_iso()

    since_iso = (
        (datetime.now(timezone.utc) - timedelta(hours=24))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    candidates = firestore_client.list_signals_for_briefing(
        since_iso, min_score=score_threshold, limit=max_signals_input
    )
    if not candidates:
        briefing = RssBriefing(
            briefing_id=briefing_id,
            briefing_date=briefing_date,
            generated_at=generated_at,
            score_threshold=score_threshold,
            selected_signal_count=0,
            total_input_signals=0,
            overview="今日無達門檻訊號。",
            sections=[],
            signal_pool_health={"reason": "no candidates above threshold"},
            model=JUDGEMENT_MODEL,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        firestore_client.upsert_briefing(briefing)
        return briefing.model_dump()

    total_judged = len(firestore_client.list_signals_for_briefing(since_iso, min_score=0, limit=2000))

    prompt = _render_prompt(candidates, total_judged)
    payload, input_tokens, output_tokens = gemini_client.generate_json(prompt)
    validated = _validate_briefing_payload(payload, candidates, max_sections)

    sections = [BriefingSection(**s) for s in validated["sections"]]

    cost_usd = (
        input_tokens / 1000 * COST_PER_1K_INPUT_TOKENS
        + output_tokens / 1000 * COST_PER_1K_OUTPUT_TOKENS
    )

    google_doc_id = None
    google_doc_url = None
    if write_google_doc:
        try:
            from app.services.briefing_doc_writer import write_briefing_to_doc
            google_doc_id, google_doc_url = write_briefing_to_doc(
                briefing_date=briefing_date,
                overview=validated["overview"],
                sections=sections,
                signal_pool_health=validated["signal_pool_health"],
            )
        except Exception as exc:
            logger.warning("Google Doc write skipped: %s", exc)

    briefing = RssBriefing(
        briefing_id=briefing_id,
        briefing_date=briefing_date,
        generated_at=generated_at,
        score_threshold=score_threshold,
        selected_signal_count=len(candidates),
        total_input_signals=total_judged,
        overview=validated["overview"],
        sections=sections,
        signal_pool_health=validated["signal_pool_health"],
        google_doc_id=google_doc_id,
        google_doc_url=google_doc_url,
        model=JUDGEMENT_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round(cost_usd, 6),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    firestore_client.upsert_briefing(briefing)
    return briefing.model_dump()
