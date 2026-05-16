from datetime import datetime, timezone

from app.clients.gemini_client import gemini_client
from app.core.config import settings
from app.models.rss import RssItem
from app.models.signal import RssSignal
from app.services.model_routing_service import resolve_model_route
from app.services.signal_v2_utils import (
    actions_conflict,
    compact_text,
    cosine_similarity,
    cosine_similarity_batch,
    decay_centroid,
    importance_bucket,
    is_generic_title,
    is_major_or_black_swan,
    overlap_ratio,
    signal_fingerprint_hash,
    signal_publisher_tier,
    short_hash,
    utc_now_iso,
)

# X3: items with less than this much total content cannot create a new signal.
# They can still match an existing signal (high embedding sim), but won't seed clusters.
MIN_TOTAL_FOR_NEW_SIGNAL = 200


def is_too_thin_for_new_signal(item: RssItem) -> bool:
    total = len(item.title or "") + len(item.summary or "") + len(item.article_lead or "")
    return total < MIN_TOTAL_FOR_NEW_SIGNAL


def match_item_to_signal(
    item: RssItem,
    active_signals: list[RssSignal],
    allow_adjudication: bool = False,
    model_overrides: dict[str, object] | None = None,
) -> tuple[str, RssSignal, dict[str, object]]:
    best_signal = None
    best_score = 0.0
    scored: list[tuple[float, RssSignal]] = []

    event_sims = cosine_similarity_batch(
        item.event_embedding, [s.event_centroid for s in active_signals]
    )
    entity_sims = cosine_similarity_batch(
        item.entity_embedding, [s.entity_centroid for s in active_signals]
    )
    impact_sims = cosine_similarity_batch(
        item.impact_embedding, [s.impact_centroid for s in active_signals]
    )
    context_sims = cosine_similarity_batch(
        item.context_embedding, [s.context_centroid for s in active_signals]
    )

    item_entities = _item_entities(item)
    item_entity_set = {e.lower() for e in item_entities}

    for idx, signal in enumerate(active_signals):
        event_sim = event_sims[idx] if idx < len(event_sims) else 0.0
        if _blocked_by_hard_gate_with_sim(item_entity_set, item, signal, event_sim):
            continue
        score = _hybrid_score_from_sims(
            item,
            signal,
            event_sims[idx] if idx < len(event_sims) else 0.0,
            entity_sims[idx] if idx < len(entity_sims) else 0.0,
            impact_sims[idx] if idx < len(impact_sims) else 0.0,
            context_sims[idx] if idx < len(context_sims) else 0.0,
            item_entities,
        )
        scored.append((score, signal))
        if score > best_score:
            best_score = score
            best_signal = signal

    threshold = (
        settings.SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD
        if is_generic_title(item.title or "")
        else settings.SIGNAL_MATCH_AUTO_THRESHOLD
    )
    if best_signal and best_score >= threshold:
        return "matched", _merge_item_into_signal(best_signal, item, best_score), {
            "match_score": best_score,
            "candidate_match_ids": [best_signal.signal_id],
        }

    ranked_candidates = [
        (score, s)
        for score, s in sorted(scored, reverse=True, key=lambda x: x[0])
        if score >= settings.SIGNAL_MATCH_REVIEW_THRESHOLD
    ][:5]
    candidates = [s.signal_id for score, s in ranked_candidates]
    if best_signal and candidates and allow_adjudication and _should_adjudicate_match(item, best_signal, best_score, scored):
        meta: dict[str, object] = {
            "match_score": best_score,
            "candidate_match_ids": candidates,
            "adjudication_attempted": True,
        }
        try:
            adjudication = _adjudicate_match(item, best_signal, best_score, model_overrides)
            meta.update(adjudication)
            decision = str(adjudication.get("adjudication_decision") or "")
            confidence = float(adjudication.get("adjudication_confidence") or 0.0)
            if decision == "same_event" and confidence >= 0.55:
                merged = _merge_item_into_signal(best_signal, item, best_score)
                _apply_adjudication_to_signal(merged, adjudication, best_signal.thread_id)
                return "matched", merged, meta
            if decision == "same_thread" and confidence >= 0.55:
                signal = _new_signal_from_item(item, best_score, candidates)
                signal.thread_id = best_signal.thread_id
                _apply_adjudication_to_signal(signal, adjudication, best_signal.thread_id)
                return "candidate", signal, meta
            if decision == "different_event" and confidence >= 0.55:
                signal = _new_signal_from_item(item, best_score, [])
                _apply_adjudication_to_signal(signal, adjudication, None)
                return "new", signal, meta
        except Exception as exc:
            meta["adjudication_error"] = str(exc)[:200]
            signal = _new_signal_from_item(item, best_score, candidates)
            return "candidate", signal, meta

    signal = _new_signal_from_item(item, best_score, candidates)
    if candidates:
        return "candidate", signal, {"match_score": best_score, "candidate_match_ids": candidates}
    return "new", signal, {"match_score": best_score, "candidate_match_ids": []}


