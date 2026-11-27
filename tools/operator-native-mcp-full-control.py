#!/usr/bin/env python3
"""Narrow, reversible operator rollout of Native MCP on the existing Server.

Default --check only reads state. --apply requires root, an exact clean source
HEAD, and an explicitly selected account/roots. This installs three Python
modules and one dedicated drop-in; it never edits TLS, OAuth, AI Access or DBs.
Required installed runtime dependencies must match the candidate exactly;
use a full Server project update first when they are absent or incompatible.
Only drlink-mcp-bridge.service is restarted. Keep the receipt for --rollback.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import grp
import errno
import struct
import shutil
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
DEPENDENCIES = ("drlink_mcp_server_executor.py", "drlink_v24.py")
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


def profile(user, roots, allow_root=False, *, approval_identity=None):
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
    settings = {"exec_user": account.pw_name, "uid": account.pw_uid,
                "roots": list(dict.fromkeys(resolved)), "admin": account.pw_uid == 0}
    if approval_identity is not None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", approval_identity):
            raise RolloutError("OAuth approval Identity hint must be a safe AI Identity name")
        settings["approval_identity"] = approval_identity
    return settings


def multi_account_profile(users, roots, allow_root=False, *, reader=None):
    """Explicit local ceiling for fresh installs; never a grant to an AI."""
    if not users or len(users) > 128 or len(set(users)) != len(users):
        raise RolloutError("Select unique existing execution accounts")
    entries = {}
    resolved = None
    for user in users:
        selected = profile(user, roots, allow_root)
        resolved = selected["roots"]
        entry = pwd.getpwnam(user)
        home = str(Path(entry.pw_dir).resolve())
        cwd = home if Path(home).is_dir() and any(
            root == "/" or home == root or home.startswith(root + "/") for root in resolved
        ) else resolved[0]
        entries[user] = {"uid": entry.pw_uid, "cwd": cwd, "roots": list(resolved)}
    if reader is not None and (reader not in entries or entries[reader]["uid"] == 0):
        raise RolloutError("Read-only executor must be an approved non-administrative account")
    return {"exec_accounts": entries, "roots": resolved,
            "admin": any(entry["uid"] == 0 for entry in entries.values()), "reader": reader}


def _profile_environment(settings):
    values = {
        "DRLINK_MCP_SERVER_SELF_ENABLED": "1",
        "DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED": "1",
        "DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED": "1",
        "DRLINK_MCP_SERVER_ALLOWED_ROOTS": os.pathsep.join(settings["roots"]),
        "DRLINK_MCP_SERVER_ADMIN_ENABLED": "1" if settings["admin"] else "0",
    }
    if "exec_accounts" in settings:
        values["DRLINK_MCP_SERVER_EXEC_ACCOUNTS"] = json.dumps(settings["exec_accounts"], sort_keys=True, separators=(",", ":"))
        # Clear inherited singleton values so an older native executor cannot
        # accidentally run the old default against a new local account map.
        values["DRLINK_MCP_SERVER_EXEC_USER"] = ""
        values["DRLINK_MCP_SERVER_DEFAULT_CWD"] = ""
        values["DRLINK_MCP_SERVER_READ_USER"] = settings.get("reader") or ""
        if "legacy_account" in settings:
            values["DRLINK_MCP_SERVER_LEGACY_ACCOUNT"] = settings["legacy_account"] or ""
            values["DRLINK_MCP_SERVER_LEGACY_RULE_IDS"] = json.dumps(
                settings["legacy_rules"], sort_keys=True, separators=(",", ":"))
    else:
        values["DRLINK_MCP_SERVER_EXEC_USER"] = settings["exec_user"]
        values["DRLINK_MCP_SERVER_DEFAULT_CWD"] = settings["roots"][0]
    return values


def dropin(settings):
    values = _profile_environment(settings)
    if settings.get("approval_identity"):
        values["DRLINK_MCP_OAUTH_OPERATOR_IDENTITY"] = settings["approval_identity"]
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
    dependencies = {}
    for name in DEPENDENCIES:
        data = git_read(source, "show", head + ":lib/" + name)
        compile(data, name, "exec")
        dependencies["usr/local/lib/drlink/" + name] = data
    return {"head": head, "source": str(source), "clean": not dirty,
            "files": files, "dependencies": dependencies}


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


def verify_runtime_dependencies(selected, layout):
    result = []
    for name, data in selected["dependencies"].items():
        installed = state(layout.root / name, layout)
        expected = digest(data)
        if installed is None or installed["sha256"] != expected:
            raise RolloutError(
                "Incompatible installed runtime dependency: " + name
                + "; complete the Server project update before this MCP-only rollout")
        result.append({"path": str(layout.root / name),
                       "candidate_sha256": expected, "installed": installed})
    return result


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
    dependencies = verify_runtime_dependencies(selected, layout)
    blobs = dict(selected["files"])
    blobs[TARGETS[-1]] = dropin(settings)
    return {"mode": "check", "head": selected["head"], "clean": selected["clean"],
            "source": selected["source"], "profile": settings,
            "dependencies": dependencies,
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
    verify_runtime_dependencies(selected, layout)
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
        verify_runtime_dependencies(selected, layout)
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
        verify_runtime_dependencies(selected, layout)
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


DEFAULT_EXECUTOR = "drlink-mcp"
DEFAULT_WORKSPACE = Path("/var/lib/drlink-mcp")


def _executor_code_acl(raw, mode, uid):
    """Linux access ACL encoding: add one named read/search entry.

    Preserve the effective rights of every existing principal, even when
    widening the ACL mask. Never change owner/other rights, grant write, or
    add the account to the egress group. The kernel validates the final ACL.
    """
    owner, user, group_obj, group, mask, other = 1, 2, 4, 8, 16, 32
    undefined = 0xffffffff
    if not 0 < uid < undefined:
        raise RolloutError("Invalid dedicated executor UID")
    if raw is None:
        entries = [(owner, (mode >> 6) & 7, undefined),
                   (group_obj, (mode >> 3) & 7, undefined),
                   (other, mode & 7, undefined)]
    else:
        if (len(raw) < 28 or len(raw) > 65536 or (len(raw)-4) % 8
                or struct.unpack_from("<I", raw)[0] != 2):
            raise RolloutError("Unsupported installed software ACL format")
        entries = list(struct.iter_unpack("<HHI", raw[4:]))
    seen = set()
    for tag, perm, ident in entries:
        if (tag not in (owner,user,group_obj,group,mask,other) or perm & ~7
                or (tag in (user,group)) == (ident == undefined)
                or (tag,ident) in seen):
            raise RolloutError("Invalid installed software ACL entry")
        seen.add((tag,ident))
    base = {tag: perm for tag,perm,ident in entries if ident == undefined}
    if not {owner,group_obj,other}.issubset(base):
        raise RolloutError("Missing base ACL entries")
    if any(tag in (user,group) for tag,_,_ in entries) and mask not in base:
        raise RolloutError("Named ACL entries require a mask")
    old_mask = base.get(mask,base[group_obj])
    if (base[owner] != (mode >> 6) & 7 or base[other] != mode & 7
            or old_mask != (mode >> 3) & 7):
        raise RolloutError("Installed software ACL and mode disagree")
    new_mask = old_mask | 5
    result = []
    for tag,perm,ident in entries:
        if tag == mask or (tag == user and ident == uid):
            continue
        if tag in (user,group_obj,group):
            # Discard only latent rights that would otherwise become effective.
            perm &= old_mask | (~new_mask & 7)
        result.append((tag,perm,ident))
    result.extend(((user,5,uid),(mask,new_mask,undefined)))
    result.sort(key=lambda entry:(entry[0],entry[2]))
    return struct.pack("<I",2) + b"".join(struct.pack("<HHI",*entry) for entry in result)


def grant_executor_code_access(path, uid):
    """Apply a single named Linux directory ACL using the kernel API.

    This does not need the optional acl package (setfacl/getfacl). The
    installed software directory is root-owned; no state or credential
    directory is opened, and no global mode fallback is permitted.
    """
    safe_path(path, Layout())
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        mode = stat.S_IMODE(info.st_mode)
        if info.st_uid != OWNER_UID or mode & 0o022:
            raise RolloutError("Unsafe installed software directory")
        name = "system.posix_acl_access"
        try:
            previous = os.getxattr(fd,name)
        except OSError as exc:
            if exc.errno != errno.ENODATA:
                raise
            previous = None
        wanted = _executor_code_acl(previous,mode,uid)
        if wanted != previous:
            os.setxattr(fd,name,wanted)
        if os.getxattr(fd,name) != wanted:
            raise RolloutError("Installed software ACL did not verify")
    finally:
        os.close(fd)


def prepare_default_executor():
    """Prepare an isolated non-admin OS account; never activate MCP access.

    Called only by the real Server installer/updater. Existing operator
    profiles, accounts, policy, state and service gates remain untouched.
    """
    require_root()
    if state(Layout().target(TARGETS[-1]), Layout()) is not None:
        return {"status": "existing explicit profile preserved", "remote_execution": "unchanged"}
    safe_path(DEFAULT_WORKSPACE.parent, Layout())
    try:
        account = pwd.getpwnam(DEFAULT_EXECUTOR)
    except KeyError:
        try:
            grp.getgrnam(DEFAULT_EXECUTOR)
        except KeyError:
            pass
        else:
            raise RolloutError("Dedicated executor group already exists without its account")
        nologin = shutil.which("nologin") or "/sbin/nologin"
        subprocess.run(["useradd", "--system", "--user-group", "--no-create-home",
                        "--home-dir", str(DEFAULT_WORKSPACE), "--shell", nologin,
                        DEFAULT_EXECUTOR], check=True, timeout=20)
        account = pwd.getpwnam(DEFAULT_EXECUTOR)
    if (account.pw_uid <= 0 or account.pw_gid <= 0
            or account.pw_dir != str(DEFAULT_WORKSPACE)
            or Path(account.pw_shell).name != "nologin"
            or grp.getgrgid(account.pw_gid).gr_name != DEFAULT_EXECUTOR
            or set(os.getgrouplist(account.pw_name, account.pw_gid)) != {account.pw_gid}):
        raise RolloutError("Existing dedicated executor account does not match the isolated profile")
    # No recursive chmod/chown, no change to existing foreign paths.
    try:
        DEFAULT_WORKSPACE.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        created = False
    fd = os.open(DEFAULT_WORKSPACE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if created:
            os.fchown(fd, account.pw_uid, account.pw_gid)
            os.fchmod(fd, 0o700)
        info = os.fstat(fd)
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (account.pw_uid, account.pw_gid, 0o700):
            raise RolloutError("Existing executor workspace ownership/mode is unsafe; left unchanged")
    finally:
        os.close(fd)
    # The worker runs as the selected account, not Bridge root. Only the
    # installed software directory may receive a narrow traversal ACL.
    lib = Path("/usr/local/lib/drlink")
    safe_path(lib, Layout())
    def can_import():
        result = subprocess.run(
            [sys.executable, "-I", "-c",
             "import sys;sys.path.insert(0,'/usr/local/lib/drlink');import drlink_mcp_full_control"],
            cwd="/", env={"PATH":"/usr/bin:/bin", "HOME":str(DEFAULT_WORKSPACE), "LANG":"C.UTF-8"},
            user=account.pw_uid, group=account.pw_gid, extra_groups=[],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=15, check=False)
        return result.returncode == 0
    if not can_import():
        grant_executor_code_access(lib,account.pw_uid)
        if not can_import():
            raise RolloutError("Dedicated executor cannot load installed software; review local ACL support")
    return {"status":"prepared", "account":DEFAULT_EXECUTOR, "workspace":str(DEFAULT_WORKSPACE),
            "remote_execution":"unchanged; requires explicit local opt-in"}


def running_profile_environment():
    """Read only execution keys from the same verified live Bridge process."""
    def pid():
        out = subprocess.check_output(
            ["/usr/bin/systemctl", "show", UNIT, "--property=MainPID", "--value"],
            text=True, timeout=5)
        return int(out.strip())
    current = pid()
    if current <= 1:
        raise RolloutError("Bridge process is not running")
    with open("/proc/%d/environ" % current, "rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024 or pid() != current:
        raise RolloutError("Could not verify the active execution profile")
    allowed = {"DRLINK_MCP_SERVER_" + key for key in (
        "SELF_ENABLED", "LOCAL_EXEC_ENABLED", "FULL_CONTROL_ENABLED", "ADMIN_ENABLED",
        "ALLOWED_ROOTS", "EXEC_USER", "DEFAULT_CWD", "EXEC_ACCOUNTS", "READ_USER",
        "LEGACY_ACCOUNT", "LEGACY_RULE_IDS")}
    allowed.add("DRLINK_MCP_OAUTH_OPERATOR_IDENTITY")
    values = {}
    for item in raw.split(b"\0"):
        key, sep, value = item.partition(b"=")
        if sep and key.decode("ascii", errors="ignore") in allowed:
            values[key.decode("ascii")] = value.decode("utf-8")
    return values


def verify_installed_profile(settings):
    actual = running_profile_environment()
    wanted = _profile_environment(settings)
    if settings.get("approval_identity"):
        wanted["DRLINK_MCP_OAUTH_OPERATOR_IDENTITY"] = settings["approval_identity"]
    if any(actual.get(key) != value for key, value in wanted.items()):
        raise RolloutError("Running Bridge profile differs from the approved profile; review existing local overrides")
    if "exec_accounts" in settings:
        for key in ("READ_USER", "LEGACY_ACCOUNT", "LEGACY_RULE_IDS"):
            env = "DRLINK_MCP_SERVER_" + key
            if actual.get(env, "") != wanted.get(env, ""):
                raise RolloutError("Running Bridge account bindings differ from the approved profile")


def read_legacy_rule_snapshot(layout):
    """Read a consistent canonical policy snapshot without changing its DB."""
    if layout.root != Path("/"):
        raise RolloutError("Legacy rule snapshot requires the installed Server database")
    from drlink_control_plane import ControlPlane
    import drlink_v24 as v24
    plane = ControlPlane("/", read_only=True)
    try:
        return v24.snapshot_legacy_server_execution_rules(plane)
    except v24.ControlPlaneError as exc:
        raise RolloutError(str(exc)) from None
    finally:
        plane.close()



def _existing_profile_settings(values, previous_bytes):
    """Recognize only an exact product-managed profile, not arbitrary overrides."""
    prefix = "DRLINK_MCP_SERVER_"
    if any(values.get(prefix + key) != "1" for key in
           ("SELF_ENABLED", "LOCAL_EXEC_ENABLED", "FULL_CONTROL_ENABLED")):
        raise RolloutError("Existing execution profile is not verified active")
    roots = values.get(prefix + "ALLOWED_ROOTS", "").split(os.pathsep)
    admin = values.get(prefix + "ADMIN_ENABLED") == "1"
    identity = values.get("DRLINK_MCP_OAUTH_OPERATOR_IDENTITY")
    if prefix + "EXEC_ACCOUNTS" in values:
        from drlink_mcp_full_control import _profile_accounts
        accounts = _profile_accounts(values)
        previous = {"exec_accounts": accounts, "roots": roots, "admin": admin,
                    "reader": values.get(prefix + "READ_USER") or None}
        if prefix + "LEGACY_ACCOUNT" in values:
            previous["legacy_account"] = values[prefix + "LEGACY_ACCOUNT"] or None
            previous["legacy_rules"] = json.loads(values.get(prefix + "LEGACY_RULE_IDS", "{}"))
        if identity:
            previous["approval_identity"] = identity
    else:
        previous = profile(values.get(prefix + "EXEC_USER"), roots, admin, approval_identity=identity)
    if dropin(previous) != previous_bytes:
        raise RolloutError("Existing operator execution profile differs from its running managed settings; preserve it and review locally")
    wanted = _profile_environment(previous)
    if any(values.get(key) != value for key, value in wanted.items()):
        raise RolloutError("Existing execution profile does not match the running Bridge")
    return previous


def prepare_profile_update(settings, layout=Layout()):
    """Prepare a reviewed additive migration, retaining every old account's authority."""
    target = layout.target(TARGETS[-1])
    previous_state = state(target, layout)
    if previous_state is None or previous_state["sha256"] == digest(dropin(settings)):
        return {"settings": settings, "previous": previous_state, "migration": False}
    if "exec_accounts" not in settings:
        raise RolloutError("An existing operator execution profile differs; preserve it and review locally")
    previous_bytes = target.read_bytes()
    previous_values = running_profile_environment()
    previous = _existing_profile_settings(previous_values, previous_bytes)
    proposed = json.loads(json.dumps(settings))
    if "exec_accounts" in previous:
        existing = previous["exec_accounts"]
        if previous.get("reader") != proposed.get("reader"):
            raise RolloutError("Changing an existing read-only account requires explicit Rule migration; existing profile preserved")
        if "legacy_account" in previous:
            proposed["legacy_account"] = previous["legacy_account"]
            proposed["legacy_rules"] = previous["legacy_rules"]
    else:
        name = previous["exec_user"]
        existing = {name: {"uid": previous["uid"], "cwd": previous["roots"][0],
                           "roots": list(previous["roots"])}}
        proposed["legacy_account"] = name
        proposed["legacy_rules"] = read_legacy_rule_snapshot(layout)
    for name, entry in existing.items():
        if name not in proposed["exec_accounts"]:
            raise RolloutError("Retain existing execution account '%s' during migration; no changes applied" % name)
        if proposed["exec_accounts"][name]["uid"] != entry["uid"]:
            raise RolloutError("Existing execution UID changed; no changes applied")
        # Existing scope and initial cwd are immutable in this additive operation.
        preserved = dict(entry)
        preserved.setdefault("roots", list(previous["roots"]))
        proposed["exec_accounts"][name] = preserved
    proposed["roots"] = list(dict.fromkeys([*previous["roots"], *proposed["roots"]]))
    if previous.get("approval_identity"):
        proposed["approval_identity"] = previous["approval_identity"]
    if previous["admin"] and not proposed["admin"]:
        raise RolloutError("Existing administrative authority must be reviewed explicitly")
    return {"settings": proposed, "previous": previous_state, "migration": True,
            "previous_bytes": previous_bytes, "previous_values": previous_values,
            "legacy_count": len(proposed.get("legacy_rules", {}))}


