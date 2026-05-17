import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.clients.embedding_client import EmbeddingClient, estimate_cost_usd
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.models.rss import RssItem
from app.models.signal import RssSignal
from app.services.llm_cost_utils import compute_llm_cost
from app.services.log_summary_utils import (
    add_duplicate_log_summary,
    add_log_summary,
    cost_text,
    seconds_text,
    tagged,
)
from app.services.model_routing_service import (
    effective_model_routes,
    resolve_model_route,
    validate_model_overrides,
)
from app.services.rss_article_extraction_service import extract_article_lead
from app.services.rss_item_signals_service import extract_item_signals, item_signals_hash
from app.services.rss_signal_matching_service import is_too_thin_for_new_signal, match_item_to_signal
from app.services.signal_v2_utils import (
    coerce_numeric_vector,
    compact_text,
    event_embedding_hash,
    is_numeric_vector,
    stable_hash,
    utc_now_iso,
)
from app.services.workflow_run_service import complete_workflow_run, fail_workflow_run, start_workflow_run

logger = logging.getLogger(__name__)

EMBEDDING_VERSION = "signal_v2_multi_planA_2026_05_13"


def process_new_items(
    since_hours: int = 6,
    limit_items: int = 250,
    max_workers: int = 5,
    article_extraction: str = "selective",
    canonicalize: str = "selective",
    embed: bool = True,
    match: bool = True,
    run_bucket: Optional[str] = None,
    embedding_client: Optional[EmbeddingClient] = None,
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    started = time.monotonic()
    request_payload = {
        "since_hours": since_hours,
        "limit_items": limit_items,
        "max_workers": max_workers,
        "article_extraction": article_extraction,
        "canonicalize": canonicalize,
        "embed": embed,
        "match": match,
        "run_bucket": run_bucket,
        "model_overrides": validate_model_overrides(model_overrides),
    }
    should_skip, workflow_run_id, existing_summary = start_workflow_run(
        "signal_process",
        run_bucket,
        request_payload,
    )
    if should_skip:
        out = dict(existing_summary)
        out.update({"skipped_duplicate": True, "run_bucket": run_bucket, "workflow_run_id": workflow_run_id})
        add_duplicate_log_summary(out, "W4 Signal Process", run_bucket)
        return out

    try:
        result = _process_new_items_inner(
            since_hours=since_hours,
            limit_items=limit_items,
            article_extraction=article_extraction,
            canonicalize=canonicalize,
            embed=embed,
            match=match,
            embedding_client=embedding_client,
            model_overrides=model_overrides,
        )
        result.update(
            {
                "run_bucket": run_bucket,
                "workflow_run_id": workflow_run_id,
                "skipped_duplicate": False,
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        )
        add_log_summary(result, _compose_signal_process_log_summary(result))
        complete_workflow_run(workflow_run_id, result)
        return result
    except Exception as exc:
        fail_workflow_run(workflow_run_id, str(exc))
        raise


def _process_new_items_inner(
    since_hours: int,
    limit_items: int,
    article_extraction: str,
    canonicalize: str,
    embed: bool,
    match: bool,
    embedding_client: Optional[EmbeddingClient],
    model_overrides: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    since = _since_iso(since_hours)
    items = firestore_client.list_rss_items_pending_v2_processing(since, limit=limit_items)
    item_updates: dict[str, dict] = {}
    processed_items: list[RssItem] = []

    extracted_count = 0
    canonicalized_count = 0
    canonical_fallback_count = 0
    embedding_skipped_cached_count = 0
    embedded_item_count = 0
    total_embedding_chars = 0

    for item in items:
        update: dict = {}
        if article_extraction != "off":
            article = extract_article_lead(item)
            if article["status"] == "success":
                extracted_count += 1
            if article.get("article_lead") and article.get("article_text_hash") != item.article_text_hash:
                item.article_lead = str(article["article_lead"])
                item.article_text_hash = str(article["article_text_hash"])
                item.article_extracted_at = str(article.get("extracted_at") or utc_now_iso())
                update.update(
                    {
                        "article_lead": item.article_lead,
                        "article_text_hash": item.article_text_hash,
                        "article_extracted_at": item.article_extracted_at,
                    }
                )
            update["article_extract_status"] = article["status"]
            item.article_extract_status = str(article["status"])

        # Plan A: mechanical item_signals extraction (replaces LLM canonicalize_item).
        # `canonicalize` parameter kept for API compatibility but no longer drives LLM.
        if canonicalize not in {"off", "false", "none"}:
            signals = extract_item_signals(item)
            new_hash = item_signals_hash(signals)
            if new_hash != item.item_signals_hash:
                item.item_signals = signals
                item.item_signals_hash = new_hash
                item.item_signals_at = utc_now_iso()
                canonicalized_count += 1  # reused stat: now counts mechanical extractions
                update.update(
                    {
                        "item_signals": item.item_signals,
                        "item_signals_hash": item.item_signals_hash,
                        "item_signals_at": item.item_signals_at,
                    }
                )

        embedding_inputs = build_embedding_inputs(item)
        embedding_hash = event_embedding_hash(embedding_inputs)
        if item.event_embedding_hash == embedding_hash and _has_valid_cached_embeddings(item):
            _normalize_item_embeddings(item)
            embedding_skipped_cached_count += 1
        elif embed:
            vectors, chars, model = _embed_inputs(embedding_inputs, embedding_client)
            item.event_embedding = vectors["event"]
            item.entity_embedding = vectors["entity"]
            item.impact_embedding = vectors["impact"]
            item.context_embedding = vectors["context"]
            item.event_embedding_hash = embedding_hash
            item.embedding_version = EMBEDDING_VERSION
            item.embedding_model = model
            item.embedded_at = utc_now_iso()
            embedded_item_count += 1
            total_embedding_chars += chars
            update.update(
                {
                    "event_embedding": item.event_embedding,
                    "entity_embedding": item.entity_embedding,
                    "impact_embedding": item.impact_embedding,
                    "context_embedding": item.context_embedding,
                    "event_embedding_hash": item.event_embedding_hash,
                    "embedding_version": item.embedding_version,
                    "embedding_model": model,
                    "embedded_at": item.embedded_at,
                }
            )
        item.v2_processing_hash = stable_hash(
            [item.content_hash, item.article_text_hash, item.item_signals_hash, item.event_embedding_hash]
        )
        item.v2_processed_at = utc_now_iso()
        update.update(
            {
                "v2_processing_hash": item.v2_processing_hash,
                "v2_processed_at": item.v2_processed_at,
            }
        )
        item_updates[item.item_id] = {k: v for k, v in update.items() if not k.startswith("_")}
        processed_items.append(item)

    written_item_updates = firestore_client.update_rss_item_v2_fields(item_updates)

    matched_count = 0
    candidate_match_count = 0
    new_signal_count = 0
    signals_written = 0
    auto_match_count = 0
    adjudicated_match_count = 0
    same_thread_candidate_count = 0
    different_event_adjudication_count = 0
    adjudication_failed_count = 0
    review_band_count = 0
    match_score_sum = 0.0
    match_scored_count = 0
    supported_signal_write_count = 0
    singleton_signal_write_count = 0
    item_signal_updates: dict[str, str] = {}
    thin_dropped_count = 0
    # Pro adjudication tokens — accumulate so the [cost] log line shows the
    # actual W4 LLM spend (not just the cheap embedding portion).
    adjudication_call_count = 0
    adjudication_input_tokens = 0
    adjudication_output_tokens = 0
    if match and processed_items:
        active_since = _since_iso(max(24, since_hours))
        active_signals = firestore_client.list_active_signals_for_matching(active_since, limit=1000)
        signals_to_write: dict[str, RssSignal] = {}
        for item in processed_items:
            if not is_numeric_vector(item.event_embedding):
                continue
            candidate_signals = _prune_active_signals(item, active_signals)
            outcome, signal, meta = match_item_to_signal(
                item,
                candidate_signals,
                allow_adjudication=True,
                model_overrides=model_overrides,
            )
            score = float(meta.get("match_score") or 0.0)
            # X3 gate: if item content is too thin and didn't match an existing signal,
            # drop it (do not seed a new singleton signal with garbage embedding).
            if outcome != "matched" and is_too_thin_for_new_signal(item):
                thin_dropped_count += 1
                continue
            if score:
                match_score_sum += score
                match_scored_count += 1
            if meta.get("candidate_match_ids") and score < settings.SIGNAL_MATCH_AUTO_THRESHOLD:
                review_band_count += 1
            if meta.get("adjudication_error"):
                adjudication_failed_count += 1
            if meta.get("adjudication_attempted"):
                adjudication_call_count += 1
                adjudication_input_tokens += int(meta.get("adjudication_input_tokens") or 0)
                adjudication_output_tokens += int(meta.get("adjudication_output_tokens") or 0)
            decision = str(meta.get("adjudication_decision") or "")
            if outcome == "matched":
                matched_count += 1
                if decision == "same_event":
                    adjudicated_match_count += 1
                else:
                    auto_match_count += 1
            elif outcome == "candidate":
                candidate_match_count += 1
                new_signal_count += 1
                if decision == "same_thread":
                    same_thread_candidate_count += 1
            else:
                new_signal_count += 1
                if decision == "different_event":
                    different_event_adjudication_count += 1
            signals_to_write[signal.signal_id] = signal
            item_signal_updates[item.item_id] = signal.signal_id
            active_signals = [s for s in active_signals if s.signal_id != signal.signal_id]
            active_signals.append(signal)
        supported_signal_write_count = sum(
            1 for signal in signals_to_write.values()
            if signal.signal_status in {"supported", "confirmed", "promoted"} or signal.cluster_size >= 2
        )
        singleton_signal_write_count = sum(1 for signal in signals_to_write.values() if signal.cluster_size <= 1)
        signals_written = firestore_client.upsert_rss_signals(list(signals_to_write.values()))
        firestore_client.update_rss_item_signal_ids(item_signal_updates)

    processed_for_match = max(1, len([item for item in processed_items if item.event_embedding]))

    embedding_cost_usd = estimate_cost_usd(total_embedding_chars)
    adjudication_cost_usd = round(
        compute_llm_cost(
            resolve_model_route("w4_match_adjudication", model_overrides).model,
            adjudication_input_tokens,
            adjudication_output_tokens,
        ),
        6,
    )

    return {
        "since_hours": since_hours,
        "candidate_item_count": len(items),
        "processed_item_count": len(processed_items),
        "item_update_count": written_item_updates,
        "article_extracted_count": extracted_count,
        "canonicalized_count": canonicalized_count,
        "canonical_fallback_count": canonical_fallback_count,
        "embedded_item_count": embedded_item_count,
        "embedding_skipped_cached_count": embedding_skipped_cached_count,
        "embedding_cost_usd": embedding_cost_usd,
        "matched_item_count": matched_count,
        "auto_match_count": auto_match_count,
        "adjudicated_match_count": adjudicated_match_count,
        "candidate_match_count": candidate_match_count,
        "same_thread_candidate_count": same_thread_candidate_count,
        "different_event_adjudication_count": different_event_adjudication_count,
        "adjudication_failed_count": adjudication_failed_count,
        "adjudication_call_count": adjudication_call_count,
        "adjudication_input_tokens": adjudication_input_tokens,
        "adjudication_output_tokens": adjudication_output_tokens,
        "adjudication_cost_usd": adjudication_cost_usd,
        "total_cost_usd": round(embedding_cost_usd + adjudication_cost_usd, 6),
        "review_band_count": review_band_count,
        "match_score_avg": round(match_score_sum / match_scored_count, 4) if match_scored_count else 0.0,
        "new_signal_count": new_signal_count,
        "candidate_match_ratio": round(candidate_match_count / processed_for_match, 4),
        "new_signal_ratio": round(new_signal_count / processed_for_match, 4),
        "duplicate_prevention_ratio": round(matched_count / processed_for_match, 4),
        "supported_signal_write_count": supported_signal_write_count,
        "singleton_signal_write_count": singleton_signal_write_count,
        "signals_written_count": signals_written,
        "thin_dropped_count": thin_dropped_count,
        "model_routing": effective_model_routes(model_overrides, ["w4_match_adjudication"]),
    }


def _compose_signal_process_log_summary(result: dict[str, object]) -> list[str]:
    lines = [
        tagged(
            "ok",
            (
                f"W4 處理 {result.get('processed_item_count', 0)}/"
                f"{result.get('candidate_item_count', 0)} 個 RSS item；"
                f"抽文 {result.get('article_extracted_count', 0)}、標準化 {result.get('canonicalized_count', 0)}、"
                f"embedding 新算 {result.get('embedded_item_count', 0)}、cache 命中 {result.get('embedding_skipped_cached_count', 0)}。"
            ),
        ),
        tagged(
            "new",
            (
                f"寫入 {result.get('signals_written_count', 0)} 個 signal："
                f"新 signal {result.get('new_signal_count', 0)}、自動掛舊 signal {result.get('auto_match_count', 0)}、"
                f"W4 same_event adjudication {result.get('adjudicated_match_count', 0)}。"
            ),
        ),
    ]
    review_count = int(result.get("review_band_count") or 0)
    failed_count = int(result.get("adjudication_failed_count") or 0)
    thin_count = int(result.get("thin_dropped_count") or 0)
    if review_count or failed_count or thin_count:
        lines.append(
            tagged(
                "warn",
                (
                    f"模糊區 {review_count}、adjudication 失敗 {failed_count}、"
                    f"thin item 丟棄 {thin_count}；必要時抽樣檢查 W4 matching。"
                ),
            )
        )
    else:
        lines.append(tagged("ok", "沒有 W4 adjudication 失敗或 thin item 丟棄。"))
    adjudication_calls = int(result.get("adjudication_call_count") or 0)
    lines.append(
        tagged(
            "cost",
            (
                f"embedding {cost_text(result.get('embedding_cost_usd'))} + "
                f"adjudication {cost_text(result.get('adjudication_cost_usd'))} "
                f"({adjudication_calls} 次 LLM call, "
                f"{int(result.get('adjudication_input_tokens') or 0)} input / "
                f"{int(result.get('adjudication_output_tokens') or 0)} output tokens)，"
                f"總成本 {cost_text(result.get('total_cost_usd'))}，"
                f"平均 match score {result.get('match_score_avg', 0)}。"
            ),
        )
    )
    lines.append(tagged("time", f"總耗時 {seconds_text(result.get('duration_ms'))}。"))
    return lines


def build_embedding_inputs(item: RssItem) -> dict[str, str]:
    """Plan A: 4 views built mechanically from item_signals + raw fields. No canonical_event dependency."""
    signals = item.item_signals if isinstance(item.item_signals, dict) else {}
    entities_text = ", ".join(str(x) for x in signals.get("entities") or [])
    event_tags_text = " ".join(str(x) for x in signals.get("event_tags") or [])
    return {
        # event: title + summary + article_lead — let the multilingual embedder do the work
        "event": compact_text(item.title, item.summary, item.article_lead, limit=3000),
        # entity: who/what — NER + dict-extracted entities
        "entity": compact_text(entities_text, limit=1000),
        # impact: which domain/face — pure metadata + event tags
        "impact": compact_text(item.category, item.desk, item.market_level, event_tags_text, limit=1200),
        # context: full body for embedding richness
        "context": compact_text(item.article_lead, item.summary, item.market_level, limit=2400),
    }


def _embed_inputs(
    embedding_inputs: dict[str, str],
    embedding_client: Optional[EmbeddingClient],
) -> tuple[dict[str, list[float]], int, str]:
    client = embedding_client or EmbeddingClient()
    keys = ["event", "entity", "impact", "context"]
    texts = [embedding_inputs[k] for k in keys]
    vectors, failed, total_chars = client.embed_batch(texts)
    if failed:
        logger.warning("Multi-vector embedding had failed indices: %s", failed)
    out = {}
    for key, vector in zip(keys, vectors):
        out[key] = coerce_numeric_vector(vector) or []
    for key in keys:
        out.setdefault(key, [])
    model = getattr(client, "model_name", settings.EMBEDDING_MODEL)
    return out, total_chars, model


def _has_valid_cached_embeddings(item: RssItem) -> bool:
    if not is_numeric_vector(item.event_embedding):
        return False
    return all(
        _is_empty_or_numeric_vector(vec)
        for vec in (item.entity_embedding, item.impact_embedding, item.context_embedding)
    )


def _is_empty_or_numeric_vector(vec: list[float] | None) -> bool:
    return not vec or is_numeric_vector(vec)


def _normalize_item_embeddings(item: RssItem) -> None:
    item.event_embedding = coerce_numeric_vector(item.event_embedding)
    item.entity_embedding = coerce_numeric_vector(item.entity_embedding) or []
    item.impact_embedding = coerce_numeric_vector(item.impact_embedding) or []
    item.context_embedding = coerce_numeric_vector(item.context_embedding) or []


def _prune_active_signals(
    item: RssItem,
    active_signals: list[RssSignal],
    max_candidates: int = 200,
) -> list[RssSignal]:
    """Pre-filter the active signal pool before running the hybrid matcher.

    The matcher's cost is dominated by 4 cosine ops per signal; capping the
    candidate set to ~200 prevents quadratic growth as active signals accrue
    across the 24h+ lookback window.
    """
    if len(active_signals) <= max_candidates:
        return active_signals

    signals = item.item_signals if isinstance(item.item_signals, dict) else {}
    item_entities = {str(e).lower() for e in (signals.get("entities") or []) if str(e).strip()}
    if not item_entities and isinstance(item.canonical_event, dict):
        item_entities = {str(e).lower() for e in (item.canonical_event.get("key_entities") or []) if str(e).strip()}
    item_category = (item.category or "").lower()
    item_desk = (item.desk or "").lower()

    if item_entities:
        entity_matches = [
            s for s in active_signals
            if any(str(e).lower() in item_entities for e in (s.key_entities or []))
        ]
        if entity_matches:
            entity_matches.sort(key=lambda s: s.window_end or s.generated_at or "", reverse=True)
            return entity_matches[:max_candidates]

    if item_category or item_desk:
        category_matches = [
            s for s in active_signals
            if (item_category and item_category in [c.lower() for c in (s.categories or [])])
            or (item_desk and item_desk in [d.lower() for d in (s.desks or [])])
        ]
        if category_matches:
            category_matches.sort(key=lambda s: s.window_end or s.generated_at or "", reverse=True)
            return category_matches[:max_candidates]

    sorted_by_recency = sorted(
        active_signals,
        key=lambda s: s.window_end or s.generated_at or "",
        reverse=True,
    )
    return sorted_by_recency[:max_candidates]


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
