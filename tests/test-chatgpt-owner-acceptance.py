#!/usr/bin/env python3
"""Regression tests for the ChatGPT owner/UI release evidence gate."""
from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "chatgpt_owner_acceptance",
    ROOT / "scripts" / "check-chatgpt-owner-acceptance.py",
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)

PROJECT_SPEC = importlib.util.spec_from_file_location(
    "project_stable_release",
    ROOT / "scripts" / "project-stable-release.py",
)
PROJECT = importlib.util.module_from_spec(PROJECT_SPEC)
assert PROJECT_SPEC.loader is not None
PROJECT_SPEC.loader.exec_module(PROJECT)

PROVENANCE = "a" * 40
SOURCE = "b" * 40
BUNDLE = "c" * 64
EXPECTED_ENDPOINT = "https://drlink.example.com/mcp"
PROVENANCE_TIME = datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def manifest():
    return {
        "source_head": SOURCE,
        "features": {"mcp_included": True},
        "artifacts": {"bootstrap-server.sh": {"sha256": BUNDLE}},
    }


def evidence():
    return {
        "schema_version": 2,
        "status": "PASS",
        "client_plan": "Business",
        "client_surface": "ChatGPT owner/UI",
        "support_reference": "https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt",
        "support_checked_at": "2026-09-28T20:00:00+09:00",
        "core_provenance_head": PROVENANCE,
        "core_source_head": SOURCE,
        "bootstrap_server_sha256": BUNDLE,
        "mcp_endpoint": "https://drlink.example.com/mcp",
        "oauth_authorization_code_consent": "PASS",
        "tool_discovery": "PASS",
        "policy_allowed_operation": "PASS",
        "policy_denied_operation": "PASS",
        "captured_at": "2026-09-28T20:30:00+09:00",
        "evidence_refs": ["owner-ui-session.txt"],
    }


class OwnerAcceptanceTests(unittest.TestCase):
    def check(self, data=None, mf=None, head=PROVENANCE, expected_endpoint=EXPECTED_ENDPOINT):
        return MOD.validate_evidence(
            data if data is not None else evidence(),
            provenance_head=head,
            manifest=mf if mf is not None else manifest(),
            provenance_committed_at=PROVENANCE_TIME,
            now=NOW,
            expected_mcp_endpoint=expected_endpoint,
        )

    def test_valid_exact_candidate_evidence(self):
        self.assertEqual(self.check(), [])

    def test_stale_provenance_rejected(self):
        self.assertIn("core_provenance_head does not match current HEAD", self.check(head="d" * 40))

    def test_machine_only_or_missing_owner_steps_rejected(self):
        data = evidence()
        data["oauth_authorization_code_consent"] = "BLOCKED"
        self.assertIn("oauth_authorization_code_consent must be PASS", self.check(data))

    def test_insecure_or_non_mcp_endpoint_rejected(self):
        data = evidence()
        data["mcp_endpoint"] = "http://127.0.0.1:6103/mcp"
        errs = self.check(data)
        self.assertTrue(any("https" in err or "public DNS" in err for err in errs), errs)

    def test_endpoint_must_match_qualified_public_endpoint(self):
        data = evidence()
        data["mcp_endpoint"] = "https://other.example.com/mcp"
        self.assertIn(
            "mcp_endpoint does not match qualified public MCP endpoint",
            self.check(data),
        )

    def test_manifest_without_mcp_rejected(self):
        mf = manifest()
        mf["features"]["mcp_included"] = False
        self.assertIn("release manifest does not include MCP", self.check(mf=mf))

    def test_pre_candidate_capture_rejected(self):
        data = evidence()
        data["captured_at"] = "2026-09-28T10:59:59+00:00"
        self.assertIn("captured_at predates current provenance commit", self.check(data))

    def test_far_future_capture_rejected(self):
        data = evidence()
        data["captured_at"] = "2026-09-28T12:11:00+00:00"
        self.assertIn("captured_at is more than 10 minutes in the future", self.check(data))

    def test_evidence_refs_required(self):
        data = evidence()
        data["evidence_refs"] = []
        self.assertIn(
            "evidence_refs must contain at least one retained evidence reference",
            self.check(data),
        )

    def test_plan_name_is_evidence_not_hardcoded_allowlist(self):
        data = evidence()
        data["client_plan"] = "Future Full MCP Plan"
        self.assertEqual(self.check(data), [])

    def test_legacy_plus_surface_is_rejected(self):
        data = evidence()
        data["client_surface"] = "ChatGPT Plus owner/UI"
        self.assertIn("client_surface must be ChatGPT owner/UI", self.check(data))

    def test_actual_plan_is_required(self):
        data = evidence()
        data["client_plan"] = ""
        self.assertIn("client_plan must record one safe actual ChatGPT plan name", self.check(data))

    def test_plan_name_rejects_control_characters(self):
        data = evidence()
        data["client_plan"] = "Business\nFAKE=PASS"
        self.assertIn(
            "client_plan must record one safe actual ChatGPT plan name",
            self.check(data),
        )

    def test_support_reference_must_be_official_help_center(self):
        data = evidence()
        data["support_reference"] = "https://example.com/full-mcp"
        self.assertIn(
            "support_reference must use the official OpenAI Help Center",
            self.check(data),
        )

    def test_support_reference_must_bind_specific_mcp_support_article(self):
        data = evidence()
        data["support_reference"] = "https://help.openai.com/en/articles/99999999-unrelated"
        self.assertIn(
            "support_reference must reference OpenAI Help Center article 12584461",
            self.check(data),
        )

    def test_support_reference_rejects_query_or_fragment(self):
        data = evidence()
        data["support_reference"] += "?source=untrusted"
        self.assertIn(
            "support_reference must not contain query or fragment",
            self.check(data),
        )

    def test_support_reference_rejects_output_injection(self):
        data = evidence()
        data["support_reference"] += "\nFAKE=PASS"
        self.assertIn(
            "support_reference must not contain surrounding whitespace or control characters",
            self.check(data),
        )

    def test_support_check_must_be_current_at_capture(self):
        data = evidence()
        data["support_checked_at"] = "2026-08-01T00:00:00+00:00"
        self.assertIn(
            "support_checked_at is older than 30 days at evidence capture time",
            self.check(data),
        )

    def test_stable_projection_requires_owner_evidence_binding(self):
        release_evidence = {
            "status": "PASS",
            "pass1_head": PROVENANCE,
            "pass2_head": PROVENANCE,
            "final_qualified_head": PROVENANCE,
            "qualification_evidence_sha256": "e" * 64,
            "trusted_qualification_review": "PASS",
            "trusted_qualification_evidence_sha256": "e" * 64,
        }
        errs = PROJECT.evidence_errors(
            release_evidence,
            PROVENANCE,
            require_chatgpt_owner=True,
        )
        self.assertTrue(any("owner/UI acceptance" in err for err in errs), errs)
        release_evidence.update(
            {
                "chatgpt_owner_ui_acceptance": "PASS",
                "chatgpt_owner_evidence_sha256": "d" * 64,
                "chatgpt_owner_evidence_provenance_head": PROVENANCE,
            }
        )
        errs = PROJECT.evidence_errors(
            release_evidence,
            PROVENANCE,
            require_chatgpt_owner=True,
        )
        self.assertTrue(any("protected owner/UI review" in err for err in errs), errs)
        release_evidence["trusted_owner_ui_review"] = "PASS"
        release_evidence["trusted_owner_ui_evidence_sha256"] = "d" * 64
        self.assertEqual(
            PROJECT.evidence_errors(
                release_evidence,
                PROVENANCE,
                require_chatgpt_owner=True,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
