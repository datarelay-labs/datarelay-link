#!/usr/bin/env python3
"""Validate retained PASS1/PASS2 qualification evidence against exact Git HEAD."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SSH_EXCEPTION_RE = re.compile(r"^(UBUNTU|ROCKY|AWS_LINUX|WINDOWS|MACOS|UBUNTU24)_SSH$")
BAD_GATE_VALUES = {"FAIL", "BLOCKED", "NOT_RUN"}


def git_head(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ValueError("unable to resolve repository HEAD")
    return proc.stdout.strip().lower()


def canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def public_mcp_endpoint_error(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return "public_mcp_endpoint must be a non-empty URL"
    if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return "public_mcp_endpoint must not contain whitespace or control characters"
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme != "https" or not host:
        return "public_mcp_endpoint must use https with a hostname"
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "public_mcp_endpoint must not contain credentials, query, or fragment"
    try:
        port = parsed.port
    except ValueError:
        return "public_mcp_endpoint port is invalid"
    if port not in (None, 443):
        return "public_mcp_endpoint must use HTTPS port 443"
    if parsed.path.rstrip("/") != "/mcp":
        return "public_mcp_endpoint path must be /mcp"
    if host == "localhost" or "." not in host:
        return "public_mcp_endpoint must use a public DNS hostname"
    try:
        ipaddress.ip_address(host)
        return "public_mcp_endpoint must not use a raw IP address"
    except ValueError:
        pass
    return None


def validate_summary(summary: object, pass_name: str, head: str, public_mcp_endpoint: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(summary, dict):
        return [f"{pass_name} summary must be an object"]
    if summary.get("schema_version") != 1:
        errors.append(f"{pass_name} summary schema_version must be 1")
    if summary.get("pass_name") != pass_name:
        errors.append(f"{pass_name} summary pass_name mismatch")
    if str(summary.get("git_head") or "").lower() != head:
        errors.append(f"{pass_name} summary git_head must equal exact HEAD {head}")
    if summary.get("final_status") != "PASS":
        errors.append(f"{pass_name} summary final_status must be PASS")
    if summary.get("public_mcp_endpoint") != public_mcp_endpoint:
        errors.append(f"{pass_name} summary public_mcp_endpoint mismatch")
    gates = summary.get("gates")
    if not isinstance(gates, dict):
        errors.append(f"{pass_name} summary gates must be an object")
        return errors
    required = {
        "FROZEN_HEAD": head,
        f"{pass_name}_HEAD": head,
        "END_HEAD": head,
        "HEAD_UNCHANGED": "YES",
        pass_name: "PASS",
    }
    for key, want in required.items():
        got = str(gates.get(key) or "")
        if got.lower() != want.lower():
            errors.append(f"{pass_name} gate {key} must be {want}, got {got or '<missing>'}")
    for key, value in gates.items():
        value_s = str(value)
        if value_s in BAD_GATE_VALUES and not SSH_EXCEPTION_RE.fullmatch(str(key)):
            errors.append(f"{pass_name} contains terminal blocking gate {key}={value_s}")
    evidence_paths = summary.get("evidence_paths")
    if not isinstance(evidence_paths, dict):
        errors.append(f"{pass_name} summary evidence_paths must be an object")
    else:
        for rel in ("summary.txt", "matrix.log"):
            if evidence_paths.get(rel) is not True:
                errors.append(f"{pass_name} summary must retain {rel}")
    return errors


def validate(root: Path, evidence_path: Path) -> tuple[dict, list[str]]:
    errors: list[str] = []
    try:
        raw = evidence_path.read_bytes()
        data = json.loads(raw)
    except Exception as exc:
        return {}, [f"unable to read qualification evidence: {exc}"]
    if not isinstance(data, dict):
        return {}, ["qualification evidence must be a JSON object"]

    try:
        head = git_head(root)
    except ValueError as exc:
        return {}, [str(exc)]

    if data.get("schema_version") != 1:
        errors.append("qualification evidence schema_version must be 1")
    if data.get("status") != "PASS":
        errors.append("qualification evidence status must be PASS")

    public_mcp_endpoint = str(data.get("public_mcp_endpoint") or "")
    endpoint_err = public_mcp_endpoint_error(public_mcp_endpoint)
    if endpoint_err:
        errors.append(endpoint_err)

    heads = {
        "pass1_head": str(data.get("pass1_head") or "").lower(),
        "pass2_head": str(data.get("pass2_head") or "").lower(),
        "final_qualified_head": str(data.get("final_qualified_head") or "").lower(),
    }
    for key, value in heads.items():
        if not SHA_RE.fullmatch(value):
            errors.append(f"{key} must be a 40-character lowercase SHA")
        elif value != head:
            errors.append(f"{key} must equal exact HEAD {head}")

    for pass_name, field, digest_field in (
        ("PASS1", "pass1_summary", "pass1_summary_sha256"),
        ("PASS2", "pass2_summary", "pass2_summary_sha256"),
    ):
        summary = data.get(field)
        digest = str(data.get(digest_field) or "").lower()
        if not SHA256_RE.fullmatch(digest):
            errors.append(f"{digest_field} must be a 64-character SHA256")
        elif isinstance(summary, dict):
            actual = hashlib.sha256(canonical_json_bytes(summary)).hexdigest()
            if actual != digest:
                errors.append(f"{digest_field} does not match embedded {field}")
        errors.extend(validate_summary(summary, pass_name, head, public_mcp_endpoint))

    outputs = {
        "head": head,
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "mcp_endpoint": public_mcp_endpoint,
        **heads,
    }
    return outputs, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args(argv)

    outputs, errors = validate(Path(args.root).resolve(), Path(args.evidence).resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print("QUALIFICATION_EVIDENCE=FAIL", file=sys.stderr)
        return 1

    print("QUALIFICATION_EVIDENCE=PASS")
    print(f"QUALIFICATION_PASS1_HEAD={outputs['pass1_head']}")
    print(f"QUALIFICATION_PASS2_HEAD={outputs['pass2_head']}")
    print(f"QUALIFICATION_FINAL_HEAD={outputs['final_qualified_head']}")
    print(f"QUALIFICATION_EVIDENCE_SHA256={outputs['evidence_sha256']}")
    print(f"QUALIFICATION_MCP_ENDPOINT={outputs['mcp_endpoint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