def verify_selected_worker(settings, layout=Layout()):
    """Verify the selected account can load code and enter each approved root."""
    if "exec_accounts" in settings:
        for name, entry in settings["exec_accounts"].items():
            verify_selected_worker({"exec_user":name, "uid":entry["uid"],
                                    "roots":list(dict.fromkeys([*entry.get("roots", settings["roots"]),entry["cwd"]]))}, layout)
        return
    account = pwd.getpwnam(settings["exec_user"])
    if account.pw_uid != settings["uid"]:
        raise RolloutError("Execution account changed after review")
    library = layout.root / "usr/local/lib/drlink"
    result = subprocess.run(
        [sys.executable, "-I", "-c",
         "import os,sys;sys.path.insert(0,sys.argv[1]);import drlink_mcp_full_control;sys.exit(0 if all(os.path.isdir(p) and os.access(p,os.X_OK) for p in sys.argv[2:]) else 1)",
         str(library), *settings["roots"]],
        cwd="/", env={"PATH":"/usr/bin:/bin", "HOME":account.pw_dir, "LANG":"C.UTF-8"},
        user=account.pw_uid, group=account.pw_gid,
        extra_groups=os.getgrouplist(account.pw_name, account.pw_gid),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=15, check=False)
    if result.returncode:
        raise RolloutError("Selected account cannot load installed code or enter the approved roots; no changes applied")


