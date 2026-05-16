import hashlib
import json
import logging
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import gemini_client
from app.clients.openai_client import openai_client
from app.core.config import settings
from app.models.signal import (
    BriefingCategory,
    BriefingSection,
    BriefingTopChange,
    RssBriefing,
    RssSignal,
)
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
from app.services.signal_v2_utils import importance_bucket, phase_flags_from_rationale
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "editorial_briefing_v2.txt"
PROMPT_TEMPLATE: Optional[str] = None


def _call_briefing_model(
    prompt: str,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, int, int, str]:
    """Returns (payload, input_tokens, output_tokens, model_used)."""
    route = resolve_model_route("w8_briefing", model_overrides)
    if route.provider == "openai" and openai_client.is_ready:
        model = route.model
        payload, in_tok, out_tok = openai_client.generate_json(
            prompt,
            model=model,
            reasoning_effort=route.reasoning_effort or settings.BRIEFING_REASONING_EFFORT,
        )
        return payload, in_tok, out_tok, model
    model = route.model if route.provider == "gemini" else default_model_route("w8_briefing", "gemini").model
    payload, in_tok, out_tok = gemini_client.generate_json(prompt, model=model)
    return payload, in_tok, out_tok, model

DEFAULT_SCORE_THRESHOLD = 60
DEFAULT_MAX_SIGNALS_INPUT = 80
DEFAULT_MAX_SECTIONS = 10

CATEGORY_TITLES = {
    "geopolitics": "國際局勢",
    "global_finance": "國際金融",
    "tech": "科技發展",
    "business_trends": "其他商業趨勢",
}
CATEGORY_ORDER = ["geopolitics", "global_finance", "tech", "business_trends"]


def _load_prompt() -> str:
    global PROMPT_TEMPLATE
    if PROMPT_TEMPLATE is None:
        PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT_TEMPLATE


def _today_date_str(briefing_date: Optional[str] = None) -> str:
    if briefing_date:
        return briefing_date
    timezone_name = settings.BRIEFING_TIMEZONE or "UTC"
    try:
        briefing_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid BRIEFING_TIMEZONE=%s, falling back to UTC", timezone_name)
        briefing_timezone = timezone.utc
    return datetime.now(briefing_timezone).strftime("%Y-%m-%d")


def _generate_briefing_id(briefing_date: str) -> str:
    digest = hashlib.sha256(f"{briefing_date}_{utc_now_iso()}".encode()).hexdigest()[:6]
    return f"brief_{briefing_date.replace('-','')}_{digest}"


def _signal_to_compact(signal: RssSignal) -> dict:
    flags = phase_flags_from_rationale(signal.adjudication_rationale)
    return {
        "signal_id": signal.signal_id,
        "title": signal.representative_title,
        "url": signal.representative_url,
        "publisher": signal.representative_publisher,
        "score": signal.importance_score,
        "impact_type": signal.impact_type,
        "primary_theme": signal.primary_theme,
        "cluster_status": signal.cluster_status,
        "topic_heat": signal.topic_heat,
        "key_entities": signal.key_entities or [],
        "regions": signal.regions or [],
        "publishers": signal.publishers,
        "source_count": signal.source_count,
        "summary_excerpt": (signal.representative_summary or "")[:300],
        "reasoning": signal.reasoning,
        "what_happened": signal.what_happened,
        "why_matters": signal.why_matters,
        "who_affected": signal.who_affected,
        "what_next": signal.what_next,
        "impacted_sectors": signal.impacted_sectors or [],
        "impacted_assets": signal.impacted_assets or [],
        "watch_points": signal.watch_points or [],
        "counterfactual": signal.counterfactual,
        "gap_note": signal.gap_note,
        "thread_id": signal.thread_id,
        "phase_id": signal.phase_id,
        "signal_status": signal.signal_status,
        "novelty_score": signal.novelty_score,
        "today_delta": signal.today_delta,
        "is_background_repeat": signal.is_background_repeat,
        "adjudication_decision": signal.adjudication_decision,  # W4: same_event | same_thread | different_event
        "adjudication_rationale": (signal.adjudication_rationale or "")[:200],
        "thread_mismatch_suspected": flags["thread_mismatch_suspected"],  # W7 phase flag
        "duplicate_suspected": flags["duplicate_suspected"],  # W7 phase flag
        "continuation_hint": (
            f"延續既有 thread {signal.thread_id}，今日新變化：{signal.today_delta}"
            if signal.thread_id and signal.today_delta
            else ""
        ),
    }


