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
WINDOWS_READ_ONLY = 'hostname & ver & where drlink'


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
        elif line.startswith("STATE_PATH_PRESENT="):
            summary["state_paths"].append(line.split("=", 1)[1])
        elif line.startswith("UNIT_") and "=" in line:
            k, v = line.split("=", 1)
            summary["service_units"][k] = v
    if alias == "frp-e2e-windows":
        # Real native version and clean-state verification are mandatory:
        # a management SSH reply alone cannot satisfy either requirement.
        summary["installed"] = "UNKNOWN"
        summary["reason"] = "Native Windows installed Source HEAD / clean-state cannot be verified"
    elif summary["installed"] == "YES":
        match = summary["source_head"] == expected_source
        if phase == "INSTALLED_CANDIDATE" and match:
            summary["status"] = "PASS"
            summary["reason"] = "Public installed version matches pinned content source"
        else:
            summary["reason"] = ("STALE_INSTALLED_SOURCE_HEAD" if not match
                                 else "PREINSTALL_CLEANROOM_REQUIRES_NO_PRODUCT")
    elif summary["installed"] == "NO":
        live_units = [n for n,v in summary["service_units"].items() if v == "active"]
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
