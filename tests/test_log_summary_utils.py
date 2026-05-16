import unittest

from app.services.log_summary_utils import (
    LOG_SUMMARY_VERSION,
    MAX_LOG_LINES,
    add_duplicate_log_summary,
    add_log_summary,
    cost_text,
    sample_values,
    seconds_text,
    tagged,
    token_text,
)


class LogSummaryUtilsTest(unittest.TestCase):
    def test_tagged_uses_stable_prefixes(self):
        self.assertEqual(tagged("ok", "完成"), "[ok] 完成")
        self.assertEqual(tagged("unknown", "完成"), "[ok] 完成")

    def test_sample_values_limits_to_three(self):
        self.assertEqual(sample_values(["a", "b", "c", "d"]), "a、b、c")

    def test_empty_lines_get_safe_default(self):
        result = {}
        add_log_summary(result, ["", None])
        self.assertEqual(result["log_summary_version"], LOG_SUMMARY_VERSION)
        self.assertIn("[ok]", result["log_summary"][0])

    def test_duplicate_summary_prepends_skip_and_preserves_previous(self):
        result = {"log_summary": ["[ok] previous"]}
        add_duplicate_log_summary(result, "W7", "DAILY_2026_05_16")
        self.assertEqual(result["log_summary_version"], LOG_SUMMARY_VERSION)
        self.assertTrue(result["log_summary"][0].startswith("[skip]"))
        self.assertIn("[ok] previous", result["log_summary"])

    def test_cost_text_handles_zero_and_small(self):
        self.assertEqual(cost_text(0), "$0")
        self.assertEqual(cost_text(None), "$0")
        # 1000× bug regression: $0.105 must NOT render as $105 or $0.000105.
        self.assertEqual(cost_text(0.105), "$0.105")
        self.assertEqual(cost_text(0.000001), "$0.000001")
        # Strips trailing zeros / lone decimal point.
        self.assertEqual(cost_text(1.0), "$1")
        self.assertEqual(cost_text(0.10), "$0.1")

    def test_cost_text_handles_garbage_input(self):
        self.assertEqual(cost_text("not a number"), "$0")
        self.assertEqual(cost_text([]), "$0")

    def test_seconds_text_threshold(self):
        self.assertEqual(seconds_text(500), "500ms")
        self.assertEqual(seconds_text(1500), "1.5s")
        self.assertEqual(seconds_text(0), "0ms")
        self.assertEqual(seconds_text(None), "0ms")
        self.assertEqual(seconds_text("garbage"), "0ms")

    def test_token_text_format(self):
        self.assertEqual(token_text(1500, 800), "1500 input / 800 output tokens")
        self.assertEqual(token_text(None, None), "0 input / 0 output tokens")
        self.assertEqual(token_text("bad", "input"), "0 input / 0 output tokens")

    def test_max_log_lines_truncates(self):
        many = [tagged("ok", f"line {i}") for i in range(MAX_LOG_LINES + 4)]
        result = {}
        add_log_summary(result, many)
        self.assertEqual(len(result["log_summary"]), MAX_LOG_LINES)


if __name__ == "__main__":
    unittest.main()
