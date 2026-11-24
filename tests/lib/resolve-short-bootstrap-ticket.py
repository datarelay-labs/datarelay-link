#!/usr/bin/env python3
"""Resolve a public fixed locator only, within an isolated test Server tree."""
import hashlib,json,re,sys
from pathlib import Path
if len(sys.argv)!=3:
    raise SystemExit("usage: resolve-short-bootstrap-ticket.py OUTPUT TEST_ROOT")
output,root=map(Path,sys.argv[1:])
if root.name not in ("server-tree","live-server") or not (root/"etc/drlink/config.json").is_file():
    raise SystemExit("isolated test Server required")
match=re.search(r"^curl -kfsS https://[^/\s]+/([A-Za-z0-9_-]{6})\|sudo bash$",output.read_text(),re.M)
if not match:
    raise SystemExit("fixed entry missing")
locator=match.group(1)
digest=hashlib.sha256(locator.encode()).hexdigest()
base=root/"var/lib/drlink/bootstrap"
index=json.loads((base/"entry-locators"/(digest+".json")).read_text())
record=json.loads((base/(index["ticket_id"]+".json")).read_text())
assert record["entry_locator_hash"]==digest
assert "bt1_wrapped" not in record
print(locator)
