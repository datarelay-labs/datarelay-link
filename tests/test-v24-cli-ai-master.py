#!/usr/bin/env python3
"""Focused public-CLI scenarios for DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_control_cli as cli
import drlink_v24 as v24
from drlink_v24_bundle import apply_v24_plan, parse_v24_bundle, prepare_v24_plan


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text("{\n  \"role\": \"server\"\n}\n", encoding="utf-8")


def _agent_root(tmp: str, hostname: str = "ubuntu-prod") -> None:
    Path(tmp, "etc/frp").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/frp/client-state.json").write_text(
        '{\n  "machine_id": "aabbccddeeff00112233445566778899",\n  "hostname": "%s",\n  "label": "%s"\n}\n'
        % (hostname, hostname),
        encoding="utf-8",
    )
    Path(tmp, "etc/frp/frpc.toml").write_text("[common]\n", encoding="utf-8")
    Path(tmp, "etc/frp/client-identity.key").write_text("x", encoding="utf-8")


class V24MasterScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-v24-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)

    def tearDown(self):
        self.plane.close()
        os.environ.pop("DRLINK_CONFIRM", None)

    def _run(self, *tokens):
        return cli.dispatch(list(tokens), root=self.tmp, plane=self.plane)

    def test_A_first_run_no_policy_allow(self):
        pol = v24.get_access_policy(self.plane, "remote")
        self.assertIsNone(pol["mode"])
        self.assertEqual(v24.effective_policy_result(None, "enabled", False), "ALLOW")
        out = self.plane.format_status()
        self.assertIn("Role: DRLink Server", out)
        self.assertIn("No access restrictions are currently configured", out)

    def test_B_C_blacklist_whitelist(self):
        v24.set_network_object(self.plane, "partner-office", type="ip", value="203.0.113.50", oneshot=True)
        v24.set_network_object(self.plane, "office-admin", type="ip", value="203.0.113.10", oneshot=True)
        # managed host object as destination
        self.plane.set_object_type("ubuntu-prod", "host")
        self.plane.set_object_value("ubuntu-prod", "198.51.100.10")
        v24.set_access_rule(
            self.plane,
            "remote",
            "block-partner-ssh",
            mode="blacklist",
            source="partner-office",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        ev = v24.evaluate_selector_policy(
            self.plane,
            "remote",
            source_name="partner-office",
            destination_name="ubuntu-prod",
            service_name="ssh",
        )
        self.assertEqual(ev["result"], "DENY")
        ev2 = v24.evaluate_selector_policy(
            self.plane,
            "remote",
            source_name="office-admin",
            destination_name="ubuntu-prod",
            service_name="ssh",
        )
        self.assertEqual(ev2["result"], "ALLOW")

        v24.reset_access_policy(self.plane, "remote", confirm=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            "office-ssh",
            mode="whitelist",
            source="office-admin",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        self.assertEqual(
            v24.evaluate_selector_policy(
                self.plane,
                "remote",
                source_name="office-admin",
                destination_name="ubuntu-prod",
                service_name="ssh",
            )["result"],
            "ALLOW",
        )
        self.assertEqual(
            v24.evaluate_selector_policy(
                self.plane,
                "remote",
                source_name="partner-office",
                destination_name="ubuntu-prod",
                service_name="ssh",
            )["result"],
            "DENY",
        )

    def test_D_E_F_last_rule_disable_reset(self):
        v24.set_network_object(self.plane, "partner-office", type="ip", value="203.0.113.50", oneshot=True)
        v24.set_network_object(self.plane, "ubuntu-prod", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            "block-partner-ssh",
            mode="blacklist",
            source="partner-office",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        v24.unset_access_rule(self.plane, "remote", "block-partner-ssh")
        pol = v24.get_access_policy(self.plane, "remote")
        self.assertEqual(pol["mode"], "blacklist")
        self.assertEqual(v24.effective_policy_result(pol["mode"], pol["enforcement"], False), "ALLOW")

        v24.set_access_rule(
            self.plane,
            "remote",
            "block-partner-ssh",
            source="partner-office",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        v24.set_policy_enforcement(self.plane, "remote", False, confirm=True)
        pol = v24.get_access_policy(self.plane, "remote")
        self.assertEqual(pol["enforcement"], "disabled")
        self.assertEqual(v24.effective_policy_result(pol["mode"], pol["enforcement"], True), "ALLOW")
        v24.set_policy_enforcement(self.plane, "remote", True, confirm=True)
        v24.reset_access_policy(self.plane, "remote", confirm=True)
        self.assertIsNone(v24.get_access_policy(self.plane, "remote")["mode"])

    def test_H_ai_oneshot_mode_required_and_conflict(self):
        v24.set_network_object(self.plane, "partner-office", type="ip", value="203.0.113.50", oneshot=True)
        v24.set_network_object(self.plane, "ubuntu-prod", type="ip", value="198.51.100.10", oneshot=True)
        with self.assertRaises(Exception) as ctx:
            v24.set_access_rule(
                self.plane,
                "remote",
                "r1",
                source="partner-office",
                destination="ubuntu-prod",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("mode", str(ctx.exception).lower())
        v24.set_access_rule(
            self.plane,
            "remote",
            "r1",
            mode="blacklist",
            source="partner-office",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        with self.assertRaises(Exception) as ctx2:
            v24.set_access_rule(
                self.plane,
                "remote",
                "r2",
                mode="whitelist",
                source="partner-office",
                destination="ubuntu-prod",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("BLACKLIST", str(ctx2.exception))
        self.assertIn("No changes were applied", str(ctx2.exception))

    def test_J_K_managed_host_internet_source_dest(self):
        # Create managed endpoint style object
        self.plane.set_object_type("github", "fqdn")
        self.plane.set_object_value("github", "github.com")
        # Simulate managed host object
        oid = None

        def write():
            nonlocal oid
            from drlink_control_db import utc_now_iso
            import secrets

            oid = "obj_%s" % secrets.token_hex(4)
            now = utc_now_iso()
            self.plane.conn.execute(
                "INSERT INTO objects(id, name, type, origin, description, status, row_version, created_at, updated_at) "
                "VALUES (?, 'ubuntu-prod', 'managed_endpoint', 'managed', '', 'active', 1, ?, ?)",
                (oid, now, now),
            )
            cid = "cli_%s" % secrets.token_hex(4)
            self.plane.conn.execute(
                "INSERT INTO clients(id, label, hostname, status, trust_status, connected, row_version, created_at, updated_at) "
                "VALUES (?, 'ubuntu-prod', 'ubuntu-prod', 'connected', 'trusted', 1, 1, ?, ?)",
                (cid, now, now),
            )
            self.plane.conn.execute(
                "INSERT INTO managed_endpoints(id, object_id, client_id) VALUES (?, ?, ?)",
                ("mep_%s" % secrets.token_hex(3), oid, cid),
            )
            return {"entity": {"type": "managed-host", "id": oid, "name": "ubuntu-prod"}, "operation": "create"}

        self.plane._mutate("seed managed host", "seed", write)
        rows = v24.list_network_objects(self.plane)
        types = {r["name"]: r["type"] for r in rows}
        self.assertEqual(types.get("ubuntu-prod"), "Managed Host")
        v24.set_access_rule(
            self.plane,
            "internet",
            "ubuntu-prod-github",
            mode="whitelist",
            source="ubuntu-prod",
            destination="github",
            service="https",
            enabled=True,
            oneshot=True,
        )
        with self.assertRaises(Exception) as ctx:
            v24.set_access_rule(
                self.plane,
                "internet",
                "bad",
                source="github",
                destination="ubuntu-prod",
                service="https",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("cannot be used as an Internet Access destination", str(ctx.exception))

    def test_W_udp_remote_service_reject(self):
        v24.set_service_object(self.plane, "dns-udp", type="udp", port=53, oneshot=True)
        # Agent context
        self.plane.close()
        cfg = Path(self.tmp, "etc/drlink/config.json")
        if cfg.exists():
            cfg.unlink()
        _agent_root(self.tmp)
        self.plane = ControlPlane(self.tmp)
        with self.assertRaises(Exception) as ctx:
            v24.set_remote_service_agent(
                self.plane,
                "dns-access",
                destination="this-host",
                service="dns-udp",
                enabled=True,
                oneshot=True,
                root=self.tmp,
            )
        self.assertIn("UDP", str(ctx.exception))

    def test_S_U_fixed_tcp_and_cross_pool(self):
        v24.set_service_object(self.plane, "legacy-db", type="fixed-tcp", port=1521, oneshot=True)
        sobj = v24.get_service_object(self.plane, "legacy-db")
        self.assertEqual(sobj["type"], "fixed-tcp")
        self.plane.close()
        cfg = Path(self.tmp, "etc/drlink/config.json")
        if cfg.exists():
            cfg.unlink()
        _agent_root(self.tmp, "branch-gateway")
        self.plane = ControlPlane(self.tmp)
        v24.set_service_object(self.plane, "legacy-db", type="fixed-tcp", port=1521, oneshot=True)
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        result = v24.set_remote_service_agent(
            self.plane,
            "legacy-db-access",
            destination="10.0.0.5",
            service="legacy-db",
            enabled=True,
            oneshot=True,
            root=self.tmp,
        )
        self.assertEqual(result["view"]["status"] in ("HEALTHY", "DEGRADED"), True)
        port = result["view"]["endpoint_port"]
        if port is not None:
            self.assertGreaterEqual(port, 6200)
            self.assertLessEqual(port, 6299)
        with self.assertRaises(Exception) as ctx:
            v24.set_remote_service_agent(
                self.plane,
                "legacy-db-access",
                service="ssh",
                oneshot=False,
                enabled=True,
                root=self.tmp,
            )
        # existing forces oneshot path with destination preserved — use explicit edit attempt
        existing = self.plane.conn.execute(
            "SELECT * FROM agent_remote_services WHERE name = ?", ("legacy-db-access",)
        ).fetchone()
        self.assertEqual(existing["pool_class"], "fixed-tcp")
        with self.assertRaises(Exception) as ctx2:
            v24.set_remote_service_agent(
                self.plane,
                "legacy-db-access",
                destination=existing["destination"],
                service="ssh",
                enabled=True,
                oneshot=True,
                root=self.tmp,
            )
        self.assertIn("Fixed TCP", str(ctx2.exception))

    def test_X_reference_safe_delete(self):
        v24.set_network_object(self.plane, "partner-office", type="ip", value="203.0.113.50", oneshot=True)
        v24.set_network_object(self.plane, "ubuntu-prod", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_access_rule(
            self.plane,
            "remote",
            "block-partner-ssh",
            mode="blacklist",
            source="partner-office",
            destination="ubuntu-prod",
            service="ssh",
            enabled=True,
            oneshot=True,
        )
        with self.assertRaises(Exception) as ctx:
            v24.unset_network_object(self.plane, "partner-office")
        self.assertIn("still referenced", str(ctx.exception))

    def test_AE_missing_dependency(self):
        with self.assertRaises(Exception) as ctx:
            v24.set_access_rule(
                self.plane,
                "remote",
                "block-admin",
                mode="blacklist",
                source="office-admin",
                destination="ubuntu-prod",
                service="ssh",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("does not exist", str(ctx.exception))
        self.assertIn("ConfigurationBundle", str(ctx.exception))

    def test_AF_AH_AI_AL_server_bundle(self):
        raw = """
