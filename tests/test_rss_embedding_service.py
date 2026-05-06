import unittest
from unittest.mock import patch

from app.models.rss import RssItem
from app.services import rss_embedding_service


def make_item(item_id: str, title: str, summary: str = "", embedded_at: str = "") -> RssItem:
    return RssItem(
        item_id=item_id,
        source_id="src",
        title=title,
        summary=summary,
        first_seen_at="2026-05-06T00:00:00Z",
        last_seen_at="2026-05-06T00:00:00Z",
        content_hash="hash",
        embedded_at=embedded_at or None,
    )


class FakeEmbeddingClient:
    def __init__(self, dim: int = 4):
        self.dim = dim
        self.calls = []
        self.is_ready = True

    def embed_batch(self, texts):
        self.calls.append(list(texts))
        vectors = [[float(len(t)), 0.1, 0.2, 0.3] for t in texts]
        return vectors, [], sum(len(t) for t in texts)


class FakeFirestoreClient:
    def __init__(self, pending_items):
        self.pending_items = pending_items
        self.embeddings_written = {}

    def list_rss_items_pending_embedding(self, since_iso, limit=1000):
        return list(self.pending_items)

    def update_rss_item_embeddings(self, embeddings):
        self.embeddings_written.update(embeddings)
        return len(embeddings)


class TestEmbeddingService(unittest.TestCase):
    def test_strip_html_and_truncate(self):
        item = make_item(
            "i1",
            "<b>Big news</b>",
            "<p>" + ("a" * 1000) + "</p>",
        )
        text = rss_embedding_service.build_text_for_embedding(item)
        self.assertNotIn("<b>", text)
        self.assertNotIn("</p>", text)
        self.assertLessEqual(len(text), rss_embedding_service.MAX_INPUT_CHARS)
        self.assertTrue(text.startswith("Big news"))

    def test_summary_limit_applied(self):
        long_summary = "x" * 2000
        item = make_item("i1", "Title", long_summary)
        text = rss_embedding_service.build_text_for_embedding(item)
        # title (5) + space (1) + summary clipped to SUMMARY_LIMIT (500)
        self.assertLessEqual(len(text), 5 + 1 + rss_embedding_service.SUMMARY_LIMIT)

    def test_embed_pending_items_writes_embeddings(self):
        items = [
            make_item("i1", "Hello world"),
            make_item("i2", "Another headline"),
        ]
        fake_fc = FakeFirestoreClient(items)
        fake_client = FakeEmbeddingClient()
        with patch.object(rss_embedding_service, "firestore_client", fake_fc):
            result = rss_embedding_service.embed_pending_items(
                window_hours=4,
                embedding_client=fake_client,
            )
        self.assertEqual(result["candidate_item_count"], 2)
        self.assertEqual(result["embedded_item_count"], 2)
        self.assertEqual(result["embedding_failed_item_count"], 0)
        self.assertEqual(set(fake_fc.embeddings_written.keys()), {"i1", "i2"})

    def test_no_candidates_short_circuit(self):
        fake_fc = FakeFirestoreClient([])
        with patch.object(rss_embedding_service, "firestore_client", fake_fc):
            result = rss_embedding_service.embed_pending_items(
                window_hours=4,
                embedding_client=FakeEmbeddingClient(),
            )
        self.assertEqual(result["candidate_item_count"], 0)
        self.assertEqual(result["embedded_item_count"], 0)


if __name__ == "__main__":
    unittest.main()
