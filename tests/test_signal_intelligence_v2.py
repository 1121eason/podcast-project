import math
import unittest
from unittest.mock import patch

from app.models.rss import RssItem
from app.models.signal import RssSignal, RssStoryThread, WorkflowRun
from app.services import (
    rss_importance_service,
    rss_signal_matching_service,
    rss_signal_processor_service,
    rss_story_thread_service,
    workflow_run_service,
)
from app.services.signal_v2_utils import decay_centroid, event_embedding_hash


def vec(cosine: float) -> list[float]:
    return [cosine, math.sqrt(max(0.0, 1.0 - cosine * cosine))]


def make_item(**kwargs) -> RssItem:
    canonical = kwargs.get("canonical_event") or {
        "key_entities": kwargs.get("entities", ["NVIDIA"]),
        "actor": "NVIDIA",
        "action": kwargs.get("action", "expands"),
        "object": "AI chip supply",
        "event_type": "tech",
        "impact_hint": "AI supply chain",
        "canonical_event_text": kwargs.get("canonical_text", "NVIDIA expands AI chip supply"),
        "confidence_score": 0.8,
    }
    return RssItem(
        item_id=kwargs.get("item_id", "item_1"),
        source_id=kwargs.get("source_id", "src_1"),
        publisher=kwargs.get("publisher", "Reuters"),
        desk="Tech",
        category="AI",
        market_level="Global",
        title=kwargs.get("title", "NVIDIA expands AI chip supply"),
        url="https://example.com/item",
        guid=kwargs.get("item_id", "item_1"),
        summary=kwargs.get("summary", "NVIDIA expands AI chip supply for cloud customers."),
        first_seen_at=kwargs.get("first_seen_at", "2026-05-10T00:00:00Z"),
        last_seen_at="2026-05-10T00:00:00Z",
        published_at=kwargs.get("published_at", "2026-05-10T00:00:00Z"),
        content_hash=kwargs.get("content_hash", "hash_1"),
        canonical_event=canonical,
        canonical_event_text=canonical["canonical_event_text"],
        canonical_event_hash=kwargs.get("canonical_event_hash", "canon_1"),
        event_embedding=kwargs.get("event_embedding", [1.0, 0.0]),
        entity_embedding=kwargs.get("entity_embedding", [1.0, 0.0]),
        impact_embedding=kwargs.get("impact_embedding", [1.0, 0.0]),
        context_embedding=kwargs.get("context_embedding", [1.0, 0.0]),
    )


def make_signal(**kwargs) -> RssSignal:
    return RssSignal(
        signal_id=kwargs.get("signal_id", "sig_1"),
        generated_at=kwargs.get("generated_at", "2026-05-10T00:00:00Z"),
        window_start="2026-05-10T00:00:00Z",
        window_end=kwargs.get("window_end", "2026-05-10T00:00:00Z"),
        member_item_ids=kwargs.get("member_item_ids", ["old_item"]),
        cluster_size=kwargs.get("cluster_size", 1),
        source_count=kwargs.get("source_count", 1),
        publisher_count=kwargs.get("publisher_count", 1),
        publishers=kwargs.get("publishers", ["Bloomberg"]),
        representative_title=kwargs.get("representative_title", "NVIDIA expands AI chip supply"),
        representative_summary="Cloud buyers receive more AI chips.",
        representative_publisher="Bloomberg",
        representative_published_at="2026-05-10T00:00:00Z",
        cluster_status=kwargs.get("cluster_status", "confirmed"),
        topic_heat=kwargs.get("topic_heat", "high"),
        key_entities=kwargs.get("key_entities", ["NVIDIA"]),
        what_happened=kwargs.get("what_happened", "NVIDIA expands AI chip supply"),
        signal_status=kwargs.get("signal_status", "provisional"),
        event_centroid=kwargs.get("event_centroid", [1.0, 0.0]),
        entity_centroid=kwargs.get("entity_centroid", [1.0, 0.0]),
        impact_centroid=kwargs.get("impact_centroid", [1.0, 0.0]),
        context_centroid=kwargs.get("context_centroid", [1.0, 0.0]),
        importance_score=kwargs.get("importance_score"),
    )


