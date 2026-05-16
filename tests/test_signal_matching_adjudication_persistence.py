"""Verify that W4 adjudication metadata (decision, confidence, rationale, candidate thread)
is persisted onto the resulting signal so W7 can consume it without recomputing."""

import math
import unittest
from unittest.mock import patch

from app.models.rss import RssItem
from app.services import rss_signal_matching_service


def vec(cosine: float) -> list[float]:
    return [cosine, math.sqrt(max(0.0, 1.0 - cosine * cosine))]


def make_item(**kwargs) -> RssItem:
    canonical = {
        "key_entities": ["NVIDIA"],
        "actor": "NVIDIA",
        "action": "expands",
        "object": "AI chip supply",
        "event_type": "tech",
        "impact_hint": "AI supply chain",
        "canonical_event_text": "NVIDIA expands AI chip supply",
        "confidence_score": 0.8,
    }
    return RssItem(
        item_id=kwargs.get("item_id", "item_1"),
        source_id="src_1",
        publisher="Reuters",
        desk="Tech",
        category="AI",
        market_level="Global",
        title=kwargs.get("title", "New export control hits NVIDIA supply chain"),
        url="https://example.com/item",
        guid="item_1",
        summary="NVIDIA expands AI chip supply for cloud customers.",
        first_seen_at="2026-05-10T00:00:00Z",
        last_seen_at="2026-05-10T00:00:00Z",
        published_at="2026-05-10T00:00:00Z",
        content_hash="hash_1",
        canonical_event=canonical,
        canonical_event_text=canonical["canonical_event_text"],
        canonical_event_hash="canon_1",
        event_embedding=kwargs.get("event_embedding", vec(0.65)),
        entity_embedding=vec(0.65),
        impact_embedding=kwargs.get("impact_embedding", vec(0.7)),
        context_embedding=kwargs.get("context_embedding", vec(0.7)),
    )


def make_signal(**kwargs):
    from app.models.signal import RssSignal

    return RssSignal(
        signal_id="sig_1",
        generated_at="2026-05-10T00:00:00Z",
        window_start="2026-05-10T00:00:00Z",
        window_end="2026-05-10T00:00:00Z",
        member_item_ids=["old_item"],
        cluster_size=1,
        source_count=1,
        publisher_count=1,
        publishers=["Bloomberg"],
        representative_title="NVIDIA expands AI chip supply",
        representative_summary="Cloud buyers receive more AI chips.",
        representative_publisher="Bloomberg",
        representative_published_at="2026-05-10T00:00:00Z",
        cluster_status="confirmed",
        topic_heat="high",
        key_entities=["NVIDIA"],
        what_happened="NVIDIA expands AI chip supply",
        signal_status="provisional",
        thread_id=kwargs.get("thread_id", "thread_a"),
        event_centroid=vec(1.0),
        entity_centroid=vec(1.0),
        impact_centroid=vec(1.0),
        context_centroid=vec(1.0),
    )


class _FakeGemini:
    def __init__(self, decision: str, confidence: float = 0.78, rationale: str = "rationale text"):
        self.decision = decision
        self.confidence = confidence
        self.rationale = rationale

    def generate_json(self, prompt, model):
        return {
            "decision": self.decision,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }, 100, 50


class TestAdjudicationPersistence(unittest.TestCase):
    def test_same_event_persists_metadata_on_merged_signal(self):
        item = make_item()
        signal = make_signal()
        with patch.object(rss_signal_matching_service, "gemini_client", _FakeGemini("same_event")):
            outcome, merged, _ = rss_signal_matching_service.match_item_to_signal(
                item, [signal], allow_adjudication=True
            )
        self.assertEqual(outcome, "matched")
        self.assertEqual(merged.adjudication_decision, "same_event")
        self.assertAlmostEqual(merged.adjudication_confidence, 0.78, places=3)
        self.assertEqual(merged.adjudication_rationale, "rationale text")
        self.assertEqual(merged.adjudication_candidate_thread_id, "thread_a")

    def test_same_thread_persists_metadata_and_thread_id(self):
        item = make_item()
        signal = make_signal()
        with patch.object(rss_signal_matching_service, "gemini_client", _FakeGemini("same_thread")):
            outcome, candidate, _ = rss_signal_matching_service.match_item_to_signal(
                item, [signal], allow_adjudication=True
            )
        self.assertEqual(outcome, "candidate")
        self.assertEqual(candidate.adjudication_decision, "same_thread")
        self.assertEqual(candidate.adjudication_candidate_thread_id, "thread_a")
        self.assertEqual(candidate.thread_id, "thread_a")

    def test_different_event_persists_metadata_without_thread_link(self):
        item = make_item()
        signal = make_signal()
        with patch.object(rss_signal_matching_service, "gemini_client", _FakeGemini("different_event")):
            outcome, new_signal, _ = rss_signal_matching_service.match_item_to_signal(
                item, [signal], allow_adjudication=True
            )
        self.assertEqual(outcome, "new")
        self.assertEqual(new_signal.adjudication_decision, "different_event")
        self.assertIsNone(new_signal.adjudication_candidate_thread_id)


if __name__ == "__main__":
    unittest.main()
