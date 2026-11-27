"""Bounded MCP runtime primitives with Python-owned authorization and jobs."""
from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import threading
from pathlib import Path

_PROCESS_LOCK = threading.Lock()
_PROCESS_LIBRARY = None
_PROCESS_DRAIN = None
_PROCESS_CHECKED = False
_PROCESS_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p
)


def _native_process_drain():
    global _PROCESS_LIBRARY, _PROCESS_DRAIN, _PROCESS_CHECKED
    mode = os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower()
    if mode == "python":
        return None
    if mode not in ("auto", "rust"):
        raise ValueError("DRLINK_MCP_RUNTIME must be auto, python or rust")
    with _PROCESS_LOCK:
        if _PROCESS_CHECKED:
            if _PROCESS_DRAIN is None and mode == "rust":
                raise RuntimeError("DRLINK_MCP_RUNTIME=rust but the Rust MCP runtime library is unavailable")
            return _PROCESS_DRAIN
        _PROCESS_CHECKED = True
        here = Path(__file__).resolve().parent.parent
        configured = os.environ.get("DRLINK_MCP_NATIVE_LIBRARY", "").strip()
        candidates = [Path(configured)] if configured else []
        candidates.extend((
            here / "native" / "libdrlink_mcp_runtime.so",
            here / "native" / "libdrlink_mcp_runtime.dylib",
            Path("/usr/local/lib/drlink/native/libdrlink_mcp_runtime.so"),
            Path("/usr/local/lib/drlink/native/libdrlink_mcp_runtime.dylib"),
        ))
        for candidate in candidates:
            try:
                library = ctypes.CDLL(str(candidate))
                drain = library.drlink_mcp_drain_child
                drain.argtypes = [
                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                    ctypes.c_bool, _PROCESS_CALLBACK, ctypes.c_void_p,
                ]
                drain.restype = ctypes.c_int
                _PROCESS_LIBRARY, _PROCESS_DRAIN = library, drain
                return drain
            except (OSError, AttributeError):
                continue
        if mode == "rust":
            raise RuntimeError("DRLINK_MCP_RUNTIME=rust but the Rust MCP process helper is unavailable")
        return None


def native_process_io_available() -> bool:
    return _native_process_drain() is not None


def drain_process(process, *, on_stdout, on_stderr, timeout_seconds: float = 0,
                  wait_for_eof: bool = False) -> int | None:
    """Drain captured pipes using the Rust Linux/macOS helper when present.

    Returns 0 on exit+EOF, 1 on timeout, or None when Python fallback is active.
    The child remains waitable; callers still enforce process-group policy and reap.
    """
    native = _native_process_drain()
    if native is None:
        return None
    streams = (process.stdout, process.stderr)
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
    callback_error = []

    def callback(which, data, size, _context):
        try:
            chunk = ctypes.string_at(data, size)
            (on_stdout if which == 1 else on_stderr)(chunk)
            return True
        except BaseException as exc:
            callback_error.append(exc)
            return False

    callback_ref = _PROCESS_CALLBACK(callback)
    timeout_ms = max(0, int(float(timeout_seconds) * 1000))
    result = native(
        process.pid, streams[0].fileno(), streams[1].fileno(),
        timeout_ms, bool(wait_for_eof), callback_ref, None,
    )
    if callback_error:
        raise RuntimeError("native process output callback failed") from callback_error[0]
    if result == 2:
        raise OSError("native child process wait or pipe I/O failed")
    if result == 3:
        raise RuntimeError("native child process output callback stopped")
    return result


