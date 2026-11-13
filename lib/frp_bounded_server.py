#!/usr/bin/env python3
"""Bounded ThreadingMixIn — acquire concurrency slot BEFORE spawning a worker.

ThreadingHTTPServer / ThreadingTCPServer spawn a thread in process_request()
before the handler runs. A semaphore taken inside do_GET/do_POST therefore
does not bound thread creation.

Use BoundedThreadingMixIn (or wrap process_request) so the limit is real.
"""
from __future__ import annotations

import contextlib
import socket
import threading
from typing import Iterator, Optional

# The server whose worker thread is running this request (None outside one).
_current = threading.local()

# Held requests (long-poll claims) that wait without a request slot are capped
# separately; above the cap the caller must answer immediately instead.
DEFAULT_MAX_PARKED = 128


class BoundedThreadingMixIn:
    """ThreadingMixIn variant with an accept-time concurrency gate.

    Subclasses must set:
      - max_concurrent: int
      - request_timeout: float (idle/read timeout applied to accepted sockets)

    Optional:
      - reject_callback(request, client_address) for overload response
      - prepare_request(request, client_address) -> socket: wrap/handshake in
        the worker thread before finish_request (keeps accept() non-blocking)
    """

    daemon_threads = True
    block_on_close = False
    max_concurrent = 32
    max_parked = DEFAULT_MAX_PARKED
    request_timeout = 30.0
    reject_callback = None

    def __init__(self, *args, **kwargs):
        self._slot_sem = threading.BoundedSemaphore(int(self.max_concurrent))
        self._parked_lock = threading.Lock()
        self._parked = 0
        super().__init__(*args, **kwargs)

    def _try_park(self) -> bool:
        """Count one parked request; refuse above ``max_parked``."""
        with self._parked_lock:
            if self._parked >= int(self.max_parked):
                return False
            self._parked += 1
            return True

    def _unpark(self) -> None:
        with self._parked_lock:
            self._parked = max(0, self._parked - 1)

    def prepare_request(self, request, client_address):
        """Optional hook: transform the accepted socket in the worker thread."""
        del client_address
        return request

    def process_request(self, request, client_address):
        # Apply idle/read timeout before any worker starts. prepare_request may
        # tighten this further (e.g. short TLS handshake deadline).
        try:
            request.settimeout(float(self.request_timeout))
        except (OSError, AttributeError):
            pass
        acquired = self._slot_sem.acquire(blocking=False)
        if not acquired:
            try:
                cb = getattr(self, "reject_callback", None)
                if callable(cb):
                    cb(request, client_address)
            except Exception:
                pass
            try:
                request.close()
            except OSError:
                pass
            return

        def run():
            sock = request
            _current.server = self
            try:
                try:
                    sock = self.prepare_request(request, client_address)
                except Exception:
                    close_quietly(request)
                    if sock is not request:
                        close_quietly(sock)
                    return
                try:
                    self.finish_request(sock, client_address)
                except Exception:
                    try:
                        self.handle_error(sock, client_address)
                    finally:
                        try:
                            self.shutdown_request(sock)
                        except Exception:
                            pass
                else:
                    try:
                        self.shutdown_request(sock)
                    except Exception:
                        pass
            finally:
                _current.server = None
                self._slot_sem.release()

        t = threading.Thread(target=run)
        t.daemon = self.daemon_threads
        try:
            t.start()
        except Exception:
            # run() never executes, so its finally-release never happens: give
            # the slot back here or capacity shrinks permanently.
            try:
                self._slot_sem.release()
            except ValueError:
                pass
            close_quietly(request)
            return


@contextlib.contextmanager
def parked_slot() -> Iterator[bool]:
    """Give this request's concurrency slot back while the caller waits.

    A held claim can wait up to 25 s. With 100 Agents that would use every one
    of the 32 slots and block ``complete`` and enrollment, so the waiting
    request parks: its slot is released for the wait and taken again (blocking)
    before the caller touches the database. Yields ``True`` when parked, and
    ``False`` when the parked-request cap is reached: the caller then answers
    immediately instead of waiting. Outside a bounded server (tests, in-process
    listeners) there is no slot to give back and the wait is free: yields ``True``.
    """
    server = getattr(_current, "server", None)
    if server is None:
        yield True
        return
    if not server._try_park():
        yield False
        return
    server._slot_sem.release()
    try:
        yield True
    finally:
        # Take the slot again before the caller continues. run()'s final
        # release then matches this acquire, so the count stays exact.
        server._slot_sem.acquire()
        server._unpark()


def close_quietly(sock: Optional[socket.socket]) -> None:
    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass
