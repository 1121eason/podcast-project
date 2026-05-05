import json
import unittest

from app.services.normalize_service import normalize_research_output


class NormalizeServiceTest(unittest.TestCase):
    def test_normalize_research_output_accepts_signal_brief_schema(self):
        raw_output = json.dumps(
            {
                "date": "2026-03-25",
                "global_mood": "Risk appetite is selective.",
                "macro_themes": ["Rates", "AI infrastructure"],
                "top_developments": [
                    {
                        "rank": 1,
                        "title": "Central banks hold rates",
                        "what_happened": "Several central banks kept policy steady.",
                        "why_it_matters": "Capital costs remain a board-level constraint.",
                        "business_implication": "CFOs may keep delaying expansion plans.",
                        "who_is_affected": "Growth companies and lenders",
                        "what_to_watch_next": "Next inflation prints",
                        "confidence_level": "high",
                        "sources": ["https://example.com/rates"],
                    }
                ],
                "watch_next": ["Inflation data"],
                "source_categories": {"markets": ["https://example.com/rates"]},
            }
        )

        normalized = normalize_research_output(raw_output)

        self.assertEqual(normalized["top_developments"][0]["confidence_level"], "high")
        self.assertEqual(
            normalized["top_developments"][0]["business_implication"],
            "CFOs may keep delaying expansion plans.",
        )


if __name__ == "__main__":
    unittest.main()