def _build_thread_groups(signals: list[RssSignal]) -> tuple[list[dict], list[dict]]:
    """Group signals by thread, attach thread + phase context.

    Returns (thread_groups, ungrouped_signals). thread_groups is a list of
    {thread, phases, signals}; ungrouped_signals is the flat list of signals
    without thread_id (orphans, e.g. brand-new signals that haven't been through W7).
    """
    threaded: dict[str, list[RssSignal]] = {}
    ungrouped: list[RssSignal] = []
    for signal in signals:
        if signal.thread_id:
            threaded.setdefault(signal.thread_id, []).append(signal)
        else:
            ungrouped.append(signal)

    thread_ids = list(threaded.keys())
    if not thread_ids:
        return [], [_signal_to_compact(s) for s in ungrouped]

    threads = firestore_client.list_story_threads_by_ids(thread_ids)
    threads_by_id = {t.thread_id: t for t in threads}
    phases_by_thread = firestore_client.list_phases_for_threads(thread_ids)

    groups: list[dict] = []
    for tid, sigs in threaded.items():
        thread = threads_by_id.get(tid)
        phases = phases_by_thread.get(tid, [])
        # Sort signals inside thread by importance desc — gives LLM a clean reading order.
        sigs.sort(key=lambda s: (s.importance_score or 0), reverse=True)
        groups.append(
            {
                "thread": _thread_context(thread, tid),
                "phases": _phase_summaries(phases),
                "signals": [_signal_to_compact(s) for s in sigs],
            }
        )
    # Sort thread groups: ones with new development today (any non-background_repeat
    # signal) first, then by max importance.
    def group_priority(g: dict) -> tuple:
        sigs = g["signals"]
        any_new = any(not s.get("is_background_repeat") for s in sigs)
        max_imp = max((int(s.get("score") or 0) for s in sigs), default=0)
        return (1 if any_new else 0, max_imp)

    groups.sort(key=group_priority, reverse=True)
    ungrouped_compact = [_signal_to_compact(s) for s in ungrouped]
    return groups, ungrouped_compact


def _thread_context(thread, thread_id: str) -> dict:
    if not thread:
        # thread_id present on signal but thread doc missing — surface for LLM awareness.
        return {"thread_id": thread_id, "title": "(thread missing)", "missing": True}
    return {
        "thread_id": thread.thread_id,
        "title": thread.title,
        "status": thread.status,
        "active_since": thread.active_since,
        "last_seen_at": thread.last_seen_at,
        "last_covered_in_podcast_at": thread.last_covered_in_podcast_at,
        "known_background": (thread.known_background or "")[:400],
        "today_delta": thread.today_delta,
        "do_not_repeat_points": (thread.do_not_repeat_points or [])[:5],
        "continuation_prompt_hint": thread.continuation_prompt_hint,
        "novelty_score": thread.novelty_score,
        "key_entities": (thread.key_entities or [])[:8],
    }


def _phase_summaries(phases: list) -> list[dict]:
    if not phases:
        return []
    out = []
    # Show active/emerging first (these represent ongoing narrative); then dormant for context.
    status_order = {"emerging": 0, "active": 1, "dormant": 2, "resolved": 3}
    for phase in sorted(phases, key=lambda p: status_order.get(p.status, 9)):
        out.append(
            {
                "phase_id": phase.phase_id,
                "title": phase.title,
                "status": phase.status,
                "signal_count": phase.signal_count,
                "parent_phase_id": phase.parent_phase_id,
                "novelty_reason": (phase.novelty_reason or "")[:120],
                "opened_at": phase.opened_at,
                "last_advanced_at": phase.last_advanced_at,
            }
        )
    return out


def _yesterday_briefing_summary(today_date: Optional[str] = None) -> str:
    """Returns a compact text summary of yesterday's briefing for continuity prompts.

    Picks the most recent briefing whose ``briefing_date`` is strictly earlier
    than ``today_date`` (independent of generated_at) so a same-day retry
    doesn't accidentally treat today's failed run as "yesterday".
    """
    recent = firestore_client.list_recent_briefings(limit=10)
    if not recent:
        return "（昨日無 briefing 紀錄，視今日為新系列起點）"

    today_date = today_date or _today_date_str()
    earlier = [b for b in recent if (b.briefing_date or "") < today_date and (b.overview or b.top_changes or b.categories)]
    if not earlier:
        return "（昨日無 briefing 紀錄，視今日為新系列起點）"

    earlier.sort(key=lambda b: b.briefing_date or "", reverse=True)
    yesterday = earlier[0]
    parts: list[str] = []
    parts.append(f"日期: {yesterday.briefing_date}")
    parts.append(f"總覽: {(yesterday.overview or '')[:300]}")
    if yesterday.top_changes:
        parts.append("昨日 top changes:")
        for tc in yesterday.top_changes[:6]:
            parts.append(f"  - [{tc.importance_score}] {tc.title}")
    parts.append("昨日 categories 標題:")
    for cat in yesterday.categories[:4]:
        section_titles = [s.title for s in cat.sections]
        if section_titles:
            parts.append(f"  {cat.title}: {' / '.join(section_titles[:5])}")
    return "\n".join(parts)


