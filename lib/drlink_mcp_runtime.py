"""Bounded MCP runtime primitives with Python-owned authorization and jobs."""
from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path


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