class FakeWorkflowFirestore:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = []
        self.updated = []

    def get_workflow_run(self, run_id):
        return self.existing

    def create_workflow_run(self, run):
        self.created.append(run)
        self.existing = run
        return True

    def update_workflow_run(self, run_id, update_data):
        self.updated.append((run_id, update_data))


class TestWorkflowRunService(unittest.TestCase):
    def test_duplicate_completed_run_skips(self):
        existing = WorkflowRun(
            run_id="signal_process_BUCKET",
            workflow_name="signal_process",
            run_bucket="BUCKET",
            status="completed",
            started_at="2026-05-10T00:00:00Z",
            request_hash="old",
            summary={"processed_item_count": 3},
        )
        fake = FakeWorkflowFirestore(existing)
        with patch.object(workflow_run_service, "firestore_client", fake):
            should_skip, run_id, summary = workflow_run_service.start_workflow_run(
                "signal_process", "BUCKET", {"limit": 10}
            )
        self.assertTrue(should_skip)
        self.assertEqual(run_id, "signal_process_BUCKET")
        self.assertEqual(summary["processed_item_count"], 3)

    def test_duplicate_running_run_skips_to_prevent_retry_spend(self):
        existing = WorkflowRun(
            run_id="signal_process_BUCKET",
            workflow_name="signal_process",
            run_bucket="BUCKET",
            status="running",
            started_at="2026-05-10T00:00:00Z",
            request_hash="old",
        )
        fake = FakeWorkflowFirestore(existing)
        with patch.object(workflow_run_service, "firestore_client", fake):
            should_skip, _, summary = workflow_run_service.start_workflow_run(
                "signal_process", "BUCKET", {"limit": 10}
            )
        self.assertTrue(should_skip)
        self.assertEqual(summary["workflow_status"], "running")


class TestSignalMatching(unittest.TestCase):
    def test_high_score_auto_merges_and_updates_centroid(self):
        item = make_item(item_id="new_item", publisher="Reuters")
        signal = make_signal()
        outcome, merged, meta = rss_signal_matching_service.match_item_to_signal(item, [signal])

        self.assertEqual(outcome, "matched")
        self.assertGreaterEqual(meta["match_score"], 0.86)
        self.assertEqual(merged.signal_status, "supported")
        self.assertIn("new_item", merged.member_item_ids)
        self.assertEqual(
            merged.event_centroid,
            decay_centroid([1.0, 0.0], [1.0, 0.0], 0.85),
        )

    def test_review_band_creates_candidate_signal(self):
        item = make_item(
            event_embedding=vec(0.65),
            impact_embedding=vec(0.7),
            context_embedding=vec(0.7),
        )
        signal = make_signal()
        outcome, candidate, meta = rss_signal_matching_service.match_item_to_signal(item, [signal])

        self.assertEqual(outcome, "candidate")
        self.assertIn("sig_1", candidate.candidate_match_ids)
        self.assertGreaterEqual(meta["match_score"], 0.76)
        self.assertLess(meta["match_score"], 0.86)

    def test_review_band_can_be_adjudicated_into_same_event(self):
        class FakeMatchGemini:
            def generate_json(self, prompt, model):
                return {
                    "decision": "same_event",
                    "confidence": 0.78,
                    "rationale": "Same actor, object, and operational impact.",
                }, 120, 40

        item = make_item(
            title="New export control hits NVIDIA supply chain",
            event_embedding=vec(0.65),
            impact_embedding=vec(0.7),
            context_embedding=vec(0.7),
        )
        signal = make_signal()

        with patch.object(rss_signal_matching_service, "gemini_client", FakeMatchGemini()):
            outcome, merged, meta = rss_signal_matching_service.match_item_to_signal(
                item,
                [signal],
                allow_adjudication=True,
            )

        self.assertEqual(outcome, "matched")
        self.assertEqual(meta["adjudication_decision"], "same_event")
        self.assertEqual(meta["adjudication_model"], "gemini-2.5-pro")
        self.assertIn(item.item_id, merged.member_item_ids)

    def test_review_band_adjudicated_different_event_stays_separate(self):
        class FakeMatchGemini:
            def generate_json(self, prompt, model):
                return {
                    "decision": "different_event",
                    "confidence": 0.9,
                    "rationale": "Same entity but different action and object.",
                }, 100, 30

        item = make_item(
            title="New export control hits NVIDIA supply chain",
            event_embedding=vec(0.65),
            impact_embedding=vec(0.7),
            context_embedding=vec(0.7),
        )
        signal = make_signal()

        with patch.object(rss_signal_matching_service, "gemini_client", FakeMatchGemini()):
            outcome, new_signal, meta = rss_signal_matching_service.match_item_to_signal(
                item,
                [signal],
                allow_adjudication=True,
            )

        self.assertEqual(outcome, "new")
        self.assertEqual(meta["adjudication_decision"], "different_event")
        self.assertEqual(new_signal.candidate_match_ids, [])

    def test_hard_gate_blocks_different_entities_with_low_similarity(self):
        item = make_item(entities=["Apple"], event_embedding=[0.0, 1.0])
        signal = make_signal(key_entities=["NVIDIA"], event_centroid=[1.0, 0.0])

        outcome, candidate, meta = rss_signal_matching_service.match_item_to_signal(item, [signal])

        self.assertEqual(outcome, "new")
        self.assertEqual(candidate.candidate_match_ids, [])
        self.assertEqual(meta["match_score"], 0.0)