def _render_prompt(
    signals: list[RssSignal],
    total_judged: int,
    briefing_date: Optional[str] = None,
    retry_feedback: str = "",
) -> str:
    template = _load_prompt()
    thread_groups, ungrouped = _build_thread_groups(signals)
    desks = Counter()
    for s in signals:
        for d in s.desks or []:
            desks[d] += 1
    high_count = sum(1 for s in signals if importance_bucket(s.importance_score) in {"critical", "high"})
    background_repeat_count = sum(1 for s in signals if s.is_background_repeat)
    yesterday_summary = _yesterday_briefing_summary(briefing_date)
    return template.format(
        thread_groups_json=json.dumps(thread_groups, ensure_ascii=False, indent=2),
        ungrouped_signals_json=json.dumps(ungrouped, ensure_ascii=False, indent=2),
        total_judged=total_judged,
        high_importance_count=high_count,
        background_repeat_count=background_repeat_count,
        thread_count=len(thread_groups),
        ungrouped_count=len(ungrouped),
        desk_distribution=", ".join(f"{k}:{v}" for k, v in desks.most_common(5)),
        yesterday_briefing_summary=yesterday_summary,
        retry_feedback=retry_feedback,
    )


def _validate_section(raw: dict, candidate_signals: list[RssSignal], section_id: str) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    if not title or not summary:
        return None
    valid_signal_ids = {s.signal_id for s in candidate_signals}
    ref_ids = [str(x) for x in (raw.get("referenced_signal_ids") or []) if str(x) in valid_signal_ids]
    ref_urls = [str(x) for x in (raw.get("referenced_urls") or [])][:10]
    if not ref_urls and ref_ids:
        ref_urls = []
        for s in candidate_signals:
            if s.signal_id in ref_ids and s.representative_url:
                ref_urls.append(s.representative_url)
    return {
        "section_id": section_id,
        "title": title[:80],
        "summary": summary[:2000],
        "importance_score": int(raw.get("importance_score") or 0),
        "impact_type": str(raw.get("impact_type") or ""),
        "is_continuation": bool(raw.get("is_continuation") or False),
        "continuation_note": str(raw.get("continuation_note") or "").strip()[:200],
        "impacted_sectors": [str(x) for x in (raw.get("impacted_sectors") or [])][:5],
        "watch_points": [str(x) for x in (raw.get("watch_points") or [])][:5],
        "referenced_signal_ids": ref_ids[:10],
        "referenced_urls": ref_urls[:10],
    }


def _validate_top_change(raw: dict, candidate_signals: list[RssSignal], rank: int) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    summary = str(raw.get("summary") or "").strip()
    if not title or not summary:
        return None
    valid_signal_ids = {s.signal_id for s in candidate_signals}
    ref_ids = [str(x) for x in (raw.get("referenced_signal_ids") or []) if str(x) in valid_signal_ids]
    ref_urls = [str(x) for x in (raw.get("referenced_urls") or [])][:10]
    if not ref_urls and ref_ids:
        ref_urls = []
        for s in candidate_signals:
            if s.signal_id in ref_ids and s.representative_url:
                ref_urls.append(s.representative_url)
    return {
        "rank": int(raw.get("rank") or rank),
        "title": title[:80],
        "summary": summary[:1200],
        "category_id": str(raw.get("category_id") or ""),
        "importance_score": int(raw.get("importance_score") or 0),
        "is_continuation": bool(raw.get("is_continuation") or False),
        "referenced_signal_ids": ref_ids[:10],
        "referenced_urls": ref_urls[:10],
    }


