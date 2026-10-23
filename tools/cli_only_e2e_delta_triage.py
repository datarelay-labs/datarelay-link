#!/usr/bin/env python3
"""Read-only, parallel CLI-only E2E evidence triage (never executes product CLI).

This tool deliberately cannot promote a 116-ID ledger result. It audits pinned
subcase evidence in parallel and proposes nonconflicting live lanes for a human
operator. Historical-source PASS cannot become latest-candidate acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from cli_only_e2e_inventory import CANONICAL, scopes

SHA = re.compile(r"[0-9a-f]{64}\Z")
HEAD = re.compile(r"[0-9a-f]{40}\Z")
LANE_STATES = {"READY", "ALREADY_OBSERVED", "HOLD_ENVIRONMENT", "HOLD_PLATFORM",
               "HOLD_APPROVAL", "HOLD_TOOLING", "HOLD_SLO"}
LEDGER_RESULTS = {"PASS", "PARTIAL", "FAIL", "BLOCKED_TOOLING",
                  "BLOCKED_PLATFORM_DENIAL", "BLOCKED_ENVIRONMENT",
                  "BLOCKED_MANAGEMENT_PATH", "FAIL_PRECONDITION",
                  "MEASURED_NOT_QUALIFIED", "NOT_RUN", "IN_PROGRESS",
                  "EXCLUDED_AI_MCP"}


def root_dir(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError("existing private 0700 run root required")
    return path.resolve()


def evidence_path(root: Path, name: str) -> Path:
    rel = Path(name)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise ValueError("only relative evidence paths are permitted")
    current = root
    for part in rel.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("symlink in evidence path")
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise ValueError("evidence is missing or outside private run root")
    return current


def read_ledger(root: Path) -> tuple[list[dict], str]:
    path = evidence_path(root, "ledger/scenario-results.tsv")
    raw = path.read_bytes()
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp, delimiter="\t")
        if not {"SCENARIO_ID", "SCOPE", "RESULT", "SOURCE_HEAD"} <= set(reader.fieldnames or []):
            raise ValueError("incompatible canonical ledger schema")
        rows = list(reader)
    if len(rows) != 116 or len({r["SCENARIO_ID"] for r in rows}) != 116:
        raise ValueError("canonical 116-ID ledger drift")
    canonical = {x["SCENARIO_ID"]: x for x in scopes(CANONICAL.read_text(encoding="utf-8"))}
    if any(r["SCENARIO_ID"] not in canonical or
           r["SCOPE"] != canonical[r["SCENARIO_ID"]]["SCOPE"] for r in rows):
        raise ValueError("original ID/scope changed relative to canonical 116-ID contract")
    if sum(r["SCOPE"] == "EXCLUDED_AI_MCP" for r in rows) != 16:
        raise ValueError("only the explicit 16 AI/MCP scenarios may be excluded")
    if any(r["RESULT"] not in LEDGER_RESULTS for r in rows):
        raise ValueError("unknown ledger disposition")
    return rows, hashlib.sha256(raw).hexdigest()


def json_pointer(data: object, path: str) -> object:
    if not path.startswith("/") or path == "/":
        raise ValueError("non-root RFC6901 pointer required")
    obj = data
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(obj, dict):
            obj = obj[part]
        elif isinstance(obj, list) and part.isascii() and part.isdecimal():
            obj = obj[int(part)]
        else:
            raise KeyError(path)
    return obj


def verify_one(root: Path, item: dict, source: str, applicable: set[str]) -> dict:
    result = {"scenario": item["scenario"], "subcase": item["subcase"],
              "receipt": item["receipt"], "status": "EVIDENCE_INVALID",
              "source_scope": "UNKNOWN"}
    try:
        if item["scenario"] not in applicable:
            raise ValueError("excluded or unknown original scenario")
        if not SHA.fullmatch(item["sha256"]):
            raise ValueError("invalid SHA256")
        raw = evidence_path(root, item["receipt"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("evidence checksum mismatch")
        data = json.loads(raw)
        assertions = item["assertions"]
        if not isinstance(assertions, list) or not assertions:
            raise ValueError("must verify actual named receipt assertions")
        for clause in assertions:
            if json_pointer(data, clause["pointer"]) != clause["equals"]:
                raise ValueError("receipt assertion mismatch")
        if item.get("source_pointer"):
            expected = item["source_head"]
            if not HEAD.fullmatch(expected):
                raise ValueError("exact source HEAD required")
            if json_pointer(data, item["source_pointer"]) != expected:
                raise ValueError("source binding did not match receipt")
            result["source_scope"] = (
                "CURRENT_INSTALLED_SOURCE" if expected == source else "HISTORICAL_SOURCE"
            )
        else:
            result["source_scope"] = "UNPINNED_RECEIPT_SOURCE"
        result["status"] = "SCOPED_EVIDENCE_VERIFIED"
        result["assertion_count"] = len(assertions)
        result["receipt_sha256"] = item["sha256"]
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        # Do not print untrusted receipt data, secrets, or pretend it is a product failure.
        result["error_class"] = "EVIDENCE_VERIFICATION_FAILURE_NOT_PRODUCT_FAILURE"
        result["error_type"] = type(exc).__name__
    return result


def conflicts(a: dict, b: dict) -> bool:
    return any(k in b["resources"] and "write" in (v, b["resources"][k])
               for k, v in a["resources"].items())


def potential_batches(lanes: list[dict], workers: int) -> list[list[str]]:
    pending = [x for x in lanes if x["state"] == "READY"]
    batches = []
    while pending:
        batch, rest = [], []
        for item in pending:
            if len(batch) < workers and not any(conflicts(item, peer) for peer in batch):
                batch.append(item)
            else:
                rest.append(item)
        batches.append([x["id"] for x in batch])
        pending = rest
    return batches


def analyse(root: Path, manifest: dict, workers: int) -> dict:
    if workers not in range(1, 9):
        raise ValueError("workers must be 1..8")
    source = manifest["installed_source"]
    if not HEAD.fullmatch(source):
        raise ValueError("installed source must be an exact SHA")
    rows, ledger_hash = read_ledger(root)
    applicable = {x["SCENARIO_ID"] for x in rows if x["SCOPE"] != "EXCLUDED_AI_MCP"}
    claims, lanes = manifest["claims"], manifest["lanes"]
    if len({(c["scenario"], c["subcase"]) for c in claims}) != len(claims):
        raise ValueError("duplicate subcase")
    if len({x["id"] for x in lanes}) != len(lanes):
        raise ValueError("duplicate lane")
    for lane in lanes:
        if lane["state"] not in LANE_STATES:
            raise ValueError("invalid lane state")
        if not lane["scenario_ids"] or not set(lane["scenario_ids"]) <= applicable:
            raise ValueError("lane targets excluded/unknown scenario")
        if not isinstance(lane["resources"], dict) or any(
            x not in ("read", "write") for x in lane["resources"].values()
        ):
            raise ValueError("invalid resource lock")
        if lane["state"] != "READY" and not lane.get("reason"):
            raise ValueError("non-ready lane needs a concrete reason")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        facts = list(executor.map(
            lambda c: verify_one(root, c, source, applicable), claims
        ))
    counts = Counter(x["RESULT"] for x in rows if x["SCOPE"] != "EXCLUDED_AI_MCP")
    return {
        "schema": "drlink.cli_only.parallel_delta_triage.v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_ledger_sha256": ledger_hash,
        "canonical_ledger_rows": len(rows),
        "applicable": len(applicable),
        "immutable_original_dispositions": dict(sorted(counts.items())),
        "verified_subcase_facts": facts,
        "evidence_verified": sum(x["status"] == "SCOPED_EVIDENCE_VERIFIED" for x in facts),
        "evidence_errors": sum(x["status"] != "SCOPED_EVIDENCE_VERIFIED" for x in facts),
        "historical_source_facts": sum(
            x["source_scope"] == "HISTORICAL_SOURCE" for x in facts
        ),
        "potential_nonconflicting_batches_NOT_EXECUTED": potential_batches(lanes, workers),
        "lane_readiness": lanes,
        "parallel_read_only_evidence_workers": workers,
        "new_real_cli_actions": 0,
        "new_product_mutations": 0,
        "full_scenario_PASS_promotions": 0,
        "release_qualification": "NOT_ESTABLISHED_BY_THIS_AUDIT",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-root", type=Path, required=True)
    ap.add_argument("--manifest", required=True, help="relative path inside RUN_ID")
    ap.add_argument("--output", required=True, help="new relative JSON path inside RUN_ID")
    ap.add_argument("--workers", type=int, default=3)
    opts = ap.parse_args()
    root = root_dir(opts.run_root)
    manifest = json.loads(evidence_path(root, opts.manifest).read_text(encoding="utf-8"))
    report = analyse(root, manifest, opts.workers)
    if report["evidence_errors"]:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    rel = Path(opts.output)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        ap.error("output must be inside RUN_ID")
    parent = root
    for part in rel.parts[:-1]:
        parent /= part
        if parent.is_symlink():
            ap.error("symlink output parent")
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    dest = parent / rel.name
    if dest.exists() or dest.is_symlink():
        ap.error("report already exists; do not overwrite frozen evidence")
    os.umask(0o077)
    data = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    with dest.open("xb") as out:
        out.write(data)
    print(json.dumps({"status": "PARALLEL_EVIDENCE_AUDIT_ONLY",
                      "path": str(dest), "sha256": hashlib.sha256(data).hexdigest(),
                      "subcases_verified": report["evidence_verified"],
                      "potential_batch_count": len(
                          report["potential_nonconflicting_batches_NOT_EXECUTED"]
                      ), "new_full_PASS": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
