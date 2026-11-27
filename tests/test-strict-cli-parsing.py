#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import frp_cli_catalog as cat  # noqa: E402


class StrictCliParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = cat

    def test_system_version_rejects_extra(self):
        err = self.cat.strict_error(["system", "version", "abc"])
        self.assertIsNotNone(err)
        self.assertIn("unexpected argument", err)

    def test_show_status_rejects_extra(self):
        err = self.cat.strict_error(["show", "status", "extra"])
        self.assertIsNotNone(err)
        self.assertIn("unexpected argument", err)

    def test_status_alone_ok(self):
        self.assertIsNone(self.cat.strict_error(["show", "status"]))

    def test_approve_requires_identity_and_pending_id(self):
        one = ["set", "ai-identity", "plugin-qual", "approve"]
        two = one + ["oap_fixture"]
        self.assertIn("Missing argument", self.cat.strict_error(one))
        self.assertIsNone(self.cat.strict_error(two))
        self.assertIn("unexpected argument: extra", self.cat.strict_error(two + ["extra"]))
        self.assertEqual(self.cat.usage_line(self.cat.find(two)), "set ai-identity <IDENTITY> approve <PENDING-ID>")

    def test_ai_identity_credential_lifecycle_is_canonical(self):
        for suffix in (["rotate"], ["revoke"], ["authentication", "oauth"],
                       ["approve", "pending-example"], ["deny", "pending-example"],
                       ["oauth-redirect", "https://localhost/callback"]):
            tokens = ["set", "ai-identity", "example-ai", *suffix]
            cmd = self.cat.find(tokens, role="server")
            self.assertIsNotNone(cmd, tokens)
            self.assertFalse(cmd["hidden"], tokens)
            self.assertIsNone(self.cat.strict_error(tokens), tokens)
        import frp_ctl_grammar as grammar
        for old in (["system", "credential", "rotate", "ai-identity", "example-ai"],
                    ["system", "credential", "approve-oauth", "pending-example"]):
            self.assertIsNone(self.cat.find(old, role="server"))
            self.assertEqual(grammar.match(old, role="server").get("status"), "error")
            self.assertEqual(grammar.match(old + ["?"], role="server").get("status"), "error")
        self.assertIsNotNone(self.cat.strict_error(["set", "ai-identity", "example-ai", "deny", "pending-example", "extra"]))

    def test_guided_menu_categories(self):
        text = self.cat.render_guided_menu("server")
        self.assertIn("Managed Hosts", text)
        self.assertIn("Network Objects", text)
        self.assertIn("Service Objects", text)
        self.assertIn("Remote Access", text)
        self.assertIn("Internet Access", text)
        self.assertIn("AI Access", text)
        self.assertIn("System", text)
        self.assertNotIn("Controlled Egress", text)


if __name__ == "__main__":
    unittest.main()