class FakeEmbeddingClient:
    model_name = "fake-embedding"

    def __init__(self):
        self.calls = 0

    def embed_batch(self, texts):
        self.calls += 1
        return [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0], [1.0, 0.0]], [], sum(len(t) for t in texts)


class FakeSignalProcessorFirestore:
    def __init__(self, items, active_signals=None):
        self.items = items
        self.active_signals = active_signals or []
        self.item_updates = {}
        self.signals = []
        self.signal_updates = {}

    def list_rss_items_pending_v2_processing(self, since_iso, limit=250):
        return list(self.items)[:limit]

    def update_rss_item_v2_fields(self, item_updates):
        self.item_updates.update(item_updates)
        return len(item_updates)

    def list_active_signals_for_matching(self, since_iso, limit=1000):
        return list(self.active_signals)

    def upsert_rss_signals(self, signals):
        self.signals.extend(signals)
        return len(signals)

    def update_rss_item_signal_ids(self, mapping):
        self.signal_updates.update(mapping)
        return len(mapping)


class TestSignalProcessorService(unittest.TestCase):
    def test_process_new_items_embeds_and_creates_provisional_signal(self):
        item = make_item(
            event_embedding=None,
            entity_embedding=None,
            impact_embedding=None,
            context_embedding=None,
            summary=(
                "NVIDIA expands AI chip supply for cloud customers, citing strong demand "
                "from hyperscalers and a sharp ramp-up across H100 / GB200 product lines. "
                "Executives say next-gen Blackwell shipments will be prioritised."
            ),
        )
        fake_firestore = FakeSignalProcessorFirestore([item])
        embedder = FakeEmbeddingClient()

        with patch.object(rss_signal_processor_service, "firestore_client", fake_firestore):
            result = rss_signal_processor_service.process_new_items(
                since_hours=6,
                limit_items=10,
                article_extraction="off",
                canonicalize="off",
                embedding_client=embedder,
            )

        self.assertEqual(result["processed_item_count"], 1)
        self.assertEqual(result["embedded_item_count"], 1)
        self.assertEqual(result["new_signal_count"], 1)
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(any("W4 處理" in line for line in result["log_summary"]))
        self.assertEqual(embedder.calls, 1)
        self.assertIn(item.item_id, fake_firestore.item_updates)
        self.assertEqual(fake_firestore.signals[0].signal_status, "provisional")

    def test_unchanged_embedding_hash_skips_embedding_call(self):
        item = make_item()
        item.event_embedding_hash = event_embedding_hash(
            rss_signal_processor_service.build_embedding_inputs(item)
        )
        fake_firestore = FakeSignalProcessorFirestore([item])
        embedder = FakeEmbeddingClient()

        with patch.object(rss_signal_processor_service, "firestore_client", fake_firestore):
            result = rss_signal_processor_service.process_new_items(
                since_hours=6,
                limit_items=10,
                article_extraction="off",
                canonicalize="off",
                embedding_client=embedder,
            )

        self.assertEqual(result["embedding_skipped_cached_count"], 1)
        self.assertEqual(embedder.calls, 0)

    def test_process_metrics_report_auto_match_and_duplicate_prevention(self):
        item = make_item()
        item.event_embedding_hash = event_embedding_hash(
            rss_signal_processor_service.build_embedding_inputs(item)
        )
        active_signal = make_signal(signal_status="provisional")
        fake_firestore = FakeSignalProcessorFirestore([item], [active_signal])
        embedder = FakeEmbeddingClient()

        with patch.object(rss_signal_processor_service, "firestore_client", fake_firestore):
            result = rss_signal_processor_service.process_new_items(
                since_hours=6,
                limit_items=10,
                article_extraction="off",
                canonicalize="off",
                embedding_client=embedder,
            )

        self.assertEqual(result["matched_item_count"], 1)
        self.assertEqual(result["auto_match_count"], 1)
        self.assertEqual(result["duplicate_prevention_ratio"], 1.0)
        self.assertEqual(result["supported_signal_write_count"], 1)

    def test_adjudication_tokens_aggregated_into_cost(self):
        """Regression: W4 must report Pro adjudication cost, not just embedding cost.

        Previously the [cost] line only showed embedding spend; the per-call Pro
        adjudication tokens returned in match_item_to_signal meta were dropped on
        the floor — making W4 cost report a fraction of reality.
        """
        # Item lands in review band → triggers adjudication.
        item = make_item(
            item_id="item_review",
            event_embedding=vec(0.65),
            impact_embedding=vec(0.7),
            context_embedding=vec(0.7),
            title="New export control hits NVIDIA supply chain",
        )
        item.event_embedding_hash = event_embedding_hash(
            rss_signal_processor_service.build_embedding_inputs(item)
        )
        active_signal = make_signal(signal_status="provisional")
        fake_firestore = FakeSignalProcessorFirestore([item], [active_signal])
        embedder = FakeEmbeddingClient()

        class FakeAdjGemini:
            def generate_json(self, prompt, model):
                return {
                    "decision": "same_event",
                    "confidence": 0.78,
                    "rationale": "Same actor / object / impact.",
                }, 1500, 800  # input_tokens=1500, output_tokens=800

        with patch.object(rss_signal_processor_service, "firestore_client", fake_firestore), \
             patch.object(rss_signal_matching_service, "gemini_client", FakeAdjGemini()):
            result = rss_signal_processor_service.process_new_items(
                since_hours=6,
                limit_items=10,
                article_extraction="off",
                canonicalize="off",
                embedding_client=embedder,
            )

        self.assertEqual(result["adjudication_call_count"], 1)
        self.assertEqual(result["adjudication_input_tokens"], 1500)
        self.assertEqual(result["adjudication_output_tokens"], 800)
        # Cost > 0 (Pro pricing applied), and total_cost >= adjudication_cost.
        self.assertGreater(result["adjudication_cost_usd"], 0)
        self.assertGreaterEqual(
            result["total_cost_usd"],
            result["adjudication_cost_usd"],
        )
        # log_summary [cost] line includes adjudication mention.
        cost_lines = [line for line in result["log_summary"] if line.startswith("[cost]")]
        self.assertTrue(cost_lines, "expected a [cost] line")
        self.assertIn("adjudication", cost_lines[0])

    def test_duplicate_run_bucket_gets_skip_log_summary(self):
        with patch.object(
            rss_signal_processor_service,
            "start_workflow_run",
            return_value=(True, "signal_process_BUCKET", {"processed_item_count": 3}),
        ):
            result = rss_signal_processor_service.process_new_items(run_bucket="BUCKET")
        self.assertTrue(result["skipped_duplicate"])
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(result["log_summary"][0].startswith("[skip]"))


