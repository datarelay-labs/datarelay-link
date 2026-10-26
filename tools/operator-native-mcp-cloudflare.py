#!/usr/bin/env python3
"""Non-root Cloudflare Tunnel for access.xdr.ooo Native MCP.

The Cloudflare account owner first creates a remotely managed Tunnel and maps
mcp.link.xdr.ooo -> http://127.0.0.1:16106 in Cloudflare Networking > Tunnels.
The private connector token is entered through a hidden SSH TTY prompt, not a
shell argument or ChatGPT. The tunnel NEVER installs a DRLink Agent, takes
TCP/443, or changes the existing FRP Server and standard MCP service.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HOME = Path("/home/aella")
CLOUDFLARED = Path("/usr/local/bin/cloudflared")
DIR = HOME / ".config/drlink-native-mcp-cloudflare"
TOKEN = DIR / "tunnel-token"
UNIT = HOME / ".config/systemd/user/drlink-native-mcp-cloudflare.service"
NAME = UNIT.name
DOMAIN = "mcp.link.xdr.ooo"
RESOURCE = "https://" + DOMAIN + "/mcp"
ISSUER = "https://" + DOMAIN
LOCAL = "http://127.0.0.1:16106"
MAX_TOKEN_LENGTH = 4096
EXPECTED_UID = 1000


def unit() -> str:
    return f"""# Native MCP only; no public port or FRP mode change.
