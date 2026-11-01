#!/usr/bin/env python3
"""F-027: diagnostics must name access-plugin saturation instead of a generic /healthz failure.

The access plugin shares one bounded worker budget between NewUserConn
authorization and /healthz. Under connection saturation the bounded server
answers the doctor probe with the fail-closed ``503 server busy`` response.
Diagnostics must still FAIL (new public connections are being rejected), but
it must say why, and it must surface the plugin's own error body when
/healthz itself reports an unhealthy control DB. Loopback-only fixture.
"""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import frp_doctor as doctor


def load_plugin():
    spec = importlib.util.spec_from_file_location(
        'frp_access_plugin_health_test', str(ROOT / 'server' / 'frp-access-plugin.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Health(BaseHTTPRequestHandler):
    body = {'ok': True}
    code = 200

    def do_GET(self):
        raw = json.dumps(self.body).encode()
        self.send_response(self.code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


class AccessPluginHealthDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = load_plugin()

    def serve(self, handler, slots=4):
        class FixtureServer(self.plugin.AccessServer):
            max_concurrent = slots
            request_timeout = 5.0

        server = FixtureServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def run_check(self, port):
        with tempfile.TemporaryDirectory() as root:
            report = doctor.Report()
            report.role = 'server'
            facts = {'units': {'drlink-access': {'active': 'active', 'enabled': 'enabled'}}}
            started = time.monotonic()
            doctor.check_access_control(
                report, doctor.Paths(root), facts,
                {'access_plugin_addr': '127.0.0.1:%d' % port}, {})
            elapsed = time.monotonic() - started
        return next(c for c in report.checks if c['id'] == 'access_plugin_health'), elapsed

    def test_healthy_plugin_passes(self):
        check, _ = self.run_check(self.serve(_Health))
        self.assertEqual(check['status'], doctor.PASS, check)

    def test_saturated_plugin_fails_with_named_busy_cause(self):
        port = self.serve(_Health, slots=1)
        # Occupy the only worker slot like an in-flight NewUserConn decision.
        holder = socket.create_connection(('127.0.0.1', port), timeout=5)
        self.addCleanup(holder.close)
        time.sleep(0.2)
        check, elapsed = self.run_check(port)
        self.assertEqual(check['status'], doctor.FAIL, check)
        text = ' '.join((check['message'], check['detail'], check['recommendation'])).lower()
        self.assertIn('server busy', text, check)
        self.assertIn('saturated', check['message'].lower(), check)
        self.assertIn('fail-closed', text, check)
        self.assertNotIn('authoritative access/registry state', check['recommendation'].lower(), check)
        self.assertLess(elapsed, doctor.NETWORK_TIMEOUT, 'busy reject must not wait for the probe deadline')

    def test_unhealthy_control_db_reports_plugin_error_body(self):
        class Unhealthy(_Health):
            code = 503
            body = {'ok': False, 'error': 'control DB unhealthy', 'authority': 'sqlite'}

        check, _ = self.run_check(self.serve(Unhealthy))
        self.assertEqual(check['status'], doctor.FAIL, check)
        self.assertIn('control DB unhealthy', check['message'] + ' ' + check['detail'], check)
        self.assertNotIn('saturated', check['message'].lower(), check)


if __name__ == '__main__':
    unittest.main()
