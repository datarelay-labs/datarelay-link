#!/usr/bin/env python3
"""DRLink Server-local MCP operations, isolated in a non-root child process.

The MCP Bridge MUST call execute_as_unprivileged_user(), not worker_dispatch()
or any file/command primitive. No arbitrary shell or sudo is exposed.
"""
from __future__ import annotations

import json
import os
import grp
from pathlib import Path
import pwd
import secrets
import shutil
import signal
import stat
import subprocess
import sys

MAX_BYTES = 1024 * 1024
MAX_OUTPUT = 65536
MAX_TIMEOUT = 30
PROTECTED_SEGMENTS = {".git", ".ssh", ".gnupg", ".aws", ".config", "secrets",
                      ".secrets", ".env", "credentials", ".credentials"}
PROTECTED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")
ALLOWED_GIT_ARGS = {
    "status": {(), ("--short",), ("--short", "--branch"), ("--porcelain=v1",)},
    "rev-parse": {("HEAD",), ("--show-toplevel",), ("--is-inside-work-tree",),
                  ("--abbrev-ref", "HEAD")},
    "diff": {("--check",), ("--stat",), ("--name-only",)},
    "log": {("-1", "--oneline"), ("-5", "--oneline"), ("--oneline", "-1")},
}


class ExecutorDenied(Exception):
    pass


def _allowed_roots() -> list[Path]:
    raw = os.environ.get("DRLINK_MCP_SERVER_ALLOWED_ROOTS", "")
    if not raw:
        raise ExecutorDenied("Server-local allowed roots are not configured")
    roots = []
    for item in raw.split(os.pathsep):
        if not item.strip() or not Path(item.strip()).is_absolute():
            raise ExecutorDenied("Allowed roots must be absolute")
        root = Path(item.strip()).resolve(strict=True)
        mode = root.stat().st_mode
        if not root.is_dir() or (mode & stat.S_IWOTH):
            raise ExecutorDenied("Unsafe allowed-root directory")
        if root not in roots:
            roots.append(root)
    if not roots:
        raise ExecutorDenied("No allowed root")
    return roots


def _locate(path: str) -> tuple[Path, tuple[str, ...]]:
    text = str(path or "")
    target = Path(text)
    if not target.is_absolute() or "\x00" in text or ".." in target.parts:
        raise ExecutorDenied("Absolute, non-traversing path required")
    for root in _allowed_roots():
        try:
            relative = target.relative_to(root)
        except ValueError:
            continue
        parts = tuple(relative.parts)
        if not parts:
            raise ExecutorDenied("A root directory is not a file")
        for segment in parts:
            lower = segment.lower()
            if (segment in (".", "..") or lower in PROTECTED_SEGMENTS
                or lower.startswith(".env") or lower.startswith("id_rsa")
                or lower.startswith("id_ed25519") or lower.endswith(PROTECTED_SUFFIXES)
                or lower.startswith("token") or lower.startswith("credential")):
                raise ExecutorDenied("Protected or sensitive file path")
        return root, parts
    raise ExecutorDenied("Path outside server-local allowed roots")


