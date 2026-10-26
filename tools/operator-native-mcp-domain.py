#!/usr/bin/env python3
"""Retarget access.xdr.ooo Native MCP OAuth identity to mcp.link.xdr.ooo.

Only the isolated dev Native MCP Preview service is changed. This does not
change DRLink Server, Agent, FRP 443, or another public MCP hostname.
Protected original service and exact-SHA rollback state are retained.
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
import time
import urllib.request

SOURCE = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "native_mcp_preview_operator", SOURCE / "tools/operator-native-mcp-preview.py")
assert SPEC and SPEC.loader
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)

HOST = "mcp.link.xdr.ooo"
RESOURCE = "https://" + HOST + "/mcp"
ISSUER = "https://" + HOST
PREVIOUS_RESOURCE = "https://mcp.xdr.ooo/access/mcp"
BACKUP_ROOT = Path("/var/backups/drlink-native-mcp-preview")
STATE = BACKUP_ROOT / "native-public-domain-state.json"
ENV_PREFIX = "Environment=DRLINK_MCP_NATIVE_PUBLIC_URL="
MARKER = "Environment=DRLINK_MCP_SERVER_SELF_ENABLED=1\n"


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def old_unit(release: Path) -> str:
    base = preview.unit_content(release)
    if base.count(MARKER) != 1:
        raise RuntimeError("Preview unit no longer matches the managed template")
    return base.replace(MARKER, MARKER + ENV_PREFIX + PREVIOUS_RESOURCE + "\n", 1)


def target_unit(release: Path) -> str:
    return old_unit(release).replace(
        ENV_PREFIX + PREVIOUS_RESOURCE, ENV_PREFIX + RESOURCE, 1)


def installed_release() -> Path:
    if not preview.root_owned(preview.UNIT):
        raise RuntimeError("Managed root-owned Native MCP Preview unit is missing")
    unit = preview.UNIT.read_text(encoding="utf-8")
    matches = re.findall(
        r"^ExecStart=/usr/bin/python3 " + re.escape(str(preview.ROOT_INSTALL)) +
        r"/([0-9a-f]{40})/lib/drlink_mcp_bridge\.py --listen 127\.0\.0\.1 --port " +
        str(preview.PORT) + r"$", unit, re.M)
    if len(matches) != 1:
        raise RuntimeError("Unexpected Native MCP Preview executable")
    path = preview.ROOT_INSTALL / matches[0]
    if not preview.root_owned(path, directory=True):
        raise RuntimeError("Immutable Native MCP release snapshot unavailable")
    return path


def read_live_unit() -> tuple[Path, str]:
    release = installed_release()
    actual = preview.UNIT.read_text(encoding="utf-8")
    if actual not in (old_unit(release), target_unit(release)):
        raise RuntimeError("Refusing to alter an unexpected Native MCP service")
    if "Environment=DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=0" not in actual:
        raise RuntimeError("Native local executor gate must remain disabled during domain change")
    return release, actual


def metadata_probe(resource: str, issuer: str):
    preview.wait_ready(timeout_seconds=15)
    for uri, name, expected in (
        ("/.well-known/oauth-protected-resource", "resource", resource),
        ("/.well-known/oauth-authorization-server", "issuer", issuer),
    ):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (preview.PORT, uri), timeout=5) as resp:
            doc = json.load(resp)
            if not isinstance(doc, dict) or doc.get(name) != expected:
                raise RuntimeError("Native MCP local OAuth identity mismatch: " + name)
    return True


def atomic(path: Path, payload: bytes, mode: int = 0o600):
    import tempfile
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".mcp-domain-", dir=str(path.parent))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def service_reload():
    preview.command(["systemctl", "daemon-reload"])
    preview.command(["systemctl", "restart", preview.SERVICE])
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])


def root_only():
    if os.geteuid() != 0:
        raise RuntimeError("This Native MCP service change requires an authorized root SSH operator")


def check():
    release, current = read_live_unit()
    print("NATIVE_PREVIEW_IMMUTABLE_SHA=" + release.name)
    print("NATIVE_PREVIEW_DOMAIN=" +
          (HOST if current == target_unit(release) else "legacy-mcp.xdr.ooo"))
    print("NATIVE_PREVIEW_SERVICE_GATE=DENY_DEFAULT")
    print("FRP_443_AND_PRIMARY_MCP=UNCHANGED")


def preflight():
    root_only()
    release, current = read_live_unit()
    if current != old_unit(release):
        raise RuntimeError("Native MCP Preview already retargeted; use --verify")
    if STATE.exists():
        raise RuntimeError("An existing Native MCP domain operation must be verified or rolled back")
    metadata_probe(PREVIOUS_RESOURCE, "https://mcp.xdr.ooo/access")
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])
    print("NATIVE_DOMAIN_PREFLIGHT=PASS")
    print("TARGET_PUBLIC_RESOURCE=" + RESOURCE)
    print("FRP_443_AND_PRIMARY_MCP=UNCHANGED")


def apply():
    root_only()
    preflight()
    release, before = read_live_unit()
    after = target_unit(release)
    if STATE.exists():
        raise RuntimeError("Native MCP domain state already exists")
    backup = BACKUP_ROOT / ("native-domain-before-" +
                             time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".service")
    if backup.exists():
        raise RuntimeError("Backup name already used")
    atomic(backup, before.encode("utf-8"))
    try:
        atomic(preview.UNIT, after.encode("utf-8"), mode=0o644)
        service_reload()
        metadata_probe(RESOURCE, ISSUER)
    except Exception:
        atomic(preview.UNIT, before.encode("utf-8"), mode=0o644)
        service_reload()
        metadata_probe(PREVIOUS_RESOURCE, "https://mcp.xdr.ooo/access")
        raise
    atomic(STATE, json.dumps({
        "release": release.name, "backup": str(backup),
        "before_sha256": sha(before.encode("utf-8")),
        "after_sha256": sha(after.encode("utf-8")),
    }, sort_keys=True).encode("utf-8"))
    print("NATIVE_MCP_DOMAIN_APPLIED=PASS")
    print("NATIVE_MCP_OAUTH_RESOURCE=" + RESOURCE)
    print("NATIVE_MCP_LOCAL_EXEC=DISABLED")
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")


def state() -> dict:
    if not preview.root_owned(STATE):
        raise RuntimeError("Managed root-owned Native MCP domain state missing")
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("Invalid Native domain state")
    return value


def verify():
    root_only()
    st = state()
    release, unit = read_live_unit()
    if release.name != st["release"] or unit != target_unit(release):
        raise RuntimeError("Native MCP unit or release differs from pinned target")
    if sha(unit.encode()) != st["after_sha256"]:
        raise RuntimeError("Native MCP unit modified since domain change")
    preview.command(["systemctl", "is-active", "--quiet", preview.SERVICE])
    metadata_probe(RESOURCE, ISSUER)
    print("NATIVE_MCP_DOMAIN_VERIFY=PASS")
    print("CHATGPT_MCP_URL=" + RESOURCE)


def rollback():
    root_only()
    st = state()
    release, unit = read_live_unit()
    if release.name != st["release"] or sha(unit.encode()) != st["after_sha256"]:
        raise RuntimeError("Refusing rollback of changed Native MCP service")
    backup = Path(st["backup"])
    if (backup.parent != BACKUP_ROOT or not preview.root_owned(backup) or
            sha(backup.read_bytes()) != st["before_sha256"]):
        raise RuntimeError("Native MCP domain backup invalid")
    atomic(preview.UNIT, backup.read_bytes(), mode=0o644)
    service_reload()
    metadata_probe(PREVIOUS_RESOURCE, "https://mcp.xdr.ooo/access")
    STATE.unlink()
    print("NATIVE_MCP_DOMAIN_ROLLBACK=PASS")
    print("FRP_443_AND_PRIMARY_MCP=PRESERVED")


def main():
    p = argparse.ArgumentParser(description="Native MCP custom domain without FRP mode switch")
    m = p.add_mutually_exclusive_group(required=True)
    for arg in ("check", "preflight", "apply", "verify", "rollback"):
        m.add_argument("--" + arg, action="store_true")
    a = p.parse_args()
    try:
        if a.check: check()
        elif a.preflight: preflight()
        elif a.apply: apply()
        elif a.verify: verify()
        else: rollback()
    except (OSError, RuntimeError, KeyError, ValueError, subprocess.CalledProcessError) as ex:
        print("NATIVE_MCP_DOMAIN_ERROR=" + str(ex), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