def hybrid_match_score(item: RssItem, signal: RssSignal) -> float:
    event_similarity = cosine_similarity(item.event_embedding, signal.event_centroid)
    entity_similarity = cosine_similarity(item.entity_embedding, signal.entity_centroid)
    impact_similarity = cosine_similarity(item.impact_embedding, signal.impact_centroid)
    context_similarity = cosine_similarity(item.context_embedding, signal.context_centroid)
    return _hybrid_score_from_sims(
        item,
        signal,
        event_similarity,
        entity_similarity,
        impact_similarity,
        context_similarity,
        _item_entities(item),
    )


def _hybrid_score_from_sims(
    item: RssItem,
    signal: RssSignal,
    event_similarity: float,
    entity_similarity: float,
    impact_similarity: float,
    context_similarity: float,
    item_entities: list[str],
) -> float:
    time_source_score = _time_source_score(item, signal)
    score = (
        0.45 * event_similarity
        + 0.20 * max(entity_similarity, overlap_ratio(item_entities, signal.key_entities))
        + 0.15 * impact_similarity
        + 0.10 * context_similarity
        + 0.10 * time_source_score
    )
    return round(max(0.0, min(1.0, score)), 4)


def _blocked_by_hard_gate(item: RssItem, signal: RssSignal) -> bool:
    item_entities = {e.lower() for e in _item_entities(item)}
    signal_entities = {e.lower() for e in (signal.key_entities or [])}
    if item_entities and signal_entities and item_entities.isdisjoint(signal_entities):
        event_sim = cosine_similarity(item.event_embedding, signal.event_centroid)
        if event_sim < 0.92:
            return True
    item_action = _item_action(item)
    signal_action = signal.what_happened or signal.representative_title or ""
    return actions_conflict(item_action, signal_action)


def _blocked_by_hard_gate_with_sim(
    item_entity_set: set[str],
    item: RssItem,
    signal: RssSignal,
    event_sim: float,
) -> bool:
    signal_entities = {e.lower() for e in (signal.key_entities or [])}
    if item_entity_set and signal_entities and item_entity_set.isdisjoint(signal_entities):
        if event_sim < 0.92:
            return True
    item_action = _item_action(item)
    signal_action = signal.what_happened or signal.representative_title or ""
    return actions_conflict(item_action, signal_action)


def _should_adjudicate_match(
    item: RssItem,
    best_signal: RssSignal,
    best_score: float,
    scored: list[tuple[float, RssSignal]],
) -> bool:
    if best_score < settings.SIGNAL_MATCH_REVIEW_THRESHOLD:
        return False
    threshold = (
        settings.SIGNAL_MATCH_GENERIC_AUTO_THRESHOLD
        if is_generic_title(item.title or "")
        else settings.SIGNAL_MATCH_AUTO_THRESHOLD
    )
    if best_score >= threshold:
        return False
    sorted_scores = sorted((score for score, _ in scored), reverse=True)
    margin = best_score - sorted_scores[1] if len(sorted_scores) > 1 else 1.0
    blob = compact_text(
        item.title,
        item.summary,
        item.article_lead,
        best_signal.representative_title,
        best_signal.what_happened,
        limit=2000,
    )
    return (
        is_major_or_black_swan(blob)
        or importance_bucket(best_signal.importance_score) in {"critical", "high"}
        or best_score >= 0.82
        or margin <= 0.04
    )


