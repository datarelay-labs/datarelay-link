#!/usr/bin/env python3
"""Read-only DRLink Native MCP + on-host Let's Encrypt public readiness probe.

This does not install a package, request a certificate, change DNS, alter
DRLink FRP port 443, install an Agent, or open a firewall. The product's
supported public MCP stack requires the qualified single443 HTTPS frontend.
"""
from __future__ import annotations

import json
import re
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import drlink_mcp_tls

DOMAIN = "mcp.link.xdr.ooo"
LOCAL_MCP = "http://127.0.0.1:16106"


def resolved_ipv4() -> set[str]:
    return {item[4][0] for item in socket.getaddrinfo(
        DOMAIN, None, family=socket.AF_INET, type=socket.SOCK_STREAM)}


def local_global_ipv4() -> set[str]:
    """Compare DNS against addresses assigned to THIS Server, not a hardcoded lab IP."""
    result = subprocess.run(
        ["ip", "-o", "-4", "addr", "show", "scope", "global"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    addresses = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) > 3 and "/" in parts[3]:
            addresses.add(parts[3].split("/", 1)[0])
    return addresses


def listening_ports() -> set[int]:
    result = subprocess.run(
        ["ss", "-H", "-lnt"], check=True, capture_output=True, text=True, timeout=5)
    ports: set[int] = set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 4:
            match = re.search(r":(\d+)$", columns[3])
            if match:
                ports.add(int(match.group(1)))
    return ports


def public_certificate_status() -> str:
    try:
        with socket.create_connection((DOMAIN, 443), timeout=5) as s:
            with ssl.create_default_context().wrap_socket(s, server_hostname=DOMAIN):
                return "PASS"
    except ssl.SSLCertVerificationError:
        return "UNTRUSTED_CERT"
    except (ssl.SSLError, OSError) as exc:
        return "UNAVAILABLE_" + type(exc).__name__


def local_mcp_status() -> tuple[bool, str]:
    req = urllib.request.Request(
        LOCAL_MCP + "/mcp",
        data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=4):
            return False, "ANONYMOUS_UNEXPECTEDLY_ALLOWED"
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            return False, "HTTP_" + str(exc.code)
    except OSError as exc:
        return False, "UNAVAILABLE_" + type(exc).__name__
    try:
        with urllib.request.urlopen(
            LOCAL_MCP + "/.well-known/oauth-protected-resource", timeout=4
        ) as metadata:
            data = json.load(metadata)
        resource = str(data.get("resource") or "")
        return True, resource
    except (ValueError, OSError) as exc:
        return False, "METADATA_" + type(exc).__name__


def public_mcp_status() -> bool:
    """Prove the public HTTPS listener actually reaches the right MCP.

    A valid certificate alone is not proof of Native MCP: FRP or unrelated
    HTTPS content may still be listening on the domain.
    """
    req = urllib.request.Request(
        "https://" + DOMAIN + "/mcp",
        data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5):
            return False
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            return False
    except (OSError, urllib.error.URLError):
        return False
    try:
        for suffix, key, wanted in (
            ("/.well-known/oauth-protected-resource", "resource",
             "https://" + DOMAIN + "/mcp"),
            ("/.well-known/oauth-authorization-server", "issuer",
             "https://" + DOMAIN),
        ):
            with urllib.request.urlopen("https://" + DOMAIN + suffix, timeout=5) as r:
                metadata = json.load(r)
            if metadata.get(key) != wanted:
                return False
        return True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def preflight() -> int:
    ip = resolved_ipv4()
    interfaces = local_global_ipv4()
    valid_dns = bool(ip & interfaces)
    ports = listening_ports()
    acme = drlink_mcp_tls.acme_runtime_status()
    cert = public_certificate_status()
    mcp_auth, oauth_resource = local_mcp_status()
    real_public = public_mcp_status() if cert == "PASS" else False

    print("TARGET_NATIVE_MCP=https://" + DOMAIN + "/mcp")
    print("DNS_TO_DEVELOPMENT_SERVER=" + ("PASS" if valid_dns else "FAIL"))
    print("DNS_IPV4=" + ",".join(sorted(ip)))
    print("NATIVE_LOCAL_ANONYMOUS_DENY=" + ("PASS" if mcp_auth else "FAIL"))
    print("NATIVE_LOCAL_OAUTH_RESOURCE=" + oauth_resource)
    print("DRLINK_PACKAGED_ACME=" + ("PASS" if acme.get("ok") else "FAIL"))
    print("DRLINK_ACME_IMPLEMENTATION=" + str(acme.get("implementation") or "unknown"))
    print("PUBLIC_LETS_ENCRYPT_CERTIFICATE=" + cert)
    print("PUBLIC_443_PORT=" + ("OCCUPIED_BY_EXISTING_SERVICE" if 443 in ports else "FREE"))
    print("LOCAL_HTTP01_80=" + ("LOCAL_LISTENER_PRESENT" if 80 in ports else "NO_LOCAL_LISTENER"))
    print("PUBLIC_NATIVE_MCP_TLS_OAUTH_HTTP401=" + ("PASS" if real_public else "NOT_READY"))
    print("PUBLIC_NATIVE_MCP_READY=" + (
        "PASS" if valid_dns and cert == "PASS" and mcp_auth and real_public and
        oauth_resource == "https://" + DOMAIN + "/mcp" else "NO"))
    print("CONFIG_CHANGE_PERFORMED=NO")
    print("RECOMMENDED_PRODUCT_MODE=single443")
    print("CUTOVER_REQUIREMENTS=BACKUP,EXPLICIT_SWITCH,FRP_AGENT_RECONNECT,HTTP01_80_INGRESS")
    return 0 if valid_dns and mcp_auth and acme.get("ok") else 1


def verify_public() -> int:
    """Verify actual public HTTPS, MCP 401, and OAuth without root or TLS bypass."""
    try:
        resolved = resolved_ipv4()
        good_dns = bool(resolved & local_global_ipv4())
        good_cert = public_certificate_status() == "PASS"
        good_mcp = public_mcp_status() if good_dns and good_cert else False
    except OSError as exc:
        print("PUBLIC_MCP_NETWORK_ERROR=" + type(exc).__name__, file=sys.stderr)
        return 1
    print("PUBLIC_DOMAIN_IPV4_MATCH=" + ("PASS" if good_dns else "FAIL"))
    print("PUBLIC_CA_TRUSTED_TLS=" + ("PASS" if good_cert else "FAIL"))
    print("PUBLIC_NATIVE_MCP_HTTP401_OAUTH=" + ("PASS" if good_mcp else "FAIL"))
    passed = good_dns and good_cert and good_mcp
    print("CHATGPT_NATIVE_MCP_PUBLIC_READY=" + ("PASS" if passed else "NO"))
    print("CHATGPT_OWNER_OAUTH_AND_TOOL_E2E=NOT_YET_VALIDATED")
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--verify-public"]:
            raise SystemExit(verify_public())
        if sys.argv[1:]:
            print("Usage: native-mcp-letsencrypt-preflight.py [--verify-public]", file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(preflight())
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print("NATIVE_MCP_LETSENCRYPT_PREFLIGHT_ERROR=" + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1)
