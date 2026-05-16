from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.clients.firestore_client import firestore_client

router = APIRouter()


def _since_iso(days: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@router.get("/api/threads")
def list_threads(
    lookback_days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=200, ge=1, le=500),
):
    """List recent story threads with phase counts for the viewer sidebar."""
    threads = firestore_client.list_recent_story_threads(
        _since_iso(lookback_days), limit=limit
    )
    if not threads:
        return []
    phases_map = firestore_client.list_phases_for_threads([t.thread_id for t in threads])

    result = []
    for thread in threads:
        phases = phases_map.get(thread.thread_id, [])
        # Count flagged signals — needs phase signal_ids; without loading every signal,
        # we approximate by counting log entries mentioning the flag types.
        mismatch_flag_count = sum(
            1
            for phase in phases
            for entry in phase.llm_decision_log
            if "different_thread" in entry
        )
        background_repeat_count = sum(
            1
            for phase in phases
            for entry in phase.llm_decision_log
            if "background_repeat" in entry
        )
        result.append(
            {
                "thread_id": thread.thread_id,
                "title": thread.title,
                "status": thread.status,
                "active_since": thread.active_since,
                "last_seen_at": thread.last_seen_at,
                "last_covered_in_podcast_at": thread.last_covered_in_podcast_at,
                "signal_count": len(thread.signal_ids),
                "phase_count": len(phases),
                "mismatch_flag_count": mismatch_flag_count,
                "background_repeat_count": background_repeat_count,
            }
        )
    result.sort(key=lambda t: t["last_seen_at"] or "", reverse=True)
    return result


@router.get("/api/threads/{thread_id}")
def get_thread(thread_id: str):
    """Full thread + nested phases + signal summaries for the phase tree view."""
    thread = firestore_client.get_story_thread_by_id(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail=f"thread not found: {thread_id}")
    phases = firestore_client.list_phases_for_thread(thread_id)

    # Collect all signal ids across phases (deduped) for batch fetch.
    all_signal_ids: list[str] = []
    seen: set[str] = set()
    for phase in phases:
        for sid in phase.signal_ids:
            if sid not in seen:
                seen.add(sid)
                all_signal_ids.append(sid)

    signals = firestore_client.list_signals_by_ids(all_signal_ids) if all_signal_ids else []
    signals_by_id = {s.signal_id: s for s in signals}

    def signal_summary(sid: str) -> Optional[dict]:
        s = signals_by_id.get(sid)
        if not s:
            return {"signal_id": sid, "missing": True}
        return {
            "signal_id": s.signal_id,
            "title": s.representative_title,
            "url": s.representative_url,
            "publisher": s.representative_publisher,
            "published_at": s.representative_published_at,
            "importance_score": s.importance_score,
            "is_background_repeat": s.is_background_repeat,
            "adjudication_decision": s.adjudication_decision,
            "adjudication_confidence": s.adjudication_confidence,
            "what_happened": s.what_happened,
            "primary_theme": s.primary_theme,
        }

    phase_views = []
    for phase in phases:
        phase_views.append(
            {
                "phase_id": phase.phase_id,
                "title": phase.title,
                "status": phase.status,
                "parent_phase_id": phase.parent_phase_id,
                "child_phase_ids": phase.child_phase_ids,
                "signal_count": phase.signal_count,
                "key_entities": phase.key_entities,
                "summary": phase.summary,
                "novelty_reason": phase.novelty_reason,
                "llm_decision_log": phase.llm_decision_log,
                "opened_at": phase.opened_at,
                "last_advanced_at": phase.last_advanced_at,
                "signals": [signal_summary(sid) for sid in phase.signal_ids],
            }
        )

    return {
        "thread": {
            "thread_id": thread.thread_id,
            "title": thread.title,
            "status": thread.status,
            "active_since": thread.active_since,
            "last_seen_at": thread.last_seen_at,
            "last_covered_in_podcast_at": thread.last_covered_in_podcast_at,
            "key_entities": thread.key_entities,
            "known_background": thread.known_background,
            "today_delta": thread.today_delta,
            "novelty_score": thread.novelty_score,
            "phases_initialized_at": thread.phases_initialized_at,
        },
        "phases": phase_views,
    }
