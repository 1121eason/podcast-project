import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from app.clients.firestore_client import firestore_client
from app.clients.gemini_client import gemini_client
from app.clients.openai_client import openai_client
from app.core.config import settings
from app.models.podcast import RssPodcastScript, ScriptSegment
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
from app.services.signal_v2_utils import phase_flags_from_rationale
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "podcast_script_v1.txt"
PROMPT_TEMPLATE: Optional[str] = None

WORD_COUNT_TARGET_LOW = 6500
WORD_COUNT_TARGET_HIGH = 7500
MANDATORY_OPENING = "歡迎回到 Informative AI。"
MANDATORY_CLOSING = "感謝各位今天的收聽，明天見。"


def _spoken_char_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def _date_prefix(briefing_date: str) -> str:
    parts = briefing_date.split("-")
    if len(parts) == 3:
        return "/".join(parts)
    return briefing_date.replace("-", "/")


def _clean_title_fragment(raw_title: str) -> str:
    title = re.sub(r"\s+", " ", str(raw_title or "")).strip()
    title = re.sub(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s*[-－—]\s*", "", title)
    title = title.strip(" -－—|｜：:")
    return title[:60]


def format_episode_title(briefing_date: str, raw_title: str) -> str:
    title = _clean_title_fragment(raw_title)
    if not title:
        title = "今日全球關鍵訊號"
    return f"{_date_prefix(briefing_date)}-{title}"


def _fallback_title_from_briefing(briefing) -> str:
    if briefing.top_changes:
        return briefing.top_changes[0].title
    if briefing.categories:
        for category in briefing.categories:
            if category.sections:
                return category.sections[0].title
    return "今日全球關鍵訊號"


def _load_prompt() -> str:
    global PROMPT_TEMPLATE
    if PROMPT_TEMPLATE is None:
        PROMPT_TEMPLATE = PROMPT_PATH.read_text(encoding="utf-8")
    return PROMPT_TEMPLATE


def _generate_script_id(briefing_date: str) -> str:
    digest = hashlib.sha256(f"{briefing_date}_{utc_now_iso()}".encode()).hexdigest()[:6]
    return f"podcast_{briefing_date.replace('-','')}_{digest}"


def _briefing_to_compact(briefing) -> dict:
    continuity_notes = []
    for tc in briefing.top_changes:
        if tc.is_continuation:
            continuity_notes.append({
                "title": tc.title,
                "is_continuation": tc.is_continuation,
                "today_delta": tc.summary[:300],
            })
    for cat in briefing.categories:
        for section in cat.sections:
            if section.is_continuation or section.continuation_note:
                continuity_notes.append({
                    "title": section.title,
                    "is_continuation": section.is_continuation,
                    "continuation_note": section.continuation_note,
                    "today_delta": section.summary[:300],
                    "do_not_repeat_points": [section.continuation_note] if section.continuation_note else [],
                })
    return {
        "briefing_id": briefing.briefing_id,
        "briefing_date": briefing.briefing_date,
        "overview": briefing.overview,
        "top_changes": [tc.model_dump() for tc in briefing.top_changes],
        "categories": [c.model_dump() for c in briefing.categories],
        "aggregated_watch_points": briefing.aggregated_watch_points,
        "signal_pool_health": briefing.signal_pool_health,
        "podcast_continuity_notes": continuity_notes[:20],
    }


def _yesterday_briefing_summary(today_date: Optional[str] = None) -> str:
    """Returns yesterday's briefing summary for podcast continuity.

    Selects the most recent briefing whose ``briefing_date`` is strictly
    earlier than ``today_date``, so a same-day retry doesn't treat an
    earlier run today as yesterday.
    """
    recent = firestore_client.list_recent_briefings(limit=10)
    if not recent:
        return "（昨日無 briefing 紀錄，視今日為新系列起點）"

    if today_date:
        earlier = [b for b in recent if (b.briefing_date or "") < today_date]
    else:
        # No today_date provided — fall back to the second-most-recent.
        earlier = recent[1:]
    earlier = [b for b in earlier if (b.overview or b.top_changes or b.categories)]
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


def _previous_podcast_summary(today_date: Optional[str] = None) -> str:
    """Returns the most-recent-before-today *actually-aired* podcast script summary.

    Critical for repetition prevention — listeners track what was SAID, not what
    was in the briefing. Briefing might list 10 sections but podcast only deep-
    dives 3–5; W9 needs to know which ones already aired so today's script can
    skip them or only write delta.

    Uses ``get_latest_podcast_script_before(today_date)`` so same-day reruns of
    today never push the prior episode out of the lookup window.
    """
    if not today_date:
        # No today_date → fall back to "5 most recent, exclude index 0 as today's run"
        # to preserve old behavior, but log so we can spot callers that should
        # always pass briefing_date.
        recent = firestore_client.list_recent_podcast_scripts(limit=5)
        previous = next((p for p in recent[1:] if p.script), None)
    else:
        previous = firestore_client.get_latest_podcast_script_before(today_date)
        if previous and not previous.script:
            previous = None

    if not previous:
        return "（無前一集 podcast 紀錄，視今日為新系列起點）"

    parts: list[str] = []
    parts.append(f"上一集日期: {previous.briefing_date}")
    parts.append(f"上一集 episode: {previous.episode_title}")
    if previous.themes_covered:
        parts.append(f"上一集 themes_covered: {', '.join(previous.themes_covered)}")
    if previous.themes_skipped:
        parts.append(f"上一集 themes_skipped: {', '.join(previous.themes_skipped)}")
    if previous.segments:
        parts.append("上一集各段落（標題 + 前 200 字）：")
        for seg in previous.segments:
            head = (seg.text or "").strip().replace("\n", " ")[:200]
            parts.append(f"  - [{seg.segment_type}] {seg.title or '(no title)'}\n    {head}")
    return "\n".join(parts)


# Backward-compat alias retained for internal callers / tests; prefer the new name.
_yesterday_podcast_summary = _previous_podcast_summary


def _build_thread_groups_for_briefing(briefing) -> tuple[list[dict], list[dict]]:
    """Reach back into W7's thread + phase context for signals referenced in this
    briefing. Same shape as W8 ``_build_thread_groups`` but driven by referenced_signal_ids
    instead of a 24h candidate query.
    """
    sig_ids: list[str] = []
    seen: set[str] = set()
    for tc in briefing.top_changes:
        for sid in tc.referenced_signal_ids or []:
            if sid not in seen:
                seen.add(sid)
                sig_ids.append(sid)
    for cat in briefing.categories:
        for sec in cat.sections:
            for sid in sec.referenced_signal_ids or []:
                if sid not in seen:
                    seen.add(sid)
                    sig_ids.append(sid)
    if not sig_ids:
        return [], []

    signals = firestore_client.list_signals_by_ids(sig_ids)
    threaded: dict[str, list] = {}
    ungrouped: list = []
    for s in signals:
        if s.thread_id:
            threaded.setdefault(s.thread_id, []).append(s)
        else:
            ungrouped.append(s)

    thread_ids = list(threaded.keys())
    threads = firestore_client.list_story_threads_by_ids(thread_ids) if thread_ids else []
    threads_by_id = {t.thread_id: t for t in threads}
    phases_by_thread = (
        firestore_client.list_phases_for_threads(thread_ids) if thread_ids else {}
    )

    groups: list[dict] = []
    for tid, sigs in threaded.items():
        thread = threads_by_id.get(tid)
        phases = phases_by_thread.get(tid, [])
        sigs.sort(key=lambda s: (s.importance_score or 0), reverse=True)
        groups.append(
            {
                "thread": _thread_context_for_podcast(thread, tid),
                "phases": _phase_summaries_for_podcast(phases),
                "signals": [_signal_for_podcast(s) for s in sigs],
            }
        )
    # Same priority as W8: today's new development first, then by max importance.
    def group_priority(g: dict) -> tuple:
        sigs_c = g["signals"]
        any_new = any(not s.get("is_background_repeat") for s in sigs_c)
        max_imp = max((int(s.get("importance_score") or 0) for s in sigs_c), default=0)
        return (1 if any_new else 0, max_imp)

    groups.sort(key=group_priority, reverse=True)
    ungrouped_compact = [_signal_for_podcast(s) for s in ungrouped]
    return groups, ungrouped_compact


def _thread_context_for_podcast(thread, thread_id: str) -> dict:
    if not thread:
        return {"thread_id": thread_id, "title": "(thread missing)", "missing": True}
    return {
        "thread_id": thread.thread_id,
        "title": thread.title,
        "status": thread.status,
        "last_covered_in_podcast_at": thread.last_covered_in_podcast_at,
        "known_background": (thread.known_background or "")[:400],
        "today_delta": thread.today_delta,
        "do_not_repeat_points": (thread.do_not_repeat_points or [])[:5],
        "continuation_prompt_hint": thread.continuation_prompt_hint,
    }


def _phase_summaries_for_podcast(phases: list) -> list[dict]:
    if not phases:
        return []
    status_order = {"emerging": 0, "active": 1, "dormant": 2, "resolved": 3}
    return [
        {
            "phase_id": p.phase_id,
            "title": p.title,
            "status": p.status,
            "signal_count": p.signal_count,
            "novelty_reason": (p.novelty_reason or "")[:120],
        }
        for p in sorted(phases, key=lambda p: status_order.get(p.status, 9))
    ]


def _signal_for_podcast(signal) -> dict:
    flags = phase_flags_from_rationale(signal.adjudication_rationale)
    return {
        "signal_id": signal.signal_id,
        "title": signal.representative_title,
        "publisher": signal.representative_publisher,
        "importance_score": signal.importance_score,
        "what_happened": signal.what_happened,
        "why_matters": signal.why_matters,
        "thread_id": signal.thread_id,
        "phase_id": signal.phase_id,
        "today_delta": signal.today_delta,
        "is_background_repeat": signal.is_background_repeat,
        "thread_mismatch_suspected": flags["thread_mismatch_suspected"],
        "duplicate_suspected": flags["duplicate_suspected"],
    }


def _render_prompt(briefing, retry_feedback: str = "") -> str:
    template = _load_prompt()
    thread_groups, ungrouped = _build_thread_groups_for_briefing(briefing)
    background_repeat_count = sum(
        1 for g in thread_groups for s in g["signals"] if s.get("is_background_repeat")
    )
    return template.format(
        today_briefing_json=json.dumps(_briefing_to_compact(briefing), ensure_ascii=False, indent=2),
        yesterday_briefing_summary=_yesterday_briefing_summary(briefing.briefing_date),
        previous_podcast_summary=_previous_podcast_summary(briefing.briefing_date),
        thread_groups_json=json.dumps(thread_groups, ensure_ascii=False, indent=2),
        ungrouped_signals_json=json.dumps(ungrouped, ensure_ascii=False, indent=2),
        thread_count=len(thread_groups),
        ungrouped_count=len(ungrouped),
        background_repeat_count=background_repeat_count,
        retry_feedback=retry_feedback,
    )


def _call_script_model(
    prompt: str,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, int, int, str]:
    route = resolve_model_route("w9_podcast_script", model_overrides)
    if route.provider == "openai" and openai_client.is_ready:
        model = route.model
        payload, in_tok, out_tok = openai_client.generate_json(
            prompt,
            model=model,
            reasoning_effort=route.reasoning_effort or settings.PODCAST_SCRIPT_REASONING_EFFORT,
        )
        return payload, in_tok, out_tok, model
    model = route.model if route.provider == "gemini" else default_model_route("w9_podcast_script", "gemini").model
    payload, in_tok, out_tok = gemini_client.generate_json(prompt, model=model)
    return payload, in_tok, out_tok, model


def _validate_script_payload(payload: dict, briefing) -> dict:
    warnings: list[str] = []
    script = str(payload.get("script") or "").strip()
    if not script:
        raise ValueError("script is empty")

    if script.startswith("歡迎回到 Informative AI") and not script.startswith(MANDATORY_OPENING):
        script = MANDATORY_OPENING + script[len("歡迎回到 Informative AI"):].lstrip(" 。.\n")
        warnings.append("opening punctuation normalized")
    elif not script.startswith(MANDATORY_OPENING):
        script = f"{MANDATORY_OPENING}\n\n{script}"
        warnings.append("mandatory opening prepended")

    if not script.rstrip().endswith(MANDATORY_CLOSING):
        script = f"{script.rstrip()}\n\n{MANDATORY_CLOSING}"
        warnings.append("mandatory closing appended")

    word_count = _spoken_char_count(script)
    duration_estimate = float(payload.get("duration_estimate_minutes") or word_count / 350)
    if word_count < WORD_COUNT_TARGET_LOW or word_count > WORD_COUNT_TARGET_HIGH:
        warnings.append(
            f"word_count outside target range: {word_count} (target {WORD_COUNT_TARGET_LOW}-{WORD_COUNT_TARGET_HIGH})"
        )

    raw_segments = payload.get("segments") or []
    # Build a flat set of all signal ids from briefing
    sig_ids = set()
    for cat in briefing.categories:
        for sec in cat.sections:
            for sid in sec.referenced_signal_ids or []:
                sig_ids.add(sid)
    for tc in briefing.top_changes:
        for sid in tc.referenced_signal_ids or []:
            sig_ids.add(sid)

    segments: list[dict] = []
    if isinstance(raw_segments, list):
        for idx, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                continue
            seg_type = str(raw.get("segment_type") or "theme")
            ref_ids = [str(x) for x in (raw.get("referenced_signal_ids") or []) if str(x) in sig_ids]
            segments.append({
                "segment_id": str(raw.get("segment_id") or f"seg_{idx+1:02d}"),
                "position": int(raw.get("position") or idx + 1),
                "segment_type": seg_type,
                "title": str(raw.get("title") or "")[:100],
                "text": str(raw.get("text") or "")[:5000],
                "duration_estimate_seconds": int(raw.get("duration_estimate_seconds") or 0),
                "referenced_signal_ids": ref_ids[:20],
                "theme": str(raw.get("theme") or "") or None,
            })
    if not segments:
        warnings.append("segments missing or empty")

    themes_covered = [str(x) for x in (payload.get("themes_covered") or [])]
    raw_skipped = payload.get("themes_skipped") or []
    themes_skipped: list[str] = []
    for item in raw_skipped:
        if isinstance(item, dict):
            themes_skipped.append(str(item.get("theme") or ""))
        else:
            themes_skipped.append(str(item))
    themes_skipped = [x for x in themes_skipped if x]

    show_notes = str(payload.get("show_notes") or "")[:5000]
    if not show_notes:
        warnings.append("show_notes missing or empty")

    raw_episode_title = str(payload.get("episode_title") or "").strip()
    if not raw_episode_title:
        raw_episode_title = _fallback_title_from_briefing(briefing)
        warnings.append("episode_title fallback used")
    episode_title = format_episode_title(briefing.briefing_date, raw_episode_title)

    return {
        "episode_title": episode_title,
        "script": script,
        "word_count": word_count,
        "duration_estimate_minutes": round(duration_estimate, 1),
        "segments": segments,
        "themes_covered": themes_covered,
        "themes_skipped": themes_skipped,
        "skipped_repetition_count": int(payload.get("skipped_repetition_count") or 0),
        "show_notes": show_notes,
        "validation_warnings": warnings,
    }


def _generate_script_with_retry(
    briefing,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict, dict, int, int, str, int]:
    """Run prompt + LLM + validation with one retry on validation failure.

    Returns (validated, raw_payload, input_tokens, output_tokens, model_used, retry_count).
    Raises on second failure. Mirrors W8 briefing's retry pattern.
    """
    total_in = 0
    total_out = 0
    model_used = ""
    last_error = ""
    for attempt in range(2):
        retry_feedback = (
            f"\n⚠️ 上一次嘗試失敗：{last_error}\n請修正後重新輸出完整 JSON。\n"
            if attempt > 0 and last_error
            else ""
        )
        prompt = _render_prompt(briefing, retry_feedback=retry_feedback)
        payload, in_tok, out_tok, model_used = _call_script_model(prompt, model_overrides)
        total_in += in_tok
        total_out += out_tok
        try:
            validated = _validate_script_payload(payload, briefing)
            return validated, payload, total_in, total_out, model_used, attempt
        except ValueError as exc:
            last_error = str(exc)[:200]
            logger.warning(
                "podcast_script_validation_failed attempt=%d error=%s", attempt + 1, last_error
            )
    raise ValueError(
        f"podcast script validation failed after retry (last error: {last_error})"
    )


def generate_daily_podcast_script(
    briefing_id: Optional[str] = None,
    write_google_doc: bool = True,
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    generated_at = utc_now_iso()
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "podcast_script",
        run_bucket,
        {
            "briefing_id": briefing_id,
            "write_google_doc": write_google_doc,
            "run_bucket": run_bucket,
            "model_overrides": validate_model_overrides(model_overrides),
        },
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W9 Podcast Script", run_bucket)
        return out

    try:
        if briefing_id:
            briefing = firestore_client.get_briefing_by_id(briefing_id)
            if not briefing:
                raise ValueError(f"briefing not found: {briefing_id}")
        else:
            recent = firestore_client.list_recent_briefings(limit=1)
            if not recent:
                raise ValueError("no briefing available")
            briefing = recent[0]

        if not briefing.categories and not briefing.top_changes:
            raise ValueError(f"briefing {briefing.briefing_id} has no content")

        script_id = _generate_script_id(briefing.briefing_date)
        validated, payload, input_tokens, output_tokens, model_used, retry_count = (
            _generate_script_with_retry(briefing, model_overrides)
        )
        # Record retry observability inside validation_warnings so it persists on the
        # script document — n8n/dashboard can grep retry rate without a schema change.
        if retry_count > 0:
            validated["validation_warnings"].append(
                f"script_retry_count={retry_count}"
            )

        segments = [ScriptSegment(**s) for s in validated["segments"]]

        # P0 fix: cost computed per actual model used (single source of truth)
        cost_usd = compute_llm_cost(model_used, input_tokens, output_tokens)

        google_doc_id = None
        google_doc_url = None
        if write_google_doc:
            try:
                from app.services.podcast_doc_writer import write_podcast_script_to_doc
                google_doc_id, google_doc_url = write_podcast_script_to_doc(
                    briefing_date=briefing.briefing_date,
                    episode_title=validated["episode_title"],
                    script=validated["script"],
                    segments=segments,
                    show_notes=validated["show_notes"],
                    themes_covered=validated["themes_covered"],
                    word_count=validated["word_count"],
                    duration_estimate=validated["duration_estimate_minutes"],
                    validation_warnings=validated["validation_warnings"],
                )
            except Exception as exc:
                logger.warning("Podcast Google Doc write skipped: %s", exc)

        podcast = RssPodcastScript(
            script_id=script_id,
            briefing_id=briefing.briefing_id,
            briefing_date=briefing.briefing_date,
            generated_at=generated_at,
            episode_title=validated["episode_title"],
            script=validated["script"],
            word_count=validated["word_count"],
            duration_estimate_minutes=validated["duration_estimate_minutes"],
            segments=segments,
            themes_covered=validated["themes_covered"],
            themes_skipped=validated["themes_skipped"],
            skipped_repetition_count=validated["skipped_repetition_count"],
            show_notes=validated["show_notes"],
            validation_warnings=validated["validation_warnings"],
            google_doc_id=google_doc_id,
            google_doc_url=google_doc_url,
            model=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost_usd, 6),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        firestore_client.upsert_podcast_script(podcast)
        result = podcast.model_dump()
        result["run_bucket"] = run_bucket
        result["workflow_run_id"] = workflow_run_id
        result["skipped_duplicate"] = False
        result["script_retry_count"] = retry_count
        result["model_routing"] = effective_model_routes(model_overrides, ["w9_podcast_script"])
        add_log_summary(result, _compose_podcast_script_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _compose_podcast_script_log_summary(result: dict[str, object]) -> list[str]:
    segments = result.get("segments") if isinstance(result.get("segments"), list) else []
    retry_count = int(result.get("script_retry_count") or 0)
    doc_status = "已寫 podcast Google Doc" if result.get("google_doc_url") else "未寫 podcast Google Doc"
    lines = [
        tagged(
            "ok",
            (
                f"W9 Script 產生 {result.get('word_count', 0)} 字、{len(segments)} 個 segment；"
                f"script_id={result.get('script_id') or 'unknown'}。"
            ),
        ),
        tagged("new", "thread / phase context 與上一集 podcast 摘要已注入 prompt，用來避免重講背景。"),
    ]
    if retry_count:
        lines.append(tagged("warn", f"script validation retry {retry_count} 次，請抽查 JSON 格式與 segments。"))
    else:
        lines.append(tagged("ok", "script validation 一次通過。"))
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
