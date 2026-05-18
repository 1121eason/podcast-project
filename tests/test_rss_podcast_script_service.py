import unittest
from unittest.mock import patch

from app.models.podcast import RssPodcastScript, ScriptSegment
from app.models.signal import (
    BriefingCategory,
    BriefingSection,
    BriefingTopChange,
    RssBriefing,
    RssSignal,
    RssStoryThread,
    RssThreadPhase,
)
from app.services import rss_podcast_script_service


def make_briefing() -> RssBriefing:
    section = BriefingSection(
        section_id="sec_01",
        title="AI 供應鏈重新定價",
        summary="summary",
        referenced_signal_ids=["sig_1"],
        referenced_urls=["https://example.com/a"],
    )
    return RssBriefing(
        briefing_id="brief_1",
        briefing_date="2026-05-09",
        generated_at="2026-05-09T00:00:00Z",
        score_threshold=60,
        overview="overview",
        top_changes=[
            BriefingTopChange(
                rank=1,
                title="全球資金重新定價 AI",
                summary="summary",
                referenced_signal_ids=["sig_2"],
                referenced_urls=["https://example.com/b"],
            )
        ],
        categories=[
            BriefingCategory(
                category_id="tech",
                title="科技發展",
                sections=[section],
            )
        ],
    )


class PodcastScriptServiceTest(unittest.TestCase):
    def test_format_episode_title_uses_date_prefix_and_strips_existing_date(self):
        title = rss_podcast_script_service.format_episode_title(
            "2026-05-09",
            "2026/05/09-全球資金重新定價 AI 與供應鏈風險",
        )

        self.assertEqual(title, "2026/05/09-全球資金重新定價 AI 與供應鏈風險")

    def test_validate_script_payload_normalizes_script_and_filters_refs(self):
        payload = {
            "script": "今天先看三件事。",
            "episode_title": "AI 供應鏈風險升溫",
            "duration_estimate_minutes": 20,
            "segments": [
                {
                    "segment_id": "seg_01",
                    "position": 1,
                    "segment_type": "top_changes",
                    "title": "今日重點",
                    "text": "content",
                    "referenced_signal_ids": ["sig_1", "missing"],
                }
            ],
            "themes_covered": ["tech_ai"],
            "themes_skipped": [{"theme": "other_signal", "reason": "empty"}],
            "show_notes": "來源：https://example.com/a",
        }

        result = rss_podcast_script_service._validate_script_payload(payload, make_briefing())

        self.assertTrue(result["script"].startswith("歡迎回到 Informative AI。"))
        self.assertTrue(result["script"].endswith("感謝各位今天的收聽，明天見。"))
        self.assertEqual(result["episode_title"], "2026/05/09-AI 供應鏈風險升溫")
        self.assertEqual(result["segments"][0]["referenced_signal_ids"], ["sig_1"])
        self.assertEqual(result["word_count"], rss_podcast_script_service._spoken_char_count(result["script"]))
        self.assertIn("mandatory opening prepended", result["validation_warnings"])
        self.assertIn("mandatory closing appended", result["validation_warnings"])

    def test_validate_script_payload_uses_title_fallback(self):
        payload = {
            "script": "歡迎回到 Informative AI。內容。感謝各位今天的收聽，明天見。",
            "segments": [],
            "show_notes": "",
        }

        result = rss_podcast_script_service._validate_script_payload(payload, make_briefing())

        self.assertEqual(result["episode_title"], "2026/05/09-全球資金重新定價 AI")
        self.assertIn("episode_title fallback used", result["validation_warnings"])


