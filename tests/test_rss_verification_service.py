import unittest
from unittest.mock import patch

from app.models.signal import RssSignal
from app.services import rss_verification_service
from app.services.rss_verification_service import (
    determine_cluster_status,
    determine_topic_heat,
    verify_signals,
)


def make_signal(**kwargs):
    base = dict(
        signal_id=kwargs.get("signal_id", "sig_test"),
        generated_at="2026-05-07T00:00:00Z",
        window_start="2026-05-06T20:00:00Z",
        window_end="2026-05-07T00:00:00Z",
        cluster_size=kwargs.get("cluster_size", 1),
        source_count=kwargs.get("source_count", 1),
        publisher_count=kwargs.get("publisher_count", 1),
        publishers=kwargs.get("publishers", []),
        market_levels=kwargs.get("market_levels", []),
        cluster_status=kwargs.get("cluster_status"),
        topic_heat=kwargs.get("topic_heat"),
    )
    return RssSignal(**base)


class TestRules(unittest.TestCase):
    def test_single_source(self):
        s = make_signal(source_count=1, publishers=["CNBC"])
        self.assertEqual(determine_cluster_status(s), "single_source")
        self.assertEqual(determine_topic_heat(s), "low")

    def test_three_same_group_partially_supported(self):
        s = make_signal(
            source_count=3,
            publisher_count=3,
            publishers=["Reuters", "Bloomberg", "WSJ"],
            market_levels=["Global"],
        )
        # Three publishers in western_finance but only 1 independent group
        self.assertEqual(determine_cluster_status(s), "partially_supported")
        self.assertEqual(determine_topic_heat(s), "high")

    def test_three_cross_group_confirmed(self):
        s = make_signal(
            source_count=3,
            publisher_count=3,
            publishers=["Reuters", "NYT", "CNBC"],
            market_levels=["Global"],
        )
        self.assertEqual(determine_cluster_status(s), "confirmed")
        self.assertEqual(determine_topic_heat(s), "high")

    def test_global_with_two_groups_confirmed(self):
        s = make_signal(
            source_count=3,
            publisher_count=3,
            publishers=["Reuters", "Bloomberg", "CNBC"],
            market_levels=["Global"],
        )
        self.assertEqual(determine_cluster_status(s), "confirmed")

    def test_regional_only_taiwan(self):
        s = make_signal(
            source_count=3,
            publisher_count=3,
            publishers=["鉅亨", "經濟日報", "工商時報"],
            market_levels=["TW"],
        )
        self.assertEqual(determine_cluster_status(s), "regional_only")

    def test_two_sources_partially_supported(self):
        s = make_signal(
            source_count=2,
            publisher_count=2,
            publishers=["CNBC", "Reuters"],
            market_levels=["Global"],
        )
        self.assertEqual(determine_cluster_status(s), "partially_supported")
        self.assertEqual(determine_topic_heat(s), "medium")

    def test_viral(self):
        s = make_signal(
            source_count=8,
            publisher_count=6,
            publishers=["CNBC", "Reuters", "NYT", "BBC", "鉅亨", "Yahoo奇摩"],
            market_levels=["Global"],
        )
        self.assertEqual(determine_topic_heat(s), "viral")

    def test_unknown_publisher_counts_as_independent(self):
        s = make_signal(
            source_count=3,
            publisher_count=3,
            publishers=["Reuters", "Random Site", "Another Random"],
            market_levels=["Global"],
        )
        self.assertEqual(determine_cluster_status(s), "confirmed")


class FakeFirestoreClient:
    def __init__(self, signals):
        self.signals = signals
        self.upserted = []

    def list_recent_signals(self, since_iso, limit=2000):
        return list(self.signals)

    def upsert_rss_signals(self, signals):
        self.upserted.extend(signals)
        return len(signals)


class TestVerifySignalsFlow(unittest.TestCase):
    def test_writes_status_and_heat(self):
        signals = [
            make_signal(
                signal_id="s1",
                source_count=3,
                publisher_count=3,
                publishers=["Reuters", "NYT", "CNBC"],
                market_levels=["Global"],
            ),
            make_signal(
                signal_id="s2",
                source_count=1,
                publisher_count=1,
                publishers=["Yahoo奇摩"],
            ),
        ]
        fake_fc = FakeFirestoreClient(signals)
        with patch.object(rss_verification_service, "firestore_client", fake_fc):
            result = verify_signals(since_hours=24)
        self.assertEqual(result["verified_signal_count"], 2)
        self.assertEqual(result["log_summary_version"], 1)
        self.assertTrue(any("W5 Verify" in line for line in result["log_summary"]))
        self.assertEqual(len(fake_fc.upserted), 2)
        s1 = next(s for s in fake_fc.upserted if s.signal_id == "s1")
        s2 = next(s for s in fake_fc.upserted if s.signal_id == "s2")
        self.assertEqual(s1.cluster_status, "confirmed")
        self.assertEqual(s1.topic_heat, "high")
        self.assertEqual(s2.cluster_status, "single_source")
        self.assertEqual(s2.topic_heat, "low")

    def test_skips_already_verified(self):
        signals = [
            make_signal(
                signal_id="s1",
                source_count=2,
                publisher_count=2,
                publishers=["CNBC", "Reuters"],
                cluster_status="partially_supported",
                topic_heat="medium",
            ),
        ]
        fake_fc = FakeFirestoreClient(signals)
        with patch.object(rss_verification_service, "firestore_client", fake_fc):
            result = verify_signals(since_hours=24)
        self.assertEqual(result["verified_signal_count"], 0)
        self.assertEqual(result["skipped_already_verified_count"], 1)

    def test_force_overrides(self):
        signals = [
            make_signal(
                signal_id="s1",
                source_count=2,
                publisher_count=2,
                publishers=["CNBC", "Reuters"],
                cluster_status="partially_supported",
                topic_heat="medium",
            ),
        ]
        fake_fc = FakeFirestoreClient(signals)
        with patch.object(rss_verification_service, "firestore_client", fake_fc):
            result = verify_signals(since_hours=24, force=True)
        self.assertEqual(result["verified_signal_count"], 1)


if __name__ == "__main__":
    unittest.main()