def capture_process(process, *, input_data: bytes | None, timeout_seconds: float,
                    stdout_limit: int, stderr_limit: int):
    """Run bounded pipe capture through the native helper, or return None.

    Python owns input, timeout selection, process-group cleanup and reaping.
    Output is always drained, while only each requested prefix is retained.
    """
    if not native_process_io_available():
        return None
    limits = (max(0, int(stdout_limit)), max(0, int(stderr_limit)))
    captured = [bytearray(), bytearray()]
    totals = [0, 0]

    def append(index, chunk):
        totals[index] += len(chunk)
        available = max(0, limits[index] - len(captured[index]))
        if available:
            captured[index].extend(chunk[:available])

    writer_error = []

    def write_input():
        stream = process.stdin
        if stream is None:
            return
        try:
            if input_data:
                stream.write(input_data)
                stream.flush()
        except (BrokenPipeError, OSError) as exc:
            writer_error.append(exc)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    writer = threading.Thread(target=write_input, daemon=True) if process.stdin is not None else None
    if writer is not None:
        writer.start()
    try:
        status = drain_process(
            process, on_stdout=lambda data: append(0, data),
            on_stderr=lambda data: append(1, data), timeout_seconds=timeout_seconds,
        )
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        if writer is not None:
            writer.join(timeout=5)
        raise
    timed_out = status == 1
    try:
        # The leader remains waitable, so its process-group id is still pinned.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        drain_status = drain_process(
            process, on_stdout=lambda data: append(0, data),
            on_stderr=lambda data: append(1, data), timeout_seconds=5,
            wait_for_eof=True,
        )
        if drain_status not in (0, None):
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
    finally:
        if writer is not None:
            writer.join(timeout=5)
    if status in (2, 3):
        raise OSError("native child process lifecycle failed")
    return {
        "stdout": bytes(captured[0]), "stderr": bytes(captured[1]),
        "stdout_truncated": totals[0] > limits[0],
        "stderr_truncated": totals[1] > limits[1],
        "timed_out": timed_out, "exit_status": process.returncode,
        "input_error": bool(writer_error),
    }


class DispatchBudget:
    """Nonblocking dispatch admission, optionally backed by the Rust runtime."""

    def __init__(self, capacity: int):
        self.capacity = max(1, int(capacity))
        self._lock = threading.Lock()
        self._inflight = 0
        self._library = None
        self._handle = None
        mode = os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower()
        if mode not in ("auto", "python", "rust"):
            raise ValueError("DRLINK_MCP_RUNTIME must be auto, python or rust")
        if mode != "python":
            self._load_native(required=mode == "rust")

    def _load_native(self, *, required: bool) -> None:
        here = Path(__file__).resolve().parent.parent
        configured = os.environ.get("DRLINK_MCP_NATIVE_LIBRARY", "").strip()
        candidates = [Path(configured)] if configured else []
        candidates.extend((
            here / "native" / "libdrlink_mcp_runtime.so",
            here / "native" / "libdrlink_mcp_runtime.dylib",
            Path("/usr/local/lib/drlink/native/libdrlink_mcp_runtime.so"),
            Path("/usr/local/lib/drlink/native/libdrlink_mcp_runtime.dylib"),
        ))
        for candidate in candidates:
            try:
                library = ctypes.CDLL(str(candidate))
                create = library.drlink_mcp_budget_new
                create.argtypes = [ctypes.c_size_t]
                create.restype = ctypes.c_void_p
                acquire = library.drlink_mcp_budget_try_acquire
                acquire.argtypes = [ctypes.c_void_p]
                acquire.restype = ctypes.c_int
                release = library.drlink_mcp_budget_release
                release.argtypes = [ctypes.c_void_p]
                release.restype = None
                free = library.drlink_mcp_budget_free
                free.argtypes = [ctypes.c_void_p]
                free.restype = None
                handle = create(self.capacity)
                if not handle:
                    raise RuntimeError("Rust MCP dispatch budget rejected capacity")
                self._library, self._handle = library, handle
                return
            except (OSError, AttributeError):
                continue
        if required:
            raise RuntimeError("DRLINK_MCP_RUNTIME=rust but the Rust MCP runtime library is unavailable")

    @property
    def inflight(self) -> int:
        with self._lock:
            return self._inflight

    def try_acquire(self) -> bool:
        if self._handle:
            if not self._library.drlink_mcp_budget_try_acquire(self._handle):
                return False
            with self._lock:
                self._inflight += 1
            return True
        with self._lock:
            if self._inflight >= self.capacity:
                return False
            self._inflight += 1
            return True

    def release(self) -> None:
        if self._handle:
            self._library.drlink_mcp_budget_release(self._handle)
            with self._lock:
                if self._inflight:
                    self._inflight -= 1
            return
        with self._lock:
            if self._inflight:
                self._inflight -= 1

    def close(self) -> None:
        if self._handle:
            self._library.drlink_mcp_budget_free(self._handle)
            self._handle = None

