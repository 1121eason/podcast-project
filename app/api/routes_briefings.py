from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.clients.firestore_client import firestore_client
from app.core.security import require_admin_token
from app.services.rss_briefing_service import generate_daily_briefing
from app.services.rss_business_impact_service import analyze_business_impact

router = APIRouter()


class BusinessImpactRequest(BaseModel):
    since_hours: int = Field(default=24, ge=1, le=168)
    min_score: int = Field(default=60, ge=0, le=100)
    max_workers: int = Field(default=5, ge=1, le=10)
    force: bool = False
    max_signals_per_run: int = Field(default=100, ge=1, le=500)


class BriefingRequest(BaseModel):
    briefing_date: Optional[str] = None
    score_threshold: int = Field(default=60, ge=0, le=100)
    max_sections: int = Field(default=10, ge=1, le=20)
    max_signals_input: int = Field(default=80, ge=5, le=200)
    write_google_doc: bool = True


@router.post("/signals/business-impact")
def business_impact_endpoint(
    request: BusinessImpactRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or BusinessImpactRequest()
    try:
        return analyze_business_impact(
            since_hours=request.since_hours,
            min_score=request.min_score,
            max_workers=request.max_workers,
            force=request.force,
            max_signals_per_run=request.max_signals_per_run,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/briefings/generate")
def briefing_generate_endpoint(
    request: BriefingRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or BriefingRequest()
    try:
        return generate_daily_briefing(
            briefing_date=request.briefing_date,
            score_threshold=request.score_threshold,
            max_sections=request.max_sections,
            max_signals_input=request.max_signals_input,
            write_google_doc=request.write_google_doc,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/briefings/recent")
def briefings_recent(limit: int = Query(default=7, ge=1, le=30)):
    briefings = firestore_client.list_recent_briefings(limit=limit)
    return {
        "count": len(briefings),
        "briefings": [b.model_dump() for b in briefings],
    }


@router.get("/briefings/{briefing_id}")
def briefing_detail(briefing_id: str):
    briefing = firestore_client.get_briefing_by_id(briefing_id)
    if not briefing:
        raise HTTPException(status_code=404, detail="briefing not found")
    return briefing.model_dump()
