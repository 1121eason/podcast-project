import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts.audit_llm_token_capture import audit_paths


class LlmTokenCaptureAuditTest(unittest.TestCase):
    def test_current_services_have_no_token_capture_violations(self):
        findings = audit_paths(["app/services"])
        self.assertEqual([f.format() for f in findings], [])

    def test_audit_flags_underscore_token_discard(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_service.py"
            path.write_text(
                textwrap.dedent(
                    """
                    from app.clients.gemini_client import gemini_client

                    def bad(prompt):
                        payload, _, _ = gemini_client.generate_json(prompt, model="gemini-2.5-pro")
                        return payload
                    """
                ),
                encoding="utf-8",
            )
            findings = audit_paths([path])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "P0")
        self.assertIn("assigned to '_'", findings[0].message)

    def test_audit_flags_provider_key_costing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad_cost.py"
            path.write_text(
                textwrap.dedent(
                    """
                    from app.services.llm_cost_utils import compute_llm_cost

                    def bad():
                        return compute_llm_cost("gemini", 100, 20)
                    """
                ),
                encoding="utf-8",
            )
            findings = audit_paths([path])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "P1")
        self.assertIn("provider key", findings[0].message)


if __name__ == "__main__":
    unittest.main()
