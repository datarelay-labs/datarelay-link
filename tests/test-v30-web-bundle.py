#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import importlib.util
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "drlink_build_web_bundle", ROOT / "scripts/build-web-bundle.py"
)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)

class V30WebBundleTests(unittest.TestCase):
    def test_bundle_is_deterministic_and_matches_declared_files(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-web-bundle-"))
        first = tmp / "one.tar.gz"
        second = tmp / "two.tar.gz"
        MOD.build(first)
        MOD.build(second)
        self.assertEqual(
            hashlib.sha256(first.read_bytes()).hexdigest(),
            hashlib.sha256(second.read_bytes()).hexdigest(),
        )
        with tarfile.open(first, "r:gz") as tf:
            names = set(tf.getnames())
        self.assertEqual(names, {"data-relay-link-web/" + name for name in MOD.FILES})

    def test_bundle_contains_compiled_static_assets_only_for_runtime_ui(self):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-web-static-"))
        bundle = MOD.build(tmp / "web.tar.gz")
        with tarfile.open(bundle, "r:gz") as tf:
            names = set(tf.getnames())
        self.assertIn("data-relay-link-web/web/dist/index.html", names)
        self.assertIn("data-relay-link-web/web/dist/app.js", names)
        self.assertIn("data-relay-link-web/web/dist/styles.css", names)
        self.assertIn("data-relay-link-web/web/dist/foundation.css", names)
        self.assertIn("data-relay-link-web/web/foundation.lock.json", names)
        self.assertIn("data-relay-link-web/web/.foundation/packs/datarelay-labs-foundation-0.1.0-pf5b.1.tgz", names)
        self.assertNotIn("data-relay-link-web/var/lib/drlink/drlink.db", names)

if __name__ == "__main__":
    unittest.main()
