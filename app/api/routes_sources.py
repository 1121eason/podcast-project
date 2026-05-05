from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.security import require_admin_token
from app.services.rss_ingest_service import ingest_rss_sources
from app.services.rss_observation_service import (
    build_signal_observation_report,
    build_source_health_summary,
    get_recent_rss_items,
)
from app.services.rss_source_service import sync_rss_sources_from_sheet

router = APIRouter()


class RssIngestRequest(BaseModel):
    limit_sources: Optional[int] = None
    include_unhealthy: bool = False
    max_workers: int = Field(default=10, ge=1, le=20)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    since_hours: Optional[int] = Field(default=24, ge=1, le=168)


@router.post("/sheets/sync")
def sync_sources_from_sheet(_: None = Depends(require_admin_token)):
    try:
        return sync_rss_sources_from_sheet()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rss/ingest")
def ingest_rss(
    request: RssIngestRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or RssIngestRequest()
    try:
        return ingest_rss_sources(
            limit_sources=request.limit_sources,
            include_unhealthy=request.include_unhealthy,
            max_workers=request.max_workers,
            timeout_seconds=request.timeout_seconds,
            since_hours=request.since_hours,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rss/health")
def rss_health():
    return build_source_health_summary()


@router.get("/rss/items")
def rss_items(since_hours: int = Query(default=24, ge=1, le=168)):
    return get_recent_rss_items(since_hours=since_hours)


@router.get("/rss/signal-report")
def rss_signal_report(since_hours: int = Query(default=24, ge=1, le=168)):
    return build_signal_observation_report(since_hours=since_hours)
