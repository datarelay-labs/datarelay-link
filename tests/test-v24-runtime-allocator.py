#!/usr/bin/env python3
"""v2.4 Remote Service runtime activation + single allocator authority tests."""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import subprocess
import tarfile
import time
from contextlib import contextmanager
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "server"))

import drlink_v24 as v24
import drlink_v24_runtime as runtime
from drlink_control_plane import ControlPlane


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class RuntimeRenderTests(unittest.TestCase):
    def test_unit_template_does_not_misidentify_legacy_admin_exec_as_supervised(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, 'frpc.toml')
            config.write_text('serverAddr = "host"\nauth.token = "fixture"\n')
            props = ('ActiveState=active\nInvocationID=' + 'a' * 32
                     + '\nExecStart=/usr/bin/python3 drlink_frpc_supervisor.py\nMainPID=123\n')
            with (mock.patch.object(runtime.subprocess, 'check_output', return_value=props),
                  mock.patch.object(runtime, '_frpc_toml_path', return_value=config),
                  mock.patch.object(runtime, '_supervisor_process_running', return_value=False, create=True)):
                self.assertEqual(runtime._supervised_invocation(), '')

    def test_existing_runtime_requires_current_connection_epoch(self):
        service = {'web': {'id': 'rs-web', 'enabled': True}}
        props = 'ActiveState=active\nInvocationID=' + 'a' * 32 + '\n'
        success = 'login to server success\n[host-rs-web] start proxy success\n'
        for logs, expected in ((success, True), (success + 'control worker is closed\n', False),
                               ('login server failed\n' + success, True), ('', False),
                               (success + '[host-rs-web] start proxy error\n', False),
                               (success + 'proxy removed: [host-rs-web other-proxy]\n', False),
                               (success + '[host-rs-web] stop proxy\n', False),
                               (success + 'proxy removed: [host-rs-web]\n' + '[host-rs-web] start proxy success\n', True)):
            with self.subTest(logs=logs), mock.patch.object(runtime.subprocess, 'check_output', side_effect=[props, logs]):
                self.assertEqual(runtime._current_runtime_ready(None, 'host', service), expected)

    def test_real_activation_requires_new_generation_success(self):
        from drlink_control_plane import ControlPlaneError
        service = {'rs-web': {'id': 'rs-web', 'enabled': True, 'v24_remote_service': True, 'remote_port': 6010}}
        toml = 'name = "host-rs-web"\nremotePort = 6010\n'
        with self.assertRaises(ControlPlaneError):
            runtime.verify_runtime_proxies(root=None, host_id='host', expected=service, toml_text=toml)
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp, 'journalctl')
            journal.write_text('#!/bin/sh\ncase "$*" in *--after-cursor*fresh*) exit 0;; esac\nprintf "login to server success\\n[host-rs-web] start proxy success\\n"\n')
            journal.chmod(0o755)
            with mock.patch.dict(os.environ, {'PATH': tmp + os.pathsep + os.environ['PATH'], 'FRP_PROXY_WAIT_MAX_ATTEMPTS': '1', 'FRP_PROXY_WAIT_SLEEP_S': '0'}):
                with self.assertRaisesRegex(ControlPlaneError, 'could not be verified'):
                    runtime.verify_runtime_proxies(root=None, host_id='host', expected=service, toml_text=toml, since_cursor='fresh')
                journal.write_text('#!/bin/sh\nprintf "login to server success\\n[host-rs-web] start proxy success\\n"\n')
                runtime.verify_runtime_proxies(root=None, host_id='host', expected=service, toml_text=toml, since_cursor='fresh')

    def test_REMOTE_SERVICE_RUNTIME_RENDER(self):
        text = runtime.render_frpc_toml_text(
            server="203.0.113.9",
            server_port=443,
            token="tok",
            host_id="host-abc",
            services={
                "ssh": {
                    "id": "ssh",
                    "enabled": True,
                    "local_ip": "127.0.0.1",
                    "local_port": 22,
                    "remote_port": 6003,
                },
                "rs-web": {
                    "id": "rs-web",
                    "enabled": True,
                    "local_ip": "127.0.0.1",
                    "local_port": 8080,
                    "remote_port": 6010,
                    "v24_remote_service": True,
                },
            },
        )
        self.assertIn('name = "host-abc-ssh"', text)
        self.assertIn('name = "host-abc-rs-web"', text)
        self.assertIn("remotePort = 6010", text)
        runtime.validate_frpc_toml_text(text)

    def test_proxy_id_stable(self):
        self.assertEqual(runtime.remote_service_proxy_id("Web-API"), "rs-web-api")
        self.assertTrue(runtime.remote_service_proxy_id("x").startswith("rs-"))

    def test_allowed_long_names_do_not_share_runtime_or_allocator_identity(self):
        names = ["c27d-fpool-lastslot-filler-%03d" % i for i in range(95)]
        ids = [runtime.remote_service_proxy_id(name) for name in names]
        self.assertEqual(len(set(ids)), len(names))
        self.assertTrue(all(runtime.SERVICE_ID_RE.fullmatch(sid) for sid in ids))
        self.assertEqual(ids, [runtime.remote_service_proxy_id(n.upper()) for n in names])

    def test_canonical_legacy_long_identity_is_preserved_without_relabeling_new_names(self):
        name = "c27d-f051-identical-long-service-prefix-first"
        legacy = ("rs-" + name)[:32]
        self.assertNotEqual(runtime.remote_service_proxy_id(name), legacy)
        self.assertEqual(runtime.remote_service_proxy_id(name, stored=legacy), legacy)
        with self.assertRaises(v24.ControlPlaneError):
            runtime.remote_service_proxy_id(name, stored="rs-unrelated-publication")


