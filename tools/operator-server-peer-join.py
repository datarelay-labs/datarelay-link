#!/usr/bin/env python3
"""One-shot authorized dev DRLink Server Peer enrollment and installation.

Run directly in an SSH TTY with sudo AFTER the central operator has issued a
one-use *manual*, management-only Enrollment Code. Never echo/paste secrets
into ChatGPT, shell arguments, process environment or Git.

This helper prompts privately, uses a 0700 temporary directory (code file 0600),
and removes the temporary secret on exit. It never installs an Agent, changes
FRP port 443, or reconfigures existing MCP/Server services.
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
from pathlib import Path
import re
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOURCE / "lib"))

import drlink_server_peer as peer
import drlink_server_peer_enroll as enrollment

MODULE_PATH = SOURCE / "tools/operator-server-peer.py"
SPEC = importlib.util.spec_from_file_location("server_peer_deployer", MODULE_PATH)
assert SPEC and SPEC.loader
deployer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployer)

CODE_RE = re.compile(r"^[0-9a-fA-F]{16}\.[0-9a-fA-F]{64}$")
SECRET_TEMP_PARENT = Path("/root")


def _save_code(code: str, target: Path) -> None:
    if not CODE_RE.fullmatch(code):
        raise peer.ServerPeerDenied("Manual Enrollment Code format invalid")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        data = (code + "\n").encode("ascii")
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def join(expected_head: str, *, central: str = "https://remote.xdr.ooo",
         label: str = "dev-drlink Server") -> None:
    if os.geteuid() != 0:
        raise peer.ServerPeerDenied("Root SSH operator access is required")
    # Confirm immutable code before reading or accepting any credentials.
    deployer.code_matches_head(expected_head)
    if deployer.UNIT.exists():
        # An already installed Peer is verified rather than re-enrolled.
        deployer.verify()
        print("SERVER_PEER_ALREADY_INSTALLED=PASS")
        return
    try:
        peer.validate_peer_root(str(deployer.ROOT))
        enrolled = True
    except peer.ServerPeerDenied:
        if deployer.ROOT.exists():
            # Existing partial enrollment may legitimately have only a pending
            # state. Do not delete it. The original code is required for
            # exact identity replay.
            if (deployer.ROOT / "server-peer.json").exists():
                raise
        enrolled = False
    if not enrolled:
        if not sys.stdin.isatty():
            raise peer.ServerPeerDenied("An interactive SSH terminal is required for private code entry")
        code = getpass.getpass("Enter the one-time central DRLink Manual Enrollment Code: ")
        try:
            with tempfile.TemporaryDirectory(
                prefix=".server-peer-code-", dir=str(SECRET_TEMP_PARENT)
            ) as directory:
                temp = Path(directory) / "enrollment.code"
                _save_code(code.strip(), temp)
                code = ""  # Do not retain a second string reference intentionally.
                enrollment.enroll(
                    root=str(deployer.ROOT), central=central, label=label,
                    code_file=str(temp),
                )
        finally:
            code = ""
        print("SERVER_PEER_ENROLLED=PASS")
    deployer.apply(expected_head)
    deployer.verify()
    print("SERVER_PEER_CHATGPT_REGISTRATION=READY_FOR_CENTRAL_AI_ACCESS")
    print("SERVER_PEER_AGENT_INSTALLED=NO")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DRLink Server Peer secure SSH join")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--central", default="https://remote.xdr.ooo")
    parser.add_argument("--label", default="dev-drlink Server")
    opts = parser.parse_args(argv)
    try:
        join(opts.expected_head, central=opts.central, label=opts.label)
    except (peer.ServerPeerDenied, RuntimeError, OSError, ValueError) as exc:
        print("SERVER_PEER_JOIN=DENY: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
