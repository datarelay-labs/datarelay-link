#!/usr/bin/env python3
"""AUD-21 step 2d: the Agent claim loop uses a held claim without changing defaults.

* ``AgentLoop`` keeps ``wait_ms`` 0 by default, so existing callers and tests
  send the same request as before.
* With ``wait_ms`` the request carries it and its timeout sits above the hold.
* After an empty claim the loop asks again at once only when the Server really
  held the claim; a fast empty answer (older Server, parked-claim cap) falls back
  to the idle poll so the Agent never spins.
* The production entry point opts in.

No network, service or credential is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_ai_agent as agent  # noqa: E402


class _Stop:
    """Stop event that records waits and stops the loop after ``rounds`` waits."""

    def __init__(self, rounds):
        self.rounds = rounds
        self.waits = []

    def is_set(self):
        return len(self.waits) >= self.rounds

    def wait(self, delay):
        self.waits.append(delay)
        return self.is_set()

    def set(self):
        self.rounds = 0


class AgentHeldClaimTests(unittest.TestCase):
    def test_default_request_is_unchanged(self):
        loop = agent.AgentLoop("http://x", "tok")
        self.assertEqual(loop.wait_ms, 0)
        with mock.patch.object(agent, "_agent_post", return_value={"jobs": []}) as post:
            self.assertEqual(loop._claim(), [])
        args, kwargs = post.call_args
        self.assertEqual(args[2], {"limit": 4})
        self.assertEqual(kwargs.get("timeout", 10), 10)

    def test_wait_request_carries_wait_ms_and_a_longer_timeout(self):
        loop = agent.AgentLoop("http://x", "tok", wait_ms=25000)
        with mock.patch.object(agent, "_agent_post", return_value={"jobs": []}) as post:
            loop._claim()
        args, kwargs = post.call_args
        self.assertEqual(args[2], {"limit": 4, "wait_ms": 25000})
        self.assertGreater(kwargs["timeout"], 25.0 + 5.0)

    def test_wait_ms_is_clamped(self):
        self.assertEqual(agent.AgentLoop("http://x", "t", wait_ms=10 ** 9).wait_ms, 25000)
        self.assertEqual(agent.AgentLoop("http://x", "t", wait_ms=-3).wait_ms, 0)

    def test_management_path_passes_wait_ms(self):
        import drlink_mgmt_sync as mgmt

        loop = agent.AgentLoop(agent_root="/nonexistent", wait_ms=25000)
        with mock.patch.object(mgmt, "claim_ai_jobs_on_server", return_value={"jobs": []}) as claim:
            loop._claim()
        self.assertEqual(claim.call_args.kwargs.get("wait_ms"), 25000)

    def test_library_default_can_be_switched_by_the_module_constant(self):
        with mock.patch.object(agent, "DEFAULT_CLAIM_WAIT_MS", 3000):
            self.assertEqual(agent.AgentLoop("http://x", "t").wait_ms, 3000)

    def test_next_delay_rules(self):
        held = agent.AgentLoop("http://x", "t", wait_ms=25000)
        plain = agent.AgentLoop("http://x", "t")
        # After a batch of jobs a held claim needs no pause; a plain poll keeps its short one.
        self.assertEqual(held._next_delay(1, False, 0.01), 0.0)
        self.assertEqual(plain._next_delay(1, False, 0.01), agent.AI_AGENT_BUSY_POLL_SECONDS)
        # The Server held the claim for (nearly) the whole wait: ask again at once.
        self.assertEqual(held._next_delay(0, False, 24.9), 0.0)
        # A fast empty answer is not a hold: do not spin.
        self.assertEqual(held._next_delay(0, False, 0.02), agent.AI_AGENT_IDLE_POLL_SECONDS)
        # A failed claim backs off even if it took long (timeout).
        self.assertEqual(held._next_delay(0, True, 30.0), agent.AI_AGENT_IDLE_POLL_SECONDS)
        # Without a hold the old idle poll applies.
        self.assertEqual(plain._next_delay(0, False, 0.02), agent.AI_AGENT_IDLE_POLL_SECONDS)

    def test_run_never_spins_on_fast_empty_claims(self):
        stop = _Stop(rounds=3)
        loop = agent.AgentLoop("http://x", "tok", stop_event=stop, wait_ms=25000)
        with mock.patch.object(agent, "_agent_post", return_value={"jobs": []}):
            loop.run()
        self.assertEqual(stop.waits, [agent.AI_AGENT_IDLE_POLL_SECONDS] * 3)

    def test_run_asks_again_at_once_after_a_full_hold(self):
        stop = _Stop(rounds=2)
        loop = agent.AgentLoop("http://x", "tok", stop_event=stop, wait_ms=25000)
        clock = iter([0.0, 25.0, 25.0, 50.0, 50.0, 75.0])
        with mock.patch.object(agent, "_agent_post", return_value={"jobs": []}), \
                mock.patch.object(agent.time, "monotonic", side_effect=lambda: next(clock)):
            # Two full holds: no waiting between claims, so the stop stub is
            # only consulted through is_set(); stop it after two claims.
            calls = {"n": 0}
            original = loop.run_once

            def counted():
                calls["n"] += 1
                if calls["n"] >= 2:
                    stop.rounds = 0
                    stop.waits.append(None)
                return original()

            loop.run_once = counted
            loop.run()
        self.assertGreaterEqual(calls["n"], 2)
        self.assertNotIn(agent.AI_AGENT_IDLE_POLL_SECONDS, stop.waits)

    def test_production_entry_point_opts_in(self):
        self.assertEqual(agent.AI_AGENT_CLAIM_WAIT_MS, 25000)
        created = []

        class Spy:
            def __init__(self, *a, **k):
                created.append(k)

            def run(self):
                return None

        with mock.patch.object(agent, "AgentLoop", Spy), \
                mock.patch.dict(agent.os.environ, {"DRLINK_AI_AGENT_TOKEN": ""}, clear=False):
            agent.main(["--agent-root", "/nonexistent", "--token-file", "/nonexistent/token"])
        self.assertEqual(created[0].get("wait_ms"), 25000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
