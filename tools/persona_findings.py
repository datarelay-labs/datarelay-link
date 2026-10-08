#!/usr/bin/env python3
"""Link frozen, directly observed user-gate findings to fast regression checks.

This is a supporting *development* check, never human-persona evidence or E2E PASS.
It reads existing ledgers; it cannot run product actions or change release evidence.
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import re
import sys
from pathlib import Path, PurePosixPath

FIELDS = ("run_id", "source_head", "contract_sha256", "finding_id", "scenario_id", "user_goal", "observation",
          "regression_file", "regression_case")
LEDGER_FIELDS = {"FINDING_ID", "SEVERITY", "USER_BLOCKING", "STATUS",
                 "CLASSIFICATION", "SURFACE", "EVIDENCE"}


def local_file(root: Path, value: str) -> Path:
    """Resolve a repository-local file without accepting absolute/traversal/symlinks."""
    rel = PurePosixPath(value)
    if not value or rel.is_absolute() or ".." in rel.parts or "\\" in value:
        raise ValueError(f"unsafe repository path: {value!r}")
    root = root.resolve()
    path = root.joinpath(*rel.parts)
    cursor = root
    for component in rel.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            raise ValueError(f"unsafe symlink in repository path: {value!r}")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError(f"missing or escaping repository file: {value!r}")
    return path


def has_test_case(path: Path, case: str) -> bool:
    """Require exact unittest Class.method or top-level test function."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeError) as exc:
        raise ValueError(f"invalid Python test {path}: {exc}") from exc
    parts = case.split(".")
    if len(parts) == 1:
        return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name == parts[0] for n in tree.body)
    if len(parts) == 2:
        return any(isinstance(n, ast.ClassDef) and n.name == parts[0]
                   and any(isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and m.name == parts[1] for m in n.body)
                   for n in tree.body)
    return False


def load_registry(root: Path, name: str) -> dict[tuple[str, str], dict]:
    registry = json.loads(local_file(root, name).read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("version") != 1:
        raise ValueError("persona regression registry version must be 1")
    entries = registry.get("findings")
    if not isinstance(entries, list) or not entries:
        raise ValueError("persona regression registry must contain findings")
    result = {}
    for row in entries:
        if not isinstance(row, dict):
            raise ValueError("finding entry is not an object")
        missing = [k for k in FIELDS if not isinstance(row.get(k), str)
                   or not row[k].strip()]
        if missing:
            raise ValueError(f"finding entry missing fields: {missing}")
        key = (row["run_id"], row["finding_id"])
        if key in result:
            raise ValueError(f"duplicate finding: {key!r}")
        if not all(re.fullmatch(r"[0-9a-f]{40}" if k == "source_head" else r"[0-9a-f]{64}", row[k]) for k in ("source_head", "contract_sha256")):
            raise ValueError(f"invalid source/contract digest: {key!r}")
        if not row["regression_case"].split(".")[-1].startswith("test_"):
            raise ValueError(f"not a test method: {key!r}")
        if not row["scenario_id"].startswith("FCS-"):
            raise ValueError(f"invalid scenario ID: {key!r}")
        test = local_file(root, row["regression_file"])
        if test.suffix != ".py" or not has_test_case(test, row["regression_case"]):
            raise ValueError(f"regression test case not found: {key!r}")
        result[key] = row
    return result


def read_ledger(path: Path) -> list[dict]:
    """Read a frozen TSV read-only; do not change its status or counts."""
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames or not LEDGER_FIELDS.issubset(reader.fieldnames):
            raise ValueError("invalid frozen findings ledger columns")
        rows = list(reader)
    if any(not row.get("FINDING_ID", "").strip() for row in rows):
        raise ValueError("finding ledger contains empty ID")
    ids = [row["FINDING_ID"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("finding ledger contains duplicate IDs")
    return rows


def read_source_identity(ledger: Path, run_id: str) -> tuple[str, str]:
    """Require the retained audit run metadata and exact original source identity."""
    run_env = ledger.parent.parent / "run.env"
    if not run_env.is_file():
        raise ValueError(f"frozen run metadata missing: {run_env}")
    fields = {}
    for line in run_env.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    if fields.get("RUN_ID") != run_id:
        raise ValueError("requested run_id does not match frozen run metadata")
    head = fields.get("PRODUCT_SOURCE_HEAD", "")
    contract = fields.get("TEST_CONTRACT_FILE_SHA256", "")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not re.fullmatch(r"[0-9a-f]{64}", contract):
        raise ValueError("frozen run source/contract identity is incomplete")
    return head, contract


def audit(root: Path, registry_name: str, ledger: Path | None,
          run_id: str | None) -> dict:
    linked = load_registry(root, registry_name)
    output = {
        "kind": "DEVELOPMENT_REGRESSION_LINK_AUDIT",
        "user_gate_result": "NOT_EVALUATED",
        "release_authorization": "NONE",
        "registry_validated": len(linked),
        "source_run": run_id,
        "open_findings": 0,
        "linked_open_findings": 0,
        "unlinked_findings": [],
        "linked_cases": [],
    }
    if ledger is None:
        return output
    if not run_id:
        raise ValueError("--run-id required with --ledger")
    source_head, contract_sha = read_source_identity(ledger, run_id)
    output["source_head"] = source_head
    output["contract_sha256"] = contract_sha
    for item in read_ledger(ledger):
        # Only explicitly disposed findings are skipped. Unexpected/new status
        # values fail open for review instead of silently hiding user defects.
        if item["STATUS"].strip().upper() in {"CLOSED", "RESOLVED", "DISPOSITIONED", "NON_ACTIONABLE"}:
            continue
        finding_id = item["FINDING_ID"].strip()
        output["open_findings"] += 1
        row = linked.get((run_id, finding_id))
        if row is None:
            output["unlinked_findings"].append({
                "finding_id": finding_id,
                "severity": item["SEVERITY"],
                "surface": item["SURFACE"],
            })
        else:
            if row["source_head"] != source_head or row["contract_sha256"] != contract_sha:
                raise ValueError(f"regression link has wrong run identity: {finding_id}")
            output["linked_open_findings"] += 1
            output["linked_cases"].append({
                "finding_id": finding_id,
                "scenario_id": row["scenario_id"],
                "regression_file": row["regression_file"],
                "regression_case": row["regression_case"],
            })
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--registry", default="tests/persona-regression-links.json")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--strict-findings", action="store_true",
                        help="fail when a frozen OPEN finding lacks a linked regression")
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.root, args.registry, args.ledger, args.run_id)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"PERSONA_FEEDBACK=INVALID: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if args.strict_findings and report["unlinked_findings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
