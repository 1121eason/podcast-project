import unittest
from unittest.mock import patch

from app.models.signal import RssSignal
from app.services import rss_business_impact_service


def make_signal(**kw):
    base = dict(
        signal_id=kw.get("signal_id", "sig_test"),
        generated_at="2026-05-07T00:00:00Z",
        window_start="2026-05-06T20:00:00Z",
        window_end="2026-05-07T00:00:00Z",
        cluster_size=1,
        source_count=2,
        publisher_count=2,
        publishers=["CNBC", "Reuters"],
        representative_title=kw.get("representative_title", "Test event"),
        representative_summary=kw.get("representative_summary", "Test summary"),
        representative_publisher=kw.get("representative_publisher", "CNBC"),
        cluster_status="partially_supported",
        topic_heat="medium",
        importance_score=kw.get("importance_score", 75),
        impact_type=kw.get("impact_type", "industry"),
        key_entities=kw.get("key_entities", ["Anthropic"]),
        regions=kw.get("regions", ["US"]),
        impact_judged_at=kw.get("impact_judged_at"),
    )
    return RssSignal(**base)


class FakeFirestoreClient:
    def __init__(self, signals):
        self.signals = signals
        self.upserted = []
        self.run_record = None

    def list_signals_for_impact(self, since_iso, min_score=60, limit=200, force=False):
        out = []
        for s in self.signals:
            if (s.importance_score or 0) < min_score:
                continue
            if not force and s.impact_judged_at:
                continue
            out.append(s)
        return out[:limit]

    def upsert_rss_signals(self, signals):
        self.upserted.extend(signals)
        return len(signals)

    def create_business_impact_run(self, run):
        self.run_record = run


class FakeGeminiClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate_json(self, prompt, model="gemini-2.5-pro"):
        self.calls += 1
        return self.payload, 300, 80


class TestPromptRendering(unittest.TestCase):
    def test_prompt_includes_fields(self):
        s = make_signal(representative_title="Anthropic raises $1.5B")
        prompt = rss_business_impact_service._render_prompt(s)
        self.assertIn("Anthropic raises $1.5B", prompt)
        self.assertIn("75", prompt)


class TestValidatePayload(unittest.TestCase):
    def test_valid(self):
        out = rss_business_impact_service._validate_payload({
            "impacted_sectors": ["semiconductor"],
            "impacted_assets": ["NVDA"],
            "impacted_regions": ["US"],
            "watch_points": ["Q3 earnings"],
            "counterfactual": "deal collapses",
            "gap_note": "no SEC filing yet",
        })
        self.assertEqual(out["impacted_sectors"], ["semiconductor"])
        self.assertEqual(out["counterfactual"], "deal collapses")

    def test_missing_lists_default_empty(self):
        out = rss_business_impact_service._validate_payload({})
        self.assertEqual(out["impacted_sectors"], [])
        self.assertEqual(out["counterfactual"], "")


class TestAnalyzeFlow(unittest.TestCase):
    def test_writes_impact_to_signal(self):
        s = make_signal()
        fake_fc = FakeFirestoreClient([s])
        fake_g = FakeGeminiClient({
            "impacted_sectors": ["AI", "semiconductor"],
            "impacted_assets": ["NVDA"],
            "impacted_regions": ["US"],
            "watch_points": ["Q3 earnings"],
            "counterfactual": "deal collapses",
            "gap_note": "missing SEC filing",
        })
        with patch.object(rss_business_impact_service, "firestore_client", fake_fc), \
             patch.object(rss_business_impact_service, "gemini_client", fake_g), \
             patch.object(rss_business_impact_service.openai_client, "client", None):
            result = rss_business_impact_service.analyze_business_impact(max_workers=1)
        self.assertEqual(result["analyzed_signal_count"], 1)
        self.assertEqual(len(fake_fc.upserted), 1)
        self.assertEqual(fake_fc.upserted[0].impacted_sectors, ["AI", "semiconductor"])
        self.assertIsNotNone(fake_fc.upserted[0].impact_judged_at)

    def test_skips_already_analyzed(self):
        s = make_signal(impact_judged_at="2026-05-06T00:00:00Z")
        fake_fc = FakeFirestoreClient([s])
        fake_g = FakeGeminiClient({})
        with patch.object(rss_business_impact_service, "firestore_client", fake_fc), \
             patch.object(rss_business_impact_service, "gemini_client", fake_g), \
             patch.object(rss_business_impact_service.openai_client, "client", None):
            result = rss_business_impact_service.analyze_business_impact(max_workers=1)
        self.assertEqual(result["analyzed_signal_count"], 0)
        self.assertEqual(fake_g.calls, 0)


if __name__ == "__main__":
    unittest.main()
