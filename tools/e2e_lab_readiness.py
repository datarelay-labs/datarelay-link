#!/usr/bin/env python3
"""Read-only DRLink E2E lab readiness inventory (not persona or E2E evidence).

Uses existing owner-assigned SSH aliases. Does not install, clean, enroll, reset,
modify product state, or bypass a previously denied effect. All reports are
written outside /tmp; blocked mandatory gates prevent a GO decision.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ALLOWED_ALIASES = frozenset({
    "frp-e2e-server", "frp-e2e-client", "frp-e2e-aws",
    "frp-e2e-rocky8", "frp-e2e-rocky9-rescue", "frp-e2e-windows",
})
EXCLUDED_ALIASES = frozenset({"frp-e2e-linux114", "frp-e2e-macos"})
SOURCE_RE = re.compile(r"^[0-9a-f]{40}$")
MCP_SERVER_ALIAS = "frp-release-server"
MCP_FQDN_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
UNIX_READ_ONLY = (
    'printf "HOST="; hostname; '
    'sed -n -E "/^(ID|VERSION_ID)=/p" /etc/os-release; '
    'if command -v drlink >/dev/null 2>&1; then '
    'echo DRLINK_INSTALLED=YES; sudo -n drlink system version; '
    'else echo DRLINK_INSTALLED=NO; fi; '
    'for p in /etc/frp /etc/drlink /var/lib/frp /var/lib/drlink /opt/frp; do '
    'if test -e "$p"; then printf "STATE_PATH_PRESENT=%s\\n" "$p"; fi; done; '
    'for unit in drlink-client.service drlink-server.service; do '
    'printf "UNIT_%s=" "$unit"; systemctl is-active "$unit" 2>/dev/null || true; done'
)
# Use the official native Windows installation path in docs/WINDOWS_CLIENT.md.
# A product CLI may not be on PATH, so a where lookup alone is insufficient.
# Read-only over the assigned existing Windows SSH alias; never install,
# extract, reset, change tunnels/credentials, or retry prior denied effects.
WINDOWS_READ_ONLY = (
    'powershell.exe -NoProfile -NonInteractive -Command "'
    "$ErrorActionPreference='Stop'; "
    "Write-Output ('HOST=' + $env:COMPUTERNAME); "
    "Write-Output 'ID=windows'; "
    "Write-Output ('VERSION_ID=' + [System.Environment]::OSVersion.Version.ToString()); "
    "$root=Join-Path $env:ProgramData 'drlink'; "
    "$cli=Join-Path $root 'tools\\drlink.cmd'; "
    "if (Test-Path -LiteralPath $cli -PathType Leaf) { "
    "Write-Output 'DRLINK_INSTALLED=YES'; "
    "& $cli system version; "
    "if ($LASTEXITCODE -ne 0) { "
    "Write-Output ('DRLINK_VERSION_FAILED_RC=' + $LASTEXITCODE) } "
    "} else { Write-Output 'DRLINK_INSTALLED=NO' }; "
    "if (Test-Path -LiteralPath $root) { "
    "Write-Output ('STATE_PATH_PRESENT=' + $root) }; "
    "$processes=Get-Process -Name frpc -ErrorAction SilentlyContinue; "
    "if ($null -ne $processes) { "
    "Write-Output 'UNIT_windows-frpc-process=active' "
    "} else { Write-Output 'UNIT_windows-frpc-process=inactive' }; "
    "$productService=Get-Service -Name 'drlink*','frpc*' "
    "-ErrorAction SilentlyContinue; "
    "if ($null -ne $productService) { "
    "Write-Output 'UNIT_windows-product-service=registered' }; "
    "try { "
    "$scheduled=Get-ScheduledTask -ErrorAction Stop | "
    "Where-Object { $_.TaskName -match 'drlink|frpc' }; "
    "if ($null -ne $scheduled) { "
    "Write-Output 'STATE_PATH_PRESENT=windows-product-scheduled-task' } "
    "} catch { Write-Output 'READ_ONLY_PROBE_ERROR=WINDOWS_SCHEDULED_TASK_QUERY_FAILED' }"
    '"'
)



# Named MCP host is independent of the functional FRP Server. Public read-only
# commands only; intentionally excludes previously denied certificate preflight,
# certificate issuance, credential, cleanup, install, and OAuth mutations.
MCP_READ_ONLY = (
    'printf "MCP_HOST="; hostname; '
    'sed -n -E "/^(ID|VERSION_ID)=/p" /etc/os-release; '
    'if command -v drlink >/dev/null 2>&1; then '
    'echo MCP_INSTALLED=YES; '
    'sudo -n drlink system version || echo MCP_VERSION_PROBE_FAILED=YES; '
    'echo MCP_CERT_STATUS_BEGIN; '
    'sudo -n drlink system certificate status || echo MCP_CERT_PROBE_FAILED=YES; '
    'echo MCP_DOCTOR_BEGIN; '
    'sudo -n drlink system diagnostics mcp || echo MCP_DIAGNOSTICS_NOT_PASS=YES; '
    'else echo MCP_INSTALLED=NO; fi'
)


def valid_mcp_hostname(hostname: str) -> bool:
    """Reject unsafe/ambiguous MCP hostnames from private operator manifests."""
    if not isinstance(hostname, str):
        return False
    if hostname != hostname.strip() or len(hostname) > 253:
        return False
    hostname = hostname.lower()
    try:
        ipaddress.ip_address(hostname)
        return False
    except ValueError:
        pass
    labels = hostname.split(".")
    return len(labels) >= 2 and all(MCP_FQDN_LABEL.fullmatch(label) for label in labels) and (
        hostname not in ("localhost", "localhost.localdomain")
        and labels[-1] not in ("local", "internal", "localhost", "lan", "home")
    )


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def verify_manifest(manifest: dict) -> list[dict]:
    errors = []
    hosts = manifest.get("hosts")
    if not isinstance(hosts, list) or not hosts:
        return [{"id": "HOST_CONFIG", "status": "NOT_READY", "reason": "Missing assigned host list"}]
    names = set()
    for host in hosts:
        alias = str(host.get("ssh_alias", ""))
        if alias not in ALLOWED_ALIASES or alias in EXCLUDED_ALIASES or alias in names:
            errors.append({"id": "HOST_CONFIG", "status": "NOT_READY",
                           "reason": "Alias not in assigned allowlist or duplicated: " + alias})
        names.add(alias)
        if host.get("role") not in ("server", "agent", "native-agent"):
            errors.append({"id": "HOST_CONFIG", "status": "NOT_READY", "reason": "Invalid role for " + alias})
    if "frp-e2e-server" not in names:
        errors.append({"id": "HOST_CONFIG", "status": "NOT_READY", "reason": "Missing assigned E2E Server"})
    # Optional for historical 6-host preflight manifests; mandatory when present
    # for the owner's new distinct MCP + function test topology.
    split = manifest.get("two_server_assignment")
    split_assigned = isinstance(split, dict) and split.get("roles_distinct") is True
    if split_assigned and "mcp_server" not in manifest:
        errors.append({"id": "MCP_HOST_CONFIG", "status": "NOT_READY",
                       "reason": "Two-Server lab manifest must separately identify the MCP Server"})
    if "mcp_server" in manifest:
        mcp = manifest["mcp_server"]
        if not isinstance(mcp, dict) or (
            mcp.get("ssh_alias") != MCP_SERVER_ALIAS or
            mcp.get("role") != "mcp-server" or
            mcp.get("required") is not True or
            not valid_mcp_hostname(mcp.get("public_hostname")) or
            MCP_SERVER_ALIAS in names or
            (split_assigned and mcp.get("public_hostname") != split.get("MCP_DNS_SERVER"))
        ):
            errors.append({"id": "MCP_HOST_CONFIG", "status": "NOT_READY",
                           "reason": "MCP Server must use the separately assigned owner SSH alias, public FQDN and mandatory role"})
    return errors


def classify_host(host: dict, result: subprocess.CompletedProcess, expected_source: str,
                  phase: str = "PREINSTALL_CLEANROOM") -> dict:
    alias = host["ssh_alias"]
    output = (result.stdout or "")[:16000]
    error = (result.stderr or "")[:800]
    # Outputs from the public version/OS/host surfaces contain no credentials.
    # Retain only allowlisted version/status lines, not raw stderr/CLI data.
    summary = {"ssh_alias": alias, "role": host["role"], "ssh_rc": result.returncode,
               "required": bool(host.get("required", True)), "host": None, "os_id": None,
               "os_version": None, "installed": "UNKNOWN", "source_head": None,
               "service_units": {}, "state_paths": [],
               "version_probe_failed": False, "probe_failed": False,
               "status": "NOT_READY", "reason": ""}
    if result.returncode != 0:
        summary["reason"] = "Existing approved management SSH route unreachable or version probe failed"
        summary["ssh_error_class"] = ("CONNECTION_REFUSED" if "Connection refused" in error
                                      else "AUTH_OR_TRANSPORT_FAILURE")
        return summary
    for line in output.splitlines():
        line = line.strip().strip("\r")
        if line.startswith("HOST="):
            summary["host"] = line[5:][:200]
        elif line.startswith("ID="):
            summary["os_id"] = line[3:].strip('"')
        elif line.startswith("VERSION_ID="):
            summary["os_version"] = line[11:].strip('"')
        elif line == "DRLINK_INSTALLED=YES":
            summary["installed"] = "YES"
        elif line == "DRLINK_INSTALLED=NO":
            summary["installed"] = "NO"
        elif line.startswith("Source HEAD:"):
            candidate = line.split(":", 1)[1].strip()
            if SOURCE_RE.fullmatch(candidate):
                summary["source_head"] = candidate
        elif line.startswith("DRLINK_VERSION_FAILED_RC="):
            summary["version_probe_failed"] = True
        elif line.startswith("READ_ONLY_PROBE_ERROR="):
            summary["probe_failed"] = True
        elif line.startswith("STATE_PATH_PRESENT="):
            summary["state_paths"].append(line.split("=", 1)[1])
        elif line.startswith("UNIT_") and "=" in line:
            k, v = line.split("=", 1)
            summary["service_units"][k] = v
    if alias == "frp-e2e-windows" and summary["os_id"] != "windows":
        summary["status"] = "NOT_READY"
        summary["reason"] = "Windows native OS identity unverified by read-only probe"
    elif summary["probe_failed"]:
        summary["status"] = "NOT_READY"
        summary["reason"] = "Native product service/task enumeration failed"
    elif summary["version_probe_failed"]:
        summary["status"] = "NOT_READY"
        summary["reason"] = "Installed CLI system version failed; Source HEAD unverified"
    elif summary["installed"] == "YES":
        match = summary["source_head"] == expected_source
        if phase == "INSTALLED_CANDIDATE" and match:
            summary["status"] = "PASS"
            summary["reason"] = "Public installed version matches pinned content source"
        else:
            summary["reason"] = ("STALE_INSTALLED_SOURCE_HEAD" if not match
                                 else "PREINSTALL_CLEANROOM_REQUIRES_NO_PRODUCT")
    elif summary["installed"] == "NO":
        live_units = [
            name for name, value in summary["service_units"].items()
            if value in ("active", "registered")
        ]
        if summary["state_paths"] or live_units:
            summary["reason"] = "RESIDUAL_STATE_OR_ACTIVE_UNITS"
        elif phase == "PREINSTALL_CLEANROOM":
            summary["status"] = "PASS"
            summary["reason"] = "No installed CLI, persistent paths or running product units detected"
        else:
            summary["reason"] = "INSTALLED_CANDIDATE_REQUIRES_PRODUCT"
    else:
        summary["reason"] = "Could not establish product installation state from public CLI"
    expected_os_id = str(host.get("expected_os_id") or "")
    if expected_os_id and summary["os_id"] != expected_os_id:
        summary["status"] = "NOT_READY"
        summary["reason"] = "Unexpected assigned native OS identity"
    return summary


def collect_host(host: dict, expected_source: str,
                 phase: str = "PREINSTALL_CLEANROOM", timeout: int = 15) -> dict:
    alias = host["ssh_alias"]
    command = WINDOWS_READ_ONLY if alias == "frp-e2e-windows" else UNIX_READ_ONLY
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", alias, command]
    try:
        result = subprocess.run(argv, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(argv, 124, "", "READ_ONLY_SSH_TIMEOUT")
    except OSError:
        result = subprocess.CompletedProcess(argv, 127, "", "READ_ONLY_SSH_UNAVAILABLE")
    return classify_host(host, result, expected_source, phase)


def classify_mcp_server(host: dict, result: subprocess.CompletedProcess, expected_source: str,
                        phase: str = "INSTALLED_CANDIDATE") -> dict:
    """Classify only the separately authorized MCP runtime's public read-only facts.

    This NEVER proves external public-CA trust or owner-side OAuth acceptance;
    those remain independent explicit GO gates in the owner manifest.
    """
    out = (result.stdout or "")[:16000]
    summary = {
        "ssh_alias": host["ssh_alias"], "role": "mcp-server",
        "required": bool(host.get("required", True)), "ssh_rc": result.returncode,
        "host": None, "os_id": None, "os_version": None,
        "installed": "UNKNOWN", "source_head": None,
        "mcp_hostname": host["public_hostname"], "mcp_public_url": "",
        "deployment_mode": "", "tls_mode": "", "certificate": "",
        "doctor_certificate_pass": False, "version_probe_failed": False,
        "certificate_probe_failed": False, "doctor_nonpass": False,
        "status": "NOT_READY", "reason": "MCP runtime/source/TLS state not qualified",
    }
    if result.returncode != 0:
        summary["reason"] = "Owner-approved MCP management route unreachable"
        summary["ssh_error_class"] = (
            "CONNECTION_REFUSED" if "Connection refused" in (result.stderr or "")[:800]
            else "AUTH_OR_TRANSPORT_FAILURE"
        )
        return summary
    pending = None
    section = ""
    for original in out.splitlines():
        line = original.strip().strip("\r")
        if line == "MCP_CERT_STATUS_BEGIN":
            section, pending = "cert", None
            continue
        if line == "MCP_DOCTOR_BEGIN":
            section, pending = "doctor", None
            continue
        if pending == "url":
            if line:
                summary["mcp_public_url"] = line
                pending = None
                continue
        elif pending == "mode":
            if line:
                summary["tls_mode"] = line
                pending = None
                continue
        elif pending == "certificate":
            if line:
                summary["certificate"] = line
                pending = None
                continue
        if line.startswith("MCP_HOST="):
            summary["host"] = line.partition("=")[2][:200]
        elif line.startswith("ID="):
            summary["os_id"] = line.partition("=")[2].strip('"')
        elif line.startswith("VERSION_ID="):
            summary["os_version"] = line.partition("=")[2].strip('"')
        elif line == "MCP_INSTALLED=YES":
            summary["installed"] = "YES"
        elif line == "MCP_INSTALLED=NO":
            summary["installed"] = "NO"
        elif line.startswith("Source HEAD:"):
            value = line.partition(":")[2].strip()
            if SOURCE_RE.fullmatch(value):
                summary["source_head"] = value
        elif line == "MCP_VERSION_PROBE_FAILED=YES":
            summary["version_probe_failed"] = True
        elif line == "MCP_CERT_PROBE_FAILED=YES":
            summary["certificate_probe_failed"] = True
        elif line == "MCP_DIAGNOSTICS_NOT_PASS=YES":
            summary["doctor_nonpass"] = True
        elif line == "URL:" and section == "cert":
            pending = "url"
        elif line == "TLS mode:" and section == "cert":
            pending = "mode"
        elif line == "Certificate:" and section == "cert":
            pending = "certificate"
        elif line.startswith("Deployment mode") and ":" in line and section == "doctor":
            summary["deployment_mode"] = line.partition(":")[2].strip()
        elif section == "doctor" and re.match(r"^mcp_tls_certificate\s+PASS\b", line):
            summary["doctor_certificate_pass"] = True
    if phase != "INSTALLED_CANDIDATE":
        summary["reason"] = "MCP Server preinstall has no independent cleanroom/ownership proof"
    elif summary["installed"] != "YES":
        summary["reason"] = "MCP Server public CLI not installed or not observable"
    elif summary["version_probe_failed"] or summary["source_head"] != expected_source:
        summary["reason"] = "MCP_SERVER_STALE_OR_UNKNOWN_INSTALLED_SOURCE_HEAD"
    elif summary["deployment_mode"] != "single443":
        summary["reason"] = "MCP_SERVER_SINGLE443_NOT_VERIFIED"
    elif summary["mcp_public_url"] != "https://" + host["public_hostname"] + "/mcp":
        summary["reason"] = "MCP_SERVER_PUBLIC_ENDPOINT_HOSTNAME_MISMATCH"
    elif summary["certificate_probe_failed"] or summary["certificate"] != "VALID":
        summary["reason"] = "MCP_SERVER_PUBLIC_CERTIFICATE_ABSENT_OR_INVALID"
    elif summary["doctor_nonpass"] or not summary["doctor_certificate_pass"]:
        summary["reason"] = "MCP_SERVER_PUBLIC_CERTIFICATE_DOCTOR_NOT_PASS"
    else:
        summary["status"] = "PASS"
        summary["reason"] = "MCP installed source, single443 and local certificate valid; separate external trusted-TLS/OAuth proof still mandatory"
    if host.get("expected_os_id") and summary["os_id"] != host["expected_os_id"]:
        summary["status"] = "NOT_READY"
        summary["reason"] = "MCP_SERVER_UNEXPECTED_NATIVE_OS_IDENTITY"
    return summary


def collect_mcp_server(host: dict, expected_source: str,
                       phase: str = "INSTALLED_CANDIDATE", timeout: int = 15) -> dict:
    """Never accept an arbitrary host or invoke a credential/certificate mutation."""
    if host.get("ssh_alias") != MCP_SERVER_ALIAS or not valid_mcp_hostname(host.get("public_hostname")):
        raise ValueError("MCP Server must use the assigned owner alias and public hostname")
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "ConnectTimeout=5", MCP_SERVER_ALIAS, MCP_READ_ONLY]
    try:
        result = subprocess.run(argv, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        result = subprocess.CompletedProcess(argv, 124, "", "READ_ONLY_SSH_TIMEOUT")
    except OSError:
        result = subprocess.CompletedProcess(argv, 127, "", "READ_ONLY_SSH_UNAVAILABLE")
    return classify_mcp_server(host, result, expected_source, phase)


def evaluate(manifest: dict, hosts: list[dict], repo_head: str) -> dict:
    checks = []
    approvals = manifest.get("approvals") or {}
    def add(name: str, ok: bool, reason: str):
        checks.append({"id": name, "status": "PASS" if ok else "NOT_READY", "reason": reason})
    add("REPO_HEAD_MATCH", repo_head == manifest.get("expected_provenance_head"),
        "Repository and explicitly pinned provenance HEAD must agree")
    add("CLEANROOM_APPROVAL", approvals.get("dedicated_disposable_lab") is True,
        "Host ownership and isolated disposal authority require legitimate independent approval")
    add("SERVER_CLEANUP_B014", approvals.get("server_cleanup_B014_resolved") is True,
        "Previously denied Server uninstall must not be retried; resolve via legitimate approval")
    add("PROTECTED_BACKUP", approvals.get("protected_backup_verified") is True,
        "Root-only E2E Server archive/snapshot check is mandatory")
    add("IMMUTABLE_ARTIFACT", approvals.get("qualified_immutable_bundle") is True,
        "Build SHA256, provenance/content binding and exact installed Source HEAD required")
    add("MCP_PUBLIC_TLS", approvals.get("trusted_mcp_tls_verified") is True,
        "No public trusted certificate/real ingress verification")
    add("OWNER_OAUTH_UI", approvals.get("actual_owner_oauth_ui_accepted") is True,
        "A real owner-side ChatGPT OAuth accept is required; no mock")
    add("AI_PERSONA_ISOLATION", approvals.get("separate_ai_personas_ready") is True,
        "Independent first-answer adviser with natural-language goal + public output only")
    add("PROSPECTIVE_PROCESS_LEDGER", approvals.get("prospective_process_registry_ready") is True,
        "Process/TTY/operator identity recorded at creation, not reconstructed after")
    add("NATIVE_APPROVALS", approvals.get("native_platform_security_denials_resolved") is True,
        "Previous Windows/Rocky platform security denials are binding until legitimately resolved")
    for host in hosts:
        if host["required"]:
            add("HOST_" + host["ssh_alias"].upper().replace("-", "_"),
                host["status"] == "PASS",
                host["reason"])
    blocked = [c["id"] for c in checks if c["status"] != "PASS"]
    return {"status": "GO" if not blocked else "NOT_READY",
            "checks": checks, "not_ready_gate_ids": blocked,
            "host_count": len(hosts), "note": "Read-only readiness, never full user E2E"}


def write_run_evidence(root: Path, report: dict, hosts: list[dict]) -> Path:
    """Append-only run directory: never replace the evidence of an earlier run."""
    import csv
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    run_dir = root / report["run_id"]
    run_dir.mkdir(mode=0o700, exist_ok=False)
    dest = run_dir / "PREFLIGHT_STATUS.json"
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    os.chmod(dest, 0o600)
    with (run_dir / "CLEANROOM_LEDGER.tsv").open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh, delimiter="\t",
            fieldnames=["ssh_alias", "role", "ssh_rc", "os_id",
                        "os_version", "installed", "source_head",
                        "status", "reason"])
        writer.writeheader()
        for host in hosts:
            writer.writerow({k: host.get(k, "") for k in writer.fieldnames})
    os.chmod(run_dir / "CLEANROOM_LEDGER.tsv", 0o600)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--worktree", type=Path, default=Path("/home/aella/datarelay-link-current"))
    opts = parser.parse_args()
    root = opts.output_dir.resolve()
    if str(root) == "/tmp" or str(root).startswith("/tmp/"):
        parser.error("E2E readiness evidence must live in a persistent path, never /tmp")
    data = opts.manifest.read_bytes()
    manifest = json.loads(data)
    errors = verify_manifest(manifest)
    if errors:
        print(json.dumps({"status": "NOT_READY", "config_errors": errors}, indent=2))
        return 2
    provenance = subprocess.run(["git", "-C", str(opts.worktree), "rev-parse", "HEAD"],
                                text=True, capture_output=True, check=False)
    head = provenance.stdout.strip() if provenance.returncode == 0 else ""
    expected = str(manifest.get("expected_installed_source_head") or "")
    if not SOURCE_RE.fullmatch(expected):
        print("Manifest requires expected_installed_source_head (40 hex chars)", file=sys.stderr)
        return 2
    phase = str(manifest.get("lab_phase") or "")
    if phase not in ("PREINSTALL_CLEANROOM", "INSTALLED_CANDIDATE"):
        print("Manifest requires lab_phase PREINSTALL_CLEANROOM or INSTALLED_CANDIDATE",
              file=sys.stderr)
        return 2
    hosts = [collect_host(h, expected, phase) for h in manifest["hosts"]]
    # The owner's independent MCP/DNS test Server must be checked separately
    # from the six functional/native E2E hosts. Historical manifests remain valid.
    if "mcp_server" in manifest:
        hosts.append(collect_mcp_server(manifest["mcp_server"], expected, phase))
    report = evaluate(manifest, hosts, head)
    report.update({"run_id": "lab-readiness-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                   + "-" + str(os.getpid()), "utc": utc_now(),
                   "worktree": str(opts.worktree.resolve()),
                   "repo_head": head, "lab_phase": phase,
                   "candidate_source_head": expected,
                   "manifest_sha256": hashlib.sha256(data).hexdigest(),
                   "hosts": hosts,
                   "excluded_hosts": sorted(EXCLUDED_ALIASES),
                   "security_denials_are_binding": True})
    run_dir = write_run_evidence(root, report, hosts)
    print(json.dumps({"status": report["status"], "run_id": report["run_id"],
                      "repo_head": head, "host_count": len(hosts),
                      "not_ready_gate_ids": report["not_ready_gate_ids"],
                      "evidence_dir": str(run_dir)}, indent=2))
    return 0 if report["status"] == "GO" else 3


if __name__ == "__main__":
    raise SystemExit(main())
