#!/usr/bin/env python3
"""Endpoint-side AI operation executor with fail-closed path and exec safety.

This module is installed on Data Relay Link clients. It is not an MCP server.
The server-side MCP Bridge dispatches authorized jobs here over the agent RPC.
"""
from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from datetime import datetime, timezone

from drlink_control_plane import ControlPlaneError, path_allowed, validate_safe_path


def _deadline_passed(deadline_at: Optional[str]) -> bool:
    text = str(deadline_at or "").strip()
    if not text:
        return False
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        deadline = datetime.fromisoformat(text)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return now >= deadline

MAX_STDOUT_BYTES = 64 * 1024
MAX_STDERR_BYTES = 16 * 1024
MAX_FILE_BYTES = 1024 * 1024
DEFAULT_EXEC_TIMEOUT = 30


def _bound(data: bytes, limit: int) -> tuple[bytes, bool]:
    if data is None:
        return b"", False
    if len(data) <= limit:
        return data, False
    return data[:limit], True


def _is_unsafe_file(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    if stat.S_ISDIR(mode) or stat.S_ISREG(mode):
        return False
    return True


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def read_file(path: str, patterns: list[str]) -> dict:
    resolved = validate_safe_path(path, patterns)
    if resolved.is_symlink() or Path(path).is_symlink():
        raise ControlPlaneError("symlink escape denied")
    if _is_unsafe_file(resolved):
        raise ControlPlaneError("special file denied")
    if not resolved.is_file():
        raise ControlPlaneError("not a regular file")
    size = resolved.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ControlPlaneError("file too large")
    data = resolved.read_bytes()
    text, truncated = _bound(data, MAX_FILE_BYTES)
    return {"path": str(resolved), "bytes": len(text), "truncated": truncated, "content_b64": _b64(text)}


def write_file(path: str, content: bytes, patterns: list[str]) -> dict:
    if len(content) > MAX_FILE_BYTES:
        raise ControlPlaneError("payload too large")
    raw = Path(path)
    decoded_ok = path_allowed(str(path), patterns)
    if not decoded_ok:
        # New files: parent must be in scope after canonicalization.
        parent = Path(os.path.realpath(str(raw.parent)))
        if not path_allowed(str(parent / raw.name), patterns) and not path_allowed(str(parent), patterns):
            raise ControlPlaneError("path is outside allowed scope")
    dest_dir = Path(os.path.realpath(str(raw.parent)))
    dest_dir.mkdir(parents=True, exist_ok=True)
    if dest_dir.is_symlink():
        raise ControlPlaneError("symlink escape denied")
    tmp = dest_dir / (".drlink-ai-" + raw.name + ".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(str(tmp), flags, 0o600)
    try:
        os.write(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)
    dest = dest_dir / raw.name
    if dest.exists() or dest.is_symlink():
        try:
            st = dest.lstat()
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
                os.unlink(str(tmp))
                raise ControlPlaneError("unsafe overwrite denied")
        except FileNotFoundError:
            pass
    os.replace(str(tmp), str(dest))
    final = Path(os.path.realpath(str(dest)))
    if final.is_symlink() or not path_allowed(str(final), patterns):
        try:
            final.unlink()
        except OSError:
            pass
        raise ControlPlaneError("path is outside allowed scope")
    return {"path": str(final), "bytes": len(content)}


def delete_file(path: str, patterns: list[str]) -> dict:
    resolved = validate_safe_path(path, patterns, must_exist=True)
    raw = Path(path)
    if raw.is_symlink() or resolved.is_symlink():
        raise ControlPlaneError("symlink escape denied")
    if _is_unsafe_file(resolved) or not resolved.is_file():
        raise ControlPlaneError("not a regular file")
    resolved.unlink()
    return {"path": str(resolved), "deleted": True}


def exec_command(command: str, timeout: int) -> dict:
    timeout = int(timeout or DEFAULT_EXEC_TIMEOUT)
    if timeout < 1:
        timeout = 1
    start = time.monotonic()
    proc = subprocess.Popen(
        ["/bin/sh", "-c", command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    result = "ALLOW"
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            proc.kill()
        stdout, stderr = proc.communicate()
        code = -9
        result = "TIMEOUT"
    duration_ms = int((time.monotonic() - start) * 1000)
    out, out_trunc = _bound(stdout or b"", MAX_STDOUT_BYTES)
    err, err_trunc = _bound(stderr or b"", MAX_STDERR_BYTES)
    return {
        "result": result if result == "TIMEOUT" else "ALLOW",
        "exit_status": code,
        "duration_ms": duration_ms,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
        "stdout_truncated": out_trunc,
        "stderr_truncated": err_trunc,
        "fingerprint": _fingerprint(command),
    }


def _fingerprint(command: str) -> str:
    import hashlib

    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]


def list_processes() -> dict:
    try:
        out = subprocess.check_output(["ps", "-eo", "pid,user,comm"], text=True, timeout=5)
    except Exception as exc:
        raise ControlPlaneError("process list failed: %s" % exc) from exc
    lines = out.splitlines()[:200]
    return {"lines": lines, "count": len(lines)}


def get_system_info() -> dict:
    uname = os.uname()
    return {
        "sysname": uname.sysname,
        "nodename": uname.nodename,
        "release": uname.release,
        "machine": uname.machine,
    }


def execute_local(capability: str, arguments: dict, *, patterns: list[str], timeout: Optional[int]) -> dict:
    cap = capability
    if cap == "get_system_info":
        return get_system_info()
    if cap == "list_processes":
        return list_processes()
    if cap == "read_file":
        return read_file(arguments.get("path") or arguments.get("operand") or "", patterns)
    if cap in ("write_file", "upload_file"):
        import base64

        content = arguments.get("content")
        if isinstance(content, str) and arguments.get("encoding") == "base64":
            payload = base64.b64decode(content)
        elif isinstance(content, bytes):
            payload = content
        else:
            payload = str(content or "").encode("utf-8")
        return write_file(arguments.get("path") or "", payload, patterns)
    if cap == "delete_file":
        return delete_file(arguments.get("path") or arguments.get("operand") or "", patterns)
    if cap == "download_file":
        return read_file(arguments.get("path") or "", patterns)
    if cap == "exec":
        return exec_command(arguments.get("command") or arguments.get("operand") or "", timeout or DEFAULT_EXEC_TIMEOUT)
    raise ControlPlaneError("unsupported local capability %s" % cap)


# Account-bound jobs are a distinct wire capability: an older Agent rejects
# them as unsupported instead of accidentally running them as its service UID.
ACCOUNT_JOB = "account-bound-v1"
ACCOUNT_ACTIONS = frozenset({"exec", "list_processes", "read_file", "write_file",
                             "delete_file", "upload_file", "download_file"})


def normalize_execution_profile(value):
    """Validate signed public profile metadata without inspecting Server paths."""
    import re
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ControlPlaneError("Invalid Agent execution profile version")
    state = value.get("state")
    if state in ("legacy", "unavailable"):
        if set(value) != {"version", "state"}:
            raise ControlPlaneError("Invalid Agent execution state")
        return dict(value)
    if state != "configured" or set(value) != {"version", "state", "accounts", "reader"}:
        raise ControlPlaneError("Invalid Agent execution profile")
    accounts = value["accounts"]
    if not isinstance(accounts, dict) or not accounts or len(accounts) > 64:
        raise ControlPlaneError("Invalid Agent execution accounts")
    def absolute(path):
        return (isinstance(path, str) and path.startswith("/") and len(path) <= 4096
                and not any(ord(c) < 32 or c in "%\\*?[]" for c in path)
                and all(part not in (".", "..") for part in path.split("/"))
                and (path == "/" or (not path.endswith("/") and "//" not in path)))
    clean = {}
    for name, entry in accounts.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}[$]?", name)
                or not isinstance(entry, dict) or set(entry) != {"uid", "home", "cwd", "roots"}
                or type(entry["uid"]) is not int or entry["uid"] < 0
                or not absolute(entry["home"]) or not absolute(entry["cwd"])
                or not isinstance(entry["roots"], list) or not entry["roots"] or len(entry["roots"]) > 64
                or not all(absolute(root) for root in entry["roots"])
                or not any(root == "/" or entry["cwd"] == root or entry["cwd"].startswith(root + "/")
                           for root in entry["roots"])):
            raise ControlPlaneError("Invalid Agent execution account")
        clean[name] = dict(entry, roots=sorted(set(entry["roots"])))
    reader = value["reader"]
    if reader is not None and (not isinstance(reader, str) or reader not in clean or clean[reader]["uid"] == 0):
        raise ControlPlaneError("Invalid Agent read-only account")
    normalized = {"version":1, "state":"configured", "accounts":clean, "reader":reader}
    if len(json.dumps(normalized)) > 65536:
        raise ControlPlaneError("Agent execution profile is too large")
    return normalized


def execution_profile_digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(normalize_execution_profile(value), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def local_execution_profile(root):
    """Read locally approved Linux account ceilings; no remote job can edit this configuration."""
    import sys
    if not sys.platform.startswith("linux"):
        return {"version":1, "state":"legacy"}
    import pwd
    path = Path(root or "/") / "etc/drlink/ai-execution.json"
    try:
        # No symlink or writable ancestor from the selected Agent root.
        current = Path(root or "/")
        for part in ("etc", "drlink", "ai-execution.json"):
            current = current / part
            try:
                info = current.lstat()
            except FileNotFoundError:
                return {"version":1, "state":"legacy"}
            if (stat.S_ISLNK(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o022):
                raise ControlPlaneError("Unsafe local Agent execution profile ownership")
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ControlPlaneError("Invalid local Agent execution profile")
        # Local config has explicit root opt-in; only public normalized metadata
        # leaves the Agent through its authenticated management claim.
        with path.open("rb") as handle:
            raw = json.loads(handle.read(65537))
        if not isinstance(raw, dict) or set(raw) != {"version","accounts","reader","allow_root"} or raw["version"] != 1 or type(raw["allow_root"]) is not bool:
            raise ControlPlaneError("Invalid local Agent execution profile")
        entries = {}
        for name, spec in raw["accounts"].items():
            entry = pwd.getpwnam(name)
            if set(spec) != {"uid","cwd","roots"} or spec["uid"] != entry.pw_uid:
                raise ControlPlaneError("Agent execution UID changed")
            if entry.pw_uid == 0 and not raw["allow_root"]:
                raise ControlPlaneError("Agent root requires explicit local approval")
            if os.geteuid() != 0 and (entry.pw_uid != os.geteuid() or entry.pw_gid != os.getegid()):
                raise ControlPlaneError("Agent cannot assume approved account")
            roots = spec["roots"]
            cwd = spec["cwd"]
            if not all(Path(p).is_dir() and str(Path(p).resolve(strict=True)) == p for p in [cwd, *roots]):
                raise ControlPlaneError("Agent execution paths must be existing canonical directories")
            entries[name] = dict(spec, home=entry.pw_dir)
        return normalize_execution_profile({"version":1,"state":"configured","accounts":entries,"reader":raw["reader"]})
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ControlPlaneError):
        return {"version":1,"state":"unavailable"}


def prepare_local_execution_profile(root, names, roots, reader=None, *, allow_root=False):
    """Build a reviewed Linux Agent profile without changing the host."""
    import pwd
    import sys
    if not sys.platform.startswith("linux"):
        raise ControlPlaneError("Account-aware Agent execution is supported on Linux only")
    if not names or len(set(names)) != len(names):
        raise ControlPlaneError("Select unique existing OS accounts")
    if not roots or any(not isinstance(r,str) or not r.startswith("/") for r in roots):
        raise ControlPlaneError("Specify existing absolute roots")
    try:
        canonical = sorted(set(str(Path(r).resolve(strict=True)) for r in roots))
        if not all(Path(r).is_dir() for r in canonical):
            raise ControlPlaneError("Roots must be directories")
        entries = {}
        for name in names:
            user = pwd.getpwnam(name)
            if user.pw_uid == 0 and not allow_root:
                raise ControlPlaneError("Root requires separate explicit approval")
            if os.geteuid() != 0 and (user.pw_uid != os.geteuid() or user.pw_gid != os.getegid()):
                raise ControlPlaneError("Local operator cannot assume selected account")
            home = str(Path(user.pw_dir).resolve())
            cwd = home if Path(home).is_dir() and any(
                r=="/" or home==r or home.startswith(r+"/") for r in canonical) else canonical[0]
            entries[name] = {"uid":user.pw_uid,"cwd":cwd,"roots":canonical}
        normalize_execution_profile({"version":1,"state":"configured","accounts":{
            n:dict(e,home=pwd.getpwnam(n).pw_dir) for n,e in entries.items()},"reader":reader})
    except (OSError,KeyError,ValueError,TypeError) as exc:
        raise ControlPlaneError("Invalid local account or directory") from exc
    return {"version":1,"accounts":entries,"reader":reader,"allow_root":bool(allow_root)}


def save_local_execution_profile(root, profile, *, previous):
    """Replace only the reviewed local file; verify and roll back on failure."""
    import tempfile
    path=Path(root or "/")/"etc/drlink/ai-execution.json"
    current=Path(root or "/")
    for part in ("etc","drlink"):
        current=current/part
        if part=="drlink" and not current.exists() and not current.is_symlink():
            try:
                current.mkdir(mode=0o755)
            except FileExistsError:
                pass
        info=current.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:
            raise ControlPlaneError("Unsafe Agent configuration directory")
    def existing():
        try:
            info=path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022 or info.st_size>65536:
            raise ControlPlaneError("Unsafe existing Agent profile")
        return path.read_bytes()
    if existing()!=previous:
        raise ControlPlaneError("Agent profile changed after review")
    # Serialize product-managed configuration edits; never follow symlinks.
    import fcntl
    fd=os.open(path.parent/".ai-execution.lock",os.O_CREAT|os.O_NOFOLLOW|os.O_RDWR,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        if existing()!=previous:
            raise ControlPlaneError("Agent profile changed after review")
        def publish(content):
            tmpfd,tmp=tempfile.mkstemp(prefix=".ai-execution-",dir=path.parent)
            try:
                with os.fdopen(tmpfd,"wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp,path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
        encoded=(json.dumps(profile,sort_keys=True,indent=2)+"\n").encode()
        publish(encoded)
        live=local_execution_profile(root)
        if live["state"]!="configured":
            if previous is None:
                path.unlink()
            else:
                publish(previous)
            raise ControlPlaneError("Agent profile validation failed; previous configuration restored")
        return live
    finally:
        os.close(fd)


def _bounded_account_communicate(proc,data,timeout,check,out_limit,err_limit):
    """Drain bounded streams while checking the current grant on a short interval."""
    import selectors
    selector=selectors.DefaultSelector()
    buffers={"out":bytearray(),"err":bytearray()}
    truncated={"out":False,"err":False}
    limits={"out":out_limit,"err":err_limit}
    def register(stream,events,tag):
        os.set_blocking(stream.fileno(),False)
        selector.register(stream,events,tag)
    register(proc.stdout,selectors.EVENT_READ,"out")
    register(proc.stderr,selectors.EVENT_READ,"err")
    pending=memoryview(data or b"")
    if proc.stdin is not None:
        if pending:
            register(proc.stdin,selectors.EVENT_WRITE,"in")
        else:
            proc.stdin.close()
    started=time.monotonic()
    next_check=started+0.5
    status="ALLOW"
    def kill():
        try:
            os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        while selector.get_map() or proc.poll() is None:
            now=time.monotonic()
            if now-started>=timeout:
                status="TIMEOUT"
                kill()
                break
            if now>=next_check:
                if not check():
                    status="DENY"
                    kill()
                    break
                next_check=time.monotonic()+0.5
            for key,_mask in selector.select(0.1):
                stream=key.fileobj
                if key.data=="in":
                    try:
                        sent=os.write(stream.fileno(),pending[:65536])
                        pending=pending[sent:]
                    except BlockingIOError:
                        continue
                    except BrokenPipeError:
                        pending=pending[:0]
                    if not pending:
                        selector.unregister(stream)
                        stream.close()
                    continue
                try:
                    chunk=os.read(stream.fileno(),65536)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(stream)
                    stream.close()
                    continue
                buf=buffers[key.data]
                available=max(0,limits[key.data]-len(buf))
                buf.extend(chunk[:available])
                truncated[key.data] |= len(chunk)>available
        if status=="ALLOW" and not check():
            status="DENY"
            kill()
        proc.wait(timeout=2)
    except BaseException:
        kill()
        proc.wait(timeout=2)
        raise
    finally:
        selector.close()
        for stream in (proc.stdin,proc.stdout,proc.stderr):
            if stream is not None:
                stream.close()
    return status,bytes(buffers["out"]),bytes(buffers["err"]),truncated


def _account_job(root, job, *, stop_event=None):
    """Recheck live local approval before running a bound operation."""
    import pwd
    import sys
    profile = local_execution_profile(root)
    args = job.get("arguments")
    if not isinstance(args, dict) or set(args) != {"binding","operation","arguments"}:
        raise ControlPlaneError("Invalid account-bound Agent job")
    binding = args["binding"]
    operation = args["operation"]
    options = args["arguments"]
    if (not isinstance(binding, dict) or set(binding) != {"account","uid","profile_digest","rule_id"}
            or operation not in ACCOUNT_ACTIONS or not isinstance(options, dict)
            or profile["state"] != "configured" or binding["profile_digest"] != execution_profile_digest(profile)):
        raise ControlPlaneError("Agent execution profile changed or unavailable")
    name = binding["account"]
    entry = profile["accounts"].get(name)
    if not entry or entry["uid"] != binding["uid"]:
        raise ControlPlaneError("Agent account is not locally approved")
    user = pwd.getpwnam(name)
    if user.pw_uid != entry["uid"]:
        raise ControlPlaneError("Agent execution UID changed")
    patterns = job.get("patterns") or []
    def within_roots(value, *, directory=False):
        if not isinstance(value, str) or not value.startswith("/") or "%" in value or not path_allowed(value, patterns):
            raise ControlPlaneError("Agent path denied")
        canonical = str(Path(value).resolve(strict=directory))
        if not any(r == "/" or canonical == r or canonical.startswith(r + "/") for r in entry["roots"]):
            raise ControlPlaneError("Agent local path ceiling denied")
        if directory and not Path(canonical).is_dir():
            raise ControlPlaneError("Agent cwd unavailable")
        return canonical
    cwd = entry["cwd"]
    if operation == "exec":
        cwd = within_roots(options.get("cwd", cwd), directory=True)
        if not isinstance(options.get("command"), str) or not options["command"] or "\x00" in options["command"]:
            raise ControlPlaneError("Invalid Agent command")
        argv = ["/bin/sh", "-c", options["command"]]
        data = None
    else:
        if operation != "list_processes":
            within_roots(options.get("path"))
        if operation in ("write_file","upload_file") and not isinstance(options.get("content"), str):
            raise ControlPlaneError("Explicit file content required")
        # Isolated Python worker, not a privileged in-process file action.
        argv = [sys.executable, "-I", "-c",
                "import sys;sys.path.insert(0,sys.argv[1]);from drlink_ai_agent import account_file_worker;account_file_worker()",
                str(Path(__file__).resolve().parent)]
        data = json.dumps({"operation":operation,"arguments":options,
                           "patterns":patterns,"roots":entry["roots"]}).encode()
        if len(data) > 2*MAX_FILE_BYTES:
            raise ControlPlaneError("Agent file request too large")
    env = {"PATH":"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
           "HOME":user.pw_dir,"USER":name,"LOGNAME":name,"LANG":"C.UTF-8"}
    identity = ({"user":user.pw_uid,"group":user.pw_gid,"extra_groups":os.getgrouplist(name,user.pw_gid)}
                if os.geteuid() == 0 else {})
    import drlink_mgmt_sync as mgmt
    def check():
        try:
            if (stop_event is not None and stop_event.is_set()) or _deadline_passed(job.get("deadline_at")):
                return False
            current=local_execution_profile(root)
            if execution_profile_digest(current)!=binding["profile_digest"]:
                return False
            return mgmt.validate_ai_job_on_server(root=root,job=job,execution_profile=current)
        except Exception:
            return False
    if not check():
        raise ControlPlaneError("Agent execution grant unavailable before launch")
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, close_fds=True, **identity)
    status,out,err,truncated=_bounded_account_communicate(proc,data,
        max(1,min(int(job.get("timeout") or 30),3600)),check,
        MAX_STDOUT_BYTES if operation=="exec" else 2*MAX_FILE_BYTES,MAX_STDERR_BYTES)
    if status!="ALLOW":
        return {"result":status,"error":"Agent grant revoked or unavailable" if status=="DENY" else "Agent job timed out",
                "exit_status":proc.returncode,"execution_user":name,"execution_uid":user.pw_uid}
    if operation == "exec":
        return {"result":"ALLOW","exit_status":proc.returncode,
                "stdout":out.decode("utf-8","replace"),"stderr":err.decode("utf-8","replace"),
                "stdout_truncated":truncated["out"],"stderr_truncated":truncated["err"],"cwd":cwd,
                "execution_user":name,"execution_uid":user.pw_uid}
    if proc.returncode or truncated["out"]:
        raise ControlPlaneError("Agent account file operation failed")
    result = json.loads(out)
    if not isinstance(result, dict) or result.get("result") != "ALLOW":
        raise ControlPlaneError("Agent account file operation denied")
    return dict(result, execution_user=name, execution_uid=user.pw_uid)


def account_file_worker():
    import sys
    try:
        data = sys.stdin.buffer.read(2*MAX_FILE_BYTES+1)
        if len(data) > 2*MAX_FILE_BYTES:
            raise ControlPlaneError("Agent file request too large")
        request = json.loads(data)
        operation = request["operation"]
        if operation not in ACCOUNT_ACTIONS or operation == "exec":
            raise ControlPlaneError("Invalid Agent file operation")
        if operation != "list_processes":
            value = request["arguments"].get("path")
            if not isinstance(value,str) or not path_allowed(value,request["patterns"]):
                raise ControlPlaneError("Agent file rule denied")
            canonical = str(Path(value).resolve(strict=False))
            if not any(r == "/" or canonical == r or canonical.startswith(r + "/")
                       for r in request["roots"]):
                raise ControlPlaneError("Agent file ceiling denied")
        result = execute_local(operation, request["arguments"], patterns=request["patterns"], timeout=30)
        sys.stdout.write(json.dumps(dict(result, result="ALLOW")))
    except Exception:
        sys.stdout.write('{"result":"DENY"}')


def _agent_post(url: str, token: str, body: dict, timeout: float = 10) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(payload)
        except Exception:
            raise ControlPlaneError("agent RPC HTTP %s" % exc.code) from exc


# Idle claim polls must not run at interactive rate. A busy poll stays short
# so a queued job is still picked up inside the MCP wait.
AI_AGENT_IDLE_POLL_SECONDS = 2.0
AI_AGENT_BUSY_POLL_SECONDS = 0.05

# Held claim (AUD-21 step 2): the production Agent asks the Server to hold an
# empty claim for this long and answer the moment a job is queued. Idle load
# becomes about fleet_size / 25 requests per second instead of fleet_size / 2.
AI_AGENT_CLAIM_WAIT_MS = 25000
# The library default stays 0 (a plain poll) so existing callers and tests are
# unchanged; the production entry point below opts in.
DEFAULT_CLAIM_WAIT_MS = 0
# The request timeout sits this far above the hold: a client that gave up on a
# claim the Server then answers would strand the claimed job.
AI_AGENT_CLAIM_TIMEOUT_MARGIN_SECONDS = 10.0
# A held claim that came back empty after at least this share of its hold was
# honoured by the Server; a much faster empty answer means the Server did not
# hold (older Server, parked-claim cap), so fall back to the idle poll.
AI_AGENT_HOLD_HONOURED_FRACTION = 0.5


class AgentLoop:
    """Poll the Server for authorized jobs and execute them locally on this host.

    Production transport uses enrolled management identity against the Server
    management URL (``/v1/ai-jobs/claim|complete``). Bearer token + MCP Bridge
    ``/agent/v1/*`` remains available for hermetic tests.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        stop_event: Optional[threading.Event] = None,
        *,
        agent_root: Optional[str] = None,
        wait_ms: Optional[int] = None,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.agent_root = agent_root
        self.stop_event = stop_event or threading.Event()
        if not self.token and not self.agent_root:
            raise ValueError("AgentLoop requires bearer token or agent_root")
        chosen = DEFAULT_CLAIM_WAIT_MS if wait_ms is None else wait_ms
        self.wait_ms = max(0, min(int(chosen or 0), AI_AGENT_CLAIM_WAIT_MS))

    def _claim(self) -> list:
        if self.agent_root:
            import drlink_mgmt_sync as mgmt

            profile = local_execution_profile(self.agent_root)
            payload = mgmt.claim_ai_jobs_on_server(
                root=self.agent_root, limit=4, wait_ms=self.wait_ms, execution_profile=profile
            )
            return list(payload.get("jobs") or [])
        body = {"limit": 4}
        timeout = 10
        if self.wait_ms:
            body["wait_ms"] = self.wait_ms
            timeout = self.wait_ms / 1000.0 + AI_AGENT_CLAIM_TIMEOUT_MARGIN_SECONDS
        payload = _agent_post(self.base_url + "/agent/v1/claim", self.token, body, timeout=timeout)
        return list(payload.get("jobs") or [])

    def _complete(
        self,
        job_id: str,
        result: dict,
        *,
        claim_token: Optional[str] = None,
        attempt_id: Optional[str] = None,
    ) -> None:
        if self.agent_root:
            import drlink_mgmt_sync as mgmt

            response = mgmt.complete_ai_job_on_server(
                root=self.agent_root,
                job_id=job_id,
                result=result,
                claim_token=claim_token,
                attempt_id=attempt_id,
            )
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise ControlPlaneError("Agent job completion was not acknowledged")
            return
        body = {"id": job_id, "result": result}
        if claim_token is not None:
            body["claim_token"] = claim_token
        if attempt_id is not None:
            body["attempt_id"] = attempt_id
        response = _agent_post(
            self.base_url + "/agent/v1/complete",
            self.token,
            body,
        )
        if not isinstance(response, dict) or response.get("ok") is not True:
            raise ControlPlaneError("Agent job completion was not acknowledged")

    @staticmethod
    def _transient_completion_failure(exc: Exception) -> bool:
        """Retry connectivity faults, never credentials, policy, or job state."""
        import urllib.error
        if isinstance(exc, urllib.error.HTTPError):
            return False
        if isinstance(exc, (OSError, TimeoutError, ConnectionError)):
            return True
        # The signed management client wraps URL/network failures in its
        # operational exception; authorization failures share its parent.
        try:
            import drlink_mgmt_sync as mgmt
            if isinstance(exc, mgmt.MgmtAuthError):
                return False
            if isinstance(exc, mgmt.MgmtSyncError):
                cause = getattr(exc, "__cause__", None)
                return (isinstance(cause, (OSError, urllib.error.URLError))
                        and not isinstance(cause, urllib.error.HTTPError))
        except ImportError:
            pass
        return False

    def _complete_with_retry(self, job_id, result, *, claim_token=None,
                             attempt_id=None, deadline_at=None) -> None:
        """Retry delivery of the *same* result, never re-run the AI command.

        The server's signed claim_token/attempt_id owns the completion.
        Rejected/terminal outcomes are not retried; the server continues to
        enforce the job deadline and exactly-once execution state.
        """
        for attempt in range(3):
            try:
                self._complete(
                    job_id, result,
                    claim_token=claim_token, attempt_id=attempt_id,
                )
                return
            except Exception as exc:
                if (attempt == 2 or self.stop_event.is_set()
                        or _deadline_passed(deadline_at)
                        or not self._transient_completion_failure(exc)):
                    # Do not log result bodies, commands, tokens or sensitive
                    # transport details in the Agent's service journal.
                    import sys
                    print("WARNING: AI completion unacknowledged (%s)" %
                          type(exc).__name__, file=sys.stderr)
                    return
                if self.stop_event.wait(0.2 * (attempt + 1)):
                    return

    def run_once(self) -> int:
        jobs = self._claim()
        for job in jobs:
            job_id = job.get("id")
            claim_token = job.get("claim_token")
            attempt_id = job.get("attempt_id")
            if _deadline_passed(job.get("deadline_at")):
                result = {
                    "result": "DENY",
                    "error": "job deadline expired before execution",
                }
                self._complete_with_retry(
                    job_id, result, claim_token=claim_token,
                    attempt_id=attempt_id, deadline_at=job.get("deadline_at"),
                )
                continue
            try:
                cap = job.get("capability") or ""
                if cap == ACCOUNT_JOB:
                    if not self.agent_root:
                        raise ControlPlaneError("Account-bound jobs require enrolled Agent management")
                    result = _account_job(self.agent_root, job, stop_event=self.stop_event)
                else:
                    if self.agent_root and cap in ACCOUNT_ACTIONS and local_execution_profile(self.agent_root)["state"] != "legacy":
                        raise ControlPlaneError("Agent requires an explicit account-bound job")
                    result = execute_local(cap, job.get("arguments") or {},
                        patterns=job.get("patterns") or [], timeout=job.get("timeout"))
            except ControlPlaneError as exc:
                result = {"result": "DENY", "error": str(exc)}
            except Exception as exc:
                result = {"result": "ERROR", "error": str(exc)}
            self._complete_with_retry(
                job_id, result, claim_token=claim_token,
                attempt_id=attempt_id, deadline_at=job.get("deadline_at"),
            )
        return len(jobs)

    def run(self) -> None:
        while not self.stop_event.is_set():
            found = 0
            failed = False
            started = time.monotonic()
            try:
                found = int(self.run_once() or 0)
            except Exception:
                found = 0
                failed = True
            delay = self._next_delay(found, failed, time.monotonic() - started)
            if delay > 0:
                self.stop_event.wait(delay)

    def _next_delay(self, found: int, failed: bool, claim_seconds: float) -> float:
        """Seconds to wait before the next claim."""
        if found:
            # With a held claim the next claim returns at once when more jobs are
            # queued and otherwise waits for work, so no pause is needed between
            # batches (it only delays queued jobs).
            return 0.0 if self.wait_ms else AI_AGENT_BUSY_POLL_SECONDS
        if (
            self.wait_ms
            and not failed
            and claim_seconds >= (self.wait_ms / 1000.0) * AI_AGENT_HOLD_HONOURED_FRACTION
        ):
            # The Server held the claim for (about) the whole wait: ask again at once.
            return 0.0
        return AI_AGENT_IDLE_POLL_SECONDS


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Data Relay Link AI agent (not an MCP server)")
    parser.add_argument(
        "--url",
        default=os.environ.get("DRLINK_MCP_URL", ""),
        help="Optional MCP Bridge base URL for bearer-token test mode",
    )
    parser.add_argument(
        "--token-file",
        default=os.environ.get("DRLINK_AI_AGENT_TOKEN_FILE", "/etc/drlink/ai-agent.token"),
    )
    parser.add_argument(
        "--agent-root",
        default=os.environ.get("DRLINK_AGENT_ROOT", ""),
        help="Agent filesystem root; when set, uses enrolled management identity",
    )
    args = parser.parse_args(argv)
    agent_root = str(args.agent_root or "").strip() or None
    token = os.environ.get("DRLINK_AI_AGENT_TOKEN") or ""
    if not token and args.token_file and os.path.isfile(args.token_file):
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    # Production default: management identity on the enrolled Agent root.
    if not token:
        if agent_root is None:
            agent_root = "/"
        AgentLoop(agent_root=agent_root, wait_ms=AI_AGENT_CLAIM_WAIT_MS).run()
        return
    if not args.url:
        raise SystemExit("ERROR: bearer-token mode requires --url / DRLINK_MCP_URL")
    AgentLoop(args.url, token, agent_root=None, wait_ms=AI_AGENT_CLAIM_WAIT_MS).run()


if __name__ == "__main__":
    main()
