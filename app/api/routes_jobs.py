from app.services.research_service import start_daily_research
from app.services.polling_service import check_and_process_job
from app.services.approval_service import (
    InvalidJobStateError,
    JobNotFoundError,
    approve_job,
)
from app.clients.firestore_client import firestore_client
from app.core.security import require_admin_token
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()

class StartJobRequest(BaseModel):
    run_date: str
    force: bool = False

class ApproveJobRequest(BaseModel):
    approved_by: str = "operator"

@router.post("/daily-briefing/start")
def start_daily_briefing(
    request: StartJobRequest,
    _: None = Depends(require_admin_token),
):
    try:
        job = start_daily_research(request.run_date, force=request.force)
        return job.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{job_id}/poll")
def poll_job(job_id: str, _: None = Depends(require_admin_token)):
    try:
        job = check_and_process_job(job_id)
        return job.model_dump()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{job_id}")
def get_job(job_id: str):
    job = firestore_client.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()

@router.post("/{job_id}/approve")
def approve_daily_briefing(
    job_id: str,
    request: ApproveJobRequest,
    _: None = Depends(require_admin_token),
):
    try:
        job = approve_job(job_id, approved_by=request.approved_by)
        return job.model_dump()
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidJobStateError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{job_id}/publish-package")
def get_publish_package(job_id: str):
    job = firestore_client.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.publish_package:
        raise HTTPException(status_code=404, detail="Publish package not available")
    return job.publish_package