configurationBundle:
  context: server
  networkObjects:
    - name: office-network
      type: cidr
      value: 203.0.113.0/24
    - name: github
      type: fqdn
      value: github.com
  serviceObjects:
    - name: https
      type: tcp
      port: 443
  internetAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: github-https
        source: office-network
        destination: github
        service: https
        enabled: true
"""
        # Force server role
        plan = prepare_v24_plan(self.plane, raw, role="server")
        self.assertFalse(plan.no_change)
        apply_v24_plan(self.plane, plan, confirm=True)
        self.assertIsNotNone(self.plane.get_object("office-network"))
        self.assertIsNotNone(v24.get_service_object(self.plane, "https"))
        pol = v24.get_access_policy(self.plane, "internet")
        self.assertEqual(pol["mode"], "whitelist")
        # reapply NO CHANGE
        plan2 = prepare_v24_plan(self.plane, raw, role="server")
        self.assertTrue(plan2.no_change)
        # context mismatch
        with self.assertRaises(Exception) as ctx:
            prepare_v24_plan(self.plane, raw.replace("context: server", "context: agent"), role="server")
        self.assertIn("No changes were applied", str(ctx.exception))
        self.assertTrue(
            "agent" in str(ctx.exception).lower() and "server" in str(ctx.exception).lower()
        )
        # order independence: rule before objects still works via whole-doc resolve on apply
        raw2 = """
