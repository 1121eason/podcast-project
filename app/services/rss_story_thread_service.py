import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.clients.gemini_client import gemini_client
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.core.logging import logger
from app.models.signal import RssSignal, RssStoryThread, RssThreadPhase
from app.services.llm_cost_utils import compute_llm_cost
from app.services.log_summary_utils import (
    add_duplicate_log_summary,
    add_log_summary,
    cost_text,
    sample_values,
    seconds_text,
    tagged,
    token_text,
)
from app.services.model_routing_service import (
    effective_model_routes,
    resolve_model_route,
    validate_model_overrides,
)
from app.services.signal_v2_utils import (
    compact_text,
    cosine_similarity,
    decay_centroid,
    importance_bucket,
    phase_flags_from_rationale,
    short_hash,
    thread_memory_hash,
    utc_now_iso,
)
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

PHASE_DECISIONS = {
    "continues_core",
    "new_axis",
    "background_repeat",
    "different_thread",
    "duplicate_suspected",
}


def consolidate_daily(
    since_hours: int = 36,
    story_lookback_days: int = 30,
    max_threads: int = 200,
    run_bucket: Optional[str] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    request_payload = {
        "since_hours": since_hours,
        "story_lookback_days": story_lookback_days,
        "max_threads": max_threads,
        "run_bucket": run_bucket,
        "model_overrides": validate_model_overrides(model_overrides),
    }
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "daily_consolidation",
        run_bucket,
        request_payload,
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W7 Daily Consolidation", run_bucket)
        return out

    try:
        result = _consolidate_daily_inner(since_hours, story_lookback_days, max_threads, model_overrides)
        result.update(
            {
                "run_bucket": run_bucket,
                "workflow_run_id": workflow_run_id,
                "skipped_duplicate": False,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
        add_log_summary(result, _compose_daily_consolidation_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _consolidate_daily_inner(
    since_hours: int,
    story_lookback_days: int,
    max_threads: int,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    since = _since_iso(since_hours)
    thread_since = _since_iso(story_lookback_days * 24)
    signals = firestore_client.list_recent_signals(since, limit=2000)
    candidates = [s for s in signals if s.signal_status in {"supported", "confirmed", "promoted", "provisional"}]
    # Composite story priority — keep importance influence but no longer dominant.
    # See _story_priority_key for the tuple definition.
    candidates.sort(key=_story_priority_key, reverse=True)
    candidates = candidates[:max_threads]
    threads = firestore_client.list_recent_story_threads(thread_since, limit=max_threads)
    threads_by_id = {t.thread_id: t for t in threads}
    signals_to_update: list[RssSignal] = []
    threads_updated: dict[str, RssStoryThread] = {}
    model_refined_count = 0
    refine_llm_input_tokens = 0
    refine_llm_output_tokens = 0

    for signal in candidates:
        thread = _find_or_create_thread(signal, list(threads_by_id.values()))
        _apply_signal_to_thread(thread, signal)
        signal.thread_id = thread.thread_id
        signal.today_delta = _today_delta_for_signal(signal)
        signal.novelty_score = _novelty_score(signal, thread)
        if model_refined_count < 10 and _should_refine_thread_with_model(thread, signal):
            refined, in_tokens, out_tokens = _refine_thread_with_model(thread, signal, model_overrides)
            refine_llm_input_tokens += in_tokens
            refine_llm_output_tokens += out_tokens
            if refined:
                model_refined_count += 1
                signal.today_delta = thread.today_delta
                signal.novelty_score = thread.novelty_score
        signal.last_consolidated_at = utc_now_iso()
        signals_to_update.append(signal)
        threads_by_id[thread.thread_id] = thread
        threads_updated[thread.thread_id] = thread

    # Phase assignment pass — group signals by thread, assign each to a phase
    # (heuristic first, LLM batch for ambiguous). See _assign_phases_for_thread.
    phase_stats: dict[str, int] = defaultdict(int)
    phases_to_upsert: dict[str, RssThreadPhase] = {}
    signals_by_thread: dict[str, list[RssSignal]] = defaultdict(list)
    for signal in signals_to_update:
        if signal.thread_id:
            signals_by_thread[signal.thread_id].append(signal)

    if signals_by_thread:
        existing_phases_map = firestore_client.list_phases_for_threads(list(signals_by_thread.keys()))
        for thread_id, thread_signals in signals_by_thread.items():
            thread = threads_by_id.get(thread_id)
            if not thread:
                continue
            existing_phases = existing_phases_map.get(thread_id, [])
            phases = _bootstrap_seed_phase_if_needed(thread, existing_phases)
            updated_phases, run_stats = _assign_phases_for_thread(
                thread,
                thread_signals,
                phases,
                model_overrides,
            )
            for phase in updated_phases:
                phases_to_upsert[phase.phase_id] = phase
            for k, v in run_stats.items():
                phase_stats[k] += v

    firestore_client.upsert_story_threads(list(threads_updated.values()))
    firestore_client.upsert_rss_signals(signals_to_update)
    if phases_to_upsert:
        firestore_client.upsert_thread_phases(list(phases_to_upsert.values()))

    result = {
        "since_hours": since_hours,
        "story_lookback_days": story_lookback_days,
        "signals_considered": len(candidates),
        "threads_updated": len(threads_updated),
        "threads_created": sum(1 for t in threads_updated.values() if len(t.signal_ids) == 1),
        "today_delta_count": sum(1 for s in signals_to_update if s.today_delta),
        "model_refined_count": model_refined_count,
        "refine_llm_input_tokens": refine_llm_input_tokens,
        "refine_llm_output_tokens": refine_llm_output_tokens,
        "phases_upserted": len(phases_to_upsert),
        "phases_created": phase_stats.get("phases_created", 0),
        "phases_advanced": phase_stats.get("phases_advanced", 0),
        "phase_heuristic_assignments": phase_stats.get("phase_heuristic_assignments", 0),
        "phase_w4_evidence_assignments": phase_stats.get("phase_w4_evidence_assignments", 0),
        "phase_llm_calls": phase_stats.get("phase_llm_calls", 0),
        "phase_llm_input_tokens": phase_stats.get("phase_llm_input_tokens", 0),
        "phase_llm_output_tokens": phase_stats.get("phase_llm_output_tokens", 0),
        "phase_llm_invalid_id_count": phase_stats.get("phase_llm_invalid_id_count", 0),
        "background_repeat_count": phase_stats.get("background_repeat_count", 0),
        "thread_mismatch_flagged_count": phase_stats.get("thread_mismatch_flagged_count", 0),
        "duplicate_suspected_count": phase_stats.get("duplicate_suspected_count", 0),
        "thread_samples": [t.title or t.thread_id for t in list(threads_updated.values())[:3]],
        "phase_samples": [p.title or p.phase_id for p in list(phases_to_upsert.values())[:3]],
        "thread_mismatch_samples": [
            s.signal_id
            for s in signals_to_update
            if phase_flags_from_rationale(s.adjudication_rationale)["thread_mismatch_suspected"]
        ][:3],
        "model_routing": effective_model_routes(
            model_overrides,
            ["w7_thread_refine", "w7_phase_assignment"],
        ),
    }
    result["phase_llm_cost_usd"] = round(
        compute_llm_cost(
            resolve_model_route("w7_phase_assignment", model_overrides).model,
            int(result["phase_llm_input_tokens"]),
            int(result["phase_llm_output_tokens"]),
        ),
        6,
    )
    result["refine_llm_cost_usd"] = round(
        compute_llm_cost(
            resolve_model_route("w7_thread_refine", model_overrides).model,
            int(result["refine_llm_input_tokens"]),
            int(result["refine_llm_output_tokens"]),
        ),
        6,
    )
    return result


def _compose_daily_consolidation_log_summary(result: dict[str, object]) -> list[str]:
    thread_samples = sample_values(result.get("thread_samples") if isinstance(result.get("thread_samples"), list) else [])
    phase_samples = sample_values(result.get("phase_samples") if isinstance(result.get("phase_samples"), list) else [])
    mismatch_samples = sample_values(
        result.get("thread_mismatch_samples") if isinstance(result.get("thread_mismatch_samples"), list) else []
    )
    lines = [
        tagged(
            "ok",
            (
                f"W7 整合 {result.get('signals_considered', 0)} 個 signal 到 {result.get('threads_updated', 0)} 條 thread；"
                f"新 thread {result.get('threads_created', 0)}、今日 delta {result.get('today_delta_count', 0)}、"
                f"Pro refine {result.get('model_refined_count', 0)} 次。"
            ),
        ),
        tagged(
            "new",
            (
                f"phase 更新 {result.get('phases_upserted', 0)} 個，新敘事軸 {result.get('phases_created', 0)}，"
                f"樣本：{phase_samples or thread_samples or '無'}。"
            ),
        ),
        tagged(
            "repeat",
            (
                f"background_repeat {result.get('background_repeat_count', 0)}、"
                f"duplicate_suspected {result.get('duplicate_suspected_count', 0)}。"
            ),
        ),
    ]
    mismatch_count = int(result.get("thread_mismatch_flagged_count") or 0)
    if mismatch_count:
        lines.append(
            tagged(
                "warn",
                f"{mismatch_count} 個 signal 疑似掛錯 thread：{mismatch_samples or '詳見 W7 viewer mismatch filter'}。",
            )
        )
    lines.append(
        tagged(
            "cost",
            (
                f"phase LLM 成本 {cost_text(result.get('phase_llm_cost_usd'))}，"
                f"refine LLM 成本 {cost_text(result.get('refine_llm_cost_usd'))}，"
                f"{result.get('phase_llm_calls', 0)} 次 call，"
                f"phase {token_text(result.get('phase_llm_input_tokens'), result.get('phase_llm_output_tokens'))}，"
                f"refine {token_text(result.get('refine_llm_input_tokens'), result.get('refine_llm_output_tokens'))}。"
            ),
        )
    )
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines


def _story_priority_key(signal: RssSignal) -> tuple:
    """Composite priority replacing raw importance-led sort.

    Order: W4 evidence > recency > signal status > publisher tier > importance bucket.
    Importance still tie-breaks via bucket but no longer dominates.
    """
    has_w4_evidence = 1 if signal.adjudication_decision in {"same_event", "same_thread"} else 0
    recency = signal.window_end or signal.generated_at or ""
    status_weight = {
        "confirmed": 4,
        "supported": 3,
        "promoted": 2,
        "provisional": 1,
    }.get(signal.signal_status or "", 0)
    tier_weight = {"tier1": 3, "other": 2, "aggregator": 1, "": 0}.get(signal.publisher_tier or "", 0)
    bucket_weight = {"critical": 4, "high": 3, "medium": 2, "noise": 1}.get(
        importance_bucket(signal.importance_score), 0
    )
    return (has_w4_evidence, recency, status_weight, tier_weight, bucket_weight)


def _find_or_create_thread(signal: RssSignal, threads: list[RssStoryThread]) -> RssStoryThread:
    if signal.thread_id:
        for thread in threads:
            if thread.thread_id == signal.thread_id:
                return thread
    best = None
    best_score = 0.0
    for thread in threads:
        score = max(
            cosine_similarity(signal.event_centroid, thread.event_centroid),
            cosine_similarity(signal.context_centroid, thread.context_centroid),
        )
        if score > best_score:
            best_score = score
            best = thread
    if best and best_score >= settings.SIGNAL_MATCH_REVIEW_THRESHOLD:
        return best
    thread_id = f"thread_{short_hash(signal.signal_id + signal.representative_title, 12)}"
    now = utc_now_iso()
    return RssStoryThread(
        thread_id=thread_id,
        title=signal.representative_title[:120],
        active_since=signal.generated_at or now,
        last_seen_at=signal.window_end or now,
        key_entities=signal.key_entities or [],
        event_centroid=signal.event_centroid,
        context_centroid=signal.context_centroid,
        known_background=(signal.what_happened or signal.representative_summary or signal.representative_title)[:500],
    )


def _apply_signal_to_thread(thread: RssStoryThread, signal: RssSignal) -> None:
    if signal.signal_id not in thread.signal_ids:
        thread.signal_ids.append(signal.signal_id)
    thread.last_seen_at = signal.window_end or utc_now_iso()
    thread.key_entities = _unique([*thread.key_entities, *(signal.key_entities or [])])[:12]
    thread.event_centroid = decay_centroid(thread.event_centroid, signal.event_centroid, settings.CENTROID_DECAY)
    thread.context_centroid = decay_centroid(thread.context_centroid, signal.context_centroid, settings.CENTROID_DECAY)
    delta = _today_delta_for_signal(signal)
    if delta and delta not in thread.latest_developments:
        thread.latest_developments = [delta, *thread.latest_developments][:12]
    if thread.known_background and thread.known_background not in thread.covered_points:
        thread.covered_points = [thread.known_background, *thread.covered_points][:20]
    thread.today_delta = delta
    thread.novelty_score = max(thread.novelty_score, _novelty_score(signal, thread))
    thread.do_not_repeat_points = thread.covered_points[:10]
    thread.continuation_prompt_hint = (
        f"延續先前提到的「{thread.title}」，今天的新變化是：{delta}"
        if delta
        else f"延續先前提到的「{thread.title}」，只補充最新變化，不重講背景。"
    )
    thread.thread_memory_hash = thread_memory_hash(
        [thread.known_background, thread.covered_points, thread.latest_developments, thread.today_delta]
    )


def _today_delta_for_signal(signal: RssSignal) -> str:
    return compact_text(
        signal.what_happened,
        signal.representative_title,
        signal.why_matters,
        limit=320,
    )


def _novelty_score(signal: RssSignal, thread: RssStoryThread) -> float:
    if not thread.covered_points:
        return 1.0
    delta = _today_delta_for_signal(signal)
    similarity = max(
        (cosine_similarity(signal.context_centroid, thread.context_centroid) or 0.0),
        0.0,
    )
    base = 1.0 - min(0.8, similarity * 0.6)
    if delta and all(delta[:60] not in point for point in thread.covered_points):
        base += 0.2
    return round(max(0.0, min(1.0, base)), 3)


def _unique(values: list[str]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _should_refine_thread_with_model(thread: RssStoryThread, signal: RssSignal) -> bool:
    if len(thread.signal_ids) <= 1:
        return False
    if importance_bucket(signal.importance_score) == "critical":
        return True
    return bool(signal.today_delta and (signal.novelty_score or 0.0) >= 0.65)


def _refine_thread_with_model(
    thread: RssStoryThread,
    signal: RssSignal,
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[bool, int, int]:
    prompt = (
        "You update story-thread memory for a daily business/geopolitical podcast.\n"
        "Return JSON only. Keep Traditional Chinese. Do not repeat background.\n"
        "Fields: known_background string, covered_points list, latest_developments list, "
        "open_questions list, today_delta string, novelty_score number 0-1, "
        "do_not_repeat_points list, continuation_prompt_hint string.\n\n"
        f"Existing thread title: {thread.title}\n"
        f"Known background: {thread.known_background}\n"
        f"Covered points: {thread.covered_points[:12]}\n"
        f"Latest developments: {thread.latest_developments[:8]}\n"
        f"Signal title: {signal.representative_title}\n"
        f"Signal what_happened: {signal.what_happened}\n"
        f"Signal why_matters: {signal.why_matters}\n"
        f"Signal what_next: {signal.what_next}\n"
        f"Signal importance: {signal.importance_score}\n"
    )
    try:
        route = resolve_model_route("w7_thread_refine", model_overrides)
        payload, input_tokens, output_tokens = gemini_client.generate_json(
            prompt,
            model=route.model,
        )
    except Exception:
        return False, 0, 0

    def as_list(field: str, max_len: int) -> list[str]:
        value = payload.get(field) or []
        if not isinstance(value, list):
            return []
        return [str(x).strip()[:300] for x in value if str(x).strip()][:max_len]

    thread.known_background = str(payload.get("known_background") or thread.known_background).strip()[:800]
    covered_points = as_list("covered_points", 20)
    latest_developments = as_list("latest_developments", 12)
    open_questions = as_list("open_questions", 10)
    do_not_repeat_points = as_list("do_not_repeat_points", 12)
    if covered_points:
        thread.covered_points = covered_points
    if latest_developments:
        thread.latest_developments = latest_developments
    if open_questions:
        thread.open_questions = open_questions
    thread.today_delta = str(payload.get("today_delta") or thread.today_delta).strip()[:500]
    try:
        thread.novelty_score = max(0.0, min(1.0, float(payload.get("novelty_score"))))
    except (TypeError, ValueError):
        pass
    if do_not_repeat_points:
        thread.do_not_repeat_points = do_not_repeat_points
    hint = str(payload.get("continuation_prompt_hint") or "").strip()
    if hint:
        thread.continuation_prompt_hint = hint[:500]
    thread.thread_memory_hash = thread_memory_hash(
        [thread.known_background, thread.covered_points, thread.latest_developments, thread.today_delta]
    )
    return True, int(input_tokens or 0), int(output_tokens or 0)


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ============================================================
# Phase tree (W7 Layer 2) — see docs/rss_ai_research_plan.md §7
# ============================================================


def _bootstrap_seed_phase_if_needed(
    thread: RssStoryThread, existing_phases: list[RssThreadPhase]
) -> list[RssThreadPhase]:
    """Lazy backfill: create one seed phase mirroring the thread on first touch.

    No LLM. Returns the (possibly augmented) phase list. Sets phases_initialized_at.
    """
    if existing_phases or thread.phases_initialized_at:
        if existing_phases and not thread.phases_initialized_at:
            thread.phases_initialized_at = utc_now_iso()
        return existing_phases
    now = utc_now_iso()
    seed_id = f"phase_{short_hash(thread.thread_id + '_seed', 12)}"
    seed = RssThreadPhase(
        phase_id=seed_id,
        thread_id=thread.thread_id,
        title=thread.title or "(seed)",
        status="active" if len(thread.signal_ids) >= 2 else "emerging",
        signal_ids=list(thread.signal_ids),
        signal_count=len(thread.signal_ids),
        key_entities=list(thread.key_entities or []),
        summary=thread.known_background[:500],
        novelty_reason="bootstrap seed phase",
        event_centroid=list(thread.event_centroid) if thread.event_centroid else None,
        context_centroid=list(thread.context_centroid) if thread.context_centroid else None,
        centroid_updated_at=now,
        opened_at=thread.active_since or now,
        last_advanced_at=thread.last_seen_at or now,
    )
    thread.phases_initialized_at = now
    return [seed]


def _assign_phases_for_thread(
    thread: RssStoryThread,
    new_signals: list[RssSignal],
    existing_phases: list[RssThreadPhase],
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[list[RssThreadPhase], dict[str, int]]:
    """Assign each signal to a phase. Returns (all phases touched, stats)."""
    stats: dict[str, int] = defaultdict(int)
    phases_by_id: dict[str, RssThreadPhase] = {p.phase_id: p for p in existing_phases}
    touched: set[str] = set()

    # Skip signals that already have a phase_id assigned (e.g. by W4 in future).
    pending = [s for s in new_signals if not s.phase_id]
    ambiguous: list[RssSignal] = []

    for signal in pending:
        # Step 1: W4 evidence shortcut — honor adjudication that already paid for an LLM call.
        # Guard: only apply if W4's candidate_thread_id matches the current thread, otherwise
        # the W4 evidence is about a relationship inside a *different* thread and using it
        # here would silently put the signal in the wrong phase.
        if (
            signal.adjudication_decision in {"same_thread", "same_event"}
            and signal.adjudication_candidate_thread_id == thread.thread_id
            and phases_by_id
        ):
            best_phase = _closest_phase_by_centroid(signal, list(phases_by_id.values()))
            if best_phase:
                _apply_signal_to_phase(
                    best_phase, signal, decision="continues_core", reason="W4 same_thread evidence"
                )
                touched.add(best_phase.phase_id)
                stats["phase_w4_evidence_assignments"] += 1
                continue
        # Step 2: cosine pre-filter
        if phases_by_id:
            best_phase, best_score = _best_phase_by_event_cosine(signal, list(phases_by_id.values()))
            if best_phase and best_score >= settings.PHASE_COSINE_AUTO_THRESHOLD:
                _apply_signal_to_phase(
                    best_phase,
                    signal,
                    decision="continues_core",
                    reason=f"cosine={best_score:.3f}",
                )
                touched.add(best_phase.phase_id)
                stats["phase_heuristic_assignments"] += 1
                continue
        ambiguous.append(signal)

    # Step 3: LLM batch — one call per thread that has ambiguous signals.
    if ambiguous:
        try:
            decisions, in_tokens, out_tokens = _llm_assign_phases(
                thread, ambiguous, list(phases_by_id.values()), model_overrides
            )
            stats["phase_llm_calls"] += 1
            stats["phase_llm_input_tokens"] += in_tokens
            stats["phase_llm_output_tokens"] += out_tokens
        except Exception as exc:
            logger.warning("phase_assignment_llm_failed thread=%s err=%s", thread.thread_id, exc)
            decisions = {}
        for signal in ambiguous:
            decision_dict = decisions.get(signal.signal_id) or {}
            phase = _route_phase_decision(
                signal, decision_dict, phases_by_id, thread, stats, touched
            )
            if phase:
                touched.add(phase.phase_id)

    # Step 4: status transitions.
    # Run over ALL phases (not just touched) so 7-day-stale phases can flip to dormant.
    # Any phase whose status actually changes must also be persisted.
    today = utc_now_iso()
    for phase in phases_by_id.values():
        before = phase.status
        _assign_phase_status(phase, today)
        if before != phase.status:
            touched.add(phase.phase_id)
            if before == "emerging" and phase.status == "active":
                stats["phases_advanced"] += 1

    return [phases_by_id[pid] for pid in touched], dict(stats)


def _closest_phase_by_centroid(
    signal: RssSignal, phases: list[RssThreadPhase]
) -> Optional[RssThreadPhase]:
    best = None
    best_score = -1.0
    for phase in phases:
        score = max(
            cosine_similarity(signal.event_centroid, phase.event_centroid),
            cosine_similarity(signal.context_centroid, phase.context_centroid),
        )
        if score > best_score:
            best = phase
            best_score = score
    return best


def _best_phase_by_event_cosine(
    signal: RssSignal, phases: list[RssThreadPhase]
) -> tuple[Optional[RssThreadPhase], float]:
    best = None
    best_score = 0.0
    for phase in phases:
        score = cosine_similarity(signal.event_centroid, phase.event_centroid)
        if score > best_score:
            best = phase
            best_score = score
    return best, best_score


def _most_recent_active_phase(phases_by_id: dict[str, RssThreadPhase]) -> Optional[RssThreadPhase]:
    actives = [p for p in phases_by_id.values() if p.status in {"active", "emerging"}]
    if not actives:
        actives = list(phases_by_id.values())
    if not actives:
        return None
    actives.sort(key=lambda p: p.last_advanced_at or p.opened_at or "", reverse=True)
    return actives[0]


def _apply_signal_to_phase(
    phase: RssThreadPhase,
    signal: RssSignal,
    decision: str,
    reason: str,
    advance: bool = True,
) -> None:
    if signal.signal_id not in phase.signal_ids:
        phase.signal_ids.append(signal.signal_id)
    phase.signal_count = len(phase.signal_ids)
    signal.phase_id = phase.phase_id
    now = utc_now_iso()
    if advance:
        phase.event_centroid = decay_centroid(
            phase.event_centroid, signal.event_centroid, settings.CENTROID_DECAY
        )
        phase.context_centroid = decay_centroid(
            phase.context_centroid, signal.context_centroid, settings.CENTROID_DECAY
        )
        phase.centroid_updated_at = now
        phase.last_advanced_at = now
        for entity in signal.key_entities or []:
            if entity and entity not in phase.key_entities:
                phase.key_entities.append(entity)
        phase.key_entities = phase.key_entities[:12]
    log_entry = f"[{now[:19]}] {decision}: {reason}"[:300]
    phase.llm_decision_log = [log_entry, *phase.llm_decision_log][:3]


def _create_phase(
    thread: RssStoryThread,
    seed_signal: RssSignal,
    title: str,
    parent_phase_id: Optional[str],
    novelty_reason: str,
) -> RssThreadPhase:
    now = utc_now_iso()
    phase_id = f"phase_{short_hash(thread.thread_id + seed_signal.signal_id + now, 12)}"
    return RssThreadPhase(
        phase_id=phase_id,
        thread_id=thread.thread_id,
        title=title[:120] or seed_signal.representative_title[:120],
        status="emerging",
        parent_phase_id=parent_phase_id,
        signal_ids=[],
        signal_count=0,
        key_entities=list(seed_signal.key_entities or [])[:12],
        summary=(seed_signal.what_happened or seed_signal.representative_summary or "")[:500],
        novelty_reason=novelty_reason[:300],
        event_centroid=list(seed_signal.event_centroid) if seed_signal.event_centroid else None,
        context_centroid=list(seed_signal.context_centroid) if seed_signal.context_centroid else None,
        centroid_updated_at=now,
        opened_at=now,
        last_advanced_at=now,
    )


def _route_phase_decision(
    signal: RssSignal,
    decision_dict: dict[str, object],
    phases_by_id: dict[str, RssThreadPhase],
    thread: RssStoryThread,
    stats: dict[str, int],
    touched: set[str],
) -> Optional[RssThreadPhase]:
    raw_decision = str(decision_dict.get("decision") or "").strip()
    decision = raw_decision if raw_decision in PHASE_DECISIONS else "continues_core"
    reason = str(decision_dict.get("novelty_reason") or "")[:300]
    target_id = decision_dict.get("phase_id")
    target = phases_by_id.get(str(target_id)) if target_id else None

    if decision == "new_axis":
        new_title = str(decision_dict.get("new_phase_title") or signal.representative_title)
        parent_id = decision_dict.get("parent_phase_id")
        parent = phases_by_id.get(str(parent_id)) if parent_id else None
        new_phase = _create_phase(
            thread,
            signal,
            title=new_title,
            parent_phase_id=parent.phase_id if parent else None,
            novelty_reason=reason or "new narrative axis",
        )
        phases_by_id[new_phase.phase_id] = new_phase
        if parent:
            if new_phase.phase_id not in parent.child_phase_ids:
                parent.child_phase_ids.append(new_phase.phase_id)
            # Parent's child_phase_ids was mutated — must persist.
            touched.add(parent.phase_id)
        _apply_signal_to_phase(new_phase, signal, decision="new_axis", reason=reason)
        stats["phases_created"] += 1
        return new_phase

    if decision == "background_repeat":
        target = target or _most_recent_active_phase(phases_by_id)
        if not target:
            stats["phase_llm_invalid_id_count"] += 1
            return None
        signal.is_background_repeat = True
        _apply_signal_to_phase(
            target, signal, decision="background_repeat", reason=reason, advance=False
        )
        stats["background_repeat_count"] += 1
        return target

    if decision == "different_thread":
        target = _most_recent_active_phase(phases_by_id)
        signal.adjudication_rationale = (
            f"thread_mismatch_suspected: {reason}"[:300] if reason else "thread_mismatch_suspected"
        )
        if target:
            _apply_signal_to_phase(target, signal, decision="different_thread", reason=reason)
        stats["thread_mismatch_flagged_count"] += 1
        return target

    if decision == "duplicate_suspected":
        dup_id = decision_dict.get("duplicate_of_signal_id")
        dup_target = None
        if dup_id:
            for phase in phases_by_id.values():
                if str(dup_id) in phase.signal_ids:
                    dup_target = phase
                    break
        target = dup_target or target or _most_recent_active_phase(phases_by_id)
        signal.adjudication_rationale = (
            f"duplicate_suspected:{dup_id} :: {reason}"[:300]
            if dup_id or reason
            else "duplicate_suspected"
        )
        if target:
            _apply_signal_to_phase(
                target, signal, decision="duplicate_suspected", reason=reason, advance=False
            )
        stats["duplicate_suspected_count"] += 1
        return target

    # continues_core (default / unknown)
    if not target:
        target = _most_recent_active_phase(phases_by_id)
        if target_id and not target:
            stats["phase_llm_invalid_id_count"] += 1
        elif target_id and target and target.phase_id != str(target_id):
            stats["phase_llm_invalid_id_count"] += 1
    if not target:
        # No phases at all — synthesize one from the signal.
        new_phase = _create_phase(
            thread,
            signal,
            title=signal.representative_title,
            parent_phase_id=None,
            novelty_reason="auto-create (no existing phases)",
        )
        phases_by_id[new_phase.phase_id] = new_phase
        target = new_phase
        stats["phases_created"] += 1
    _apply_signal_to_phase(target, signal, decision="continues_core", reason=reason)
    return target


def _assign_phase_status(phase: RssThreadPhase, today_iso: str) -> None:
    if phase.status == "resolved":
        return
    if phase.status == "emerging" and phase.signal_count >= 2:
        phase.status = "active"
    if phase.status in {"active", "emerging"}:
        try:
            last = datetime.fromisoformat((phase.last_advanced_at or phase.opened_at).replace("Z", "+00:00"))
            now = datetime.fromisoformat(today_iso.replace("Z", "+00:00"))
            if (now - last).days >= settings.PHASE_DORMANT_AFTER_DAYS:
                phase.status = "dormant"
        except (ValueError, AttributeError):
            pass


def _llm_assign_phases(
    thread: RssStoryThread,
    signals: list[RssSignal],
    phases: list[RssThreadPhase],
    model_overrides: Optional[dict[str, object]] = None,
) -> tuple[dict[str, dict[str, object]], int, int]:
    """Single Gemini Flash call for ambiguous signals in one thread.

    Returns ({signal_id: decision_dict}, input_tokens, output_tokens).
    Empty dict on failure (caller falls back).
    """
    phase_summaries = []
    for phase in phases:
        phase_summaries.append(
            {
                "phase_id": phase.phase_id,
                "title": phase.title,
                "status": phase.status,
                "summary": (phase.summary or "")[:200],
                "key_entities": phase.key_entities[:6],
                "signal_count": phase.signal_count,
            }
        )
    signal_summaries = []
    for signal in signals:
        signal_summaries.append(
            {
                "signal_id": signal.signal_id,
                "title": signal.representative_title[:160],
                "what_happened": (signal.what_happened or "")[:200],
                "key_entities": (signal.key_entities or [])[:6],
                "importance_score": signal.importance_score,
            }
        )
    prompt = (
        "You assign new RSS signals to narrative phases inside a story thread.\n"
        "Return JSON ONLY with shape: {\"decisions\": [...]}.\n"
        "For each input signal, return one decision object with these fields:\n"
        "  signal_id (echo back), decision, phase_id, new_phase_title, parent_phase_id, "
        "duplicate_of_signal_id, novelty_reason.\n\n"
        "decision must be one of:\n"
        "  continues_core      — extends an existing phase's narrative; phase_id required\n"
        "  new_axis            — opens a new narrative axis; new_phase_title required, parent_phase_id is the phase it forks from\n"
        "  background_repeat   — repeats info already covered, no new development; phase_id of the existing phase required\n"
        "  different_thread    — this signal probably doesn't belong to this thread\n"
        "  duplicate_suspected — looks like an undetected duplicate of another signal in this thread; "
        "duplicate_of_signal_id required\n\n"
        "Use Traditional Chinese for novelty_reason and new_phase_title.\n\n"
        f"Thread title: {thread.title}\n"
        f"Thread known_background: {(thread.known_background or '')[:400]}\n\n"
        f"Existing phases ({len(phase_summaries)}):\n{phase_summaries}\n\n"
        f"New signals to classify ({len(signal_summaries)}):\n{signal_summaries}\n"
    )
    route = resolve_model_route("w7_phase_assignment", model_overrides)
    payload, input_tokens, output_tokens = gemini_client.generate_json(prompt, model=route.model)
    decisions_list = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(decisions_list, list):
        return {}, int(input_tokens or 0), int(output_tokens or 0)
    by_signal: dict[str, dict[str, object]] = {}
    for entry in decisions_list:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("signal_id")
        if sid:
            by_signal[str(sid)] = entry
    return by_signal, int(input_tokens or 0), int(output_tokens or 0)
