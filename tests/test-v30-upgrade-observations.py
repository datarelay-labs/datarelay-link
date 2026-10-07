#!/usr/bin/env python3
from __future__ import annotations
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "lib")); sys.path.insert(0,str(ROOT / "tests/lib"))
from drlink_control_db import open_control_db
from v30_upgrade_observations import TABLE_COLUMNS, V30_TABLES, collect, compare, verify_runtime, verify_evidence


class UpgradeObservationTests(unittest.TestCase):
    def baseline(self):
        return {"schema_version":1,"integrity":"ok","v30_tables_present":sorted(V30_TABLES),
                "tables":{name:{"count":1,"sha256":hashlib.sha256(name.encode()).hexdigest()} for name in TABLE_COLUMNS}}

    def test_nonempty_unchanged_baseline_passes(self):
        b=self.baseline(); result=compare(b,copy.deepcopy(b))
        self.assertEqual([result[k] for k in ("managed_hosts","policy","control_db")],["PASS"]*3)

    def test_empty_hosts_or_services_never_prove_preservation(self):
        for name in ("clients","published_services"):
            b=self.baseline();b["tables"][name]["count"]=0
            self.assertEqual(compare(b,copy.deepcopy(b))["managed_hosts"],"BLOCKED")

    def test_changed_policy_or_port_is_rejected(self):
        for name,key in (("policy_rules","policy"),("published_services","managed_hosts"),("client_tags","managed_hosts")):
            b=self.baseline();a=copy.deepcopy(b);a["tables"][name]["sha256"]="0"*64
            self.assertEqual(compare(b,a)[key],"FAIL")

    def test_missing_tables_or_empty_policy_never_pass(self):
        b=self.baseline();a=copy.deepcopy(b);a["v30_tables_present"]=[]
        self.assertEqual(compare(b,a)["control_db"],"FAIL")
        b["tables"]["policy_rules"]["count"]=0
        self.assertEqual(compare(b,copy.deepcopy(b))["policy"],"BLOCKED")
        del a["tables"]["clients"]
        with self.assertRaises(ValueError):compare(b,a)

    def test_runtime_requires_exact_observed_version_and_source(self):
        sha="a"*40;text="Data Relay Link: 3.0.0-dev+gaaaaaaa\nSource HEAD: "+sha+"\n"
        verify_runtime(text,sha,"3.0.0")
        for bad in (text.replace(sha,"unknown"),text.replace("3.0.0","2.4.0"),text+"Source HEAD: "+sha+"\n"):
            with self.assertRaises(ValueError):verify_runtime(bad,sha,"3.0.0")

    def retained(self, tmp):
        root=Path(tmp); baseline=self.baseline(); prior="b"*40; candidate="a"*40
        files={
            "before-state.json":json.dumps(baseline), "after-state.json":json.dumps(baseline),
            "reboot-state.json":json.dumps(baseline),
            "v240-version.txt":"Data Relay Link: 2.4.0\nChannel: stable\nSource HEAD: "+prior+"\n",
            "v300-health.txt":"Data Relay Link: 3.0.0-dev+gaaaaaaa\nSource HEAD: "+candidate+"\n",
            "reboot-health.txt":"Data Relay Link: 3.0.0-dev+gaaaaaaa\nSource HEAD: "+candidate+"\n",
            "boot-before.txt":"00000000-0000-0000-0000-000000000001\n",
            "boot-after.txt":"00000000-0000-0000-0000-000000000002\n",
        }
        for name,text in files.items():(root/name).write_text(text)
        return {"evidence_root":tmp,"prior_source_head":prior,"source_head":candidate,
                "prior_channel":"stable","baseline_release_qualified":True,
                "observations":{n:hashlib.sha256(t.encode()).hexdigest() for n,t in files.items()}}

    def test_retained_evidence_verifies_observations_not_pass_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.retained(tmp);verify_evidence(doc)
            (Path(tmp)/"after-state.json").write_text('{}')
            with self.assertRaisesRegex(ValueError,"digest mismatch"):verify_evidence(doc)
        with self.assertRaises(ValueError):verify_evidence({"final_status":"PASS"})

    def test_development_baseline_rejected_for_stable_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.retained(tmp);doc["prior_channel"]="development";doc["baseline_release_qualified"]=False
            with self.assertRaisesRegex(ValueError,"prior-stable"):verify_evidence(doc)

    def test_matching_hashes_cannot_make_empty_inventory_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.retained(tmp)
            for name in ("before-state.json","after-state.json","reboot-state.json"):
                data=self.baseline();data["tables"]["clients"]["count"]=0
                text=json.dumps(data);(Path(tmp)/name).write_text(text)
                doc["observations"][name]=hashlib.sha256(text.encode()).hexdigest()
            with self.assertRaisesRegex(ValueError,"not proven"):verify_evidence(doc)

    def test_reboot_and_symlink_observations_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc=self.retained(tmp)
            p=Path(tmp)/"boot-after.txt";p.write_text((Path(tmp)/"boot-before.txt").read_text())
            doc["observations"][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,"did not change"):verify_evidence(doc)
            p.unlink();p.symlink_to(Path(tmp)/"boot-before.txt")
            with self.assertRaisesRegex(ValueError,"unsafe"):verify_evidence(doc)

    def test_collect_readonly_hashes_no_raw_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=open_control_db(tmp)
            c.execute("INSERT INTO clients(id,label,hostname,created_at,updated_at) VALUES ('private-host','private-label','private-name','t','t')")
            c.commit();c.close()
            db=Path(tmp)/"var/lib/drlink/drlink.db";original=db.read_bytes()
            snapshot=collect(tmp)
            self.assertEqual(snapshot["tables"]["clients"]["count"],1)
            self.assertNotIn("private-host",json.dumps(snapshot));self.assertNotIn("private-label",json.dumps(snapshot))
            self.assertEqual(db.read_bytes(),original)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sqlite3.OperationalError):collect(tmp)
            self.assertFalse((Path(tmp)/"var/lib/drlink/drlink.db").exists())


if __name__ == "__main__":unittest.main()
