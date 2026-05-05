import unittest
from unittest.mock import patch

from app.services import rss_source_service
from app.services.rss_source_service import (
    classify_health_status,
    count_duplicate_sheet_source_ids,
    parse_sheet_source_rows,
)


class RssSourceServiceTest(unittest.TestCase):
    def test_parse_sheet_rows_skips_missing_urls_and_keeps_health_separate(self):
        rows = [
            ["ignored", "metadata"],
            [
                "ID",
                "市場等級",
                "資料來源",
                "類別",
                "分類",
                "中文名稱",
                "精簡說明（可看到的新聞內容）",
                "RSS URL",
                "狀態",
                "上次偵測時間",
            ],
            [
                "reuters-us",
                "Global",
                "Reuters",
                "Market",
                "U.S. Markets",
                "美國市場",
                "Headlines",
                "https://example.com/rss",
                "✅ OK (200)",
                "2026-05-05 08:00",
            ],
            ["missing-url", "Global", "Reuters", "Market", "Bonds", "債券", "", "", "成功", ""],
        ]

        sources = parse_sheet_source_rows(rows, synced_at="2026-05-05T00:00:00Z")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].source_id, "reuters-us")
        self.assertEqual(sources[0].publisher, "Reuters")
        self.assertEqual(sources[0].desk, "Market")
        self.assertEqual(sources[0].health_status, "stable")
        self.assertTrue(sources[0].is_fetchable)

    def test_only_exact_ok_200_status_is_fetchable(self):
        self.assertEqual(classify_health_status("✅ OK (200)"), ("stable", True))
        self.assertEqual(classify_health_status("成功"), ("not_ok", False))
        self.assertEqual(classify_health_status("OK"), ("not_ok", False))
        self.assertEqual(classify_health_status(""), ("unknown", False))

    def test_duplicate_sheet_ids_get_stable_unique_source_ids(self):
        rows = [
            [
                "ID",
                "市場等級",
                "資料來源",
                "類別",
                "分類",
                "中文名稱",
                "精簡說明（可看到的新聞內容）",
                "RSS URL",
                "狀態",
                "上次偵測時間",
            ],
            ["dup", "Global", "CNBC", "Market", "Business", "", "", "https://example.com/a", "✅ OK (200)", ""],
            ["dup", "Global", "CNBC", "Market", "Tech", "", "", "https://example.com/b", "✅ OK (200)", ""],
        ]

        sources = parse_sheet_source_rows(rows, synced_at="2026-05-05T00:00:00Z")

        self.assertEqual(len({source.source_id for source in sources}), 2)
        self.assertTrue(all(source.source_id.startswith("dup-") for source in sources))
        self.assertEqual(count_duplicate_sheet_source_ids(rows), 1)

    def test_failed_status_is_not_fetchable_but_not_an_importance_signal(self):
        health_status, is_fetchable = classify_health_status("503 失敗")

        self.assertEqual(health_status, "broken")
        self.assertFalse(is_fetchable)

    def test_sync_uses_batch_write_and_deactivates_missing_sources(self):
        rows = [
            [
                "ID",
                "市場等級",
                "資料來源",
                "類別",
                "分類",
                "中文名稱",
                "精簡說明（可看到的新聞內容）",
                "RSS URL",
                "狀態",
                "上次偵測時間",
            ],
            [
                "source-1",
                "Global",
                "CNBC",
                "Market",
                "Business",
                "商業",
                "Headlines",
                "https://example.com/rss",
                "✅ OK (200)",
                "2026-05-05 08:00",
            ],
        ]

        class FakeSheetsClient:
            def read_source_rows(self):
                return rows

        class FakeFirestore:
            def __init__(self):
                self.sources = []
                self.active_source_ids = set()

            def upsert_rss_sources(self, sources):
                self.sources = sources

            def deactivate_missing_rss_sources(self, active_source_ids, synced_at):
                self.active_source_ids = active_source_ids
                return 3

        fake_firestore = FakeFirestore()

        with (
            patch.object(rss_source_service, "SheetsClient", return_value=FakeSheetsClient()),
            patch.object(rss_source_service, "firestore_client", fake_firestore),
        ):
            result = rss_source_service.sync_rss_sources_from_sheet()

        self.assertEqual(result["synced_source_count"], 1)
        self.assertEqual(result["fetchable_source_count"], 1)
        self.assertEqual(result["deactivated_missing_source_count"], 3)
        self.assertEqual(result["unique_source_count"], 1)
        self.assertEqual(result["duplicate_source_id_count"], 0)
        self.assertEqual(fake_firestore.active_source_ids, {"source-1"})


if __name__ == "__main__":
    unittest.main()
