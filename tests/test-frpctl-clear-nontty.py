#!/usr/bin/env python3
"""Public system clear must fail usefully without a TTY and work with one."""
from __future__ import annotations

import os
import pty
import select
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "frpctl"
CALL = 'source "$1"; frpctl_clear_screen'


class PublicClearTerminalTests(unittest.TestCase):
    def _env(self) -> dict[str, str]:
        return {**os.environ, "FRP_CTL_SOURCED": "1", "TERM": "unknown"}

    def test_noninteractive_clear_rejects_with_actionable_guidance(self):
        result = subprocess.run(
            ["bash", "-c", CALL, "_", str(SOURCE)],
            input=b"", capture_output=True, env=self._env(), timeout=15,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"", "do not emit escapes into captured logs")
        detail = result.stderr.decode(errors="replace")
        self.assertIn("interactive terminal", detail.lower())
        self.assertIn("system clear", detail)
        self.assertNotIn("I need something more specific", detail)

    def test_interactive_tty_clear_succeeds(self):
        env = self._env()
        env["TERM"] = "xterm"
        master, slave = pty.openpty()
        try:
            child = subprocess.Popen(
                ["bash", "-c", CALL, "_", str(SOURCE)],
                stdin=slave, stdout=slave, stderr=slave, env=env,
            )
            os.close(slave)
            slave = -1
            child.wait(timeout=15)
            chunks = []
            while select.select([master], [], [], 0.1)[0]:
                try:
                    block = os.read(master, 4096)
                except OSError:
                    break
                if not block:
                    break
                chunks.append(block)
            output = b"".join(chunks)
            self.assertEqual(child.returncode, 0, output[:200])
            self.assertIn(b"\x1b[", output, "real terminal is cleared")
        finally:
            os.close(master)
            if slave >= 0:
                os.close(slave)


if __name__ == "__main__":
    unittest.main()
