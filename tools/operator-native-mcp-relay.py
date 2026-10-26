#!/usr/bin/env python3
"""Isolated /access/mcp HTTPS relay route on the existing DRLink frontend.

This does NOT install an Agent, change a certificate, alter FRP's :443 SNI,
or retarget the central /mcp. It includes narrowly scoped Nginx locations in
the existing publicly trusted mcp.xdr.ooo TLS virtual host, forwarding to the
already established SSH reverse port 127.0.0.1:16107 on this relay machine.

Administrator-only command. Exact byte backups, nginx -t and rollback are
required before changing the running frontend. Public renewal regeneration
can replace the generated frontend config; verify after renewals/upgrades.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

FRONTEND = Path("/etc/drlink/frontend.conf")
INCLUDE = Path("/etc/drlink/native-mcp-access.conf")
STATE_DIR = Path("/var/backups/drlink-native-mcp-access")
STATE = STATE_DIR / "deployment-state.json"
TLS_HOST = "mcp.xdr.ooo"
REMOTE_PORT = 16107
MARKER = "        include /etc/drlink/native-mcp-access.conf;\n"

ROUTES = {
    "/access/mcp": "/mcp",
    "/access/healthz": "/healthz",
    "/access/.well-known/oauth-protected-resource": "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/access/mcp": "/.well-known/oauth-protected-resource/mcp",
    "/access/.well-known/oauth-authorization-server": "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-authorization-server/access": "/.well-known/oauth-authorization-server",
    "/access/oauth/authorize": "/oauth/authorize",
    "/access/oauth/continue": "/oauth/continue",
    "/access/oauth/token": "/oauth/token",
    "/access/oauth/register": "/oauth/register",
    "/access/register": "/register",
    "/access/oauth/revoke": "/oauth/revoke",
}


def _run(*args: str):
    return subprocess.run(list(args), check=True, capture_output=True, text=True)


def _checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _config() -> bytes:
    if FRONTEND.is_symlink() or not FRONTEND.is_file() or FRONTEND.stat().st_uid != 0:
        raise RuntimeError("Refusing to modify a non-root-owned or symlinked frontend")
    return FRONTEND.read_bytes()


def _locate_server(text: str) -> tuple[int, int]:
    # Exact vhost and exact SNI-specific cert only. Reject ambiguous templates.
    literal = "        server_name mcp.xdr.ooo;\n"
    if text.count(literal) != 1:
        raise RuntimeError("Expected exactly one mcp.xdr.ooo public TLS vhost")
    start = text.index(literal)
    next_server = text.find("\n    server {", start + len(literal))
    if next_server < 0:
        next_server = len(text)
    piece = text[start:next_server]
    if (
        "listen 443 ssl;" not in text[max(0, start - 100):start] or
        "ssl_certificate /var/lib/drlink/tls/mcp/active/fullchain.pem;" not in piece or
        "ssl_certificate_key /var/lib/drlink/tls/mcp/active/privkey.pem;" not in piece or
        "proxy_pass http://127.0.0.1:6103;" not in piece
    ):
        raise RuntimeError("Public TLS vhost differs from expected DRLink frontend")
    return start, next_server


def fragment() -> bytes:
    parts = ["# Direct Native MCP reverse relay to access.xdr.ooo; no central Agent/Server Peer."]
    for public, backend in ROUTES.items():
        parts.append(f"""location = {public} {{
    proxy_pass http://127.0.0.1:{REMOTE_PORT}{backend};
    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;
    proxy_set_header Mcp-Method $http_mcp_method;
    proxy_set_header Mcp-Name $http_mcp_name;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 180s;
    proxy_send_timeout 180s;
    proxy_connect_timeout 10s;
    proxy_buffering off;
    proxy_request_buffering off;
    add_header X-Accel-Buffering no;
    client_max_body_size 2m;
}}
""")
    return ("\n".join(parts) + "\n").encode("utf-8")


def candidate(before: bytes) -> bytes:
    text = before.decode("utf-8")
    start, end = _locate_server(text)
    if MARKER in text:
        raise RuntimeError("Native route already exists; use --verify")
    anchor = "        ssl_prefer_server_ciphers off;\n"
    chunk = text[start:end]
    if chunk.count(anchor) != 1:
        raise RuntimeError("Public TLS anchor does not match expected frontend")
    return (text[:start] + chunk.replace(anchor, anchor + MARKER, 1) + text[end:]).encode()


def _atomic(path: Path, payload: bytes, mode: int):
    fd, tmp = tempfile.mkstemp(prefix=".native-mcp-", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
        df = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(df)
        finally:
            os.close(df)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _port_ready():
    with socket.create_connection(("127.0.0.1", REMOTE_PORT), timeout=3):
        return True


def _ensure_root():
    if os.geteuid() != 0:
        raise RuntimeError("Run this operator command as root")


def preflight():
    original = _config()
    proposed = candidate(original)
    _port_ready()
    if INCLUDE.exists() or STATE.exists():
        raise RuntimeError("Native route already installed or a prior deployment exists")
    if not (proposed and fragment()):
        raise RuntimeError("Empty proxy candidate")
    _run("nginx", "-t", "-c", str(FRONTEND))
    print("NATIVE_RELAY_PREFLIGHT=PASS")
    print("PUBLIC_TLS_HOST=" + TLS_HOST)
    print("ACCESS_MCP_ROUTE=https://mcp.xdr.ooo/access/mcp")
    print("PUBLIC_DEFAULT_MCP=PRESERVED")


def apply():
    _ensure_root()
    preflight()
    if STATE_DIR.exists() and STATE_DIR.is_symlink():
        raise RuntimeError("Backup state symlink denied")
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    before = _config()
    after = candidate(before)
    file_mode = stat.S_IMODE(FRONTEND.stat().st_mode)
    backup = STATE_DIR / ("frontend-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".conf")
    if backup.exists():
        raise RuntimeError("Backup name collision")
    _atomic(backup, before, 0o600)
    changed = False
    try:
        _atomic(INCLUDE, fragment(), 0o644)
        _atomic(FRONTEND, after, file_mode)
        changed = True
        _run("nginx", "-t", "-c", str(FRONTEND))
        _run("systemctl", "reload", "drlink-frontend.service")
        _atomic(STATE, json.dumps({
            "backup": str(backup), "frontend_before_sha256": _checksum(before),
            "frontend_after_sha256": _checksum(after),
            "fragment_sha256": _checksum(fragment()),
        }, sort_keys=True).encode(), 0o600)
    except Exception:
        if changed:
            _atomic(FRONTEND, before, file_mode)
            _run("nginx", "-t", "-c", str(FRONTEND))
            _run("systemctl", "reload", "drlink-frontend.service")
        if INCLUDE.exists():
            INCLUDE.unlink()
        raise
    print("NATIVE_RELAY_APPLIED=PASS")
    print("PUBLIC_DEFAULT_MCP=PRESERVED")
    print("ACCESS_MCP_ROUTE=https://mcp.xdr.ooo/access/mcp")
    print("BACKUP_CREATED=" + str(backup))


def _load_state():
    if not STATE.is_file() or STATE.is_symlink():
        raise RuntimeError("No managed Native relay state")
    saved = json.loads(STATE.read_text("utf-8"))
    if not isinstance(saved, dict):
        raise RuntimeError("Invalid managed deployment state")
    return saved


def verify():
    _ensure_root()
    saved = _load_state()
    before = _config()
    if _checksum(before) != saved["frontend_after_sha256"]:
        raise RuntimeError("Frontend changed since Native MCP route installation")
    if not INCLUDE.is_file() or INCLUDE.is_symlink():
        raise RuntimeError("Native MCP snippet absent")
    if _checksum(INCLUDE.read_bytes()) != saved["fragment_sha256"]:
        raise RuntimeError("Native MCP snippet unexpectedly changed")
    _port_ready()
    _run("nginx", "-t", "-c", str(FRONTEND))
    _run("systemctl", "is-active", "--quiet", "drlink-frontend.service")
    print("NATIVE_RELAY_VERIFY=PASS")
    print("ACCESS_MCP_ROUTE=https://mcp.xdr.ooo/access/mcp")


def rollback():
    _ensure_root()
    saved = _load_state()
    current = _config()
    if _checksum(current) != saved["frontend_after_sha256"]:
        raise RuntimeError("Refusing rollback: frontend differs from managed release")
    backup = Path(saved["backup"])
    if backup.parent != STATE_DIR or backup.is_symlink() or not backup.is_file():
        raise RuntimeError("Managed frontend backup absent")
    original = backup.read_bytes()
    if _checksum(original) != saved["frontend_before_sha256"]:
        raise RuntimeError("Backup hash mismatch")
    _atomic(FRONTEND, original, stat.S_IMODE(FRONTEND.stat().st_mode))
    _run("nginx", "-t", "-c", str(FRONTEND))
    _run("systemctl", "reload", "drlink-frontend.service")
    INCLUDE.unlink()
    STATE.unlink()
    print("NATIVE_RELAY_ROLLBACK=PASS")
    print("PRIMARY_MCP_TLS_AND_FRP=PRESERVED")


def main():
    parser = argparse.ArgumentParser(description="Existing trusted TLS Native MCP relay")
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("preflight", "apply", "verify", "rollback"):
        modes.add_argument("--" + name, action="store_true")
    opts = parser.parse_args()
    try:
        if opts.preflight: preflight()
        elif opts.apply: apply()
        elif opts.verify: verify()
        else: rollback()
    except (RuntimeError, OSError, subprocess.CalledProcessError, ValueError, KeyError) as exc:
        print("NATIVE_RELAY_ERROR=" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