class RuntimeProxyIdentityMigrationTests(unittest.TestCase):
    def test_old_rows_keep_ids_and_subsequent_schema_checks_do_not_relabel_new_rows(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE published_services(id TEXT PRIMARY KEY, name TEXT)")
        conn.executescript(v24.V2_SCHEMA_SQL.replace("  runtime_proxy_id TEXT,\n", ""))
        name = "c27d-f051-identical-long-service-prefix-first"
        conn.execute("INSERT INTO published_services VALUES ('pub-old', ?)", (name,))
        conn.execute("INSERT INTO remote_service_meta(service_id) VALUES ('pub-old')")
        conn.execute("INSERT INTO agent_remote_services(name,destination,service_object,updated_at) "
                     "VALUES (?, 'target', 'tcp', '2026-10-27T00:00:00Z')", (name,))
        v24.ensure_v2_schema(conn)
        legacy = ("rs-" + name)[:32]
        self.assertEqual(conn.execute("SELECT runtime_proxy_id FROM remote_service_meta").fetchone()[0], legacy)
        self.assertEqual(conn.execute("SELECT runtime_proxy_id FROM agent_remote_services").fetchone()[0], legacy)
        conn.execute("INSERT INTO published_services VALUES ('pub-new', 'new-long-name-pending-publication')")
        conn.execute("INSERT INTO remote_service_meta(service_id) VALUES ('pub-new')")
        v24.ensure_v2_schema(conn)
        self.assertIsNone(conn.execute("SELECT runtime_proxy_id FROM remote_service_meta "
                                       "WHERE service_id='pub-new'").fetchone()[0])


class FRPAuthenticatedReloadSecurityTests(unittest.TestCase):
    def test_existing_admin_requires_strong_auth_and_loopback_private_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "frpc.toml")
            secure = (
                'serverAddr = "203.0.113.9"\n'
                'webServer.addr = "127.0.0.1"\n'
                'webServer.port = 17400\n'
                'webServer.user = "drlink-admin"\n'
                'webServer.password = "%s"\n'
            ) % ("AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_abcd"[:40])
            path.write_text(secure)
            # The insecure file case must be deterministic even when a Codex
            # execution profile or CI runner starts with umask 0077.
            path.chmod(0o644)
            self.assertIsNone(runtime._trusted_existing_frpc_admin(path, secure))
            path.chmod(0o600)
            self.assertIsNotNone(runtime._trusted_existing_frpc_admin(path, secure))
            for bad in (
                secure.replace('"127.0.0.1"', '"0.0.0.0"'),
                secure.replace('"127.0.0.1"', '"::1"'),
                secure.replace('17400', '80'),
                secure.replace('drlink-admin', ''),
                secure.replace('AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_abcd'[:40], 'admin'),
                secure + 'webServer.enablePrometheus = true\n',
            ):
                self.assertIsNone(runtime._trusted_existing_frpc_admin(path, bad))

    def test_authenticated_local_reload_must_verify_all_proxy_statuses(self):
        from drlink_control_db import ControlPlaneError
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "frpc.toml")
            outputs = [
                mock.Mock(returncode=0, stdout="frpc: syntax is ok"),
                mock.Mock(returncode=0, stdout="reload success"),
                mock.Mock(returncode=0, stdout="NAME TYPE STATUS\nagent-web tcp running"),
            ]
            with (mock.patch.object(runtime, "_frpc_running_invocation_id",
                                  return_value="a" * 32),
                  mock.patch.object(runtime.Path, "is_file", return_value=True),
                 mock.patch.object(runtime.subprocess, "run", side_effect=outputs) as call,
                 mock.patch.object(runtime, "_current_runtime_ready", return_value=True)):
                runtime._reload_frpc_authenticated(
                    path, root=None, host_id="agent",
                    expected={"web": {"id": "web", "enabled": True}},
                )
            self.assertEqual(call.call_count, 3)
            self.assertEqual([x.args[0][1] for x in call.call_args_list],
                             ["verify", "reload", "status"])
            with (mock.patch.object(runtime, "_frpc_running_invocation_id",
                                  return_value="a" * 32),
                  mock.patch.object(runtime.Path, "is_file", return_value=True),
                 mock.patch.object(runtime.subprocess, "run",
                                  side_effect=[outputs[0], outputs[1],
                                               mock.Mock(returncode=0, stdout="NAME TYPE STATUS")]),
                 mock.patch.object(runtime, "_current_runtime_ready", return_value=True)):
                with self.assertRaisesRegex(ControlPlaneError, "all expected proxies"):
                    runtime._reload_frpc_authenticated(
                        path, root=None, host_id="agent",
                        expected={"web": {"id": "web", "enabled": True}},
                    )

    def test_removed_proxy_must_not_remain_running_after_reload(self):
        from drlink_control_db import ControlPlaneError
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "frpc.toml")
            result = [
                mock.Mock(returncode=0, stdout="frpc: syntax is ok"),
                mock.Mock(returncode=0, stdout="reload success"),
                mock.Mock(returncode=0,
                          stdout="NAME TYPE STATUS\nagent-web tcp running\n"
                                 "agent-retired tcp running\n"),
            ]
            with (mock.patch.object(runtime, "_frpc_running_invocation_id",
                                    return_value="a" * 32),
                  mock.patch.object(runtime.Path, "is_file", return_value=True),
                  mock.patch.object(runtime.subprocess, "run", side_effect=result),
                  mock.patch.object(runtime, "_current_runtime_ready", return_value=True)):
                with self.assertRaisesRegex(ControlPlaneError, "retained a removed"):
                    runtime._reload_frpc_authenticated(
                        path, root=None, host_id="agent",
                        expected={"web": {"id": "web", "enabled": True}},
                        removed_names={"agent-retired"},
                    )

    def test_reload_must_not_treat_changed_process_generation_as_healthy(self):
        from drlink_control_db import ControlPlaneError
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "frpc.toml")
            result = [
                mock.Mock(returncode=0, stdout="frpc: syntax is ok"),
                mock.Mock(returncode=0, stdout="reload success"),
                mock.Mock(returncode=0, stdout="agent-web tcp running\n"),
            ]
            with (mock.patch.object(runtime, "_frpc_running_invocation_id",
                                    side_effect=["a" * 32, "b" * 32]),
                  mock.patch.object(runtime.Path, "is_file", return_value=True),
                  mock.patch.object(runtime.subprocess, "run", side_effect=result),
                  mock.patch.object(runtime, "_current_runtime_ready", return_value=True)):
                with self.assertRaisesRegex(ControlPlaneError, "changed the Agent process"):
                    runtime._reload_frpc_authenticated(
                        path, root=None, host_id="agent",
                        expected={"web": {"id": "web", "enabled": True}},
                    )

    def test_admin_reload_errors_never_leak_credentials(self):
        from drlink_control_db import ControlPlaneError
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "frpc.toml")
            private = "EXAMPLE_SECRET_MUST_NOT_APPEAR"
            result = [
                mock.Mock(returncode=0, stdout="frpc: syntax is ok"),
                mock.Mock(returncode=1, stdout="", stderr=private),
            ]
            with (mock.patch.object(runtime, "_frpc_running_invocation_id",
                                    return_value="a" * 32),
                  mock.patch.object(runtime.Path, "is_file", return_value=True),
                  mock.patch.object(runtime.subprocess, "run", side_effect=result)):
                with self.assertRaises(ControlPlaneError) as ctx:
                    runtime._reload_frpc_authenticated(
                        path, root=None, host_id="agent", expected={}
                    )
            self.assertNotIn(private, str(ctx.exception))



