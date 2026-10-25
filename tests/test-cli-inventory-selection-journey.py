#!/usr/bin/env python3
"""Public CLI inventory discovery -> selector -> detail journey contract.

The operator learns a name/ID from public show output, never from the DB.
"""
from __future__ import annotations
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LIB=ROOT/"lib"
if not LIB.is_dir():
    LIB=Path("/usr/local/lib/drlink")
sys.path.insert(0,str(LIB))
from drlink_control_plane import ControlPlane, ControlPlaneError
import drlink_v24 as v24
import drlink_v24_cli as cli

class InventoryJourney(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory(prefix="drlink-inventory-journey-")
        self.addCleanup(self.root.cleanup)
        self.saved={key:os.environ.get(key) for key in ("FRP_DEPLOY_TEST_ROOT","DRLINK_SKIP_ACTIVATION","DRLINK_CONFIRM")}
        self.addCleanup(self.restore)
        os.environ["FRP_DEPLOY_TEST_ROOT"]=self.root.name
        os.environ["DRLINK_SKIP_ACTIVATION"]="1"
        os.environ["DRLINK_CONFIRM"]="yes"
        folder=Path(self.root.name)/"etc/drlink"
        folder.mkdir(parents=True)
        (folder/"config.json").write_text(json.dumps({"role":"server"})+"\n")
        self.plane=ControlPlane(self.root.name)
        self.addCleanup(self.plane.close)
        v24.ensure_v2_schema(self.plane.conn)

    def restore(self):
        for key,value in self.saved.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value

    def output(self,*args):
        buf=io.StringIO()
        with redirect_stdout(buf):
            rc=cli.handle_show(self.plane,list(args))
        self.assertEqual(rc,0,args)
        return buf.getvalue()

    def test_six_object_collections_roundtrip(self):
        v24.set_network_object(self.plane,"lab-ip",type="ip",value="192.0.2.10",oneshot=True)
        v24.set_network_group(self.plane,"lab-net-group",members=["lab-ip"],oneshot=True)
        v24.set_service_object(self.plane,"lab-ssh",type="tcp",port=2222,oneshot=True)
        v24.set_service_group(self.plane,"lab-svc-group",members=["lab-ssh"],oneshot=True)
        v24.set_permission_object(self.plane,"lab-perm",permissions=["host-info"],oneshot=True)
        v24.set_permission_group(self.plane,"lab-perm-group",members=["lab-perm"],oneshot=True)
        pairs=[
            ("network-objects","network-object","lab-ip","Network Object:"),
            ("network-groups","network-group","lab-net-group","Network Group:"),
            ("service-objects","service-object","lab-ssh","Service Object:"),
            ("service-groups","service-group","lab-svc-group","Service Group:"),
            ("permission-objects","permission-object","lab-perm","Permission Object:"),
            ("permission-groups","permission-group","lab-perm-group","Permission Group:"),
        ]
        for collection,single,name,heading in pairs:
            with self.subTest(collection=collection):
                listing=self.output(collection)
                self.assertIn(name,listing)
                details=self.output(single,name)
                self.assertIn(heading+" "+name,details)

    def test_missing_selector_explains_where_to_find_it(self):
        for singular,plural in (
            ("network-object","network-objects"),
            ("network-group","network-groups"),
            ("service-object","service-objects"),
            ("service-group","service-groups"),
            ("permission-object","permission-objects"),
            ("permission-group","permission-groups"),
            ("enrollment","enrollments"),
            ("ai-identity","ai-identities"),
        ):
            with self.subTest(singular=singular):
                with self.assertRaises(ControlPlaneError) as err:
                    cli.handle_show(self.plane,[singular])
                self.assertIn("show "+plural,str(err.exception))

    def test_managed_host_id_is_the_first_selector_even_with_spaces(self):
        mid="abcdef0123456789abcdef0123456789"
        self.plane.upsert_client(mid,label="Example Office Gateway",hostname="lab-agent",connected=True)
        listing=self.output("managed-hosts")
        self.assertIn("HOST ID",listing)
        selector=next(line for line in listing.splitlines() if line.startswith(mid)).split()[0]
        self.assertEqual(selector,mid)
        self.assertIn("Host ID: "+mid,self.output("managed-host",selector))
        self.assertIn("remote-services",self.output("managed-host",selector))
        with self.assertRaises(ControlPlaneError) as err:
            cli.handle_show(self.plane,["managed-host"])
        self.assertIn("show managed-hosts",str(err.exception))

    def test_agent_target_mismatch_gives_repair_commands(self):
        """DEGRADED is actionable rather than just an unexplained status."""
        agent_dir=tempfile.TemporaryDirectory(prefix="drlink-target-journey-")
        self.addCleanup(agent_dir.cleanup)
        root=agent_dir.name
        (Path(root)/"etc/drlink").mkdir(parents=True)
        (Path(root)/"etc/drlink/config.json").write_text('{"role":"agent"}\\n')
        (Path(root)/"etc/frp").mkdir(parents=True)
        (Path(root)/"etc/frp/client-state.json").write_text(
            json.dumps({"hostname":"lab-agent", "machine_id":"a"*32, "services":{}})+"\\n")
        ap=ControlPlane(root)
        self.addCleanup(ap.close)
        v24.ensure_v2_schema(ap.conn)
        ap.conn.execute(
            "INSERT INTO agent_remote_services "
            "(name,destination,service_object,enabled,status,endpoint_host,"
            "endpoint_port,pending_allocation,delete_pending,pool_class,reason,updated_at)"
            " VALUES(?,?,?,1,'DEGRADED',?,6001,0,0,'normal',?,?)",
            ("aio-ssh", "lab-agent", "ssh", "203.0.113.10",
             "Published target_host diverges from authoritative destination reference "
             "(10.22.33.44 != 127.0.0.1).", "2026-01-01T00:00:00Z"))
        ap.conn.commit()
        output=io.StringIO()
        previous=os.environ.get("FRP_DEPLOY_TEST_ROOT")
        os.environ["FRP_DEPLOY_TEST_ROOT"]=root
        try:
            with redirect_stdout(output):
                self.assertEqual(cli.handle_show(ap,["remote-service","aio-ssh"]),0)
        finally:
            if previous is None: os.environ.pop("FRP_DEPLOY_TEST_ROOT",None)
            else: os.environ["FRP_DEPLOY_TEST_ROOT"]=previous
        text=output.getvalue()
        self.assertIn("DEGRADED",text)
        self.assertIn("On Server: define a Network Object",text)
        self.assertIn(
            "set remote-service aio-ssh destination <NETWORK-OBJECT> service ssh enabled",
            text)
        self.assertIn("Then verify:",text)

if __name__=="__main__":
    unittest.main(verbosity=2)
