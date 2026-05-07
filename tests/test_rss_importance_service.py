import unittest
from unittest.mock import patch

from app.models.signal import RssSignal
from app.services import rss_importance_service


def make_signal(**kwargs):
    base = dict(
        signal_id=kwargs.get("signal_id", "sig_test"),
        generated_at="2026-05-07T00:00:00Z",
        window_start="2026-05-06T20:00:00Z",
        window_end="2026-05-07T00:00:00Z",
        cluster_size=1,
        source_count=1,
        publisher_count=1,
        publishers=kwargs.get("publishers", ["CNBC"]),
        market_levels=kwargs.get("market_levels", ["Global"]),
        cluster_status=kwargs.get("cluster_status", "single_source"),
        topic_heat=kwargs.get("topic_heat", "low"),
        representative_title=kwargs.get("representative_title", "Test title"),
        representative_summary=kwargs.get("representative_summary", "Test summary"),
        importance_score=kwargs.get("importance_score"),
    )
    return RssSignal(**base)


class FakeFirestoreClient:
    def __init__(self, signals):
        self.signals = signals
        self.upserted = []
        self.run_record = None

    def list_recent_signals(self, since_iso, limit=2000):
        return list(self.signals)

    def upsert_rss_signals(self, signals):
        self.upserted.extend(signals)
        return len(signals)

    def create_judgement_run(self, run):
        self.run_record = run


class FakeGeminiClient:
    def __init__(self, payload, input_tokens=400, output_tokens=80):
        self.payload = payload
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = []

    def generate_json(self, prompt):
        self.calls.append(prompt)
        return self.payload, self.input_tokens, self.output_tokens


class TestPromptRendering(unittest.TestCase):
    def test_render_prompt_substitutes_fields(self):
        signal = make_signal(
            representative_title="Anthropic raises $1.5B",
            publishers=["CNBC", "Reuters"],
            market_levels=["Global"],
        )
        prompt = rss_importance_service._render_prompt(signal)
        self.assertIn("Anthropic raises $1.5B", prompt)
        self.assertIn("CNBC, Reuters", prompt)
        self.assertIn("Global", prompt)


class TestValidatePayload(unittest.TestCase):
    def test_valid_payload(self):
        out = rss_importance_service._validate_payload({
            "importance_score": 75,
            "impact_type": "market",
            "key_entities": ["Anthropic", "Goldman"],
            "regions": ["US"],
            "reasoning": "AI funding",
            "heat_vs_importance_note": "",
        })
        self.assertEqual(out["importance_score"], 75)
        self.assertEqual(out["impact_type"], "market")

    def test_missing_score_raises(self):
        with self.assertRaises(ValueError):
            rss_importance_service._validate_payload({
                "impact_type": "market",
                "key_entities": [],
                "regions": [],
                "reasoning": "x",
            })

    def test_invalid_impact_type_raises(self):
        with self.assertRaises(ValueError):
            rss_importance_service._validate_payload({
                "importance_score": 50,
                "impact_type": "weather",
                "key_entities": [],
                "regions": [],
                "reasoning": "x",
            })

    def test_score_out_of_range(self):
        with self.assertRaises(ValueError):
            rss_importance_service._validate_payload({
                "importance_score": 150,
                "impact_type": "market",
                "key_entities": [],
                "regions": [],
                "reasoning": "x",
            })


class TestJudgeFlow(unittest.TestCase):
    def test_judge_writes_score(self):
        signal = make_signal(
            signal_id="s1",
            cluster_status="confirmed",
            topic_heat="high",
        )
        fake_fc = FakeFirestoreClient([signal])
        fake_gemini = FakeGeminiClient({
            "importance_score": 82,
            "impact_type": "market",
            "key_entities": ["Anthropic"],
            "regions": ["US"],
            "reasoning": "Big AI funding",
            "heat_vs_importance_note": "",
        })

        with patch.object(rss_importance_service, "firestore_client", fake_fc), \
             patch.object(rss_importance_service, "gemini_client", fake_gemini):
            result = rss_importance_service.judge_signals(since_hours=4, max_workers=1)

        self.assertEqual(result["judged_signal_count"], 1)
        self.assertEqual(result["score_80plus_count"], 1)
        self.assertEqual(len(fake_fc.upserted), 1)
        self.assertEqual(fake_fc.upserted[0].importance_score, 82)
        self.assertEqual(fake_fc.upserted[0].impact_type, "market")

    def test_skips_already_judged(self):
        signal = make_signal(
            signal_id="s1",
            cluster_status="confirmed",
            topic_heat="high",
            importance_score=70,
        )
        fake_fc = FakeFirestoreClient([signal])
        fake_gemini = FakeGeminiClient({
            "importance_score": 50,
            "impact_type": "market",
            "key_entities": [],
            "regions": [],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        })
        with patch.object(rss_importance_service, "firestore_client", fake_fc), \
             patch.object(rss_importance_service, "gemini_client", fake_gemini):
            result = rss_importance_service.judge_signals(since_hours=4, max_workers=1)
        self.assertEqual(result["judged_signal_count"], 0)
        self.assertEqual(result["skipped_already_judged_count"], 1)
        self.assertEqual(len(fake_gemini.calls), 0)

    def test_skips_unverified(self):
        signal = make_signal(
            signal_id="s1",
            cluster_status=None,
            topic_heat=None,
        )
        fake_fc = FakeFirestoreClient([signal])
        fake_gemini = FakeGeminiClient({
            "importance_score": 50,
            "impact_type": "market",
            "key_entities": [],
            "regions": [],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        })
        with patch.object(rss_importance_service, "firestore_client", fake_fc), \
             patch.object(rss_importance_service, "gemini_client", fake_gemini):
            result = rss_importance_service.judge_signals(since_hours=4, max_workers=1)
        self.assertEqual(result["judged_signal_count"], 0)
        self.assertEqual(result["skipped_unverified_count"], 1)


