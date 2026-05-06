import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from app.clients.embedding_client import EmbeddingClient
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.models.rss import RssItem
from app.models.signal import RssClusteringRun, RssSignal
from app.services.rss_embedding_service import embed_pending_items
from app.services.rss_source_service import utc_now_iso

logger = logging.getLogger(__name__)


def _window_start_iso(window_hours: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    return start.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"cluster_{ts}_{suffix}"


def _generate_signal_id(generated_at: str, fingerprint: str) -> str:
    date_part = generated_at[:10].replace("-", "")
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:8]
    return f"sig_{date_part}_{digest}"


def _cluster_embeddings(
    matrix: np.ndarray,
    distance_threshold: float,
) -> np.ndarray:
    if matrix.shape[0] == 1:
        return np.array([0])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = matrix / norms
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    )
    return clustering.fit_predict(normalized)


def _pick_representative_index(
    cluster_indices: list[int],
    matrix: np.ndarray,
) -> int:
    if len(cluster_indices) == 1:
        return cluster_indices[0]
    sub = matrix[cluster_indices]
    centroid = sub.mean(axis=0)
    norms = np.linalg.norm(sub, axis=1)
    norms[norms == 0] = 1.0
    centroid_norm = np.linalg.norm(centroid) or 1.0
    sims = (sub @ centroid) / (norms * centroid_norm)
    best_local = int(np.argmax(sims))
    return cluster_indices[best_local]


def _unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for v in values:
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        ordered.append(v)
    return ordered


def run_clustering(
    window_hours: int = 4,
    embedding_client: Optional[EmbeddingClient] = None,
    distance_threshold: Optional[float] = None,
) -> dict[str, object]:
    started = time.monotonic()
    threshold = (
        distance_threshold
        if distance_threshold is not None
        else settings.CLUSTERING_DISTANCE_THRESHOLD
    )
    run_id = _generate_run_id()
    generated_at = _now_iso()
    window_start = _window_start_iso(window_hours)

    embed_result = embed_pending_items(
        window_hours=window_hours,
        embedding_client=embedding_client,
    )

    items = firestore_client.list_rss_items_with_embedding(window_start)

    if not items:
        run = RssClusteringRun(
            run_id=run_id,
            generated_at=generated_at,
            window_hours=window_hours,
            candidate_item_count=int(embed_result.get("candidate_item_count") or 0),
            embedded_item_count=int(embed_result.get("embedded_item_count") or 0),
            embedding_failed_item_count=int(
                embed_result.get("embedding_failed_item_count") or 0
            ),
            embedding_skipped_cached_count=0,
            cluster_count=0,
            multi_source_cluster_count=0,
            singleton_cluster_count=0,
            duration_ms=int((time.monotonic() - started) * 1000),
            embedding_cost_usd=float(embed_result.get("cost_usd") or 0.0),
        )
        firestore_client.create_clustering_run(run)
        return run.model_dump()

    embeddings = np.array([item.embedding for item in items], dtype=np.float32)

    labels = _cluster_embeddings(embeddings, threshold)

    cluster_buckets: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        cluster_buckets.setdefault(int(label), []).append(idx)

    signals: list[RssSignal] = []
    item_to_signal: dict[str, str] = {}

    for label, indices in cluster_buckets.items():
        rep_idx = _pick_representative_index(indices, embeddings)
        rep_item = items[rep_idx]

        member_items = [items[i] for i in indices]
        publishers = _unique_preserve_order([m.publisher for m in member_items])
        desks = _unique_preserve_order([m.desk for m in member_items])
        market_levels = _unique_preserve_order([m.market_level for m in member_items])
        categories = _unique_preserve_order([m.category for m in member_items])
        source_ids = _unique_preserve_order([m.source_id for m in member_items])

        fingerprint_parts = [rep_item.url or rep_item.guid or rep_item.item_id]
        fingerprint_parts.extend(sorted(m.item_id for m in member_items))
        fingerprint = "|".join(fingerprint_parts)
        signal_id = _generate_signal_id(generated_at, fingerprint)

        signal = RssSignal(
            signal_id=signal_id,
            generated_at=generated_at,
            window_start=window_start,
            window_end=generated_at,
            member_item_ids=[m.item_id for m in member_items],
            cluster_size=len(member_items),
            source_count=len(source_ids),
            publisher_count=len(publishers),
            publishers=publishers,
            desks=desks,
            market_levels=market_levels,
            categories=categories,
            representative_item_id=rep_item.item_id,
            representative_title=rep_item.title,
            representative_url=rep_item.url,
            representative_summary=rep_item.summary,
            representative_published_at=rep_item.published_at,
            representative_publisher=rep_item.publisher,
        )
        signals.append(signal)
        for m in member_items:
            item_to_signal[m.item_id] = signal_id

    firestore_client.upsert_rss_signals(signals)
    firestore_client.update_rss_item_signal_ids(item_to_signal)

    multi_source = sum(1 for s in signals if s.source_count >= 2)
    singletons = sum(1 for s in signals if s.cluster_size == 1)

    run = RssClusteringRun(
        run_id=run_id,
        generated_at=generated_at,
        window_hours=window_hours,
        candidate_item_count=int(embed_result.get("candidate_item_count") or 0),
        embedded_item_count=int(embed_result.get("embedded_item_count") or 0),
        embedding_failed_item_count=int(
            embed_result.get("embedding_failed_item_count") or 0
        ),
        embedding_skipped_cached_count=max(0, len(items) - int(embed_result.get("embedded_item_count") or 0)),
        cluster_count=len(signals),
        multi_source_cluster_count=multi_source,
        singleton_cluster_count=singletons,
        duration_ms=int((time.monotonic() - started) * 1000),
        embedding_cost_usd=float(embed_result.get("cost_usd") or 0.0),
    )
    firestore_client.create_clustering_run(run)
    result = run.model_dump()
    result["embedding_breakdown"] = embed_result
    return result
