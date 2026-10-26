#!/usr/bin/env python3
"""Public Internet Access diagnostics and linked operator-guide regressions."""
import os
import json
from pathlib import Path
import re
import shlex
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "lib"))
import frp_doctor as doctor
import frp_ctl_grammar as grammar
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24


class InternetDestinationGroupGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="drlink-destination-guidance-")
        root = Path(self.tmp.name)
        (root / "etc/drlink").mkdir(parents=True)
        (root / "etc/drlink/config.json").write_text('{"role":"server"}\n')
        self.env = patch.dict(os.environ, {"FRP_DEPLOY_TEST_ROOT": self.tmp.name,
                                           "FRP_SKIP_SYSTEMD": "1", "DRLINK_CONFIRM": "yes"})
        self.env.start()
        self.plane = ControlPlane(self.tmp.name)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_network_object(self.plane, "office", type="ip", value="10.20.30.40", oneshot=True)
        v24.set_service_object(self.plane, "web", type="tcp", port=443, oneshot=True)

    def tearDown(self):
        self.plane.close()
        self.env.stop()
        self.tmp.cleanup()

    def _rejected(self, destination):
        before = "\n".join(self.plane.conn.iterdump())
        with self.assertRaises(ControlPlaneError) as caught:
            v24.set_access_rule(self.plane, "internet", "blocked", mode="whitelist",
                                source="office", destination=destination, service="web",
                                enabled=False, oneshot=True)
        self.assertEqual(before, "\n".join(self.plane.conn.iterdump()))
        return str(caught.exception)

    def test_nonpublic_ip_group_names_actual_kind_and_preserves_denial(self):
        for index, address in enumerate(("10.20.30.41", "192.0.2.41", "fd00::41")):
            with self.subTest(address=address):
                name = "ip-%d" % index
                v24.set_network_object(self.plane, name, type="ip", value=address, oneshot=True)
                v24.set_network_group(self.plane, "group-" + name, members=[name], oneshot=True)
                text = self._rejected("group-" + name)
                self.assertIn("non-public IP Network Object '%s'" % name, text)
                self.assertNotIn("contains Managed Host", text)
                self.assertIn("public IP", text)

    def test_nonpublic_cidr_group_names_actual_leaf_and_preserves_denial(self):
        for index, address in enumerate(("10.0.0.0/8", "192.0.2.0/24", "fd00::/64")):
            with self.subTest(address=address):
                name = "cidr-%d" % index
                v24.set_network_object(self.plane, name, type="cidr", value=address, oneshot=True)
                v24.set_network_group(self.plane, "group-" + name, members=[name], oneshot=True)
                text = self._rejected("group-" + name)
                self.assertIn("non-public CIDR Network Object '%s'" % name, text)
                self.assertIn("group-" + name, text)
                self.assertNotIn("contains Managed Host", text)

    def test_real_managed_host_group_remains_explicitly_rejected(self):
        self.plane.upsert_client("managed-client", label="managed", hostname="managed",
                                 addresses=[{"address": "8.8.8.8", "active": True}])
        v24.set_network_group(self.plane, "managed-group", members=["managed"], oneshot=True)
        text = self._rejected("managed-group")
        self.assertIn("contains Managed Host 'managed'", text)

    def test_public_ip_and_cidr_groups_remain_valid_destinations(self):
        for index, (kind, address) in enumerate((("ip", "8.8.8.8"), ("cidr", "8.8.8.0/24"))):
            name = "public-%d" % index
            v24.set_network_object(self.plane, name, type=kind, value=address, oneshot=True)
            v24.set_network_group(self.plane, "group-" + name, members=[name], oneshot=True)
            v24.set_access_rule(self.plane, "internet", "allowed-%d" % index,
                                mode="whitelist", source="office", destination="group-" + name,
                                service="web", enabled=False, oneshot=True)
            self.assertIsNotNone(self.plane._get_rule("internet", "allowed-%d" % index))


