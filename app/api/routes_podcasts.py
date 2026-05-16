from typing import Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.model_routing_payloads import ModelRouteOverride, dump_model_overrides
from app.clients.firestore_client import firestore_client
from app.core.config import settings
from app.core.security import require_admin_token
from app.services.rss_podcast_script_service import generate_daily_podcast_script
from app.services.rss_podcast_run_service import run_daily_podcast

router = APIRouter()


class PodcastScriptRequest(BaseModel):
    briefing_id: Optional[str] = None
    write_google_doc: bool = True
    run_bucket: Optional[str] = None
    model_overrides: Optional[dict[str, ModelRouteOverride]] = None


class PodcastRunDailyRequest(BaseModel):
    briefing_id: Optional[str] = None
    write_google_doc: bool = True
    force_audio: bool = False
    force_package: bool = False
    run_bucket: Optional[str] = None
    model_overrides: Optional[dict[str, ModelRouteOverride]] = None


def _today_date_str() -> str:
    try:
        tz = ZoneInfo(settings.BRIEFING_TIMEZONE or "UTC")
    except ZoneInfoNotFoundError:
        tz = timezone.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


@router.post("/podcasts/generate-script")
def podcast_generate_script(
    request: PodcastScriptRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or PodcastScriptRequest()
    try:
        return generate_daily_podcast_script(
            briefing_id=request.briefing_id,
            write_google_doc=request.write_google_doc,
            run_bucket=request.run_bucket,
            model_overrides=dump_model_overrides(request.model_overrides),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/podcasts/run-daily")
def podcast_run_daily(
    request: PodcastRunDailyRequest | None = None,
    _: None = Depends(require_admin_token),
):
    request = request or PodcastRunDailyRequest()
    try:
        return run_daily_podcast(
            briefing_id=request.briefing_id,
            write_google_doc=request.write_google_doc,
            force_audio=request.force_audio,
            force_package=request.force_package,
            run_bucket=request.run_bucket,
            model_overrides=dump_model_overrides(request.model_overrides),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/podcasts/recent")
def podcasts_recent(limit: int = Query(default=7, ge=1, le=30)):
    scripts = firestore_client.list_recent_podcast_scripts(limit=limit)
    return {
        "count": len(scripts),
        "scripts": [s.model_dump() for s in scripts],
    }


@router.get("/podcasts/today")
def podcast_today():
    today = _today_date_str()
    scripts = firestore_client.list_recent_podcast_scripts(limit=30)
    script = next((s for s in scripts if s.briefing_date == today), None)
    if not script:
        raise HTTPException(status_code=404, detail="today's podcast script not found")
    episode = firestore_client.get_podcast_episode_by_script_id(script.script_id)
    package = firestore_client.get_publish_package_by_script_id(script.script_id)
    return {
        "briefing_date": today,
        "script": script.model_dump(),
        "episode": episode.model_dump() if episode else None,
        "publish_package": package.model_dump() if package else None,
    }


@router.get("/podcasts/{script_id}/episode")
def podcast_episode(script_id: str):
    episode = firestore_client.get_podcast_episode_by_script_id(script_id)
    if not episode:
        raise HTTPException(status_code=404, detail="podcast episode not found")
    return episode.model_dump()


@router.get("/podcasts/{script_id}/publish-package")
def podcast_publish_package(script_id: str):
    package = firestore_client.get_publish_package_by_script_id(script_id)
    if not package:
        raise HTTPException(status_code=404, detail="podcast publish package not found")
    return package.model_dump()


@router.get("/podcasts/{script_id}")
def podcast_detail(script_id: str):
    script = firestore_client.get_podcast_script_by_id(script_id)
    if not script:
        raise HTTPException(status_code=404, detail="podcast script not found")
    return script.model_dump()
