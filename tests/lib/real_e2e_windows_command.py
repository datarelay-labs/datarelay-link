#!/usr/bin/env python3
"""Turn the official Windows Zero-Touch operator command into the base64
UTF-16LE payload that the Real E2E harness feeds to ``powershell -EncodedCommand``.

Shared by tests/run-real-e2e.sh so the parser can be unit-tested.  Accepted
shapes (what ``drlink set enrollment zero-touch`` really prints):

* ``powershell.exe -NoProfile -ExecutionPolicy Bypass -Command '<script>'``
  (single quotes escaped as ``''``)
* ``powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand <b64>``
* raw script line starting with ``$ErrorActionPreference=`` (private-CA IP plan)

``--encode-file <script.ps1>`` prints the -EncodedCommand payload of a
repository script (used for the pre-enrollment probe).

Anything else fails closed with "missing windows one-line command".
"""
from __future__ import annotations

import base64
import binascii
import re
import sys

_PREFIX = r"powershell\.exe -NoProfile -ExecutionPolicy Bypass"
_COMMAND = re.compile(_PREFIX + r" -Command '(.*)'\s*$")
_ENCODED = re.compile(_PREFIX + r" -EncodedCommand ([A-Za-z0-9+/]+={0,2})\s*$")
_RAW_START = "$ErrorActionPreference="
_ERROR = "missing windows one-line command"


def _encode(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def encode_script_file(path) -> str:
    """Base64 UTF-16LE of a repository PowerShell script (for -EncodedCommand)."""
    with open(path, encoding="utf-8") as handle:
        return _encode(handle.read())


def extract_encoded_command(text: str) -> str:
    # splitlines() already removes \r\n; strip stray \r/whitespace as well so a
    # CR from an SSH/PTY transport never ends up inside the script.
    lines = [line.strip() for line in text.splitlines()]
    for line in lines:
        if line.startswith("powershell.exe -NoProfile"):
            match = _COMMAND.match(line)
            if match:
                # Official -Command quoting uses '' escapes; decode them.
                return _encode(match.group(1).replace("''", "'"))
            match = _ENCODED.match(line)
            if match:
                encoded = match.group(1)
                try:
                    decoded = base64.b64decode(encoded, validate=True)
                    decoded.decode("utf-16le")
                except (binascii.Error, UnicodeDecodeError, ValueError):
                    break
                return encoded
            break
    else:
        for line in lines:
            if line.startswith(_RAW_START):
                return _encode(line)
    raise SystemExit(_ERROR)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--encode-file":
        print(encode_script_file(argv[2]))
        return 0
    if len(argv) != 3:
        raise SystemExit("usage: real_e2e_windows_command.py <cli-output> <encoded-out>")
    with open(argv[1], encoding="utf-8") as handle:
        encoded = extract_encoded_command(handle.read())
    with open(argv[2], "w", encoding="ascii") as handle:
        handle.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
