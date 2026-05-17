import unittest

from app.clients.firestore_client import FirestoreClient, MULTI_VECTOR_BATCH_WRITE_LIMIT
from app.models.signal import RssSignal


class FakeDoc:
    def __init__(self, doc_id):
        self.doc_id = doc_id


class FakeCollection:
    def document(self, doc_id):
        return FakeDoc(doc_id)


class FakeBatch:
    def __init__(self, db):
        self.db = db
        self.write_count = 0

    def update(self, doc, data):
        self.write_count += 1

    def set(self, doc, data):
        self.write_count += 1

    def commit(self):
        self.db.commits.append(self.write_count)


class FakeDb:
    def __init__(self):
        self.commits = []

    def collection(self, name):
        return FakeCollection()

    def batch(self):
        return FakeBatch(self)


def make_client(fake_db):
    client = object.__new__(FirestoreClient)
    client.db = fake_db
    return client


def make_signal(signal_id):
    return RssSignal(
        signal_id=signal_id,
        generated_at="2026-05-18T00:00:00Z",
        window_start="2026-05-18T00:00:00Z",
        window_end="2026-05-18T00:00:00Z",
        representative_title="title",
        event_centroid=[1.0, 0.0],
        entity_centroid=[1.0, 0.0],
        impact_centroid=[1.0, 0.0],
        context_centroid=[1.0, 0.0],
    )


class FirestoreClientBatchingTest(unittest.TestCase):
    def test_v2_item_vector_updates_commit_in_small_batches(self):
        fake_db = FakeDb()
        client = make_client(fake_db)
        updates = {
            f"item_{i}": {
                "event_embedding": [1.0, 0.0],
                "entity_embedding": [1.0, 0.0],
                "impact_embedding": [1.0, 0.0],
                "context_embedding": [1.0, 0.0],
            }
            for i in range(MULTI_VECTOR_BATCH_WRITE_LIMIT + 1)
        }

        written = client.update_rss_item_v2_fields(updates)

        self.assertEqual(written, MULTI_VECTOR_BATCH_WRITE_LIMIT + 1)
        self.assertEqual(fake_db.commits, [MULTI_VECTOR_BATCH_WRITE_LIMIT, 1])

    def test_signal_upserts_commit_in_small_batches(self):
        fake_db = FakeDb()
        client = make_client(fake_db)
        signals = [make_signal(f"sig_{i}") for i in range(MULTI_VECTOR_BATCH_WRITE_LIMIT + 1)]

        written = client.upsert_rss_signals(signals)

        self.assertEqual(written, MULTI_VECTOR_BATCH_WRITE_LIMIT + 1)
        self.assertEqual(fake_db.commits, [MULTI_VECTOR_BATCH_WRITE_LIMIT, 1])


if __name__ == "__main__":
    unittest.main()
