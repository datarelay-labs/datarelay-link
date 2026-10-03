#!/usr/bin/env python3
"""Anti-regression gate: forbid obsolete current product surface.

Fails when development-era ACL/profile/access/egress/help-legacy grammar
reappears in the current CLI catalog, grammar, help, menus, normative docs,
installer/package lists, or current Real E2E harnesses.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_cli_catalog as catalog  # noqa: E402
import frp_ctl_grammar as grammar  # noqa: E402

# Narrow allowlist: every entry must state why it remains.
# Valid classes: UPSTREAM_FRP_ENGINE | IMMUTABLE_HISTORICAL_FIXTURE | PRIOR_RELEASE_MIGRATION_TEST
ALLOWLIST = {
    # Prior-release upgrade fixtures may mention old filenames.
    str(ROOT / "tests" / "fixtures"): "PRIOR_RELEASE_MIGRATION_TEST: prior-release upgrade fixtures",
}

FORBIDDEN_DOC_PATTERNS = [
    r"(?m)^help legacy\s*$",
    r"(?i)use\s+`?help legacy`?",
    r"(?i)(?<!rejects top-level )(?<!rejects )\bdrlink access\b",
    r"(?i)(?<!rejects top-level )(?<!rejects )\bdrlink egress\b",
    r"(?i)^\s*set service-profile\s*$",
    r"(?i)^\s*set internet-profile\s*$",
    r"(?i)^\s*set acl\b",
    r"(?i)\bshow version\b",
    r"(?i)\bshow info\b",
    r"(?i)\bshow audit\b",
    r"(?i)\bshow upstream\b",
    r"(?i)\bshow backups\b",
]

FORBIDDEN_E2E_PATTERNS = [
    r"\bhelp legacy\b",
    r"\bdrlink show clients\b",
    r"\bdrlink show client\b",
    r"\bdrlink access\b",
    r"\bfrpctl access\b",
    r"\bdrlink egress\b",
    r"\bfrpctl egress\b",
    r"\bservice-profile\b",
    r"\binternet-profile\b",
    r"\bset acl\b",
    r"\bshow acl\b",
    r"\bsudo frp-access\b",
    r"\bsudo frp-egress\b",
    r"\bsudo frp-profile\b",
]

NORMATIVE_DOCS = [
    ROOT / "docs" / "CLI_REFERENCE.md",
    ROOT / "docs" / "PRODUCT_MASTER.md",
    ROOT / "docs" / "CONTROL_PLANE_ARCHITECTURE.md",
    ROOT / "docs" / "Data Relay Link CLI Information Architecture.md",
    ROOT / "docs" / "SECURITY.md",
    ROOT / "docs" / "INSTALLATION.md",
    ROOT / "docs" / "TROUBLESHOOTING.md",
    ROOT / "docs" / "RELEASE_CHECKLIST.md",
    ROOT / "README.md",
    ROOT / "README.ko.md",
]

CURRENT_VERSION_SURFACES = [
    ROOT / "tests" / "test-version-governance.sh",
    ROOT / "tests" / "test-frpctl-completion.sh",
    ROOT / "tests" / "human-ux-e2e" / "framework" / "state_machine.py",
    ROOT / "tests" / "human-ux-e2e" / "scenarios" / "discovery_server.py",
]

CURRENT_E2E = [
    ROOT / "tests" / "run-real-e2e.sh",
    ROOT / "tests" / "run-short-url-e2e.sh",
    ROOT / "tests" / "test-real-e2e-canonical-cli.sh",
]

DEAD_TOOLS = (
    ROOT / "tools" / "frp-access",
    ROOT / "tools" / "frp-egress",
    ROOT / "tools" / "frp-profile",
)

LEGACY_MENU_LABELS = (
    "ACLs",
    "Access Lists",
    "Service Profiles",
    "Internet Profiles",
    "Egress Profiles",
    "Profiles",
)

INSTALL_SURFACES = (
    ROOT / "install-server.sh",
    ROOT / "lib" / "server-project-files.manifest",
    ROOT / "scripts" / "build-bundles.py",
)


def _allowlisted(path: Path) -> bool:
    text = str(path)
    for prefix, reason in ALLOWLIST.items():
        if text.startswith(prefix):
            if not reason or ":" not in reason:
                raise AssertionError("unjustified allowlist entry: %s" % prefix)
            return True
    return False


class LegacyReintroductionGate(unittest.TestCase):
    def test_allowlist_entries_are_justified(self):
        for prefix, reason in ALLOWLIST.items():
            self.assertTrue(
                reason.startswith(
                    (
                        "UPSTREAM_FRP_ENGINE:",
                        "IMMUTABLE_HISTORICAL_FIXTURE:",
                        "PRIOR_RELEASE_MIGRATION_TEST:",
                    )
                ),
                "UNJUSTIFIED_LEGACY_ALLOWLIST_ENTRIES: %s -> %s" % (prefix, reason),
            )

    def test_dead_policy_tools_absent(self):
        present = [str(p.relative_to(ROOT)) for p in DEAD_TOOLS if p.exists()]
        self.assertEqual(present, [], "dead legacy tools still present: %s" % present)

    def test_install_surfaces_omit_dead_tools(self):
        bad = []
        for path in INSTALL_SURFACES:
            text = path.read_text(encoding="utf-8")
            for tool in ("tools/frp-access", "tools/frp-egress", "tools/frp-profile"):
                if tool in text:
                    bad.append("%s:%s" % (path.name, tool))
            for token in (
                "frp-access 0755",
                "frp-egress 0755",
                "frp-profile 0755",
            ):
                if token in text:
                    bad.append("%s:%s" % (path.name, token))
        self.assertEqual(bad, [], "fresh-install still packages dead tools: %s" % bad)

    def test_fresh_install_omits_obsolete_policy_json_creation(self):
        text = (ROOT / "install-server.sh").read_text(encoding="utf-8")
        # Must not initialize obsolete authority stores on fresh install.
        for needle in (
            "save_access_state(mod.empty_access_state()",
            "save_profiles_state(mod.empty_profiles_state()",
            "save_egress_state(mod.empty_egress_state()",
            "'access_control_file': '/var/lib/drlink/access-control.json'",
            "'service_profiles_file': '/var/lib/drlink/service-profiles.json'",
            '"egress_control_file": "/var/lib/drlink/egress-control.json"',
            "'egress_control_file': '/var/lib/drlink/egress-control.json'",
        ):
            self.assertNotIn(
                needle,
                text,
                "install-server still creates/configures obsolete policy JSON: %s" % needle,
            )

    def test_hidden_compat_aliases_empty(self):
        self.assertEqual(
            len(catalog.HIDDEN_COMPAT_ALIASES),
            0,
            "HIDDEN_COMPAT_ALIASES must be empty for current product surface",
        )

    def test_no_forbidden_catalog_paths(self):
        forbidden_tokens = {
            "access",
            "egress",
            "acl",
            "acls",
            "service-profile",
            "service-profiles",
            "internet-profile",
            "internet-profiles",
            "access-rule",
            "access-rules",
        }
        bad = []
        for cmd in catalog.COMMANDS:
            if any(tok in forbidden_tokens for tok in cmd["path"]):
                bad.append("/".join(cmd["path"]))
            if cmd.get("surface") in ("hidden_compat", "legacy_only"):
                bad.append("/".join(cmd["path"]) + " surface=" + cmd.get("surface"))
        self.assertEqual(bad, [], "forbidden catalog paths: %s" % bad)

    def test_mcp_tls_status_has_single_public_surface(self):
        self.assertIsNone(
            catalog.find(["show", "mcp-tls"], role="server"),
            "show mcp-tls must not duplicate system certificate status",
        )
        self.assertIsNotNone(
            catalog.find(["system", "certificate", "status"], role="server")
            or catalog.find(["system", "certificate"], role="server"),
            "system certificate status must remain discoverable",
        )
        result = grammar.match(["show", "mcp-tls"], role="server")
        self.assertEqual(result.get("status"), "error", result)
        self.assertIn("system certificate status", result.get("message") or "")

    def test_guided_menu_has_no_legacy_labels(self):
        bad = []
        for key, entries in catalog.NAVIGATION_TREE.items():
            for item in entries:
                label = item[1] if len(item) > 1 else ""
                if label in LEGACY_MENU_LABELS:
                    bad.append("%s -> %s" % (key, label))
                target = item[4] if len(item) > 4 else None
                if isinstance(target, str) and any(
                    x in target
                    for x in (
                        "show acls",
                        "show service-profiles",
                        "show internet-profiles",
                        "create_access_list",
                        "create_service_profile",
                        "create_egress_profile",
                    )
                ):
                    bad.append("%s dead-end target %s" % (key, target))
        self.assertEqual(bad, [], "guided menu legacy labels/dead-ends: %s" % bad)

    def test_grammar_rejects_obsolete_commands(self):
        samples = [
            ["help", "legacy"],
            ["access", "list"],
            ["egress", "list"],
            ["set", "service-profile", "office"],
            ["set", "internet-profile", "api"],
            ["set", "acl", "office"],
            ["show", "acls"],
            ["create", "service-profile", "x"],
            ["show", "mcp-tls"],
        ]
        for tokens in samples:
            result = grammar.match(tokens, role="server")
            self.assertEqual(
                result.get("status"),
                "error",
                "expected rejection for %s, got %s" % (tokens, result),
            )

    def test_grammar_rejects_noncanonical_root_commands(self):
        samples = [
            ["create"], ["revoke"], ["purge"], ["release"], ["update"],
            ["restore"], ["add"], ["remove"], ["delete"], ["rename"],
            ["enable"], ["disable"], ["apply"], ["discard"], ["sync"],
            ["doctor"], ["support-bundle"], ["pause"], ["resume"], ["restart"],
            ["autostart"], ["uninstall"], ["access"], ["egress"], ["history"],
            ["clear"], ["quit"], ["q"], ["status"], ["server-status"], ["version"],
            ["explain"], ["export"], ["import"], ["diff"],
        ]
        for tokens in samples:
            result = grammar.match(tokens, role="server")
            self.assertNotEqual(
                result.get("status"),
                "ok",
                "noncanonical root still executes: %s -> %s" % (tokens, result),
            )
            question = grammar.match(tokens + ["?"], role="server")
            self.assertEqual(
                question.get("status"),
                "error",
                "noncanonical root still has successful ? help: %s -> %s"
                % (tokens, question),
            )
            self.assertEqual(question.get("exit_code"), 2, (tokens, question))

    def test_hidden_dispatch_resources_are_rejected(self):
        samples = (
            (["show", "version"], "system version"),
            (["show", "info"], "system info"),
            (["show", "audit"], "system audit"),
            (["show", "upstream"], "system update check-engine"),
            (["show", "backups"], "system backup"),
            (["set", "client"], "set managed-host"),
        )
        for tokens, guidance in samples:
            result = grammar.match(tokens, role="server")
            self.assertEqual(result.get("status"), "error", (tokens, result))
            self.assertEqual(result.get("exit_code"), 2, (tokens, result))
            self.assertIn(guidance, result.get("message") or "", (tokens, result))
            question = grammar.match(tokens + ["?"], role="server")
            self.assertEqual(question.get("status"), "error", (tokens, question))
            self.assertEqual(question.get("exit_code"), 2, (tokens, question))

    def test_canonical_control_plane_still_routes(self):
        for tokens in (
            ["show", "remote-access"],
            ["set", "internet-access", "allow-api"],
            ["show", "managed-hosts"],
            ["set", "service-object", "pin", "type", "fixed-tcp", "port", "1521"],
        ):
            result = grammar.match(tokens, role="server")
            self.assertEqual(result.get("status"), "ok", tokens)
            self.assertEqual(result.get("action"), "control_plane", tokens)

    def test_normative_docs_have_no_legacy_instructions(self):
        failures = []
        for path in NORMATIVE_DOCS:
            if not path.is_file() or _allowlisted(path):
                continue
            text = path.read_text(encoding="utf-8")
            for pat in FORBIDDEN_DOC_PATTERNS:
                if re.search(pat, text):
                    failures.append("%s matches %s" % (path.name, pat))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_current_e2e_has_no_legacy_command_usage(self):
        failures = []
        for path in CURRENT_E2E:
            if not path.is_file() or _allowlisted(path):
                continue
            text = path.read_text(encoding="utf-8")
            for pat in FORBIDDEN_E2E_PATTERNS:
                if re.search(pat, text):
                    failures.append("%s matches %s" % (path.name, pat))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_current_version_surfaces_use_system_version(self):
        failures = []
        for path in CURRENT_VERSION_SURFACES:
            if not path.is_file() or _allowlisted(path):
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"(?i)\bshow version\b", text):
                failures.append("%s still references show version" % path.relative_to(ROOT))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_final_commands_json_parity(self):
        rows = json.loads((ROOT / "lib" / "frp_cli_final_commands.json").read_text())
        self.assertEqual(len(rows), len(catalog.COMMANDS))
        self.assertEqual(sum(len(row.get("aliases") or []) for row in rows), 0)
        self.assertEqual([row["path"] for row in rows if row.get("hidden")], [])
        self.assertEqual(catalog.REWRITES, {})
        for row in rows:
            self.assertNotEqual(row.get("surface"), "hidden_compat")
            self.assertNotIn(row["path"][0], ("access", "egress"))


if __name__ == "__main__":
    unittest.main()