class RuntimeApplyRemoveTests(unittest.TestCase):
    def test_long_name_runtime_preserves_canonical_old_id_and_distinguishes_new_peer(self):
        first = "c27d-f051-identical-long-service-prefix-first"
        second = "c27d-f051-identical-long-service-prefix-second"
        legacy = runtime.legacy_remote_service_proxy_id(first)
        self.plane.conn.execute("UPDATE agent_remote_services SET name=?, runtime_proxy_id=? WHERE name='web'",
                                (first, legacy))
        now = v24.utc_now_iso()
        self.plane.conn.execute("INSERT INTO agent_object_catalog VALUES ('service-object','web-peer',?,?)",
                                ('{"name":"web-peer","type":"tcp","port":8081}', now))
        self.plane.conn.execute("INSERT INTO agent_remote_services "
                                "(name,destination,service_object,endpoint_port,pending_allocation,updated_at) "
                                "VALUES (?, 'agent-1','web-peer',6011,0,?)", (second, now))
        self.plane.conn.commit()
        desired = runtime.build_desired_runtime_services(self.plane, runtime.load_client_state(self.tmp), root=self.tmp)
        self.assertEqual(desired[legacy]['remote_port'], 6010)
        self.assertEqual(desired[runtime.remote_service_proxy_id(second)]['remote_port'], 6011)
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result['ok'], result)
        self.assertEqual(runtime._configured_v24_runtime_ports(self.tmp), {first: 6010, second: 6011})

    def _populate_capacity_projection(self):
        # Distinct canonical services with a shared local target are sufficient
        # to expose projection work growth; no wall-clock/SLO assertion.
        for index in range(1, 199):
            self.plane.conn.execute(
                "INSERT INTO agent_remote_services "
                "(name,destination,service_object,enabled,status,endpoint_host,endpoint_port,"
                "pending_allocation,delete_pending,pool_class,reason,updated_at) "
                "SELECT ?,destination,service_object,enabled,status,endpoint_host,?,"
                "pending_allocation,delete_pending,pool_class,reason,updated_at "
                "FROM agent_remote_services WHERE name='web'",
                ('capacity-%s' % index, 6010 + index))
        self.plane.conn.commit()

    def test_capacity_projection_reads_identity_once_and_refreshes_next_call(self):
        self._populate_capacity_projection()
        state = runtime.load_client_state(self.tmp)
        with mock.patch.object(v24, 'load_agent_identity', wraps=v24.load_agent_identity) as identity:
            first = runtime.build_desired_runtime_services(self.plane, state, root=self.tmp)
            self.assertEqual(sum(bool(rec.get('v24_remote_service')) for rec in first.values()), 199)
            self.assertEqual(identity.call_count, 1)
            second = runtime.build_desired_runtime_services(self.plane, state, root=self.tmp)
            self.assertEqual(second, first)
            self.assertEqual(identity.call_count, 2)  # no cache across operations

    def test_capacity_single_service_status_only_resolves_its_target(self):
        self._populate_capacity_projection()
        queries = []
        self.plane.conn.set_trace_callback(queries.append)
        try:
            status, _ = runtime.verified_remote_service_status(self.plane, 'web', root=self.tmp)
        finally:
            self.plane.conn.set_trace_callback(None)
        self.assertEqual(status, 'DEGRADED')  # fixture has no installed v2.4 proxy
        targets = [q for q in queries if "kind='service-object'" in q]
        self.assertEqual(len(targets), 1, 'one status must not resolve all 199 targets')

    def _provision_existing_secure_admin_fixture(self):
        # Explicitly test the already-approved/admin-provisioned path;
        # the product must not auto-open a new HTTP management endpoint.
        frp = Path(self.tmp, "etc/frp")
        config = frp / "frpc.toml"
        state = json.loads((frp / "client-state.json").read_text())
        admin = {"port": 17400, "user": "local-admin",
                 "password": "AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPp0123456789_"[:40]}
        text = runtime.render_frpc_toml_text(
            server=state["frp_server"], server_port=state["frp_server_port"],
            token="tok", host_id=state["host_id"],
            services=state["services"], reload_admin=admin,
        )
        config.write_text(text, encoding="utf-8")
        config.chmod(0o600)
        self.assertIsNotNone(runtime._trusted_existing_frpc_admin(config, text))
        return config, state

    def test_isolated_apply_and_failed_rollback_never_restart_unrelated_runtime(self):
        from drlink_control_db import ControlPlaneError
        config = Path(self.tmp, 'etc/frp/frpc.toml')
        before = config.read_bytes()
        state = Path(self.tmp, 'etc/frp/client-state.json')
        before_state = state.read_bytes()
        with (mock.patch.object(runtime, '_supervised_invocation', return_value='a' * 32),
              mock.patch.object(runtime, '_current_runtime_ready', return_value=True),
              mock.patch.object(runtime, '_restart_frpc') as restart,
              mock.patch.object(runtime, '_wait_supervised_runtime',
                                side_effect=[ControlPlaneError('registration failed'), None]) as wait):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result['ok'])
        self.assertNotIn('RECOVERY_REQUIRED', result['error'])
        self.assertEqual(wait.call_count, 2)
        restart.assert_not_called()
        self.assertEqual(config.read_bytes(), before)
        self.assertEqual(state.read_bytes(), before_state)

    def test_F007_securely_provisioned_admin_reloads_changed_proxy_without_full_restart(self):
        config, state = self._provision_existing_secure_admin_fixture()
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=True),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated") as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        reload.assert_called_once()
        restart.assert_not_called()
        self.assertIn('webServer.addr = "127.0.0.1"', config.read_text())
        self.assertIn("rs-web", json.loads(
            Path(self.tmp, "etc/frp/client-state.json").read_text())["services"])
        self.assertIn("remotePort = 6010", config.read_text())
        row = self.plane.conn.execute(
            "SELECT status, runtime_verified FROM agent_remote_services "
            "WHERE name='web'"
        ).fetchone()
        self.assertEqual((row["status"], row["runtime_verified"]), ("HEALTHY", 1))

    def test_F007_failed_secure_reload_restores_config_without_full_restart(self):
        from drlink_control_db import ControlPlaneError
        config, state = self._provision_existing_secure_admin_fixture()
        previous = config.read_bytes()
        old_state = Path(self.tmp, "etc/frp/client-state.json").read_bytes()
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=True),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated",
                                side_effect=[ControlPlaneError("reload rejected"), None]) as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result["ok"], result)
        self.assertEqual(reload.call_count, 2)  # old config rollback, no global restart
        restart.assert_not_called()
        self.assertEqual(config.read_bytes(), previous)
        self.assertEqual(
            Path(self.tmp, "etc/frp/client-state.json").read_bytes(), old_state
        )

    def test_F007_reload_rollback_failure_is_recovery_required_not_restart(self):
        from drlink_control_db import ControlPlaneError
        config, _state = self._provision_existing_secure_admin_fixture()
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=True),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated",
                                side_effect=ControlPlaneError("admin rejected")) as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result["ok"], result)
        self.assertIn("RECOVERY_REQUIRED", result["error"])
        self.assertEqual(reload.call_count, 2)
        restart.assert_not_called()

    def test_F007_weak_admin_cannot_silently_enable_new_management_listener(self):
        config, _state = self._provision_existing_secure_admin_fixture()
        original = config.read_text(encoding="utf-8")
        config.write_text(original.replace("local-admin", "admin")
                          .replace("AaBbCcDdEeFfGgHhIiJjKkLlMmNnOoPp0123456789_"[:40],
                                   "weak"), encoding="utf-8")
        self.assertIsNone(runtime._trusted_existing_frpc_admin(
            config, config.read_text()
        ))
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=True),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated") as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        restart.assert_called_once()
        reload.assert_not_called()
        self.assertNotIn("webServer.", config.read_text(encoding="utf-8"))

    def test_F007_missing_or_unverified_admin_uses_existing_restart_contract(self):
        config, state = self._provision_existing_secure_admin_fixture()
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=False),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated") as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        restart.assert_called_once()
        reload.assert_not_called()

    def test_F007_common_server_config_change_cannot_use_proxy_hot_reload(self):
        config, state = self._provision_existing_secure_admin_fixture()
        state["frp_server_port"] = 7001
        _write_json(Path(self.tmp, "etc/frp/client-state.json"), state)
        with (mock.patch.object(runtime, "_current_runtime_ready", return_value=True),
              mock.patch.object(runtime, "_restart_frpc") as restart,
              mock.patch.object(runtime, "_reload_frpc_authenticated") as reload):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        restart.assert_called_once()
        reload.assert_not_called()

    def test_reconnect_forces_fresh_generation_even_with_identical_artifacts(self):
        with mock.patch.object(runtime, '_restart_frpc') as restart:
            self.assertTrue(runtime.apply_agent_runtime(self.plane, root=self.tmp)['ok'])
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp, force_reapply=True)
            self.assertTrue(result['ok'], result)
            self.assertFalse(result.get('no_change'))
            self.assertEqual(restart.call_count, 2)

    def test_same_runtime_keeps_sessions_and_all_verified_rows(self):
        with mock.patch.object(runtime, '_restart_frpc') as restart:
            first = runtime.apply_agent_runtime(self.plane, root=self.tmp)
            self.assertTrue(first['ok'], first)
            runtime.mark_runtime_status(self.plane, ok=True)
            second = runtime.apply_agent_runtime(self.plane, root=self.tmp)
            self.assertTrue(second['ok'], second)
            self.assertEqual(restart.call_count, 1)
            self.assertTrue(second.get('no_change'))
            row = self.plane.conn.execute("SELECT runtime_verified, status FROM agent_remote_services WHERE name='web'").fetchone()
            self.assertEqual(row['runtime_verified'], 1)
            self.assertEqual(row['status'], 'HEALTHY')

    def test_wss_runtime_apply_preserves_trusted_allocator_ca(self):
        """A Remote Service reconciliation must keep the WSS trust anchor."""
        frp = Path(self.tmp, "etc/frp")
        state_path = frp / "client-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["frp_transport"] = "wss"
        _write_json(state_path, state)
        ca_path = Path(self.tmp, "etc/drlink/allocator-ca.crt")
        ca_path.parent.mkdir(parents=True, exist_ok=True)
        ca_path.write_text("test-owned CA fixture", encoding="utf-8")

        applied = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(applied["ok"], applied)
        rendered = (frp / "frpc.toml").read_text(encoding="utf-8")
        self.assertIn('transport.protocol = "wss"', rendered)
        self.assertIn('transport.tls.trustedCaFile = "%s"' % ca_path, rendered)
        self.assertNotIn('transport.tls.trustedCaFile = ""', rendered)

    def test_wss_macos_flat_state_uses_its_own_allocator_ca(self):
        """Apple Silicon's flat Application Support state keeps its own CA."""
        linux = Path(self.tmp, "etc/frp")
        state = json.loads((linux / "client-state.json").read_text(encoding="utf-8"))
        state["frp_transport"] = "wss"
        mac = Path(self.tmp, "Library/Application Support/drlink")
        mac.mkdir(parents=True, exist_ok=True)
        _write_json(mac / "client-state.json", state)
        (mac / "frpc.toml").write_text(
            (linux / "frpc.toml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        ca_path = mac / "allocator-ca.crt"
        ca_path.write_text("test-owned macOS CA fixture", encoding="utf-8")
        (linux / "client-state.json").unlink()
        (linux / "frpc.toml").unlink()

        with mock.patch.dict(os.environ, {"FRP_MACOS_STATE_ROOT": str(mac)}):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        rendered = (mac / "frpc.toml").read_text(encoding="utf-8")
        self.assertIn('transport.tls.trustedCaFile = "%s"' % ca_path, rendered)

    def test_unsupported_transport_does_not_silently_fallback_to_tcp(self):
        """An invalid enrolled transport must not rewrite the live Agent."""
        frp = Path(self.tmp, "etc/frp")
        state_path = frp / "client-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["frp_transport"] = "invalid-transport"
        _write_json(state_path, state)
        existing = (frp / "frpc.toml").read_text(encoding="utf-8")

        with mock.patch.object(runtime, "_restart_frpc") as restart:
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result["ok"], result)
        self.assertIn("unsupported FRP transport", result["error"])
        self.assertEqual((frp / "frpc.toml").read_text(encoding="utf-8"), existing)
        restart.assert_not_called()

    def test_wss_missing_allocator_ca_fails_before_runtime_rewrite(self):
        """Missing WSS CA must not install an untrusted frpc configuration."""
        frp = Path(self.tmp, "etc/frp")
        state_path = frp / "client-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["frp_transport"] = "wss"
        _write_json(state_path, state)
        existing = (frp / "frpc.toml").read_text(encoding="utf-8")

        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result["ok"], result)
        self.assertIn("allocator CA", result["error"])
        self.assertEqual((frp / "frpc.toml").read_text(encoding="utf-8"), existing)

    def test_successful_full_apply_refreshes_all_included_verification(self):
        self.plane.conn.execute("UPDATE agent_remote_services SET runtime_verified=1, status='HEALTHY', reason=''")
        self.plane.conn.commit()
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.plane.conn.execute("SELECT runtime_verified FROM agent_remote_services WHERE name='web'").fetchone()[0], 1)

    def test_fresh_apply_without_continuing_generation_proof_stays_degraded(self):
        # A native startup check can succeed even though the current process
        # cannot later be bound to that verified proxy generation.
        with mock.patch.object(runtime, '_current_runtime_ready', return_value=False):
            result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result['ok'], result)
        row = self.plane.conn.execute(
            "SELECT status, runtime_verified, reason FROM agent_remote_services "
            "WHERE name='web'"
        ).fetchone()
        self.assertEqual((row['status'], row['runtime_verified']), ('DEGRADED', 0))
        self.assertIn('active generation', row['reason'])

    def test_same_artifacts_with_unhealthy_runtime_reapply_for_recovery(self):
        with mock.patch.object(runtime, '_restart_frpc') as restart:
            self.assertTrue(runtime.apply_agent_runtime(self.plane, root=self.tmp)['ok'])
            with mock.patch.object(runtime, '_current_runtime_ready', return_value=False):
                recovered = runtime.apply_agent_runtime(self.plane, root=self.tmp)
            self.assertTrue(recovered['ok'], recovered)
            self.assertEqual(restart.call_count, 2)
            self.assertFalse(recovered.get('no_change'))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-rt-")
        frp = Path(self.tmp, "etc/frp")
        frp.mkdir(parents=True)
        frp.chmod(0o700)
        _write_json(
            frp / "client-state.json",
            {
                "schema_version": 2,
                "allocator_url": "https://example:6099/enroll",
                "frp_server": "203.0.113.9",
                "frp_server_port": 443,
                "frp_transport": "tcp",
                "hostname": "agent-1",
                "machine_id": "aabbccddeeff00112233445566778899",
                "host_id": "agent-1-aabbccdd",
                "services": {
                    "ssh": {
                        "id": "ssh",
                        "name": "SSH",
                        "preset": "ssh",
                        "protocol": "tcp",
                        "local_ip": "127.0.0.1",
                        "local_port": 22,
                        "remote_port": 6003,
                        "enabled": True,
                        "ssh_user": "ec2-user",
                    }
                },
            },
        )
        (frp / "frpc.toml").write_text(
            'serverAddr = "203.0.113.9"\nserverPort = 443\n\n'
            'auth.method = "token"\nauth.token = "tok"\n\n'
            "transport.tls.enable = true\n\n"
            "[[proxies]]\nname = \"agent-1-aabbccdd-ssh\"\ntype = \"tcp\"\n"
            'localIP = "127.0.0.1"\nlocalPort = 22\nremotePort = 6003\n',
            encoding="utf-8",
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_SKIP_ACTIVATION"] = "0"
        os.environ["FRP_SKIP_SYSTEMD"] = "1"
        # These tests simulate native activation separately. Bind their
        # continuing-generation proof explicitly instead of relying on an
        # arbitrary non-root path to stand in for a live process.
        self.runtime_ready_patch = mock.patch.object(
            runtime, "_current_runtime_ready", return_value=True)
        self.runtime_ready_patch.start()
        self.addCleanup(self.runtime_ready_patch.stop)
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_object_catalog(kind, name, payload, synced_at) VALUES (?,?,?,?)",
            ("service-object", "web", '{"name":"web","type":"tcp","port":8080}', now),
        )
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at) "
            "VALUES ('web','agent-1','web',1,'DEGRADED','drlink.local',6010,0,0,'normal','',?)",
            (now,),
        )
        self.plane.conn.commit()

    def tearDown(self):
        self.plane.close()
        for k in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_SKIP_ACTIVATION", "FRP_SKIP_SYSTEMD",
                  "DRLINK_FAULT_RUNTIME_CONFIG", "DRLINK_FAULT_RUNTIME_VERIFY", "DRLINK_FAULT_RUNTIME_RESTART"):
            os.environ.pop(k, None)

    @contextmanager
    def _pinned_local_frp_fixture(self):
        # Every connection belongs to disposable loopback fixtures. No host
        # service/systemd, external endpoint or operational identity is used.
        def port():
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                return sock.getsockname()[1]

        target = socket.socket()
        target.bind(('127.0.0.1', 0))
        target.listen()
        target.settimeout(0.1)
        target_port = target.getsockname()[1]
        marker = b'SSH-2.0-U001-local-target-marker\r\n'
        stop = threading.Event()
        def serve():
            while not stop.is_set():
                try:
                    connection, _ = target.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.sendall(marker)
        thread = threading.Thread(target=serve)
        thread.start()
        binaries = Path(self.tmp, 'fixture-bin')
        binaries.mkdir()
        archive = ROOT / 'third_party/frp/v0.71.0/binaries/frp_0.71.0_linux_amd64.tar.gz'
        with tarfile.open(archive) as package:
            for name in ('frpc', 'frps'):
                member = next(item for item in package.getmembers() if item.name.endswith('/'+name))
                (binaries/name).write_bytes(package.extractfile(member).read())
                (binaries/name).chmod(0o755)
        control_port, web_port = port(), port()
        state = runtime.load_client_state(self.tmp)
        state.update(frp_server='127.0.0.1', frp_server_port=control_port, services={})
        _write_json(Path(self.tmp, 'etc/frp/client-state.json'), state)
        self.plane.conn.execute("UPDATE agent_object_catalog SET payload=? WHERE kind='service-object' AND name='web'",
            (json.dumps({'name':'web','type':'tcp','port':target_port}),))
        self.plane.conn.execute("UPDATE agent_remote_services SET endpoint_port=? WHERE name='web'",(web_port,))
        self.plane.commit_if_autonomous()
        server_config=Path(self.tmp,'fixture-frps.toml')
        server_config.write_text('bindAddr = "127.0.0.1"\nbindPort = %d\nproxyBindAddr = "127.0.0.1"\nauth.method = "token"\nauth.token = "tok"\n'%control_port)
        server_log=Path(self.tmp,'fixture-frps.log').open('w')
        client_log=Path(self.tmp,'fixture-frpc.log')
        client_output=client_log.open('w')
        server=subprocess.Popen([str(binaries/'frps'),'-c',str(server_config)],stdout=server_log,stderr=subprocess.STDOUT)
        clients=[]
        def restart(root):
            for process in clients:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
            client_output.seek(0)
            client_output.truncate()
            clients.append(subprocess.Popen([str(binaries/'frpc'),'-c',str(Path(self.tmp,'etc/frp/frpc.toml'))],stdout=client_output,stderr=subprocess.STDOUT))
        def verify(**kwargs):
            deadline=time.monotonic()+8
            names=['%s-%s'%(kwargs['host_id'],record['id']) for record in kwargs['expected'].values() if record.get('enabled',True)]
            while time.monotonic()<deadline:
                logs=client_log.read_text()
                if clients[-1].poll() is not None:
                    raise AssertionError('fixture frpc exited: '+logs)
                if 'login to server success' in logs and all('[%s] start proxy success'%name in logs for name in names):
                    return
                time.sleep(0.01)
            raise AssertionError('fixture proxy registration timed out: '+client_log.read_text())
        def fresh(endpoint):
            with socket.create_connection(('127.0.0.1',endpoint),timeout=2) as connection:
                return connection.recv(1024)
        try:
            deadline=time.monotonic()+8
            while 'frps started successfully' not in Path(self.tmp,'fixture-frps.log').read_text():
                if server.poll() is not None or time.monotonic()>deadline:
                    raise AssertionError('fixture frps did not start')
                time.sleep(0.01)
            with mock.patch('drlink_mgmt_sync.use_live_mgmt_path',return_value=False), mock.patch.object(runtime,'_restart_frpc',side_effect=restart), mock.patch.object(runtime,'verify_runtime_proxies',side_effect=verify):
                initial=runtime.apply_agent_runtime(self.plane,root=self.tmp)
                self.assertTrue(initial['ok'],initial)
                self.assertEqual(fresh(web_port),marker)
                yield port, target_port, marker, fresh
        finally:
            for process in clients+[server]:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)
            stop.set()
            thread.join(timeout=2)
            target.close()
            server_log.close()
            client_output.close()

    def test_U001_public_create_cannot_promote_proxy_omitted_by_catalog_race(self):
        with self._pinned_local_frp_fixture() as (port, _, _, fresh):
            endpoint=port()
            self.plane.conn.execute("INSERT INTO agent_object_catalog(kind,name,payload,synced_at) VALUES ('service-object','u001-ssh',?,?)",
                (json.dumps({'name':'u001-ssh','type':'tcp','port':22}),v24.utc_now_iso()))
            self.plane.commit_if_autonomous()
            apply=runtime.apply_agent_runtime
            observed=[]
            def catalog_race(plane, **kwargs):
                # A concurrent authoritative catalog refresh removes a definition
                # after setter validation but before projection. Real apply must
                # still verify the unaffected proxy and demote the omitted row.
                plane.conn.execute("DELETE FROM agent_object_catalog WHERE kind='service-object' AND name='u001-ssh'")
                plane.commit_if_autonomous()
                result=apply(plane,**kwargs)
                observed.append(result)
                return result
            with mock.patch.object(v24,'allocate_endpoint_port',return_value=endpoint), mock.patch.object(runtime,'apply_agent_runtime',side_effect=catalog_race):
                result=v24.set_remote_service_agent(self.plane,'u001-ssh-access',destination='this-host',service='u001-ssh',enabled=True,root=self.tmp)
            self.assertTrue(observed[-1]['ok'],observed)
            self.assertNotIn('rs-u001-ssh-access',runtime.load_client_state(self.tmp)['services'])
            self.assertNotIn('rs-u001-ssh-access',Path(self.tmp,'etc/frp/frpc.toml').read_text())
            with self.assertRaises(OSError):
                fresh(endpoint)
            view=result['view']
            self.assertEqual(view['endpoint_port'],endpoint)
            self.assertEqual(view['status'],'DEGRADED',v24.format_remote_service_view(view))
            self.assertNotIn('Remote Service activated',v24.format_remote_service_view(view))
            self.assertIsNone(view['connection'])
            row=self.plane.conn.execute("SELECT enabled,runtime_verified,endpoint_port FROM agent_remote_services WHERE name='u001-ssh-access'").fetchone()
            self.assertEqual(tuple(row),(1,0,endpoint))

    def test_U001_runtime_invalidation_before_final_status_write_is_not_overwritten(self):
        with self._pinned_local_frp_fixture() as (port,target_port,marker,fresh):
            endpoint=port()
            self.plane.conn.execute("INSERT INTO agent_object_catalog(kind,name,payload,synced_at) VALUES ('service-object','u001-window',?,?)",
                (json.dumps({'name':'u001-window','type':'tcp','port':target_port}),v24.utc_now_iso()))
            self.plane.commit_if_autonomous()
            verify=runtime.verified_remote_service_status
            proofs=[]
            def invalidate_after_guard(plane,name,**kwargs):
                proof=verify(plane,name,**kwargs)
                self.assertEqual(proof,('HEALTHY',''))
                self.assertEqual(fresh(endpoint),marker)
                proofs.append(proof)
                # Product runtime invalidates proof before replacing config.
                # Finish that real generation between the final read and write.
                plane.conn.execute("DELETE FROM agent_object_catalog WHERE kind='service-object' AND name='u001-window'")
                plane.commit_if_autonomous()
                applied=runtime.apply_agent_runtime(plane,root=self.tmp)
                self.assertTrue(applied['ok'],applied)
                return proof
            with mock.patch.object(v24,'allocate_endpoint_port',return_value=endpoint), \
                 mock.patch.object(runtime,'verified_remote_service_status',side_effect=invalidate_after_guard):
                result=v24.set_remote_service_agent(self.plane,'u001-window-access',destination='this-host',service='u001-window',enabled=True,root=self.tmp)
            self.assertEqual(len(proofs),1)
            with self.assertRaises(OSError):
                fresh(endpoint)
            self.assertEqual(result['view']['status'],'DEGRADED',result)
            row=self.plane.conn.execute("SELECT status,runtime_verified,enabled,endpoint_port FROM agent_remote_services WHERE name='u001-window-access'").fetchone()
            self.assertEqual(tuple(row),('DEGRADED',0,1,endpoint))

    def test_U001_management_ack_cannot_restore_health_after_generation_lost_proxy(self):
        import drlink_mgmt_sync as mgmt
        with self._pinned_local_frp_fixture() as (port,target_port,_,fresh):
            endpoint=port()
            self.plane.conn.execute("INSERT INTO agent_object_catalog(kind,name,payload,synced_at) VALUES ('service-object','u001-ack',?,?)",
                (json.dumps({'name':'u001-ack','type':'tcp','port':target_port}),v24.utc_now_iso()))
            self.plane.commit_if_autonomous()
            publication={'status':'DEGRADED','endpoint_port':endpoint}
            receipts=[]
            def upsert(**body):
                receipts.append(body['runtime_verified'])
                if body['runtime_verified']:
                    # Another reconciliation completes during this management
                    # response. Actual FRP projects the remaining valid proxy.
                    self.plane.conn.execute("DELETE FROM agent_object_catalog WHERE kind='service-object' AND name='u001-ack'")
                    self.plane.commit_if_autonomous()
                    applied=runtime.apply_agent_runtime(self.plane,root=self.tmp)
                    self.assertTrue(applied['ok'],applied)
                    publication['status']='HEALTHY'  # Stale successful response.
                return dict(publication,endpoint_host='127.0.0.1',pending_allocation=0,reason='')
            def push(plane,**kwargs):
                row=plane.conn.execute("SELECT status FROM agent_remote_services WHERE name='u001-ack-access'").fetchone()
                publication['status']=row['status']
            with mock.patch.object(mgmt,'use_live_mgmt_path',return_value=True), \
                 mock.patch.object(v24,'sync_agent_catalog_from_server'), \
                 mock.patch.object(mgmt,'upsert_remote_service_on_server',side_effect=upsert), \
                 mock.patch.object(v24,'_push_agent_remote_service_status',side_effect=push):
                result=v24.set_remote_service_agent(self.plane,'u001-ack-access',destination='this-host',service='u001-ack',enabled=True,root=self.tmp)
            self.assertEqual(receipts,[False,True])
            self.assertNotIn('rs-u001-ack-access',runtime.load_client_state(self.tmp)['services'])
            with self.assertRaises(OSError):
                fresh(endpoint)
            self.assertEqual(result['view']['status'],'DEGRADED',result)
            self.assertEqual(publication,{'status':'DEGRADED','endpoint_port':endpoint})
            self.assertNotIn('Remote Service activated',v24.format_remote_service_view(result['view']))

    def test_U001_public_healthy_create_has_proxy_and_fresh_target_traffic(self):
        with self._pinned_local_frp_fixture() as (port,target_port,marker,fresh):
            endpoint=port()
            self.plane.conn.execute("INSERT INTO agent_object_catalog(kind,name,payload,synced_at) VALUES ('service-object','u001-target',?,?)",
                (json.dumps({'name':'u001-target','type':'tcp','port':target_port}),v24.utc_now_iso()))
            self.plane.commit_if_autonomous()
            with mock.patch.object(v24,'allocate_endpoint_port',return_value=endpoint):
                result=v24.set_remote_service_agent(self.plane,'u001-access',destination='this-host',service='u001-target',enabled=True,root=self.tmp)
            self.assertEqual(result['view']['status'],'HEALTHY',result)
            self.assertIn('Remote Service activated',v24.format_remote_service_view(result['view']))
            self.assertIn('rs-u001-access',runtime.load_client_state(self.tmp)['services'])
            self.assertEqual(fresh(endpoint),marker)

    def test_F004_F017_runtime_omitted_service_cannot_be_healthy(self):
        # PASS1 F004/F017: a published row with a public port but no local
        # service object is excluded from the generated frpc proxy config.
        # A successful apply of other proxies must never mark that row HEALTHY.
        self.plane.conn.execute(
            "INSERT INTO agent_remote_services"
            "(name,destination,service_object,enabled,status,endpoint_host,endpoint_port,"
            "pending_allocation,delete_pending,pool_class,reason,updated_at) "
            "VALUES ('orphan','agent-1','absent-service-object',1,'DEGRADED',"
            "'example.test',6090,0,0,'normal','Runtime activation pending.',"
            "'2026-10-09T00:00:00Z')"
        )
        self.plane.conn.commit()
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["applied"], ["rs-web"])
        state = runtime.load_client_state(self.tmp)["services"]
        self.assertNotIn("rs-orphan", state)
        orphan = self.plane.conn.execute(
            "SELECT status,runtime_verified,reason FROM agent_remote_services "
            "WHERE name='orphan'"
        ).fetchone()
        self.assertEqual(orphan["status"], "DEGRADED", dict(orphan))
        self.assertEqual(orphan["runtime_verified"], 0, dict(orphan))
        self.assertIn("runtime proxy", orphan["reason"].lower())
        valid = self.plane.conn.execute(
            "SELECT status,runtime_verified FROM agent_remote_services "
            "WHERE name='web'"
        ).fetchone()
        self.assertEqual((valid["status"],valid["runtime_verified"]), ("HEALTHY",1))

    def test_F004_stale_port_mismatch_cannot_be_marked_verified(self):
        applied = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(applied["ok"], applied)
        self.plane.conn.execute(
            "UPDATE agent_remote_services SET endpoint_port=6091, "
            "status='HEALTHY', runtime_verified=1 WHERE name='web'"
        )
        self.plane.conn.commit()
        runtime.mark_runtime_status(self.plane, ok=True)
        row = self.plane.conn.execute(
            "SELECT status,runtime_verified FROM agent_remote_services "
            "WHERE name='web'"
        ).fetchone()
        self.assertEqual((row["status"],row["runtime_verified"]), ("DEGRADED",0))

    def test_isolated_skip_fixture_can_simulate_activation_only_with_matching_root(self):
        # The synthetic historical lifecycle suite uses explicit disposable
        # FRP_DEPLOY_TEST_ROOT + DRLINK_SKIP_ACTIVATION; it must not punch a
        # verification hole in a normal real Client process.
        for deployment_root, expected in ((self.tmp, ("HEALTHY", 1)),
                                          (self.tmp + "-wrong", ("DEGRADED", 0))):
            with self.subTest(root_matches=deployment_root == self.tmp):
                self.plane.conn.execute(
                    "UPDATE agent_remote_services SET status='DEGRADED', "
                    "reason='Runtime activation pending.', runtime_verified=0 "
                    "WHERE name='web'"
                )
                self.plane.conn.commit()
                with mock.patch.dict(os.environ, {
                    "FRP_DEPLOY_TEST_ROOT": deployment_root,
                    "DRLINK_SKIP_ACTIVATION": "1",
                }):
                    runtime.mark_runtime_status(self.plane, ok=True)
                row = self.plane.conn.execute(
                    "SELECT status,runtime_verified FROM agent_remote_services WHERE name='web'"
                ).fetchone()
                self.assertEqual((row["status"], row["runtime_verified"]), expected)

    def test_REMOTE_SERVICE_RUNTIME_APPLY(self):
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        text = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        self.assertIn("rs-web", text)
        self.assertIn("remotePort = 6010", text)
        self.assertIn("remotePort = 6003", text)  # legacy preserved
        state = json.loads(Path(self.tmp, "etc/frp/client-state.json").read_text(encoding="utf-8"))
        self.assertIn("ssh", state["services"])
        self.assertIn("rs-web", state["services"])

    def test_REMOTE_SERVICE_RUNTIME_REMOVE(self):
        runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.plane.conn.execute("DELETE FROM agent_remote_services WHERE name='web'")
        self.plane.conn.commit()
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertTrue(result["ok"], result)
        text = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        self.assertNotIn("rs-web", text)
        self.assertIn("remotePort = 6003", text)

    def test_REMOTE_SERVICE_RUNTIME_ROLLBACK(self):
        os.environ["DRLINK_FAULT_RUNTIME_CONFIG"] = "1"
        before = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        result = runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertFalse(result["ok"])
        after = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_REMOTE_SERVICE_HEALTHY_REQUIRES_RUNTIME_ACK(self):
        os.environ["DRLINK_SKIP_ACTIVATION"] = "1"
        os.environ["DRLINK_SERVER_REACHABLE"] = "1"
        os.environ["DRLINK_MGMT_MODE"] = "local"
        v24.set_service_object(self.plane, "ssh", type="tcp", port=22, oneshot=True)
        # Without skip, runtime would be required; with skip unit tests still allocate.
        # Prove production helper refuses HEALTHY language without runtime when not skipped:
        os.environ["DRLINK_SKIP_ACTIVATION"] = "0"
        # Missing usable token path already present; force verify failure.
        os.environ["DRLINK_FAULT_RUNTIME_VERIFY"] = "1"
        self.plane.conn.execute("DELETE FROM agent_remote_services")
        self.plane.conn.commit()
        # Seed catalog + create via local path
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_object_catalog(kind, name, payload, synced_at) VALUES (?,?,?,?)",
            ("service-object", "ssh", '{"name":"ssh","type":"tcp","port":22}', now),
        )
        result = v24.set_remote_service_agent(
            self.plane,
            "needs-runtime",
            destination="this-host",
            service="ssh",
            enabled=True,
            oneshot=True,
            root=self.tmp,
            server_reachable=True,
        )
        self.assertEqual(result["view"]["status"], "DEGRADED")
        self.assertNotEqual(result["view"]["status"], "HEALTHY")