class FakeStoryFirestore:
    def __init__(self, signals, threads=None, phases=None):
        self.signals = signals
        self.threads = threads or []
        self.phases = phases or []
        self.written_threads = []
        self.written_signals = []
        self.written_phases = []

    def list_recent_signals(self, since_iso, limit=2000):
        return list(self.signals)

    def list_recent_story_threads(self, since_iso, limit=200):
        return list(self.threads)

    def upsert_story_threads(self, threads):
        self.written_threads.extend(threads)
        return len(threads)

    def upsert_rss_signals(self, signals):
        self.written_signals.extend(signals)
        return len(signals)

    def list_phases_for_threads(self, thread_ids):
        result = {tid: [] for tid in thread_ids}
        for phase in self.phases:
            if phase.thread_id in result:
                result[phase.thread_id].append(phase)
        return result

    def list_phases_for_thread(self, thread_id):
        return [p for p in self.phases if p.thread_id == thread_id]

    def upsert_thread_phases(self, phases):
        self.written_phases.extend(phases)
        return len(phases)


class FakeThreadGemini:
    def __init__(self):
        self.calls = []

    def generate_json(self, prompt, model):
        self.calls.append((prompt, model))
        return {
            "known_background": "先前已提過 AI GPU 供應緊張。",
            "covered_points": ["AI GPU 供應緊張"],
            "latest_developments": ["今天新增雲端客戶配額調整"],
            "open_questions": ["雲端客戶是否轉嫁成本"],
            "today_delta": "今天的新變化是雲端客戶拿到新的 GPU 配額。",
            "novelty_score": 0.82,
            "do_not_repeat_points": ["不要重講 GPU 短缺背景"],
            "continuation_prompt_hint": "延續先前提到的 AI GPU 供應緊張，今天的新變化是雲端配額調整。",
        }, 100, 80


