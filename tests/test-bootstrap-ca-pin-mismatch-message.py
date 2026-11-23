#!/usr/bin/env python3
"""F-005 regression: a wrong CA SHA256 pin must fail loudly.

The pin shell aborts (set -e) when the fetched CA fingerprint differs from the
operator's pin. It used to exit rc=1 with no output, so operators could not
tell why the bootstrap did nothing. The abort must stay (no installer runs)
but must print an actionable error that names the mismatch.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_zero_touch as zt


def _fake_bin(tmp: Path) -> Path:
    """curl/openssl stubs so the generated shell runs offline."""
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "curl").write_text(
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do [ \"$1\" = -o ] && { out=$2; shift; }; shift; done\n"
        "echo cert > \"$out\"\n",
        encoding="utf-8",
    )
    (bindir / "openssl").write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  x509) while [ $# -gt 0 ]; do [ \"$1\" = -out ] && { echo der > \"$2\"; }; shift; done ;;\n"
        "  dgst) echo 'SHA2-256(stdin)= %s' ;;\n"
        "esac\n" % ("ab" * 32),
        encoding="utf-8",
    )
    for f in bindir.iterdir():
        f.chmod(0o755)
    return bindir


class CaPinMismatchMessage(unittest.TestCase):
    def _run(self, pin: str):
        tmp = Path(tempfile.mkdtemp(prefix="drlink-pin-"))
        bindir = _fake_bin(tmp)
        shell = zt._private_ca_pin_shell("https://203.0.113.10:8443", pin) + "echo PIN_OK"
        return subprocess.run(
            ["bash", "-c", shell],
            env={"PATH": "%s:/usr/bin:/bin" % bindir},
            capture_output=True,
            text=True,
        )

    def test_mismatch_aborts_with_message(self):
        res = self._run("cd" * 32)
        self.assertNotEqual(res.returncode, 0)
        self.assertNotIn("PIN_OK", res.stdout)
        self.assertIn("fingerprint", (res.stderr + res.stdout).lower())
        self.assertIn("mismatch", (res.stderr + res.stdout).lower())

    def test_match_continues(self):
        res = self._run("ab" * 32)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("PIN_OK", res.stdout)


if __name__ == "__main__":
    unittest.main()
