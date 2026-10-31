#!/usr/bin/env python3
"""Wake waiters when the Control DB changes (AUD-21 step 2, design D2a).

The MCP Bridge and the management API (allocator) are separate processes that
share only the SQLite file, so an in-process event cannot tell a held claim that
a job was queued, nor tell a result wait that the Agent completed it.

``DbChangeWatcher`` polls ``PRAGMA data_version`` on a connection of its own.
SQLite changes that value whenever a *different* connection, in any process,
commits. Each change bumps ``generation`` and wakes every waiter. The database
stays the source of truth: callers re-read it after a wake-up, and fall back to
a bounded poll when no wake-up arrives, so a missed signal costs only latency.

The watcher only reads (one trivial pragma, about 100 per second at the default
interval). It never writes and never holds a transaction open.

Waking everyone on every commit does not scale: with a hundred held claims and
dozens of result waits, one enqueue made every waiter run its own database
probe. ``subscribe(kind, key)`` therefore wakes only the waiters a change
concerns, using one query per change for all of them:

* ``claim``/``<client_id>``: a job is queued for that host.
* ``job``/``<job_id>``: that job reached a terminal status.

A subscriber registers first, then looks at the database, then waits; the
watcher evaluates after each commit it notices, so a change is seen by the look
or by the wake-up. The bounded fallback poll stays with the caller.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Union

LOG = logging.getLogger("drlink.dbwatch")

DEFAULT_INTERVAL_SECONDS = 0.01
START_BASELINE_WAIT_SECONDS = 0.2
# How often the loop checks that the database file still exists (a restore or a
# deleted test root replaces or removes it).
FILE_CHECK_EVERY_SECONDS = 1.0


# Chunk size for the IN (...) lists of the per-change evaluation. SQLite's
# variable limit is 999 on old builds; stay well below it.
TOPIC_QUERY_CHUNK = 400

KIND_CLAIM = "claim"
KIND_JOB = "job"


class Subscription:
    """One waiter's interest in a topic (see ``DbChangeWatcher.subscribe``)."""

    def __init__(self, watcher: "DbChangeWatcher", kind: str, key: str):
        self.kind = kind
        self.key = key
        self._watcher = watcher
        self._event = threading.Event()
        watcher._register(self)

    def clear(self) -> None:
        """Forget earlier signals. Call before looking at the database."""
        self._event.clear()

    def wait(self, timeout: float) -> bool:
        """Block until the topic is signalled or ``timeout``; True if signalled."""
        return self._event.wait(max(0.0, float(timeout)))

    def close(self) -> None:
        self._watcher._unregister(self)

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class DbChangeWatcher:
    def __init__(self, db_path: Union[str, Path], interval: float = DEFAULT_INTERVAL_SECONDS):
        self.db_path = Path(db_path)
        self.interval = max(0.002, float(interval))
        self._cond = threading.Condition()
        self._generation = 0
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._topic_lock = threading.Lock()
        self._topics: Dict[tuple, list] = {}
        # Counters for tests and metrics: evaluations = per-change topic queries,
        # wakeups = subscriber signals sent by them.
        self.stats = {"evaluations": 0, "wakeups": 0}

    # -- state -------------------------------------------------------------
    @property
    def generation(self) -> int:
        with self._cond:
            return self._generation

    @property
    def ready(self) -> bool:
        """True once a baseline was read, so a commit can no longer go unnoticed.

        Callers that need millisecond wake-ups use ``wait`` only when this is
        true and otherwise keep their own short poll (missing or in-memory
        database, watcher not started yet).
        """
        return self._ready.is_set() and self.running

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive() and not self._stop.is_set())

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> "DbChangeWatcher":
        with self._cond:
            if self._thread and self._thread.is_alive():
                return self
            self._stop.clear()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run, name="drlink-db-watch", daemon=True
            )
            self._thread.start()
        # Let the first baseline be taken before the caller looks at the database,
        # so a commit right after start() is seen. Bounded: a missing database
        # simply leaves the watcher not ready.
        self._ready.wait(START_BASELINE_WAIT_SECONDS)
        return self

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        self._wake_all_topics()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(2.0)

    # -- waiting -----------------------------------------------------------
    def wait(self, since_generation: int, timeout: float) -> int:
        """Block until ``generation`` exceeds ``since_generation`` or ``timeout``.

        Returns the generation at return. A caller that was too slow to call
        ``wait`` before a change still returns immediately, because the
        generation it passed is already behind.
        """
        deadline_wait = max(0.0, float(timeout))
        with self._cond:
            if self._generation > since_generation or self._stop.is_set():
                return self._generation
            self._cond.wait_for(
                lambda: self._generation > since_generation or self._stop.is_set(),
                timeout=deadline_wait,
            )
            return self._generation

    # -- topics ------------------------------------------------------------
    def subscribe(self, kind: str, key: str) -> Subscription:
        """Register for wake-ups about ``key``. Register BEFORE looking at the DB."""
        return Subscription(self, str(kind), str(key))

    def subscription_count(self) -> int:
        with self._topic_lock:
            return sum(len(subs) for subs in self._topics.values())

    def _register(self, sub: Subscription) -> None:
        with self._topic_lock:
            self._topics.setdefault((sub.kind, sub.key), []).append(sub)

    def _unregister(self, sub: Subscription) -> None:
        with self._topic_lock:
            subs = self._topics.get((sub.kind, sub.key))
            if not subs:
                return
            try:
                subs.remove(sub)
            except ValueError:
                pass
            if not subs:
                self._topics.pop((sub.kind, sub.key), None)

    def _wake_all_topics(self) -> None:
        with self._topic_lock:
            everyone = [sub for subs in self._topics.values() for sub in subs]
        for sub in everyone:
            sub._event.set()

    def _wake_topics(self, topics) -> None:
        woken = []
        with self._topic_lock:
            for topic in topics:
                woken.extend(self._topics.get(topic, ()))
        for sub in woken:
            sub._event.set()
        self.stats["wakeups"] += len(woken)

    def _dispatch_topics(self, conn: sqlite3.Connection) -> None:
        """After a change: one query per topic kind for ALL subscribers."""
        with self._topic_lock:
            claim_keys = [key for (kind, key) in self._topics if kind == KIND_CLAIM]
            job_keys = [key for (kind, key) in self._topics if kind == KIND_JOB]
        if not claim_keys and not job_keys:
            return
        self.stats["evaluations"] += 1
        topics = []
        try:
            for start in range(0, len(claim_keys), TOPIC_QUERY_CHUNK):
                chunk = claim_keys[start:start + TOPIC_QUERY_CHUNK]
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                    "SELECT DISTINCT client_id FROM ai_jobs WHERE status = 'queued' "
                    "AND client_id IN (%s)" % marks,
                    chunk,
                ):
                    topics.append((KIND_CLAIM, row[0]))
            for start in range(0, len(job_keys), TOPIC_QUERY_CHUNK):
                chunk = job_keys[start:start + TOPIC_QUERY_CHUNK]
                marks = ",".join("?" * len(chunk))
                for row in conn.execute(
                    "SELECT id FROM ai_jobs WHERE id IN (%s) "
                    "AND status NOT IN ('queued', 'running')" % marks,
                    chunk,
                ):
                    topics.append((KIND_JOB, row[0]))
        except sqlite3.Error:
            # Schema not ready or file busy: let everyone re-read the database.
            self._wake_all_topics()
            return
        self._wake_topics(topics)

    # -- poll loop ---------------------------------------------------------
    def _open(self) -> Optional[sqlite3.Connection]:
        try:
            if not self.db_path.exists():
                return None
            conn = sqlite3.connect(
                "file:%s" % self.db_path,
                uri=True,
                isolation_level=None,
                timeout=1.0,
                check_same_thread=False,
            )
            conn.execute("PRAGMA busy_timeout = 1000")
            return conn
        except sqlite3.Error:
            return None

    @staticmethod
    def _data_version(conn: sqlite3.Connection) -> int:
        return int(conn.execute("PRAGMA data_version").fetchone()[0])

    def _bump(self, wake_topics: bool = True) -> None:
        with self._cond:
            self._generation += 1
            self._cond.notify_all()
        if wake_topics:
            # Abnormal path (file replaced or unreadable): nothing can be
            # assumed, every subscriber re-reads the database.
            self._wake_all_topics()

    def _run(self) -> None:
        conn: Optional[sqlite3.Connection] = None
        last: Optional[int] = None
        next_file_check = 0.0
        try:
            while not self._stop.is_set():
                if conn is None:
                    conn = self._open()
                    last = None
                    if conn is None:
                        self._ready.clear()
                        self._stop.wait(max(self.interval, 0.25))
                        continue
                now = time.monotonic()
                if now >= next_file_check:
                    next_file_check = now + FILE_CHECK_EVERY_SECONDS
                    if not self.db_path.exists():
                        try:
                            conn.close()
                        except sqlite3.Error:
                            pass
                        conn = None
                        self._ready.clear()
                        self._bump()
                        continue
                try:
                    current = self._data_version(conn)
                except sqlite3.Error:
                    # The file was replaced (restore) or is momentarily
                    # unreadable: reopen and treat it as a change so waiters
                    # re-read the database.
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass
                    conn = None
                    self._bump()
                    self._stop.wait(self.interval)
                    continue
                if last is not None and current != last:
                    self._bump(wake_topics=False)
                    self._dispatch_topics(conn)
                last = current
                self._ready.set()
                self._stop.wait(self.interval)
        except Exception:  # pragma: no cover - last-resort guard, never kill the process
            LOG.exception("DbChangeWatcher stopped unexpectedly")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            # Release anyone still waiting so they fall back to a database read.
            self._stop.set()
            with self._cond:
                self._cond.notify_all()
            self._wake_all_topics()


_REGISTRY: Dict[str, DbChangeWatcher] = {}
_REGISTRY_LOCK = threading.Lock()


def get_watcher(db_path: Union[str, Path], interval: float = DEFAULT_INTERVAL_SECONDS) -> DbChangeWatcher:
    """Return the process-wide watcher for ``db_path``, starting it on first use."""
    key = str(Path(db_path))
    with _REGISTRY_LOCK:
        watcher = _REGISTRY.get(key)
        if watcher is None or not watcher.running:
            watcher = DbChangeWatcher(key, interval=interval)
            _REGISTRY[key] = watcher
            watcher.start()
        return watcher
