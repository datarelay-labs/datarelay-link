#!/usr/bin/env python3
"""S01: bounded catalog flag metadata for high-priority options."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Runtime preset vocabulary (lib/frp_service_profiles.py, tools/frp-client).
SUPPORTED_PRESETS = {"ssh", "http", "https", "custom"}


def load_catalog():
    path = ROOT / "lib" / "frp_cli_catalog.py"
    spec = importlib.util.spec_from_file_location("frp_cli_catalog", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_grammar():
    sys.path.insert(0, str(ROOT / "lib"))
    import frp_ctl_grammar

    return frp_ctl_grammar


class CatalogFlagMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load_catalog()

    def _flag(self, path, name):
        cmd = self.cat.find(list(path), include_aliases=True)
        self.assertIsNotNone(cmd, path)
        return next(f for f in cmd["flags"] if f["name"] == name)

    def test_retired_flag_style_service_and_internet_paths_absent(self):
        self.assertIsNone(self.cat.find(["set", "service"], include_aliases=True))
        self.assertIsNone(self.cat.find(["test", "internet"], include_aliases=True))
        grammar = load_grammar()
        for toks in (["set", "service", "--preset", "ssh"], ["test", "internet", "--protocol", "https"]):
            result = grammar.match(toks, "server")
            self.assertNotEqual(result.get("status"), "ok", result)

    def test_enrollment_ttl_role(self):
        enroll = self._flag(("set", "enrollment"), "--ttl")
        self.assertEqual(enroll.get("role"), "enrollment")
        self.assertEqual(enroll.get("type"), "duration")

    def test_older_than_metadata(self):
        flag = self._flag(("unset", "enrollment"), "--older-than")
        self.assertEqual(flag.get("type"), "integer")
        self.assertEqual(flag.get("unit"), "days")


if __name__ == "__main__":
    unittest.main()