class FakeFirestore:
    def __init__(self, signals=None, threads=None, phases=None, podcast_scripts=None, briefings=None):
        self.signals = {s.signal_id: s for s in (signals or [])}
        self.threads = {t.thread_id: t for t in (threads or [])}
        self._phases = phases or []
        self.podcast_scripts = list(podcast_scripts or [])
        self.briefings = list(briefings or [])
        self.written_scripts = []

    def list_signals_by_ids(self, ids):
        return [self.signals[i] for i in ids if i in self.signals]

    def list_story_threads_by_ids(self, ids):
        return [self.threads[i] for i in ids if i in self.threads]

    def list_phases_for_threads(self, ids):
        out = {i: [] for i in ids}
        for p in self._phases:
            if p.thread_id in out:
                out[p.thread_id].append(p)
        return out

    def list_recent_podcast_scripts(self, limit=5):
        # Mirror Firestore: order by generated_at desc.
        sorted_by_gen = sorted(
            self.podcast_scripts, key=lambda p: p.generated_at or "", reverse=True
        )
        return sorted_by_gen[:limit]

    def get_latest_podcast_script_before(self, briefing_date):
        # Mirror Firestore helper: filter by briefing_date < given, order by date desc.
        candidates = [p for p in self.podcast_scripts if (p.briefing_date or "") < briefing_date]
        if not candidates:
            return None
        candidates.sort(
            key=lambda p: (p.briefing_date or "", p.generated_at or ""), reverse=True
        )
        return candidates[0]

    def list_recent_briefings(self, limit=10):
        return list(self.briefings)[:limit]

    def upsert_podcast_script(self, podcast):
        self.written_scripts.append(podcast)


def make_threaded_briefing(signal_id="sig_1", thread_id="thread_a") -> RssBriefing:
    """Briefing whose top_changes/sections reference a signal that has a thread."""
    section = BriefingSection(
        section_id="sec_01",
        title="OpenAI Microsoft 算力爭議",
        summary="今日新進展",
        is_continuation=True,
        continuation_note="昨日已詳述背景",
        referenced_signal_ids=[signal_id],
        referenced_urls=["https://example.com/x"],
    )
    return RssBriefing(
        briefing_id="brief_thread",
        briefing_date="2026-05-15",
        generated_at="2026-05-15T00:00:00Z",
        score_threshold=60,
        overview="overview",
        top_changes=[
            BriefingTopChange(
                rank=1,
                title="OpenAI MS 緊張",
                summary="summary",
                referenced_signal_ids=[signal_id],
                referenced_urls=["https://example.com/x"],
            )
        ],
        categories=[
            BriefingCategory(category_id="tech", title="科技發展", sections=[section])
        ],
    )


def make_signal_in_thread(sid, thread_id, **kw):
    return RssSignal(
        signal_id=sid,
        generated_at="2026-05-15T00:00:00Z",
        window_start="2026-05-14T20:00:00Z",
        window_end="2026-05-15T00:00:00Z",
        publishers=["Reuters"],
        representative_title=kw.get("title", "OpenAI Microsoft 算力爭議"),
        representative_url="https://example.com/x",
        representative_publisher="Reuters",
        importance_score=kw.get("importance", 80),
        thread_id=thread_id,
        what_happened=kw.get("what_happened", "OpenAI 要求更多算力"),
        is_background_repeat=kw.get("is_background_repeat", False),
        adjudication_rationale=kw.get("adjudication_rationale"),
    )


def make_thread(thread_id="thread_a", **kw):
    return RssStoryThread(
        thread_id=thread_id,
        title=kw.get("title", "OpenAI Microsoft 關係緊張"),
        status="active",
        active_since="2026-05-01T00:00:00Z",
        last_seen_at="2026-05-15T00:00:00Z",
        known_background=kw.get("known_background", "OpenAI 與 Microsoft 在 Q3 算力配額談判持續緊張"),
        do_not_repeat_points=kw.get("do_not_repeat_points", ["GPU 短缺背景已詳述"]),
        continuation_prompt_hint="延續 OpenAI–MS 緊張，今日有新進展",
        today_delta="算力配額談判破局",
    )


