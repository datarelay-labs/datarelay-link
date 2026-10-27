#!/usr/bin/env python3
"""Narrow, reversible operator rollout of Native MCP on the existing Server.

Default --check only reads state. --apply requires root, an exact clean source
HEAD, and an explicitly selected account/roots. This installs three Python
modules and one dedicated drop-in; it never edits TLS, OAuth, AI Access or DBs.
Only drlink-mcp-bridge.service is restarted. Keep the receipt for --rollback.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import subprocess
import sys
import tempfile

UNIT = "drlink-mcp-bridge.service"
MODULES = ("drlink_mcp_bridge.py", "drlink_mcp_full_control.py", "drlink_control_plane.py")
TARGETS = tuple("usr/local/lib/drlink/" + name for name in MODULES) + (
    "etc/systemd/system/drlink-mcp-bridge.service.d/zz-native-full-control.conf",
)
OWNER_UID, OWNER_GID = 0, 0
MAX_SOURCE_BYTES = 8 * 1024 * 1024


class RolloutError(Exception):
    pass


@dataclass(frozen=True)
class Layout:
    # An alternate root is an internal disposable-test seam, never a CLI option.
    root: Path = Path("/")

    @property
    def backups(self):
        return self.root / "var/backups/drlink-native-mcp"

    def target(self, name):
        if name not in TARGETS:
            raise RolloutError("Unexpected rollout target")
        return self.root / name


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require_root():
    if os.geteuid() != 0:
        raise RolloutError("Apply and rollback require an authorized root invocation")


def profile(user, roots, allow_root=False):
    if not user or not roots:
        raise RolloutError("--exec-user and at least one --allowed-root are required")
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        raise RolloutError("Execution account does not exist") from None
    if account.pw_uid == 0 and not allow_root:
        raise RolloutError("Root execution requires the separate --allow-root opt-in")
    resolved = []
    for value in roots:
        path = Path(value)
        if (not path.is_absolute() or not path.is_dir() or ":" in str(path)
                or any(ord(char) < 32 for char in str(path))):
            raise RolloutError("Allowed roots must be existing absolute directories without control characters or ':'")
        canonical = str(path.resolve(strict=True))
        if ":" in canonical or any(ord(char) < 32 for char in canonical):
            raise RolloutError("Canonical root contains an unsafe environment character")
        resolved.append(canonical)
    return {"exec_user": account.pw_name, "uid": account.pw_uid,
            "roots": list(dict.fromkeys(resolved)), "admin": account.pw_uid == 0}


def dropin(settings):
    values = {
        "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
        "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
        "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
        "DRLINK_MCP_SERVER_EXEC_USER": settings["exec_user"],
        "DRLINK_MCP_SERVER_ALLOWED_ROOTS": os.pathsep.join(settings["roots"]),
        "DRLINK_MCP_SERVER_DEFAULT_CWD": settings["roots"][0],
        "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if settings["admin"] else "0",
    }
    def escape(value):
        return value.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    text = "# Managed by operator-native-mcp-full-control.py; see rollout receipt.\n[Service]\n"
    text += "".join('Environment="' + key + "=" + escape(value) + '"\n'
                    for key, value in values.items())
    return text.encode()


def git_read(source, *args):
    owner = pwd.getpwuid(source.stat().st_uid)
    options = {}
    if os.geteuid() == 0 and (owner.pw_uid != os.geteuid() or owner.pw_gid != os.getegid()):
        options = {"user": owner.pw_uid, "group": owner.pw_gid,
                   "extra_groups": os.getgrouplist(owner.pw_name, owner.pw_gid)}
    env = {"PATH": "/usr/bin:/bin", "HOME": owner.pw_dir,
           "LANG": "C.UTF-8", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ["/usr/bin/git", "-c", "core.fsmonitor=false", "-C", str(source), *args],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=20, check=False, **options,
    )
    if result.returncode:
        raise RolloutError("Source Git verification failed")
    if len(result.stdout) > MAX_SOURCE_BYTES:
        raise RolloutError("Source verification response exceeds its bound")
    return result.stdout


def candidate(source, expected_head=None, *, clean_required=False):
    source = Path(source).resolve(strict=True)
    head = git_read(source, "rev-parse", "HEAD").decode().strip()
    if expected_head and (not re.fullmatch(r"[0-9a-f]{40}", expected_head)
                          or head != expected_head):
        raise RolloutError("Expected exact candidate HEAD does not match the source checkout")
    if clean_required and not expected_head:
        raise RolloutError("--apply requires --head with the exact 40-character candidate HEAD")
    dirty = bool(git_read(source, "status", "--porcelain=v1", "--untracked-files=all"))
    if clean_required and dirty:
        raise RolloutError("Candidate worktree must be completely clean before apply")
    files = {}
    for name, target in zip(MODULES, TARGETS):
        # Install immutable committed blobs, never mutable working-tree bytes.
        data = git_read(source, "show", head + ":lib/" + name)
        compile(data, name, "exec")
        files[target] = data
    return {"head": head, "source": str(source), "clean": not dirty, "files": files}


def safe_path(path, layout):
    relative = path.relative_to(layout.root)
    current = layout.root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RolloutError("Symlink in a rollout or backup path")
        if current.exists():
            info = current.stat()
            if info.st_uid != OWNER_UID or stat.S_IMODE(info.st_mode) & 0o022:
                raise RolloutError("Rollout paths must be root-owned and not group/world writable")


def state(path, layout):
    safe_path(path, layout)
    if not path.exists():
        return None
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RolloutError("Rollout target must be a regular file")
    return {"sha256": digest(path.read_bytes()), "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid}


def atomic_write(path, data, *, mode=0o644, uid=None, gid=None):
    uid = OWNER_UID if uid is None else uid
    gid = OWNER_GID if gid is None else gid
    handle, temporary = tempfile.mkstemp(prefix=".native-mcp-", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            os.fchown(stream.fileno(), uid, gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_receipt(path, receipt):
    atomic_write(path, (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode(), mode=0o600)


def service(action):
    args = ["/usr/bin/systemctl", action]
    if action != "daemon-reload":
        args.append(UNIT)
    if action == "is-active":
        args.append("--quiet")
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=45, check=False)
    if result.returncode:
        raise RolloutError("Bridge service operation failed: " + action)


def restart_bridge():
    service("daemon-reload")
    service("restart")
    service("is-active")


def check(source, head, settings, layout=Layout()):
    selected = candidate(source, head)
    blobs = dict(selected["files"])
    blobs[TARGETS[-1]] = dropin(settings)
    return {"mode": "check", "head": selected["head"], "clean": selected["clean"],
            "source": selected["source"], "profile": settings,
            "service": UNIT, "changes": [
                {"path": str(layout.target(name)), "candidate_sha256": digest(data),
                 "installed": state(layout.target(name), layout)} for name, data in blobs.items()],
            "ai_access": "unchanged; explicit per-call authorization remains required"}


def load_receipt(path, layout):
    path = Path(path).absolute()
    if (path.name != "receipt.json" or path.parent.parent != layout.backups
            or not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{12}-[0-9a-f]{8}", path.parent.name)):
        raise RolloutError("Receipt must be inside the dedicated rollout backup directory")
    safe_path(path, layout)
    receipt = json.loads(path.read_text())
    if (receipt.get("version") != 1 or receipt.get("service") != UNIT
            or not isinstance(receipt.get("files"), dict)
            or set(receipt["files"]) != set(TARGETS)):
        raise RolloutError("Unexpected rollout receipt structure")
    for index, name in enumerate(TARGETS):
        entry = receipt["files"][name]
        if (entry.get("backup") != str(index) + ".before"
                or not re.fullmatch(r"[0-9a-f]{64}", entry.get("after", ""))):
            raise RolloutError("Invalid receipt file binding")
    return path, receipt


def rollback(path, layout=Layout()):
    require_root()
    path, receipt = load_receipt(path, layout)
    restored = []
    # Validate every target and backup before any write. A later unrelated edit
    # refuses the whole rollback rather than partly restoring older state.
    for name, entry in receipt["files"].items():
        current = state(layout.target(name), layout)
        before = entry["before"]
        before_hash = before["sha256"] if before else None
        installed = {"sha256": entry["after"], "mode": 0o644, "uid": OWNER_UID, "gid": OWNER_GID}
        if current not in (before, installed):
            raise RolloutError("Rollback refuses a subsequently modified target: " + name)
        data = None
        if before:
            backup = path.parent / entry["backup"]
            backup_state = state(backup, layout)
            if not backup_state or backup_state["sha256"] != before_hash:
                raise RolloutError("Rollback backup hash does not match the receipt")
            data = backup.read_bytes()
        restored.append((name, before, data, current != before))
    for name, before, data, changed in restored:
        if not changed:
            continue
        destination = layout.target(name)
        if before:
            atomic_write(destination, data, mode=before["mode"], uid=before["uid"], gid=before["gid"])
        else:
            destination.unlink()
    restart_bridge()
    receipt["status"] = "rolled_back"
    save_receipt(path, receipt)
    return {"mode": "rollback", "status": "rolled_back", "receipt": str(path)}


def apply(source, head, settings, layout=Layout()):
    require_root()
    selected = candidate(source, head, clean_required=True)
    files = dict(selected["files"])
    files[TARGETS[-1]] = dropin(settings)
    previous = {name: state(layout.target(name), layout) for name in TARGETS}
    service("is-active")
    safe_path(layout.backups, layout)
    layout.backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    directory = layout.backups / (stamp + "-" + head[:12] + "-" + secrets.token_hex(4))
    directory.mkdir(mode=0o700)
    receipt_path = directory / "receipt.json"
    receipt = {"version": 1, "service": UNIT, "head": head, "source": selected["source"],
               "profile": settings, "status": "prepared", "files": {}}
    for index, name in enumerate(TARGETS):
        backup = str(index) + ".before"
        if previous[name]:
            original = layout.target(name).read_bytes()
            if digest(original) != previous[name]["sha256"]:
                raise RolloutError("Installed target changed while preparing its backup")
            atomic_write(directory / backup, original, mode=0o600)
        receipt["files"][name] = {"before": previous[name], "after": digest(files[name]), "backup": backup}
    save_receipt(receipt_path, receipt)
    try:
        if any(state(layout.target(name), layout) != previous[name] for name in TARGETS):
            raise RolloutError("Installed state changed after rollout preparation")
        for name in TARGETS:
            destination = layout.target(name)
            safe_path(destination, layout)
            if state(destination, layout) != previous[name]:
                raise RolloutError("Installed target changed after rollout preparation: " + name)
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            atomic_write(destination, files[name])
        if any(state(layout.target(name), layout)["sha256"] != receipt["files"][name]["after"]
               for name in TARGETS):
            raise RolloutError("Installed module or drop-in checksum mismatch")
        restart_bridge()
        receipt["status"] = "applied"
        save_receipt(receipt_path, receipt)
    except Exception as failure:
        try:
            rollback(receipt_path, layout)
        except Exception as restore_failure:
            raise RolloutError("Rollout failed; rollback requires review; receipt=" + str(receipt_path)
                               + "; cause=" + str(restore_failure)) from failure
        raise RolloutError("Rollout failed and was rolled back; receipt=" + str(receipt_path)) from failure
    return {"mode": "apply", "status": "applied", "head": head, "receipt": str(receipt_path),
            "service": UNIT, "installed_sha256": {name: digest(files[name]) for name in TARGETS}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only plan; the default")
    mode.add_argument("--apply", action="store_true", help="Apply the exact clean candidate as root")
    mode.add_argument("--rollback", type=Path, metavar="RECEIPT")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head", help="Exact 40-character candidate Git HEAD; required for apply")
    parser.add_argument("--exec-user")
    parser.add_argument("--allowed-root", action="append", default=[])
    parser.add_argument("--allow-root", action="store_true", help="Explicit opt-in for execution UID 0")
    args = parser.parse_args(argv)
    try:
        if args.rollback:
            result = rollback(args.rollback)
        else:
            settings = profile(args.exec_user, args.allowed_root, args.allow_root)
            operation = apply if args.apply else check
            result = operation(args.source, args.head, settings)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RolloutError, OSError, ValueError, KeyError, SyntaxError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