def _parent_fd(root: Path, parts: tuple[str, ...]) -> int:
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        for segment in parts[:-1]:
            next_fd = os.open(segment,
                              os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _regular_fd(parent: int, leaf: str) -> int:
    fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    mode = os.fstat(fd).st_mode
    if not stat.S_ISREG(mode):
        os.close(fd)
        raise ExecutorDenied("Not a regular file")
    return fd


def _read(path: str) -> dict:
    root, parts = _locate(path)
    parent = _parent_fd(root, parts)
    try:
        fd = _regular_fd(parent, parts[-1])
        try:
            if os.fstat(fd).st_size > MAX_BYTES:
                raise ExecutorDenied("File exceeds maximum size")
            data = os.read(fd, MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ExecutorDenied("File exceeds maximum size")
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    import base64
    return {"path": path, "bytes": len(data),
            "content_b64": base64.b64encode(data).decode("ascii")}


def _write(path: str, content: str) -> dict:
    data = str(content).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ExecutorDenied("Content exceeds maximum size")
    root, parts = _locate(path)
    parent = _parent_fd(root, parts)
    tmp = ".drlink-server-mcp-" + secrets.token_hex(12)
    try:
        mode = 0o600
        previous = None
        try:
            old_fd = _regular_fd(parent, parts[-1])
        except FileNotFoundError:
            pass
        else:
            try:
                previous = os.fstat(old_fd)
                # Replacing another account's file changes its owner; deny.
                if (previous.st_uid != os.geteuid() or previous.st_gid != os.getegid()
                        or previous.st_nlink != 1):
                    raise ExecutorDenied("File ownership or hard-link safety check failed")
                mode = stat.S_IMODE(previous.st_mode)
                if mode & 0o6000:
                    raise ExecutorDenied("Privileged file mode is not editable")
            finally:
                os.close(old_fd)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            os.fchmod(fd, mode)
            offset = 0
            while offset < len(data):
                offset += os.write(fd, data[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        if previous is not None:
            current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (previous.st_dev, previous.st_ino):
                raise ExecutorDenied("File changed while validating replacement")
        else:
            try:
                os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ExecutorDenied("File appeared before creation")
        os.replace(tmp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(tmp, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)
    return {"path": path, "bytes": len(data)}


def _delete(path: str) -> dict:
    root, parts = _locate(path)
    parent = _parent_fd(root, parts)
    try:
        fd = _regular_fd(parent, parts[-1])
        try:
            current = os.fstat(fd)
            link = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (link.st_dev, link.st_ino):
                raise ExecutorDenied("File changed while validating deletion")
            os.unlink(parts[-1], dir_fd=parent)
            os.fsync(parent)
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    return {"path": path, "deleted": True}


def _git(argv: object, cwd: str) -> dict:
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ExecutorDenied("Command must be an argv array")
    if not (2 <= len(argv) <= 5) or argv[0] != "git":
        raise ExecutorDenied("Only bounded git read-only commands are supported")
    command, flags = argv[1], tuple(argv[2:])
    if flags not in ALLOWED_GIT_ARGS.get(command, set()):
        raise ExecutorDenied("Git command or flags are not in the read-only allowlist")
    root, parts = _locate(cwd + "/.drlink-workspace-check")
    # The synthetic leaf is used only to validate the selected working directory.
    dirfd = _parent_fd(root, parts)
    try:
        # Restrict subprocess cwd to the already-open directory descriptor.
        runner_cwd = "/proc/self/fd/%d" % dirfd
        subprocess_env = {
            "PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
            "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat",
            "GIT_OPTIONAL_LOCKS": "0", "GIT_EXTERNAL_DIFF": "",
        }
        binary = shutil.which("git", path="/usr/bin:/bin")
        if not binary:
            raise ExecutorDenied("Git executable unavailable")
        # Git repository config can define executable fsmonitor / external-diff.
        # Force these hooks off even for read-only Git probes.
        safe_argv = [binary, "-c", "core.fsmonitor=false", "-c", "diff.external=",
                     command]
        if command == "diff":
            safe_argv.extend(("--no-ext-diff", "--no-textconv"))
        safe_argv.extend(flags)
        # cwd via fd pathname is resolved before close; no shell, no user env.
        proc = subprocess.Popen(safe_argv, cwd=runner_cwd,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=subprocess_env,
                                start_new_session=True, pass_fds=(dirfd,))
        try:
            out, err = proc.communicate(timeout=MAX_TIMEOUT)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise ExecutorDenied("Git command timed out")
        return {"exit_status": proc.returncode,
                "stdout": out[:MAX_OUTPUT].decode("utf-8", "replace"),
                "stderr": err[:MAX_OUTPUT].decode("utf-8", "replace"),
                "stdout_truncated": len(out) > MAX_OUTPUT,
                "stderr_truncated": len(err) > MAX_OUTPUT}
    finally:
        os.close(dirfd)


def _run_dev_test(argv: object, cwd: str) -> dict:
    """Bounded developer test execution, not a general-purpose shell.

    The MCP Bridge must separately require per-identity command-exec and an
    explicit scoped worktree path. This worker independently checks the
    operator-configured workspace roots and a non-root OS identity.
    """
    if os.environ.get("DRLINK_MCP_SERVER_DEV_TEST_ENABLED") != "1":
        raise ExecutorDenied("Development test execution is disabled")
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ExecutorDenied("Developer command requires an argv array")
    if not argv or any(
        not arg or len(arg) > 256 or "\x00" in arg or "\n" in arg or "\r" in arg
        for arg in argv
    ):
        raise ExecutorDenied("Invalid developer command argument")
    if not isinstance(cwd, str) or not cwd:
        raise ExecutorDenied("Developer command requires a working directory")
    # The synthetic leaf is solely for checking the cwd and opens no files.
    root, parts = _locate(cwd.rstrip("/") + "/.drlink-mcp-dev-command-scope")
    dirfd = _parent_fd(root, parts)
    try:
        # Only one exact standalone test script or a bounded pytest suite;
        # no bash -c, Python -c, pip install, sudo, Git writes or custom flags.
        executable = ""
        if (len(argv) == 2 and argv[0] in ("python3", "bash")
                and argv[1].startswith("tests/test-")
                and argv[1].endswith(".py" if argv[0] == "python3" else ".sh")):
            script = argv[1]
            executable = argv[0]
            child_argv = [script]
        elif (3 <= len(argv) <= 5 and argv[:3] == ["python3", "-m", "pytest"]
              and (len(argv) == 3 or argv[3] == "-q")
              and (len(argv) < 5 or (argv[4].startswith("tests/test-")
                  and argv[4].endswith(".py")))):
            executable = "python3"
            child_argv = argv[1:]
        else:
            raise ExecutorDenied("Developer command outside approved test argv")
        if len(argv) == 2 or len(argv) == 5:
            file_arg = argv[1] if len(argv) == 2 else argv[4]
            segments = Path(file_arg).parts
            if len(segments) != 2 or segments[0] != "tests" or segments[1] in (".", ".."):
                raise ExecutorDenied("Unsafe test script path")
            # Both parent and leaf are opened without following symlinks.
            test_dir = os.open("tests", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=dirfd)
            try:
                test_fd = _regular_fd(test_dir, segments[1])
                os.close(test_fd)
            finally:
                os.close(test_dir)
        binary = shutil.which(executable, path="/usr/bin:/bin")
        if not binary:
            raise ExecutorDenied("Developer test interpreter not found")
        env = {
            "PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
            "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        proc = subprocess.Popen([binary, *child_argv],
                                cwd="/proc/self/fd/%d" % dirfd, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True,
                                pass_fds=(dirfd,), close_fds=True)
        try:
            stdout, stderr = proc.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise ExecutorDenied("Developer test command timed out")
        return {
            "exit_status": proc.returncode,
            "stdout": stdout[:MAX_OUTPUT].decode("utf-8", "replace"),
            "stderr": stderr[:MAX_OUTPUT].decode("utf-8", "replace"),
            "stdout_truncated": len(stdout) > MAX_OUTPUT,
            "stderr_truncated": len(stderr) > MAX_OUTPUT,
        }
    finally:
        os.close(dirfd)


def worker_dispatch(request: dict) -> dict:
    action = str(request.get("action") or "")
    if action == "read_file":
        return _read(request.get("path") or "")
    if action == "write_file":
        return _write(request.get("path") or "", request.get("content") or "")
    if action == "delete_file":
        return _delete(request.get("path") or "")
    if action == "run_git":
        return _git(request.get("argv"), request.get("cwd") or "")
    if action == "run_dev_test":
        return _run_dev_test(request.get("argv"), request.get("cwd") or "")
    raise ExecutorDenied("Unsupported Server-local operation")


def execute_as_unprivileged_user(request: dict) -> dict:
    """Process separation; Python's Popen switches uid/gid before exec."""
    run_as = os.environ.get("DRLINK_MCP_SERVER_EXEC_USER", "")
    if not run_as or run_as in ("root", "0") or not os.environ.get("DRLINK_MCP_SERVER_ALLOWED_ROOTS"):
        raise ExecutorDenied("Server-local executor is not configured")
    try:
        entry = pwd.getpwnam(run_as)
    except KeyError:
        raise ExecutorDenied("Server-local executor account does not exist") from None
    if entry.pw_uid == 0 or entry.pw_gid == 0:
        raise ExecutorDenied("Privileged executor account is forbidden")
    if grp.getgrgid(entry.pw_gid).gr_name in {
        "root", "sudo", "wheel", "docker", "lxd", "disk", "shadow",
    }:
        raise ExecutorDenied("Privileged executor primary group is forbidden")
    sanitized = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/nonexistent",
        "DRLINK_MCP_SERVER_ALLOWED_ROOTS": os.environ["DRLINK_MCP_SERVER_ALLOWED_ROOTS"],
        "DRLINK_MCP_SERVER_DEV_TEST_ENABLED":
            "1" if os.environ.get("DRLINK_MCP_SERVER_DEV_TEST_ENABLED") == "1" else "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd="/", env=sanitized, user=entry.pw_uid, group=entry.pw_gid,
        extra_groups=[], close_fds=True, start_new_session=True,
    )
    wait_limit = 125 if request.get("action") == "run_dev_test" else MAX_TIMEOUT + 3
    try:
        out, _ = proc.communicate(json.dumps(request).encode("utf-8"), timeout=wait_limit)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise ExecutorDenied("Server-local worker timed out")
    if proc.returncode:
        raise ExecutorDenied("Server-local worker could not complete the request")
    if len(out) > MAX_BYTES * 2:
        raise ExecutorDenied("Oversized Server-local worker response")
    try:
        response = json.loads(out)
    except (ValueError, UnicodeDecodeError):
        raise ExecutorDenied("Invalid Server-local worker response") from None
    if not isinstance(response, dict) or response.get("result") != "ALLOW":
        raise ExecutorDenied(str(response.get("error") or "Server-local operation denied"))
    return dict(response.get("payload") or {})


def main() -> int:
    if sys.argv[1:] != ["--worker"]:
        return 2
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 4096)
        if len(raw) > MAX_BYTES + 2048:
            raise ExecutorDenied("Request is too large")
        req = json.loads(raw)
        if not isinstance(req, dict):
            raise ExecutorDenied("Invalid operation")
        response = {"result": "ALLOW", "payload": worker_dispatch(req)}
    except (ExecutorDenied, OSError, ValueError, TypeError) as exc:
        response = {"result": "DENY", "error": str(exc)}
    sys.stdout.write(json.dumps(response))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
