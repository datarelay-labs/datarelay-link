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
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import select
import signal
import socket
import socketserver
import struct
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
    default_directory: str | None = None

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


def execution_profile_status(settings: dict | None) -> dict:
    """Non-mutating readiness projection. No account/path values are returned."""
    names = {"self": "SELF_ENABLED", "local": "LOCAL_EXEC_ENABLED",
             "full": "FULL_CONTROL_ENABLED", "admin": "ADMIN_ENABLED"}
    status = {key: (None if settings is None else settings.get("DRLINK_MCP_SERVER_" + suffix) == "1")
              for key, suffix in names.items()}
    def result(readiness, reason):
        return dict(status, readiness=readiness, reason=reason)
    if settings is None:
        return result("Unknown", "Running Bridge environment not verified")
    if not status["self"]:
        return result("Disabled", "Server-self is disabled")
    if not status["local"]:
        return result("Disabled", "Server-local executor is disabled")
    name = settings.get("DRLINK_MCP_SERVER_EXEC_USER", "")
    raw = settings.get("DRLINK_MCP_SERVER_ALLOWED_ROOTS", "")
    if not name or not raw:
        return result("Not ready", "Execution account or allowed roots missing")
    try:
        account = pwd.getpwnam(name)
    except KeyError:
        return result("Not ready", "Configured execution account does not exist")
    if account.pw_uid == 0 and (not status["full"] or not status["admin"]):
        return result("Not ready", "Administrative account requires explicit local opt-in")
    try:
        if any(not p or not Path(p).is_absolute() or not Path(p).is_dir() for p in raw.split(os.pathsep)):
            return result("Not ready", "Configured root is missing or invalid")
    except OSError:
        return result("Not ready", "Configured root cannot be verified")
    return result("Configured", "Execution profile configured; effective AI Access and live operation must be verified")


def _profile_accounts(settings) -> dict:
    """Local, operator-selected accounts. Explicit maps pin the actual UID."""
    raw = settings.get("DRLINK_MCP_SERVER_EXEC_ACCOUNTS")
    if raw is None:
        name = settings.get("DRLINK_MCP_SERVER_EXEC_USER", "")
        if not name:
            raise FullControlDenied("Native execution account is not configured")
        return {name: {"uid": None, "cwd": settings.get("DRLINK_MCP_SERVER_DEFAULT_CWD") or None}}
    try:
        entries = json.loads(raw)
    except (ValueError, TypeError):
        raise FullControlDenied("Invalid local execution account profile") from None
    if not isinstance(entries, dict) or not entries or len(entries) > 128:
        raise FullControlDenied("Invalid local execution account profile")
    for name, entry in entries.items():
        if (not isinstance(name, str) or not name or not isinstance(entry, dict)
                or not {"uid"} <= set(entry) <= {"uid", "cwd"}
                or type(entry["uid"]) is not int or entry["uid"] < 0
                or ("cwd" in entry and (not isinstance(entry["cwd"], str)
                                        or not Path(entry["cwd"]).is_absolute()))):
            raise FullControlDenied("Invalid local execution account entry")
    return entries


def legacy_execution_account() -> str | None:
    # Never reinterpret an unbound legacy rule as a grant to a new account
    # map. The previous singleton must be explicitly migrated/reviewed first.
    if "DRLINK_MCP_SERVER_EXEC_ACCOUNTS" in os.environ:
        return None
    return os.environ.get("DRLINK_MCP_SERVER_EXEC_USER") or None


def configured_account(name: str | None = None) -> Account:
    required = ("DRLINK_MCP_SERVER_SELF_ENABLED", "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED",
                "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED")
    if any(os.environ.get(key) != "1" for key in required):
        raise FullControlDenied("Native full-control profile is not enabled")
    entries = _profile_accounts(os.environ)
    if name is None:
        name = legacy_execution_account()
    if name is None or name not in entries:
        raise FullControlDenied("Execution account not locally approved")
    spec = entries[name]
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        raise FullControlDenied("Configured execution account does not exist") from None
    if spec["uid"] is not None and spec["uid"] != entry.pw_uid:
        raise FullControlDenied("Configured execution account UID changed")
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
                      entry.pw_dir, tuple(roots), spec.get("cwd"))
    account.launch_options()
    return account


def eligible_accounts() -> dict[str, Account]:
    """Only locally configured, currently resolvable and launchable accounts."""
    result = {}
    for name in _profile_accounts(os.environ):
        try:
            result[name] = configured_account(name)
        except (FullControlDenied, OSError):
            continue
    return result


def default_cwd(account: Account) -> str:
    return account.default_directory or account.home


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


