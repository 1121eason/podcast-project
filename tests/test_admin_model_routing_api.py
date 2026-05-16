import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class AdminModelRoutingApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_model_routing_requires_admin_token(self):
        response = self.client.get("/admin/model-routing")
        self.assertEqual(response.status_code, 401)

    def test_patch_model_routing_accepts_route_update(self):
        from app.api import routes_admin
        from app.core import security

        captured = {}

        def fake_set_runtime_model_routing(routes, note=None):
            captured["routes"] = routes
            captured["note"] = note
            return {"version": 1, "routes": routes, "updated_at": "now"}

        with patch.object(security.settings, "ADMIN_TOKEN", "token"), \
             patch.object(routes_admin, "set_runtime_model_routing", side_effect=fake_set_runtime_model_routing), \
             patch.object(routes_admin, "effective_model_routes", return_value={}):
            response = self.client.patch(
                "/admin/model-routing",
                headers={"X-Admin-Token": "token"},
                json={
                    "note": "w8 ab test",
                    "routes": {
                        "w8_briefing": {
                            "provider": "openai",
                            "model": "gpt-5",
                            "reasoning_effort": "medium",
                        }
                    },
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["note"], "w8 ab test")
        self.assertEqual(captured["routes"]["w8_briefing"]["provider"], "openai")
        self.assertEqual(response.json()["runtime_config"]["routes"]["w8_briefing"]["model"], "gpt-5")

    def test_patch_rejects_invalid_route(self):
        from app.core import security

        with patch.object(security.settings, "ADMIN_TOKEN", "token"):
            response = self.client.patch(
                "/admin/model-routing",
                headers={"X-Admin-Token": "token"},
                json={
                    "routes": {
                        "w7_phase_assignment": {
                            "provider": "openai",
                            "model": "gpt-5",
                        }
                    }
                },
            )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
