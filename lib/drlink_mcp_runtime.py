"""Bounded MCP runtime primitives with Python-owned authorization and jobs."""
from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

_PROCESS_LOCK = threading.Lock()
_PROCESS_LIBRARY = None
_PROCESS_DRAIN = None
_PROCESS_DRAIN_STATEFUL = False
_PROCESS_WATCH_NEW = None
_PROCESS_WATCH_FREE = None
_PROCESS_CHECKED = False
_OUTPUT_NEW = None
_OUTPUT_APPEND = None
_OUTPUT_PAGE = None
_OUTPUT_FREE = None
_OUTPUT_CHECKED = False
_WRITE_CHUNKS = None
_WRITE_CHUNKS_CHECKED = False
_READ_REQUEST_BODY = None
_READ_REQUEST_BODY_CHECKED = False
_PROCESS_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_bool, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p
)
_WRITE_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p
)
_READ_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p
)


def _native_process_drain():
    global _PROCESS_LIBRARY, _PROCESS_DRAIN, _PROCESS_DRAIN_STATEFUL, _PROCESS_WATCH_NEW, _PROCESS_WATCH_FREE, _PROCESS_CHECKED
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
                try:
                    drain = library.drlink_mcp_drain_child_stateful
                    drain.argtypes = [
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                        ctypes.c_bool, ctypes.POINTER(ctypes.c_bool), _PROCESS_CALLBACK, ctypes.c_void_p,
                    ]
                    _PROCESS_DRAIN_STATEFUL = True
                except AttributeError:
                    if sys.platform == "darwin":
                        # A legacy ABI cannot retain the one-shot NOTE_EXIT
                        # observation across retries. Skip it so auto mode
                        # falls back to Python and explicit Rust fails closed.
                        raise
                    drain = library.drlink_mcp_drain_child
                    drain.argtypes = [
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                        ctypes.c_bool, _PROCESS_CALLBACK, ctypes.c_void_p,
                    ]
                drain.restype = ctypes.c_int
                watch_new = library.drlink_mcp_process_watch_new
                watch_new.argtypes = [ctypes.c_int]
                watch_new.restype = ctypes.c_int
                watch_free = library.drlink_mcp_process_watch_free
                watch_free.argtypes = [ctypes.c_int]
                watch_free.restype = None
                _PROCESS_LIBRARY, _PROCESS_DRAIN = library, drain
                _PROCESS_WATCH_NEW, _PROCESS_WATCH_FREE = watch_new, watch_free
                return drain
            except (OSError, AttributeError):
                continue
        if mode == "rust":
            raise RuntimeError("DRLINK_MCP_RUNTIME=rust but the Rust MCP process helper is unavailable")
        return None


def native_process_io_available() -> bool:
    return _native_process_drain() is not None


def _native_output_api():
    global _OUTPUT_NEW, _OUTPUT_APPEND, _OUTPUT_PAGE, _OUTPUT_FREE, _OUTPUT_CHECKED
    mode = os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower()
    if mode == "python":
        return None
    if _OUTPUT_CHECKED:
        return _OUTPUT_NEW
    if _native_process_drain() is None:
        return None
    library = _PROCESS_LIBRARY
    try:
        create = library.drlink_mcp_output_new
        create.argtypes = [ctypes.c_size_t]
        create.restype = ctypes.c_void_p
        append = library.drlink_mcp_output_append
        append.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        append.restype = ctypes.c_int
        page = library.drlink_mcp_output_page
        page.argtypes = [
            ctypes.c_void_p, ctypes.c_uint64, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t),
            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_bool),
        ]
        page.restype = ctypes.c_int
        free = library.drlink_mcp_output_free
        free.argtypes = [ctypes.c_void_p]
        free.restype = None
    except AttributeError as exc:
        if os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower() == "rust":
            raise RuntimeError("Rust MCP runtime lacks its bounded output API") from exc
        return None
    _OUTPUT_NEW, _OUTPUT_APPEND, _OUTPUT_PAGE, _OUTPUT_FREE = create, append, page, free
    _OUTPUT_CHECKED = True
    return _OUTPUT_NEW


def native_output_new(capacity: int):
    create = _native_output_api()
    if create is None:
        return None
    handle = create(max(1, int(capacity)))
    if not handle:
        raise RuntimeError("Rust MCP runtime rejected bounded output capacity")
    return handle


def native_output_append(handle, value: bytes) -> None:
    if not handle or not value:
        return
    buffer = ctypes.create_string_buffer(value, len(value))
    if _OUTPUT_APPEND(handle, buffer, len(value)) != 1:
        raise RuntimeError("Rust MCP runtime could not append bounded output")


