import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.signal import RssSignal


class TestSignalsApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_cluster_requires_admin_token(self):
        response = self.client.post("/signals/cluster")
        self.assertEqual(response.status_code, 401)

    def test_embed_requires_admin_token(self):
        response = self.client.post("/signals/embed")
        self.assertEqual(response.status_code, 401)

    def test_process_new_items_requires_admin_token(self):
        response = self.client.post("/signals/process-new-items")
        self.assertEqual(response.status_code, 401)

    def test_cluster_calls_service(self):
        from app.api import routes_signals

        captured = {}

        def fake_run_clustering(window_hours, distance_threshold):
            captured["window_hours"] = window_hours
            captured["distance_threshold"] = distance_threshold
            return {"run_id": "fake_run", "cluster_count": 3}

        with patch.object(routes_signals, "run_clustering", side_effect=fake_run_clustering):
            response = self.client.post(
                "/signals/cluster",
                headers={"X-Admin-Token": _get_admin_token()},
                json={"window_hours": 6},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run_id"], "fake_run")
        self.assertEqual(captured["window_hours"], 6)

    def test_process_new_items_calls_service(self):
        from app.api import routes_signals

        captured = {}

        def fake_process_new_items(**kwargs):
            captured.update(kwargs)
            return {"processed_item_count": 2, "skipped_duplicate": False}

        with patch.object(routes_signals, "process_new_items", side_effect=fake_process_new_items):
            response = self.client.post(
                "/signals/process-new-items",
                headers={"X-Admin-Token": _get_admin_token()},
                json={
                    "since_hours": 6,
                    "limit_items": 25,
                    "run_bucket": "UTC_TEST",
                    "model_overrides": {
                        "w4_match_adjudication": {
                            "provider": "gemini",
                            "model": "gemini-2.5-flash",
                        }
                    },
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["processed_item_count"], 2)
        self.assertEqual(captured["limit_items"], 25)
        self.assertEqual(captured["run_bucket"], "UTC_TEST")
        self.assertEqual(captured["model_overrides"]["w4_match_adjudication"]["model"], "gemini-2.5-flash")

    def test_consolidate_daily_calls_service(self):
        from app.api import routes_signals

        captured = {}

        def fake_consolidate_daily(**kwargs):
            captured.update(kwargs)
            return {"threads_updated": 3, "skipped_duplicate": False}

        with patch.object(routes_signals, "consolidate_daily", side_effect=fake_consolidate_daily):
            response = self.client.post(
                "/signals/consolidate-daily",
                headers={"X-Admin-Token": _get_admin_token()},
                json={"since_hours": 36, "story_lookback_days": 30, "run_bucket": "DAILY_TEST"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["threads_updated"], 3)
        self.assertEqual(captured["story_lookback_days"], 30)
        self.assertEqual(captured["run_bucket"], "DAILY_TEST")

    def test_recent_signals(self):
        from app.api import routes_signals

        signal = RssSignal(
            signal_id="sig_test",
            generated_at="2026-05-06T00:00:00Z",
            window_start="2026-05-06T00:00:00Z",
            window_end="2026-05-06T04:00:00Z",
            cluster_size=3,
            source_count=2,
            publisher_count=2,
            publishers=["CNBC", "Reuters"],
            representative_title="Anthropic raises funding",
        )

        with patch.object(routes_signals.firestore_client, "list_recent_signals", return_value=[signal]):
            response = self.client.get("/signals/recent?hours=24")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["signals"][0]["signal_id"], "sig_test")


def _get_admin_token() -> str:
    from app.core.config import settings
    return settings.ADMIN_TOKEN or "x"


if __name__ == "__main__":
    unittest.main()
