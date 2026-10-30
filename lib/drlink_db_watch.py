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
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Optional, Union

LOG = logging.getLogger("drlink.dbwatch")

DEFAULT_INTERVAL_SECONDS = 0.01


class DbChangeWatcher:
    def __init__(self, db_path: Union[str, Path], interval: float = DEFAULT_INTERVAL_SECONDS):
        self.db_path = Path(db_path)
        self.interval = max(0.002, float(interval))
        self._cond = threading.Condition()
        self._generation = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- state -------------------------------------------------------------
    @property
    def generation(self) -> int:
        with self._cond:
            return self._generation

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
            self._thread = threading.Thread(
                target=self._run, name="drlink-db-watch", daemon=True
            )
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
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

    def _bump(self) -> None:
        with self._cond:
            self._generation += 1
            self._cond.notify_all()

    def _run(self) -> None:
        conn: Optional[sqlite3.Connection] = None
        last: Optional[int] = None
        try:
            while not self._stop.is_set():
                if conn is None:
                    conn = self._open()
                    last = None
                    if conn is None:
                        self._stop.wait(max(self.interval, 0.25))
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
                    self._bump()
                last = current
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