def native_output_page(handle, cursor: int, page_limit: int) -> dict:
    if not handle:
        raise ValueError("Rust MCP output handle is closed")
    buffer = ctypes.create_string_buffer(max(1, int(page_limit)))
    written, next_cursor = ctypes.c_size_t(), ctypes.c_uint64()
    total, dropped = ctypes.c_uint64(), ctypes.c_uint64()
    evicted = ctypes.c_bool()
    if _OUTPUT_PAGE(
        handle, max(0, int(cursor)), max(0, int(page_limit)), buffer,
        len(buffer), ctypes.byref(written), ctypes.byref(next_cursor),
        ctypes.byref(total), ctypes.byref(dropped), ctypes.byref(evicted),
    ) != 1:
        raise RuntimeError("Rust MCP runtime could not read bounded output")
    return {
        "data": buffer.raw[:written.value], "next_cursor": next_cursor.value,
        "total_bytes": total.value, "truncated_before": dropped.value,
        "cursor_was_evicted": bool(evicted.value),
    }


def native_output_free(handle) -> None:
    if handle:
        _OUTPUT_FREE(handle)


def write_mcp_response(writer, data: bytes, *, chunk_limit: int = 64 * 1024) -> None:
    """Write an HTTP-framed response body with bounded Rust chunks when loaded.

    HTTP framing, TLS, headers, and the socket remain owned by the Python
    handler. The native helper only bounds each write and retries short writes;
    a blocked Python writer naturally applies backpressure to the handler.
    """
    raw = bytes(data)
    limit = max(1, min(64 * 1024, int(chunk_limit)))
    if not raw:
        return
    if _native_process_drain() is None:
        view = memoryview(raw)
        while view:
            written = writer.write(view)
            if written is None or written <= 0 or written > len(view):
                raise OSError("MCP response writer made no valid progress")
            view = view[written:]
        return

    global _WRITE_CHUNKS, _WRITE_CHUNKS_CHECKED
    with _PROCESS_LOCK:
        if not _WRITE_CHUNKS_CHECKED:
            try:
                write_chunks = _PROCESS_LIBRARY.drlink_mcp_write_chunks
                write_chunks.argtypes = [
                    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                    _WRITE_CALLBACK, ctypes.c_void_p,
                ]
                write_chunks.restype = ctypes.c_int
                _WRITE_CHUNKS = write_chunks
            except AttributeError as exc:
                if os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower() == "rust":
                    raise RuntimeError("Rust MCP runtime lacks bounded response I/O") from exc
            _WRITE_CHUNKS_CHECKED = True
    if _WRITE_CHUNKS is None:
        # Auto mode preserves the Python fallback when an older optional
        # library lacks this additive response-write entry point.
        view = memoryview(raw)
        while view:
            written = writer.write(view)
            if written is None or written <= 0 or written > len(view):
                raise OSError("MCP response writer made no valid progress")
            view = view[written:]
        return

    callback_error = []

    def write_callback(pointer, size, _context):
        try:
            chunk = ctypes.string_at(pointer, size)
            written = writer.write(chunk)
            return -1 if written is None else int(written)
        except BaseException as exc:
            callback_error.append(exc)
            return -1

    callback = _WRITE_CALLBACK(write_callback)
    payload = ctypes.c_char_p(raw)
    result = _WRITE_CHUNKS(payload, len(raw), limit, callback, None)
    if callback_error:
        raise OSError("MCP response write callback failed") from callback_error[0]
    if result != 1:
        raise OSError("Rust MCP response write failed or stalled")


def read_mcp_request_body(reader, length: int, *, max_bytes: int = 2_000_000) -> bytes:
    """Read an already length-checked HTTP body in bounded native chunks.

    The Python HTTP/TLS stream remains the reader and JSON/authentication stay
    in Python. Rust only enforces the existing 2 MB ceiling and 64 KiB read
    chunks; older optional libraries keep the original single-read path.
    """
    size = int(length)
    limit = min(2_000_000, max(0, int(max_bytes)))
    if size < 0 or size > limit:
        raise ValueError("MCP request body exceeds the configured limit")
    if size == 0:
        return b""
    if _native_process_drain() is None:
        return reader.read(size)

    global _READ_REQUEST_BODY, _READ_REQUEST_BODY_CHECKED
    with _PROCESS_LOCK:
        if not _READ_REQUEST_BODY_CHECKED:
            try:
                read_body = _PROCESS_LIBRARY.drlink_mcp_read_request_body
                read_body.argtypes = [ctypes.c_void_p, ctypes.c_size_t, _READ_CALLBACK, ctypes.c_void_p]
                read_body.restype = ctypes.c_int
                _READ_REQUEST_BODY = read_body
            except AttributeError as exc:
                if os.environ.get("DRLINK_MCP_RUNTIME", "auto").strip().lower() == "rust":
                    raise RuntimeError("Rust MCP runtime lacks bounded request I/O") from exc
            _READ_REQUEST_BODY_CHECKED = True
    if _READ_REQUEST_BODY is None:
        return reader.read(size)

    output = ctypes.create_string_buffer(size)
    callback_error = []

    def read_callback(target, capacity, _context):
        try:
            chunk = reader.read(capacity)
            if not chunk:
                return 0
            raw = bytes(chunk)
            if len(raw) > capacity:
                return -1
            ctypes.memmove(target, raw, len(raw))
            return len(raw)
        except BaseException as exc:
            callback_error.append(exc)
            return -1

    callback = _READ_CALLBACK(read_callback)
    result = _READ_REQUEST_BODY(output, size, callback, None)
    if callback_error:
        raise OSError("MCP request body reader callback failed") from callback_error[0]
    if result != 1:
        raise OSError("MCP request body was incomplete or native read failed")
    return output.raw[:size]