configurationBundle:
  context: server
  internetAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: block-x
        source: office-network
        destination: github
        service: https
        enabled: true
"""
        # conflicting mode should fail before mutation of internetAccess — reset first
        v24.reset_access_policy(self.plane, "internet", confirm=True)
        plan3 = prepare_v24_plan(self.plane, raw2, role="server")
        apply_v24_plan(self.plane, plan3, confirm=True)
        self.assertEqual(v24.get_access_policy(self.plane, "internet")["mode"], "blacklist")

    def test_AN_dependency_parity_validates_group_members_before_apply(self):
        rev_before = self.plane.current_revision()
        bad_bundles = (
            (
                "Network Object",
                """configurationBundle:
  context: server
  networkGroups:
    - name: admins
      members: [missing-network]
""",
            ),
            (
                "Service Object",
                """configurationBundle:
  context: server
  serviceGroups:
    - name: admin-services
      members: [missing-service]
""",
            ),
            (
                "Permission Object",
                """configurationBundle:
  context: server
  permissionGroups:
    - name: operators
      members: [missing-permission]
""",
            ),
        )
        for label, raw in bad_bundles:
            with self.subTest(label=label):
                with self.assertRaises(Exception) as ctx:
                    prepare_v24_plan(self.plane, raw, role="server")
                self.assertIn(label, str(ctx.exception))
                self.assertIn("does not exist", str(ctx.exception))
                self.assertEqual(self.plane.current_revision(), rev_before)

        good = """configurationBundle:
  context: server
  networkObjects:
    - name: admin-net
      type: ip
      value: 198.51.100.10
  networkGroups:
    - name: admins
      members: [admin-net]
  serviceObjects:
    - name: ssh-alt
      type: tcp
      port: 2222
  serviceGroups:
    - name: admin-services
      members: [ssh-alt]
  permissionObjects:
    - name: read-basic
      permissions: [host-info]
  permissionGroups:
    - name: readers
      members: [read-basic]
