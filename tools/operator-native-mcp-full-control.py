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
        acl = shutil.which("setfacl")
        if acl:
            subprocess.run([acl, "-m", "u:"+DEFAULT_EXECUTOR+":r-x", str(lib)], check=True, timeout=10)
        if not can_import():
            raise RolloutError("Dedicated executor cannot load installed software; review local ACL support")
    return {"status":"prepared", "account":DEFAULT_EXECUTOR, "workspace":str(DEFAULT_WORKSPACE),
            "remote_execution":"unchanged; requires explicit local opt-in"}


def verify_installed_profile(settings):
    """Check the actual restarted process, not just the generated drop-in."""
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
    actual = dict(item.partition(b"=")[::2] for item in raw.split(b"\0") if b"=" in item)
    wanted = {
        "SELF_ENABLED": "1", "LOCAL_EXEC_ENABLED": "1", "FULL_CONTROL_ENABLED": "1",
        "EXEC_USER": settings["exec_user"], "ALLOWED_ROOTS": os.pathsep.join(settings["roots"]),
        "DEFAULT_CWD": settings["roots"][0], "ADMIN_ENABLED": "1" if settings["admin"] else "0",
    }
    if any(actual.get(("DRLINK_MCP_SERVER_"+key).encode()) != value.encode()
           for key, value in wanted.items()):
        raise RolloutError("Running Bridge profile differs from the approved profile; review existing local overrides")


def verify_selected_worker(settings, layout=Layout()):
    """Verify the selected account can load code and enter each approved root."""
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


def configure_installed(settings, layout=Layout()):
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
    if previous is not None:
        if previous["sha256"] != digest(proposed):
            raise RolloutError("An existing operator execution profile differs; preserve it and review locally")
        verify_installed_profile(settings)
        return {"status": "already configured", "service": UNIT, "ai_access": "unchanged"}
    verify_selected_worker(settings, layout)
    service("is-active")
    target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    safe_path(target, layout)
    # Publish complete bytes with no overwrite. A failed write must not
    # leave a partially active systemd profile.
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
    try:
        restart_bridge()
        verify_installed_profile(settings)
    except Exception as failure:
        try:
            if state(target, layout) is None or digest(target.read_bytes()) != digest(proposed):
                raise RolloutError("Local configuration changed during activation; manual review required")
            target.unlink()
            restart_bridge()
        except Exception as restore_failure:
            raise RolloutError("Local execution setup failed; rollback requires local review") from restore_failure
        raise RolloutError("Local execution setup failed and was rolled back") from failure
    return {"status": "configured", "service": UNIT, "ai_access": "unchanged"}


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
            settings = profile(args.exec_user, args.allowed_root, args.allow_root,
                               approval_identity=args.approval_ai_identity)
            if args.configure_installed:
                if not sys.stdin.isatty() or not sys.stdout.isatty():
                    raise RolloutError("Installed execution setup requires a local interactive administrator")
                print("Execution account: " + settings["exec_user"])
                print("Allowed initial directories / file roots: " + ", ".join(settings["roots"]))
                print("General commands have the selected account's real OS authority; not a filesystem sandbox.")
                if input("Activate this existing execution profile? [y/N]: ").strip().lower() not in ("y", "yes"):
                    print(json.dumps({"status": "cancelled", "ai_access": "unchanged"}))
                    return 0
                if settings["admin"] and input("Separately approve UID 0 administrative execution? [y/N]: ").strip().lower() not in ("y", "yes"):
                    print(json.dumps({"status": "cancelled", "ai_access": "unchanged"}))
                    return 0
                result = configure_installed(settings)
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