def drain_process(process, *, on_stdout, on_stderr, timeout_seconds: float = 0,
                  wait_for_eof: bool = False) -> int | None:
    """Drain captured pipes using the Rust Linux/macOS helper when present.

    Returns 0 on exit+EOF, 9 on leader exit while pipes remain open, 1 on timeout,
    or None when Python fallback is active.
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
    watch_fd = getattr(process, "_drlink_mcp_process_watch_fd", None)
    if watch_fd is None:
        watch_fd = _PROCESS_WATCH_NEW(process.pid)
        if watch_fd < 0 and sys.platform == "darwin":
            raise OSError("native child process watcher creation failed")
        process._drlink_mcp_process_watch_fd = watch_fd
    try:
        if _PROCESS_DRAIN_STATEFUL:
            exited = ctypes.c_bool(getattr(process, "_drlink_mcp_leader_exited", False))
            result = native(
                process.pid, streams[0].fileno(), streams[1].fileno(), watch_fd,
                timeout_ms, bool(wait_for_eof), ctypes.byref(exited), callback_ref, None,
            )
            process._drlink_mcp_leader_exited = exited.value
        else:
            result = native(
                process.pid, streams[0].fileno(), streams[1].fileno(), watch_fd,
                timeout_ms, bool(wait_for_eof), callback_ref, None,
            )
    except BaseException:
        free_process_watch(process)
        raise
    if callback_error:
        free_process_watch(process)
        raise RuntimeError("native process output callback failed") from callback_error[0]
    if result == 2 or (result >= 4 and result != 9):
        free_process_watch(process)
        raise OSError("native child process wait or pipe I/O failed (status %s)" % result)
    if result == 3:
        free_process_watch(process)
        raise RuntimeError("native child process output callback stopped")
    # Status 0 means both pipes reached EOF. Status 9 means the leader exited
    # but descendant-held pipes still need process-group cleanup and another drain.
    if result == 0:
        free_process_watch(process)
    return result
def free_process_watch(process) -> None:
    watch_fd = getattr(process, "_drlink_mcp_process_watch_fd", None)
    if watch_fd is not None:
        _PROCESS_WATCH_FREE(watch_fd)
        del process._drlink_mcp_process_watch_fd
    if hasattr(process, "_drlink_mcp_leader_exited"):
        del process._drlink_mcp_leader_exited


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
        except PermissionError:
            # Do not hide a real process-group denial or leave the owned
            # child behind while unwinding another native-drain failure.
            try:
                process.kill()
            except OSError:
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
        free_process_watch(process)
        raise
    timed_out = status == 1
    try:
        # A completed EOF drain leaves no captured descendant holding these
        # pipes. Group cleanup is needed only after timeout or leader-exit with
        # inherited pipes still open; preserve denials on those paths.
        if status != 0:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                try:
                    process.kill()
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                for stream in (process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
                free_process_watch(process)
                raise OSError(
                    "process-group cleanup denied after native drain (status %s, returncode %s)"
                    % (status, process.returncode)
                ) from exc
        drain_status = 0
        if status != 0:
            drain_status = drain_process(
                process, on_stdout=lambda data: append(0, data),
                on_stderr=lambda data: append(1, data), timeout_seconds=5,
                wait_for_eof=True,
            )
        final_drain_incomplete = drain_status not in (0, None)
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
            free_process_watch(process)
    if status in (2, 3):
        raise OSError("native child process lifecycle failed")
    if final_drain_incomplete:
        raise OSError("native child process output capture did not reach EOF")
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
        self._required = mode == "rust"
        if mode != "python":
            self._load_native(required=self._required)

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

    def accept(self, listener_fd: int) -> int | None:
        """Accept one ready connection natively, or return None in Python mode."""
        if self._handle is None:
            return None
        accept = getattr(self._library, "drlink_mcp_accept", None)
        if accept is None:
            if not self._required:
                return None
            raise RuntimeError("Rust MCP runtime lacks bounded listener accept support")
        accept.argtypes = [ctypes.c_int]
        accept.restype = ctypes.c_int
        result = int(accept(int(listener_fd)))
        if result < 0:
            error = -result
            raise OSError(error, os.strerror(error))
        return result

    def close(self) -> None:
        if self._handle:
            self._library.drlink_mcp_budget_free(self._handle)
            self._handle = None

