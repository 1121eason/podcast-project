import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class TestBriefingsApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_business_impact_requires_admin_token(self):
        r = self.client.post("/signals/business-impact")
        self.assertEqual(r.status_code, 401)

    def test_briefings_generate_requires_admin_token(self):
        r = self.client.post("/briefings/generate")
        self.assertEqual(r.status_code, 401)

    def test_briefings_recent_no_auth(self):
        from app.api import routes_briefings
        with patch.object(routes_briefings.firestore_client, "list_recent_briefings", return_value=[]):
            r = self.client.get("/briefings/recent?limit=3")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)


if __name__ == "__main__":
    unittest.main()
