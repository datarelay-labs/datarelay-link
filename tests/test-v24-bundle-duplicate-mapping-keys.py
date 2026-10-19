#!/usr/bin/env python3
"""CLI-only S-018: duplicate YAML mapping keys must fail closed.

Duplicate keys can silently discard an earlier configuration section. Both
canonical and transitional Bundle YAML ingestion must reject ambiguity before
any change plan is constructed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_configuration_bundle import BundleError, _safe_load_yaml
from drlink_v24_bundle import parse_v24_bundle


class DuplicateYamlMappingKeyTests(unittest.TestCase):
    BAD = {
        "duplicate_root": """configurationBundle:
  context: server
configurationBundle:
  context: agent
""",
        "duplicate_same_context": """configurationBundle:
  context: server
  context: server
""",
        "duplicate_conflicting_context": """configurationBundle:
  context: agent
  context: server
""",
        "duplicate_network_object_value": """configurationBundle:
  context: server
  networkObjects:
    - name: test-object
      type: ip
      value: 198.51.100.10
      value: 198.51.100.11
""",
        "duplicate_network_object_section": """configurationBundle:
  context: server
  networkObjects:
    - name: first-object
      type: ip
      value: 198.51.100.10
  networkObjects:
    - name: second-object
      type: ip
      value: 198.51.100.11
""",
        "duplicate_nested_policy_mode": """configurationBundle:
  context: server
  remoteAccess:
    mode: whitelist
    mode: blacklist
""",
        "duplicate_new_service_port": """configurationBundle:
  context: server
  serviceObjects:
    - name: ssh-test
      type: tcp
      port: 22
      port: 23
""",
    }

    def test_canonical_duplicate_keys_fail_closed(self):
        for label, document in self.BAD.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                BundleError, "duplicate|Duplicate"
            ):
                parse_v24_bundle(document)

    def test_transitional_loader_duplicate_keys_fail_closed(self):
        for label, document in self.BAD.items():
            with self.subTest(label=label), self.assertRaisesRegex(
                BundleError, "duplicate|Duplicate"
            ):
                _safe_load_yaml(document)

    def test_benign_bundle_preserved(self):
        data = parse_v24_bundle(
            "configurationBundle:\n  context: server\n"
            "  networkObjects:\n"
            "    - name: test\n"
            "      type: ip\n"
            "      value: 198.51.100.10\n"
        )
        self.assertEqual(data["context"], "server")
        self.assertEqual(data["body"]["networkObjects"][0]["value"], "198.51.100.10")

    def test_yaml_merge_explicit_override_retained(self):
        # YAML merge overrides are not repeated keys in the authored mapping.
        document = """configurationBundle:
  context: server
  networkObjects:
    - <<: &defaults
        type: ip
        value: 198.51.100.10
      name: test
      value: 198.51.100.11
"""
        result = parse_v24_bundle(document)
        self.assertEqual(result["body"]["networkObjects"][0]["type"], "ip")
        self.assertEqual(
            result["body"]["networkObjects"][0]["value"], "198.51.100.11"
        )

    def test_duplicate_error_does_not_echo_submitted_values(self):
        # PyYAML ConstructorError source snippets could leak raw values in
        # user-facing CLI output. Duplicate-key errors identify the line only.
        document = """configurationBundle:
  context: server
  remoteAccess:
    mode: sensitive-secret-alpha
    mode: sensitive-secret-beta
"""
        for loader in (parse_v24_bundle, _safe_load_yaml):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(BundleError) as cm:
                    loader(document)
                message = str(cm.exception)
                self.assertIn("duplicate YAML mapping key at line 5", message)
                self.assertNotIn("sensitive-secret-alpha", message)
                self.assertNotIn("sensitive-secret-beta", message)
                self.assertNotIn("mode:", message)

    def test_unsafe_yaml_python_tag_still_rejected(self):
        with self.assertRaises(BundleError):
            parse_v24_bundle(
                "configurationBundle:\n"
                "  context: server\n"
                "  networkObjects: !!python/object/apply:os.system ['exit 5']\n"
            )


if __name__ == "__main__":
    unittest.main()
