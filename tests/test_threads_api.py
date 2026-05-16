import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.signal import RssSignal, RssStoryThread, RssThreadPhase


class FakeFirestore:
    def __init__(self, threads=None, phases=None, signals=None):
        self.threads = {t.thread_id: t for t in (threads or [])}
        self.phases_by_thread: dict[str, list[RssThreadPhase]] = {}
        for p in phases or []:
            self.phases_by_thread.setdefault(p.thread_id, []).append(p)
        self.signals = {s.signal_id: s for s in (signals or [])}

    def list_recent_story_threads(self, since_iso, limit=200):
        return list(self.threads.values())

    def list_phases_for_threads(self, thread_ids):
        return {tid: list(self.phases_by_thread.get(tid, [])) for tid in thread_ids}

    def list_phases_for_thread(self, thread_id):
        return list(self.phases_by_thread.get(thread_id, []))

    def get_story_thread_by_id(self, thread_id):
        return self.threads.get(thread_id)

    def list_signals_by_ids(self, signal_ids):
        return [self.signals[sid] for sid in signal_ids if sid in self.signals]


def make_thread(thread_id="thread_a", **kw):
    return RssStoryThread(
        thread_id=thread_id,
        title=kw.get("title", "OpenAI Microsoft 關係"),
        status="active",
        active_since="2026-05-01T00:00:00Z",
        last_seen_at=kw.get("last_seen_at", "2026-05-14T00:00:00Z"),
        signal_ids=kw.get("signal_ids", ["sig_1"]),
        last_covered_in_podcast_at=kw.get("last_covered_in_podcast_at"),
    )


def make_phase(phase_id, thread_id="thread_a", **kw):
    return RssThreadPhase(
        phase_id=phase_id,
        thread_id=thread_id,
        title=kw.get("title", "算力配額爭議"),
        status=kw.get("status", "active"),
        parent_phase_id=kw.get("parent_phase_id"),
        signal_ids=kw.get("signal_ids", []),
        signal_count=len(kw.get("signal_ids", [])),
        novelty_reason=kw.get("novelty_reason", ""),
        llm_decision_log=kw.get("llm_decision_log", []),
        opened_at="2026-05-10T00:00:00Z",
        last_advanced_at=kw.get("last_advanced_at", "2026-05-14T00:00:00Z"),
    )


def make_signal(signal_id="sig_1", **kw):
    return RssSignal(
        signal_id=signal_id,
        generated_at="2026-05-14T00:00:00Z",
        window_start="2026-05-14T00:00:00Z",
        window_end="2026-05-14T00:00:00Z",
        representative_title=kw.get("representative_title", "OpenAI 算力爭議"),
        representative_url="https://example.com/x",
        representative_publisher="Reuters",
        representative_published_at="2026-05-14T00:00:00Z",
        importance_score=kw.get("importance_score", 75),
        is_background_repeat=kw.get("is_background_repeat", False),
        adjudication_decision=kw.get("adjudication_decision"),
        what_happened="OpenAI 要求更多算力",
    )


class TestThreadsAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_list_threads_returns_shape(self):
        thread = make_thread()
        phase = make_phase(
            "phase_1",
            signal_ids=["sig_1"],
            llm_decision_log=["[2026-05-14T00:00:00Z] different_thread: oops"],
        )
        fake = FakeFirestore(threads=[thread], phases=[phase])
        from app.api import routes_threads

        with patch.object(routes_threads, "firestore_client", fake):
            r = self.client.get("/api/threads")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        item = body[0]
        self.assertEqual(item["thread_id"], "thread_a")
        self.assertEqual(item["phase_count"], 1)
        self.assertGreaterEqual(item["mismatch_flag_count"], 1)
        self.assertIn("last_seen_at", item)

    def test_get_thread_returns_nested_phases_and_signals(self):
        thread = make_thread()
        phase = make_phase("phase_1", signal_ids=["sig_1"])
        signal = make_signal("sig_1", adjudication_decision="same_thread", is_background_repeat=False)
        fake = FakeFirestore(threads=[thread], phases=[phase], signals=[signal])
        from app.api import routes_threads

        with patch.object(routes_threads, "firestore_client", fake):
            r = self.client.get("/api/threads/thread_a")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["thread"]["thread_id"], "thread_a")
        self.assertEqual(len(body["phases"]), 1)
        self.assertEqual(len(body["phases"][0]["signals"]), 1)
        self.assertEqual(body["phases"][0]["signals"][0]["adjudication_decision"], "same_thread")

    def test_get_thread_404_when_missing(self):
        fake = FakeFirestore()
        from app.api import routes_threads

        with patch.object(routes_threads, "firestore_client", fake):
            r = self.client.get("/api/threads/nope")
        self.assertEqual(r.status_code, 404)


class TestViewerStaticServed(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_viewer_index_html_served(self):
        r = self.client.get("/viewer/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Story Thread Viewer", r.text)


if __name__ == "__main__":
    unittest.main()
