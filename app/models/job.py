from pydantic import BaseModel, Field
from typing import Any, Literal, Optional
from datetime import datetime

JOB_STATUS_RUNNING = "running"
JOB_STATUS_RESEARCHING = "researching"
JOB_STATUS_NORMALIZING = "normalizing"
JOB_STATUS_WRITING_BRIEFING = "writing_briefing"
JOB_STATUS_PENDING_REVIEW = "pending_review"
JOB_STATUS_APPROVED = "approved"
JOB_STATUS_GENERATING_AUDIO = "generating_audio"
JOB_STATUS_UPLOADING_AUDIO = "uploading_audio"
JOB_STATUS_PACKAGING = "packaging"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_FAILED_RESEARCH = "failed_research"
JOB_STATUS_FAILED_DOC_WRITE = "failed_doc_write"
JOB_STATUS_FAILED_PROCESSING = "failed_processing"
JOB_STATUS_CANCELLED = "cancelled"

ACTIVE_JOB_STATUSES = {
    JOB_STATUS_RUNNING,
    JOB_STATUS_RESEARCHING,
    JOB_STATUS_NORMALIZING,
    JOB_STATUS_WRITING_BRIEFING,
    JOB_STATUS_PENDING_REVIEW,
    JOB_STATUS_APPROVED,
    JOB_STATUS_GENERATING_AUDIO,
    JOB_STATUS_UPLOADING_AUDIO,
    JOB_STATUS_PACKAGING,
}

TERMINAL_JOB_STATUSES = {
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_FAILED_RESEARCH,
    JOB_STATUS_FAILED_DOC_WRITE,
    JOB_STATUS_FAILED_PROCESSING,
    JOB_STATUS_CANCELLED,
}

JobStatus = Literal[
    "running",
    "researching",
    "normalizing",
    "writing_briefing",
    "pending_review",
    "approved",
    "generating_audio",
    "uploading_audio",
    "packaging",
    "completed",
    "failed",
    "failed_research",
    "failed_doc_write",
    "failed_processing",
    "cancelled",
]

class JobRecord(BaseModel):
    job_id: str
    run_date: str
    status: JobStatus = JOB_STATUS_RESEARCHING
    interaction_id: Optional[str] = None
    interaction_status: Optional[str] = None
    research_backend: Optional[str] = None
    raw_research_output: Optional[str] = None
    normalized_research_data: Optional[dict[str, Any]] = None
    prompt_version: str = "research_v1"
    briefing_name: str = "Signal Brief 每日高訊號情資"
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None
    doc_id: Optional[str] = None
    doc_url: Optional[str] = None
    audio_url: Optional[str] = None
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    script_text: Optional[str] = None
    publish_package: Optional[dict[str, Any]] = None
    error: Optional[str] = None
