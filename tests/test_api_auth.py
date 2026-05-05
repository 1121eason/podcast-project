import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import security
from app.main import app
from app.models.job import JobRecord


class ApiAuthTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_mutating_endpoint_rejects_missing_admin_token(self):
        with patch.object(security.settings, "ADMIN_TOKEN", "secret"):
            response = self.client.post(
                "/jobs/daily-briefing/start",
                json={"run_date": "2026-03-25"},
            )

        self.assertEqual(response.status_code, 401)

    def test_mutating_endpoint_accepts_valid_admin_token(self):
        job = JobRecord(job_id="briefing_2026_03_25", run_date="2026-03-25")

        with (
            patch.object(security.settings, "ADMIN_TOKEN", "secret"),
            patch("app.api.routes_jobs.start_daily_research", return_value=job),
        ):
            response = self.client.post(
                "/jobs/daily-briefing/start",
                headers={"X-Admin-Token": "secret"},
                json={"run_date": "2026-03-25"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["job_id"], "briefing_2026_03_25")


if __name__ == "__main__":
    unittest.main()
