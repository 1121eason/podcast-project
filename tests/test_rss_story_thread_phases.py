"""Tests for W7 phase tree (lazy bootstrap, heuristic + LLM assignment, status transitions)."""

import math
import unittest
from unittest.mock import patch

from app.models.signal import RssSignal, RssStoryThread, RssThreadPhase
from app.services import rss_story_thread_service


def vec(cosine: float) -> list[float]:
    return [cosine, math.sqrt(max(0.0, 1.0 - cosine * cosine))]


def make_signal(**kwargs) -> RssSignal:
    return RssSignal(
        signal_id=kwargs.get("signal_id", "sig_x"),
        generated_at=kwargs.get("generated_at", "2026-05-14T00:00:00Z"),
        window_start="2026-05-14T00:00:00Z",
        window_end=kwargs.get("window_end", "2026-05-14T00:00:00Z"),
        member_item_ids=kwargs.get("member_item_ids", ["item_x"]),
        cluster_size=1,
        source_count=1,
        publisher_count=1,
        publishers=kwargs.get("publishers", ["Reuters"]),
        publisher_tier=kwargs.get("publisher_tier", "tier1"),
        representative_title=kwargs.get("representative_title", "OpenAI 與 Microsoft 算力配額爭議"),
        representative_summary="算力配額談判細節",
        representative_publisher="Reuters",
        representative_published_at="2026-05-14T00:00:00Z",
        key_entities=kwargs.get("key_entities", ["OpenAI", "Microsoft"]),
        what_happened=kwargs.get("what_happened", "OpenAI 要求更多算力，Microsoft 拒絕"),
        signal_status=kwargs.get("signal_status", "supported"),
        event_centroid=kwargs.get("event_centroid", vec(1.0)),
        entity_centroid=vec(1.0),
        impact_centroid=vec(1.0),
        context_centroid=kwargs.get("context_centroid", vec(1.0)),
        importance_score=kwargs.get("importance_score"),
        adjudication_decision=kwargs.get("adjudication_decision"),
        adjudication_confidence=kwargs.get("adjudication_confidence"),
        adjudication_candidate_thread_id=kwargs.get("adjudication_candidate_thread_id"),
    )


def make_thread(**kwargs) -> RssStoryThread:
    return RssStoryThread(
        thread_id=kwargs.get("thread_id", "thread_x"),
        title=kwargs.get("title", "OpenAI Microsoft 關係緊張"),
        active_since=kwargs.get("active_since", "2026-05-01T00:00:00Z"),
        last_seen_at=kwargs.get("last_seen_at", "2026-05-14T00:00:00Z"),
        signal_ids=kwargs.get("signal_ids", []),
        key_entities=kwargs.get("key_entities", ["OpenAI", "Microsoft"]),
        event_centroid=kwargs.get("event_centroid", vec(1.0)),
        context_centroid=kwargs.get("context_centroid", vec(1.0)),
        known_background=kwargs.get("known_background", ""),
        phases_initialized_at=kwargs.get("phases_initialized_at"),
    )


def make_phase(**kwargs) -> RssThreadPhase:
    return RssThreadPhase(
        phase_id=kwargs.get("phase_id", "phase_x"),
        thread_id=kwargs.get("thread_id", "thread_x"),
        title=kwargs.get("title", "算力配額爭議"),
        status=kwargs.get("status", "active"),
        signal_ids=kwargs.get("signal_ids", []),
        signal_count=kwargs.get("signal_count", 0),
        key_entities=kwargs.get("key_entities", ["OpenAI", "Microsoft"]),
        summary=kwargs.get("summary", ""),
        event_centroid=kwargs.get("event_centroid", vec(1.0)),
        context_centroid=kwargs.get("context_centroid", vec(1.0)),
        opened_at=kwargs.get("opened_at", "2026-05-10T00:00:00Z"),
        last_advanced_at=kwargs.get("last_advanced_at", "2026-05-14T00:00:00Z"),
    )