def configure_installed(settings, layout=Layout(), *, reviewed=None):
    """Configure ONLY the existing local execution profile of installed code.

    No source checkout or software replacement. Existing explicitly configured
    native profiles are never silently overwritten. Use the previous rollout
    workflow for an intentionally changed existing profile.
    """
    require_root()
    for name in (*TARGETS[:-1], *("usr/local/lib/drlink/" + n for n in DEPENDENCIES)):
        if state(layout.target(name) if name in TARGETS else layout.root / name, layout) is None:
            raise RolloutError("Installed Native MCP runtime is incomplete; update the Server first")
    target = layout.target(TARGETS[-1])
    previous = state(target, layout)
    # Reuse the existing profile format and location, not a second policy.
    proposed = dropin(settings)
    if previous is not None and previous["sha256"] == digest(proposed):
        verify_installed_profile(settings)
        return {"status": "already configured", "service": UNIT, "ai_access": "unchanged"}
    replacing = previous is not None
    if replacing:
        if (not reviewed or not reviewed.get("migration") or reviewed["settings"] != settings
                or reviewed["previous"] != previous or reviewed["previous_bytes"] != target.read_bytes()
                or reviewed["previous_values"] != running_profile_environment()):
            raise RolloutError("An existing operator execution profile differs or changed after review; preserve it and review locally")
    verify_selected_worker(settings, layout)
    service("is-active")
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    safe_path(target, layout)
    # A reviewed migration replaces only the exact previously approved bytes.
    if replacing:
        if state(target, layout) != previous:
            raise RolloutError("Existing execution profile changed after review")
        atomic_write(target, proposed, mode=previous["mode"], uid=previous["uid"], gid=previous["gid"])
    else:
        _publish_new_profile(target, proposed)
    try:
        restart_bridge()
        verify_installed_profile(settings)
    except Exception as failure:
        try:
            if state(target, layout) is None or digest(target.read_bytes()) != digest(proposed):
                raise RolloutError("Local configuration changed during activation; manual review required")
            if replacing:
                atomic_write(target, reviewed["previous_bytes"], mode=previous["mode"],
                             uid=previous["uid"], gid=previous["gid"])
            else:
                target.unlink()
            restart_bridge()
            if replacing and running_profile_environment() != reviewed["previous_values"]:
                raise RolloutError("Restored profile is not confirmed active")
        except Exception as restore_failure:
            raise RolloutError("Local execution setup failed; rollback requires local review") from restore_failure
        raise RolloutError("Local execution setup failed and was rolled back") from failure
    return {"status": "migrated" if replacing else "configured", "service": UNIT, "ai_access": "unchanged"}


