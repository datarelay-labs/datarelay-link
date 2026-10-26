#!/usr/bin/env python3
"""Optional Server-as-Managed-Host peer unit (NO Agent install).

Requires a separately enrolled Server-peer management identity produced by
lib/drlink_server_peer_enroll.py with a real centrally issued Manual Code.
No SSH/FRP Agent installation, no public port, no existing service replacement.
"""
from __future__ import annotations

import argparse
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
ROOT = Path("/var/lib/drlink-server-peer")
RELEASES = Path("/opt/drlink-server-peer/releases")
SERVICE = "drlink-server-peer.service"
UNIT = Path("/etc/systemd/system") / SERVICE


def command(argv, *, check=True):
    return subprocess.run(argv, check=check, capture_output=True, text=True)


def _git(*args):
    # The operator runs this script as root against an explicitly selected
    # developer-owned worktree. Trust only this exact root; never '*' or a
    # mutable, unrelated repository.
    return ["git", "-c", f"safe.directory={SOURCE}", "-C", str(SOURCE), *args]


def source_head():
    return command(_git("rev-parse", "HEAD")).stdout.strip()


def code_matches_head(sha):
    actual = source_head()
    if len(sha) != 40 or sha != actual:
        raise RuntimeError(f"Server Peer source HEAD mismatch: actual {actual}, wanted {sha}")
    files = ("lib/drlink_server_peer.py", "lib/drlink_server_peer_enroll.py",
             "lib/drlink_mcp_server_executor.py", "tools/operator-server-peer.py",
             "tools/operator-server-peer-join.py")
    for file in files:
        local = (SOURCE / file).read_bytes()
        expected = subprocess.check_output(_git("show", sha + ":" + file))
        if local != expected:
            raise RuntimeError(f"Uncommitted Server Peer code: {file}")
    return files


def check_identity():
    sys.path.insert(0, str(SOURCE / "lib"))
    from drlink_server_peer import validate_peer_root
    identity = validate_peer_root(str(ROOT))
    return identity


def remote_probe(snapshot):
    result = command(["/usr/bin/python3", str(snapshot / "lib/drlink_server_peer.py"),
                      "--root", str(ROOT), "--probe-central"])
    if "SERVER_PEER_CENTRAL_AUTH=PASS" not in result.stdout:
        raise RuntimeError("Signed central DRLink management authorization not confirmed")
    return True


def snapshot(sha):
    dst = RELEASES / sha
    if dst.exists() or dst.is_symlink():
        raise RuntimeError("Pinned Server Peer snapshot exists; refusing to overwrite")
    RELEASES.mkdir(parents=True, exist_ok=True)
    archive = subprocess.check_output(_git(
        "archive", "--format=tar", sha, "lib", "VERSION"))
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=str(RELEASES)) as stage:
        out = Path(stage)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
            for entry in tf.getmembers():
                rel = Path(entry.name)
                if rel.is_absolute() or ".." in rel.parts or not (entry.isfile() or entry.isdir()):
                    raise RuntimeError("Unsafe release archive entry")
            tf.extractall(out, filter="data")
        for item in out.rglob("*"):
            if item.is_file():
                item.chmod(0o644)
            if item.is_dir():
                item.chmod(0o755)
        os.replace(out, dst)
    return dst


def unit_text(dst):
    return f"""# Managed by operator-server-peer.py; no Agent product installed.
[Unit]
Description=Data Relay Link Server Peer (native signed Managed Host)
Wants=network-online.target
After=network-online.target drlink-server.service
Requires=drlink-server.service

[Service]
Type=simple
User=root
Group=root
UMask=0077
Environment=DRLINK_SERVER_PEER_ENABLED=1
Environment=DRLINK_SERVER_PEER_READ_ENABLED=0
ExecStart=/usr/bin/python3 {dst}/lib/drlink_server_peer.py --root {ROOT}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=read-only
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
"""


