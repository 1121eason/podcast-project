import unittest
from unittest.mock import patch

from app.services import model_routing_service


class FakeRuntimeConfigStore:
    def __init__(self, config=None):
        self.config = config or {}
        self.written = None

    def get_runtime_config(self, config_id):
        return self.config

    def set_runtime_config(self, config_id, payload):
        self.written = (config_id, payload)
        self.config = payload


class ModelRoutingServiceTest(unittest.TestCase):
    def tearDown(self):
        model_routing_service.clear_model_routing_cache()

    def test_request_override_beats_runtime_config(self):
        fake = FakeRuntimeConfigStore(
            {
                "version": 1,
                "routes": {
                    "w8_briefing": {
                        "provider": "gemini",
                        "model": "gemini-2.5-pro",
                    }
                },
            }
        )
        with patch.dict("os.environ", {"MODEL_ROUTING_RUNTIME_ENABLED": "true"}), \
             patch.object(model_routing_service, "firestore_client", fake):
            route = model_routing_service.resolve_model_route(
                "w8_briefing",
                {
                    "w8_briefing": {
                        "provider": "openai",
                        "model": "gpt-5",
                        "reasoning_effort": "low",
                    }
                },
            )
        self.assertEqual(route.provider, "openai")
        self.assertEqual(route.model, "gpt-5")
        self.assertEqual(route.reasoning_effort, "low")
        self.assertEqual(route.source, "request")

    def test_invalid_provider_for_gemini_only_route_is_rejected(self):
        with self.assertRaises(ValueError):
            model_routing_service.validate_model_overrides(
                {"w7_phase_assignment": {"provider": "openai", "model": "gpt-5"}}
            )

    def test_set_runtime_model_routing_preserves_existing_routes(self):
        fake = FakeRuntimeConfigStore(
            {
                "version": 1,
                "routes": {
                    "w5_judgement": {
                        "provider": "gemini",
                        "model": "gemini-2.5-flash",
                    }
                },
            }
        )
        with patch.dict("os.environ", {"MODEL_ROUTING_RUNTIME_ENABLED": "true"}), \
             patch.object(model_routing_service, "firestore_client", fake):
            out = model_routing_service.set_runtime_model_routing(
                {
                    "w9_podcast_script": {
                        "provider": "gemini",
                        "model": "gemini-2.5-pro",
                    }
                },
                note="ab-test",
            )
        self.assertEqual(out["routes"]["w5_judgement"]["model"], "gemini-2.5-flash")
        self.assertEqual(out["routes"]["w9_podcast_script"]["model"], "gemini-2.5-pro")
        self.assertEqual(fake.written[0], "model_routing")


if __name__ == "__main__":
    unittest.main()