class TestBootstrap(unittest.TestCase):
    def test_seed_phase_created_when_thread_uninitialized(self):
        thread = make_thread(signal_ids=["old_1", "old_2", "old_3"])
        phases = rss_story_thread_service._bootstrap_seed_phase_if_needed(thread, [])
        self.assertEqual(len(phases), 1)
        seed = phases[0]
        self.assertEqual(seed.thread_id, thread.thread_id)
        self.assertEqual(seed.signal_count, 3)
        self.assertEqual(seed.status, "active")
        self.assertIsNotNone(thread.phases_initialized_at)
        self.assertEqual(seed.title, thread.title)

    def test_seed_phase_emerging_when_only_one_signal(self):
        thread = make_thread(signal_ids=["old_1"])
        phases = rss_story_thread_service._bootstrap_seed_phase_if_needed(thread, [])
        self.assertEqual(phases[0].status, "emerging")

    def test_already_initialized_thread_unchanged(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        existing = [make_phase()]
        phases = rss_story_thread_service._bootstrap_seed_phase_if_needed(thread, existing)
        self.assertEqual(phases, existing)


class TestPhaseAssignment(unittest.TestCase):
    def test_cosine_heuristic_assigns_without_llm(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(event_centroid=vec(1.0))
        signal = make_signal(event_centroid=vec(1.0))  # cosine == 1.0 ≥ 0.82
        with patch.object(rss_story_thread_service, "gemini_client") as fake_gemini:
            updated, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_heuristic_assignments"), 1)
        self.assertEqual(stats.get("phase_llm_calls", 0), 0)
        fake_gemini.generate_json.assert_not_called()
        self.assertEqual(signal.phase_id, phase.phase_id)
        self.assertIn(signal.signal_id, phase.signal_ids)

    def test_w4_evidence_shortcut_uses_no_llm(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        # Phase centroid is orthogonal to signal — cosine path would FAIL.
        phase = make_phase(event_centroid=vec(0.0), context_centroid=vec(0.0))
        signal = make_signal(
            event_centroid=vec(0.5),
            context_centroid=vec(0.5),
            adjudication_decision="same_thread",
            adjudication_confidence=0.7,
            adjudication_candidate_thread_id="thread_x",
        )
        with patch.object(rss_story_thread_service, "gemini_client") as fake_gemini:
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_w4_evidence_assignments"), 1)
        self.assertEqual(stats.get("phase_llm_calls", 0), 0)
        fake_gemini.generate_json.assert_not_called()
        self.assertEqual(signal.phase_id, phase.phase_id)

    def test_llm_path_continues_core_routes_to_existing_phase(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(event_centroid=vec(0.0))  # force ambiguous
        signal = make_signal()  # default event_centroid=vec(1.0) is orthogonal to phase vec(0.0)

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "continues_core",
                            "phase_id": phase.phase_id,
                            "novelty_reason": "延續配額爭議",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_llm_calls"), 1)
        self.assertEqual(signal.phase_id, phase.phase_id)
        self.assertIn(signal.signal_id, phase.signal_ids)

    def test_llm_path_new_axis_creates_phase_with_parent(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        parent = make_phase(phase_id="phase_parent", event_centroid=vec(0.0))
        signal = make_signal()  # default event_centroid=vec(1.0) is orthogonal to phase vec(0.0)

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "new_axis",
                            "new_phase_title": "IPO 時程衝突",
                            "parent_phase_id": parent.phase_id,
                            "novelty_reason": "從算力爭議延伸到 IPO",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            updated, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [parent]
            )
        self.assertEqual(stats.get("phases_created"), 1)
        # Parent should have new phase as child.
        new_phase_ids = [p.phase_id for p in updated if p.phase_id != parent.phase_id]
        self.assertEqual(len(new_phase_ids), 1)
        new_phase_id = new_phase_ids[0]
        self.assertIn(new_phase_id, parent.child_phase_ids)
        new_phase = next(p for p in updated if p.phase_id == new_phase_id)
        self.assertEqual(new_phase.parent_phase_id, parent.phase_id)
        self.assertEqual(new_phase.status, "emerging")
        self.assertEqual(new_phase.title, "IPO 時程衝突")

    def test_llm_path_background_repeat_flags_signal_no_advance(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(event_centroid=vec(0.0), last_advanced_at="2026-05-10T00:00:00Z")
        original_advanced = phase.last_advanced_at
        signal = make_signal()  # default event_centroid=vec(1.0) is orthogonal to phase vec(0.0)

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "background_repeat",
                            "phase_id": phase.phase_id,
                            "novelty_reason": "重複講背景",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("background_repeat_count"), 1)
        self.assertTrue(signal.is_background_repeat)
        self.assertEqual(phase.last_advanced_at, original_advanced)  # not advanced

    def test_llm_path_invalid_phase_id_falls_back(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(phase_id="phase_real", event_centroid=vec(0.0))
        signal = make_signal()  # default event_centroid=vec(1.0) is orthogonal to phase vec(0.0)

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "continues_core",
                            "phase_id": "phase_does_not_exist",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_llm_invalid_id_count"), 1)
        # Falls back to most-recent-active phase.
        self.assertEqual(signal.phase_id, phase.phase_id)

    def test_different_thread_decision_flags_signal(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(event_centroid=vec(0.0))
        signal = make_signal()  # default event_centroid=vec(1.0) is orthogonal to phase vec(0.0)

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "different_thread",
                            "novelty_reason": "這條應該是別的 thread",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("thread_mismatch_flagged_count"), 1)
        self.assertIn("thread_mismatch_suspected", signal.adjudication_rationale or "")


class TestStatusTransitions(unittest.TestCase):
    def test_emerging_promoted_to_active_after_two_signals(self):
        phase = make_phase(status="emerging", signal_count=2, last_advanced_at="2026-05-14T00:00:00Z")
        rss_story_thread_service._assign_phase_status(phase, "2026-05-14T00:00:00Z")
        self.assertEqual(phase.status, "active")

    def test_active_becomes_dormant_after_seven_days(self):
        phase = make_phase(status="active", last_advanced_at="2026-05-01T00:00:00Z")
        rss_story_thread_service._assign_phase_status(phase, "2026-05-15T00:00:00Z")
        self.assertEqual(phase.status, "dormant")

    def test_resolved_status_is_sticky(self):
        phase = make_phase(status="resolved", last_advanced_at="2026-05-01T00:00:00Z")
        rss_story_thread_service._assign_phase_status(phase, "2026-05-15T00:00:00Z")
        self.assertEqual(phase.status, "resolved")


class TestPersistenceFixes(unittest.TestCase):
    """Regressions for P1.2 — status transitions & parent updates must reach Firestore."""

    def test_dormant_transition_returned_for_upsert(self):
        # Phase last advanced 10 days ago, no signal touches it today — should flip
        # to dormant AND be in the returned list so caller upserts it.
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        stale = make_phase(
            phase_id="phase_stale",
            status="active",
            last_advanced_at="2026-05-04T00:00:00Z",  # 11 days before 2026-05-15
        )
        # Pass NO new signals — only the status sweep should run.
        with patch.object(rss_story_thread_service, "utc_now_iso", return_value="2026-05-15T00:00:00Z"):
            updated, _ = rss_story_thread_service._assign_phases_for_thread(
                thread, [], [stale]
            )
        self.assertEqual(stale.status, "dormant")
        self.assertIn(stale, updated, "dormant transition must be returned for upsert")

    def test_new_axis_parent_added_to_returned_list(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        parent = make_phase(phase_id="phase_parent", event_centroid=vec(0.0))
        signal = make_signal()  # orthogonal to parent → ambiguous → LLM

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "new_axis",
                            "new_phase_title": "新軸",
                            "parent_phase_id": parent.phase_id,
                            "novelty_reason": "test",
                        }
                    ]
                }, 100, 50

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            updated, _ = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [parent]
            )
        # Both parent (mutated child_phase_ids) and the new phase must be in updated.
        ids = {p.phase_id for p in updated}
        self.assertIn(parent.phase_id, ids, "parent's child_phase_ids was mutated — must be upserted")
        self.assertEqual(len(parent.child_phase_ids), 1)


class TestPhaseLLMTokenAccounting(unittest.TestCase):
    """Regression for P1.3 — phase LLM tokens must be tracked, not discarded."""

    def test_llm_tokens_recorded_into_stats(self):
        thread = make_thread(phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(event_centroid=vec(0.0))
        signal = make_signal()

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "continues_core",
                            "phase_id": phase.phase_id,
                        }
                    ]
                }, 1234, 567

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_llm_input_tokens"), 1234)
        self.assertEqual(stats.get("phase_llm_output_tokens"), 567)


