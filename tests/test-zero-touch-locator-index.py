#!/usr/bin/env python3
"""Server-side locator index; no enrollment secret or installed-service mutation."""
import importlib.util
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "allocator_locator_index", ROOT / "server/frp-port-allocator.py")
allocator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(allocator)


class LocatorIndex(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_route_and_platform(self):
        with patch.object(allocator.ZT, "new_bootstrap_locator", return_value="A3xK9mP2"):
            locator = allocator.claim_entry_locator(self.root, "a" * 16, "windows", 200, now=100)
        self.assertEqual(locator, "A3xK9mP2")
        expected = {"schema": 1, "ticket_id": "a" * 16,
                    "platform": "windows", "expires_at": 200}
        self.assertEqual(allocator.resolve_entry_locator(self.root, "/A3xK9mP2", now=100), expected)
        for bad in ("/A3xK9mP2/", "/i/A3xK9mP2", "/A3xK9mP2?platform=linux",
                    "/a3xK9mP2", "/enroll", "/A3xK9m", "/%413xK9mP2"):
            self.assertIsNone(allocator.resolve_entry_locator(self.root, bad, now=100))
        self.assertIsNone(allocator.resolve_entry_locator(self.root, "/A3xK9mP2", now=200))
        path = allocator.entry_locator_index_path(self.root, locator)
        self.assertEqual(json.loads(path.read_text()), expected)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_collision_preserves_original_even_after_expiry(self):
        with patch.object(allocator.ZT, "new_bootstrap_locator", side_effect=["A3xK9mP2", "A3xK9mP2", "B3xK9mP2"]):
            self.assertEqual(allocator.claim_entry_locator(self.root, "a" * 16, "linux", 200, now=100),
                             "A3xK9mP2")
            self.assertEqual(allocator.claim_entry_locator(self.root, "b" * 16, "macos", 400, now=300),
                             "B3xK9mP2")
        self.assertIsNone(allocator.resolve_entry_locator(self.root, "/A3xK9mP2", now=300))
        self.assertEqual(allocator.resolve_entry_locator(self.root, "/B3xK9mP2", now=300)["ticket_id"],
                         "b" * 16)

    def test_concurrent_collision_is_atomic(self):
        with patch.object(allocator.ZT, "new_bootstrap_locator", return_value="A3xK9mP2"):
            def claim(n):
                try:
                    return allocator.claim_entry_locator(self.root, "%016x" % n, "linux", 200, now=100)
                except allocator.BootstrapPathExists:
                    return None
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(claim, range(1, 9)))
        self.assertEqual(results.count("A3xK9mP2"), 1)
        self.assertEqual(results.count(None), 7)
        rec = allocator.resolve_entry_locator(self.root, "/A3xK9mP2", now=100)
        self.assertEqual(int(rec["ticket_id"], 16), results.index("A3xK9mP2") + 1)

    def test_corrupt_record_and_wrong_types_fail_closed(self):
        with patch.object(allocator.ZT, "new_bootstrap_locator", return_value="A3xK9mP2"):
            for ticket, platform, expiry in (("not-id", "linux", 200),
                                             ("a" * 16, "auto", 200),
                                             ("a" * 16, "linux", 100),
                                             ("a" * 16, "linux", True)):
                with self.assertRaises(ValueError):
                    allocator.claim_entry_locator(self.root, ticket, platform, expiry, now=100)
            allocator.claim_entry_locator(self.root, "a" * 16, "linux", 200, now=100)
        path = allocator.entry_locator_index_path(self.root, "A3xK9mP2")
        for raw in ('{', '[]', '{"schema":1}', '{"schema":1,"ticket_id":"aaaaaaaaaaaaaaaa",'
                    '"platform":"linux","expires_at":200,"bt1":"unexpected"}'):
            path.write_text(raw)
            self.assertIsNone(allocator.resolve_entry_locator(self.root, "/A3xK9mP2", now=100))

    def test_locator_never_redeemable(self):
        self.assertIsNone(allocator.parse_bootstrap_ticket("A3xK9mP2"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
