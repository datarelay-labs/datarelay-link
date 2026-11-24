#!/usr/bin/env python3
"""Regression: Real E2E harness must parse every official Windows Zero-Touch
command shape, not only the ``-Command '...'`` one.

The product intentionally prints raw PowerShell for the private-CA IP plan
(``$ErrorActionPreference=...``) and may fall back to ``-EncodedCommand``.
Before the fix the harness accepted only ``-Command`` and aborted with
"missing windows one-line command" (BUG: harness parser defect).
"""
from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "lib"))
sys.path.insert(0, str(ROOT / "lib"))
import real_e2e_windows_command as parser  # noqa: E402
import frp_zero_touch as zt  # noqa: E402

PREFIX = "powershell.exe -NoProfile -ExecutionPolicy Bypass"
SCRIPT = "$ErrorActionPreference='Stop';Write-Output 'it''s ok';exit 0"


def encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def decode(encoded: str) -> str:
    return base64.b64decode(encoded).decode("utf-16le")


def cli_output(command_line: str, eol: str = "\n") -> str:
    return eol.join([
        "Enrollment ID : abc",
        "Zero-touch Windows Agent command",
        command_line,
        "Expires : 2026-11-17T00:00:00Z",
        "",
    ])


class WindowsCommandParse(unittest.TestCase):
    def test_command_form_is_unescaped_before_encoding(self):
        quoted = "'" + SCRIPT.replace("'", "''") + "'"
        line = "%s -Command %s" % (PREFIX, quoted)
        self.assertEqual(decode(parser.extract_encoded_command(cli_output(line))), SCRIPT)

    def test_fixed_windows_entry_is_accepted(self):
        for authority in ("192.0.2.20:6099","remote.example.test"):
            script=zt.render_entry_command(authority,"A3xK9m","windows")
            self.assertEqual(decode(parser.extract_encoded_command(cli_output(script))),script)

    def test_encoded_command_form_passes_through_validated(self):
        enc = encode(SCRIPT)
        line = "%s -EncodedCommand %s" % (PREFIX, enc)
        self.assertEqual(parser.extract_encoded_command(cli_output(line)), enc)

    def test_crlf_output_does_not_leak_carriage_return(self):
        quoted = "'" + SCRIPT.replace("'", "''") + "'"
        for line in ("%s -Command %s" % (PREFIX, quoted), SCRIPT):
            with self.subTest(line=line[:24]):
                out = parser.extract_encoded_command(cli_output(line, "\r\n"))
                self.assertEqual(decode(out), SCRIPT)

    def test_unknown_or_missing_command_fails_closed(self):
        for text in (
            "",
            "Zero-touch Windows Agent command\nno command here\n",
            "%s -Command not-quoted\n" % PREFIX,
            "%s -EncodedCommand !!!not-base64!!!\n" % PREFIX,
            "%s -EncodedCommand %s\n" % (PREFIX, base64.b64encode(b"abc").decode()),
        ):
            with self.subTest(text=text[:30]):
                with self.assertRaises(SystemExit) as caught:
                    parser.extract_encoded_command(text)
                self.assertIn("windows", str(caught.exception).lower())

    def test_command_line_tool_writes_encoded_file_and_exit_code(self):
        tool = ROOT / "tests" / "lib" / "real_e2e_windows_command.py"
        with tempfile.TemporaryDirectory(prefix="drlink-win-parse-") as td:
            src, dst = Path(td) / "cli.out", Path(td) / "cmd.enc"
            src.write_text(cli_output(SCRIPT), encoding="utf-8")
            ok = subprocess.run([sys.executable, "-I", str(tool), str(src), str(dst)])
            self.assertEqual(ok.returncode, 0)
            self.assertEqual(decode(dst.read_text(encoding="ascii")), SCRIPT)
            src.write_text("nothing\n", encoding="utf-8")
            bad = subprocess.run([sys.executable, "-I", str(tool), str(src), str(dst)],
                                 capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("missing windows one-line command", bad.stderr)

    def test_harness_uses_shared_parser_not_inline_copy(self):
        text = (ROOT / "tests" / "run-real-e2e.sh").read_text(encoding="utf-8")
        self.assertIn("real_e2e_windows_command.py", text)
        self.assertNotIn('raise SystemExit("missing windows one-line command")', text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
