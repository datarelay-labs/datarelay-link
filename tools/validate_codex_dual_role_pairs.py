#!/usr/bin/env python3
"""Auditor-only consistency check for Codex Direct-vs-AI persona evidence.

This tool never executes a product command, launches Codex or converts
synthetic/CLI evidence into an actual user-test PASS.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
OUTCOMES = {
    "PASS", "FAIL", "PARTIAL", "BLOCKED_TOOLING",
    "BLOCKED_ENVIRONMENT", "BLOCKED", "NOT_RUN", "NOT_APPLICABLE",
}
FIELDS = (
    "PAIR_ID", "SCENARIO_ID", "FEATURE_ID", "ROLE",
    "AUDITOR_CODEX_THREAD", "DIRECT_CODEX_THREAD",
    "AI_OPERATOR_CODEX_THREAD", "AI_ADVISER_CODEX_THREAD",
    "DIRECT_GOAL_SHA256", "AI_GOAL_SHA256",
    "DIRECT_BASELINE_SHA256", "AI_BASELINE_SHA256",
    "DIRECT_SOURCE_HEAD", "AI_SOURCE_HEAD",
    "DIRECT_RESULT", "AI_RESULT", "FINAL_RESULT",
    "DIRECT_EVIDENCE", "AI_FIRST_ANSWER_EVIDENCE",
    "AI_FIRST_ANSWER_SHA256", "AI_OPERATOR_EVIDENCE", "BLOCK_REASON",
)


def read_tsv(path: Path, required: tuple[str, ...]) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        missing = set(required) - set(reader.fieldnames or ())
        if missing:
            raise ValueError("Missing ledger columns: " + ",".join(sorted(missing)))
        return list(reader)


def evidence_file(root: Path, ref: str) -> Path | None:
    if not ref or Path(ref).is_absolute():
        return None
    user_path = root / ref
    p = user_path.resolve()
    if (user_path.is_symlink() or not p.is_relative_to(root.resolve())
            or not p.is_file()):
        return None
    if p.stat().st_size == 0:
        return None
    return p


def evaluate(
    rows: list[dict], *,
    evidence_root: Path,
    expected_ids: set[str],
    expected_features: set[str],
    expected_head: str,
) -> dict:
    problems: list[str] = []
    seen_pairs: set[str] = set()
    present_scenarios: set[str] = set()
    present_features: set[str] = set()
    fresult = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "BLOCKED": 0, "N_A": 0}
    for number, row in enumerate(rows, 1):
        pair = str(row.get("PAIR_ID") or "").strip()
        prefix = f"row {number} pair {pair or '-'}"
        scenario = str(row.get("SCENARIO_ID") or "").strip()
        feature = str(row.get("FEATURE_ID") or "").strip()
        if not pair or pair in seen_pairs:
            problems.append(prefix + ": missing/duplicate PAIR_ID")
        seen_pairs.add(pair)
        if scenario not in expected_ids:
            problems.append(prefix + ": unexpected scenario")
        else:
            present_scenarios.add(scenario)
        if not feature or feature not in expected_features:
            problems.append(prefix + ": unknown/unmapped feature")
        else:
            present_features.add(feature)

        direct = str(row.get("DIRECT_RESULT") or "").upper().strip()
        ai = str(row.get("AI_RESULT") or "").upper().strip()
        final = str(row.get("FINAL_RESULT") or "").upper().strip()
        if any(status not in OUTCOMES for status in (direct, ai, final)):
            problems.append(prefix + ": unknown result")
            continue
        if final == "PASS":
            fresult["PASS"] += 1
        elif final == "FAIL":
            fresult["FAIL"] += 1
        elif final == "NOT_APPLICABLE":
            fresult["N_A"] += 1
        elif final.startswith("BLOCKED"):
            fresult["BLOCKED"] += 1
        else:
            fresult["PARTIAL"] += 1

        if final != "PASS" and not str(row.get("BLOCK_REASON") or "").strip():
            problems.append(prefix + ": non-PASS disposition lacks reason")
        if direct == "PASS" and ai != "PASS" and final == "PASS":
            problems.append(prefix + ": Direct PASS with missing/failed AI cannot PASS")
        if final == "PASS" and (direct != "PASS" or ai != "PASS"):
            problems.append(prefix + ": FINAL PASS requires both direct and AI PASS")
        if final == "NOT_APPLICABLE":
            if direct != "NOT_APPLICABLE" or ai != "NOT_APPLICABLE":
                problems.append(prefix + ": N/A only when both lanes N/A")
            continue

        for key in ("DIRECT_GOAL_SHA256", "AI_GOAL_SHA256",
                    "DIRECT_BASELINE_SHA256", "AI_BASELINE_SHA256"):
            if not HEX64.fullmatch(str(row.get(key) or "")):
                problems.append(prefix + ": invalid " + key)
        if row.get("DIRECT_GOAL_SHA256") != row.get("AI_GOAL_SHA256"):
            problems.append(prefix + ": Direct/AI goals differ")
        if row.get("DIRECT_BASELINE_SHA256") != row.get("AI_BASELINE_SHA256"):
            problems.append(prefix + ": Direct/AI starting baselines differ")
        for key in ("DIRECT_SOURCE_HEAD", "AI_SOURCE_HEAD"):
            val = str(row.get(key) or "")
            if not HEX40.fullmatch(val) or val != expected_head:
                problems.append(prefix + ": installed Source HEAD mismatch " + key)

        if final == "PASS":
            ids = [str(row.get(key) or "") for key in (
                "AUDITOR_CODEX_THREAD", "DIRECT_CODEX_THREAD",
                "AI_OPERATOR_CODEX_THREAD", "AI_ADVISER_CODEX_THREAD",
            )]
            if any(not ident for ident in ids) or len(set(ids)) != 4:
                problems.append(prefix + ": missing/identical Codex actor contexts")
            if not row.get("ROLE"):
                problems.append(prefix + ": missing role")
            for key in ("DIRECT_EVIDENCE", "AI_FIRST_ANSWER_EVIDENCE",
                        "AI_OPERATOR_EVIDENCE"):
                path = evidence_file(evidence_root, str(row.get(key) or ""))
                if path is None:
                    problems.append(prefix + ": missing/unsafe/empty " + key)
                elif key == "AI_FIRST_ANSWER_EVIDENCE":
                    sha = hashlib.sha256(path.read_bytes()).hexdigest()
                    if sha != row.get("AI_FIRST_ANSWER_SHA256"):
                        problems.append(prefix + ": first AI answer SHA256 mismatch")

    for scenario in sorted(expected_ids - present_scenarios):
        problems.append("missing scenario " + scenario)
    for feature in sorted(expected_features - present_features):
        problems.append("missing feature " + feature)
    return {
        "EVIDENCE_SCHEMA": "PASS" if not problems else "FAIL",
        "PAIR_ROWS": len(rows),
        "SCENARIO_COVERAGE": len(present_scenarios),
        "EXPECTED_SCENARIOS": len(expected_ids),
        "FEATURE_COVERAGE": len(present_features),
        "EXPECTED_FEATURES": len(expected_features),
        "PAIR_RESULTS": fresult,
        "ALL_PAIRS_STRUCTURALLY_PASS": bool(
            rows and not problems and fresult["PASS"] == len(rows)
        ),
        "ACTUAL_CODEX_ROLE_EXECUTION_VERIFIED": False,
        "PRODUCT_E2E_PASS_PROVEN": False,
        "ERRORS": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["fcs", "full-e2e"], required=True)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--feature-inventory", type=Path, required=True)
    parser.add_argument("--scenario-inventory", type=Path)
    args = parser.parse_args()
    if not HEX40.fullmatch(args.expected_head):
        parser.error("expected HEAD must be a 40-character lowercase hex SHA")
    if args.mode == "fcs":
        expected = {f"FCS-{i:03d}" for i in range(1, 16)}
    else:
        if args.scenario_inventory is None:
            parser.error("full-e2e needs its canonical 116-ID scenario inventory")
        scenario_rows = read_tsv(args.scenario_inventory, ("SCENARIO_ID",))
        expected = {row["SCENARIO_ID"] for row in scenario_rows}
        if len(expected) != 116 or len(scenario_rows) != 116:
            parser.error("full-e2e inventory must contain exactly 116 unique scenarios")
    inventory = read_tsv(args.feature_inventory, ("FEATURE_ID", "SUPPORTED"))
    features = {str(row["FEATURE_ID"]) for row in inventory
                if str(row["SUPPORTED"]).upper().strip() == "YES"}
    if not features:
        parser.error("feature inventory must contain at least one supported feature")
    rows = read_tsv(args.pairs, FIELDS)
    report = evaluate(rows, evidence_root=args.evidence_root,
                      expected_ids=expected, expected_features=features,
                      expected_head=args.expected_head)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["EVIDENCE_SCHEMA"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