def _validate_briefing_payload(payload: dict, candidate_signals: list[RssSignal], max_sections_per_category: int) -> dict:
    overview = str(payload.get("overview") or "").strip()
    if not overview:
        raise ValueError("missing overview")

    raw_categories = payload.get("categories") or []
    if not isinstance(raw_categories, list) or not raw_categories:
        raise ValueError("missing categories")

    by_id = {}
    for raw in raw_categories:
        if not isinstance(raw, dict):
            continue
        cid = str(raw.get("category_id") or "").strip()
        if cid in CATEGORY_TITLES:
            by_id[cid] = raw

    categories: list[dict] = []
    flat_sections: list[dict] = []
    sec_counter = 0
    for cid in CATEGORY_ORDER:
        raw = by_id.get(cid, {})
        title = str(raw.get("title") or CATEGORY_TITLES[cid])
        cat_overview = str(raw.get("category_overview") or "").strip()[:300]
        raw_sections = raw.get("sections") or []
        if not isinstance(raw_sections, list):
            raw_sections = []
        validated_sections = []
        for raw_sec in raw_sections[:max_sections_per_category]:
            sec_counter += 1
            validated = _validate_section(raw_sec, candidate_signals, f"sec_{sec_counter:02d}")
            if validated:
                validated_sections.append(validated)
                flat_sections.append(validated)
        categories.append({
            "category_id": cid,
            "title": title,
            "category_overview": cat_overview or "今日無達門檻訊號。",
            "sections": validated_sections,
        })

    pool_health = payload.get("signal_pool_health") or {}
    if not isinstance(pool_health, dict):
        pool_health = {}

    raw_top_changes = payload.get("top_changes") or []
    top_changes: list[dict] = []
    if isinstance(raw_top_changes, list):
        for idx, raw in enumerate(raw_top_changes[:8]):
            validated = _validate_top_change(raw, candidate_signals, idx + 1)
            if validated:
                top_changes.append(validated)

    raw_watch = payload.get("aggregated_watch_points") or []
    watch_points: list[str] = []
    if isinstance(raw_watch, list):
        for w in raw_watch[:20]:
            text = str(w or "").strip()
            if text:
                watch_points.append(text[:200])

    return {
        "overview": overview[:2000],
        "top_changes": top_changes,
        "categories": categories,
        "sections": flat_sections,
        "aggregated_watch_points": watch_points,
        "signal_pool_health": pool_health,
    }


def _generate_with_retry(
    candidates: list[RssSignal],
    total_judged: int,
    briefing_date: Optional[str],
    max_sections: int,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, dict, int, int, str, int]:
    """Run prompt + LLM + validation with one retry on validation failure.

    Returns (validated, raw_payload, input_tokens, output_tokens, model_used, retry_count).
    Raises on second failure.
    """
    total_in = 0
    total_out = 0
    last_payload: dict = {}
    model_used = ""
    last_error = ""
    for attempt in range(2):
        retry_feedback = (
            f"\n⚠️ 上一次嘗試失敗：{last_error}\n請修正後重新輸出完整 JSON。\n"
            if attempt > 0 and last_error
            else ""
        )
        prompt = _render_prompt(
            candidates, total_judged, briefing_date, retry_feedback=retry_feedback
        )
        payload, in_tok, out_tok, model_used = _call_briefing_model(prompt, model_overrides)
        total_in += in_tok
        total_out += out_tok
        last_payload = payload
        try:
            validated = _validate_briefing_payload(payload, candidates, max_sections)
            return validated, payload, total_in, total_out, model_used, attempt
        except ValueError as exc:
            last_error = str(exc)[:200]
            logger.warning(
                "briefing_validation_failed attempt=%d error=%s", attempt + 1, last_error
            )
    # Both attempts failed.
    raise ValueError(
        f"briefing validation failed after retry (last error: {last_error})"
    )


