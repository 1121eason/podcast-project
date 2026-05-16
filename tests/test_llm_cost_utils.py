"""Regression tests for llm_cost_utils — guards against the 1000x bug
that previously inflated all reported costs."""

import unittest

from app.services.llm_cost_utils import compute_llm_cost, pricing_for_model


class TestComputeLLMCost(unittest.TestCase):
    def test_pro_20k_input_8k_output_matches_public_price(self):
        # Gemini 2.5 Pro: $1.25/M input, $10/M output.
        # 20k input × $1.25/M = $0.025
        # 8k output × $10/M = $0.080
        # Total = $0.105
        cost = compute_llm_cost("gemini-2.5-pro", 20_000, 8_000)
        self.assertAlmostEqual(cost, 0.105, places=4)

    def test_flash_typical_usage(self):
        # Gemini 2.5 Flash: $0.075/M input, $0.30/M output.
        # 10k input × $0.075/M = $0.00075
        # 2k output × $0.30/M  = $0.00060
        # Total = $0.00135
        cost = compute_llm_cost("gemini-2.5-flash", 10_000, 2_000)
        self.assertAlmostEqual(cost, 0.00135, places=5)

    def test_unknown_model_falls_back_to_pro_pricing(self):
        # Unknown model uses fallback (Pro-level) so we over-report rather than
        # silently undercount.
        cost_unknown = compute_llm_cost("imaginary-model-7000", 20_000, 8_000)
        cost_pro = compute_llm_cost("gemini-2.5-pro", 20_000, 8_000)
        self.assertEqual(cost_unknown, cost_pro)

    def test_zero_tokens_zero_cost(self):
        self.assertEqual(compute_llm_cost("gemini-2.5-pro", 0, 0), 0.0)

    def test_none_model_uses_fallback(self):
        self.assertGreater(compute_llm_cost(None, 1000, 0), 0)

    def test_pricing_for_model_returns_dict(self):
        p = pricing_for_model("gemini-2.5-pro")
        self.assertEqual(p["input"], 1.25)
        self.assertEqual(p["output"], 10.0)

    def test_briefing_typical_full_run(self):
        # Realistic W8 briefing: ~8k input + 4k output of Pro.
        # Should be on the order of a couple cents, not $50.
        cost = compute_llm_cost("gemini-2.5-pro", 8_000, 4_000)
        self.assertLess(cost, 0.10)
        self.assertGreater(cost, 0.0)


if __name__ == "__main__":
    unittest.main()