class InternetAccessRecoveryGuidanceTests(unittest.TestCase):
    def _diagnose(self, config):
        with tempfile.TemporaryDirectory(prefix="drlink-listener-guidance-") as tmp:
            root = Path(tmp)
            legacy = root / "var/lib/drlink/egress-control.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"schema_version":1,"egress_profiles":{},"tcp_relays":{}}\n')
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            env = {
                "FRP_DEPLOY_TEST_ROOT": tmp,
                "FRP_SKIP_SYSTEMD": "1",
                "FRP_EGRESS_LISTEN_ADDR": "",
                "FRP_EGRESS_LISTEN_PORT": "",
            }
            report = doctor.Report()
            with patch.dict(os.environ, env):
                doctor.check_egress_control(report, doctor.Paths(tmp), {}, config)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(before, after, "diagnostic recovery must not change fixture state")
            return report

    def _assert_supported_recovery(self, report, check_id):
        issue = next(c for c in report.checks if c["id"] == check_id and c["status"] in (doctor.WARN, doctor.FAIL))
        self.assertIn(issue["status"], (doctor.WARN, doctor.FAIL))
        text = doctor.render_human(report)
        for phrase in (
            "Internet Access listener", "installer-owned", "same immutable",
            "FRP_EGRESS_LISTEN_ADDR", "FRP_EGRESS_LISTEN_PORT",
            "deployment mode", "Server identity",
            "docs/INSTALLATION.md#internet-access-listener-recovery",
            "show internet-access", "system diagnostics",
        ):
            self.assertIn(phrase, text)
        self.assertNotIn("fix egress_listen_addr", text)
        self.assertNotIn("prefer an internal/trusted egress_listen_addr", text)
        return issue

    def test_wildcard_bind_warning_has_supported_installer_recovery(self):
        report = self._diagnose({"egress_listen_addr": "0.0.0.0", "egress_listen_port": 6102})
        issue = self._assert_supported_recovery(report, "EGRESS_LISTEN_BIND")
        self.assertEqual(issue["status"], doctor.WARN)

    def test_invalid_listener_port_has_supported_recovery(self):
        report = self._diagnose({"egress_listen_addr": "192.0.2.10", "egress_listen_port": 70000})
        issue = self._assert_supported_recovery(report, "EGRESS_CONFIG_ERROR")
        self.assertEqual(issue["status"], doctor.FAIL)

    def test_service_port_collision_has_supported_recovery(self):
        report = self._diagnose({
            "egress_listen_addr": "192.0.2.10", "egress_listen_port": 6005,
            "port_start": 6000, "port_end": 6098,
        })
        issue = self._assert_supported_recovery(report, "EGRESS_PORT_COLLISION")
        self.assertEqual(issue["status"], doctor.FAIL)

    def test_linked_guide_policy_examples_and_listener_recovery_are_current(self):
        guide = (ROOT / "docs/CONTROLLED_EGRESS.md").read_text()
        lifecycle = guide.split("## 19.", 1)[1].split("## 23.", 1)[0]
        self.assertIn("union of enabled Rule matches", lifecycle)
        self.assertIn("WHITELIST", lifecycle)
        self.assertIn("material narrowing", lifecycle)
        for obsolete in ("disabled at the bottom", "moving a rule", "## 21. Shadowing", "→ DENY", "→ ALLOW"):
            self.assertNotIn(obsolete, lifecycle)
        examples = re.findall(r"^test internet-access .+$", guide, re.MULTILINE)
        self.assertTrue(examples)
        for example in examples:
            result = grammar.match(shlex.split(example), role="server")
            self.assertEqual(result.get("status"), "ok", (example, result))
            self.assertIn(" source ", example)
            self.assertIn(" destination ", example)
            self.assertIn(" service ", example)
        installation = (ROOT / "docs/INSTALLATION.md").read_text()
        self.assertIn("### Internet Access listener recovery", installation)
        for phrase in ("same immutable", "FRP_EGRESS_LISTEN_ADDR", "FRP_EGRESS_LISTEN_PORT", "Do not edit `config.json`", "current `direct` or `single443`", "omitted"):
            self.assertIn(phrase, installation)
        troubleshooting = (ROOT / "docs/TROUBLESHOOTING.md").read_text()
        self.assertIn("INSTALLATION.md#internet-access-listener-recovery", troubleshooting)
        for command in ("show ai-access <RULE>", "show permission-group <GROUP>", "set ai-access <RULE> permission <REPLACEMENT>", "set permission-group <GROUP> members <RETAINED_MEMBERS>"):
            self.assertIn(command, troubleshooting)

    def test_documented_installer_override_persists_bind_and_retains_mode_identity_port(self):
        with tempfile.TemporaryDirectory(prefix="drlink-listener-reconfigure-") as tmp:
            root = Path(tmp)
            config = root / "etc/drlink/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({
                "public_host": "203.0.113.10", "public_ip": "203.0.113.10",
                "public_url_host": "203.0.113.10", "deployment_mode": "direct",
                "egress_listen_addr": "0.0.0.0", "egress_listen_port": 6108,
                "port_start": 6000, "port_end": 6098,
            }))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
            env.update({
                "FRP_SERVER_SOURCED": "1", "FRP_SERVER_TEST_ROOT": tmp,
                "FRP_SERVER_CONFIG": str(config), "FRP_SKIP_SYSTEMD": "1",
                "FRP_EGRESS_LISTEN_ADDR": "192.0.2.10",
            })
            # Invoke only the real isolated resolution/write helpers, never install.
            script = 'source "$1/install-server.sh"; load_existing_server_config; resolve_server_settings; write_server_config'
            # Desktop/SSH runners may have a controlling /dev/tty even when
            # stdout/stderr are captured. The fixture exercises a noninteractive
            # installer config resolution, so detach only this child session;
            # otherwise resolve_server_settings prompts on the runner TTY.
            proc = subprocess.run(
                ["bash", "-euo", "pipefail", "-c", script, "listener-fixture", str(ROOT)],
                env=env, stdin=subprocess.DEVNULL, start_new_session=True,
                capture_output=True, text=True, timeout=20,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            observed = json.loads(config.read_text())
            self.assertEqual(observed["egress_listen_addr"], "192.0.2.10")
            self.assertEqual(observed["egress_listen_port"], 6108)
            self.assertEqual(observed["deployment_mode"], "direct")
            self.assertEqual(observed["public_ip"], "203.0.113.10")
            self.assertEqual(observed["public_url_host"], "203.0.113.10")


if __name__ == "__main__":
    unittest.main()