def make_phase(pid, thread_id, **kw):
    return RssThreadPhase(
        phase_id=pid,
        thread_id=thread_id,
        title=kw.get("title", "算力配額爭議"),
        status=kw.get("status", "active"),
        signal_count=kw.get("signal_count", 4),
        opened_at="2026-05-10T00:00:00Z",
        last_advanced_at="2026-05-15T00:00:00Z",
    )


def make_yesterday_podcast() -> RssPodcastScript:
    return RssPodcastScript(
        script_id="podcast_yesterday",
        briefing_id="brief_yesterday",
        briefing_date="2026-05-14",
        generated_at="2026-05-14T07:30:00Z",
        episode_title="2026/05/14-OpenAI MS 緊張白熱化",
        script="歡迎回到 Informative AI。內容。感謝各位今天的收聽，明天見。",
        themes_covered=["geopolitics", "tech_ai"],
        themes_skipped=["semi_supply_chain"],
        segments=[
            ScriptSegment(
                segment_id="seg_01",
                position=1,
                segment_type="theme",
                title="OpenAI MS 算力爭議",
                text="昨天詳細講了 OpenAI 跟 Microsoft 為了 Q3 算力配額僵持的背景，特別是 GPU 短缺的脈絡。",
                theme="tech_ai",
            ),
        ],
    )


class TestThreadAndPhaseInjection(unittest.TestCase):
    def test_thread_groups_built_from_briefing_referenced_signals(self):
        briefing = make_threaded_briefing()
        signal = make_signal_in_thread("sig_1", "thread_a")
        thread = make_thread()
        phase = make_phase("phase_compute", "thread_a")
        fake = FakeFirestore(signals=[signal], threads=[thread], phases=[phase])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            prompt = rss_podcast_script_service._render_prompt(briefing)
        # Thread context surfaced
        self.assertIn("OpenAI Microsoft 關係緊張", prompt)
        self.assertIn("OpenAI 與 Microsoft 在 Q3 算力配額談判持續緊張", prompt)
        self.assertIn("GPU 短缺背景已詳述", prompt)
        # Phase tree surfaced
        self.assertIn("算力配額爭議", prompt)
        self.assertIn("phase_compute", prompt)
        # Header counts
        self.assertIn("共 1 條 thread", prompt)

    def test_phase_flags_visible_in_prompt(self):
        briefing = make_threaded_briefing()
        signal = make_signal_in_thread(
            "sig_1",
            "thread_a",
            adjudication_rationale="thread_mismatch_suspected: oops",
        )
        thread = make_thread()
        fake = FakeFirestore(signals=[signal], threads=[thread])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            prompt = rss_podcast_script_service._render_prompt(briefing)
        self.assertIn('"thread_mismatch_suspected": true', prompt)
        # Rule text references the boolean field name
        self.assertIn("thread_mismatch_suspected == true", prompt)

    def test_background_repeat_count_in_header(self):
        briefing = make_threaded_briefing()
        sig_new = make_signal_in_thread("sig_1", "thread_a", is_background_repeat=False)
        sig_repeat = make_signal_in_thread("sig_2", "thread_a", is_background_repeat=True)
        # Add sig_2 to briefing referenced ids
        briefing.top_changes[0].referenced_signal_ids = ["sig_1", "sig_2"]
        thread = make_thread()
        fake = FakeFirestore(signals=[sig_new, sig_repeat], threads=[thread])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            prompt = rss_podcast_script_service._render_prompt(briefing)
        self.assertIn("background_repeat — **不要單獨開 sub-topic**", prompt)
        self.assertIn("1 則 signal 標記為 background_repeat", prompt)