def _publish_new_profile(target, proposed):
    fd, staging = tempfile.mkstemp(prefix=".native-profile-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o644)
            os.fchown(stream.fileno(), OWNER_UID, OWNER_GID)
            stream.write(proposed)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staging, target, follow_symlinks=False)
    finally:
        os.unlink(staging)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read-only plan; the default")
    mode.add_argument("--apply", action="store_true", help="Apply the exact clean candidate as root")
    mode.add_argument("--rollback", type=Path, metavar="RECEIPT")
    mode.add_argument("--configure-installed", action="store_true", help="Explicit local setup of the installed execution profile")
    mode.add_argument("--prepare-default", action="store_true", help="Installer-only preparation; does not activate execution")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--head", help="Exact 40-character candidate Git HEAD; required for apply")
    parser.add_argument("--exec-user")
    parser.add_argument("--exec-account", action="append", default=[])
    parser.add_argument("--read-user")
    parser.add_argument("--allowed-root", action="append", default=[])
    parser.add_argument("--allow-root", action="store_true", help="Explicit opt-in for execution UID 0")
    parser.add_argument("--approval-ai-identity", help="Verified AI Identity shown in unbound OAuth operator commands (display only)")
    args = parser.parse_args(argv)
    try:
        if args.rollback:
            result = rollback(args.rollback)
        elif args.prepare_default:
            result = prepare_default_executor()
        else:
            if args.exec_account:
                if not args.configure_installed or args.exec_user or args.approval_ai_identity:
                    raise RolloutError("Multiple execution accounts require installed local configuration")
                settings = multi_account_profile(args.exec_account, args.allowed_root, args.allow_root,
                                                 reader=args.read_user)
            else:
                if args.read_user:
                    raise RolloutError("--read-user requires --exec-account")
                settings = profile(args.exec_user, args.allowed_root, args.allow_root,
                                   approval_identity=args.approval_ai_identity)
            if args.configure_installed:
                if not sys.stdin.isatty() or not sys.stdout.isatty():
                    raise RolloutError("Installed execution setup requires a local interactive administrator")
                reviewed = prepare_profile_update(settings)
                settings = reviewed["settings"]
                if reviewed["migration"]:
                    print("Existing accounts retain their exact local roots and default directories.")
                    print("Legacy Rule snapshots retained: %d; edited Rules need explicit account review." % reviewed["legacy_count"])
                if "exec_accounts" in settings:
                    for account, entry in settings["exec_accounts"].items():
                        print("Eligible execution account: %s (UID %s; default cwd %s)" %
                              (account, entry["uid"], entry["cwd"]))
                        print("  Approved roots: " + ", ".join(entry.get("roots", settings["roots"])))
                    print("Read-only executor: " + (settings.get("reader") or "not configured"))
                    print("AI Access rules separately grant a subset and default; no AI rights are created.")
                else:
                    print("Execution account: " + settings["exec_user"])
                print("Allowed initial directories / file roots: " + ", ".join(settings["roots"]))
                print("General commands have the selected account's real OS authority; not a filesystem sandbox.")
                if input("Activate this existing execution profile? [y/N]: ").strip().lower() not in ("y", "yes"):
                    print(json.dumps({"status": "cancelled", "ai_access": "unchanged"}))
                    return 0
                if settings["admin"] and input("Separately approve UID 0 administrative execution? [y/N]: ").strip().lower() not in ("y", "yes"):
                    print(json.dumps({"status": "cancelled", "ai_access": "unchanged"}))
                    return 0
                result = configure_installed(settings, reviewed=reviewed)
            else:
                operation = apply if args.apply else check
                result = operation(args.source, args.head, settings)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (RolloutError, OSError, ValueError, KeyError, SyntaxError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
