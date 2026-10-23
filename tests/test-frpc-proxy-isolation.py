#!/usr/bin/env python3
"""Process-level regression: unrelated proxy edits preserve live children."""
import os
import json
import time
from unittest.mock import patch
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from drlink_frpc_supervisor import Supervisor, split_config, live_status, private_write

HEADER='serverAddr = "localhost"\nauth.token = "test-only"\n'
def proxy(name, port):
    return '\n[[proxies]]\nname = "%s"\ntype = "tcp"\nlocalPort = 1\nremotePort = %d\n' % (name, port)

class Isolation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.config=self.root/'frpc.toml'
        # A genuine long-lived child, not a mocked restart counter.
        self.binary=self.root/'child'
        self.binary.write_text('#!/usr/bin/env python3\nimport time\nprint("login to server success",flush=True)\ntime.sleep(60)\n')
        self.binary.chmod(0o700)
        self.s=Supervisor(self.config, self.root/'runtime', str(self.binary));self.addCleanup(self.s.close)
    def apply(self, text):
        self.config.write_text(text);self.s.reconcile()
    def test_unrelated_create_disable_enable_delete_keeps_original_pid(self):
        base=HEADER+proxy('original',6000); self.apply(base)
        pid=self.s.children['original'].process.pid
        for text in (base+proxy('second',6001),base,base+proxy('second',6001),base):
            self.apply(text)
            self.assertEqual(self.s.children['original'].process.pid,pid)
            self.assertIsNone(self.s.children['original'].process.poll())
    def test_edit_restarts_only_edited_proxy_and_rollback_preserves_other(self):
        base=HEADER+proxy('a',6000)+proxy('b',6001);self.apply(base)
        a=self.s.children['a'].process.pid;b=self.s.children['b'].process.pid
        self.apply(HEADER+proxy('a',6000)+proxy('b',6002))
        self.assertEqual(self.s.children['a'].process.pid,a)
        self.assertNotEqual(self.s.children['b'].process.pid,b)
        self.apply(base);self.assertEqual(self.s.children['a'].process.pid,a)
    def test_common_change_replaces_all(self):
        self.apply(HEADER+proxy('a',6000));old=self.s.children['a'].process.pid
        self.apply(HEADER.replace('localhost','127.0.0.1')+proxy('a',6000))
        self.assertNotEqual(self.s.children['a'].process.pid,old)
    def test_invalid_duplicate_preserves_generation(self):
        self.apply(HEADER+proxy('a',6000));pid=self.s.children['a'].process.pid
        self.config.write_text(HEADER+proxy('a',6000)+proxy('a',6001))
        with self.assertRaises(ValueError):self.s.reconcile()
        self.assertEqual(self.s.children['a'].process.pid,pid)
    def test_private_configs_and_dead_child_not_ready(self):
        self.apply(HEADER+proxy('a',6000))
        self.assertEqual(self.s.directory.stat().st_mode&0o777,0o700)
        for p in self.s.directory.glob('*.toml'):self.assertEqual(p.stat().st_mode&0o777,0o600)
        c=self.s.children['a'];c.connected=True;c.ready=True
        c.process.terminate();c.process.wait(timeout=3)
        self.assertFalse(self.s.snapshot()['children']['a']['ready'])

    def test_connection_epochs_are_independent_and_fail_closed(self):
        self.apply(HEADER+proxy('a',6000)+proxy('b',6001))
        a=self.s.children['a'];b=self.s.children['b']
        a.consume(b'login to server success\n[a] start proxy success\n')
        b.consume(b'login to server success\n[b] start proxy success\n')
        self.assertTrue(a.ready and b.ready)
        b.consume(b'session closed\n')
        self.assertTrue(a.ready);self.assertFalse(b.ready)
        b.consume(b'[b] start proxy success\n')
        self.assertFalse(b.ready)
    def test_live_proof_rejects_stale_wrong_config_dead_and_wrong_parent(self):
        # Test the actual /proc binding, not a fake active-service bit.
        self.s.directory=self.root/'runtime-proxies';self.s.directory.mkdir(mode=0o700)
        self.apply(HEADER+proxy('a',6000))
        c=self.s.children['a'];c.connected=True;c.ready=True
        with patch.dict(os.environ,{'INVOCATION_ID':'a'*32}):snap=self.s.snapshot()
        status=self.s.directory/'status.json'
        private_write(status,json.dumps(snap));self.assertIsNotNone(live_status(self.config,'a'*32))
        for key,value in [('updated',time.time()-5),('config_hash','wrong'),('start','wrong')]:
            bad=dict(snap);bad[key]=value;private_write(status,json.dumps(bad))
            self.assertIsNone(live_status(self.config,'a'*32))
        private_write(status,json.dumps(snap));status.chmod(0o644)
        self.assertIsNone(live_status(self.config,'a'*32));status.chmod(0o600)
        c.process.terminate();c.process.wait(timeout=3)
        self.assertIsNone(live_status(self.config,'a'*32))

if __name__=='__main__':unittest.main()
