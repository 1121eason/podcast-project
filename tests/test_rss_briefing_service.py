import unittest
from unittest.mock import patch
from datetime import datetime, timezone

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
    def __init__(self, signals, threads=None, phases=None):
        self.signals = signals
        self.threads = {t.thread_id: t for t in (threads or [])}
        self._phases = phases or []
        self.briefing_written = None
        self.recent_briefings = []

    def list_signals_for_briefing(self, since_iso, min_score=70, limit=80):
        return [s for s in self.signals if (s.importance_score or 0) >= min_score][:limit]

    def list_recent_briefings(self, limit=2):
        return list(self.recent_briefings)[:limit]

    def upsert_briefing(self, briefing):
        self.briefing_written = briefing

    def list_story_threads_by_ids(self, thread_ids):
        return [self.threads[tid] for tid in thread_ids if tid in self.threads]

    def list_phases_for_threads(self, thread_ids):
        result = {tid: [] for tid in thread_ids}
        for p in self._phases:
            if p.thread_id in result:
                result[p.thread_id].append(p)
        return result


class FakeGeminiClient:
    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, prompt, model="gemini-2.5-pro"):
        return self.payload, 1500, 400


class TestBriefingFlow(unittest.TestCase):
    def test_default_briefing_date_uses_configured_timezone(self):
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                fixed = datetime(2026, 5, 7, 22, 0, 0, tzinfo=timezone.utc)
                return fixed.astimezone(tz) if tz else fixed

        with patch.object(rss_briefing_service, "datetime", FixedDateTime), \
             patch.object(rss_briefing_service.settings, "BRIEFING_TIMEZONE", "Australia/Brisbane"):
            self.assertEqual(rss_briefing_service._today_date_str(), "2026-05-08")

    def test_explicit_briefing_date_is_preserved(self):
        self.assertEqual(rss_briefing_service._today_date_str("2026-05-07"), "2026-05-07")

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
            "top_changes": [
                {
                    "rank": 1,
                    "title": "美伊衝突緩和",
                    "summary": "200 字摘要...",
                    "category_id": "geopolitics",
                    "importance_score": 90,
                    "is_continuation": False,
                    "referenced_signal_ids": ["s1"],
                    "referenced_urls": ["https://example.com/1"],
                }
            ],
            "aggregated_watch_points": ["伊朗 48 小時內回應"],
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
             patch.object(rss_briefing_service, "gemini_client", fake_g), \
             patch.object(rss_briefing_service.openai_client, "client", None):
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
             patch.object(rss_briefing_service, "gemini_client", fake_g), \
             patch.object(rss_briefing_service.openai_client, "client", None):
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


