#!/usr/bin/env python3
"""Invalid retained configuration must give a supported recovery procedure."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "lib"))
import frp_doctor as doctor
import frp_enrollment_lifecycle as lifecycle


class RetentionRecoveryTests(unittest.TestCase):
    def test_public_diagnostics_invalid_config_is_read_only_and_names_supported_recovery(self):
        with tempfile.TemporaryDirectory(prefix="drlink-retention-guidance-") as tmp:
            root = Path(tmp)
            config = root / "etc/drlink/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"public_host": "203.0.113.10", "enrollment_retention_days": "invalid"}))
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            with patch.dict(os.environ, {"FRP_DEPLOY_TEST_ROOT": tmp, "FRP_SKIP_SYSTEMD": "1"}):
                text, _code, report = doctor.run_doctor(tmp, {}, skip_network=True)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.assertEqual(after, before)
            issue = next(c for c in report.checks if c["id"] == "enrollment_retention_config")
            self.assertEqual(issue["status"], doctor.WARN)
            self.assertEqual(issue["section"], "state")
            self.assertIn("enrollment_retention_config", text)
            self.assertIn("installer-owned", text)
            self.assertIn("same immutable", text)
            self.assertIn("docs/INSTALLATION.md#enrollment-retention-recovery", text)
            self.assertIn("show enrollments", text)
            self.assertNotIn("set enrollment_retention_days", text)
            self.assertIn("installer-owned", doctor.render_json(report))

    def test_documented_normal_installer_reconfigure_restores_default_preserves_identity_and_mode(self):
        with tempfile.TemporaryDirectory(prefix="drlink-retention-reconfigure-") as tmp:
            root = Path(tmp)
            config = root / "etc/drlink/config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({
                "public_host": "203.0.113.10", "public_ip": "203.0.113.10",
                "public_url_host": "203.0.113.10", "deployment_mode": "direct",
                "enrollment_retention_days": "invalid", "egress_listen_addr": "192.0.2.10",
                "egress_listen_port": 6108, "port_start": 6000, "port_end": 6098,
            }))
            identity = root / "etc/frp/server_token"
            identity.parent.mkdir(parents=True)
            identity.write_bytes(b"isolated-existing-identity\n")
            record = root / "var/lib/drlink/enrollments/fixture.json"
            record.parent.mkdir(parents=True)
            record.write_bytes(b'{"fixture":"retained-record"}\n')
            env = {k: v for k, v in os.environ.items() if not k.startswith(("FRP_", "DRLINK_"))}
            env.update(FRP_SERVER_SOURCED="1", FRP_SERVER_TEST_ROOT=tmp,
                       FRP_SERVER_CONFIG=str(config), FRP_SKIP_SYSTEMD="1")
            script = 'source "$1/install-server.sh"; load_existing_server_config; resolve_server_settings; write_server_config'
            proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script, "retention-fixture", str(ROOT)],
                                  env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            actual = json.loads(config.read_text())
            self.assertEqual(lifecycle.retention_days_from_config(actual), 30)
            self.assertEqual(actual["public_ip"], "203.0.113.10")
            self.assertEqual(actual["deployment_mode"], "direct")
            self.assertEqual(actual["egress_listen_addr"], "192.0.2.10")
            self.assertEqual(actual["egress_listen_port"], 6108)
            self.assertEqual(identity.read_bytes(), b"isolated-existing-identity\n")
            self.assertEqual(record.read_bytes(), b'{"fixture":"retained-record"}\n')
            guide = (ROOT / "docs/INSTALLATION.md").read_text()
            self.assertIn("### Enrollment retention recovery", guide)
            self.assertIn("without `--upgrade`", guide)
            self.assertIn("30 days", guide)
            self.assertIn("same immutable", guide)
            self.assertIn("retained terminal records", guide)


if __name__ == "__main__":
    unittest.main()