"""
        rev_before_good = self.plane.current_revision()
        audit_before_good = int(
            self.plane.conn.execute("SELECT COUNT(*) AS c FROM audit_events").fetchone()["c"]
        )
        plan = prepare_v24_plan(self.plane, good, role="server")
        self.assertFalse(plan.no_change)
        # Dry-run applyability validation must leave no authoritative residue.
        self.assertEqual(self.plane.current_revision(), rev_before_good)
        self.assertEqual(
            int(self.plane.conn.execute("SELECT COUNT(*) AS c FROM audit_events").fetchone()["c"]),
            audit_before_good,
        )
        self.assertIsNone(self.plane.get_object("admin-net"))
        self.assertIsNone(self.plane.get_object_group("admins"))
        self.assertIsNone(v24.get_service_object(self.plane, "ssh-alt"))
        self.assertIsNone(v24.get_permission_object(self.plane, "read-basic"))

        result = apply_v24_plan(self.plane, plan, confirm=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertIsNotNone(self.plane.get_object_group("admins"))
        self.assertIsNotNone(v24.get_service_group(self.plane, "admin-services"))
        self.assertIsNotNone(v24.get_permission_group(self.plane, "readers"))

    def test_AO_post_bundle_catalog_rejects_rule_reference_to_deleted_dependency(self):
        v24.set_network_object(
            self.plane, "src", type="ip", value="198.51.100.20", oneshot=True
        )
        v24.set_network_object(
            self.plane, "dst", type="ip", value="198.51.100.21", oneshot=True
        )
        v24.set_service_object(self.plane, "ssh-alt", type="tcp", port=2222, oneshot=True)
        rev_before = self.plane.current_revision()
        raw = """configurationBundle:
  context: server
  serviceObjects:
    - name: ssh-alt
      state: absent
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: block-alt
        source: src
        destination: dst
        service: ssh-alt
        enabled: true
"""
        with self.assertRaises(Exception) as ctx:
            prepare_v24_plan(self.plane, raw, role="server")
        self.assertIn("Required Service Object 'ssh-alt' does not exist", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev_before)
        self.assertIsNotNone(v24.get_service_object(self.plane, "ssh-alt"))

    def test_AP_deleted_network_dependency_rejected_before_test_diff_apply(self):
        v24.set_network_object(
            self.plane, "src-p0d", type="ip", value="198.51.100.31", oneshot=True
        )
        v24.set_network_object(
            self.plane, "dst-p0d", type="ip", value="198.51.100.32", oneshot=True
        )
        v24.set_service_object(self.plane, "ssh-p0d", type="tcp", port=2223, oneshot=True)
        rev_before = self.plane.current_revision()
        raw = """configurationBundle:
  context: server
  networkObjects:
    - name: dst-p0d
      state: absent
  remoteAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: allow-p0d
        source: src-p0d
        destination: dst-p0d
        service: ssh-p0d
        enabled: true