def generate_daily_briefing(
    briefing_date: Optional[str] = None,
    score_threshold: int = DEFAULT_SCORE_THRESHOLD,
    max_sections: int = DEFAULT_MAX_SECTIONS,
    max_signals_input: int = DEFAULT_MAX_SIGNALS_INPUT,
    write_google_doc: bool = True,
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    """
    max_sections is interpreted as "max sections per category".
    """
    started = time.monotonic()
    briefing_date = _today_date_str(briefing_date)
    briefing_id = _generate_briefing_id(briefing_date)
    generated_at = utc_now_iso()
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "briefing_generate",
        run_bucket,
        {
            "briefing_date": briefing_date,
            "score_threshold": score_threshold,
            "max_sections": max_sections,
            "max_signals_input": max_signals_input,
            "write_google_doc": write_google_doc,
            "run_bucket": run_bucket,
            "model_overrides": validate_model_overrides(model_overrides),
        },
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W8 Briefing", run_bucket)
        return out

    try:
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
                model=resolve_model_route("w8_briefing", model_overrides).model,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            firestore_client.upsert_briefing(briefing)
            result = briefing.model_dump()
            result["run_bucket"] = run_bucket
            result["workflow_run_id"] = workflow_run_id
            result["skipped_duplicate"] = False
            result["briefing_retry_count"] = 0
            result["model_routing"] = effective_model_routes(model_overrides, ["w8_briefing"])
            add_log_summary(result, _compose_briefing_log_summary(result))
            complete_workflow_run(workflow_run_id, result)
            return result

        total_judged = len(firestore_client.list_signals_for_briefing(since_iso, min_score=0, limit=2000))

        validated, payload, input_tokens, output_tokens, model_used, retry_count = (
            _generate_with_retry(candidates, total_judged, briefing_date, max_sections, model_overrides)
        )
        # Persist retry observability into the stored briefing so we can
        # measure retry-trigger-rate after the fact (validates "pure insurance" assumption).
        if isinstance(validated.get("signal_pool_health"), dict):
            validated["signal_pool_health"]["briefing_retry_count"] = retry_count

        sections = [BriefingSection(**s) for s in validated["sections"]]
        categories = [
            BriefingCategory(
                category_id=c["category_id"],
                title=c["title"],
                category_overview=c["category_overview"],
                sections=[BriefingSection(**s) for s in c["sections"]],
            )
            for c in validated["categories"]
        ]
        top_changes = [BriefingTopChange(**tc) for tc in validated["top_changes"]]
        aggregated_watch_points = validated["aggregated_watch_points"]

        # P0 fix: cost computed per actual model used (single source of truth)
        cost_usd = compute_llm_cost(model_used, input_tokens, output_tokens)

        google_doc_id = None
        google_doc_url = None
        if write_google_doc:
            try:
                from app.services.briefing_doc_writer import write_briefing_to_doc
                google_doc_id, google_doc_url = write_briefing_to_doc(
                    briefing_date=briefing_date,
                    overview=validated["overview"],
                    top_changes=top_changes,
                    categories=categories,
                    aggregated_watch_points=aggregated_watch_points,
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
            top_changes=top_changes,
            categories=categories,
            sections=sections,
            aggregated_watch_points=aggregated_watch_points,
            signal_pool_health=validated["signal_pool_health"],
            google_doc_id=google_doc_id,
            google_doc_url=google_doc_url,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        firestore_client.upsert_briefing(briefing)
        result = briefing.model_dump()
        result["run_bucket"] = run_bucket
        result["workflow_run_id"] = workflow_run_id
        result["skipped_duplicate"] = False
        result["briefing_retry_count"] = retry_count
        result["model_routing"] = effective_model_routes(model_overrides, ["w8_briefing"])
        add_log_summary(result, _compose_briefing_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _compose_briefing_log_summary(result: dict[str, object]) -> list[str]:
    categories = result.get("categories") if isinstance(result.get("categories"), list) else []
    section_count = sum(len(c.get("sections") or []) for c in categories if isinstance(c, dict))
    top_changes = result.get("top_changes") if isinstance(result.get("top_changes"), list) else []
    doc_status = "已寫 Google Doc" if result.get("google_doc_url") else "未寫 Google Doc"
    retry_count = int(result.get("briefing_retry_count") or 0)
    lines = [
        tagged(
            "ok",
            (
                f"W8 Briefing 選入 {result.get('selected_signal_count', 0)}/"
                f"{result.get('total_input_signals', 0)} 個 signal，輸出 {section_count} 個 section、"
                f"{len(top_changes)} 個 top change。"
            ),
        ),
        tagged("new", "thread / phase context 已注入 prompt；LLM 可依 do_not_repeat 與 background_repeat 控制重複。"),
    ]
    if retry_count:
        lines.append(tagged("warn", f"briefing validation retry {retry_count} 次，請抽查輸出格式是否穩定。"))
    else:
        lines.append(tagged("ok", "briefing validation 一次通過。"))
    lines.append(tagged("ok", doc_status + "。"))
    lines.append(
        tagged(
            "cost",
            (
                f"LLM 成本 {cost_text(result.get('cost_usd'))}，"
                f"{token_text(result.get('input_tokens'), result.get('output_tokens'))}，model={result.get('model') or 'unknown'}。"
            ),
        )
    )
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines
