#!/usr/bin/env python3
"""Operator-applied DRLink v2.4 Server Native MCP development preview.

The existing Server/Agent/MCP units, database files and public listeners are
never overwritten. This creates a separate root-owned code snapshot and
loopback-only systemd unit. The Server-local executor stays disabled.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

SOURCE = Path(__file__).resolve().parent.parent
SERVICE = "drlink-mcp-native-preview.service"
UNIT = Path("/etc/systemd/system") / SERVICE
PORT = 16106
ROOT_INSTALL = Path("/opt/drlink-native-mcp-preview/releases")
DB = Path("/var/lib/drlink/drlink.db")
PUBLIC = "https://access.xdr.ooo/mcp"


def command(args: list[str], *, check: bool = True, capture: bool = True):
    return subprocess.run(args, check=check, capture_output=capture, text=True)


def source_head() -> str:
    result = command(["git", "-c", f"safe.directory={SOURCE}",
                      "-C", str(SOURCE), "rev-parse", "HEAD"])
    return result.stdout.strip()


def source_integrity(expected: str):
    actual = source_head()
    if actual != expected:
        raise RuntimeError(f"Candidate HEAD mismatch: actual {actual}; expected {expected}")
    for cmd in (["diff", "--quiet"], ["diff", "--cached", "--quiet"]):
        code = command(["git", "-c", f"safe.directory={SOURCE}",
                        "-C", str(SOURCE), *cmd], check=False)
        if code.returncode:
            raise RuntimeError("Candidate worktree has uncommitted tracked changes")
    expected_content = (SOURCE / "lib/drlink_mcp_server_executor.py").read_bytes()
    committed = subprocess.check_output(["git", "-c", f"safe.directory={SOURCE}",
                                         "-C", str(SOURCE), "show",
                                         expected + ":lib/drlink_mcp_server_executor.py"])
    if expected_content != committed:
        raise RuntimeError("Executor source does not match exact candidate HEAD")
    print(f"SOURCE_HEAD_PASS={actual}")


def port_available() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", PORT))
            return True
        except OSError:
            return False


def public_tls_status() -> str:
    try:
        with urllib.request.urlopen("https://access.xdr.ooo/.well-known/oauth-protected-resource",
                                    timeout=4) as resp:
            return f"HTTPS_{resp.status}"
    except Exception as exc:
        # Only the failure class, never certificate data or authentication material.
        return type(exc).__name__


def preflight(expected: str):
    source_integrity(expected)
    if not port_available() and os.geteuid() != 0:
        raise RuntimeError(f"Loopback TCP port {PORT} is already occupied")
    if os.geteuid() == 0:
        command(["systemctl", "is-active", "--quiet", "drlink-server.service"])
        if UNIT.exists():
            raise RuntimeError(f"Preview unit already exists: {UNIT}. Use --verify or --rollback.")
        if not port_available():
            raise RuntimeError(f"Loopback TCP port {PORT} is already occupied")
        if not DB.is_file():
            raise RuntimeError("Server authoritative DB not found; refusing preview")
        with sqlite3.connect("file:" + str(DB) + "?mode=ro", uri=True) as conn:
            migration_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            ai_table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ai_policy_rules'"
            ).fetchone()
            if not migration_table or not ai_table:
                raise RuntimeError("Missing authoritative v2.4 control-plane tables")
            schema_version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()[0]
            if schema_version != 2:
                raise RuntimeError(f"Unexpected control DB schema {schema_version}; no changes applied")
        print("LIVE_CONTROL_DB_SCHEMA=PASS")
    print(f"LOOPBACK_PORT={PORT}")
    print("SERVER_SELF_ENABLED=1")
    print("SERVER_LOCAL_EXEC_ENABLED=0")
    print(f"PUBLIC_TLS_STATUS={public_tls_status()}")
    print("PREFLIGHT=PASS")


def immutable_snapshot(expected: str) -> Path:
    dest = ROOT_INSTALL / expected
    if dest.exists():
        raise RuntimeError("Immutable snapshot already exists; refusing overwrite")
    ROOT_INSTALL.mkdir(parents=True, exist_ok=True, mode=0o755)
    archive = subprocess.check_output(
        ["git", "-c", f"safe.directory={SOURCE}", "-C", str(SOURCE),
         "archive", "--format=tar", expected, "lib", "server", "VERSION"]
    )
    with tempfile.TemporaryDirectory(prefix=".native-mcp-", dir=str(ROOT_INSTALL)) as work:
        temp = Path(work)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
            for entry in tf.getmembers():
                rel = Path(entry.name)
                if rel.is_absolute() or ".." in rel.parts or not (
                        rel.parts and rel.parts[0] in ("lib", "server", "VERSION")):
                    raise RuntimeError("Unsafe archive path")
                if not (entry.isfile() or entry.isdir()):
                    raise RuntimeError("Unsupported archive object")
                if entry.name != "VERSION" and not entry.name.startswith(("lib/", "server/")) and entry.name not in ("lib", "server"):
                    raise RuntimeError("Unexpected archive member")
            tf.extractall(temp, filter="data")
        if not (temp / "lib/drlink_mcp_server_executor.py").is_file():
            raise RuntimeError("Server executor absent from immutable snapshot")
        if not (temp / "lib/drlink_mcp_bridge.py").is_file():
            raise RuntimeError("MCP Bridge absent from immutable snapshot")
        for file in temp.rglob("*"):
            if file.is_file():
                file.chmod(0o644)
            elif file.is_dir():
                file.chmod(0o755)
        os.replace(temp, dest)
    return dest


def backup_db() -> Path:
    root = Path("/var/backups/drlink-native-mcp-preview")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    dest = root / ("control-db-before-preview-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".sqlite")
    if dest.exists():
        raise RuntimeError("Backup name conflict")
    with sqlite3.connect(str(DB)) as source:
        with sqlite3.connect(str(dest)) as target:
            source.backup(target)
    dest.chmod(0o600)
    # Do not return or print DB contents. Backups are retained for operator recovery.
    return dest


def unit_content(release: Path) -> str:
    return f"""# Managed by operator-native-mcp-preview.py; isolated dev-only preview
[Unit]
Description=Data Relay Link v2.4 Server Native MCP preview
After=network.target drlink-server.service
Requires=drlink-server.service

[Service]
Type=simple
User=root
Group=root
UMask=0077
Environment=DRLINK_MCP_PUBLIC_URL={PUBLIC}
Environment=DRLINK_MCP_SERVER_SELF_ENABLED=1
Environment=DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0
ExecStart=/usr/bin/python3 {release}/lib/drlink_mcp_bridge.py --listen 127.0.0.1 --port {PORT}
Restart=on-failure
RestartSec=4
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/var/lib/drlink
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
"""


def local_probe():
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/mcp",
        data=b'{"jsonrpc":"2.0","method":"tools/list","id":1}',
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4):
            raise RuntimeError("Unauthenticated tools/list unexpectedly succeeded")
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError(f"Unexpected unauthenticated MCP status: {exc.code}") from None
    for suffix in ("/.well-known/oauth-protected-resource",
                   "/.well-known/oauth-authorization-server"):
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{suffix}", timeout=4) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Metadata endpoint status {resp.status}: {suffix}")
            data = json.load(resp)
            if not isinstance(data, dict):
                raise RuntimeError("Invalid MCP/OAuth metadata")
    print("LOCAL_MCP_AUTH_DENIAL=PASS")
    print("LOCAL_OAUTH_METADATA=PASS")


def apply(expected: str):
    if os.geteuid() != 0:
        raise RuntimeError("--apply requires direct operator root execution")
    preflight(expected)
    snapshot = immutable_snapshot(expected)
    backup = backup_db()
    print(f"ROOT_OWNED_SNAPSHOT={snapshot}")
    print(f"DB_BACKUP_CREATED={backup}")
    UNIT.write_text(unit_content(snapshot), encoding="utf-8")
    UNIT.chmod(0o644)
    command(["systemctl", "daemon-reload"])
    command(["systemctl", "start", SERVICE])
    try:
        local_probe()
        command(["systemctl", "is-active", "--quiet", SERVICE])
    except Exception:
        command(["systemctl", "stop", SERVICE], check=False)
        raise
    print("PREVIEW_DEPLOYMENT=PASS")
    print("PUBLIC_TLS_AND_CHATGPT_OAUTH=NOT_VALIDATED")
    print("AI_ACCESS_SERVER_SELF_RULE=NOT_CONFIGURED")


def verify():
    if os.geteuid() == 0:
        command(["systemctl", "is-active", "--quiet", SERVICE])
    local_probe()
    print(f"PUBLIC_TLS_STATUS={public_tls_status()}")
    print("PREVIEW_VERIFY=PASS")


def rollback():
    if os.geteuid() != 0:
        raise RuntimeError("--rollback requires direct operator root execution")
    if not UNIT.exists() or "Managed by operator-native-mcp-preview.py" not in UNIT.read_text():
        raise RuntimeError("Refusing to modify an unmanaged service")
    command(["systemctl", "stop", SERVICE], check=False)
    command(["systemctl", "disable", SERVICE], check=False)
    UNIT.unlink()
    command(["systemctl", "daemon-reload"])
    print("PREVIEW_UNIT_ROLLED_BACK=PASS")
    print("EXISTING_SERVER_AND_BACKUP=PRESERVED")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--expected-head", default="")
    args = parser.parse_args()
    try:
        if args.preflight or args.apply:
            if len(args.expected_head) != 40:
                raise RuntimeError("--expected-head requires a full 40-character source commit")
            (apply if args.apply else preflight)(args.expected_head)
        elif args.verify:
            verify()
        else:
            rollback()
    except (RuntimeError, OSError, subprocess.CalledProcessError, sqlite3.Error) as exc:
        print(f"PREVIEW_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