"""
        path = Path(self.tmp, "p0d-dependency.yaml")
        path.write_text(raw, encoding="utf-8")
        for tokens in (
            ("test", "configuration", str(path)),
            ("system", "diff", "configuration", str(path)),
        ):
            with self.subTest(tokens=tokens):
                with self.assertRaises(SystemExit) as ctx:
                    self._run(*tokens)
                self.assertIn("Required Network Object 'dst-p0d' does not exist", str(ctx.exception))
                self.assertEqual(self.plane.current_revision(), rev_before)
                self.assertIsNotNone(self.plane.get_object("dst-p0d"))

    def test_AQ_internal_network_storage_types_rejected_by_bundle_validator(self):
        rev_before = self.plane.current_revision()
        for token, value in (
            ("host", "198.51.100.40"),
            ("network", "198.51.100.0/24"),
        ):
            with self.subTest(type=token):
                raw = """configurationBundle:
  context: server
  networkObjects:
    - name: internal-alias-%s
      type: %s
      value: %s
""" % (token, token, value)
                with self.assertRaises(Exception) as ctx:
                    prepare_v24_plan(self.plane, raw, role="server")
                self.assertIn("Accepted: ip, cidr, fqdn", str(ctx.exception))
                self.assertEqual(self.plane.current_revision(), rev_before)
                self.assertIsNone(self.plane.get_object("internal-alias-%s" % token))

    def test_AP_public_test_and_apply_reject_same_live_dependency(self):
        v24.set_network_object(
            self.plane, "src-parity", type="ip", value="198.51.100.31", oneshot=True
        )
        v24.set_network_object(
            self.plane, "dst-parity", type="ip", value="198.51.100.32", oneshot=True
        )
        v24.set_service_object(
            self.plane, "svc-parity", type="tcp", port=2233, oneshot=True
        )
        v24.set_access_rule(
            self.plane,
            "remote",
            "rule-parity",
            mode="blacklist",
            source="src-parity",
            destination="dst-parity",
            service="svc-parity",
            enabled=True,
            oneshot=True,
        )
        rev_before = self.plane.current_revision()
        bundle = Path(self.tmp, "dependency-parity.yaml")
        bundle.write_text(
            """configurationBundle:
  context: server
  serviceObjects:
    - name: svc-parity
      state: absent
""",
            encoding="utf-8",
        )

        messages = []
        for args in (
            ("test", "configuration", str(bundle)),
            ("system", "apply", "configuration", str(bundle)),
        ):
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as ctx:
                    self._run(*args)
                msg = str(ctx.exception)
                self.assertIn("still referenced", msg.lower())
                self.assertIn("rule-parity", msg)
                self.assertIn("No changes were applied", msg)
                messages.append(msg)
                self.assertEqual(self.plane.current_revision(), rev_before)
                self.assertIsNotNone(v24.get_service_object(self.plane, "svc-parity"))
                self.assertIsNotNone(self.plane._get_rule("remote", "rule-parity"))

        self.assertEqual(messages[0], messages[1])

    def test_AP_public_test_diff_reject_unapplyable_bundle_and_internal_types(self):
        v24.set_network_object(
            self.plane, "src", type="ip", value="198.51.100.30", oneshot=True
        )
        v24.set_network_object(
            self.plane, "dst", type="ip", value="198.51.100.31", oneshot=True
        )
        v24.set_service_object(
            self.plane, "ssh-parity", type="tcp", port=2223, oneshot=True
        )
        rev_before = self.plane.current_revision()

        dependency_bad = """configurationBundle:
  context: server
  serviceObjects:
    - name: ssh-parity
      state: absent
  remoteAccess:
    mode: blacklist
    enforcement: enabled
    rules:
      - name: block-parity
        source: src
        destination: dst
        service: ssh-parity
        enabled: true
