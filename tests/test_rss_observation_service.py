import unittest
from unittest.mock import patch

from app.models.rss import RssItem, RssSource
from app.services import rss_observation_service


class FakeFirestore:
    def __init__(self, items, sources):
        self.items = items
        self.sources = sources

    def list_rss_items_since(self, since_iso):
        return self.items

    def list_rss_sources(self, fetchable_only=False):
        if fetchable_only:
            return [source for source in self.sources if source.is_fetchable]
        return self.sources


class RssObservationServiceTest(unittest.TestCase):
    def test_signal_report_is_observational_not_importance_ranking(self):
        items = [
            RssItem(
                item_id="1",
                source_id="source-1",
                publisher="CNBC",
                desk="Market",
                category="Rates",
                market_level="Global",
                title="Markets watch central bank decision",
                url="https://example.com/1",
                first_seen_at="2026-05-05T00:00:00Z",
                last_seen_at="2026-05-05T00:00:00Z",
                content_hash="hash-1",
            )
        ]
        sources = [
            RssSource(source_id="source-1", feed_url="https://example.com/1", is_fetchable=True),
            RssSource(source_id="source-2", feed_url="https://example.com/2", is_fetchable=True),
        ]

        with patch.object(
            rss_observation_service,
            "firestore_client",
            FakeFirestore(items, sources),
        ):
            report = rss_observation_service.build_signal_observation_report()

        self.assertEqual(report["report_type"], "rss_signal_observation")
        self.assertTrue(report["rss_frequency_is_not_importance"])
        self.assertNotIn("importance_level", report["summary"])
        self.assertEqual(report["summary"]["fetchable_source_count"], 2)
        self.assertEqual(report["summary"]["active_source_count"], 1)
        self.assertEqual(report["summary"]["active_fetchable_source_count"], 1)
        self.assertEqual(report["summary"]["silent_fetchable_source_count"], 1)
        self.assertIn("Higher RSS frequency is an observation signal", report["caveats"][1])


if __name__ == "__main__":
    unittest.main()