class TestW4EvidenceShortcutGuard(unittest.TestCase):
    """Regression for P2 — shortcut must only apply when W4's candidate thread matches."""

    def test_shortcut_fires_when_candidate_thread_matches(self):
        thread = make_thread(thread_id="thread_x", phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(thread_id="thread_x", event_centroid=vec(0.0))
        signal = make_signal(
            adjudication_decision="same_thread",
            adjudication_candidate_thread_id="thread_x",  # matches!
        )
        with patch.object(rss_story_thread_service, "gemini_client") as fake:
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_w4_evidence_assignments"), 1)
        fake.generate_json.assert_not_called()

    def test_shortcut_skipped_when_candidate_thread_differs(self):
        # W4 said "same_thread as a signal in thread_other", but W7 placed this signal in thread_x.
        # Shortcut MUST NOT fire — that would silently put the signal in the wrong phase.
        thread = make_thread(thread_id="thread_x", phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(thread_id="thread_x", event_centroid=vec(0.0))
        signal = make_signal(
            adjudication_decision="same_thread",
            adjudication_candidate_thread_id="thread_other",  # mismatch
        )

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {
                    "decisions": [
                        {
                            "signal_id": signal.signal_id,
                            "decision": "continues_core",
                            "phase_id": phase.phase_id,
                        }
                    ]
                }, 50, 25

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        # Shortcut skipped → fell through to LLM batch.
        self.assertEqual(stats.get("phase_w4_evidence_assignments", 0), 0)
        self.assertEqual(stats.get("phase_llm_calls"), 1)

    def test_shortcut_skipped_when_candidate_thread_id_is_none(self):
        # best_signal had no thread_id → adjudication_candidate_thread_id is None.
        thread = make_thread(thread_id="thread_x", phases_initialized_at="2026-05-10T00:00:00Z")
        phase = make_phase(thread_id="thread_x", event_centroid=vec(0.0))
        signal = make_signal(
            adjudication_decision="same_thread",
            adjudication_candidate_thread_id=None,
        )

        class FakeGemini:
            def generate_json(self, prompt, model):
                return {"decisions": []}, 30, 10

        with patch.object(rss_story_thread_service, "gemini_client", FakeGemini()):
            _, stats = rss_story_thread_service._assign_phases_for_thread(
                thread, [signal], [phase]
            )
        self.assertEqual(stats.get("phase_w4_evidence_assignments", 0), 0)


class TestStoryPriorityKey(unittest.TestCase):
    def test_w4_evidence_outranks_higher_importance_without_evidence(self):
        with_evidence = make_signal(
            signal_id="sig_evidenced",
            adjudication_decision="same_thread",
            importance_score=50,
        )
        without_evidence = make_signal(
            signal_id="sig_high_imp",
            adjudication_decision=None,
            importance_score=95,
            window_end="2026-05-14T01:00:00Z",
        )
        ranked = sorted(
            [without_evidence, with_evidence],
            key=rss_story_thread_service._story_priority_key,
            reverse=True,
        )
        self.assertEqual(ranked[0].signal_id, with_evidence.signal_id)


if __name__ == "__main__":
    unittest.main()
