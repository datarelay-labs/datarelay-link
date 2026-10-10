"""PF-11B Link-owned read-only connectivity evidence for the pinned Foundation evaluator.

The product reads only its authoritative MCP TLS host/certificate identity.
There is no caller-provided probe URL, hostname, IP, CA, proxy or credential.
A real default-root DNS test has a hard subprocess timeout; synthetic roots
never touch the actual developer machine network/time service.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import drlink_mcp_tls as mcp_tls
from drlink_control_plane import ControlPlane
from drlink_foundation_security import (
    FoundationDiagnosticPolicy,
    FoundationNetworkEvidence,
    foundation_diagnose_network,
)

_DNS_SCRIPT = (
    "import socket,sys\n"
    "try:\n"
    " infos=socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)\n"
    " sys.exit(0 if infos else 1)\n"
    "except (OSError,ValueError):\n"
    " sys.exit(1)\n"
)
_CHRONY_OFFSET = re.compile(
    r"(?im)^\s*Last offset\s*:\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s+seconds\s*$"
)


def _probe_dns(hostname: str) -> bool:
    """DNS only, from the already-configured MCP TLS hostname, max 3 seconds."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _DNS_SCRIPT, hostname],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return result.returncode == 0


def _probe_ntp() -> tuple[bool | None, int | None]:
    """Bounded, read-only OS sync state plus independently measured offset."""
    timedatectl = Path("/usr/bin/timedatectl")
    if not timedatectl.is_file():
        return None, None
    try:
        result = subprocess.run(
            [str(timedatectl), "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if result.returncode != 0:
        return None, None
    synced = result.stdout.strip().lower()
    if synced == "no":
        return False, None
    if synced != "yes":
        return None, None

    # Host synchronization alone does not give a measured clock offset.
    # Never convert this to Foundation NTP PASS without an actual measurement.
    chrony = next(
        (p for p in (Path("/usr/bin/chronyc"), Path("/usr/sbin/chronyc"))
         if p.is_file()), None,
    )
    if chrony is None:
        return True, None
    try:
        result = subprocess.run(
            [str(chrony), "-n", "tracking"], capture_output=True,
            text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, None
    if result.returncode != 0:
        return True, None
    match = _CHRONY_OFFSET.search(result.stdout[:4096])
    if match is None:
        return True, None
    try:
        milliseconds = round(float(match.group(1)) * 1000)
    except (ValueError, OverflowError):
        return True, None
    if not -86_400_000 <= milliseconds <= 86_400_000:
        return True, None
    return True, milliseconds


def _product_hostname(root: str | None) -> str | None:
    plane = ControlPlane(root, read_only=True)
    try:
        configured = mcp_tls.load_state(plane)
    finally:
        plane.close()
    raw = configured.get("hostname")
    if not raw or type(raw) is not str:
        return None
    try:
        return mcp_tls.canonicalize_hostname(raw)
    except (ValueError, mcp_tls.McpTlsError):
        return None


def _active_certificate_expiry(root: str | None) -> int | None:
    try:
        active = mcp_tls.read_active_material(root)
        if not isinstance(active, dict) or active.get("not_yet_valid"):
            return None
        timestamp = active.get("not_after")
        if not isinstance(timestamp, str) or not timestamp:
            return None
        date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if date.tzinfo is None:
            return None
        result = int(date.timestamp())
        return result if result >= 0 else None
    except (OSError, ValueError, TypeError, mcp_tls.McpTlsError):
        return None


def collect_link_connectivity(
    root: str | None = None, *,
    now: int | None = None,
    resolver: Callable[[str], bool | None] | None = None,
    ntp_probe: Callable[[], tuple[bool | None, int | None]] | None = None,
    cert_reader: Callable[[str | None], dict | None] | None = None,
    proxy_configured: bool | None = None,
    ca_configured: bool | None = None,
) -> dict:
    """Read-only product evidence -> exactly one pinned shared PF-11B evaluator.

    The explicit probe callbacks are only for deterministic in-process native
    tests; Web endpoints NEVER accept any probe/certificate/hostname inputs.
    Synthetic product roots have no live DNS/time service probes by default.
    """
    moment = int(time.time()) if now is None else now
    if type(moment) is not int or moment < 0:
        raise ValueError("invalid diagnostic collection timestamp")
    synthetic_root = bool(root and root != "/")

    try:
        hostname = _product_hostname(root)
    except (OSError, ValueError):
        hostname = None
    dns_ok = None
    if hostname is not None:
        if resolver is not None:
            try:
                dns_ok = resolver(hostname)
            except (OSError, ValueError):
                dns_ok = False
        elif not synthetic_root:
            dns_ok = _probe_dns(hostname)
    if dns_ok is not None and type(dns_ok) is not bool:
        raise ValueError("invalid product DNS observation")

    ntp_synced, ntp_offset_ms = None, None
    if ntp_probe is not None:
        ntp_synced, ntp_offset_ms = ntp_probe()
    elif not synthetic_root:
        ntp_synced, ntp_offset_ms = _probe_ntp()

    # Optional outbound proxies/enterprise CA must NEVER be shown as PASS
    # from mere presence of configuration. Verification is a separate
    # credential- and trust-bound native probe, not this read-only workflow.
    if proxy_configured is None:
        proxy_configured = bool(
            not synthetic_root and (
                os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
            )
        )
    if ca_configured is None:
        ca_configured = bool(
            not synthetic_root and (
                os.environ.get("SSL_CERT_FILE") or
                os.environ.get("REQUESTS_CA_BUNDLE")
            )
        )
    active = cert_reader(root) if cert_reader is not None else None
    if cert_reader is None:
        expiry = _active_certificate_expiry(root)
    elif isinstance(active, dict) and isinstance(active.get("not_after"), str):
        try:
            parsed = datetime.fromisoformat(
                active["not_after"].replace("Z", "+00:00")
            )
            expiry = int(parsed.timestamp()) if parsed.tzinfo and not active.get("not_yet_valid") else None
        except (ValueError, OverflowError):
            expiry = None
    else:
        expiry = None

    evidence = FoundationNetworkEvidence(
        collected_at=moment, dns_ok=dns_ok,
        ntp_synchronized=ntp_synced, ntp_offset_ms=ntp_offset_ms,
        proxy_enabled=proxy_configured, proxy_reachable=None,
        trusted_ca_configured=ca_configured, trusted_ca_verified=None,
        certificate_not_after=expiry,
    )
    report = foundation_diagnose_network(
        evidence, now=moment, policy=FoundationDiagnosticPolicy(),
    )
    return {
        "status": report.status.value,
        "collected_at": report.collected_at,
        "read_only": True,
        "authoritative_mutation": False,
        "all_required_checks_verified": report.status.value == "pass",
        "dns_target_source": "product_mcp_tls_configuration",
        "certificate_evidence_type": "active_certificate_expiry_only",
        "proxy_and_ca_trust_verified": False,
        "findings": [
            {
                "area": item.area.value,
                "severity": item.severity.value,
                "code": item.code.value,
                "remediation": item.remediation.value,
                "checked_at": item.checked_at,
            }
            for item in report.findings
        ],
    }


__all__ = ["collect_link_connectivity"]
