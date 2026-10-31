#!/usr/bin/env python3
"""AUD-21 step 2: DbChangeWatcher wakes waiters when ANY connection commits.

The MCP Bridge and the management API (allocator) are separate processes that
share only the SQLite file, so a held claim or a result wait cannot rely on an
in-process event. The watcher polls PRAGMA data_version on a connection of its
own and wakes waiters when another connection, in any process, committed.

Disposable temp roots only; no service or credential is touched.
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_db_watch import DbChangeWatcher  # noqa: E402


def _make_db(directory: Path) -> Path:
    path = directory / "w.db"
    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.close()
    return path


class DbChangeWatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="drlink-watch-"))
        self.db = _make_db(self.tmp)
        self.watcher = DbChangeWatcher(self.db, interval=0.01)
        self.watcher.start()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self.watcher.stop)

    def _commit_later(self, delay: float, value: str = "x") -> threading.Thread:
        def run():
            time.sleep(delay)
            conn = sqlite3.connect(str(self.db), isolation_level=None)
            conn.execute("INSERT INTO t (v) VALUES (?)", (value,))
            conn.close()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return t

    def test_wakes_on_commit_from_another_connection(self):
        gen = self.watcher.generation
        self._commit_later(0.15)
        started = time.monotonic()
        new_gen = self.watcher.wait(gen, timeout=3.0)
        elapsed = time.monotonic() - started
        self.assertGreater(new_gen, gen)
        self.assertGreaterEqual(elapsed, 0.1)
        self.assertLess(elapsed, 0.5, "wake-up must follow the commit within milliseconds")

    def test_wakes_on_commit_from_another_process(self):
        gen = self.watcher.generation
        code = (
            "import sqlite3,sys,time;time.sleep(0.2);"
            "c=sqlite3.connect(sys.argv[1],isolation_level=None);"
            "c.execute(\"INSERT INTO t (v) VALUES ('p')\");c.close()"
        )
        proc = subprocess.Popen([sys.executable, "-c", code, str(self.db)])
        self.addCleanup(proc.wait)
        started = time.monotonic()
        new_gen = self.watcher.wait(gen, timeout=5.0)
        self.assertGreater(new_gen, gen)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_timeout_returns_unchanged_generation(self):
        gen = self.watcher.generation
        started = time.monotonic()
        self.assertEqual(self.watcher.wait(gen, timeout=0.2), gen)
        self.assertGreaterEqual(time.monotonic() - started, 0.15)

    def test_missed_signal_returns_immediately(self):
        gen = self.watcher.generation
        self._commit_later(0.0).join()
        deadline = time.monotonic() + 2.0
        while self.watcher.generation == gen and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreater(self.watcher.generation, gen)
        started = time.monotonic()
        self.assertGreater(self.watcher.wait(gen, timeout=5.0), gen)
        self.assertLess(time.monotonic() - started, 0.05)

    def test_many_waiters_all_wake(self):
        gen = self.watcher.generation
        results = []
        lock = threading.Lock()

        def waiter():
            value = self.watcher.wait(gen, timeout=3.0)
            with lock:
                results.append(value)

        threads = [threading.Thread(target=waiter, daemon=True) for _ in range(40)]
        for t in threads:
            t.start()
        self._commit_later(0.2)
        for t in threads:
            t.join(3.0)
        self.assertEqual(len(results), 40)
        self.assertTrue(all(r > gen for r in results))

    def test_stop_wakes_waiters_and_ends_thread(self):
        gen = self.watcher.generation
        out = []
        t = threading.Thread(target=lambda: out.append(self.watcher.wait(gen, timeout=10.0)), daemon=True)
        t.start()
        time.sleep(0.1)
        started = time.monotonic()
        self.watcher.stop()
        t.join(2.0)
        self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertFalse(self.watcher.running)

    def test_watcher_never_writes_to_the_database(self):
        before = self.db.stat().st_mtime_ns
        time.sleep(0.2)
        conn = sqlite3.connect(str(self.db))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 0)
        conn.close()
        self.assertEqual(self.db.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
