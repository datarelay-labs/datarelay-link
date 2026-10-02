#!/usr/bin/env python3
"""Validate retained real ChatGPT owner/UI acceptance evidence."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

PASS_FIELDS = (
    "oauth_authorization_code_consent",
    "tool_discovery",
    "policy_allowed_operation",
    "policy_denied_operation",
)
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CLIENT_PLAN_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,80}$")
SUPPORT_MAX_AGE = timedelta(days=30)


def _endpoint_error(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return "mcp_endpoint must be a non-empty string"
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return "mcp_endpoint must use https with a hostname"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "mcp_endpoint must not contain credentials, query, or fragment"
    if parsed.path.rstrip("/") != "/mcp":
        return "mcp_endpoint path must be /mcp"
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or "." not in host:
        return "mcp_endpoint must use a public DNS hostname"
    try:
        ipaddress.ip_address(host)
        return "mcp_endpoint must not use a raw IP address"
    except ValueError:
        pass
    return None


def _support_reference_error(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return "support_reference must be a non-empty URL"
    if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return "support_reference must not contain surrounding whitespace or control characters"
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        return "support_reference must use https"
    if parsed.username or parsed.password:
        return "support_reference must not contain credentials"
    if parsed.query or parsed.fragment:
        return "support_reference must not contain query or fragment"
    if host != "openai.com" and not host.endswith(".openai.com"):
        return "support_reference must use an official openai.com hostname"
    return None


def _parse_timestamp(value: object, field: str, errs: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errs.append(f"{field} must be an offset-aware ISO-8601 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed
    except ValueError:
        errs.append(f"{field} must be an offset-aware ISO-8601 timestamp")
        return None


def validate_evidence(
    data: object,
    *,
    provenance_head: str,
    manifest: dict,
    provenance_committed_at: datetime | None = None,
    now: datetime | None = None,
) -> list[str]:
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["evidence must be a JSON object"]
    if data.get("schema_version") != 2:
        errs.append("schema_version must be 2")
    if data.get("status") != "PASS":
        errs.append("status must be PASS")
    source_head = str(manifest.get("source_head") or "")
    server_artifact = (manifest.get("artifacts") or {}).get("bootstrap-server.sh") or {}
    bundle_sha = str(server_artifact.get("sha256") or "")
    if not HEX40.fullmatch(provenance_head):
        errs.append("current provenance HEAD is invalid")
    if data.get("core_provenance_head") != provenance_head:
        errs.append("core_provenance_head does not match current HEAD")
    if not HEX40.fullmatch(source_head) or data.get("core_source_head") != source_head:
        errs.append("core_source_head does not match release manifest")
    if not HEX64.fullmatch(bundle_sha) or data.get("bootstrap_server_sha256") != bundle_sha:
        errs.append("bootstrap_server_sha256 does not match release manifest")
    if (manifest.get("features") or {}).get("mcp_included") is not True:
        errs.append("release manifest does not include MCP")
    if data.get("client_surface") != "ChatGPT owner/UI":
        errs.append("client_surface must be ChatGPT owner/UI")
    client_plan = data.get("client_plan")
    if (
        not isinstance(client_plan, str)
        or client_plan != client_plan.strip()
        or CLIENT_PLAN_RE.fullmatch(client_plan) is None
    ):
        errs.append("client_plan must record one safe actual ChatGPT plan name")
    support_err = _support_reference_error(data.get("support_reference"))
    if support_err:
        errs.append(support_err)
    endpoint_err = _endpoint_error(data.get("mcp_endpoint"))
    if endpoint_err:
        errs.append(endpoint_err)
    for key in PASS_FIELDS:
        if data.get(key) != "PASS":
            errs.append(f"{key} must be PASS")
    captured_dt = _parse_timestamp(data.get("captured_at"), "captured_at", errs)
    support_checked_dt = _parse_timestamp(
        data.get("support_checked_at"), "support_checked_at", errs
    )
    if captured_dt is not None and provenance_committed_at is not None:
        if provenance_committed_at.tzinfo is None:
            raise ValueError("provenance_committed_at must be timezone-aware")
        if captured_dt.astimezone(timezone.utc) < provenance_committed_at.astimezone(timezone.utc):
            errs.append("captured_at predates current provenance commit")
    if captured_dt is not None and now is not None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if captured_dt.astimezone(timezone.utc) > now.astimezone(timezone.utc) + timedelta(minutes=10):
            errs.append("captured_at is more than 10 minutes in the future")
    if captured_dt is not None and support_checked_dt is not None:
        captured_utc = captured_dt.astimezone(timezone.utc)
        support_utc = support_checked_dt.astimezone(timezone.utc)
        if support_utc > captured_utc + timedelta(minutes=10):
            errs.append("support_checked_at is after evidence capture time")
        if captured_utc - support_utc > SUPPORT_MAX_AGE:
            errs.append("support_checked_at is older than 30 days at evidence capture time")
    if support_checked_dt is not None and now is not None:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        if support_checked_dt.astimezone(timezone.utc) > now.astimezone(timezone.utc) + timedelta(minutes=10):
            errs.append("support_checked_at is more than 10 minutes in the future")
    refs = data.get("evidence_refs")
    if not isinstance(refs, list) or not refs or any(not isinstance(v, str) or not v.strip() for v in refs):
        errs.append("evidence_refs must contain at least one retained evidence reference")
    return errs


def _git_head(repo: Path) -> str:
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def _git_commit_time(repo: Path) -> datetime:
    raw = subprocess.check_output(
        ["git", "-C", str(repo), "show", "-s", "--format=%cI", "HEAD"],
        text=True,
    ).strip()
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("git commit timestamp is not timezone-aware")
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--print-endpoint", action="store_true")
    args = ap.parse_args(argv)
    repo = Path(args.root).resolve()
    try:
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        manifest = json.loads((repo / "release-manifest.json").read_text(encoding="utf-8"))
        head = _git_head(repo)
        committed_at = _git_commit_time(repo)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: unable to load ChatGPT owner/UI evidence: {exc}", file=sys.stderr)
        return 1
    errs = validate_evidence(
        evidence,
        provenance_head=head,
        manifest=manifest,
        provenance_committed_at=committed_at,
        now=datetime.now(timezone.utc),
    )
    if errs:
        for err in errs:
            print(f"ERROR: {err}", file=sys.stderr)
        print("CHATGPT_OWNER_UI_ACCEPTANCE=BLOCKED", file=sys.stderr)
        return 1
    if args.print_endpoint:
        print(evidence["mcp_endpoint"])
        return 0
    print("CHATGPT_OWNER_UI_ACCEPTANCE=PASS")
    print(f"CHATGPT_CORE_PROVENANCE_HEAD={head}")
    print(f"CHATGPT_CORE_SOURCE_HEAD={manifest['source_head']}")
    print(f"CHATGPT_MCP_ENDPOINT={evidence['mcp_endpoint']}")
    print(f"CHATGPT_CLIENT_PLAN={evidence['client_plan']}")
    print(f"CHATGPT_SUPPORT_REFERENCE={evidence['support_reference']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