def _adjudicate_match(
    item: RssItem,
    signal: RssSignal,
    score: float,
    model_overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    item_signals = item.item_signals if isinstance(item.item_signals, dict) else {}
    prompt = (
        "You are adjudicating whether a new RSS item belongs to an existing signal.\n"
        "Return JSON only with fields: decision, confidence, rationale.\n"
        "decision must be one of: same_event, same_thread, different_event.\n"
        "same_event means merge into the existing signal. same_thread means related continuation but not the same event. "
        "different_event means keep separate.\n\n"
        f"Hybrid score: {score}\n"
        f"New item title: {item.title}\n"
        f"New item summary: {item.summary[:600]}\n"
        f"New item lead: {(item.article_lead or '')[:600]}\n"
        f"New item signals: entities={item_signals.get('entities')} action={item_signals.get('primary_action')} tags={item_signals.get('event_tags')}\n"
        f"Existing signal title: {signal.representative_title}\n"
        f"Existing signal summary: {(signal.representative_summary or '')[:600]}\n"
        f"Existing signal what_happened: {signal.what_happened}\n"
        f"Existing signal entities: {signal.key_entities}\n"
        f"Existing signal publishers: {signal.publishers}\n"
    )
    route = resolve_model_route("w4_match_adjudication", model_overrides)
    payload, input_tokens, output_tokens = gemini_client.generate_json(
        prompt,
        model=route.model,
    )
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"same_event", "same_thread", "different_event"}:
        decision = "different_event"
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence"))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "adjudication_decision": decision,
        "adjudication_confidence": confidence,
        "adjudication_rationale": str(payload.get("rationale") or "").strip()[:300],
        "adjudication_model": route.model,
        "adjudication_input_tokens": input_tokens,
        "adjudication_output_tokens": output_tokens,
    }


def _time_source_score(item: RssItem, signal: RssSignal) -> float:
    source_bonus = 1.0
    if item.publisher and item.publisher in (signal.publishers or []):
        source_bonus = 0.5
    try:
        item_ts = _parse_ts(item.published_at or item.first_seen_at)
        signal_ts = _parse_ts(signal.window_end or signal.generated_at)
        hours = abs((item_ts - signal_ts).total_seconds()) / 3600
        time_score = max(0.0, 1.0 - min(hours, 48) / 48)
    except Exception:
        time_score = 0.5
    return round((time_score + source_bonus) / 2, 4)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _item_entities(item: RssItem) -> list[str]:
    """Read entities from item_signals (Plan A) with canonical_event as legacy fallback."""
    signals = item.item_signals if isinstance(item.item_signals, dict) else {}
    entities = signals.get("entities") or []
    if not entities and isinstance(item.canonical_event, dict):
        entities = item.canonical_event.get("key_entities") or []
    return [str(e) for e in entities if str(e).strip()]


def _item_action(item: RssItem) -> str:
    """Read action from item_signals (Plan A) with canonical_event as legacy fallback, then title."""
    signals = item.item_signals if isinstance(item.item_signals, dict) else {}
    action = signals.get("primary_action") or ""
    if not action and isinstance(item.canonical_event, dict):
        action = item.canonical_event.get("action") or ""
    return str(action or item.title or "")


