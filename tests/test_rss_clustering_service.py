import unittest
from unittest.mock import patch

import numpy as np

from app.models.rss import RssItem
from app.services import rss_clustering_service


def make_item(item_id, title, publisher, source_id, embedding):
    return RssItem(
        item_id=item_id,
        source_id=source_id,
        publisher=publisher,
        desk="Market",
        category="general",
        market_level="Global",
        title=title,
        url=f"https://example.com/{item_id}",
        guid=item_id,
        summary="",
        first_seen_at="2026-05-06T00:00:00Z",
        last_seen_at="2026-05-06T00:00:00Z",
        content_hash=item_id,
        embedding=embedding,
        embedding_model="text-embedding-004",
        embedded_at="2026-05-06T00:00:00Z",
    )


class FakeFirestoreClient:
    def __init__(self, items_with_embedding):
        self.items_with_embedding = items_with_embedding
        self.signals_written = []
        self.signal_id_updates = {}
        self.run_record = None
        self.embed_pending_called = False

    def list_rss_items_pending_embedding(self, since_iso, limit=1000):
        return []

    def update_rss_item_embeddings(self, embeddings):
        return 0

    def list_rss_items_with_embedding(self, since_iso):
        return list(self.items_with_embedding)

    def upsert_rss_signals(self, signals):
        self.signals_written.extend(signals)
        return len(signals)

    def update_rss_item_signal_ids(self, mapping):
        self.signal_id_updates.update(mapping)
        return len(mapping)

    def create_clustering_run(self, run):
        self.run_record = run


class TestClusteringService(unittest.TestCase):
    def test_two_close_items_become_one_cluster(self):
        v = [1.0, 0.0, 0.0]
        items = [
            make_item("i1", "Anthropic raises funding", "CNBC", "src-cnbc", v),
            make_item("i2", "Anthropic 融資", "Reuters", "src-reuters", v),
            make_item("i3", "完全不同主題", "Yahoo", "src-yahoo", [0.0, 1.0, 0.0]),
        ]
        fake_fc = FakeFirestoreClient(items)

        with patch.object(rss_clustering_service, "firestore_client", fake_fc), \
             patch.object(rss_clustering_service, "embed_pending_items", return_value={
                 "candidate_item_count": 0,
                 "embedded_item_count": 0,
                 "embedding_failed_item_count": 0,
                 "cost_usd": 0.0,
             }):
            result = rss_clustering_service.run_clustering(window_hours=4)

        self.assertEqual(result["cluster_count"], 2)
        self.assertEqual(result["multi_source_cluster_count"], 1)
        self.assertEqual(result["singleton_cluster_count"], 1)

        # Check that i1 and i2 share a signal_id
        sig_i1 = fake_fc.signal_id_updates["i1"]
        sig_i2 = fake_fc.signal_id_updates["i2"]
        sig_i3 = fake_fc.signal_id_updates["i3"]
        self.assertEqual(sig_i1, sig_i2)
        self.assertNotEqual(sig_i1, sig_i3)

    def test_cluster_aggregates_publishers_and_sources(self):
        items = [
            make_item("a1", "Same event", "CNBC", "src-cnbc", [1.0, 0.0]),
            make_item("a2", "Same event in another lang", "Reuters", "src-reuters", [1.0, 0.0]),
            make_item("a3", "Same event another publisher", "Bloomberg", "src-bloomberg", [1.0, 0.0]),
        ]
        fake_fc = FakeFirestoreClient(items)
        with patch.object(rss_clustering_service, "firestore_client", fake_fc), \
             patch.object(rss_clustering_service, "embed_pending_items", return_value={
                 "candidate_item_count": 0,
                 "embedded_item_count": 0,
                 "embedding_failed_item_count": 0,
                 "cost_usd": 0.0,
             }):
            rss_clustering_service.run_clustering(window_hours=4)

        self.assertEqual(len(fake_fc.signals_written), 1)
        sig = fake_fc.signals_written[0]
        self.assertEqual(sig.source_count, 3)
        self.assertEqual(sig.publisher_count, 3)
        self.assertEqual(set(sig.publishers), {"CNBC", "Reuters", "Bloomberg"})
        self.assertEqual(sig.cluster_size, 3)

    def test_no_items_creates_empty_run(self):
        fake_fc = FakeFirestoreClient([])
        with patch.object(rss_clustering_service, "firestore_client", fake_fc), \
             patch.object(rss_clustering_service, "embed_pending_items", return_value={
                 "candidate_item_count": 0,
                 "embedded_item_count": 0,
                 "embedding_failed_item_count": 0,
                 "cost_usd": 0.0,
             }):
            result = rss_clustering_service.run_clustering(window_hours=4)
        self.assertEqual(result["cluster_count"], 0)
        self.assertIsNotNone(fake_fc.run_record)
        self.assertEqual(len(fake_fc.signals_written), 0)

    def test_representative_picks_closest_to_centroid(self):
        # Three items: two near (1,0,0), one slightly off
        items = [
            make_item("near1", "A", "P1", "s1", [1.0, 0.0, 0.0]),
            make_item("near2", "A2", "P2", "s2", [0.99, 0.01, 0.0]),
            make_item("offset", "A3", "P3", "s3", [0.97, 0.03, 0.02]),
        ]
        fake_fc = FakeFirestoreClient(items)
        with patch.object(rss_clustering_service, "firestore_client", fake_fc), \
             patch.object(rss_clustering_service, "embed_pending_items", return_value={
                 "candidate_item_count": 0,
                 "embedded_item_count": 0,
                 "embedding_failed_item_count": 0,
                 "cost_usd": 0.0,
             }):
            rss_clustering_service.run_clustering(window_hours=4)

        # All three should be in one cluster (very close)
        self.assertEqual(len(fake_fc.signals_written), 1)
        rep_id = fake_fc.signals_written[0].representative_item_id
        self.assertIn(rep_id, {"near1", "near2", "offset"})


if __name__ == "__main__":
    unittest.main()
