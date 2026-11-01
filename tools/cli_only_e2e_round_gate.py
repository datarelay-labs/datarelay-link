#!/usr/bin/env python3
"""Read-only full-sweep/batch-fix E2E round gate; never executes product actions.

Reads immutable or active 116-ID CLI-only TSV ledgers. No result is promoted:
an exact candidate binding is a minimum evidence check, not proof of real E2E.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from cli_only_e2e_inventory import CANONICAL, EXCLUDED, FIELDS, scopes

HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
OUTCOMES = frozenset({
    "PASS", "FAIL", "PARTIAL", "NOT_RUN", "IN_PROGRESS",
    "FAIL_PRECONDITION", "BLOCKED_ENVIRONMENT", "BLOCKED_TOOLING",
    "BLOCKED_PLATFORM_DENIAL", "BLOCKED_MANAGEMENT_PATH",
    "MEASURED_NOT_QUALIFIED", "EXCLUDED_AI_MCP", "OPTIONAL_NOT_SELECTED",
})
PENDING = {"NOT_RUN", "IN_PROGRESS"}
DEFICIENT = OUTCOMES - {"PASS", "EXCLUDED_AI_MCP", "OPTIONAL_NOT_SELECTED"}


def load_ledger(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("ledger must be an existing non-symlink file")
    raw = path.read_bytes()
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("missing canonical 116-ID ledger fields")
        rows = list(reader)
    canonical = {r["SCENARIO_ID"]: r for r in scopes(CANONICAL.read_text(encoding="utf-8"))}
    if len(rows) != 116 or len({r["SCENARIO_ID"] for r in rows}) != 116:
        raise ValueError("expected 116 unique canonical scenario IDs")
    for r in rows:
        sid, result = r["SCENARIO_ID"], r["RESULT"]
        if sid not in canonical or r["SCOPE"] != canonical[sid]["SCOPE"]:
            raise ValueError("scenario ID/scope mismatch")
        if result not in OUTCOMES:
            raise ValueError("unsupported result")
        if sid in EXCLUDED:
            if result != "EXCLUDED_AI_MCP":
                raise ValueError("AI/MCP exclusion cannot be promoted to PASS")
        elif result == "EXCLUDED_AI_MCP":
            raise ValueError("extra AI/MCP exclusion")
        if result == "OPTIONAL_NOT_SELECTED" and sid != "P-019":
            raise ValueError("only P-019 is optional")
        if not HEAD_RE.fullmatch(r["SOURCE_HEAD"]):
            raise ValueError("scenario source HEAD must be an exact Git SHA")
    heads = {r["SOURCE_HEAD"] for r in rows}
    if len(heads) != 1:
        raise ValueError("mixed candidate source HEAD in one ledger")
    return {
        "head": heads.pop(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "rows": {r["SCENARIO_ID"]: r for r in rows},
    }


def minimum_exact_receipts(row: dict, head: str) -> bool:
    """A necessary but NOT sufficient condition for a native E2E PASS."""
    return (
        row["RESULT"] == "PASS"
        and row["SOURCE_HEAD"] == head
        and row["INSTALLED_HEAD"] == head
        and bool(row["ACTUAL_COMMAND"].strip())
        and bool(row["EVIDENCE"].strip())
    )


def audit(data: dict) -> dict:
    rows = data["rows"]
    applied = {s: r for s, r in rows.items() if s not in EXCLUDED}
    mandatory = {s: r for s, r in applied.items() if s != "P-019"}
    counts = Counter(r["RESULT"] for r in applied.values())
    missing = sorted(s for s, r in mandatory.items() if r["RESULT"] in PENDING)
    weak = sorted(s for s, r in applied.items()
                  if r["RESULT"] == "PASS" and not minimum_exact_receipts(r, data["head"]))
    blockers = sorted(s for s, r in applied.items() if r["RESULT"].startswith("BLOCKED_")
                      or r["RESULT"] == "FAIL_PRECONDITION")
    failed = sorted(s for s, r in applied.items() if r["RESULT"] == "FAIL")
    partial = sorted(s for s, r in applied.items() if r["RESULT"] == "PARTIAL")
    empty_blocker_reason = sorted(
        s for s in blockers if not (applied[s]["SKIP_REASON"].strip()
                                    or applied[s]["NOTES"].strip())
    )
    if missing:
        stage = "FINISH_FULL_SWEEP"
    elif failed or partial or blockers or counts["MEASURED_NOT_QUALIFIED"] or weak:
        stage = "FREEZE_THEN_BATCH_FIX"
    else:
        stage = "CHECK_COMPLETE_NATIVE_ACCEPTANCE"
    pass_gate = stage == "CHECK_COMPLETE_NATIVE_ACCEPTANCE" and all(
        r["RESULT"] == "PASS" for r in mandatory.values())
    return {
        "schema": "drlink.cli_only.round_gate.v1",
        "candidate_source_head": data["head"],
        "immutable_input_sha256": data["sha256"],
        "canonical_total": len(rows),
        "cli_only_scope": len(applied),
        "ai_mcp_excluded": len(EXCLUDED),
        "dispositions": dict(sorted(counts.items())),
        "mandatory_not_run_or_in_progress": missing,
        "fail_ids": failed,
        "partial_ids": partial,
        "blocked_or_failed_prerequisite_ids": blockers,
        "blocked_missing_reason_ids": empty_blocker_reason,
        "pass_without_exact_native_minimum_receipts": weak,
        "exact_head_minimum_receipt_pass_count": sum(
            minimum_exact_receipts(r, data["head"]) for r in applied.values()),
        "phase": stage,
        "full_sweep_dispositioned": not missing,
        "all_applicable_cli_e2e_pass": pass_gate,
        "note": ("Native source binding/receipt fields are minimum checks only. "
                 "Real user actions, effects, runtime identity and traffic "
                 "must still be independently verified; this audit runs no tests."),
    }


def compare(before: dict, after: dict) -> dict:
    left, right = before["rows"], after["rows"]
    promotions = []
    stale_promotions = []
    regressions = []
    unchanged_defects = []
    changes = []
    for sid in sorted(set(left) - EXCLUDED):
        a, b = left[sid], right[sid]
        was, now = a["RESULT"], b["RESULT"]
        if was != now:
            changes.append({"id": sid, "before": was, "after": now})
        if was != "PASS" and now == "PASS":
            (promotions if minimum_exact_receipts(b, after["head"])
             else stale_promotions).append(sid)
        if was == "PASS" and now != "PASS":
            regressions.append(sid)
        if was in DEFICIENT and now in DEFICIENT:
            unchanged_defects.append(sid)
    return {
        "before_candidate": before["head"],
        "after_candidate": after["head"],
        "candidate_changed": before["head"] != after["head"],
        "original_frozen_sha256": before["sha256"],
        "new_run_sha256": after["sha256"],
        "disposition_changes": changes,
        "new_pass_with_minimum_exact_native_receipts": promotions,
        "pass_promotions_missing_exact_native_receipts": stale_promotions,
        "regressed_from_pass": regressions,
        "still_not_pass": unchanged_defects,
        "warning": ("Same candidate: not a new fix/retest iteration."
                    if before["head"] == after["head"] else
                    "Different candidate: only exact-native-bound PASS may count as a promotion."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", type=Path, required=True, help="current 116-ID TSV")
    ap.add_argument("--previous-ledger", type=Path, help="prior immutable 116-ID TSV")
    ap.add_argument("--require-full-sweep", action="store_true",
                    help="nonzero if any mandatory scenario remains NOT_RUN/IN_PROGRESS")
    args = ap.parse_args()
    try:
        current = load_ledger(args.ledger)
        report = audit(current)
        if args.previous_ledger:
            report["round_delta"] = compare(load_ledger(args.previous_ledger), current)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(json.dumps({"error": type(exc).__name__, "description": str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 3 if args.require_full_sweep and not report["full_sweep_dispositioned"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