class TestPreviousPodcastSummary(unittest.TestCase):
    def test_previous_podcast_summary_loaded_when_present(self):
        yesterday = make_yesterday_podcast()
        fake = FakeFirestore(podcast_scripts=[yesterday])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            summary = rss_podcast_script_service._previous_podcast_summary("2026-05-15")
        self.assertIn("2026/05/14-OpenAI MS 緊張白熱化", summary)
        self.assertIn("themes_covered: geopolitics, tech_ai", summary)
        self.assertIn("OpenAI MS 算力爭議", summary)
        self.assertIn("昨天詳細講了 OpenAI 跟 Microsoft", summary)
        self.assertIn("上一集日期: 2026-05-14", summary)

    def test_same_date_skipped(self):
        # Same date as today → should NOT be treated as previous episode.
        same_day = make_yesterday_podcast()
        same_day.briefing_date = "2026-05-15"
        fake = FakeFirestore(podcast_scripts=[same_day])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            summary = rss_podcast_script_service._previous_podcast_summary("2026-05-15")
        self.assertIn("無前一集 podcast 紀錄", summary)

    def test_previous_podcast_in_full_prompt(self):
        briefing = make_threaded_briefing()
        yesterday = make_yesterday_podcast()
        fake = FakeFirestore(podcast_scripts=[yesterday])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            prompt = rss_podcast_script_service._render_prompt(briefing)
        # Block label and content visible
        self.assertIn("【上一集 podcast 摘要】", prompt)
        self.assertIn("OpenAI MS 算力爭議", prompt)

    def test_same_day_reruns_dont_push_yesterday_out(self):
        """P2 regression: 5 same-day reruns of today must NOT hide yesterday from the
        prior-episode lookup. Previously list_recent_podcast_scripts(limit=5) ordered
        by generated_at desc → 5 same-day docs filled the window, yesterday vanished."""
        from app.models.podcast import RssPodcastScript

        yesterday = make_yesterday_podcast()  # 2026-05-14
        same_day_reruns = [
            RssPodcastScript(
                script_id=f"podcast_today_v{i}",
                briefing_id="brief_today",
                briefing_date="2026-05-15",
                generated_at=f"2026-05-15T{10 + i:02d}:00:00Z",
                episode_title=f"Today rerun {i}",
                script="...",
                segments=[],
            )
            for i in range(6)
        ]
        fake = FakeFirestore(podcast_scripts=same_day_reruns + [yesterday])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            summary = rss_podcast_script_service._previous_podcast_summary("2026-05-15")
        # Must find yesterday despite the 6 same-day reruns ahead of it by generated_at.
        self.assertIn("2026/05/14-OpenAI MS 緊張白熱化", summary)
        self.assertIn("上一集日期: 2026-05-14", summary)

    def test_picks_latest_rerun_of_prior_date(self):
        """If yesterday had multiple reruns, pick the latest by generated_at."""
        from app.models.podcast import RssPodcastScript

        early = RssPodcastScript(
            script_id="y_early",
            briefing_id="b_y",
            briefing_date="2026-05-14",
            generated_at="2026-05-14T07:00:00Z",
            episode_title="Yesterday early version",
            script="early",
            segments=[],
        )
        late = RssPodcastScript(
            script_id="y_late",
            briefing_id="b_y",
            briefing_date="2026-05-14",
            generated_at="2026-05-14T09:00:00Z",
            episode_title="Yesterday final version",
            script="final",
            segments=[],
        )
        fake = FakeFirestore(podcast_scripts=[early, late])
        with patch.object(rss_podcast_script_service, "firestore_client", fake):
            summary = rss_podcast_script_service._previous_podcast_summary("2026-05-15")
        self.assertIn("Yesterday final version", summary)
        self.assertNotIn("Yesterday early version", summary)


