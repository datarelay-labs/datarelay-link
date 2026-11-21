#!/usr/bin/env python3
"""S-023: local FRP success cannot establish an enrolled Server management identity."""
from __future__ import annotations

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import drlink_v24_cli as cli
import drlink_mgmt_sync as mgmt


class CatalogProofTests(unittest.TestCase):
    def setUp(self):
        self.plane = SimpleNamespace(root="/")
        self.healthy_row = {
            "name": "ssh", "destination": "localhost", "service_object": "ssh",
            "enabled": 1, "delete_pending": 0, "pending_allocation": 0,
            "endpoint_host": "203.0.113.9", "endpoint_port": 6006,
            "status": "HEALTHY", "runtime_verified": 1, "reason": "",
        }

    def test_S023_unknown_enrollment_fails_closed_despite_live_frpc(self):
        """Rocky9 reproduction: live FRP alone cannot promote management-denied service."""
        with (
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "fetch_server_catalog",
                              side_effect=mgmt.MgmtSyncError("management identity rejected")) as read,
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
        ):
            state = cli._agent_authenticated_management(self.plane, "Healthy")
            self.assertIs(state, False)
            self.assertEqual(
                cli._agent_service_status(
                    self.plane, self.healthy_row, "Healthy", management_verified=state
                ), "DEGRADED"
            )
            read.assert_called_once_with("/")

    def test_S008_one_missing_proxy_cannot_reuse_global_healthy_runtime(self):
        # FRP's aggregate service may be active while one proxy never bound.
        # A configured target health check is not required for this runtime proof.
        with (
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status",
                       return_value=("DEGRADED", "Runtime proxy is not ready in the active generation.")) as proof,
        ):
            state = cli._agent_service_status(
                self.plane, self.healthy_row, "Healthy", management_verified=True
            )
        self.assertEqual(state, "DEGRADED")
        proof.assert_called_once_with(self.plane, "ssh", root="/")

    def test_auth_success_can_remain_healthy_and_reuses_one_read(self):
        services = [dict(self.healthy_row, name="ssh"), dict(self.healthy_row, name="web")]
        self.plane.conn = mock.MagicMock()
        self.plane.conn.execute.return_value = services
        with (
            mock.patch.object(cli, "_require_agent"),
            mock.patch.object(cli, "_agent_runtime_level", return_value="Healthy"),
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "fetch_server_catalog", return_value={"managedHosts": [{"id": "registered-host"}]}) as read,
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status", return_value=("HEALTHY", "")),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(cli.handle_show(self.plane, ["remote-services"]), 0)
        self.assertEqual(output.getvalue().count("HEALTHY"), 2)
        read.assert_called_once_with("/")

    def test_S008_list_checks_each_proxy_without_hiding_healthy_sibling(self):
        services = [dict(self.healthy_row, name="ssh"), dict(self.healthy_row, name="web")]
        self.plane.conn = mock.MagicMock()
        self.plane.conn.execute.return_value = services
        def verify(_plane, name, *, root):
            self.assertEqual(root, "/")
            return ("DEGRADED", "Runtime proxy absent") if name == "ssh" else ("HEALTHY", "")
        with (
            mock.patch.object(cli, "_require_agent"),
            mock.patch.object(cli, "_agent_runtime_level", return_value="Healthy"),
            mock.patch.object(cli, "_agent_authenticated_management", return_value=True),
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status", side_effect=verify) as proof,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(cli.handle_show(self.plane, ["remote-services"]), 0)
        lines = output.getvalue().splitlines()
        ssh = next(line for line in lines if line.startswith("ssh "))
        web = next(line for line in lines if line.startswith("web "))
        self.assertTrue(ssh.endswith("DEGRADED"))
        self.assertTrue(web.endswith("HEALTHY"))
        self.assertEqual(proof.call_count, 2)
        self.assertIn("not application availability at the target", output.getvalue())

    def test_S008_per_service_proof_exception_is_never_healthy(self):
        with (
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status",
                       side_effect=OSError("private runtime details")),
        ):
            self.assertEqual(
                cli._agent_service_status(self.plane, self.healthy_row, "Healthy", True),
                "DEGRADED",
            )

    def test_S008_single_service_does_not_claim_target_listener_verified(self):
        self.plane.conn = mock.MagicMock()
        self.plane.conn.execute.return_value.fetchone.return_value = self.healthy_row
        with (
            mock.patch.object(cli, "_require_agent"),
            mock.patch.object(cli, "_agent_runtime_level", return_value="Healthy"),
            mock.patch.object(cli, "_agent_authenticated_management", return_value=True),
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status",
                       return_value=("HEALTHY", "")),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(cli.handle_show(self.plane, ["remote-service", "ssh"]), 0)
        text = output.getvalue()
        self.assertIn("Status: HEALTHY", text)
        self.assertIn("Target application availability is not established", text)
        self.assertIn("test the public endpoint", text)

    def test_catalog_denied_projects_all_healthy_rows_degraded_once(self):
        services = [dict(self.healthy_row, name="ssh"), dict(self.healthy_row, name="web")]
        self.plane.conn = mock.MagicMock()
        self.plane.conn.execute.return_value = services
        with (
            mock.patch.object(cli, "_require_agent"),
            mock.patch.object(cli, "_agent_runtime_level", return_value="Healthy"),
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "fetch_server_catalog",
                              side_effect=mgmt.MgmtSyncError("unknown identity")) as read,
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(cli.handle_show(self.plane, ["remote-services"]), 0)
        self.assertEqual(output.getvalue().count("DEGRADED"), 2)
        read.assert_called_once_with("/")

    def test_local_runtime_degraded_does_not_contact_management_server(self):
        with (
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "fetch_server_catalog") as read,
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
        ):
            self.assertIsNone(cli._agent_authenticated_management(self.plane, "Warning"))
            self.assertEqual(cli._agent_service_status(
                self.plane, self.healthy_row, "Warning", management_verified=None
            ), "DEGRADED")
            read.assert_not_called()

    def test_explicit_offline_fixture_keeps_existing_local_semantics(self):
        with (
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=False),
            mock.patch.object(mgmt, "fetch_server_catalog") as read,
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            mock.patch("drlink_v24_runtime.verified_remote_service_status", return_value=("HEALTHY", "")),
        ):
            state = cli._agent_authenticated_management(self.plane, "Healthy")
            self.assertIsNone(state)
            self.assertEqual(cli._agent_service_status(
                self.plane, self.healthy_row, "Healthy", management_verified=state
            ), "HEALTHY")
            read.assert_not_called()

    def test_single_service_guidance_is_actionable_without_exposing_auth_error(self):
        self.plane.conn = mock.MagicMock()
        self.plane.conn.execute.return_value.fetchone.return_value = self.healthy_row
        with (
            mock.patch.object(cli, "_require_agent"),
            mock.patch.object(cli, "_agent_runtime_level", return_value="Healthy"),
            mock.patch.object(mgmt, "use_live_mgmt_path", return_value=True),
            mock.patch.object(mgmt, "fetch_server_catalog",
                              side_effect=mgmt.MgmtSyncError("sensitive internal denied secret")),
            mock.patch("drlink_agent_lifecycle.load_lifecycle_intent", return_value="active"),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(cli.handle_show(self.plane, ["remote-service", "ssh"]), 0)
        txt = output.getvalue()
        self.assertIn("Status: DEGRADED", txt)
        self.assertIn("management", txt.lower())
        self.assertIn("system diagnostics", txt)
        self.assertNotIn("sensitive internal", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
