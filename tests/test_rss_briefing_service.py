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

    def test_generates_briefing_with_categories(self):
        signals = [
            make_signal("s1", 90, "Iran-US peace deal", "https://example.com/1"),
            make_signal("s2", 85, "AMD AI forecast", "https://example.com/2"),
        ]
        fake_fc = FakeFirestoreClient(signals)
        fake_g = FakeGeminiClient({
            "overview": "今日訊號池呈現地緣政治緩和...",
            "categories": [
                {
                    "category_id": "geopolitics",
                    "title": "國際局勢",
                    "category_overview": "美伊衝突取得突破。",
                    "sections": [
                        {
                            "title": "美伊談判取得進展",
                            "summary": "美伊近日傳出 14 點備忘錄...",
                            "importance_score": 90,
                            "impact_type": "macro",
                            "impacted_sectors": ["energy"],
                            "watch_points": ["伊朗外長表態"],
                            "referenced_signal_ids": ["s1"],
                            "referenced_urls": ["https://example.com/1"],
                        }
                    ],
                },
                {
                    "category_id": "global_finance",
                    "title": "國際金融",
                    "category_overview": "今日無達門檻訊號",
                    "sections": [],
                },
                {
                    "category_id": "tech",
                    "title": "科技發展",
                    "category_overview": "AI 投資面有新進展。",
                    "sections": [
                        {
                            "title": "AMD AI 財測強勁",
                            "summary": "AMD 釋出強勁 AI 財測...",
                            "importance_score": 85,
                            "impact_type": "corporate",
                            "impacted_sectors": ["semiconductor"],
                            "watch_points": ["NVIDIA 財報"],
                            "referenced_signal_ids": ["s2"],
                            "referenced_urls": ["https://example.com/2"],
                        }
                    ],
                },
                {
                    "category_id": "business_trends",
                    "title": "其他商業趨勢",
                    "category_overview": "",
                    "sections": [],
                },
            ],
            "signal_pool_health": {
                "total_judged": 2,
                "high_importance_count": 2,
            },
        })

        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", fake_g):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-07", write_google_doc=False
            )

        self.assertEqual(result["selected_signal_count"], 2)
        self.assertEqual(len(result["categories"]), 4)
        # categories are in fixed order
        self.assertEqual(result["categories"][0]["category_id"], "geopolitics")
        self.assertEqual(result["categories"][1]["category_id"], "global_finance")
        self.assertEqual(result["categories"][2]["category_id"], "tech")
        self.assertEqual(result["categories"][3]["category_id"], "business_trends")
        # geopolitics has 1 section
        self.assertEqual(len(result["categories"][0]["sections"]), 1)
        # global_finance is empty
        self.assertEqual(len(result["categories"][1]["sections"]), 0)
        # flat sections aggregate all
        self.assertEqual(len(result["sections"]), 2)

    def test_missing_category_filled_empty(self):
        signals = [make_signal("s1", 75, "Test", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)
        # Gemini only returned one category; others should be filled empty
        fake_g = FakeGeminiClient({
            "overview": "test",
            "categories": [
                {
                    "category_id": "tech",
                    "title": "科技發展",
                    "category_overview": "x",
                    "sections": [
                        {
                            "title": "Test",
                            "summary": "x x x",
                            "importance_score": 75,
                            "impact_type": "tech",
                            "referenced_signal_ids": ["s1"],
                            "referenced_urls": ["https://example.com/1"],
                        }
                    ],
                }
            ],
            "signal_pool_health": {},
        })
        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", fake_g):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-07", write_google_doc=False
            )
        self.assertEqual(len(result["categories"]), 4)
        cat_ids = [c["category_id"] for c in result["categories"]]
        self.assertEqual(cat_ids, ["geopolitics", "global_finance", "tech", "business_trends"])
        # tech has 1 section, others empty
        for c in result["categories"]:
            if c["category_id"] == "tech":
                self.assertEqual(len(c["sections"]), 1)
            else:
                self.assertEqual(len(c["sections"]), 0)


if __name__ == "__main__":
    unittest.main()
