import unittest

from app.services.publish_package_service import build_publish_package


class PublishPackageServiceTest(unittest.TestCase):
    def test_build_publish_package_contains_required_upload_fields(self):
        package = build_publish_package(
            run_date="2026-03-25",
            research_data={
                "global_mood": "Markets are cautious but constructive.",
                "top_developments": [
                    {
                        "title": "AI capex remains elevated",
                        "business_implication": "Vendors with power access gain leverage.",
                        "sources": ["https://example.com/ai", "https://example.com/ai"],
                    }
                ],
                "source_categories": {"industry": ["https://example.com/source"]},
            },
            reviewed_briefing_text="Reviewed briefing text",
            script_text="Podcast script",
            doc_url="https://docs.google.com/document/d/doc/edit",
            audio_url="https://drive.google.com/file/d/audio/view",
        )

        self.assertIn("episode_title", package)
        self.assertIn("podcast_description", package)
        self.assertEqual(package["audio_url"], "https://drive.google.com/file/d/audio/view")
        self.assertEqual(package["doc_url"], "https://docs.google.com/document/d/doc/edit")
        self.assertEqual(
            package["source_links"],
            ["https://example.com/ai", "https://example.com/source"],
        )
        self.assertEqual(package["quality_report"]["status"], "needs_review")
        self.assertTrue(package["manual_upload_checklist"])


if __name__ == "__main__":
    unittest.main()