class TestGuardRails(unittest.TestCase):
    def test_market_wrap_caps_score(self):
        payload = {
            "importance_score": 90,
            "impact_type": "macro",
            "key_entities": ["Iran"],
            "regions": ["Global"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload, title="【歐股盤後】收漲", summary="", source_count=1, topic_heat="low"
        )
        self.assertEqual(out["importance_score"], 45)
        self.assertIn("market_wrap", out["heat_vs_importance_note"])

    def test_market_wrap_english_pattern(self):
        payload = {
            "importance_score": 80,
            "impact_type": "market",
            "key_entities": [],
            "regions": [],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload, title="Stocks rise as market closes higher", summary="", source_count=1, topic_heat="low"
        )
        self.assertEqual(out["importance_score"], 45)

    def test_single_corp_earnings_caps(self):
        payload = {
            "importance_score": 80,
            "impact_type": "corporate",
            "key_entities": ["Fortinet Inc."],
            "regions": ["US"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="Fortinet Jumps on Outlook Hike",
            summary="",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 65)

    def test_systemic_company_not_capped(self):
        payload = {
            "importance_score": 78,
            "impact_type": "corporate",
            "key_entities": ["Apple", "iPhone"],
            "regions": ["Global"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="Apple beats earnings expectations",
            summary="",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 78)

    def test_market_wrap_under_cap_unchanged(self):
        payload = {
            "importance_score": 30,
            "impact_type": "market",
            "key_entities": [],
            "regions": [],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload, title="美股收漲", summary="", source_count=1, topic_heat="low"
        )
        self.assertEqual(out["importance_score"], 30)

    def test_public_health_no_market_caps(self):
        payload = {
            "importance_score": 92,
            "impact_type": "macro",
            "key_entities": ["cruise ship", "Hantavirus"],
            "regions": ["US"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="クルーズ船感染ハンタウイルス",
            summary="cruise ship outbreak",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 65)
        self.assertIn("public-health", out["heat_vs_importance_note"])

    def test_public_health_summary_only_does_not_trigger(self):
        # Title doesn't mention health; only summary does (e.g. metaphorical 感染力).
        # Guard should NOT fire.
        payload = {
            "importance_score": 80,
            "impact_type": "industry",
            "key_entities": ["China", "Wind Power Industry"],
            "regions": ["CN"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="中国对风电的大力投资正在获得回报",
            summary="這份政策具有感染力，影響整個產業鏈",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 80)

    def test_public_health_with_market_entity_not_capped(self):
        payload = {
            "importance_score": 80,
            "impact_type": "macro",
            "key_entities": ["Pfizer", "stock", "vaccine"],
            "regions": ["US"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="New disease outbreak boosts Pfizer stock",
            summary="",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 80)

    def test_analysis_feature_caps(self):
        payload = {
            "importance_score": 82,
            "impact_type": "corporate",
            "key_entities": ["Apple", "Cook", "AI"],
            "regions": ["Global"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="為何庫克在交棒前突然加碼AI？",
            summary="",
            source_count=1,
            topic_heat="low",
        )
        self.assertEqual(out["importance_score"], 60)
        self.assertIn("analysis", out["heat_vs_importance_note"])

    def test_analysis_multi_source_not_capped(self):
        payload = {
            "importance_score": 75,
            "impact_type": "corporate",
            "key_entities": ["Apple"],
            "regions": ["Global"],
            "reasoning": "x",
            "heat_vs_importance_note": "",
        }
        out = rss_importance_service._apply_guard_rails(
            payload,
            title="Why Apple is doubling down on AI",
            summary="",
            source_count=3,
            topic_heat="medium",
        )
        self.assertEqual(out["importance_score"], 75)

    def test_summary_truncation(self):
        from app.models.signal import RssSignal

        signal = RssSignal(
            signal_id="s1",
            generated_at="2026-05-07T00:00:00Z",
            window_start="2026-05-06T20:00:00Z",
            window_end="2026-05-07T00:00:00Z",
            cluster_size=1,
            source_count=1,
            publisher_count=1,
            publishers=["CNBC"],
            representative_title="Test",
            representative_summary="x" * 5000,
            cluster_status="single_source",
            topic_heat="low",
        )
        prompt = rss_importance_service._render_prompt(signal)
        self.assertNotIn("x" * 400, prompt)


if __name__ == "__main__":
    unittest.main()