[Unit]
Description=DataRelay Native MCP Cloudflare HTTPS connector (mcp.link.xdr.ooo)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
UMask=0077
Environment=HOME={HOME}
ExecStart={CLOUDFLARED} tunnel --no-autoupdate --protocol http2 run --token-file {TOKEN}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
"""


def run(*command: str):
    env = dict(os.environ)
    env["XDG_RUNTIME_DIR"] = "/run/user/%s" % os.getuid()
    env["DBUS_SESSION_BUS_ADDRESS"] = (
        "unix:path=" + env["XDG_RUNTIME_DIR"] + "/bus")
    return subprocess.run(command, env=env, check=True, capture_output=True, text=True)


def owner():
    if os.getuid() != EXPECTED_UID or os.geteuid() != EXPECTED_UID:
        raise RuntimeError("Run as the dev-drlink aella SSH user, without sudo")


def _http(path: str, *, data: bytes | None = None):
    url = LOCAL + path
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    request = urllib.request.Request(url, headers=headers, data=data,
                                      method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.status, dict(response.headers), response.read(32768)
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), err.read(32768)


def local_check():
    status, _, _ = _http(
        "/mcp", data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
    if status != 401:
        raise RuntimeError("Native MCP must deny anonymous tools/list with HTTP 401")
    for path in ("/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-authorization-server"):
        status, _, body = _http(path)
        if status != 200 or not isinstance(json.loads(body), dict):
            raise RuntimeError("Native MCP OAuth discovery unavailable")
    return True


def secure_staging():
    owner()
    if not CLOUDFLARED.is_file() or not os.access(CLOUDFLARED, os.X_OK):
        raise RuntimeError("Cloudflared executable missing from expected path")
    if UNIT.is_symlink() or (UNIT.exists() and UNIT.read_text() != unit()):
        raise RuntimeError("Refusing to overwrite an unrelated Cloudflare service")
    if DIR.is_symlink():
        raise RuntimeError("Cloudflare token directory is a symlink")
    if DIR.exists():
        if (DIR.stat().st_uid != os.geteuid() or
                stat.S_IMODE(DIR.stat().st_mode) & 0o077):
            raise RuntimeError("Cloudflare token directory ownership or mode unsafe")
    if TOKEN.exists():
        if (TOKEN.is_symlink() or not TOKEN.is_file()
                or TOKEN.stat().st_uid != os.geteuid()
                or stat.S_IMODE(TOKEN.stat().st_mode) & 0o077):
            raise RuntimeError("Cloudflare token file is unsafe")
    return True


def _atomic(path: Path, payload: bytes):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".token-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def install_unit():
    secure_staging()
    DIR.mkdir(parents=True, mode=0o700, exist_ok=True)
    UNIT.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not UNIT.exists():
        _atomic(UNIT, unit().encode("utf-8"))
        UNIT.chmod(0o644)
    run("systemctl", "--user", "daemon-reload")
    print("CLOUDFLARE_NATIVE_MCP_UNIT=STAGED")
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")


def check():
    secure_staging()
    local_check()
    if UNIT.exists():
        print("CLOUDFLARE_NATIVE_MCP_UNIT=STAGED")
    else:
        print("CLOUDFLARE_NATIVE_MCP_UNIT=NOT_INSTALLED")
    if TOKEN.exists():
        print("CLOUDFLARE_TUNNEL_TOKEN=STORED_PRIVATELY")
    else:
        print("CLOUDFLARE_TUNNEL_TOKEN=NOT_CONFIGURED")
    print("CLOUDFLARE_DASHBOARD_HOSTNAME=" + DOMAIN)
    print("CLOUDFLARE_DASHBOARD_SERVICE_URL=" + LOCAL)
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")
    print("LOCAL_NATIVE_MCP_AUTH_AND_OAUTH=PASS")


def activate():
    install_unit()
    local_check()
    if not TOKEN.exists():
        if not sys.stdin.isatty():
            raise RuntimeError("Interactive SSH terminal required for hidden token entry")
        token = getpass.getpass("Enter Cloudflare Tunnel connector token (input hidden): ").strip()
        try:
            if (len(token) < 40 or len(token) > MAX_TOKEN_LENGTH or
                    not re.fullmatch(r"[A-Za-z0-9._-]+", token) or
                    not token.startswith("eyJ")):
                raise RuntimeError("Cloudflare Tunnel token format invalid")
            _atomic(TOKEN, (token + "\n").encode("ascii"))
        finally:
            token = ""
    run("systemctl", "--user", "enable", "--now", NAME)
    # Guard immediate crashes; activation is NOT proof DNS or OAuth works.
    time.sleep(1)
    run("systemctl", "--user", "is-active", "--quiet", NAME)
    print("CLOUDFLARE_NATIVE_MCP_SERVICE=ACTIVE")
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")
    print("CUSTOM_MCP_URL=" + RESOURCE)
    print("PUBLIC_DNS_AND_OAUTH=VERIFY_SEPARATELY")


def public_verify():
    import ssl
    ctx = ssl.create_default_context()
    for route, field, expected in (
        ("/.well-known/oauth-protected-resource", "resource", RESOURCE),
        ("/.well-known/oauth-authorization-server", "issuer", ISSUER),
    ):
        with urllib.request.urlopen(RESOURCE[:-4] + route, timeout=12, context=ctx) as response:
            data = json.load(response)
            if data.get(field) != expected:
                raise RuntimeError("Public Native MCP " + field + " mismatch")
    req = urllib.request.Request(
        RESOURCE, data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx):
            raise RuntimeError("Public Native MCP unexpectedly allowed anonymous tools")
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError("Public Native MCP returned %s instead of 401" % exc.code) from None
    print("NATIVE_MCP_PUBLIC_TLS=PASS")
    print("NATIVE_MCP_PUBLIC_OAUTH=PASS")
    print("NATIVE_MCP_ANONYMOUS_DENY=PASS")
    print("CUSTOM_CHATGPT_MCP_URL=" + RESOURCE)
    print("ACTUAL_CHATGPT_OAUTH_CONSENT=NOT_YET_TESTED")


def stop():
    secure_staging()
    run("systemctl", "--user", "disable", "--now", NAME)
    print("NATIVE_MCP_CLOUDFLARE_STOPPED=PASS")
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")


def main():
    p = argparse.ArgumentParser(description="Nonroot Cloudflare Tunnel for Native MCP")
    m = p.add_mutually_exclusive_group(required=True)
    for arg in ("check", "stage", "activate", "verify", "stop"):
        m.add_argument("--" + arg, action="store_true")
    args = p.parse_args()
    try:
        if args.check: check()
        elif args.stage: install_unit()
        elif args.activate: activate()
        elif args.verify: public_verify()
        else: stop()
    except (OSError, RuntimeError, ValueError, urllib.error.URLError,
            subprocess.CalledProcessError) as err:
        print("NATIVE_CLOUDFLARE_ERROR=" + type(err).__name__ + ": " + str(err), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
