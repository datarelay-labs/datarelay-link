#!/usr/bin/env python3
"""PF11B Link native evidence + pinned Foundation evaluator; offline fixtures."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from drlink_control_plane import ControlPlane
import drlink_mcp_tls as mcp_tls
from drlink_web_connectivity import collect_link_connectivity, _probe_dns, _probe_ntp

NOW = 1781049600
TLS_VALID = datetime.fromtimestamp(NOW + 100*86400, timezone.utc).isoformat()
TLS_WARN = datetime.fromtimestamp(NOW + 4*86400, timezone.utc).isoformat()
TLS_EXPIRED = datetime.fromtimestamp(NOW - 60, timezone.utc).isoformat()


class LinkConnectivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pf11b-link-evidence-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        plane = ControlPlane(str(self.root))
        plane.close()

    def configure_tls(self, hostname="mcp.example.test"):
        plane = ControlPlane(str(self.root))
        try:
            state = mcp_tls.default_state()
            state["hostname"] = hostname
            state["mode"] = mcp_tls.MODE_PRIVATE_CA
            mcp_tls.save_state(plane, state)
        finally:
            plane.close()

    def sample(self, **kwargs):
        return collect_link_connectivity(
            str(self.root), now=NOW, **kwargs
        )

    def test_no_hostname_or_clock_proof_unknown_without_host_commands(self):
        with mock.patch("drlink_web_connectivity.subprocess.run") as run:
            result = self.sample()
            run.assert_not_called()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(
            [x["area"] for x in result["findings"]],
            ["dns", "ntp", "proxy", "trusted_ca", "certificate"],
        )
        self.assertEqual(result["findings"][0]["code"], "evidence_unavailable")
        self.assertEqual(result["findings"][1]["code"], "evidence_unavailable")
        self.assertEqual(result["findings"][-1]["code"], "certificate_missing")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["authoritative_mutation"])
        self.assertFalse(result["all_required_checks_verified"])

    def test_native_configured_hostname_is_only_dns_target_not_response_data(self):
        self.configure_tls()
        calls = []
        result = self.sample(
            resolver=lambda host: (calls.append(host), True)[-1],
            ntp_probe=lambda: (True, 1200),
            cert_reader=lambda _root: {"not_after": TLS_VALID},
        )
        self.assertEqual(calls, ["mcp.example.test"])
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["all_required_checks_verified"])
        encoded = json.dumps(result)
        self.assertNotIn("mcp.example.test", encoded)
        self.assertNotIn("203.0.113.", encoded)
        self.assertEqual([x["code"] for x in result["findings"][:2]],
                         ["healthy", "healthy"])

    def test_dns_failure_reports_real_failure_not_healthy(self):
        self.configure_tls()
        state = self.sample(
            resolver=lambda _: False, ntp_probe=lambda: (True, 0),
            cert_reader=lambda _: {"not_after": TLS_VALID},
        )
        self.assertEqual(state["status"], "fail")
        self.assertEqual(state["findings"][0]["code"], "dns_failure")

    def test_real_clock_unsynchronized_and_offset_thresholds(self):
        self.configure_tls()
        for probe, expected_status, ntp_reason in (
            ((False, None), "fail", "time_not_synchronized"),
            ((True, None), "unknown", "evidence_unavailable"),
            ((True, 10000), "warn", "time_offset_warning"),
            ((True, 30001), "fail", "time_offset_high"),
        ):
            with self.subTest(clock=probe):
                state = self.sample(
                    resolver=lambda _: True,
                    ntp_probe=lambda info=probe: info,
                    cert_reader=lambda _: {"not_after": TLS_VALID},
                )
                self.assertEqual(state["status"], expected_status)
                self.assertEqual(state["findings"][1]["code"], ntp_reason)

    def test_native_certificate_expiration_not_config_intent(self):
        self.configure_tls()
        for expiry, reason in ((TLS_WARN, "certificate_expiring"),
                                (TLS_EXPIRED, "certificate_expired")):
            with self.subTest(expiry=expiry):
                state = self.sample(
                    resolver=lambda _: True,
                    ntp_probe=lambda: (True, 0),
                    cert_reader=lambda _: {"not_after": expiry},
                )
                self.assertEqual(state["findings"][-1]["code"], reason)
        missing = self.sample(
            resolver=lambda _: True, ntp_probe=lambda: (True, 0),
            cert_reader=lambda _: None,
        )
        self.assertEqual(missing["status"], "unknown")
        self.assertEqual(missing["findings"][-1]["code"], "certificate_missing")

    def test_invalid_source_hostname_never_triggers_dns(self):
        plane = ControlPlane(str(self.root))
        try:
            plane.conn.execute("INSERT OR REPLACE INTO system_meta(key,value) VALUES (?,?)",
                               (mcp_tls.META_KEY, '{"hostname":"https://bad.example/path"}'))
        finally:
            plane.close()
        with mock.patch("drlink_web_connectivity._probe_dns") as probe:
            result = self.sample(cert_reader=lambda _: None)
            probe.assert_not_called()
        self.assertEqual(result["findings"][0]["code"], "evidence_unavailable")

    def test_proxy_and_ca_are_not_claimed_healthy_from_unverified_configuration(self):
        self.configure_tls()
        result = self.sample(
            resolver=lambda _: True, ntp_probe=lambda: (True, 0),
            cert_reader=lambda _: {"not_after": TLS_VALID},
            proxy_configured=True, ca_configured=True,
        )
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["findings"][2]["code"], "evidence_unavailable")
        self.assertEqual(result["findings"][3]["code"], "evidence_unavailable")
        self.assertFalse(result["all_required_checks_verified"])

    def test_dns_subprocess_is_fixed_bounded_and_silent(self):
        from subprocess import CompletedProcess
        with mock.patch("drlink_web_connectivity.subprocess.run",
                        return_value=CompletedProcess([], 0)) as run:
            self.assertTrue(_probe_dns("mcp.example.test"))
            argv = run.call_args.args[0]
            self.assertEqual(argv[0], sys.executable)
            self.assertEqual(argv[-1], "mcp.example.test")
            self.assertIn("getaddrinfo", argv[2])
            self.assertLessEqual(run.call_args.kwargs["timeout"], 3)
        with mock.patch("drlink_web_connectivity.subprocess.run",
                        side_effect=__import__("subprocess").TimeoutExpired([], 3)):
            self.assertFalse(_probe_dns("mcp.example.test"))

    def test_chrony_remaining_system_time_not_old_last_offset_drives_totp(self):
        from subprocess import CompletedProcess

        def stub(argv, **kwargs):
            if "timedatectl" in argv[0]:
                return CompletedProcess(argv, 0, stdout="yes\n")
            return CompletedProcess(
                argv, 0,
                stdout=(
                    "System time     : 31.250 seconds slow of NTP time\n"
                    "Last offset     : +0.001 seconds\n"
                    "Leap status     : Normal\n"
                ),
            )

        self.configure_tls()
        with mock.patch("drlink_web_connectivity.Path.is_file", return_value=True), \
             mock.patch("drlink_web_connectivity.subprocess.run", side_effect=stub):
            observed = _probe_ntp()
        self.assertEqual(observed, (True, -31250))
        report = self.sample(
            resolver=lambda _: True, ntp_probe=lambda: observed,
            cert_reader=lambda _: {"not_after": TLS_VALID},
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["findings"][1]["code"], "time_offset_high")

    def test_chrony_missing_system_time_cannot_show_healthy_ntp(self):
        from subprocess import CompletedProcess

        def stub(argv, **kwargs):
            if "timedatectl" in argv[0]:
                return CompletedProcess(argv, 0, stdout="yes\n")
            return CompletedProcess(
                argv, 0,
                stdout="Last offset     : +0.004 seconds\nLeap status     : Normal\n",
            )

        with mock.patch("drlink_web_connectivity.Path.is_file", return_value=True), \
             mock.patch("drlink_web_connectivity.subprocess.run", side_effect=stub):
            self.assertEqual(_probe_ntp(), (True, None))

    def test_chrony_leap_not_synchronised_overrides_timedatectl_yes(self):
        from subprocess import CompletedProcess

        def stub(argv, **kwargs):
            if "timedatectl" in argv[0]:
                return CompletedProcess(argv, 0, stdout="yes\n")
            return CompletedProcess(
                argv, 0,
                stdout=(
                    "System time     : 0.001 seconds fast of NTP time\n"
                    "Last offset     : +0.001 seconds\n"
                    "Leap status     : Not synchronised\n"
                ),
            )

        with mock.patch("drlink_web_connectivity.Path.is_file", return_value=True), \
             mock.patch("drlink_web_connectivity.subprocess.run", side_effect=stub):
            self.assertEqual(_probe_ntp(), (False, None))

    def test_ntp_probe_only_uses_absolute_read_only_commands(self):
        from subprocess import CompletedProcess
        def stub(argv, **kwargs):
            self.assertTrue(argv[0].startswith("/usr/"))
            self.assertLessEqual(kwargs["timeout"], 2)
            if "timedatectl" in argv[0]:
                return CompletedProcess(argv, 0, stdout="yes\n")
            return CompletedProcess(
                argv, 0,
                stdout=(
                    "System time     : 0.004 seconds fast of NTP time\n"
                    "Last offset     : +0.250 seconds\n"
                    "Leap status     : Normal\n"
                ),
            )
        with mock.patch("drlink_web_connectivity.Path.is_file", return_value=True), \
             mock.patch("drlink_web_connectivity.subprocess.run", side_effect=stub):
            self.assertEqual(_probe_ntp(), (True, 4))
        with mock.patch("drlink_web_connectivity.Path.is_file", return_value=False):
            self.assertEqual(_probe_ntp(), (None, None))


if __name__ == "__main__":
    unittest.main()