class TestThreadContextInjection(unittest.TestCase):
    """W8 must surface W7 thread + phase context to the LLM, not flatten it."""

    def _make_threaded_signal(self, sid, score, thread_id, **kw):
        from app.models.signal import RssSignal

        return RssSignal(
            signal_id=sid,
            generated_at="2026-05-15T00:00:00Z",
            window_start="2026-05-14T20:00:00Z",
            window_end="2026-05-15T00:00:00Z",
            cluster_size=2,
            source_count=2,
            publisher_count=2,
            publishers=["Reuters"],
            representative_title=kw.get("title", "OpenAI Microsoft 算力爭議"),
            representative_url=kw.get("url", "https://example.com/x"),
            representative_publisher="Reuters",
            cluster_status="confirmed",
            topic_heat="high",
            importance_score=score,
            thread_id=thread_id,
            phase_id=kw.get("phase_id"),
            today_delta=kw.get("today_delta", "今日新發展"),
            is_background_repeat=kw.get("is_background_repeat", False),
            adjudication_decision=kw.get("adjudication_decision"),
        )

    def test_thread_context_injected_into_prompt(self):
        from app.models.signal import RssStoryThread, RssThreadPhase

        signal = self._make_threaded_signal("s1", 85, "thread_a")
        thread = RssStoryThread(
            thread_id="thread_a",
            title="OpenAI Microsoft 關係緊張",
            status="active",
            active_since="2026-05-01T00:00:00Z",
            last_seen_at="2026-05-15T00:00:00Z",
            known_background="OpenAI 與 Microsoft 在 Q3 算力配額談判持續緊張。",
            do_not_repeat_points=["GPU 短缺背景已詳述", "Sam Altman 公開信內容"],
            continuation_prompt_hint="延續 OpenAI–MS 緊張，今日談判出現新進展。",
            today_delta="算力配額談判破局",
        )
        phase = RssThreadPhase(
            phase_id="phase_compute",
            thread_id="thread_a",
            title="算力配額爭議",
            status="active",
            signal_count=4,
            opened_at="2026-05-10T00:00:00Z",
            last_advanced_at="2026-05-15T00:00:00Z",
        )
        fake_fc = FakeFirestoreClient([signal], threads=[thread], phases=[phase])
        with patch.object(rss_briefing_service, "firestore_client", fake_fc):
            prompt = rss_briefing_service._render_prompt(
                [signal], total_judged=1, briefing_date="2026-05-15"
            )

        # Thread context must appear
        self.assertIn("OpenAI Microsoft 關係緊張", prompt)
        self.assertIn("OpenAI 與 Microsoft 在 Q3 算力配額談判持續緊張", prompt)
        self.assertIn("GPU 短缺背景已詳述", prompt)
        self.assertIn("Sam Altman 公開信內容", prompt)
        self.assertIn("延續 OpenAI–MS 緊張", prompt)
        # Phase context must appear
        self.assertIn("算力配額爭議", prompt)
        self.assertIn("phase_compute", prompt)
        # Counts in instruction line
        self.assertIn("共 1 條 thread", prompt)

    def test_background_repeat_signal_count_surfaced(self):
        from app.models.signal import RssStoryThread

        s_new = self._make_threaded_signal("s_new", 80, "thread_a", is_background_repeat=False)
        s_repeat = self._make_threaded_signal("s_rep", 70, "thread_a", is_background_repeat=True)
        thread = RssStoryThread(
            thread_id="thread_a",
            title="X",
            active_since="2026-05-01T00:00:00Z",
            last_seen_at="2026-05-15T00:00:00Z",
        )
        fake_fc = FakeFirestoreClient([s_new, s_repeat], threads=[thread])
        with patch.object(rss_briefing_service, "firestore_client", fake_fc):
            prompt = rss_briefing_service._render_prompt(
                [s_new, s_repeat], total_judged=2, briefing_date="2026-05-15"
            )
        # Header summary calls out background_repeat count (only s_rep flagged).
        self.assertIn("background_repeat 的訊號共 1 則", prompt)
        # Both signals appear in JSON with the flag set correctly
        self.assertIn('"is_background_repeat": true', prompt)
        self.assertIn('"is_background_repeat": false', prompt)

    def test_orphan_signal_without_thread_goes_to_ungrouped(self):
        signal_no_thread = self._make_threaded_signal("s_orphan", 75, None)
        fake_fc = FakeFirestoreClient([signal_no_thread])
        with patch.object(rss_briefing_service, "firestore_client", fake_fc):
            prompt = rss_briefing_service._render_prompt(
                [signal_no_thread], total_judged=1, briefing_date="2026-05-15"
            )
        self.assertIn("共 0 條 thread", prompt)
        self.assertIn("ungrouped signals 共 1 則", prompt)
        self.assertIn("s_orphan", prompt)


class TestPhaseFlagDerivation(unittest.TestCase):
    """W7 writes thread_mismatch / duplicate_suspected into adjudication_rationale text;
    W8 must surface these as explicit booleans so the prompt rules can fire."""

    def _signal(self, sid, rationale=None):
        from app.models.signal import RssSignal

        return RssSignal(
            signal_id=sid,
            generated_at="2026-05-15T00:00:00Z",
            window_start="2026-05-14T20:00:00Z",
            window_end="2026-05-15T00:00:00Z",
            cluster_size=1,
            source_count=1,
            publisher_count=1,
            publishers=["Reuters"],
            representative_title="Test",
            representative_url="https://example.com/x",
            representative_publisher="Reuters",
            importance_score=70,
            thread_id="thread_a",
            adjudication_rationale=rationale,
        )

    def test_thread_mismatch_rationale_becomes_boolean(self):
        sig = self._signal("s_mismatch", rationale="thread_mismatch_suspected: 看起來是別的故事")
        compact = rss_briefing_service._signal_to_compact(sig)
        self.assertTrue(compact["thread_mismatch_suspected"])
        self.assertFalse(compact["duplicate_suspected"])

    def test_duplicate_rationale_becomes_boolean(self):
        sig = self._signal("s_dup", rationale="duplicate_suspected:sigv2_xxx :: 看起來重複")
        compact = rss_briefing_service._signal_to_compact(sig)
        self.assertTrue(compact["duplicate_suspected"])
        self.assertFalse(compact["thread_mismatch_suspected"])

    def test_w4_only_rationale_does_not_set_phase_flags(self):
        # W4-style rationale (free-form, no W7 prefix) should set neither boolean.
        sig = self._signal("s_w4", rationale="Same actor and impact")
        compact = rss_briefing_service._signal_to_compact(sig)
        self.assertFalse(compact["thread_mismatch_suspected"])
        self.assertFalse(compact["duplicate_suspected"])

    def test_phase_flags_visible_in_full_prompt(self):
        sig = self._signal("s_mismatch", rationale="thread_mismatch_suspected: oops")
        fake_fc = FakeFirestoreClient([sig])
        with patch.object(rss_briefing_service, "firestore_client", fake_fc):
            prompt = rss_briefing_service._render_prompt(
                [sig], total_judged=1, briefing_date="2026-05-15"
            )
        self.assertIn('"thread_mismatch_suspected": true', prompt)
        # And the prompt's rule text uses the new field name (not the old wrong one).
        self.assertIn("thread_mismatch_suspected == true", prompt)
        self.assertIn("duplicate_suspected == true", prompt)