class TestStoryThreadService(unittest.TestCase):
    def test_consolidation_creates_thread_and_today_delta(self):
        signal = make_signal(
            signal_status="supported",
            importance_score=85,
            what_happened="NVIDIA ships a new AI GPU allocation to cloud providers",
        )
        fake_firestore = FakeStoryFirestore([signal])

        with patch.object(rss_story_thread_service, "firestore_client", fake_firestore):
            result = rss_story_thread_service.consolidate_daily(run_bucket=None)

        self.assertEqual(result["signals_considered"], 1)
        self.assertEqual(result["threads_created"], 1)
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(any("W7 整合" in line for line in result["log_summary"]))
        self.assertEqual(len(fake_firestore.written_threads), 1)
        self.assertTrue(fake_firestore.written_signals[0].today_delta)
        self.assertTrue(fake_firestore.written_threads[0].continuation_prompt_hint)

    def test_consolidation_refines_high_importance_existing_thread_with_gemini(self):
        signal = make_signal(
            signal_status="supported",
            importance_score=90,
            what_happened="NVIDIA changes AI GPU allocation for cloud providers",
        )
        thread = RssStoryThread(
            thread_id="thread_1",
            title="AI GPU supply",
            active_since="2026-05-01T00:00:00Z",
            last_seen_at="2026-05-09T00:00:00Z",
            signal_ids=["old_signal"],
            key_entities=["NVIDIA"],
            event_centroid=[1.0, 0.0],
            context_centroid=[1.0, 0.0],
            known_background="AI GPU supply has been tight.",
        )
        fake_firestore = FakeStoryFirestore([signal], [thread])
        fake_gemini = FakeThreadGemini()

        with patch.object(rss_story_thread_service, "firestore_client", fake_firestore), \
             patch.object(rss_story_thread_service, "gemini_client", fake_gemini):
            result = rss_story_thread_service.consolidate_daily(run_bucket=None)

        self.assertEqual(result["model_refined_count"], 1)
        self.assertEqual(len(fake_gemini.calls), 1)
        self.assertIn("雲端客戶拿到新的 GPU 配額", fake_firestore.written_threads[0].today_delta)


class TestQualityGate(unittest.TestCase):
    def test_quality_gate_skips_low_value_singleton(self):
        signal = make_signal(
            cluster_status="single_source",
            topic_heat="low",
            signal_status="provisional",
            representative_title="Market wrap: stocks close higher",
        )
        self.assertFalse(rss_importance_service._passes_quality_gate(signal, "supported_or_promoted"))

    def test_quality_gate_allows_major_black_swan_singleton(self):
        signal = make_signal(
            cluster_status="single_source",
            topic_heat="low",
            signal_status="provisional",
            representative_title="New export control hits NVIDIA supply chain",
        )
        self.assertTrue(rss_importance_service._passes_quality_gate(signal, "supported_or_promoted"))


if __name__ == "__main__":
    unittest.main()