"""
        dep_path = Path(self.tmp, "dependency-bad.yaml")
        dep_path.write_text(dependency_bad, encoding="utf-8")

        for tokens in (
            ("test", "configuration", str(dep_path)),
            ("system", "diff", "configuration", str(dep_path)),
        ):
            with self.subTest(tokens=tokens):
                with self.assertRaises(SystemExit) as ctx:
                    cli.dispatch(list(tokens), root=self.tmp, plane=self.plane)
                self.assertIn(
                    "Required Service Object 'ssh-parity' does not exist",
                    str(ctx.exception),
                )
                self.assertEqual(self.plane.current_revision(), rev_before)
                self.assertIsNotNone(v24.get_service_object(self.plane, "ssh-parity"))

        for internal_type in ("host", "network"):
            with self.subTest(internal_type=internal_type):
                type_bad = """configurationBundle:
  context: server
  networkObjects:
    - name: internal-type
      type: %s
      value: 198.51.100.40
""" % internal_type
                type_path = Path(self.tmp, "type-%s.yaml" % internal_type)
                type_path.write_text(type_bad, encoding="utf-8")
                for tokens in (
                    ("test", "configuration", str(type_path)),
                    ("system", "diff", "configuration", str(type_path)),
                ):
                    with self.assertRaises(SystemExit) as ctx:
                        cli.dispatch(list(tokens), root=self.tmp, plane=self.plane)
                    self.assertIn("Accepted: ip, cidr, fqdn", str(ctx.exception))
                    self.assertEqual(self.plane.current_revision(), rev_before)
                    self.assertIsNone(self.plane.get_object("internal-type"))

    def test_AO_malformed_markdown_reject(self):
        bad = "```yaml\nconfigurationBundle:\n  context: server\n```\n"
        with self.assertRaises(Exception) as ctx:
            parse_v24_bundle(bad)
        self.assertIn("not valid ConfigurationBundle YAML", str(ctx.exception))

    def test_AS_AT_role_errors(self):
        # Server rejects remote-service
        import io
        from contextlib import redirect_stderr

        err = io.StringIO()
        with redirect_stderr(err):
            rc = cli.dispatch(["set", "remote-service", "ssh-access"], root=self.tmp, plane=self.plane)
        self.assertNotEqual(rc, 0)
        self.assertIn("Agent Host", err.getvalue())
        # Agent rejects internet-access
        self.plane.close()
        # Role markers must be exclusive for this host.
        cfg = Path(self.tmp, "etc/drlink/config.json")
        if cfg.exists():
            cfg.unlink()
        _agent_root(self.tmp)
        self.plane = ControlPlane(self.tmp)
        err2 = io.StringIO()
        with redirect_stderr(err2):
            rc2 = cli.dispatch(
                [
                    "set",
                    "internet-access",
                    "r1",
                    "mode",
                    "whitelist",
                    "source",
                    "a",
                    "destination",
                    "b",
                    "service",
                    "https",
                    "enabled",
                ],
                root=self.tmp,
                plane=self.plane,
            )
        self.assertNotEqual(rc2, 0)
        self.assertIn("DRLink Server", err2.getvalue())

    def test_Z_AA_ai_access_policy(self):
        self.plane.set_ai_principal("claude", enabled=True)
        self.plane.conn.execute(
            "UPDATE ai_principals SET credential_status = 'verified' WHERE name = 'claude'"
        )
        v24.set_network_object(self.plane, "ubuntu-prod", type="ip", value="198.51.100.10", oneshot=True)
        v24.set_permission_object(
            self.plane, "read-only", permissions=["host-info", "process-read", "file-read"], oneshot=True
        )
        v24.set_ai_access_rule(
            self.plane,
            "claude-prod",
            mode="whitelist",
            source="claude",
            destination="ubuntu-prod",
            permission="read-only",
            enabled=True,
            oneshot=True,
        )
        ev = v24.evaluate_ai_access_v24(
            self.plane, identity="claude", destination="ubuntu-prod", permission="read-only"
        )
        self.assertEqual(ev["result"], "ALLOW")
        ev2 = v24.evaluate_ai_access_v24(
            self.plane, identity="claude", destination="ubuntu-prod", permission="command-exec"
        )
        self.assertEqual(ev2["result"], "DENY")
        v24.set_policy_enforcement(self.plane, "ai", False, confirm=True)
        ev3 = v24.evaluate_ai_access_v24(
            self.plane, identity="claude", destination="ubuntu-prod", permission="command-exec"
        )
        self.assertEqual(ev3["result"], "ALLOW")
        self.assertEqual(ev3["auth"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
