import unittest
from unittest.mock import Mock, patch

from app.models.job import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_NORMALIZING,
    JOB_STATUS_PENDING_REVIEW,
    JobRecord,
)
from app.services import approval_service, polling_service


class FakeFirestore:
    def __init__(self, job):
        self.job = job
        self.updates = []

    def get_job(self, job_id):
        return self.job

    def update_job(self, job_id, updates):
        self.updates.append(updates)
        for key, value in updates.items():
            setattr(self.job, key, value)


class PollingAndApprovalTest(unittest.TestCase):
    def test_poll_writes_doc_and_stops_at_pending_review(self):
        job = JobRecord(
            job_id="briefing_2026_03_25",
            run_date="2026-03-25",
            status=JOB_STATUS_NORMALIZING,
            raw_research_output="raw",
        )
        fake_firestore = FakeFirestore(job)

        with (
            patch.object(polling_service, "firestore_client", fake_firestore),
            patch.object(polling_service, "normalize_research_output", return_value={"date": "2026-03-25"}),
            patch.object(
                polling_service,
                "generate_and_write_briefing",
                return_value=("https://docs.google.com/document/d/doc/edit", "doc", "draft"),
            ),
        ):
            processed = polling_service.check_and_process_job(job.job_id)

        self.assertEqual(processed.status, JOB_STATUS_PENDING_REVIEW)
        self.assertEqual(processed.doc_id, "doc")
        self.assertEqual(processed.doc_url, "https://docs.google.com/document/d/doc/edit")
        self.assertIsNone(processed.audio_url)

    def test_approve_reads_reviewed_doc_before_generating_audio(self):
        job = JobRecord(
            job_id="briefing_2026_03_25",
            run_date="2026-03-25",
            status=JOB_STATUS_PENDING_REVIEW,
            doc_id="doc",
            doc_url="https://docs.google.com/document/d/doc/edit",
            normalized_research_data={
                "global_mood": "Cautious",
                "top_developments": [
                    {
                        "title": "Supply chain shifts",
                        "business_implication": "Buyers need backup suppliers.",
                        "sources": ["https://example.com/source"],
                    }
                ],
            },
        )
        fake_firestore = FakeFirestore(job)
        fake_docs_client = Mock()
        fake_docs_client.get_document_text.return_value = "Reviewed briefing from Google Doc"

        with (
            patch.object(approval_service, "firestore_client", fake_firestore),
            patch.object(approval_service, "docs_client", fake_docs_client),
            patch.object(approval_service, "generate_podcast_script", return_value="Script from reviewed doc") as script_mock,
            patch.object(approval_service, "generate_podcast_audio_from_script", return_value=b"audio") as audio_mock,
            patch.object(approval_service, "upload_audio_to_drive", return_value="https://drive.google.com/file/d/audio/view"),
        ):
            approved = approval_service.approve_job(job.job_id, approved_by="editor")

        script_mock.assert_called_once_with("Reviewed briefing from Google Doc")
        audio_mock.assert_called_once_with("Script from reviewed doc")
        self.assertEqual(approved.status, JOB_STATUS_COMPLETED)
        self.assertEqual(approved.script_text, "Script from reviewed doc")
        self.assertEqual(approved.publish_package["audio_url"], "https://drive.google.com/file/d/audio/view")


if __name__ == "__main__":
    unittest.main()
