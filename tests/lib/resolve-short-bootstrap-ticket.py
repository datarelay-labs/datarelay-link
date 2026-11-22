#!/usr/bin/env python3
"""Test fixture: resolve an issued short URL to its protected internal ticket.

This script is strictly test-only; require the isolated test server tree
and the corresponding test token, and verify the wrapper and handle hash.
"""
import hashlib
import importlib.machinery
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if len(sys.argv) != 3:
    raise SystemExit("usage: resolve-short-bootstrap-ticket.py OUTPUT TEST_ROOT")
output, root = Path(sys.argv[1]), Path(sys.argv[2])
if (not root.is_dir() or root.name not in ("server-tree", "live-server")
        or not (root / "etc/drlink/config.json").is_file()):
    raise SystemExit("isolated test server tree required")
match = re.search(r"/i/([A-Za-z0-9_-]{22})(?:\\b|/|\\?)", output.read_text())
if not match:
    raise SystemExit("no short Zero-Touch handle in product output")
handle = match.group(1)
digest = hashlib.sha256(handle.encode("ascii")).hexdigest()
bootstrap = root / "var/lib/drlink/bootstrap"
index = json.loads((bootstrap / "handles" / (digest[:16] + ".json")).read_text())
if index["handle_hash"] != digest:
    raise SystemExit("handle index mismatch")
record = json.loads((bootstrap / (index["ticket_id"] + ".json")).read_text())
if record.get("short_handle_hash") != digest:
    raise SystemExit("record handle mismatch")
paths = [root / "etc/frp/server_token", bootstrap / "bt1-wrap.key"]
path = ROOT / "server/frp-port-allocator.py"
loader = importlib.machinery.SourceFileLoader("_zt_fixture_allocator", str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
for secret_path in paths:
    if not secret_path.is_file():
        continue
    token = secret_path.read_text().strip()
    ticket = module.unwrap_bootstrap_ticket(record["bt1_wrapped"], token)
    if module.bootstrap_wrap_matches_record(ticket, record):
        print(ticket)
        raise SystemExit(0)
raise SystemExit("isolated test token does not match issued ticket wrap")
