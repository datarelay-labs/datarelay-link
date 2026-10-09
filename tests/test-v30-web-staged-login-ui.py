#!/usr/bin/env python3
"""Supplemental (NOT browser E2E) staged Web login UX contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web/src/main.tsx"
BUNDLE = ROOT / "web/dist/app.js"


class StagedLoginUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.bundle = BUNDLE.read_text(encoding="utf-8")

    def test_password_submission_excludes_otp_and_recovery(self):
        block = self.source.split("async function submit(e:React.FormEvent)", 1)[1]
        block = block.split("async function finishLoginMfa", 1)[0]
        self.assertIn('"/api/v1/auth/login/start"', block)
        self.assertIn("JSON.stringify({username,password})", block)
        self.assertNotIn("totp:", block)
        self.assertNotIn("recovery_code:", block)
        self.assertIn('setPassword("")', block)
        self.assertNotIn('"/api/v1/auth/login"', self.source)

    def test_second_factor_is_a_distinct_accessibility_labeled_step(self):
        block = self.source.split("if(mfaChallenge)return <AuthScaffold>", 1)[1]
        block = block.split("if(setup)return <AuthScaffold>", 1)[0]
        self.assertIn('title="Verify your sign-in"', block)
        self.assertIn("No session has been granted yet.", block)
        self.assertIn('onSubmit={finishLoginMfa}', block)
        self.assertIn('autoComplete="one-time-code"', block)
        self.assertIn("Use recovery code", block)
        self.assertIn("Cancel and start over", block)
        self.assertNotIn("name=\"password\"", block)
        initial = self.source.split('if(setup)return <AuthScaffold>', 1)[1]
        initial = initial.split("function DraftWorkspace", 1)[0]
        self.assertNotIn("showMfa", initial)
        self.assertNotIn("Use MFA / recovery", initial)

    def test_production_bundle_contains_separate_login_endpoints(self):
        for phrase in (
            "/api/v1/auth/login/start",
            "/api/v1/auth/login/complete",
            "/api/v1/auth/login/cancel",
            "Verify your sign-in",
            "Verify and sign in",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.bundle)


if __name__ == "__main__":
    unittest.main()
