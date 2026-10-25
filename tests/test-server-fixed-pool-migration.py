#!/usr/bin/env python3
"""Legacy FRPS allow-list migration must preserve all unrelated settings."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import frp_server_config as config


class FixedPoolMigration(unittest.TestCase):
    def migrate(self, text, start=6200, end=6299):
        return config.ensure_frps_allowed_pool(text, start, end)

    def test_legacy_pool_and_identity(self):
        before = ('bindPort = 443\n'
                  'auth.tokenSource.file.path = "/etc/frp/server_token"\n'
                  'allowPorts = [{ start = 6000, end = 6098 }] # service pool\n'
                  '[[httpPlugins]]\nname = "frp-access"\n')
        after = self.migrate(before)
        self.assertIn('{ start = 6200, end = 6299 }', after)
        self.assertEqual(after.replace(', { start = 6200, end = 6299 }', ''), before)
        self.assertEqual(self.migrate(after), after)

    def test_multiline_comments_and_custom_pool(self):
        before = 'allowPorts = [\n {start=6000,end=6007}, # ] comment\n]\nbindPort=7000\n'
        after = self.migrate(before, 6400, 6402)
        self.assertIn('{ start = 6400, end = 6402 }', after)
        self.assertIn('# ] comment', after)
        self.assertEqual(self.migrate(after, 6400, 6402), after)

    def test_existing_coverage_is_byte_identical(self):
        for text in ('allowPorts = [{start=6000,end=6500}]\n',
                     'allowPorts=[{start=6200,end=6249},{start=6250,end=6299}]\n',
                     'bindPort = 443\n', 'allowPorts=[]\n'):
            self.assertEqual(self.migrate(text), text)

    def test_unknown_or_invalid_syntax_fails_closed(self):
        for text in ('allowPorts=[{start=6000,end=6098}\n',
                     'allowPorts=[{foo=6000}]\n',
                     'allowPorts=[{start=6098,end=6000}]\n',
                     'allowPorts=[{single=0}]\n'):
            with self.assertRaises(config.ConfigError):
                self.migrate(text)
        with self.assertRaises(config.ConfigError):
            self.migrate('allowPorts=[{single=6000}]\n', 6299, 6200)


if __name__ == '__main__':
    unittest.main()
