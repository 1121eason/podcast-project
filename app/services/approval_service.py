from datetime import datetime

from app.clients.docs_client import docs_client
from app.clients.firestore_client import firestore_client
from app.core.logging import logger
from app.models.job import (
    JOB_STATUS_APPROVED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_GENERATING_AUDIO,
    JOB_STATUS_PACKAGING,
    JOB_STATUS_PENDING_REVIEW,
    JOB_STATUS_UPLOADING_AUDIO,
)
from app.services.audio_service import generate_podcast_audio_from_script
from app.services.publish_package_service import build_publish_package
from app.services.script_service import generate_podcast_script
from app.services.storage_service import upload_audio_to_drive


class JobNotFoundError(Exception):
    pass


class InvalidJobStateError(Exception):
    pass


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _update_job(job, job_id: str, **updates):
    for key, value in updates.items():
        setattr(job, key, value)
    firestore_client.update_job(job_id, updates)
    return job


def approve_job(job_id: str, approved_by: str = "operator"):
    job = firestore_client.get_job(job_id)
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")

    if job.status == JOB_STATUS_COMPLETED and job.publish_package:
        return job

    if job.status != JOB_STATUS_PENDING_REVIEW:
        raise InvalidJobStateError(
            f"Job {job_id} must be pending_review before approval; current status is {job.status}"
        )

    if not job.doc_id:
        raise InvalidJobStateError(f"Job {job_id} has no Google Doc ID to approve")

    logger.info(f"Approving reviewed briefing for {job_id}")
    reviewed_briefing_text = docs_client.get_document_text(job.doc_id)
    if not reviewed_briefing_text.strip():
        raise InvalidJobStateError(f"Job {job_id} reviewed Google Doc is empty")

    _update_job(
        job,
        job_id,
        status=JOB_STATUS_APPROVED,
        approved_at=_utc_now(),
        approved_by=approved_by,
        error=None,
    )

    logger.info("Generating podcast script from reviewed briefing")
    script_text = generate_podcast_script(reviewed_briefing_text)
    _update_job(
        job,
        job_id,
        status=JOB_STATUS_GENERATING_AUDIO,
        script_text=script_text,
    )

    logger.info("Generating approved podcast audio")
    audio_content = generate_podcast_audio_from_script(script_text)
    _update_job(job, job_id, status=JOB_STATUS_UPLOADING_AUDIO)

    audio_url = upload_audio_to_drive(job.run_date, audio_content)
    _update_job(job, job_id, status=JOB_STATUS_PACKAGING, audio_url=audio_url)

    publish_package = build_publish_package(
        run_date=job.run_date,
        research_data=job.normalized_research_data or {},
        reviewed_briefing_text=reviewed_briefing_text,
        script_text=script_text,
        doc_url=job.doc_url or "",
        audio_url=audio_url,
    )

    return _update_job(
        job,
        job_id,
        status=JOB_STATUS_COMPLETED,
        publish_package=publish_package,
        completed_at=_utc_now(),
    )