class TestRetryCountObservability(unittest.TestCase):
    """retry_count must reach result + signal_pool_health for production telemetry."""

    def _valid_payload(self):
        return {
            "overview": "ok",
            "categories": [
                {
                    "category_id": "tech",
                    "title": "科技發展",
                    "category_overview": "x",
                    "sections": [
                        {
                            "title": "T",
                            "summary": "S",
                            "importance_score": 85,
                            "impact_type": "tech",
                            "referenced_signal_ids": ["s1"],
                            "referenced_urls": ["https://example.com/1"],
                        }
                    ],
                }
            ],
            "signal_pool_health": {"main_themes": ["x"]},
        }

    def test_retry_count_zero_on_first_call_success(self):
        signals = [make_signal("s1", 85, "Test", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)
        fake_g = FakeGeminiClient(self._valid_payload())
        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", fake_g), \
             patch.object(rss_briefing_service.openai_client, "client", None):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-15", write_google_doc=False
            )
        self.assertEqual(result["briefing_retry_count"], 0)
        self.assertEqual(result["signal_pool_health"]["briefing_retry_count"], 0)
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(any("W8 Briefing" in line for line in result["log_summary"]))

    def test_retry_count_one_when_first_call_fails(self):
        signals = [make_signal("s1", 85, "Test", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)

        good = self._valid_payload()

        class FlakyGemini:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt, model="gemini-2.5-pro"):
                self.calls += 1
                if self.calls == 1:
                    return {"categories": []}, 100, 50  # missing overview
                return good, 1500, 400

        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", FlakyGemini()), \
             patch.object(rss_briefing_service.openai_client, "client", None):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-15", write_google_doc=False
            )
        self.assertEqual(result["briefing_retry_count"], 1)
        self.assertEqual(result["signal_pool_health"]["briefing_retry_count"], 1)


class TestRetryOnValidationFailure(unittest.TestCase):
    """First LLM call returns invalid JSON → retry once before giving up."""

    def test_retry_succeeds_after_first_invalid_payload(self):
        signals = [make_signal("s1", 85, "Test", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)

        valid_payload = {
            "overview": "test overview",
            "categories": [
                {
                    "category_id": "tech",
                    "title": "科技發展",
                    "category_overview": "x",
                    "sections": [
                        {
                            "title": "T",
                            "summary": "S",
                            "importance_score": 85,
                            "impact_type": "tech",
                            "referenced_signal_ids": ["s1"],
                            "referenced_urls": ["https://example.com/1"],
                        }
                    ],
                }
            ],
            "signal_pool_health": {},
        }

        class FlakyGemini:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt, model="gemini-2.5-pro"):
                self.calls += 1
                if self.calls == 1:
                    # First call: missing overview → triggers ValueError in validation
                    return {"categories": []}, 100, 50
                return valid_payload, 1500, 400

        flaky = FlakyGemini()
        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", flaky), \
             patch.object(rss_briefing_service.openai_client, "client", None):
            result = rss_briefing_service.generate_daily_briefing(
                briefing_date="2026-05-15", write_google_doc=False
            )
        self.assertEqual(flaky.calls, 2)
        self.assertEqual(result["overview"], "test overview")

    def test_two_failures_raises(self):
        signals = [make_signal("s1", 85, "Test", "https://example.com/1")]
        fake_fc = FakeFirestoreClient(signals)

        class AlwaysBadGemini:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt, model="gemini-2.5-pro"):
                self.calls += 1
                return {"categories": []}, 100, 50  # missing overview, always fails

        bad = AlwaysBadGemini()
        with patch.object(rss_briefing_service, "firestore_client", fake_fc), \
             patch.object(rss_briefing_service, "gemini_client", bad), \
             patch.object(rss_briefing_service.openai_client, "client", None):
            with self.assertRaises(ValueError) as ctx:
                rss_briefing_service.generate_daily_briefing(
                    briefing_date="2026-05-15", write_google_doc=False
                )
        self.assertEqual(bad.calls, 2)
        self.assertIn("after retry", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
