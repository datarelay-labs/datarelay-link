#!/usr/bin/env python3
"""Doctor must compare the generated proxy identity, never service substrings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import frp_doctor as doctor
import drlink_v24_runtime as runtime

class ProxyIdentityTests(unittest.TestCase):
    def check(self, services, rendered=None, host_id='fixture-host'):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root, 'etc/frp'); base.mkdir(parents=True)
            state = {'schema_version': 1, 'host_id': host_id, 'hostname': 'fixture',
                     'machine_id': '1234567890', 'services': services}
            base.joinpath('client-state.json').write_text(json.dumps(state))
            base.joinpath('frpc.toml').write_text(rendered if rendered is not None else
                runtime.render_frpc_toml_text(server='203.0.113.1', server_port=443,
                    token='fixture', host_id=host_id or 'fixture-12345678', services=services))
            report = doctor.Report(); report.role = 'client'
            doctor.check_client(report, doctor.Paths(root), {}, True)
            return next(c for c in report.checks if c['id'] == 'frpc_config')

    def test_http_https_prefixes_do_not_report_false_port_drift(self):
        services = {'rs-web-http': {'remote_port': 6000, 'local_port': 8080},
                    'rs-web-https': {'remote_port': 6001, 'local_port': 8443}}
        self.assertEqual(self.check(services)['status'], doctor.PASS)
        self.assertEqual(self.check(services, host_id='')['status'], doctor.PASS)

    def test_disabled_prefix_is_not_enabled_by_another_proxy(self):
        services = {'rs-web': {'enabled': False, 'remote_port': 6000, 'local_port': 80},
                    'rs-web-api': {'remote_port': 6001, 'local_port': 8080}}
        self.assertEqual(self.check(services)['status'], doctor.PASS)

    def test_wrong_port_and_missing_exact_proxy_still_fail(self):
        services = {'ssh': {'remote_port': 6000, 'local_port': 22},
                    'extra-ssh': {'remote_port': 6001, 'local_port': 22}}
        text = runtime.render_frpc_toml_text(server='203.0.113.1', server_port=443,
            token='fixture', host_id='fixture-host', services=services)
        self.assertEqual(self.check(services, text.replace('remotePort = 6000', 'remotePort = 6999'))['status'], doctor.FAIL)
        self.assertEqual(self.check(services, text.replace('name = "fixture-host-ssh"', 'name = "other-host-ssh"'))['status'], doctor.FAIL)
        self.assertEqual(self.check(services, text.replace('remotePort = 6000', '# missing remote port'))['status'], doctor.FAIL)

    def test_disabled_exact_proxy_still_warns(self):
        services = {'web': {'id': 'rs-web', 'remote_port': 6000, 'local_port': 80}}
        text = runtime.render_frpc_toml_text(server='203.0.113.1', server_port=443,
            token='fixture', host_id='fixture-host', services=services)
        services['web']['enabled'] = False
        self.assertEqual(self.check(services, text)['status'], doctor.WARN)

if __name__ == '__main__': unittest.main()
