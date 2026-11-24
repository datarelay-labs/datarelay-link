#!/usr/bin/env python3
"""Test-only operator: verify a fixture Agent's locally read public key.

Never approves a key merely because it appears in a network request.
Only works on the temporary test fixture's own allocator and Agent trees.
"""
import hashlib,importlib.util,json,re,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
cfg,client=map(Path,sys.argv[1:3])
locator,machine=sys.argv[3:5]
if cfg.name!="config.json" or cfg.parent.name!="allocator" or client.parent!=cfg.parent.parent:
    raise SystemExit("isolated allocator/client fixture required")
if not re.fullmatch(r"[A-Za-z0-9_-]{6}",locator):
    raise SystemExit("invalid locator")
data=json.loads(cfg.read_text())
if Path(data["registry_file"]).parent!=cfg.parent or Path(data["token_file"]).parent!=cfg.parent:
    raise SystemExit("fixture paths must remain local")
spec=importlib.util.spec_from_file_location("fixture_allocator",ROOT/"server/frp-port-allocator.py")
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
allocator=mod.Allocator(str(cfg))
digest=hashlib.sha256(locator.encode()).hexdigest()
index=Path(allocator.bootstrap_dir)/"entry-locators"/(digest+".json")
ticket=json.loads(index.read_text())["ticket_id"]
pub=client/"etc/frp/client-identity.pub"
deadline=time.monotonic()+25
while time.monotonic()<deadline:
    record,_=allocator.load_bootstrap(ticket)
    if not record or record.get("completed_at") or record.get("revoked_at") or record.get("expires_at",0)<=time.time():
        break
    state=record["entry_approval"]
    if state.get("approved"):
        break
    if pub.is_file():
        try: fp=mod.MGMT.pubkey_fingerprint(pub.read_text())
        except Exception:
            time.sleep(.1);continue
        candidate=state["candidates"].get(fp)
        if candidate and candidate.get("machine_id")==machine:
            code,_=allocator.approve_entry_request(ticket,machine,fp)
            if code!=200: raise SystemExit("fixture approval rejected")
            break
    time.sleep(.1)
