import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import security
from app.main import app


class SourcesApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_sheet_sync_requires_admin_token(self):
        with patch.object(security.settings, "ADMIN_TOKEN", "secret"):
            response = self.client.post("/sources/sheets/sync")

        self.assertEqual(response.status_code, 401)

    def test_sheet_sync_accepts_admin_token(self):
        with (
            patch.object(security.settings, "ADMIN_TOKEN", "secret"),
            patch(
                "app.api.routes_sources.sync_rss_sources_from_sheet",
                return_value={"synced_source_count": 1},
            ),
        ):
            response = self.client.post(
                "/sources/sheets/sync",
                headers={"X-Admin-Token": "secret"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["synced_source_count"], 1)

    def test_rss_ingest_requires_admin_token(self):
        with patch.object(security.settings, "ADMIN_TOKEN", "secret"):
            response = self.client.post("/sources/rss/ingest")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
