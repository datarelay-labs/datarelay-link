#!/usr/bin/env python3
"""AUD-21: MCP Bridge must not answer JSON-RPC -32603 under concurrent calls.

Field symptom (dev-drlink / DR_Link MCP): `exec` against a Managed Host
intermittently returns `-32603 internal error`; about 1 of 6 simultaneous calls
failed while sequential calls and a burst of 3 succeeded. The bridge catches
every non-ControlPlaneError exception in `tools/call`, so the real exception is
not visible. This test pins the externally visible contract: a burst of
simultaneous, individually valid `exec` calls must all complete with a normal
result and none may be turned into `internal error`.

It reuses the existing bridge harness (real ControlPlane, real HTTP server,
real AgentLoop workers) in a disposable temp root. No service, credential or
production state is touched.
"""
from __future__ import annotations

import importlib.util
import sys
import threading
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "tests"))


def _load_e2e_harness():
    path = ROOT / "tests" / "test-ai-access-mcp-e2e.py"
    spec = importlib.util.spec_from_file_location("ai_access_mcp_e2e_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_E2E = _load_e2e_harness()
INTERNAL_ERROR = -32603


class MCPBridgeConcurrentCallTests(unittest.TestCase):
    # Borrow the harness plumbing without inheriting (and re-running) its tests.
    setUp = _E2E.MCPBridgeE2ETests.setUp
    tearDown = _E2E.MCPBridgeE2ETests.tearDown
    _token = _E2E.MCPBridgeE2ETests._token
    call = _E2E.MCPBridgeE2ETests.call
    text_of = _E2E.MCPBridgeE2ETests.text_of

    THREADS = 12
    ROUNDS = 4

    def _burst(self, endpoint):
        """Release THREADS simultaneous exec calls per round, ROUNDS times."""
        results = []
        guard = threading.Lock()
        barrier = threading.Barrier(self.THREADS)

        def worker(index):
            for rnd in range(self.ROUNDS):
                try:
                    barrier.wait(timeout=60)
                    marker = "burst-%d-%d" % (index, rnd)
                    status, payload = self.call(
                        self.cursor,
                        "exec",
                        {"endpoint": endpoint, "command": "echo %s" % marker},
                        req_id=index * 1000 + rnd,
                    )
                    outcome = (marker, status, payload)
                except Exception as exc:  # transport failure is also a failure
                    outcome = ("%d-%d" % (index, rnd), None, {"transport_error": type(exc).__name__})
                with guard:
                    results.append(outcome)

        threads = [
            threading.Thread(target=worker, args=(i,), name="burst-%d" % i, daemon=True)
            for i in range(self.THREADS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=180)
        return results

    def test_concurrent_exec_never_returns_internal_error(self):
        results = self._burst("lab1")
        self.assertEqual(len(results), self.THREADS * self.ROUNDS, "burst did not finish")

        internal = [r for r in results
                    if isinstance(r[2], dict) and (r[2].get("error") or {}).get("code") == INTERNAL_ERROR]
        transport = [r for r in results if isinstance(r[2], dict) and "transport_error" in r[2]]
        shapes = Counter(
            "error:%s" % (r[2].get("error") or {}).get("code") if r[2].get("error")
            else "result" for r in results if isinstance(r[2], dict)
        )
        self.assertEqual(
            (len(internal), len(transport)),
            (0, 0),
            "concurrent exec produced %d internal error(s) and %d transport error(s) "
            "out of %d calls; outcome shapes=%s"
            % (len(internal), len(transport), len(results), dict(shapes)),
        )
        for marker, status, payload in results:
            self.assertEqual(status, 200, marker)
            self.assertIn(marker, self.text_of(payload), "call %s lost its own output" % marker)


if __name__ == "__main__":
    unittest.main()
