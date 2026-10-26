#!/usr/bin/env python3
"""Enroll a DRLink Server as a Managed Server peer, without installing an Agent.

Only a centrally issued, one-use Manual Enrollment Code is accepted. State and
ECDSA management keys are isolated from the DRLink Server and Agent files.
Crash/lost-response replay preserves the SAME operation_id and key pair.
Never log or persist the raw enrollment secret outside the supplied code file.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import frp_mgmt_auth as MGMT
import frp_machine_id as MID
from drlink_server_peer import SERVER_PEER_ROLE, ServerPeerDenied, validate_peer_root

CODE_RE = re.compile(r"^([0-9a-f]{16})\.([0-9a-f]{64})$", re.IGNORECASE)
DEFAULT_ROOT = "/var/lib/drlink-server-peer"
DEFAULT_CENTRAL = "https://remote.xdr.ooo"
MAX_RESPONSE = 65536


def _secret_file(path: str) -> str:
    src = Path(path)
    if src.is_symlink() or not src.is_file() or src.stat().st_mode & 0o077:
        raise ServerPeerDenied("Enrollment Code file must be a private regular file")
    if src.stat().st_uid != os.geteuid():
        raise ServerPeerDenied("Enrollment Code file ownership mismatch")
    raw = src.read_text(encoding="utf-8").strip()
    if not CODE_RE.fullmatch(raw):
        raise ServerPeerDenied("Expected a manual Enrollment Code; do not use a Zero-Touch installer ticket")
    return raw


def _atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_name(path.name + "." + secrets.token_hex(8))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def _post(url: str, payload: dict, enrollment_id: str, secret: str) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    signature = hmac.new(secret.encode("ascii"), ts.encode() + b"\n" + body,
                         hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "X-Enrollment-ID": enrollment_id,
                 "X-Timestamp": ts, "X-Signature": signature},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12, context=ssl.create_default_context()) as resp:
            raw = resp.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        raise ServerPeerDenied(f"Central Enrollment API rejected request (HTTP {exc.code})") from None
    except (OSError, urllib.error.URLError) as exc:
        raise ServerPeerDenied("Central enrollment transport failed; preserve pending state for exact replay") from None
    if len(raw) > MAX_RESPONSE:
        raise ServerPeerDenied("Oversized central enrollment response")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ServerPeerDenied("Central enrollment response is invalid JSON") from None
    if not isinstance(data, dict):
        raise ServerPeerDenied("Central enrollment response is invalid")
    if data.get("error"):
        raise ServerPeerDenied("Central enrollment request was denied")
    return data


def _verify_response(body: dict, secret: str) -> dict:
    value = dict(body)
    received = str(value.pop("response_hmac", "") or "")
    expected = MGMT.hmac_hex(secret, MGMT.canonical_json(value))
    if not received or not hmac.compare_digest(received, expected):
        raise ServerPeerDenied("Central enrollment response failed HMAC integrity verification")
    if value.get("services") != [] or value.get("mgmt_status") != "enrolled":
        raise ServerPeerDenied("Server peer must enroll management-only with an empty service set")
    if not value.get("token_ciphertext") or value.get("mgmt_mac_key"):
        raise ServerPeerDenied("Central enrollment payload did not match the v2.4 management contract")
    return value


def enroll(*, root: str, central: str, code_file: str, label: str) -> dict:
    home = Path(root)
    if not home.is_absolute() or home == Path("/") or home == Path("/etc/frp"):
        raise ServerPeerDenied("Dedicated absolute state root required")
    origin = central.rstrip("/")
    url = urlparse(origin)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment):
        raise ServerPeerDenied("Central endpoint must be a fixed HTTPS origin")
    code = _secret_file(code_file)
    match = CODE_RE.fullmatch(code)
    if match is None:
        raise ServerPeerDenied("Invalid manual Enrollment Code")
    enrollment_id, secret = (part.lower() for part in match.groups())
    digest = hashlib.sha256(code.encode("ascii")).hexdigest()
    if home.is_symlink():
        raise ServerPeerDenied("State root symlink denied")
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    if home.stat().st_mode & 0o077 or home.stat().st_uid != os.geteuid():
        raise ServerPeerDenied("State root owner/mode unsafe")
    directory = home / "etc/frp"
    parent = home / "etc"
    if parent.is_symlink() or directory.is_symlink():
        raise ServerPeerDenied("Server-peer identity directory symlink denied")
    parent.mkdir(exist_ok=True, mode=0o700)
    directory.mkdir(exist_ok=True, mode=0o700)
    if (parent.stat().st_uid != os.geteuid()
            or directory.stat().st_uid != os.geteuid()
            or parent.stat().st_mode & 0o077
            or directory.stat().st_mode & 0o077):
        raise ServerPeerDenied("Server-peer identity directory ownership or mode unsafe")
    if (home / "server-peer.json").exists():
        raise ServerPeerDenied("Server peer is already enrolled; never re-enroll or overwrite identity")
    pending = home / "enroll-pending.json"
    recovering = pending.exists()
    if recovering:
        if pending.is_symlink() or pending.stat().st_mode & 0o077:
            raise ServerPeerDenied("Pending state is unsafe")
        stage = json.loads(pending.read_text(encoding="utf-8"))
        if (stage.get("code_sha256") != digest or stage.get("central_origin") != origin
                or stage.get("label") != label):
            raise ServerPeerDenied("A different enrollment transaction is already pending")
    else:
        stage = {
            "role": SERVER_PEER_ROLE, "machine_id": MID.validate_machine_id("server-" + secrets.token_hex(16)),
            "operation_id": secrets.token_hex(16), "code_sha256": digest,
            "central_origin": origin, "label": label,
        }
        _atomic_json(pending, stage)
    machine_id = str(stage["machine_id"])
    key = directory / "client-identity.key"
    public = directory / "client-identity.pub"
    if not key.exists() and not public.exists():
        MGMT.generate_keypair(key, public)
    if key.is_symlink() or public.is_symlink() or not key.is_file() or not public.is_file():
        raise ServerPeerDenied("Pending Server-peer key pair is incomplete")
    MGMT.validate_private_key(key)
    pem = public.read_text("utf-8")
    if MGMT.canonicalize_pubkey_from_private(key) != MGMT.canonicalize_pubkey_pem(pem):
        raise ServerPeerDenied("Pending Server-peer key pair differs")
    # The central API refuses /enroll/preflight once a code is consumed.
    # An interrupted original transaction must replay the identical key and
    # operation_id directly to /enroll (central enforces exact replay binding).
    if not recovering:
        preflight = _post(origin + "/enroll/preflight", {
            "machine_id": machine_id, "purpose": "fresh-manual-enrollment",
        }, enrollment_id, secret)
        if preflight.get("valid") is not True:
            raise ServerPeerDenied("Central manual enrollment preflight denied")
    payload = {
        "machine_id": machine_id, "hostname": label, "services": [],
        "mgmt_pubkey": pem, "mgmt_alg": MGMT.MGMT_ALG,
        "operation_id": stage["operation_id"],
    }
    response = _post(origin + "/enroll", payload, enrollment_id, secret)
    _verify_response(response, secret)
    mac = MGMT.derive_mac_key(secret, machine_id)
    macpath = directory / "client-identity.mac"
    if macpath.exists():
        # A crash after central enrollment but before the remaining state
        # commit must not regenerate identity material or lose recovery.
        if (macpath.is_symlink() or macpath.stat().st_mode & 0o077
                or macpath.read_text("utf-8").strip() != mac):
            raise ServerPeerDenied("Stored management MAC does not match the original enrollment transaction")
    else:
        fd = os.open(macpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            os.write(fd, (mac + "\n").encode())
            os.fsync(fd)
        finally:
            os.close(fd)
    _atomic_json(directory / "client-state.json", {
        "machine_id": machine_id, "label": label, "hostname": label,
        "role": SERVER_PEER_ROLE,
    })
    _atomic_json(directory / "server-endpoint.json", {"mgmt_url": origin})
    _atomic_json(home / "server-peer.json", {
        "role": SERVER_PEER_ROLE, "machine_id": machine_id, "central_origin": origin,
    })
    try:
        pending.unlink()
    except FileNotFoundError:
        pass
    return validate_peer_root(str(home))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Enroll DRLink Server Peer using a central Manual Enrollment Code")
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--central", default=DEFAULT_CENTRAL)
    parser.add_argument("--code-file", required=True,
                        help="private 0600 file containing centrally issued MANUAL code")
    parser.add_argument("--label", default="dev-drlink Server")
    args = parser.parse_args(argv)
    try:
        result = enroll(root=args.root, central=args.central,
                        code_file=args.code_file, label=args.label)
    except (ServerPeerDenied, OSError, ValueError) as exc:
        print("SERVER_PEER_ENROLL=DENY: " + str(exc), file=sys.stderr)
        return 2
    print("SERVER_PEER_ENROLL=PASS")
    print("SERVER_PEER_CENTRAL=" + result["central_origin"])
    print("SERVER_PEER_AGENT_INSTALLED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
