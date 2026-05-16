from app.clients.firestore_client import firestore_client
from app.models.signal import WorkflowRun
from app.services.signal_v2_utils import stable_hash, utc_now_iso


def make_run_id(workflow_name: str, run_bucket: str) -> str:
    safe_workflow = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in workflow_name)
    safe_bucket = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in run_bucket)
    return f"{safe_workflow}_{safe_bucket}"


def start_workflow_run(
    workflow_name: str,
    run_bucket: str | None,
    request_payload: dict,
) -> tuple[bool, str, dict]:
    """
    Returns (should_skip, run_id, existing_summary).
    No run_bucket means no idempotency guard, useful for local/manual calls.
    """
    if not run_bucket:
        return False, "", {}

    run_id = make_run_id(workflow_name, run_bucket)
    request_hash = stable_hash(request_payload)
    existing = firestore_client.get_workflow_run(run_id)
    if existing and existing.status in {"running", "completed"}:
        summary = dict(existing.summary or {})
        summary.setdefault("workflow_status", existing.status)
        summary.setdefault("request_hash", existing.request_hash)
        summary.setdefault("incoming_request_hash", request_hash)
        return True, run_id, summary

    run = WorkflowRun(
        run_id=run_id,
        workflow_name=workflow_name,
        run_bucket=run_bucket,
        status="running",
        started_at=utc_now_iso(),
        request_hash=request_hash,
    )
    created = firestore_client.create_workflow_run(run)
    if not created:
        existing = firestore_client.get_workflow_run(run_id)
        if existing and existing.status in {"running", "completed"}:
            summary = dict(existing.summary or {})
            summary.setdefault("workflow_status", existing.status)
            summary.setdefault("request_hash", existing.request_hash)
            summary.setdefault("incoming_request_hash", request_hash)
            return True, run_id, summary
    return False, run_id, {}


def complete_workflow_run(run_id: str, summary: dict) -> None:
    if not run_id:
        return
    firestore_client.update_workflow_run(
        run_id,
        {
            "status": "completed",
            "completed_at": utc_now_iso(),
            "summary": summary,
            "error": None,
        },
    )


def fail_workflow_run(run_id: str, error: str, summary: dict | None = None) -> None:
    if not run_id:
        return
    firestore_client.update_workflow_run(
        run_id,
        {
            "status": "failed",
            "completed_at": utc_now_iso(),
            "summary": summary or {},
            "error": error,
        },
    )
