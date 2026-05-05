from app.clients.firestore_client import firestore_client
from app.models.job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_FAILED_DOC_WRITE,
    JOB_STATUS_FAILED_PROCESSING,
    JOB_STATUS_NORMALIZING,
    JOB_STATUS_PENDING_REVIEW,
    JOB_STATUS_WRITING_BRIEFING,
    TERMINAL_JOB_STATUSES,
)
from app.services.normalize_service import normalize_research_output
from app.services.docs_writer_service import generate_and_write_briefing
from app.core.logging import logger

def _update_job(job, job_id: str, **updates):
    for key, value in updates.items():
        setattr(job, key, value)
    firestore_client.update_job(job_id, updates)
    return job


def check_and_process_job(job_id: str):
    job = firestore_client.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
        
    if job.status in TERMINAL_JOB_STATUSES:
        return job

    if job.status == JOB_STATUS_PENDING_REVIEW:
        return job

    if not job.raw_research_output and not job.normalized_research_data:
        return _update_job(
            job,
            job_id,
            status=JOB_STATUS_FAILED,
            error="No research output available for processing",
        )

    try:
        _update_job(
            job,
            job_id,
            status=JOB_STATUS_NORMALIZING,
            interaction_status="completed",
            error=None,
        )
        logger.info("Research completed, processing output...")

        research_data = job.normalized_research_data
        if not research_data:
            research_data = normalize_research_output(job.raw_research_output or "")
            _update_job(job, job_id, normalized_research_data=research_data)

        _update_job(job, job_id, status=JOB_STATUS_WRITING_BRIEFING)
        doc_url, doc_id, _briefing_text = generate_and_write_briefing(job.run_date, research_data)
        logger.info("Briefing draft written, waiting for editorial approval")
        return _update_job(
            job,
            job_id,
            status=JOB_STATUS_PENDING_REVIEW,
            doc_url=doc_url,
            doc_id=doc_id,
        )
    except Exception as e:
        logger.error(f"Error processing completed research: {e}")
        failure_status = JOB_STATUS_FAILED_DOC_WRITE if "document" in str(e).lower() else JOB_STATUS_FAILED_PROCESSING
        return _update_job(job, job_id, status=failure_status, error=str(e))
