import unittest

from app.models.podcast import ScriptSegment
from app.services import podcast_doc_writer


class PodcastDocWriterTest(unittest.TestCase):
    def test_format_podcast_text_marks_codex_backup_doc(self):
        text = podcast_doc_writer._format_podcast_text(
            briefing_date="2026-05-09",
            episode_title="2026/05/09-測試標題",
            script="歡迎回到 Informative AI。內容。感謝各位今天的收聽，明天見。",
            segments=[
                ScriptSegment(
                    segment_id="seg_01",
                    position=1,
                    segment_type="opening",
                    title="開場",
                    duration_estimate_seconds=30,
                )
            ],
            show_notes="show notes",
            themes_covered=["tech_ai"],
            word_count=32,
            duration_estimate=1.5,
            validation_warnings=["warning"],
        )

        self.assertIn("更新紀錄：", text)
        self.assertIn("Codex 更新", text)
        self.assertIn("Episode title：2026/05/09-測試標題", text)
        self.assertIn("不是人工審稿關卡", text)
        self.assertIn("驗證提醒：warning", text)


if __name__ == "__main__":
    unittest.main()
