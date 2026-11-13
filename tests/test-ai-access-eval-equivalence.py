#!/usr/bin/env python3
"""AUD-21 2g: AI Access evaluation does fewer database reads and decides identically.

``evaluate_ai_access_v24`` runs on every MCP tools/call and used to look up the
destination of every enabled rule with its own query. It now resolves the
destinations of the caller's rules in a batch inside the same call. Nothing is
cached between calls, so every call still evaluates the current database.

* The decision (mode, enforcement, matched rules, result, auth) must equal the
  previous implementation, kept below verbatim as the reference, for every
  identity / destination / permission combination of a mixed rule set
  (objects, nested groups, permission objects and groups, disabled rules,
  other identities, the reserved Server target, mixed-case names).
* The number of statements must not grow with the number of rules.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane  # noqa: E402
import drlink_v24 as v24  # noqa: E402


def _reference_ref_name_match(plane_db, ref_kind, ref_id, name):
    if ref_kind == "server":
        return ref_id == v24.SERVER_SELF_REF_ID and name == v24.SERVER_SELF_TARGET
    if ref_kind == "object":
        obj = plane_db.conn.execute("SELECT name FROM objects WHERE id = ?", (ref_id,)).fetchone()
        return bool(obj and obj["name"].lower() == name.lower())
    grp = plane_db.conn.execute("SELECT name FROM object_groups WHERE id = ?", (ref_id,)).fetchone()
    if grp and grp["name"].lower() == name.lower():
        return True
    members = plane_db._expand_group_members(ref_id, set())
    return any(m["name"].lower() == name.lower() for m in members)


def _reference_evaluate(plane_db, *, identity, destination, permission):
    """The implementation before AUD-21 2g (per-rule destination queries)."""
    pol = v24.get_access_policy(plane_db, "ai")
    principal = plane_db.get_principal(identity)
    if not principal:
        return {"mode": pol["mode"], "enforcement": pol["enforcement"], "matched_rules": [],
                "result": "DENY", "plane": "ai", "auth": "UNAUTHENTICATED"}
    status = str(principal["credential_status"] or "").lower()
    auth_ok = status in ("verified", "active") and bool(principal["enabled"])
    if not auth_ok:
        return {"mode": pol["mode"], "enforcement": pol["enforcement"], "matched_rules": [],
                "result": "DENY", "plane": "ai", "auth": "UNAUTHENTICATED"}
    wanted_perms = (
        v24.expand_permissions(plane_db, permission)
        if v24.get_permission_object(plane_db, permission) or v24.get_permission_group(plane_db, permission)
        else {permission}
    )
    matched = []
    for row in plane_db.conn.execute("SELECT * FROM ai_policy_rules WHERE enabled = 1 ORDER BY name"):
        if row["source_identity_id"] != principal["id"]:
            continue
        if destination == v24.SERVER_SELF_TARGET:
            if row["destination_ref_kind"] != "server" or row["destination_ref_id"] != v24.SERVER_SELF_REF_ID:
                continue
        else:
            if row["destination_ref_kind"] == "server" or not _reference_ref_name_match(
                plane_db, row["destination_ref_kind"], row["destination_ref_id"], destination
            ):
                continue
        if row["permission_ref_kind"] == "permission_object":
            perms = {
                r["permission"]
                for r in plane_db.conn.execute(
                    "SELECT permission FROM permission_object_members WHERE permission_object_id = ?",
                    (row["permission_ref_id"],),
                )
            }
        else:
            perms = set()
            for mid in plane_db.conn.execute(
                "SELECT permission_object_id FROM permission_group_members WHERE group_id = ?",
                (row["permission_ref_id"],),
            ):
                for r in plane_db.conn.execute(
                    "SELECT permission FROM permission_object_members WHERE permission_object_id = ?",
                    (mid["permission_object_id"],),
                ):
                    perms.add(r["permission"])
        if wanted_perms & perms or permission.lower() in {p.lower() for p in perms}:
            matched.append(row["name"])
    result = v24.effective_policy_result(pol["mode"], pol["enforcement"], bool(matched), plane="ai")
    return {"mode": pol["mode"], "enforcement": pol["enforcement"], "matched_rules": matched,
            "result": result, "plane": "ai", "auth": "VERIFIED"}


def _verify(plane, name):
    plane.conn.execute(
        "UPDATE ai_principals SET credential_status = 'verified', enabled = 1 WHERE name = ?", (name,)
    )
    plane.conn.commit()


class AiAccessEvaluationEquivalence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-ai-eval-")
        Path(self.tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
        Path(self.tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)
        p = self.plane
        for who in ("bot", "other", "off"):
            p.set_ai_principal(who, enabled=True)
        for who in ("bot", "other", "off"):
            _verify(p, who)
        for i in range(1, 13):
            v24.set_network_object(p, "n%02d" % i, type="ip", value="198.51.100.%d" % i, oneshot=True)
        v24.set_network_object(p, "MixedCase", type="ip", value="198.51.100.200", oneshot=True)
        v24.set_network_group(p, "g-inner", members=["n01", "n02"], oneshot=True)
        v24.set_network_group(p, "g-outer", members=["n03"], oneshot=True)
        # The public API only takes Network Objects; nesting exists in imported/legacy
        # data, which the evaluation must still follow, so add it directly.
        inner_id = p.conn.execute("SELECT id FROM object_groups WHERE name = 'g-inner'").fetchone()["id"]
        outer_id = p.conn.execute("SELECT id FROM object_groups WHERE name = 'g-outer'").fetchone()["id"]
        p.conn.execute(
            "INSERT INTO object_group_members(group_id, member_kind, member_id) VALUES (?, 'group', ?)",
            (outer_id, inner_id),
        )
        p.conn.commit()
        v24.set_network_group(p, "g-solo", members=["n04"], oneshot=True)
        v24.set_permission_object(p, "p-exec", permissions=["command-exec"], oneshot=True)
        v24.set_permission_object(p, "p-read", permissions=["host-info", "process-read"], oneshot=True)
        v24.set_permission_group(p, "p-ops", members=["p-exec", "p-read"], oneshot=True)
        v24.set_permission_group(p, "p-readonly", members=["p-read"], oneshot=True)
        rules = []
        for i in range(1, 13):  # one rule per object, alternating permission kinds
            rules.append(("r-obj-%02d" % i, "bot", "n%02d" % i, "p-exec" if i % 2 else "p-ops", True))
        rules += [
            ("r-grp-outer", "bot", "g-outer", "p-read", True),
            ("r-grp-solo", "bot", "g-solo", "p-readonly", True),
            ("r-mixed", "bot", "MixedCase", "p-exec", True),
            ("r-disabled", "bot", "n05", "p-ops", False),
            ("r-other-1", "other", "n06", "p-exec", True),
            ("r-other-2", "other", "g-outer", "p-ops", True),
            ("r-off", "off", "n07", "p-exec", True),
        ]
        for name, src, dst, perm, enabled in rules:
            v24.set_ai_access_rule(p, name, mode="whitelist", source=src, destination=dst,
                                   permission=perm, enabled=enabled, oneshot=True)
        # A rule can only be created for a verified identity; "off" loses it afterwards:
        # authentication is necessary but never sufficient, and the rule must not apply.
        p.conn.execute("UPDATE ai_principals SET credential_status = 'pending' WHERE name = 'off'")
        p.conn.commit()

    def tearDown(self):
        self.plane.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _triples(self):
        identities = ["bot", "other", "off", "ghost"]
        destinations = (
            ["n%02d" % i for i in range(1, 13)]
            + ["N03", "mixedcase", "MIXEDCASE", "MixedCase", "g-inner", "g-outer", "G-SOLO", "g-solo",
               "nope", "", v24.SERVER_SELF_TARGET]
        )
        permissions = ["command-exec", "host-info", "process-read", "p-exec", "p-read", "p-ops",
                       "p-readonly", "COMMAND-EXEC", "file-read", "nonexistent"]
        return [(i, d, p) for i in identities for d in destinations for p in permissions]

    def test_decision_equals_reference_for_every_combination(self):
        checked = 0
        for identity, destination, permission in self._triples():
            want = _reference_evaluate(self.plane, identity=identity, destination=destination, permission=permission)
            got = v24.evaluate_ai_access_v24(
                self.plane, identity=identity, destination=destination, permission=permission
            )
            self.assertEqual(got, want, (identity, destination, permission))
            checked += 1
        self.assertGreater(checked, 800)
        # The set is not trivially all-DENY: some combinations are allowed.
        allowed = [
            1 for i, d, p in self._triples()
            if v24.evaluate_ai_access_v24(self.plane, identity=i, destination=d, permission=p)["result"] == "ALLOW"
        ]
        self.assertGreater(len(allowed), 20)

    def test_server_self_target_never_matches_a_user_object(self):
        got = v24.evaluate_ai_access_v24(
            self.plane, identity="bot", destination=v24.SERVER_SELF_TARGET, permission="command-exec"
        )
        want = _reference_evaluate(
            self.plane, identity="bot", destination=v24.SERVER_SELF_TARGET, permission="command-exec"
        )
        self.assertEqual(got, want)
        self.assertEqual(got["matched_rules"], [])

    def _count_statements(self, **kwargs):
        seen = []
        self.plane.conn.set_trace_callback(lambda sql: seen.append(sql))
        try:
            v24.evaluate_ai_access_v24(self.plane, **kwargs)
        finally:
            self.plane.conn.set_trace_callback(None)
        return len(seen)

    def test_statement_count_does_not_grow_with_the_number_of_rules(self):
        kwargs = dict(identity="bot", destination="n01", permission="command-exec")
        before = self._count_statements(**kwargs)
        for i in range(40):  # 40 more rules for the same caller
            v24.set_network_object(self.plane, "extra%02d" % i, type="ip", value="203.0.113.%d" % (i + 1), oneshot=True)
            v24.set_ai_access_rule(
                self.plane, "r-extra-%02d" % i, mode="whitelist", source="bot",
                destination="extra%02d" % i, permission="p-exec", enabled=True, oneshot=True,
            )
        after = self._count_statements(**kwargs)
        self.assertLessEqual(after, before + 4, "statements grew from %d to %d with 40 more rules" % (before, after))
        self.assertLessEqual(after, 30, "evaluation issued %d statements" % after)


if __name__ == "__main__":
    unittest.main()
