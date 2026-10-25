#!/usr/bin/env python3
"""A public DNS alias must retain the serving Server's candidate identity."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from frp_zero_touch import render_short_url_bootstrap_script


class AliasProvenance(unittest.TestCase):
    def script(self, **overrides):
        provenance = dict(source_head='a' * 40, immutable_source_ref='a' * 40,
                          sha256='b' * 64, channel='development')
        provenance.update(overrides)
        return render_short_url_bootstrap_script(
            'https://192.0.2.10:6099/enroll', 'c' * 64, 'A' * 22,
            'https://bootstrap.example.com/artifacts/agent/bootstrap-client.sh',
            qualified_provenance=provenance)

    def run_binding(self, digest, requested=None):
        script = self.script()
        # Execute the renderer's identity gate as Bash, without downloads or
        # installation. The native install remains an independent E2E gate.
        binding = script.split('# Bind public-hostname aliases', 1)[1].split('chmod 0700', 1)[0]
        binding = '\n'.join(binding.splitlines()[1:])
        return subprocess.run(['bash', '-c', 'GOT=' + digest + '\n' + binding +
                               '\npython3 -c \'import os,json; print(json.dumps(dict(os.environ)))\''],
                              capture_output=True, text=True, env=dict(os.environ, **(requested or {})))

    def test_alias_exports_exact_qualified_source(self):
        result = self.run_binding('b' * 64)
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)
        self.assertEqual(env['FRP_EXPECTED_SOURCE_HEAD'], 'a' * 40)
        self.assertEqual(env['FRP_EXPECTED_SOURCE_REF'], 'a' * 40)
        self.assertEqual(env['FRP_BUNDLE_SHA256'], 'b' * 64)

    def test_wrong_artifact_never_adopts_qualified_identity(self):
        self.assertNotEqual(self.run_binding('d' * 64).returncode, 0)

    def test_requested_identity_is_never_overwritten_on_mismatch(self):
        for key,value in (('FRP_EXPECTED_SOURCE_HEAD','d' * 40),
                          ('FRP_EXPECTED_SOURCE_REF','d' * 40),
                          ('FRP_BUNDLE_SHA256','d' * 64),
                          ('FRP_EXPECTED_RELEASE_CHANNEL','stable')):
            with self.subTest(key=key):
                self.assertNotEqual(self.run_binding('b' * 64, {key:value}).returncode, 0)

    def test_incoherent_identity_fails_closed(self):
        for overrides in (dict(immutable_source_ref='d' * 40), dict(channel='bad'),
                          dict(source_head='main'), dict(sha256='bad')):
            with self.assertRaises(ValueError):
                self.script(**overrides)


if __name__ == '__main__':
    unittest.main()
