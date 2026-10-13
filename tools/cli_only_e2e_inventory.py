#!/usr/bin/env python3
"""CLI-only E2E auditor inventory/ledger; never executes a product command."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile

CANONICAL = Path(__file__).resolve().parents[1] / "docs/FULL_USER_E2E_SCENARIOS.md"
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
SCENARIO_RE = re.compile(
    r"^## ((?:U|O|A|S|C|P|X)-[0-9]{3})\s+[—:-]\s+(.+)$", re.MULTILINE
)
EXPECTED_GROUPS = {"U": 13, "O": 15, "A": 20, "S": 20, "C": 15, "P": 24, "X": 9}
# Explicit scope exclusions ONLY. All other parts stay mandatory as in the
# original canonical contract; no "not applicable" for an inaccessible host.
EXCLUDED = frozenset({
    "U-007", "U-011", "O-013", "O-014", "A-006", "C-006", "P-011",
    "X-001", "X-002", "X-003", "X-004", "X-005",
    "X-007", "X-008", "X-009", "X-010",
})
# Scenario remains in scope: omit ONLY its AI-support/MCP/Plugin substeps.
MIXED = {
    "U-009": "Public CLI hostname/bootstrap/DNS stays; exclude MCP-specific public endpoint",
    "U-013": "Direct CLI terminology/discovery stays; exclude AI-generated recommendations",
    "A-004": "Remote Access CLI policy stays; exclude AI-specific workflows",
    "A-007": "Network/Service/Managed Host references stay; exclude AI Identity/Permission references",
    "A-009": "Server CLI backup/restore stays; exclude AI-identity-specific state",
    "A-011": "Server CLI system actions stay; exclude MCP endpoint/TLS/OAuth acceptance",
    "A-012": "Zero-Touch credential lifecycle stays; exclude AI identity references",
    "A-016": "Command-to-use-case/ID/Direct evidence traceability stays; exclude AI mirrors",
    "S-017": "CLI-driven DNS/TLS/hostname failure/recovery stays; exclude MCP-specific OAuth/TLS",
    "S-024": "All non-AI operator/admin mistakes stay; exclude AI-assisted variants",
    "C-015": "Direct roles and non-AI mistakes under load stay; exclude AI-assisted role",
    "P-023": "All non-AI/MCP topology mixed stress stays; exclude AI/MCP-only traffic",
    "P-024": "All non-AI CLI/function-under-load collisions stay; exclude AI/MCP lanes",
}
assert not EXCLUDED.intersection(MIXED)
FIELDS = (
    "RUN_ID", "SCENARIO_ID", "ORIGINAL_HEADING", "MANDATORY_OR_CONDITIONAL",
    "SCOPE", "REMOVED_SUBSTEPS", "TARGET_HOSTS", "SOURCE_HEAD",
    "INSTALLED_HEAD", "ACTUAL_COMMAND", "RESULT", "EVIDENCE",
    "CLEANUP", "SKIP_REASON", "START_UTC", "END_UTC",
    "PERFORMANCE_PROFILE", "NOTES",
)
OUTCOMES = frozenset({
    "NOT_RUN", "IN_PROGRESS", "PASS", "FAIL", "PARTIAL",
    "BLOCKED_ENVIRONMENT", "BLOCKED_TOOLING", "BLOCKED_PLATFORM_DENIAL",
    "BLOCKED_MANAGEMENT_PATH", "FAIL_PRECONDITION", "MEASURED_NOT_QUALIFIED",
    "EXCLUDED_AI_MCP",
})
BLOCKED = {x for x in OUTCOMES if x.startswith("BLOCKED_")}
FINAL_FAILURE = {"FAIL", "PARTIAL", "FAIL_PRECONDITION", "MEASURED_NOT_QUALIFIED"} | BLOCKED


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def default_targets(group: str) -> str:
    if group in {"A"}:
        return "frp-e2e-server"
    if group in {"U", "O"}:
        return "frp-e2e-server;frp-e2e-client;frp-e2e-aws;applicable-native-hosts"
    return "frp-e2e-server;frp-e2e-client;frp-e2e-aws;frp-e2e-rocky8;frp-e2e-rocky9-rescue;frp-e2e-windows"


def scopes(content: str) -> list[dict[str, str]]:
    result = []
    for match in SCENARIO_RE.finditer(content):
        sid, heading = match.groups()
        group = sid.split("-", 1)[0]
        condition = heading.rsplit(" — ", 1)[-1] if " — " in heading else ""
        state = "EXCLUDED_AI_MCP" if sid in EXCLUDED else (
            "CLI_PART_ONLY" if sid in MIXED else "CLI_ALL"
        )
        result.append({
            "SCENARIO_ID": sid,
            "ORIGINAL_HEADING": heading,
            "MANDATORY_OR_CONDITIONAL": condition,
            "SCOPE": state,
            "REMOVED_SUBSTEPS": (
                "Owner-explicit AI-support/MCP/Plugin exclusion" if sid in EXCLUDED
                else MIXED.get(sid, "")
            ),
            "TARGET_HOSTS": "excluded" if sid in EXCLUDED else default_targets(group),
        })
    identifiers = [x["SCENARIO_ID"] for x in result]
    actual_groups = collections.Counter(x["SCENARIO_ID"][0] for x in result)
    if len(result) != 116 or len(set(identifiers)) != 116 or actual_groups != EXPECTED_GROUPS:
        raise ValueError("canonical Full User E2E 116-ID inventory drift")
    if any(not x["MANDATORY_OR_CONDITIONAL"] for x in result):
        raise ValueError("canonical scenario requirement label missing")
    if not EXCLUDED.issubset(identifiers) or not set(MIXED).issubset(identifiers):
        raise ValueError("explicit CLI-only scope mapping contains invalid ID")
    return result


def safe_root(root: Path):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("private run root must be an existing real directory")
    if root.stat().st_mode & 0o077:
        raise ValueError("run root must be owner-private (0700)")
    return root.resolve()


def ledger_path(root: Path) -> Path:
    return safe_root(root) / "ledger/scenario-results.tsv"


def write_atomic(path: Path, rows: list[dict]):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", newline="", encoding="utf-8", dir=path.parent,
        prefix=".cli-only-ledger-", delete=False,
    ) as fh:
        temp = Path(fh.name)
        os.chmod(temp, 0o600)
        try:
            writer = csv.DictWriter(fh, fieldnames=FIELDS, delimiter="\t",
                                    extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            fh.flush()
            os.fsync(fh.fileno())
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
    os.replace(temp, path)


def initialize(root: Path, canonical_text: str, source_head: str):
    if not HEAD_RE.fullmatch(source_head):
        raise ValueError("source_head must be exact 40-hex Git SHA")
    root = safe_root(root)
    dst = root / "ledger/scenario-results.tsv"
    meta = root / "ledger/contract-source.json"
    if dst.exists() or meta.exists():
        raise FileExistsError("current-run CLI-only inventory already initialized")
    inventory = scopes(canonical_text)
    run_id = root.name
    rows = []
    for scenario in inventory:
        excluded = scenario["SCOPE"] == "EXCLUDED_AI_MCP"
        rows.append({
            **scenario, "RUN_ID": run_id, "SOURCE_HEAD": source_head,
            "INSTALLED_HEAD": "", "ACTUAL_COMMAND": "",
            "RESULT": "EXCLUDED_AI_MCP" if excluded else "NOT_RUN",
            "EVIDENCE": "", "CLEANUP": "", "SKIP_REASON":
                "Excluded solely by owner: AI support/MCP/Plugin" if excluded else "",
            "START_UTC": "", "END_UTC": "",
            "PERFORMANCE_PROFILE": "8h/24h OPTIONAL; base 3600s REQUIRED"
                if scenario["SCENARIO_ID"] == "P-019" else "",
            "NOTES": "",
        })
    write_atomic(dst, rows)
    receipt = {
        "canonical_path": "docs/FULL_USER_E2E_SCENARIOS.md",
        "canonical_sha256": hashlib.sha256(canonical_text.encode()).hexdigest(),
        "repository_head": source_head,
        "frozen_utc": utc_now(),
        "row_count": len(rows),
        "excluded_ai_mcp": sum(x["SCOPE"] == "EXCLUDED_AI_MCP" for x in inventory),
        "in_scope": sum(x["SCOPE"] != "EXCLUDED_AI_MCP" for x in inventory),
        "execution_count": 0,
        "not_a_full_user_e2e": True,
        "not_product_pass": True,
    }
    meta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with meta.open("x", encoding="utf-8") as fh:
        os.chmod(meta, 0o600)
        json.dump(receipt, fh, indent=2)
        fh.write("\n")
    return dst


def read_ledger(root: Path):
    with ledger_path(root).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("result ledger schema changed unexpectedly")
        rows = list(reader)
    if len(rows) != 116 or len({x["SCENARIO_ID"] for x in rows}) != 116:
        raise ValueError("scenario ledger coverage drift")
    return rows


def record(
    root: Path, sid: str, *, result: str, target: str,
    installed_head: str, command: str, cleanup: str,
    evidence: str, skip_reason: str, notes: str,
):
    if result not in OUTCOMES - {"NOT_RUN", "EXCLUDED_AI_MCP"}:
        raise ValueError("cannot invent or erase a scenario disposition")
    if installed_head and not HEAD_RE.fullmatch(installed_head):
        raise ValueError("installed Source HEAD must be an exact SHA or unknown")
    if result in BLOCKED | {"FAIL_PRECONDITION", "PARTIAL", "FAIL"} and not skip_reason:
        raise ValueError("blocked/failed/partial criterion needs actual reason")
    if result == "PASS" and not (target and command and evidence and
                                cleanup in {"DONE", "NO_OWNED_RESOURCES"}):
        raise ValueError("PASS requires actual command, evidence and verified cleanup")
    safe_root(root)
    rows = read_ledger(root)
    matching = [x for x in rows if x["SCENARIO_ID"] == sid]
    if not matching:
        raise ValueError("not a canonical scenario ID")
    current = matching[0]
    if current["SCOPE"] == "EXCLUDED_AI_MCP":
        raise ValueError("excluded AI/MCP scenario cannot be promoted into CLI-only E2E")
    if current["RESULT"] == "PASS":
        raise ValueError("freeze passed evidence; use a new RUN_ID to retest")
    if result == "PASS":
        if installed_head != current["SOURCE_HEAD"]:
            raise ValueError("current candidate must equal actually installed Source HEAD")
        if not evidence_file(root, evidence):
            raise ValueError("PASS evidence path must be safe and contain actual output")
    if evidence and not evidence_file(root, evidence):
        raise ValueError("evidence file absent, empty or outside private RUN_ID")
    current.update({
        "INSTALLED_HEAD": installed_head,
        "TARGET_HOSTS": target,
        "ACTUAL_COMMAND": command,
        "RESULT": result,
        "EVIDENCE": evidence,
        "CLEANUP": cleanup,
        "SKIP_REASON": skip_reason,
        "START_UTC": current["START_UTC"] or utc_now(),
        "END_UTC": utc_now() if result != "IN_PROGRESS" else "",
        "NOTES": notes,
    })
    write_atomic(ledger_path(root), rows)
    return current


def evidence_file(root: Path, relative: str):
    if not relative or Path(relative).is_absolute():
        return False
    base = safe_root(root)
    path = (base / relative).resolve()
    return path.is_relative_to(base) and path.is_file() and path.stat().st_size > 0


def summary(rows: list[dict]):
    included = [r for r in rows if r["SCOPE"] != "EXCLUDED_AI_MCP"]
    counts = collections.Counter(r["RESULT"] for r in included)
    mandatory = [r for r in included if r["SCENARIO_ID"] != "P-019"]
    pending = any(r["RESULT"] in {"NOT_RUN", "IN_PROGRESS"} for r in mandatory)
    # "Executable scope complete" is not a pass and includes a truthful
    # exhausted list of explicitly BLOCKED scenarios.
    all_dispositioned = not pending
    qualified = (
        bool(mandatory) and all(r["RESULT"] == "PASS" for r in mandatory)
        and all(r["RESULT"] in {"PASS", "NOT_RUN"} for r in included)
    )
    return {
        "SCENARIOS_CANONICAL": len(rows),
        "SCENARIOS_CLI_SCOPE": len(included),
        "EXCLUDED_AI_MCP": len(rows) - len(included),
        "PASS": counts["PASS"],
        "NOT_RUN": counts["NOT_RUN"],
        "IN_PROGRESS": counts["IN_PROGRESS"],
        "FAIL": counts["FAIL"],
        "PARTIAL": counts["PARTIAL"],
        "BLOCKED": sum(counts[key] for key in BLOCKED),
        "MEASURED_NOT_QUALIFIED": counts["MEASURED_NOT_QUALIFIED"],
        "EXECUTABLE_SCOPE_COMPLETE": all_dispositioned,
        "ALL_APPLICABLE_CLI_E2E_PASS": qualified,
        "FULL_USER_E2E_PASS": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["init", "record", "summary"])
    p.add_argument("--run-root", type=Path, required=True)
    p.add_argument("--source-head")
    p.add_argument("--scenario-id")
    p.add_argument("--result")
    p.add_argument("--target", default="")
    p.add_argument("--installed-head", default="")
    p.add_argument("--actual-command", default="")
    p.add_argument("--evidence", default="")
    p.add_argument("--cleanup", default="")
    p.add_argument("--skip-reason", default="")
    p.add_argument("--notes", default="")
    args = p.parse_args()
    if args.action == "init":
        if not args.source_head:
            p.error("init needs --source-head")
        initialize(args.run_root, CANONICAL.read_text(encoding="utf-8"), args.source_head)
    elif args.action == "record":
        if not args.scenario_id or not args.result:
            p.error("record requires --scenario-id and --result")
        record(args.run_root, args.scenario_id, result=args.result,
               target=args.target, installed_head=args.installed_head,
               command=args.actual_command, evidence=args.evidence,
               cleanup=args.cleanup, skip_reason=args.skip_reason,
               notes=args.notes)
    print(json.dumps(summary(read_ledger(args.run_root)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
