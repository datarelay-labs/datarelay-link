#!/usr/bin/env python3
"""Regression tests for the ChatGPT Plus owner/UI release evidence gate."""
from __future__ import annotations

import importlib.util
import unittest
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


def manifest():
    return {
        "source_head": SOURCE,
        "features": {"mcp_included": True},
        "artifacts": {"bootstrap-server.sh": {"sha256": BUNDLE}},
    }


def evidence():
    return {
        "schema_version": 1,
        "status": "PASS",
        "client_surface": "ChatGPT Plus owner/UI",
        "core_provenance_head": PROVENANCE,
        "core_source_head": SOURCE,
        "bundle_sha256": BUNDLE,
        "mcp_endpoint": "https://drlink.example.com/mcp",
        "oauth_authorization_code_consent": "PASS",
        "tool_discovery": "PASS",
        "policy_allowed_operation": "PASS",
        "policy_denied_operation": "PASS",
        "captured_at": "2026-09-28T12:00:00+09:00",
        "evidence_refs": ["owner-ui-session.txt"],
    }


class OwnerAcceptanceTests(unittest.TestCase):
    def check(self, data=None, mf=None, head=PROVENANCE):
        return MOD.validate_evidence(
            data if data is not None else evidence(),
            provenance_head=head,
            manifest=mf if mf is not None else manifest(),
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

    def test_manifest_without_mcp_rejected(self):
        mf = manifest()
        mf["features"]["mcp_included"] = False
        self.assertIn("release manifest does not include MCP", self.check(mf=mf))

    def test_evidence_refs_required(self):
        data = evidence()
        data["evidence_refs"] = []
        self.assertIn(
            "evidence_refs must contain at least one retained evidence reference",
            self.check(data),
        )

    def test_stable_projection_requires_owner_evidence_binding(self):
        release_evidence = {
            "status": "PASS",
            "pass1_head": PROVENANCE,
            "pass2_head": PROVENANCE,
            "final_qualified_head": PROVENANCE,
        }
        errs = PROJECT.evidence_errors(
            release_evidence,
            PROVENANCE,
            require_chatgpt_owner=True,
        )
        self.assertTrue(any("owner/UI acceptance" in err for err in errs), errs)
        release_evidence.update(
            {
                "chatgpt_plus_owner_ui_acceptance": "PASS",
                "chatgpt_owner_evidence_sha256": "d" * 64,
                "chatgpt_owner_evidence_provenance_head": PROVENANCE,
            }
        )
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
