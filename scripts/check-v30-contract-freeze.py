#!/usr/bin/env python3
"""Validate the frozen DRLink 3.0 cross-document management contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = {
    "docs/PRODUCT_MASTER.md": [
        "Current project version: **3.0.0**",
        "Optional Full Web Management",
        "100 Managed Hosts",
        "SSO/OIDC/IdP integration is excluded from 3.0",
    ],
    "docs/VERSION_POLICY.md": [
        "Current development target             3.0.0",
        "first stable generation with Optional Full Web Management",
    ],
    "docs/DATA_RELAY_ROADMAP.md": [
        "DRL3-0 — Scope and architecture freeze",
        "Managed Hosts          1 / 10 / 50 / 100",
        "SSO/IdP integration is not required",
        "Management Scalability Layer",
        "DRL3-8 — 3.0 Qualification and Stable Release",
        "100_HOST_CONTROL_PLANE_SCALE=PASS",
    ],
    "docs/WEB_MANAGEMENT.md": [
        "Admin",
        "Operator",
        "Read Only",
        "MFA",
        "disabled by default",
        "local recovery",
        "Authoritative management state",
        "Operator preference state",
        "Operational state",
        "Derived state",
        "Temporary Access",
        "Managed Host Approval / Quarantine",
        "Public Automation API",
        "Signed Event Webhook",
        "Access Hygiene",
        "Managed Update / Staged Rollout",
        "SSO/OIDC/IdP integration is **not part of Data Relay Link 3.0**",
    ],
    "docs/MANAGEMENT_SURFACE_CONTRACT.md": [
        "CLI",
        "Web",
        "MCP",
        "Core",
        "Service Account",
        "Change Plan",
        "RECOVERY_AUTHORITY",
        "Emergency New-Access Cutoff",
    ],
    "docs/CONTROL_PLANE_ARCHITECTURE.md": [
        "SQLite",
        "authoritative",
        "Web",
        "Agent",
        "durable spool",
        "checkpoint",
        "Operational State Aggregator",
    ],
    "docs/AI_ACCESS_MCP.md": [
        "MCP",
        "authorization",
        "management permissions",
        "AI Identity",
    ],
}

def main() -> int:
    failures = []
    for rel, needles in REQUIRED.items():
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                failures.append(f"{rel}: missing contract marker: {needle}")
    if failures:
        print("DRL3_0_CONTRACT_FREEZE=FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("DRL3_0_CONTRACT_FREEZE=PASS")
    print(f"CONTRACT_DOCUMENTS={len(REQUIRED)}")
    print("CROSS_DOCUMENT_CONTRACT=PASS")
    print("WEB_LOCAL_AUTH_CONTRACT=PASS")
    print("SSO_IDP_DEPENDENCY=NO")
    print("ARCHITECTURE_REINVENTION_REQUIRED=NO")
    return 0

if __name__ == "__main__":
    sys.exit(main())
