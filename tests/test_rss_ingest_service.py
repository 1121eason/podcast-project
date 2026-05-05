import unittest
from unittest.mock import patch

from app.models.rss import RssSource
from app.services import rss_ingest_service


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Central bank holds rates</title>
      <link>https://example.com/rates</link>
      <guid>rates-1</guid>
      <description><![CDATA[Policy makers stayed cautious.]]></description>
      <pubDate>Tue, 05 May 2026 01:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Chip supply chain shifts</title>
      <link>https://example.com/chips</link>
      <guid>chips-1</guid>
      <description>New capacity comes online.</description>
      <pubDate>Tue, 05 May 2026 02:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class FakeFirestore:
    def __init__(self, sources):
        self.sources = sources
        self.items = {}
        self.runs = []

    def list_rss_sources(self, fetchable_only=False):
        if fetchable_only:
            return [source for source in self.sources if source.is_fetchable]
        return self.sources

    def upsert_rss_item(self, item):
        if item.item_id in self.items:
            self.items[item.item_id] = item
            return False
        self.items[item.item_id] = item
        return True

    def upsert_rss_items(self, items):
        new_item_count = 0
        updated_item_count = 0
        for item in items:
            if self.upsert_rss_item(item):
                new_item_count += 1
            else:
                updated_item_count += 1
        return new_item_count, updated_item_count

    def create_rss_ingest_run(self, run):
        self.runs.append(run)

    def update_rss_source_ingest_results(self, source_results, ingested_at):
        self.source_results = source_results
        self.ingested_at = ingested_at


class RssIngestServiceTest(unittest.TestCase):
    def test_parse_feed_items_extracts_required_fields(self):
        source = RssSource(
            source_id="source-1",
            publisher="Reuters",
            desk="Market",
            category="Rates",
            feed_url="https://example.com/rss",
        )

        items = rss_ingest_service.parse_feed_items(
            RSS_XML,
            source,
            seen_at="2026-05-05T00:00:00Z",
        )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "Central bank holds rates")
        self.assertEqual(items[0].published_at, "2026-05-05T01:00:00Z")
        self.assertEqual(items[0].publisher, "Reuters")
        self.assertTrue(items[0].content_hash)

    def test_ingest_dedupes_items_and_keeps_running_after_broken_feed(self):
        sources = [
            RssSource(source_id="ok", feed_url="https://example.com/ok", is_fetchable=True),
            RssSource(source_id="bad", feed_url="https://example.com/bad", is_fetchable=True),
        ]
        fake_firestore = FakeFirestore(sources)

        def fake_fetch(url, timeout_seconds=10):
            if url.endswith("/bad"):
                raise RuntimeError("upstream 503")
            return RSS_XML

        with (
            patch.object(rss_ingest_service, "firestore_client", fake_firestore),
            patch.object(rss_ingest_service, "fetch_feed_xml", side_effect=fake_fetch),
        ):
            first_run = rss_ingest_service.ingest_rss_sources(since_hours=None)
            second_run = rss_ingest_service.ingest_rss_sources(since_hours=None)

        self.assertEqual(first_run["new_item_count"], 2)
        self.assertEqual(first_run["failed_source_count"], 1)
        self.assertEqual(first_run["timeout_seconds"], 10)
        self.assertEqual(len(first_run["source_results"]), 2)
        self.assertEqual(first_run["skipped_old_item_count"], 0)
        self.assertEqual(len(fake_firestore.source_results), 2)
        self.assertEqual(second_run["new_item_count"], 0)
        self.assertEqual(second_run["updated_item_count"], 2)

    def test_ingest_accepts_timeout_and_worker_options(self):
        sources = [
            RssSource(source_id="ok", feed_url="https://example.com/ok", is_fetchable=True),
        ]
        fake_firestore = FakeFirestore(sources)

        with (
            patch.object(rss_ingest_service, "firestore_client", fake_firestore),
            patch.object(rss_ingest_service, "fetch_feed_xml", return_value=RSS_XML) as fetch_mock,
        ):
            run = rss_ingest_service.ingest_rss_sources(
                max_workers=3,
                timeout_seconds=7,
                since_hours=None,
            )

        fetch_mock.assert_called_once_with("https://example.com/ok", timeout_seconds=7)
        self.assertEqual(run["max_workers"], 3)
        self.assertEqual(run["timeout_seconds"], 7)
        self.assertEqual(run["source_results"][0]["item_count"], 2)

    def test_ingest_filters_old_items_by_published_at_window(self):
        sources = [
            RssSource(source_id="ok", feed_url="https://example.com/ok", is_fetchable=True),
        ]
        fake_firestore = FakeFirestore(sources)

        with (
            patch.object(rss_ingest_service, "firestore_client", fake_firestore),
            patch.object(rss_ingest_service, "fetch_feed_xml", return_value=RSS_XML),
            patch.object(
                rss_ingest_service,
                "utc_now_iso",
                return_value="2026-05-05T03:00:00Z",
            ),
        ):
            run = rss_ingest_service.ingest_rss_sources(since_hours=1)

        self.assertEqual(run["new_item_count"], 1)
        self.assertEqual(run["skipped_old_item_count"], 1)
        self.assertEqual(run["source_results"][0]["item_count"], 1)


if __name__ == "__main__":
    unittest.main()
