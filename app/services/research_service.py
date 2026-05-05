from app.clients.gemini_client import gemini_client
from app.clients.firestore_client import firestore_client
from app.models.job import (
    ACTIVE_JOB_STATUSES,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED_RESEARCH,
    JOB_STATUS_NORMALIZING,
    JOB_STATUS_RESEARCHING,
    JobRecord,
)
from app.core.logging import logger
import os

def _load_research_prompt(run_date: str, topic: str) -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "research_v1.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()
    return prompt_template.format(date=run_date, topic=topic)


def start_daily_research(run_date: str, force: bool = False) -> JobRecord:
    job_id = f"briefing_{run_date.replace('-', '_')}"
    
    existing_job = firestore_client.get_job(job_id)
    if existing_job and not force and existing_job.status in ACTIVE_JOB_STATUSES.union({JOB_STATUS_COMPLETED}):
        logger.info(f"Job {job_id} is already {existing_job.status}")
        return existing_job
    if existing_job and force:
        logger.info(f"Force restarting job: {job_id}")

    logger.info(f"Starting new research job: {job_id}")
    job_record = JobRecord(
        job_id=job_id,
        run_date=run_date,
        status=JOB_STATUS_RESEARCHING,
        interaction_status="running",
        research_backend="gemini_generate_content",
    )
    firestore_client.create_job(job_record)

    try:
        prompt = _load_research_prompt(run_date, topic="全球高訊號情資")
        raw_research_output = gemini_client.generate_research(prompt)
        firestore_client.update_job(job_id, {
            "status": JOB_STATUS_NORMALIZING,
            "interaction_status": "completed",
            "raw_research_output": raw_research_output,
        })
        job_record.status = JOB_STATUS_NORMALIZING
        job_record.interaction_status = "completed"
        job_record.raw_research_output = raw_research_output
        return job_record
    except Exception as e:
        firestore_client.update_job(job_id, {
            "status": JOB_STATUS_FAILED_RESEARCH,
            "interaction_status": "failed",
            "error": str(e),
        })
        job_record.status = JOB_STATUS_FAILED_RESEARCH
        job_record.interaction_status = "failed"
        job_record.error = str(e)
        raise
