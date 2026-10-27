#!/usr/bin/env python3
"""Operator-selected Native MCP administration profile.

OAuth, AI Access and audit remain the Bridge's per-call responsibility. This
module provides the same general command/file capability as an Agent, running
as the locally configured OS account, with explicit opt-in for UID 0. Command
execution is administrative access, NOT a filesystem sandbox. Workspace rules
validate the initial cwd; they do not confine a shell's subsequent operations.
No settings here change the permissions of the tool used to deploy this code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import signal
import subprocess
import sys
import threading
import time
from typing import Any

LIBRARY = Path(__file__).resolve().parent
if str(LIBRARY) not in sys.path:
    sys.path.insert(0, str(LIBRARY))
from drlink_ai_agent import execute_local
from drlink_control_plane import path_allowed

WINDOW = 1024 * 1024
PAGE = 65536
MAX_JOBS = 32
FILE_ACTIONS = frozenset({"read_file", "write_file", "delete_file", "upload_file", "download_file", "list_processes"})


class FullControlDenied(Exception):
    pass


def _integer(value: Any, default: int, maximum: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise FullControlDenied("Invalid numeric execution option")
    return value


@dataclass(frozen=True)
class Account:
    name: str
    uid: int
    gid: int
    home: str
    roots: tuple[str, ...]

    def launch_options(self) -> dict:
        if os.geteuid() == 0:
            return {"user": self.uid, "group": self.gid,
                    "extra_groups": os.getgrouplist(self.name, self.gid)}
        if self.uid != os.geteuid() or self.gid != os.getegid():
            raise FullControlDenied("Bridge cannot assume the configured OS account")
        return {}

    def environment(self) -> dict[str, str]:
        # No Bridge bearer tokens or process environment inherited by commands.
        return {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME": self.home, "USER": self.name, "LOGNAME": self.name,
                "LANG": "C.UTF-8", "SHELL": "/bin/sh", "GIT_TERMINAL_PROMPT": "0"}


def configured_account() -> Account:
    required = ("DRLINK_MCP_SERVER_SELF_ENABLED", "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED",
                "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED")
    if any(os.environ.get(name) != "1" for name in required):
        raise FullControlDenied("Native full-control profile is not enabled")
    name = os.environ.get("DRLINK_MCP_SERVER_EXEC_USER", "")
    if not name:
        raise FullControlDenied("Native execution account is not configured")
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        raise FullControlDenied("Configured execution account does not exist") from None
    if entry.pw_uid == 0 and os.environ.get("DRLINK_MCP_SERVER_ADMIN_ENABLED") != "1":
        raise FullControlDenied("Administrative account requires explicit local operator opt-in")
    raw = os.environ.get("DRLINK_MCP_SERVER_ALLOWED_ROOTS", "")
    if not raw:
        raise FullControlDenied("Native allowed roots are not configured")
    roots = []
    for text in raw.split(os.pathsep):
        path = Path(text)
        if not text or not path.is_absolute() or not path.is_dir():
            raise FullControlDenied("Configured root must be an existing absolute directory")
        roots.append(str(path.resolve(strict=True)))
    account = Account(entry.pw_name, entry.pw_uid, entry.pw_gid,
                      entry.pw_dir, tuple(roots))
    account.launch_options()
    return account


def allowed_path(path: str, patterns: list[str], account: Account) -> str:
    if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
        raise FullControlDenied("An absolute path is required")
    if not path_allowed(path, patterns):
        raise FullControlDenied("Path is outside the current AI Access rule")
    canonical = str(Path(path).resolve(strict=False))
    if not any(root == "/" or canonical == root or canonical.startswith(root + "/")
               for root in account.roots):
        raise FullControlDenied("Path is outside the operator-selected roots")
    return canonical


@dataclass
class Output:
    data: bytearray = field(default_factory=bytearray)
    dropped: int = 0
    total: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, value: bytes) -> None:
        with self.lock:
            self.data.extend(value)
            self.total += len(value)
            excess = max(0, len(self.data) - WINDOW)
            if excess:
                del self.data[:excess]
                self.dropped += excess

    def page(self, cursor: int) -> dict:
        with self.lock:
            start = min(self.total, max(cursor, self.dropped))
            chunk = bytes(self.data[start - self.dropped:start - self.dropped + PAGE])
            return {"text": chunk.decode("utf-8", "replace"), "next_cursor": start + len(chunk),
                    "total_bytes": self.total, "truncated_before": self.dropped,
                    "cursor_was_evicted": cursor < self.dropped}


@dataclass
class Job:
    identifier: str
    owner: str
    account: Account
    cwd: str
    fingerprint: str
    process: subprocess.Popen
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    timed_out: bool = False
    stdout: Output = field(default_factory=Output)
    stderr: Output = field(default_factory=Output)
    done: threading.Event = field(default_factory=threading.Event)
    input_lock: threading.Lock = field(default_factory=threading.Lock)


def _drain(stream, output: Output) -> None:
    try:
        while True:
            data = stream.read(8192)
            if not data:
                break
            output.append(data)
    finally:
        stream.close()


def _terminate(job: Job) -> None:
    if job.process.poll() is None:
        try:
            os.killpg(job.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class FullControlRuntime:
    """Bounded per-Bridge job registry; job ownership is an authenticated AI id.

    The Bridge rechecks AI Access before *each* start/read/stdin/stop request.
    Jobs never accept an OS uid, account, capability or policy from the caller.
    """
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def context(self, owner: str, identifier: str) -> str:
        return self._owned(owner, identifier).cwd

    def _owned(self, owner: str, identifier: str) -> Job:
        account = configured_account()
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None or not owner or job.owner != owner or job.account != account:
                raise FullControlDenied("Job unavailable to this identity or execution profile")
            return job

    def _finish(self, job: Job, timeout: int, readers: list[threading.Thread]) -> None:
        try:
            job.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            job.timed_out = True
            _terminate(job)
            job.process.wait()
        finally:
            for reader in readers:
                reader.join(timeout=1)
            with job.input_lock:
                if job.process.stdin is not None and not job.process.stdin.closed:
                    job.process.stdin.close()
            job.finished = time.monotonic()
            job.done.set()

    def start(self, owner: str, args: dict, patterns: list[str], *, git: bool = False) -> dict:
        account = configured_account()
        if not owner:
            raise FullControlDenied("Authenticated AI identity is required")
        cwd = allowed_path(args.get("cwd") or account.home, patterns, account)
        if not Path(cwd).is_dir():
            raise FullControlDenied("Command working directory does not exist")
        argv = args.get("argv")
        command = args.get("command")
        if command is not None:
            if argv is not None or not isinstance(command, str) or not command or "\x00" in command:
                raise FullControlDenied("Supply one shell command or one argv array")
            argv = ["/bin/sh", "-c", command]
        if (not isinstance(argv, list) or not argv or len(argv) > 4096 or
                any(not isinstance(value, str) or "\x00" in value for value in argv)
                or not argv[0] or len(json.dumps(argv)) > WINDOW):
            raise FullControlDenied("Invalid command argv")
        if git and Path(argv[0]).name != "git":
            raise FullControlDenied("server_git expects a Git argv array")
        timeout = _integer(args.get("timeout_seconds"), 3600, 86400)
        if timeout == 0:
            raise FullControlDenied("A positive process timeout is required")
        wait_ms = _integer(args.get("wait_ms"), 1000, 5000)
        environment = account.environment()
        with self.lock:
            now = time.monotonic()
            expired = [key for key, value in self.jobs.items()
                       if value.finished is not None and now - value.finished > 600]
            for key in expired:
                del self.jobs[key]
            if len(self.jobs) >= MAX_JOBS:
                raise FullControlDenied("Native process limit reached; collect or stop existing jobs")
            proc = subprocess.Popen(argv, cwd=cwd, env=environment,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True,
                                    close_fds=True, **account.launch_options())
            os.set_blocking(proc.stdin.fileno(), False)
            identifier = "sj_" + secrets.token_hex(16)
            job = Job(identifier, owner, account, cwd,
                      hashlib.sha256(json.dumps(argv).encode()).hexdigest()[:16], proc)
            self.jobs[identifier] = job
        readers = [threading.Thread(target=_drain, args=(proc.stdout, job.stdout), daemon=True),
                   threading.Thread(target=_drain, args=(proc.stderr, job.stderr), daemon=True)]
        for thread in readers:
            thread.start()
        threading.Thread(target=self._finish, args=(job, timeout, readers), daemon=True).start()
        return self.poll(owner, identifier, wait_ms=wait_ms)

    def poll(self, owner: str, identifier: str, *, stdout_cursor: int = 0,
             stderr_cursor: int = 0, wait_ms: int = 0) -> dict:
        job = self._owned(owner, identifier)
        outpos = _integer(stdout_cursor, 0, 2 ** 63 - 1)
        errpos = _integer(stderr_cursor, 0, 2 ** 63 - 1)
        job.done.wait(_integer(wait_ms, 0, 5000) / 1000)
        return {"job_id": identifier, "state": "completed" if job.done.is_set() else "running",
                "exit_status": job.process.poll(), "timed_out": job.timed_out,
                "stdout": job.stdout.page(outpos), "stderr": job.stderr.page(errpos),
                "execution_user": job.account.name, "cwd": job.cwd,
                "fingerprint": job.fingerprint,
                "duration_ms": int(((job.finished or time.monotonic()) - job.started) * 1000)}

    def send(self, owner: str, identifier: str, data: str, *, eof: bool = False) -> dict:
        job = self._owned(owner, identifier)
        if not isinstance(data, str) or len(data.encode()) > PAGE or not isinstance(eof, bool):
            raise FullControlDenied("Invalid bounded process input")
        raw = data.encode("utf-8")
        with job.input_lock:
            pipe = job.process.stdin
            if pipe is None or pipe.closed or job.process.poll() is not None:
                raise FullControlDenied("Process input is closed")
            try:
                written = os.write(pipe.fileno(), raw) if raw else 0
            except BlockingIOError:
                written = 0
            except BrokenPipeError:
                raise FullControlDenied("Process input is closed") from None
            if eof and written == len(raw):
                pipe.close()
        return {"job_id": identifier, "accepted_bytes": written,
                "input_closed": pipe.closed}

    def stop(self, owner: str, identifier: str) -> dict:
        job = self._owned(owner, identifier)
        _terminate(job)
        return self.poll(owner, identifier, wait_ms=1000)

    def close(self) -> None:
        with self.lock:
            jobs = list(self.jobs.values())
        for job in jobs:
            _terminate(job)
        for job in jobs:
            job.done.wait(3)


def execute_file_action(action: str, arguments: dict, patterns: list[str]) -> dict:
    """Reuse the Agent operation implementation in the selected OS-account child."""
    account = configured_account()
    if action not in FILE_ACTIONS:
        raise FullControlDenied("Unknown Native file/process action")
    if action != "list_processes":
        allowed_path(arguments.get("path") or "", patterns, account)
    request = {"capability": action, "arguments": arguments, "patterns": patterns}
    encoded = json.dumps(request).encode("utf-8")
    if len(encoded) > 2 * WINDOW:
        raise FullControlDenied("Native file request too large")
    proc = subprocess.Popen([sys.executable, "-I", str(Path(__file__).resolve()), "--file-worker"],
                            cwd="/", env=account.environment(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, close_fds=True, **account.launch_options())
    try:
        raw, _ = proc.communicate(encoded, timeout=35)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise FullControlDenied("Native file operation timed out") from None
    if proc.returncode or len(raw) > 2 * WINDOW:
        raise FullControlDenied("Native file worker failed")
    try:
        response = json.loads(raw)
    except (ValueError, UnicodeError):
        raise FullControlDenied("Invalid Native worker response") from None
    if not isinstance(response, dict) or response.get("status") != "ok":
        raise FullControlDenied("Native file operation denied by account or path policy")
    return response["payload"]


def main() -> int:
    if sys.argv[1:] != ["--file-worker"]:
        return 2
    try:
        raw = sys.stdin.buffer.read(2 * WINDOW + 1)
        if len(raw) > 2 * WINDOW:
            raise ValueError("request too large")
        request = json.loads(raw)
        if request.get("capability") not in FILE_ACTIONS:
            raise ValueError("unsupported worker action")
        payload = execute_local(request["capability"], request["arguments"],
                                patterns=request["patterns"], timeout=30)
        response = {"status": "ok", "payload": payload}
    except Exception as exc:
        response = {"status": "denied", "error_class": type(exc).__name__}
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
