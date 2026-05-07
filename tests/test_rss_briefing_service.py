import unittest
from unittest.mock import patch

from app.models.signal import RssSignal
from app.services import rss_briefing_service


def make_signal(sid, score, title, url, publishers=None):
    return RssSignal(
        signal_id=sid,
        generated_at="2026-05-07T00:00:00Z",
        window_start="2026-05-06T20:00:00Z",
        window_end="2026-05-07T00:00:00Z",
        cluster_size=2,
        source_count=2,
        publisher_count=2,
        publishers=publishers or ["CNBC", "Reuters"],
        representative_title=title,
        representative_url=url,
        representative_publisher=(publishers or ["CNBC"])[0],
        cluster_status="partially_supported",
        topic_heat="medium",
        importance_score=score,
        impact_type="market",
    )


class FakeFirestoreClient:
    def __init__(self, signals):
        self.signals = signals
        self.briefing_written = None

    def list_signals_for_briefing(self, since_iso, min_score=70, limit=80):
        return [s for s in self.signals if (s.importance_score or 0) >= min_score][:limit]

    def upsert_briefing(self, briefing):
        self.briefing_written = briefing


class FakeGeminiClient:
    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, prompt):
        return self.payload, 1500, 400


class TestBriefingFlow(unittest.TestCase):
    def test_no_signals_writes_empty_briefing(self):
        fake_fc = FakeFirestoreClient([])
        with patch.object(rss_briefing_service, "firestore_client", fake_fc):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-07", write_google_doc=False
            )
        self.assertEqual(result["selected_signal_count"], 0)
        self.assertEqual(result["overview"], "今日無達門檻訊號。")

    def test_generates_briefing_with_sections(self):
        signals = [
            make_signal("s1", 90, "Iran-US peace deal", "https://example.com/1"),
            make_signal("s2", 85, "AMD AI forecast", "https://example.com/2"),
        ]
        fake_fc = FakeFirestoreClient(signals)
        fake_g = FakeGeminiClient({
            "overview": "今日訊號池呈現地緣政治緩和...",
            "sections": [
                {
                    "title": "美伊談判取得進展",
                    "summary": "美伊近日傳出 14 點備忘錄...",
                    "importance_score": 90,
                    "impact_type": "macro",
                    "impacted_sectors": ["energy", "global markets"],
                    "watch_points": ["伊朗外長表態"],
                    "referenced_signal_ids": ["s1"],
                    "referenced_urls": ["https://example.com/1"],
                },
                {
                    "title": "AMD AI 財測強勁",
                    "summary": "AMD 釋出強勁 AI 財測...",
                    "importance_score": 85,
                    "impact_type": "corporate",
                    "impacted_sectors": ["semiconductor"],
                    "watch_points": ["NVIDIA 財報"],
                    "referenced_signal_ids": ["s2"],
                    "referenced_urls": ["https://example.com/2"],
                },
            ],
            "signal_pool_health": {
                "total_judged": 2,
                "high_importance_count": 2,
                "main_themes": ["geopolitics", "AI"],
                "coverage_gaps": [],
            },
        })

        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", fake_g):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-07", write_google_doc=False
            )

        self.assertEqual(result["selected_signal_count"], 2)
        self.assertEqual(len(result["sections"]), 2)
        self.assertEqual(result["sections"][0]["title"], "美伊談判取得進展")
        self.assertIn("https://example.com/1", result["sections"][0]["referenced_urls"])

    def test_invalid_signal_ids_filtered(self):
        signals = [make_signal("s1", 90, "Real signal", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)
        fake_g = FakeGeminiClient({
            "overview": "test overview",
            "sections": [
                {
                    "title": "A",
                    "summary": "x",
                    "importance_score": 90,
                    "impact_type": "macro",
                    "referenced_signal_ids": ["s1", "fake_id_999"],
                    "referenced_urls": [],
                }
            ],
            "signal_pool_health": {},
        })
        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", fake_g):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-07", write_google_doc=False
            )
        section = result["sections"][0]
        self.assertEqual(section["referenced_signal_ids"], ["s1"])
        self.assertIn("https://example.com/1", section["referenced_urls"])


if __name__ == "__main__":
    unittest.main()