class TestRetryOnValidationFailure(unittest.TestCase):
    def _valid_payload(self):
        return {
            "script": "歡迎回到 Informative AI。" + ("內容。" * 200) + "感謝各位今天的收聽，明天見。",
            "episode_title": "AI 供應鏈",
            "duration_estimate_minutes": 20,
            "segments": [
                {
                    "segment_id": "seg_01",
                    "position": 1,
                    "segment_type": "top_changes",
                    "title": "今日重點",
                    "text": "ok",
                    "referenced_signal_ids": ["sig_1"],
                }
            ],
            "themes_covered": ["tech_ai"],
            "themes_skipped": [],
            "show_notes": "x",
        }

    def test_retry_succeeds_after_first_invalid_payload(self):
        briefing = make_threaded_briefing()
        signal = make_signal_in_thread("sig_1", "thread_a")
        good = self._valid_payload()

        class FlakyGemini:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt, model="gemini-2.5-pro"):
                self.calls += 1
                if self.calls == 1:
                    return {"segments": []}, 100, 50  # missing script → ValueError
                return good, 1500, 400

        flaky = FlakyGemini()
        fake = FakeFirestore(signals=[signal])
        with patch.object(rss_podcast_script_service, "firestore_client", fake), \
             patch.object(rss_podcast_script_service, "gemini_client", flaky), \
             patch.object(rss_podcast_script_service.openai_client, "client", None):
            validated, _, _, _, _, retry_count = (
                rss_podcast_script_service._generate_script_with_retry(briefing)
            )
        self.assertEqual(flaky.calls, 2)
        self.assertEqual(retry_count, 1)
        self.assertTrue(validated["script"].startswith("歡迎回到 Informative AI"))

    def test_generate_script_returns_log_summary(self):
        briefing = make_threaded_briefing()
        good = self._valid_payload()

        class GoodGemini:
            def generate_json(self, prompt, model="gemini-2.5-pro"):
                return good, 1500, 400

        fake = FakeFirestore(briefings=[briefing])
        with patch.object(rss_podcast_script_service, "firestore_client", fake), \
             patch.object(rss_podcast_script_service, "gemini_client", GoodGemini()), \
             patch.object(rss_podcast_script_service.openai_client, "client", None):
            result = rss_podcast_script_service.generate_daily_podcast_script(
                write_google_doc=False
            )
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(any("W9 Script" in line for line in result["log_summary"]))
        self.assertEqual(len(fake.written_scripts), 1)

    def test_google_doc_write_error_is_visible(self):
        briefing = make_threaded_briefing()
        good = self._valid_payload()

        class GoodGemini:
            def generate_json(self, prompt, model="gemini-2.5-pro"):
                return good, 1500, 400

        fake = FakeFirestore(briefings=[briefing])
        with patch.object(rss_podcast_script_service, "firestore_client", fake), \
             patch.object(rss_podcast_script_service, "gemini_client", GoodGemini()), \
             patch.object(rss_podcast_script_service.openai_client, "client", None), \
             patch(
                 "app.services.podcast_doc_writer.write_podcast_script_to_doc",
                 return_value=(None, None, "Docs API service not initialized"),
             ):
            result = rss_podcast_script_service.generate_daily_podcast_script(
                write_google_doc=True
            )

        self.assertEqual(result["google_doc_error"], "Docs API service not initialized")
        self.assertIsNone(result["google_doc_url"])
        self.assertEqual(fake.written_scripts[0].google_doc_error, "Docs API service not initialized")
        self.assertTrue(any("未寫 podcast Google Doc" in line for line in result["log_summary"]))

    def test_two_failures_raises(self):
        briefing = make_threaded_briefing()

        class BadGemini:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt, model="gemini-2.5-pro"):
                self.calls += 1
                return {"segments": []}, 100, 50

        bad = BadGemini()
        fake = FakeFirestore()
        with patch.object(rss_podcast_script_service, "firestore_client", fake), \
             patch.object(rss_podcast_script_service, "gemini_client", bad), \
             patch.object(rss_podcast_script_service.openai_client, "client", None):
            with self.assertRaises(ValueError) as ctx:
                rss_podcast_script_service._generate_script_with_retry(briefing)
        self.assertEqual(bad.calls, 2)
        self.assertIn("after retry", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
