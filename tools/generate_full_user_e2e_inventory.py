#!/usr/bin/env python3
"""Freeze the 116 official Full User E2E scenario headings, auditor-only.

This extractor preserves the current canonical contract terminology and
ordering. It never invokes a product, Codex, a persona or an E2E test, and it
does NOT decide scenario applicability, product health or PASS.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

REPO = Path("/home/aella/datarelay-link-current")
CANONICAL = REPO / "docs/FULL_USER_E2E_SCENARIOS.md"
PATTERN = re.compile(
    r"^## ((?:U|O|A|S|C|P|X)-[0-9]{3})\s+[—:-]\s+(.+)$",
    re.MULTILINE,
)
EXPECTED_COUNTS = {"U": 13, "O": 15, "A": 20, "S": 20,
                   "C": 15, "P": 24, "X": 9}
FIELDS = ("SCENARIO_ID", "ROLE_GROUP", "HEADING", "REQUIREMENT_TEXT")


def parse_scenarios(content: str) -> list[dict]:
    rows: list[dict] = []
    for scenario_id, heading in PATTERN.findall(content):
        group = scenario_id.split("-", 1)[0]
        # Preserve the original requirement text instead of inventing
        # applicability or relaxing any MANDATORY/CONDITIONAL obligation.
        required = ""
        if " — " in heading:
            required = heading.rsplit(" — ", 1)[1]
        rows.append({
            "SCENARIO_ID": scenario_id,
            "ROLE_GROUP": group,
            "HEADING": heading,
            "REQUIREMENT_TEXT": required,
        })
    if len(rows) != 116:
        raise ValueError("Canonical E2E headings must number exactly 116")
    ids = [r["SCENARIO_ID"] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate canonical E2E scenario heading")
    counts = {name: sum(row["ROLE_GROUP"] == name for row in rows)
              for name in EXPECTED_COUNTS}
    if counts != EXPECTED_COUNTS:
        raise ValueError("Canonical E2E role-group inventory drift")
    if any(not r["REQUIREMENT_TEXT"] for r in rows):
        raise ValueError("Canonical E2E heading lacks explicit condition")
    return rows


def write_inventory(*, root: Path, content: str, repo_head: str,
                    document_path: Path = CANONICAL) -> Path:
    if root.is_symlink():
        raise ValueError("E2E RUN_ID root may not be a symlink")
    dest = root.resolve()
    if dest == Path("/tmp") or Path("/tmp") in dest.parents:
        raise ValueError("E2E evidence must be durable, not under /tmp")
    if not dest.is_dir() or dest.stat().st_mode & 0o077:
        raise ValueError("E2E RUN_ID root must exist and be owner-private")
    if not re.fullmatch(r"[0-9a-f]{40}", repo_head):
        raise ValueError("Expected commit HEAD must be 40 lower-case hex")
    rows = parse_scenarios(content)
    ledger = dest / "ledger"
    ledger.mkdir(mode=0o700, exist_ok=True)
    ledger.chmod(0o700)
    path = ledger / "scenario-inventory.tsv"
    meta = ledger / "scenario-inventory-source.json"
    if path.exists() or meta.exists():
        raise FileExistsError("E2E contract inventory already frozen for this RUN_ID")
    with path.open("x", newline="", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    receipt = {
        "source_path": str(document_path),
        "source_head": repo_head,
        "source_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "frozen_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scenario_count": len(rows),
        "role_counts": EXPECTED_COUNTS,
        "scenario_ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "evidence_kind": "AUDITOR_SUPPORTING_INVENTORY_NOT_ACTUAL_E2E",
        "actual_codex_persona_test_completed": False,
    }
    with meta.open("x", encoding="utf-8") as handle:
        os.chmod(meta, 0o600)
        json.dump(receipt, handle, indent=2)
        handle.write("\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    source = CANONICAL.read_text(encoding="utf-8")
    head = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"],
        text=True, timeout=8,
    ).strip()
    try:
        outfile = write_inventory(root=args.run_root, content=source,
                                  repo_head=head)
    except (OSError, ValueError) as exc:
        print("SCENARIO_INVENTORY_BLOCKED=" + type(exc).__name__ + ": " + str(exc))
        return 2
    print(json.dumps({"source_head": head, "scenarios": 116,
                      "inventory_path": str(outfile),
                      "user_or_ai_test_executed": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