class AllocatorAuthorityTests(unittest.TestCase):
    def test_policy_and_restore_project_canonical_legacy_long_identity(self):
        import drlink_runtime_policy as policy
        import drlink_upgrade_reconcile as reconcile
        name = 'c27d-f051-identical-long-service-prefix-first'
        legacy = runtime.legacy_remote_service_proxy_id(name)
        self.plane.set_published_service('agent1', name, service_type='tcp', target_mode='self',
                                         target_host='127.0.0.1', target_port=22, public_port=6007)
        publication = self.plane.conn.execute("SELECT id FROM published_services WHERE name=?", (name,)).fetchone()[0]
        self.plane.conn.execute("INSERT INTO remote_service_meta(service_id, service_object_id, runtime_proxy_id) "
                                "VALUES (?, 'fixture-service', ?)", (publication, legacy))
        self.plane.conn.commit()
        restored = reconcile.build_client_inventory_from_control_plane(self.plane)
        self.assertEqual(restored['clients']['agent1']['services'][legacy]['remote_port'], 6007)
        mapping = policy.build_proxy_map(self.plane)
        key = policy.expected_proxy_name('agent1', 'agent1', legacy)
        self.assertEqual(mapping[key]['published_id'], publication)
        self.assertEqual(mapping[key]['public_port'], 6007)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-alloc-")
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        Path(self.tmp, "etc/drlink").mkdir(parents=True)
        Path(self.tmp, "var/lib/drlink/runtime").mkdir(parents=True)
        _write_json(
            Path(self.tmp, "etc/drlink/config.json"),
            {
                "port_start": 6000,
                "port_end": 6098,
                "tcp_relay_port_start": 6200,
                "tcp_relay_port_end": 6299,
                "allocator_listen_port": 6099,
                "frp_control_listen_port": 443,
                "egress_listen_port": 6102,
                "access_plugin_addr": "127.0.0.1:6101",
            },
        )
        _write_json(
            Path(self.tmp, "var/lib/drlink/runtime/client-inventory.json"),
            {
                "schema_version": 2,
                "reserved": [],
                "clients": {
                    "legacyhost00112233445566778899aabb": {
                        "hostname": "legacy",
                        "services": {
                            "ssh": {
                                "name": "SSH",
                                "protocol": "tcp",
                                "local_ip": "127.0.0.1",
                                "local_port": 22,
                                "remote_port": 6002,
                                "preset": "ssh",
                                "enabled": True,
                                "ssh_user": "root",
                            }
                        },
                    }
                },
            },
        )
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR IGNORE INTO clients(id, label, hostname, status, trust_status, connected, "
            "row_version, created_at, updated_at) VALUES (?,?,?,?,?,?,1,?,?)",
            ("agent1", "agent1", "agent1", "connected", "trusted", 1, now, now),
        )
        self.plane.conn.commit()

    def tearDown(self):
        self.plane.close()
        os.environ.pop("FRP_DEPLOY_TEST_ROOT", None)

    def test_ALLOCATOR_SEES_LEGACY_SERVICE_PORTS(self):
        port = v24.allocate_endpoint_port(self.plane, "agent1", "new-svc", "normal")
        self.assertNotEqual(port, 6002)
        self.assertGreaterEqual(port, 6000)

    def test_ALLOCATOR_SEES_PROTECTED_PORTS(self):
        # Force only protected-adjacent free ports by marking everything used except 6099-ish
        # Protected includes 6099/443/6102/6101 — ensure allocator never returns them.
        for p in range(6000, 6099):
            if p in (6099, 443, 6101, 6102):
                continue
            self.plane.conn.execute(
                "INSERT OR REPLACE INTO port_reservations(public_port, client_id, service_id, service_name, released, created_at) "
                "VALUES (?,?,?,?,0,?)",
                (p, "agent1", "", "hold-%s" % p, v24.utc_now_iso()),
            )
        self.plane.conn.commit()
        with self.assertRaises(v24.ControlPlaneError):
            v24.allocate_endpoint_port(self.plane, "agent1", "overflow", "normal")

    def test_ALLOCATOR_SEES_OS_BOUND_PORTS(self):
        # Bind an otherwise free port and ensure allocator skips it.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 6005))
        sock.listen(1)
        try:
            # Mark 6000-6004 used so next candidate is 6005 then 6006
            for p in range(6000, 6005):
                self.plane.conn.execute(
                    "INSERT OR REPLACE INTO port_reservations(public_port, client_id, service_id, service_name, released, created_at) "
                    "VALUES (?,?,?,?,0,?)",
                    (p, "agent1", "", "hold-%s" % p, v24.utc_now_iso()),
                )
            self.plane.conn.commit()
            port = v24.allocate_endpoint_port(self.plane, "agent1", "after-bound", "normal")
            self.assertNotEqual(port, 6005)
            self.assertEqual(port, 6006)
        finally:
            sock.close()

    def test_ALLOCATOR_USES_EXISTING_REGISTRY(self):
        # Registry owns 6002; sqlite empty → must not pick 6002
        port = v24.allocate_endpoint_port(self.plane, "agent1", "reg-aware", "normal")
        self.assertNotEqual(port, 6002)

    def test_ALLOCATOR_CONCURRENT_UNIQUE_PORTS(self):
        results = []
        errors = []

        def worker(i):
            try:
                p = ControlPlane(self.tmp)
                v24.ensure_v2_schema(p.conn)
                port = v24.allocate_endpoint_port(p, "agent1", "c-%s" % i, "normal")
                results.append(port)
                p.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), len(set(results)))


class OfflineRuntimeReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-off-")
        frp = Path(self.tmp, "etc/frp")
        frp.mkdir(parents=True)
        _write_json(
            frp / "client-state.json",
            {
                "schema_version": 2,
                "allocator_url": "https://example:6099/enroll",
                "frp_server": "203.0.113.9",
                "frp_server_port": 443,
                "hostname": "agent-1",
                "machine_id": "aabbccddeeff00112233445566778899",
                "host_id": "agent-1-aabbccdd",
                "services": {},
            },
        )
        (frp / "frpc.toml").write_text(
            'serverAddr = "203.0.113.9"\nserverPort = 443\nauth.method = "token"\n'
            'auth.token = "tok"\ntransport.tls.enable = true\n',
            encoding="utf-8",
        )
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["FRP_SKIP_SYSTEMD"] = "1"
        os.environ["DRLINK_SKIP_ACTIVATION"] = "0"
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_object_catalog(kind, name, payload, synced_at) VALUES (?,?,?,?)",
            ("service-object", "http", '{"name":"http","type":"tcp","port":80}', now),
        )
        self.plane.conn.commit()

    def tearDown(self):
        self.plane.close()
        for k in ("FRP_DEPLOY_TEST_ROOT", "FRP_SKIP_SYSTEMD", "DRLINK_SKIP_ACTIVATION"):
            os.environ.pop(k, None)

    def test_REMOTE_SERVICE_OFFLINE_CREATE_RUNTIME_RECONCILE(self):
        # Offline create stores DEGRADED without endpoint → runtime must not emit proxy.
        v24.set_remote_service_agent(
            self.plane,
            "offline-new",
            destination="this-host",
            service="http",
            enabled=True,
            oneshot=True,
            root=self.tmp,
            server_reachable=False,
        )
        runtime.apply_agent_runtime(self.plane, root=self.tmp)
        text = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        self.assertNotIn("rs-offline-new", text)

    def test_REMOTE_SERVICE_DEPENDENCY_INVALIDATION_REMOVES_STALE_RUNTIME(self):
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at) "
            "VALUES ('stale','agent-1','http',1,'DEGRADED','drlink.local',6011,0,0,'normal',"
            "'Required Service Object ''http'' is missing or invalid after reconnect.',?)",
            (now,),
        )
        self.plane.conn.commit()
        # Seed a stale proxy then reconcile should drop it due to dependency reason.
        state = json.loads(Path(self.tmp, "etc/frp/client-state.json").read_text(encoding="utf-8"))
        state["services"]["rs-stale"] = {
            "id": "rs-stale",
            "local_ip": "127.0.0.1",
            "local_port": 80,
            "remote_port": 6011,
            "enabled": True,
            "v24_remote_service": True,
        }
        _write_json(Path(self.tmp, "etc/frp/client-state.json"), state)
        runtime.apply_agent_runtime(self.plane, root=self.tmp)
        text = Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8")
        self.assertNotIn("rs-stale", text)

    def test_REMOTE_SERVICE_DELETE_CLOSES_RUNTIME_PROXY(self):
        now = v24.utc_now_iso()
        self.plane.conn.execute(
            "INSERT OR REPLACE INTO agent_remote_services"
            "(name, destination, service_object, enabled, status, endpoint_host, endpoint_port, "
            "pending_allocation, delete_pending, pool_class, reason, updated_at) "
            "VALUES ('gone','agent-1','http',1,'HEALTHY','drlink.local',6012,0,0,'normal','',?)",
            (now,),
        )
        self.plane.conn.commit()
        runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertIn("rs-gone", Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8"))
        self.plane.conn.execute("DELETE FROM agent_remote_services WHERE name='gone'")
        self.plane.conn.commit()
        runtime.apply_agent_runtime(self.plane, root=self.tmp)
        self.assertNotIn("rs-gone", Path(self.tmp, "etc/frp/frpc.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
