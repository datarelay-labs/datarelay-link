#!/usr/bin/env python3
"""AUD-21 step 2e: a Control DB change wakes only the waiters it concerns.

Step 2a woke *every* waiter on *every* commit. With about a hundred held claims
and thirty result waits that is a herd: one enqueue ran a hundred database
probes, so thirty simultaneous calls took seconds of CPU (measured: 215 waits
per call, 209 ms CPU per call).

``DbChangeWatcher.subscribe(kind, key)`` narrows the wake-up:

* ``claim`` waiters wake when a job is queued for their host.
* ``job`` waiters wake when their job reaches a terminal status.
* Everything else stays asleep until the bounded fallback poll, which keeps the
  database the source of truth: a missed signal costs latency only.

Disposable temp databases only; no service or credential is touched.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import drlink_db_watch as W  # noqa: E402


def _make_db(path):
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE ai_jobs (id TEXT PRIMARY KEY, client_id TEXT NOT NULL, "
        "status TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX ai_jobs_client_status ON ai_jobs(client_id, status)")
    return conn


class TopicWakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drlink-topic-wake-"))
        self.db = self.tmp / "control.db"
        self.writer = _make_db(self.db)
        self.watcher = W.DbChangeWatcher(self.db, interval=0.005).start()
        self.assertTrue(self.watcher.ready)

    def tearDown(self):
        self.watcher.stop()
        self.writer.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_claim_topic_wakes_only_the_host_that_got_a_job(self):
        subs = {}
        for index in range(20):
            sub = self.watcher.subscribe("claim", "host%02d" % index)
            sub.clear()
            subs[index] = sub
        try:
            self.writer.execute("INSERT INTO ai_jobs VALUES ('j1', 'host03', 'queued')")
            self.assertTrue(subs[3].wait(1.0), "the host with a queued job must wake")
            for index, sub in subs.items():
                if index != 3:
                    self.assertFalse(
                        sub.wait(0.0), "host%02d has no job and must stay asleep" % index
                    )
        finally:
            for sub in subs.values():
                sub.close()

    def test_unrelated_commits_do_not_wake_claim_waiters(self):
        sub = self.watcher.subscribe("claim", "hostA")
        sub.clear()
        try:
            for index in range(10):
                self.writer.execute(
                    "INSERT INTO ai_jobs VALUES (?, 'hostB', 'running')", ("r%d" % index,)
                )
                time.sleep(0.02)
            self.assertFalse(sub.wait(0.2))
        finally:
            sub.close()

    def test_job_topic_wakes_on_terminal_status_only(self):
        self.writer.execute("INSERT INTO ai_jobs VALUES ('j1', 'h', 'running')")
        self.writer.execute("INSERT INTO ai_jobs VALUES ('j2', 'h', 'running')")
        time.sleep(0.05)
        one = self.watcher.subscribe("job", "j1")
        two = self.watcher.subscribe("job", "j2")
        one.clear()
        two.clear()
        try:
            self.writer.execute("UPDATE ai_jobs SET status = 'done' WHERE id = 'j1'")
            self.assertTrue(one.wait(1.0), "j1 reached a terminal status")
            self.assertFalse(two.wait(0.15), "j2 is still running and must stay asleep")
            self.writer.execute("UPDATE ai_jobs SET status = 'timeout' WHERE id = 'j2'")
            self.assertTrue(two.wait(1.0))
        finally:
            one.close()
            two.close()

    def test_a_change_before_the_wait_is_not_lost(self):
        sub = self.watcher.subscribe("claim", "hostA")
        sub.clear()
        try:
            self.writer.execute("INSERT INTO ai_jobs VALUES ('j1', 'hostA', 'queued')")
            time.sleep(0.15)  # the signal arrives before the waiter sleeps
            started = time.monotonic()
            self.assertTrue(sub.wait(2.0))
            self.assertLess(time.monotonic() - started, 0.2)
        finally:
            sub.close()

    def test_wait_times_out_when_nothing_changes(self):
        sub = self.watcher.subscribe("claim", "hostA")
        sub.clear()
        try:
            started = time.monotonic()
            self.assertFalse(sub.wait(0.2))
            self.assertGreaterEqual(time.monotonic() - started, 0.15)
        finally:
            sub.close()

    def test_close_unregisters_and_stats_show_one_query_per_change(self):
        subs = [self.watcher.subscribe("claim", "host%02d" % i) for i in range(50)]
        before = dict(self.watcher.stats)
        self.writer.execute("INSERT INTO ai_jobs VALUES ('j1', 'host07', 'queued')")
        time.sleep(0.3)
        delta = self.watcher.stats["evaluations"] - before["evaluations"]
        self.assertGreaterEqual(delta, 1)
        self.assertLessEqual(delta, 3, "one commit is evaluated once, not once per waiter")
        self.assertEqual(self.watcher.stats["wakeups"] - before["wakeups"], 1)
        for sub in subs:
            sub.close()
        self.assertEqual(self.watcher.subscription_count(), 0)

    def test_stop_releases_subscribers(self):
        sub = self.watcher.subscribe("claim", "hostA")
        sub.clear()
        threading.Timer(0.1, self.watcher.stop).start()
        started = time.monotonic()
        self.assertTrue(sub.wait(3.0), "a stopping watcher wakes everyone to re-read the DB")
        self.assertLess(time.monotonic() - started, 1.0)
        sub.close()

    def test_replaced_database_file_wakes_everyone(self):
        sub = self.watcher.subscribe("job", "j1")
        sub.clear()
        try:
            self.writer.close()
            os.unlink(str(self.db))
            self.assertTrue(sub.wait(3.0), "a deleted or restored database must wake waiters")
        finally:
            sub.close()
            self.writer = sqlite3.connect(":memory:")


if __name__ == "__main__":
    unittest.main(verbosity=2)
