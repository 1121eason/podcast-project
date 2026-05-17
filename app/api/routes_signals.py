from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.model_routing_payloads import ModelRouteOverride, dump_model_overrides
from app.clients.firestore_client import firestore_client
from app.core.logging import logger
from app.core.security import require_admin_token
from app.services.rss_clustering_service import run_clustering
from app.services.rss_embedding_service import embed_pending_items
from app.services.rss_importance_service import judge_signals
from app.services.rss_signal_processor_service import process_new_items
from app.services.rss_story_thread_service import consolidate_daily
from app.services.rss_verification_service import verify_signals

router = APIRouter()


class ClusterRequest(BaseModel):
    window_hours: int = Field(default=4, ge=1, le=72)
    distance_threshold: Optional[float] = Field(default=None, ge=0.05, le=0.5)


class EmbedRequest(BaseModel):
    window_hours: int = Field(default=4, ge=1, le=72)


class VerifyRequest(BaseModel):
    since_hours: int = Field(default=24, ge=1, le=336)
    force: bool = False


class JudgeRequest(BaseModel):
    since_hours: int = Field(default=4, ge=1, le=336)
    max_workers: int = Field(default=5, ge=1, le=10)
    force: bool = False
    max_signals_per_run: int = Field(default=200, ge=1, le=2000)
    quality_gate: str = "supported_or_promoted"
    run_bucket: Optional[str] = None
    model_overrides: Optional[dict[str, ModelRouteOverride]] = None


class SignalProcessRequest(BaseModel):
    since_hours: int = Field(default=6, ge=1, le=72)
    limit_items: int = Field(default=250, ge=1, le=2000)
    max_workers: int = Field(default=5, ge=1, le=20)
    article_extraction: str = "selective"
    canonicalize: str = "selective"
    embed: bool = True
    match: bool = True
    run_bucket: Optional[str] = None
    model_overrides: Optional[dict[str, ModelRouteOverride]] = None


class ConsolidateDailyRequest(BaseModel):
    since_hours: int = Field(default=36, ge=1, le=336)
    story_lookback_days: int = Field(default=30, ge=1, le=180)
    max_threads: int = Field(default=200, ge=1, le=1000)
    run_bucket: Optional[str] = None
    model_overrides: Optional[dict[str, ModelRouteOverride]] = None


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


@router.post("/process-new-items")
def process_new_items_endpoint(
    request: SignalProcessRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or SignalProcessRequest()
    try:
        return process_new_items(
            since_hours=request.since_hours,
            limit_items=request.limit_items,
            max_workers=request.max_workers,
            article_extraction=request.article_extraction,
            canonicalize=request.canonicalize,
            embed=request.embed,
            match=request.match,
            run_bucket=request.run_bucket,
            model_overrides=dump_model_overrides(request.model_overrides),
        )
    except Exception as exc:
        import traceback
        logger.error("process_new_items failed:\n%s", traceback.format_exc())
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


@router.get("/runs/clustering")
def clustering_runs(since_hours: int = Query(default=48, ge=1, le=336)):
    runs = firestore_client.list_recent_clustering_runs(_since_iso(since_hours))
    return {
        "since_hours": since_hours,
        "count": len(runs),
        "runs": [r.model_dump() for r in runs],
    }


@router.post("/verify")
def verify_endpoint(
    request: VerifyRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or VerifyRequest()
    try:
        return verify_signals(since_hours=request.since_hours, force=request.force)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/judge")
def judge_endpoint(
    request: JudgeRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or JudgeRequest()
    try:
        return judge_signals(
            since_hours=request.since_hours,
            max_workers=request.max_workers,
            force=request.force,
            max_signals_per_run=request.max_signals_per_run,
            quality_gate=request.quality_gate,
            run_bucket=request.run_bucket,
            model_overrides=dump_model_overrides(request.model_overrides),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/consolidate-daily")
def consolidate_daily_endpoint(
    request: ConsolidateDailyRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or ConsolidateDailyRequest()
    try:
        return consolidate_daily(
            since_hours=request.since_hours,
            story_lookback_days=request.story_lookback_days,
            max_threads=request.max_threads,
            run_bucket=request.run_bucket,
            model_overrides=dump_model_overrides(request.model_overrides),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/top")
def top_signals(
    since_hours: int = Query(default=24, ge=1, le=336),
    min_score: int = Query(default=60, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=200),
):
    signals = firestore_client.list_top_signals(
        _since_iso(since_hours), min_score=min_score, limit=limit
    )
    return {
        "since_hours": since_hours,
        "min_score": min_score,
        "count": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "importance_score": s.importance_score,
                "cluster_status": s.cluster_status,
                "topic_heat": s.topic_heat,
                "impact_type": s.impact_type,
                "publishers": s.publishers,
                "source_count": s.source_count,
                "publisher_count": s.publisher_count,
                "key_entities": s.key_entities,
                "regions": s.regions,
                "reasoning": s.reasoning,
                "heat_vs_importance_note": s.heat_vs_importance_note,
                "representative_title": s.representative_title,
                "representative_url": s.representative_url,
                "representative_published_at": s.representative_published_at,
            }
            for s in signals
        ],
    }


@router.get("/by-status")
def by_status(
    status: str = Query(...),
    since_hours: int = Query(default=24, ge=1, le=336),
    limit: int = Query(default=50, ge=1, le=500),
):
    signals = firestore_client.list_top_signals(
        _since_iso(since_hours), min_score=0, limit=limit, status=status
    )
    return {
        "since_hours": since_hours,
        "status": status,
        "count": len(signals),
        "signals": [
            {
                "signal_id": s.signal_id,
                "cluster_status": s.cluster_status,
                "topic_heat": s.topic_heat,
                "importance_score": s.importance_score,
                "representative_title": s.representative_title,
                "representative_url": s.representative_url,
                "publishers": s.publishers,
                "source_count": s.source_count,
            }
            for s in signals
        ],
    }


@router.get("/runs/judgement")
def judgement_runs(since_hours: int = Query(default=48, ge=1, le=336)):
    runs = firestore_client.list_recent_judgement_runs(_since_iso(since_hours))
    return {
        "since_hours": since_hours,
        "count": len(runs),
        "runs": [r.model_dump() for r in runs],
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
