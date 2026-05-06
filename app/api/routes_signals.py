from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.clients.firestore_client import firestore_client
from app.core.security import require_admin_token
from app.services.rss_clustering_service import run_clustering
from app.services.rss_embedding_service import embed_pending_items

router = APIRouter()


class ClusterRequest(BaseModel):
    window_hours: int = Field(default=4, ge=1, le=72)
    distance_threshold: Optional[float] = Field(default=None, ge=0.05, le=0.5)


class EmbedRequest(BaseModel):
    window_hours: int = Field(default=4, ge=1, le=72)


def _since_iso(hours: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@router.post("/cluster")
def cluster_signals(
    request: ClusterRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or ClusterRequest()
    try:
        return run_clustering(
            window_hours=request.window_hours,
            distance_threshold=request.distance_threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/embed")
def embed_signals(
    request: EmbedRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or EmbedRequest()
    try:
        return embed_pending_items(window_hours=request.window_hours)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recent")
def recent_signals(
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=200, ge=1, le=500),
):
    signals = firestore_client.list_recent_signals(_since_iso(hours), limit=limit)
    return {
        "since_hours": hours,
        "count": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "generated_at": s.generated_at,
                "cluster_size": s.cluster_size,
                "source_count": s.source_count,
                "publisher_count": s.publisher_count,
                "publishers": s.publishers,
                "desks": s.desks,
                "market_levels": s.market_levels,
                "representative_title": s.representative_title,
                "representative_url": s.representative_url,
                "representative_publisher": s.representative_publisher,
                "representative_published_at": s.representative_published_at,
                "cluster_status": s.cluster_status,
                "topic_heat": s.topic_heat,
                "importance_score": s.importance_score,
                "impact_type": s.impact_type,
            }
            for s in signals
        ],
    }


@router.get("/{signal_id}")
def signal_detail(signal_id: str):
    signal = firestore_client.get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="signal not found")
    members = firestore_client.list_rss_items_by_ids(signal.member_item_ids)
    return {
        "signal": signal.model_dump(),
        "members": [
            {
                "item_id": m.item_id,
                "publisher": m.publisher,
                "title": m.title,
                "url": m.url,
                "published_at": m.published_at,
                "first_seen_at": m.first_seen_at,
                "summary": m.summary,
            }
            for m in members
        ],
    }


@router.get("/runs/clustering")
def clustering_runs(since_hours: int = Query(default=48, ge=1, le=336)):
    runs = firestore_client.list_recent_clustering_runs(_since_iso(since_hours))
    return {
        "since_hours": since_hours,
        "count": len(runs),
        "runs": [r.model_dump() for r in runs],
    }