def allowed_cwd(path: str, patterns: list[str], account: Account) -> str:
    """Validate an initial command directory, not a file-operation operand.

    Only an explicitly filesystem-wide AI rule AND operator root permit
    resolving a directory alias. Scoped command grants and all direct file
    operations retain the existing no-symlink policy.
    """
    if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
        raise FullControlDenied("An absolute working directory is required")
    if path_allowed(path, patterns):
        canonical = allowed_path(path, patterns, account)
    elif "/**" in patterns and "/" in account.roots:
        # Do not reinterpret traversal or encoded path syntax in the fallback.
        if ".." in Path(path).parts or "%" in path:
            raise FullControlDenied("Invalid working directory path")
        try:
            canonical = str(Path(path).resolve(strict=True))
        except (OSError, RuntimeError):
            raise FullControlDenied("Working directory cannot be resolved") from None
        canonical = allowed_path(canonical, patterns, account)
    else:
        raise FullControlDenied(
            "Working directory is outside the current AI Access rule or contains "
            "a symbolic link; scoped execution requires a non-symlink path"
        )
    if not Path(canonical).is_dir():
        raise FullControlDenied("Command working directory does not exist or is not a directory")
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
            return {"text": chunk.decode("utf-8", "replace"),
                    "data_b64": base64.b64encode(chunk).decode("ascii"),
                    "next_cursor": start + len(chunk),
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
    grant_rule: str | None = None
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    timed_out: bool = False
    stdout: Output = field(default_factory=Output)
    stderr: Output = field(default_factory=Output)
    done: threading.Event = field(default_factory=threading.Event)
    input_lock: threading.Lock = field(default_factory=threading.Lock)
    lifecycle_lock: threading.Lock = field(default_factory=threading.Lock)
    readers_stop: threading.Event = field(default_factory=threading.Event)
    output_complete: bool = True


def _drain(stream, output: Output, stop: threading.Event) -> None:
    try:
        while not stop.is_set():
            # A bounded wait also permits closing an inherited pipe held by a
            # deliberately detached process after the managed group exits.
            if not select.select([stream], [], [], 0.1)[0]:
                continue
            data = os.read(stream.fileno(), 8192)
            if not data:
                break
            output.append(data)
    finally:
        stream.close()


def _terminate(job: Job, *, timeout: bool = False) -> None:
    # Only the finish worker reaps the leader. Holding its waitable PID until
    # group cleanup prevents a completed job from signaling a reused PGID.
    with job.lifecycle_lock:
        if job.process.returncode is not None:
            return
        if timeout:
            if os.waitid(os.P_PID, job.process.pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                return
            job.timed_out = True
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

    def grant_context(self, owner: str, identifier: str) -> dict:
        job = self._owned(owner, identifier)
        return {"cwd": job.cwd, "account": job.account.name, "uid": job.account.uid,
                "rule_id": job.grant_rule}

    def revoke(self, owner: str, identifier: str) -> None:
        # Internal-only cancellation, never a public authorization bypass.
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None or not owner or job.owner != owner:
                raise FullControlDenied("Job unavailable to this identity")
        if not job.done.is_set():
            _terminate(job)

    def _owned(self, owner: str, identifier: str) -> Job:
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None or not owner or job.owner != owner:
                raise FullControlDenied("Job unavailable to this identity or execution profile")
        try:
            account = configured_account(job.account.name)
            if job.account != account:
                raise FullControlDenied("Job execution profile changed")
        except (FullControlDenied, OSError):
            self.revoke(owner, identifier)
            raise FullControlDenied("Job unavailable to this identity or execution profile") from None
        return job

    def _finish(self, job: Job, timeout: int, readers: list[threading.Thread]) -> None:
        timer = threading.Timer(timeout, _terminate, args=(job,), kwargs={"timeout": True})
        timer.daemon = True
        timer.start()
        try:
            # Observe exit without reaping, then clean remaining same-group
            # descendants while the leader still pins the process-group ID.
            os.waitid(os.P_PID, job.process.pid, os.WEXITED | os.WNOWAIT)
            with job.lifecycle_lock:
                try:
                    os.killpg(job.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                job.process.wait()
        finally:
            timer.cancel()
            for reader in readers:
                reader.join(timeout=1)
            job.output_complete = not any(reader.is_alive() for reader in readers)
            job.readers_stop.set()
            for reader in readers:
                reader.join()
            with job.input_lock:
                if job.process.stdin is not None and not job.process.stdin.closed:
                    job.process.stdin.close()
            job.finished = time.monotonic()
            job.done.set()

    def start(self, owner: str, args: dict, patterns: list[str], *, git: bool = False,
              account_name: str | None = None, grant_rule: str | None = None) -> dict:
        account = configured_account(account_name)
        if not owner:
            raise FullControlDenied("Authenticated AI identity is required")
        cwd = allowed_cwd(args["cwd"] if "cwd" in args else default_cwd(account), patterns, account)
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
            # Completed output remains available until its TTL expires or the
            # bounded registry needs room. Never reclaim a live process slot.
            completed = sorted(
                ((value.finished, key) for key, value in self.jobs.items()
                 if value.done.is_set() and value.finished is not None),
            )
            while len(self.jobs) >= MAX_JOBS and completed:
                _, oldest = completed.pop(0)
                del self.jobs[oldest]
            if len(self.jobs) >= MAX_JOBS:
                raise FullControlDenied("Native process limit reached; collect or stop existing jobs")
            proc = subprocess.Popen(argv, cwd=cwd, env=environment,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True,
                                    close_fds=True, **account.launch_options())
            os.set_blocking(proc.stdin.fileno(), False)
            identifier = "sj_" + secrets.token_hex(16)
            job = Job(identifier, owner, account, cwd,
                      hashlib.sha256(json.dumps(argv).encode()).hexdigest()[:16], proc,
                      grant_rule=grant_rule)
            self.jobs[identifier] = job
        readers = [threading.Thread(target=_drain, args=(proc.stdout, job.stdout, job.readers_stop), daemon=True),
                   threading.Thread(target=_drain, args=(proc.stderr, job.stderr, job.readers_stop), daemon=True)]
        for thread in readers:
            thread.start()
        threading.Thread(target=self._finish, args=(job, timeout, readers), daemon=True).start()
        return self._snapshot(job, wait_ms=wait_ms)

    def poll(self, owner: str, identifier: str, *, stdout_cursor: int = 0,
             stderr_cursor: int = 0, wait_ms: int = 0) -> dict:
        job = self._owned(owner, identifier)
        return self._snapshot(job, stdout_cursor=stdout_cursor,
                              stderr_cursor=stderr_cursor, wait_ms=wait_ms)

    @staticmethod
    def _snapshot(job: Job, *, stdout_cursor: int = 0,
                  stderr_cursor: int = 0, wait_ms: int = 0) -> dict:
        # A command/stop already holds its authorized Job reference. History
        # reclamation must not turn an executed operation into a false DENY.
        outpos = _integer(stdout_cursor, 0, 2 ** 63 - 1)
        errpos = _integer(stderr_cursor, 0, 2 ** 63 - 1)
        job.done.wait(_integer(wait_ms, 0, 5000) / 1000)
        return {"job_id": job.identifier, "state": "completed" if job.done.is_set() else "running",
                "exit_status": job.process.returncode, "timed_out": job.timed_out,
                "output_complete": job.done.is_set() and job.output_complete,
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
            if pipe is None or pipe.closed or job.process.returncode is not None:
                raise FullControlDenied("Process input is closed")
            try:
                # <= PIPE_BUF makes a nonblocking pipe write atomic. Trim
                # only an incomplete UTF-8 suffix so accepted_bytes always
                # identifies a suffix that the string API can resend intact.
                limit = min(PAGE, os.fpathconf(pipe.fileno(), "PC_PIPE_BUF"))
                chunk = raw[:limit].decode("utf-8", "ignore").encode("utf-8")
                written = os.write(pipe.fileno(), chunk) if chunk else 0
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
        return self._snapshot(job, wait_ms=1000)

    def close(self) -> None:
        with self.lock:
            jobs = list(self.jobs.values())
        for job in jobs:
            _terminate(job)
        for job in jobs:
            job.done.wait(3)


def execute_file_action(action: str, arguments: dict, patterns: list[str],
                        *, account_name: str | None = None) -> dict:
    """Reuse the Agent operation implementation in the selected OS-account child."""
    account = configured_account(account_name)
    if action not in FILE_ACTIONS:
        raise FullControlDenied("Unknown Native file/process action")
    if not isinstance(arguments, dict):
        raise FullControlDenied("Native file arguments must be an object")
    if action in ("write_file", "upload_file") and not isinstance(arguments.get("content"), str):
        raise FullControlDenied("Native write content must be an explicitly supplied string")
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


# --- One runtime for several Bridge worker processes (AUD-21 D7) ------------------------------
#
# The jobs above are OS processes, timers and threads of ONE Bridge process, so a job started by
# worker A cannot be polled by worker B. With several workers the runtime lives in one extra
# process and the workers reach it over a private Unix socket. The worker still evaluates AI
# Access for every call; the runtime still checks job ownership itself. Same methods, same
# arguments, same FullControlDenied.

_REMOTE_METHODS = frozenset({"context", "grant_context", "revoke", "start", "poll", "send", "stop"})
_IPC_MAX_BYTES = 4 * 1024 * 1024


def _peer_is_service_user(connection: socket.socket) -> bool:
    try:
        creds = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", creds)
    except (OSError, AttributeError, struct.error):
        return False
    return uid == os.geteuid()


class _FullControlHandler(socketserver.StreamRequestHandler):
    def _reply(self, message: dict) -> None:
        try:
            self.wfile.write(json.dumps(message).encode("utf-8") + b"\n")
        except OSError:
            pass

    def handle(self) -> None:
        try:
            if not _peer_is_service_user(self.request):
                raise FullControlDenied("Peer is not the Bridge service account")
            line = self.rfile.readline(_IPC_MAX_BYTES + 1)
            if not line or len(line) > _IPC_MAX_BYTES:
                raise FullControlDenied("Invalid full-control request")
            request = json.loads(line.decode("utf-8"))
            method = request.get("method")
            if method not in _REMOTE_METHODS:
                raise FullControlDenied("Unknown full-control method")
            args = request.get("args") or []
            kwargs = request.get("kwargs") or {}
            if not isinstance(args, list) or not isinstance(kwargs, dict):
                raise FullControlDenied("Invalid full-control request")
            result = getattr(self.server.runtime, method)(*args, **kwargs)
            self._reply({"result": result})
        except FullControlDenied as exc:
            self._reply({"error": {"message": str(exc)}})
        except Exception:
            self._reply({"error": {"message": "Native full-control operation failed"}})


class _FullControlServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    request_queue_size = 64


def serve_full_control(path: str, runtime: "FullControlRuntime | None" = None) -> _FullControlServer:
    """Serve ``runtime`` on a private Unix socket in a background thread; return the server."""
    directory = os.path.dirname(os.path.abspath(path))
    info = os.stat(directory)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise FullControlDenied("The full-control socket directory must be private")
    if os.path.lexists(path):
        os.unlink(path)
    previous = os.umask(0o177)
    try:
        server = _FullControlServer(path, _FullControlHandler)
    finally:
        os.umask(previous)
    os.chmod(path, 0o600)
    server.runtime = runtime if runtime is not None else FullControlRuntime()
    thread = threading.Thread(target=server.serve_forever, name="drlink-full-control", daemon=True)
    thread.start()
    return server


class RemoteFullControlRuntime:
    """Client side of serve_full_control(); a drop-in for FullControlRuntime in a worker."""

    def __init__(self, path: str, *, timeout: float = 30.0):
        self.path = path
        self.timeout = timeout

    def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        payload = json.dumps({"method": method, "args": list(args), "kwargs": kwargs}).encode("utf-8") + b"\n"
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.path)
                connection.sendall(payload)
                chunks = []
                size = 0
                while True:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if chunk.endswith(b"\n") or size > _IPC_MAX_BYTES:
                        break
            reply = json.loads(b"".join(chunks).decode("utf-8"))
        except (OSError, ValueError):
            raise FullControlDenied("Native full-control service is unavailable") from None
        if not isinstance(reply, dict):
            raise FullControlDenied("Native full-control service is unavailable")
        error = reply.get("error")
        if error:
            raise FullControlDenied(str(error.get("message") or "Native full-control operation failed"))
        return reply.get("result")

    def context(self, owner: str, identifier: str) -> str:
        return self._call("context", owner, identifier)

    def grant_context(self, owner: str, identifier: str) -> dict:
        return self._call("grant_context", owner, identifier)

    def revoke(self, owner: str, identifier: str) -> None:
        self._call("revoke", owner, identifier)

    def start(self, owner: str, args: dict, patterns: list, *, git: bool = False,
              account_name: str | None = None, grant_rule: str | None = None) -> dict:
        return self._call("start", owner, args, patterns, git=git,
                          account_name=account_name, grant_rule=grant_rule)

    def poll(self, owner: str, identifier: str, *, stdout_cursor: int = 0,
             stderr_cursor: int = 0, wait_ms: int = 0) -> dict:
        return self._call("poll", owner, identifier, stdout_cursor=stdout_cursor,
                          stderr_cursor=stderr_cursor, wait_ms=wait_ms)

    def send(self, owner: str, identifier: str, data: str, *, eof: bool = False) -> dict:
        return self._call("send", owner, identifier, data, eof=eof)

    def stop(self, owner: str, identifier: str) -> dict:
        return self._call("stop", owner, identifier)

    def close(self) -> None:
        return None