def _new_signal_from_item(item: RssItem, match_score: float, candidates: list[str]) -> RssSignal:
    """Plan A: seed signal from item_signals + raw fields. Importance LLM will overwrite key_entities/what_happened later."""
    generated_at = utc_now_iso()
    signal_id = _signal_id_for_item(item, generated_at)
    entities = _item_entities(item)
    # what_happened defaults to title — importance service rewrites this anyway
    what_happened = item.title or (item.summary or "")[:200]
    publishers = [item.publisher] if item.publisher else []
    return RssSignal(
        signal_id=signal_id,
        generated_at=generated_at,
        window_start=item.first_seen_at,
        window_end=generated_at,
        member_item_ids=[item.item_id],
        cluster_size=1,
        source_count=1,
        publisher_count=1 if item.publisher else 0,
        publishers=publishers,
        publisher_tier=signal_publisher_tier(publishers),
        desks=[item.desk] if item.desk else [],
        market_levels=[item.market_level] if item.market_level else [],
        categories=[item.category] if item.category else [],
        representative_item_id=item.item_id,
        representative_title=item.title,
        representative_url=item.url,
        representative_summary=item.summary or item.article_lead,
        representative_published_at=item.published_at,
        representative_publisher=item.publisher,
        key_entities=entities,
        what_happened=what_happened,
        signal_status="provisional",
        event_centroid=item.event_embedding,
        entity_centroid=item.entity_embedding,
        impact_centroid=item.impact_embedding,
        context_centroid=item.context_embedding,
        confidence_score=0.0,
        match_score=match_score,
        candidate_match_ids=candidates,
        last_member_at=item.first_seen_at,
        signal_fingerprint_hash=signal_fingerprint_hash([item.item_id, item.event_embedding_hash or item.content_hash]),
    )


def _merge_item_into_signal(signal: RssSignal, item: RssItem, match_score: float) -> RssSignal:
    members = list(dict.fromkeys([*(signal.member_item_ids or []), item.item_id]))
    publishers = _append_unique(signal.publishers, item.publisher)
    desks = _append_unique(signal.desks, item.desk)
    market_levels = _append_unique(signal.market_levels, item.market_level)
    categories = _append_unique(signal.categories, item.category)
    entities = _append_unique(signal.key_entities or [], *_item_entities(item))
    signal.member_item_ids = members
    signal.cluster_size = len(members)
    signal.source_count = max(signal.source_count or 0, len(members))
    signal.publisher_count = len(publishers)
    signal.publishers = publishers
    signal.publisher_tier = signal_publisher_tier(publishers)
    signal.desks = desks
    signal.market_levels = market_levels
    signal.categories = categories
    signal.key_entities = entities
    signal.window_end = utc_now_iso()
    signal.last_member_at = item.first_seen_at
    signal.match_score = match_score
    signal.signal_status = "supported" if len(members) >= 2 else signal.signal_status
    signal.event_centroid = decay_centroid(signal.event_centroid, item.event_embedding, settings.CENTROID_DECAY)
    signal.entity_centroid = decay_centroid(signal.entity_centroid, item.entity_embedding, settings.CENTROID_DECAY)
    signal.impact_centroid = decay_centroid(signal.impact_centroid, item.impact_embedding, settings.CENTROID_DECAY)
    signal.context_centroid = decay_centroid(signal.context_centroid, item.context_embedding, settings.CENTROID_DECAY)
    signal.signal_fingerprint_hash = signal_fingerprint_hash([members, signal.event_centroid])
    return signal


def _append_unique(values: list[str] | None, *new_values: str) -> list[str]:
    out = []
    seen = set()
    for value in [*(values or []), *new_values]:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _signal_id_for_item(item: RssItem, generated_at: str) -> str:
    day = generated_at[:10].replace("-", "")
    digest = short_hash(item.canonical_event_hash or item.content_hash or item.item_id, 10)
    return f"sigv2_{day}_{digest}"


def _apply_adjudication_to_signal(
    signal: RssSignal,
    adjudication: dict[str, object],
    candidate_thread_id: str | None,
) -> None:
    """Persist W4 adjudication output onto signal so W7 phase assignment can consume it."""
    decision = adjudication.get("adjudication_decision")
    if decision:
        signal.adjudication_decision = str(decision)
    confidence = adjudication.get("adjudication_confidence")
    if confidence is not None:
        try:
            signal.adjudication_confidence = float(confidence)
        except (TypeError, ValueError):
            signal.adjudication_confidence = None
    rationale = adjudication.get("adjudication_rationale")
    if rationale:
        signal.adjudication_rationale = str(rationale)[:300]
    if candidate_thread_id:
        signal.adjudication_candidate_thread_id = candidate_thread_id
