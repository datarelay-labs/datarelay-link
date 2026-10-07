#!/usr/bin/env python3
"""Read-only, redacted v2.4 -> v3.0 state observations for qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

# Only persistent configuration columns; no credentials, heartbeat, or audit rows.
TABLE_COLUMNS = {
    "clients": ("id", "label", "description", "hostname", "trust_status"),
    "client_groups": ("id", "name", "description"),
    "client_group_members": ("group_id", "client_id"),
    "client_tags": ("client_id", "key", "value"),
    "published_services": ("id", "client_id", "name", "service_type", "target_mode", "target_host", "target_port", "public_port", "enabled", "released"),
    "port_reservations": ("public_port", "client_id", "service_id", "service_name", "released"),
    "objects": ("id", "name", "type", "origin", "description", "status"),
    "object_values": ("object_id", "value", "normalized"),
    "object_groups": ("id", "name", "description"),
    "object_group_members": ("group_id", "member_kind", "member_id"),
    "policy_rules": ("id", "plane", "name", "position", "action", "enabled", "description"),
    "rule_sources": ("rule_id", "ref_kind", "ref_id"),
    "rule_destinations": ("rule_id", "ref_kind", "ref_id"),
    "rule_services": ("rule_id", "protocol", "port"),
}
V30_TABLES = {"management_change_plans", "management_jobs", "audit_ingest_checkpoints"}


def collect(root: str = "/") -> dict:
    path = Path(root) / "var/lib/drlink/drlink.db"
    # mode=ro cannot silently manufacture an empty DB on a stale installation.
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise ValueError("control database integrity check failed")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = {}
        for table, columns in TABLE_COLUMNS.items():
            rows = list(conn.execute("SELECT " + ",".join(columns) + " FROM " + table))
            # Stable order without leaking identities or configuration values.
            encoded = sorted(json.dumps(list(row), ensure_ascii=True, separators=(",", ":")) for row in rows)
            result[table] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(encoded).encode()).hexdigest()}
        return {"schema_version": 1, "integrity": "ok", "tables": result,
                "v30_tables_present": sorted(V30_TABLES & tables)}
    finally:
        conn.close()


def compare(before: dict, after: dict) -> dict:
    for observation in (before, after):
        if observation.get("schema_version") != 1 or observation.get("integrity") != "ok":
            raise ValueError("invalid upgrade state observation")
        for table in TABLE_COLUMNS:
            row = observation.get("tables", {}).get(table, {})
            if type(row.get("count")) is not int or row["count"] < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256", ""))):
                raise ValueError("missing/invalid table observation: " + table)
    bt, at = before["tables"], after["tables"]
    changed = [table for table in TABLE_COLUMNS if bt[table] != at[table]]
    host_tables = {"clients", "client_groups", "client_group_members", "client_tags", "published_services", "port_reservations"}
    policies = set(TABLE_COLUMNS) - host_tables
    host_result = "PASS" if not host_tables.intersection(changed) else "FAIL"
    if bt["clients"]["count"] == 0 or bt["published_services"]["count"] == 0:
        host_result = "BLOCKED"  # Empty inventories are not preservation proof.
    policy_result = "PASS" if not policies.intersection(changed) else "FAIL"
    if bt["policy_rules"]["count"] == 0:
        policy_result = "BLOCKED"
    migrated = "PASS" if V30_TABLES <= set(after.get("v30_tables_present", [])) else "FAIL"
    return {"changed_tables": changed, "managed_hosts": host_result,
            "policy": policy_result, "control_db": migrated,
            "nonempty_hosts": bt["clients"]["count"],
            "nonempty_services": bt["published_services"]["count"]}


def verify_runtime(text: str, source_head: str, version: str) -> None:
    sources = re.findall(r"^Source HEAD:\s*(\S+)\s*$", text, re.M)
    if not re.fullmatch(r"[0-9a-f]{40}", source_head) or sources != [source_head]:
        raise ValueError("installed runtime source differs from qualified artifact")
    if not re.search(r"^Data Relay Link:\s*" + re.escape(version) + r"(?:[+\-\s]|$)", text, re.M):
        raise ValueError("installed runtime version differs from candidate")


OBSERVATION_FILES = (
    "before-state.json", "after-state.json", "reboot-state.json",
    "v240-version.txt", "v300-health.txt", "reboot-health.txt",
    "boot-before.txt", "boot-after.txt",
)


def verify_evidence(document: dict, *, require_prior_stable: bool = True) -> None:
    """Validate retained observations, not success labels supplied by a runner."""
    root_text = document.get("evidence_root")
    if not isinstance(root_text, str) or not root_text:
        raise ValueError("retained upgrade observations are missing")
    root = Path(root_text).resolve(strict=True)
    checksums = document.get("observations")
    if not isinstance(checksums, dict):
        raise ValueError("upgrade observation checksums are missing")
    texts = {}
    for name in OBSERVATION_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            raise ValueError("missing/unsafe upgrade observation: " + name)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksums.get(name):
            raise ValueError("upgrade observation digest mismatch: " + name)
        texts[name] = raw.decode("utf-8")
    before = json.loads(texts["before-state.json"])
    for name in ("after-state.json", "reboot-state.json"):
        result = compare(before, json.loads(texts[name]))
        if any(result[k] != "PASS" for k in ("managed_hosts", "policy", "control_db")):
            raise ValueError("upgrade preservation not proven: " + name + " " + json.dumps(result, sort_keys=True))
    verify_runtime(texts["v240-version.txt"], str(document.get("prior_source_head", "")), "2.4.0")
    for name in ("v300-health.txt", "reboot-health.txt"):
        verify_runtime(texts[name], str(document.get("source_head", "")), "3.0.0")
    boots = [texts[name].strip() for name in ("boot-before.txt", "boot-after.txt")]
    if any(not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", x) for x in boots) or boots[0] == boots[1]:
        raise ValueError("observed reboot identity did not change")
    if require_prior_stable and (
        document.get("baseline_release_qualified") is not True
        or document.get("prior_channel") != "stable"
        or not re.search(r"^Channel:\s*stable\s*$", texts["v240-version.txt"], re.M)
    ):
        raise ValueError("development baseline cannot prove a prior-stable upgrade")


def build_observation_manifest(evidence_root: str, prior_source_head: str, source_head: str) -> dict:
    """Package retained observations without executing lifecycle or certifying release.

    A version string saying stable is not release-qualification evidence. This
    read-only producer therefore never sets baseline_release_qualified to True;
    the release consumer must still validate that separate authority boundary.
    """
    root = Path(evidence_root).resolve(strict=True)
    observations = {}
    prior_text = ""
    for name in OBSERVATION_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
            raise ValueError("missing/unsafe upgrade observation: " + name)
        raw = path.read_bytes()
        observations[name] = hashlib.sha256(raw).hexdigest()
        if name == "v240-version.txt":
            prior_text = raw.decode("utf-8")
    channels = re.findall(r"^Channel:\s*(\S+)\s*$", prior_text, re.M)
    if len(channels) != 1:
        raise ValueError("prior runtime must report exactly one channel")
    document = {
        "schema_version": 1,
        "kind": "upgrade_observation_manifest",
        "evidence_root": str(root),
        "prior_source_head": prior_source_head,
        "source_head": source_head,
        "prior_channel": channels[0],
        "baseline_release_qualified": False,
        "observations": observations,
    }
    # Re-read and hash-match through the same consumer. A changed file, empty
    # inventory, changed policy, wrong runtime, or unobserved reboot cannot pass.
    verify_evidence(document, require_prior_stable=False)
    document["observation_status"] = "VERIFIED"
    return document


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect"); c.add_argument("--root", default="/")
    c = sub.add_parser("compare"); c.add_argument("before"); c.add_argument("after")
    c = sub.add_parser("runtime"); c.add_argument("path"); c.add_argument("head"); c.add_argument("version")
    c = sub.add_parser("verify"); c.add_argument("path")
    c = sub.add_parser("manifest", help="package retained observations; does not qualify a release")
    c.add_argument("--evidence-root", required=True)
    c.add_argument("--prior-source-head", required=True)
    c.add_argument("--source-head", required=True)
    args = ap.parse_args()
    if args.command == "manifest":
        print(json.dumps(build_observation_manifest(args.evidence_root, args.prior_source_head, args.source_head), sort_keys=True))
        return 0
    if args.command == "verify":
        verify_evidence(json.loads(Path(args.path).read_text())); return 0
    if args.command == "collect":
        print(json.dumps(collect(args.root), sort_keys=True)); return 0
    if args.command == "runtime":
        verify_runtime(Path(args.path).read_text(), args.head, args.version); return 0
    result = compare(json.loads(Path(args.before).read_text()), json.loads(Path(args.after).read_text()))
    print(json.dumps(result, sort_keys=True))
    return 0 if all(result[k] == "PASS" for k in ("managed_hosts", "policy", "control_db")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
