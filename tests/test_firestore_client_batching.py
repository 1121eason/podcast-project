import unittest

from app.clients.firestore_client import FirestoreClient, MULTI_VECTOR_BATCH_WRITE_LIMIT
from app.models.signal import RssSignal


class FakeDoc:
    def __init__(self, doc_id, data=None):
        self.doc_id = doc_id
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class FakeQuery:
    def __init__(self, docs, field=None, value=None, order_field=None, limit_count=None):
        self.docs = docs
        self.field = field
        self.value = value
        self.order_field = order_field
        self.limit_count = limit_count

    def order_by(self, field, direction=None):
        return FakeQuery(self.docs, self.field, self.value, field, self.limit_count)

    def limit(self, count):
        return FakeQuery(self.docs, self.field, self.value, self.order_field, count)

    def stream(self):
        rows = list(self.docs)
        if self.field:
            rows = [row for row in rows if row.get(self.field) and row.get(self.field) >= self.value]
        if self.order_field:
            rows.sort(key=lambda row: row.get(self.order_field) or "", reverse=True)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return [FakeDoc(row["item_id"], row) for row in rows]


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def document(self, doc_id):
        return FakeDoc(doc_id)

    def where(self, filter):
        return FakeQuery(self.docs, filter.field_path, filter.value)


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
    def __init__(self, docs=None):
        self.commits = []
        self.docs = docs or []

    def collection(self, name):
        return FakeCollection(self.docs)

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


def make_item_doc(item_id, first_seen_at, processed=False, published_at=None):
    doc = {
        "item_id": item_id,
        "source_id": "src_1",
        "publisher": "Reuters",
        "title": f"title {item_id}",
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "published_at": published_at or first_seen_at,
        "content_hash": f"hash_{item_id}",
    }
    if processed:
        doc["v2_processed_at"] = first_seen_at
        doc["event_embedding_hash"] = f"event_hash_{item_id}"
    return doc


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

    def test_pending_v2_processing_scans_past_already_processed_window(self):
        docs = [
            make_item_doc(f"processed_{i}", f"2026-05-18T00:0{i}:00Z", processed=True)
            for i in range(5)
        ] + [
            make_item_doc(f"pending_{i}", f"2026-05-18T00:1{i}:00Z", processed=False)
            for i in range(3)
        ]
        fake_db = FakeDb(docs)
        client = make_client(fake_db)

        items = client.list_rss_items_pending_v2_processing("2026-05-18T00:00:00Z", limit=3)

        self.assertEqual([item.item_id for item in items], ["pending_2", "pending_1", "pending_0"])

    def test_pending_v2_processing_still_respects_requested_limit(self):
        docs = [
            make_item_doc(f"pending_{i}", f"2026-05-18T00:{i:02d}:00Z", processed=False)
            for i in range(10)
        ]
        fake_db = FakeDb(docs)
        client = make_client(fake_db)

        items = client.list_rss_items_pending_v2_processing("2026-05-18T00:00:00Z", limit=4)

        self.assertEqual(len(items), 4)
        self.assertEqual([item.item_id for item in items], ["pending_9", "pending_8", "pending_7", "pending_6"])


if __name__ == "__main__":
    unittest.main()
