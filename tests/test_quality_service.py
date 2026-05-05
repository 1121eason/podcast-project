import unittest

from app.services.quality_service import build_quality_report


class QualityServiceTest(unittest.TestCase):
    def test_quality_report_passes_complete_package(self):
        research_data = {
            "top_developments": [
                {
                    "sources": ["https://example.com/1"],
                    "business_implication": "Capital allocation may shift.",
                    "confidence_level": "high",
                },
                {
                    "sources": ["https://example.com/2"],
                    "business_implication": "Supply chains may need redundancy.",
                    "confidence_level": "medium",
                },
                {
                    "sources": ["https://example.com/3"],
                    "business_implication": "Market entry timing may change.",
                    "confidence_level": "low",
                },
            ]
        }

        report = build_quality_report(
            research_data=research_data,
            reviewed_briefing_text="Reviewed briefing",
            script_text="Podcast script",
            source_links=[
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
                "https://example.com/4",
                "https://example.com/5",
            ],
        )

        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["warnings"])

    def test_quality_report_flags_missing_sources(self):
        report = build_quality_report(
            research_data={
                "top_developments": [
                    {
                        "sources": [],
                        "business_implication": "",
                        "confidence_level": "unknown",
                    }
                ]
            },
            reviewed_briefing_text="Reviewed briefing",
            script_text="Podcast script",
            source_links=[],
        )

        self.assertEqual(report["status"], "needs_review")
        self.assertIn("At least one development has no source link.", report["warnings"])


if __name__ == "__main__":
    unittest.main()
