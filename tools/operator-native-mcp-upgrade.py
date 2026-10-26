#!/usr/bin/env python3
"""One-time immutable Native MCP Preview upgrade, preserving existing services.

Target: access.xdr.ooo local Preview only; never touch root FRP :443 or
the standard MCP Bridge. The public HTTPS/OAuth issuer is provided by an
isolated TLS frontend route at mcp.xdr.ooo/access/mcp. After install the
Server-local developer executor intentionally stays OFF until separately
authorized by the operator.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

SOURCE = Path(__file__).resolve().parent.parent
OPERATOR = SOURCE / "tools/operator-native-mcp-preview.py"
SPEC = importlib.util.spec_from_file_location("native_mcp_preview", OPERATOR)
assert SPEC and SPEC.loader
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)

PUBLIC_RESOURCE = "https://mcp.xdr.ooo/access/mcp"
PUBLIC_ISSUER = "https://mcp.xdr.ooo/access"
BACKUP_DIR = Path("/var/backups/drlink-native-mcp-preview")
STATE = BACKUP_DIR / "native-mcp-upgrade-state.json"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save(path: Path, data: bytes, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".native-mcp-", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _unit_sha(unit: str) -> str:
    matches = re.findall(
        r"^ExecStart=/usr/bin/python3 " + re.escape(str(preview.ROOT_INSTALL)) +
        r"/([0-9a-f]{40})/lib/drlink_mcp_bridge\.py --listen 127\.0\.0\.1 --port " +
        str(preview.PORT) + "$",
        unit,
        re.M,
    )
    if len(matches) != 1:
        raise RuntimeError("The live Native MCP Preview is not pinned to an immutable SHA")
    return matches[0]


def _upgraded_unit(release: Path) -> str:
    text = preview.unit_content(release)
    original = "Environment=DRLINK_MCP_SERVER_SELF_ENABLED=1\n"
    if text.count(original) != 1:
        raise RuntimeError("Unexpected Native MCP Preview service template")
    return text.replace(
        original, original +
        "Environment=DRLINK_MCP_NATIVE_PUBLIC_URL=" + PUBLIC_RESOURCE + "\n",
        1,
    )


def _current_unit() -> tuple[str, str]:
    unit = preview.UNIT
    if not preview.root_owned(unit):
        raise RuntimeError("Expected root-owned Native MCP Preview unit missing")
    text = unit.read_text("utf-8")
    sha = _unit_sha(text)
    old = preview.unit_content(preview.ROOT_INSTALL / sha)
    newer = _upgraded_unit(preview.ROOT_INSTALL / sha)
    if text not in (old, newer):
        raise RuntimeError("Native MCP Preview service differs from managed template")
    return text, sha


def metadata_probe():
    preview.wait_ready()
    urls = (
        ("http://127.0.0.1:%s/.well-known/oauth-protected-resource" % preview.PORT,
         "resource", PUBLIC_RESOURCE),
        ("http://127.0.0.1:%s/.well-known/oauth-authorization-server" % preview.PORT,
         "issuer", PUBLIC_ISSUER),
    )
    for url, key, expected in urls:
        with urllib.request.urlopen(url, timeout=5) as response:
            obj = json.load(response)
            if obj.get(key) != expected:
                raise RuntimeError("Native MCP OAuth " + key + " mismatch")


def _root_required():
    if os.geteuid() != 0:
        raise RuntimeError("Root SSH operator required for service replacement")


def preflight(expected: str):
    preview.source_integrity(expected)
    unit, current = _current_unit()
    if STATE.exists():
        raise RuntimeError("An upgrade state already exists; use --verify or --rollback")
    if current == expected:
        raise RuntimeError("This Native MCP Preview already runs the target source")
    if "DRLINK_MCP_NATIVE_PUBLIC_URL=" in unit:
        raise RuntimeError("Native MCP Preview public route was already upgraded")
    if not preview.root_owned(preview.ROOT_INSTALL / current, directory=True):
        raise RuntimeError("Previous root-owned immutable MCP release is unavailable")
    if (preview.ROOT_INSTALL / expected).exists():
        raise RuntimeError("New candidate release snapshot already exists; do not overwrite")
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])
    print("NATIVE_UPGRADE_PREFLIGHT=PASS")
    print("PREVIOUS_IMMUTABLE_SHA=" + current)
    print("TARGET_IMMUTABLE_SHA=" + expected)
    print("CANONICAL_MCP_RESOURCE=" + PUBLIC_RESOURCE)
    print("DEFAULT_MCP_AND_FRP=PRESERVED")


def _restore_old(unit: str):
    _save(preview.UNIT, unit.encode("utf-8"), 0o644)
    preview.command(["systemctl", "daemon-reload"])
    preview.command(["systemctl", "restart", preview.SERVICE])
    preview.wait_ready()
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])


def apply(expected: str):
    _root_required()
    preflight(expected)
    old_unit, old_sha = _current_unit()
    latest = preview.immutable_snapshot(expected)
    backup = BACKUP_DIR / ("native-unit-before-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".service")
    if backup.exists():
        raise RuntimeError("Native MCP backup name collision")
    _save(backup, old_unit.encode("utf-8"), 0o600)
    new_unit = _upgraded_unit(latest)
    try:
        _save(preview.UNIT, new_unit.encode("utf-8"), 0o644)
        preview.command(["systemctl", "daemon-reload"])
        preview.command(["systemctl", "restart", preview.SERVICE])
        metadata_probe()
        preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])
    except Exception:
        _restore_old(old_unit)
        raise
    _save(STATE, json.dumps({
        "from": old_sha, "to": expected, "backup": str(backup),
        "old_sha256": _hash(old_unit.encode("utf-8")),
        "new_sha256": _hash(new_unit.encode("utf-8")),
    }, sort_keys=True).encode("utf-8"))
    print("NATIVE_MCP_UPGRADED=PASS")
    print("NATIVE_MCP_OAUTH_METADATA=PASS")
    print("SERVER_LOCAL_EXEC_ENABLED=0")
    print("ORIGINAL_MCP_AND_FRP=PRESERVED")


def _state() -> dict:
    if not STATE.is_file() or STATE.is_symlink():
        raise RuntimeError("Native MCP upgrade state not installed")
    value = json.loads(STATE.read_text("utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Native MCP upgrade state is invalid")
    return value


def verify():
    _root_required()
    state = _state()
    now, source = _current_unit()
    if source != state["to"] or _hash(now.encode()) != state["new_sha256"]:
        raise RuntimeError("Installed Native MCP unit does not match recorded upgrade")
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])
    metadata_probe()
    print("NATIVE_MCP_UPGRADE_VERIFY=PASS")
    print("CANONICAL_MCP_RESOURCE=" + PUBLIC_RESOURCE)


def rollback():
    _root_required()
    state = _state()
    now, source = _current_unit()
    if source != state["to"] or _hash(now.encode()) != state["new_sha256"]:
        raise RuntimeError("Cannot roll back a modified Native MCP Preview unit")
    path = Path(state["backup"])
    if path.parent != BACKUP_DIR or path.is_symlink() or not path.is_file():
        raise RuntimeError("Original Native MCP service backup absent")
    old = path.read_bytes()
    if _hash(old) != state["old_sha256"]:
        raise RuntimeError("Original Native MCP service backup hash mismatch")
    _restore_old(old.decode("utf-8"))
    STATE.unlink()
    print("NATIVE_MCP_UPGRADE_ROLLBACK=PASS")
    print("PREVIOUS_IMMUTABLE_SHA=" + state["from"])


def main():
    parser = argparse.ArgumentParser(description="Pinned Native MCP Preview upgrade")
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("preflight", "apply", "verify", "rollback"):
        modes.add_argument("--" + mode, action="store_true")
    parser.add_argument("--expected-head", default="")
    args = parser.parse_args()
    try:
        if args.preflight or args.apply:
            if not re.fullmatch(r"[0-9a-f]{40}", args.expected_head):
                raise RuntimeError("Exact 40-character Git SHA required")
            (apply if args.apply else preflight)(args.expected_head)
        elif args.verify: verify()
        else: rollback()
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError,
            subprocess.CalledProcessError) as exc:
        print("NATIVE_MCP_UPGRADE_ERROR=" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