def apply(sha):
    if os.geteuid() != 0:
        raise RuntimeError("Server Peer apply requires root operator")
    code_matches_head(sha)
    if UNIT.exists():
        raise RuntimeError("Server Peer unit already present; do not overwrite")
    check_identity()
    dst = snapshot(sha)
    try:
        remote_probe(dst)
    except Exception:
        # Keep the staged immutable source for diagnosis. No unit created.
        raise RuntimeError("Central signed Server Peer authorization failed; no service installed") from None
    UNIT.write_text(unit_text(dst))
    UNIT.chmod(0o644)
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "start", SERVICE])
    command(["systemctl", "is-active", "--quiet", SERVICE])
    print("SERVER_PEER_SERVICE=PASS")
    print("SERVER_PEER_AGENT_INSTALLED=NO")
    print("CENTRAL_MANAGEMENT_AUTH=PASS")
    print("SERVER_PEER_LOCAL_EXEC=DISABLED")


def _root_owned(path: Path, *, directory: bool = False) -> bool:
    return (not path.is_symlink() and
            (path.is_dir() if directory else path.is_file()) and
            path.stat().st_uid == 0)


def installed_release() -> Path:
    """Bind validation to immutable installed SHA, not a later Git worktree HEAD."""
    if not _root_owned(UNIT):
        raise RuntimeError("Managed root-owned Server Peer unit missing")
    target = UNIT.read_text(encoding="utf-8")
    matches = [line for line in target.splitlines() if line.startswith("ExecStart=")]
    pattern = re.compile(
        r"ExecStart=/usr/bin/python3 " + re.escape(str(RELEASES)) +
        r"/([0-9a-f]{40})/lib/drlink_server_peer\.py --root " + re.escape(str(ROOT))
    )
    if len(matches) != 1:
        raise RuntimeError("Server Peer unit must contain one pinned ExecStart")
    match = pattern.fullmatch(matches[0])
    if match is None:
        raise RuntimeError("Server Peer unit ExecStart does not match pinned release contract")
    dst = RELEASES / match.group(1)
    if not _root_owned(dst, directory=True):
        raise RuntimeError("Root-owned Server Peer release snapshot missing")
    if target != unit_text(dst):
        raise RuntimeError("Server Peer unit differs from trusted managed template")
    for filename in ("lib/drlink_server_peer.py",
                     "lib/drlink_server_peer_enroll.py",
                     "lib/drlink_mcp_server_executor.py"):
        actual = dst / filename
        if not actual.is_file() or actual.is_symlink():
            raise RuntimeError("Server Peer release file missing")
        expected = subprocess.check_output(_git("show", match.group(1) + ":" + filename))
        if actual.read_bytes() != expected:
            raise RuntimeError("Server Peer installed file differs from immutable Git commit")
    return dst


def verify():
    if os.geteuid() != 0:
        raise RuntimeError("Server Peer verify requires root operator")
    check_identity()
    command(["systemctl", "is-active", "--quiet", SERVICE])
    dst = installed_release()
    remote_probe(dst)
    print("SERVER_PEER_VERIFY=PASS")
    print("SERVER_PEER_CENTRAL_AUTH=PASS")


def rollback():
    if os.geteuid() != 0:
        raise RuntimeError("Server Peer rollback requires root operator")
    if not UNIT.is_file() or "Managed by operator-server-peer.py" not in UNIT.read_text():
        raise RuntimeError("Refusing rollback of an unmanaged unit")
    command(["systemctl", "stop", SERVICE], check=False)
    command(["systemctl", "disable", SERVICE], check=False)
    UNIT.unlink()
    command(["systemctl", "daemon-reload"])
    print("SERVER_PEER_UNIT_REMOVED=PASS")
    print("SERVER_PEER_IDENTITY_AND_EXISTING_SERVER=PRESERVED")


def main(argv=None):
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--verify", action="store_true")
    modes.add_argument("--rollback", action="store_true")
    parser.add_argument("--expected-head", default="")
    args = parser.parse_args(argv)
    try:
        if args.preflight or args.apply:
            files = code_matches_head(args.expected_head)
            if args.preflight:
                print("SERVER_PEER_SOURCE=PASS")
                print("SERVER_PEER_AGENT_INSTALL_REQUIRED=NO")
                print("SERVER_PEER_ENROLLMENT=REQUIRED_BEFORE_APPLY")
            else:
                apply(args.expected_head)
        elif args.verify:
            verify()
        else:
            rollback()
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"SERVER_PEER_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
