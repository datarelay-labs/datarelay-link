#!/usr/bin/env python3
"""Independent entry authorization: isolated allocator, real P-256 signatures."""
import importlib.util
import json
import hashlib
import os
import ssl
import subprocess
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_fixture", ROOT / "tests/test-bootstrap-ticket.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
MOD = fixture.MOD


class EntryApproval(unittest.TestCase):
    def setUp(self):
        self.env = fixture.Env()
        self.addCleanup(self.env.cleanup)
        self.a = self.env.allocator
        self.now = int(time.time())
        self.raw, self.enrollment, self.ticket = self.a.issue_bootstrap_ticket(
            self.env.ssh_services(), 600, entry_platform="linux")
        self.locator = self.ticket["_entry_locator"]
        self.key, self.pub, self.fp = self.identity("agent")
        self.other_key, self.other_pub, self.other_fp = self.identity("other")

    def identity(self, name):
        key = self.env.root / (name + ".key")
        pub = self.env.root / (name + ".pub")
        MOD.MGMT.generate_keypair(key, pub)
        pem = pub.read_text()
        return key, pem, MOD.MGMT.pubkey_fingerprint(pem)

    def request(self, key=None, pub=None, machine="machine-a", nonce=None):
        key = key or self.key
        pub = pub or self.pub
        nonce = nonce or MOD.MGMT.new_nonce()
        payload = {"locator": self.locator, "machine_id": machine,
                   "hostname": "host-a", "public_key": pub, "nonce": nonce,
                   "timestamp": int(time.time())}
        payload["signature"] = MOD.MGMT.sign_message(
            key, MOD.ZT.entry_claim_message("request", payload))
        return self.a.request_entry_approval(payload)

    def redeem(self, challenge, key=None, pub=None, machine="machine-a"):
        key = key or self.key
        pub = pub or self.pub
        payload = {"locator": self.locator, "machine_id": machine,
                   "hostname": "host-a", "public_key": pub, "nonce": challenge,
                   "timestamp": int(time.time())}
        payload["signature"] = MOD.MGMT.sign_message(
            key, MOD.ZT.entry_claim_message("redeem", payload))
        return self.a.redeem_entry_approval(payload)

    def test_real_https_route_cli_approval_and_verified_stage(self):
        import frp_pki
        pki = frp_pki.ensure_pki(self.env.root / "pki", "127.0.0.1")
        # The real allocator serves entry + authorization. A harmless fixture
        # installer is served under the same TLS endpoint, with a real digest.
        handler = MOD.make_handler(self.a)
        payload = b'#!/bin/bash\n[[ -n "$FRP_BOOTSTRAP_LOCATOR" && -z "${FRP_BOOTSTRAP_TICKET:-}" ]] || exit 9\nprintf STAGE_VERIFIED\n'
        class FixtureHandler(handler):
            def do_GET(inner):
                if inner.path == "/fixture/bootstrap-client.sh":
                    return inner._send_bootstrap_headers(200, "text/plain", payload)
                if inner.path == "/fixture/SHA256SUMS":
                    return inner._send_bootstrap_headers(200, "text/plain",
                        hashlib.sha256(payload).hexdigest() + "  bootstrap-client.sh\n")
                return super().do_GET()
        http = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(pki["server_crt"], pki["server_key"])
        http.socket = context.wrap_socket(http.socket, server_side=True)
        authority = "127.0.0.1:%s" % http.server_port
        origin = "https://" + authority
        cfg = json.loads(self.env.cfg.read_text())
        cfg.update(allocator_public_url=origin + "/enroll",
                   client_installer_url=origin + "/fixture/bootstrap-client.sh",
                   windows_client_installer_url=origin + "/fixture/bootstrap-client.ps1",
                   tls_ca_cert=str(pki["ca_crt"]), bootstrap_dir=str(self.a.bootstrap_dir))
        self.env.cfg.write_text(json.dumps(cfg))
        self.a.reload_cfg_if_changed()
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        trusted = ssl.create_default_context(cafile=str(pki["ca_crt"]))
        def call(path, body=None, ctx=trusted):
            request = urllib.request.Request(origin + path,
                data=None if body is None else json.dumps(body).encode(),
                headers={"Content-Type":"application/json"})
            try:
                with urllib.request.urlopen(request, context=ctx, timeout=5) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as exc:
                return exc.code, exc.read()
        self.assertEqual(call("/ZT0000")[0], 404)
        self.assertEqual(call("/" + self.locator + "?platform=windows")[0], 404)
        status, script = call("/" + self.locator)
        self.assertEqual(status, 200, script)
        self.assertNotIn(self.raw.encode(), script)
        self.assertNotIn(self.enrollment["secret"].encode(), script)
        self.assertIn(b"FRP_BOOTSTRAP_LOCATOR=", script)
        # Real Bash stage: no package install, just hash-verified inert script.
        stage = subprocess.run(["bash"], input=script, capture_output=True, timeout=15)
        self.assertEqual(stage.returncode, 0, stage.stderr)
        self.assertIn(b"STAGE_VERIFIED", stage.stdout)
        truncated = subprocess.run(["bash"], input=script.rsplit(b"}", 1)[0],
                                   capture_output=True, timeout=10)
        self.assertNotEqual(truncated.returncode, 0)
        self.assertNotIn(b"STAGE_VERIFIED", truncated.stdout)
        claim = {"locator":self.locator,"machine_id":"machine-a","hostname":"host-a",
                 "public_key":self.pub,"nonce":MOD.MGMT.new_nonce(),"timestamp":int(time.time())}
        claim["signature"] = MOD.MGMT.sign_message(self.key, MOD.ZT.entry_claim_message("request", claim))
        status, response = call("/bootstrap/entry/request", claim)
        self.assertEqual(status, 200, response)
        pending = json.loads(response)
        self.assertEqual(pending["status"], "pending")
        config_path = self.env.root / "etc/drlink/config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps(cfg))
        env = dict(os.environ, FRP_DEPLOY_TEST_ROOT=str(self.env.root), FRP_AUDIT_LOG="/audit.jsonl")
        args = ["python3", str(ROOT/"tools/frp-enrollments"), self.ticket["id"]]
        detail = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(detail.returncode, 0, detail.stderr)
        self.assertIn(self.fp, detail.stdout)
        approved = subprocess.run(args + ["--approve","machine-a",self.fp],
                                  env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(approved.returncode, 0, approved.stderr)
        claim["nonce"] = pending["challenge"]
        claim["signature"] = MOD.MGMT.sign_message(self.key, MOD.ZT.entry_claim_message("redeem", claim))
        status, response = call("/bootstrap/entry/redeem", claim)
        self.assertEqual(status, 200, response)
        self.assertEqual(json.loads(response)["enrollment_code"],
                         self.enrollment["id"] + "." + self.enrollment["secret"])
        self.assertEqual(call("/bootstrap/entry/redeem", claim)[0], 403)
        # Actual CLI issuance, including numeric-IP and FQDN authority and all
        # three platform selections. New public issuance must not expose bt1.
        import re
        for platform, host in (("linux", authority), ("macos", "bootstrap.example.test"), ("windows", authority)):
            cfg["bootstrap_hostname"] = host
            config_path.write_text(json.dumps(cfg))
            result = subprocess.run(["python3", str(ROOT/"tools/frp-create-client"),
                "--one-line","--platform",platform,"--client-name","fixture-"+platform],
                env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            pattern = (r"iex\(curl\.exe -kfsS https://" + re.escape(host) +
                       r"/([A-Za-z0-9_-]{6})\|Out-String\)" if platform == "windows" else
                       r"curl -kfsS https://" + re.escape(host) +
                       r"/([A-Za-z0-9_-]{6})\|sudo bash")
            commands = [line for line in result.stdout.splitlines() if re.fullmatch(pattern,line)]
            self.assertEqual(len(commands), 1, result.stdout)
            self.assertNotIn("bt1.", result.stdout)
            self.assertNotIn("/i/", result.stdout)
            locator = re.fullmatch(pattern,commands[0]).group(1)
            self.assertEqual(self.a._entry_active_ticket(locator)[0]["entry_approval"]["platform"],platform)
        self.assertIn("enrollment.entry.approved", (self.env.root/"audit.jsonl").read_text())
        # Windows entry is selected by issuance rather than query/user agent.
        _, _, win = self.a.issue_bootstrap_ticket(self.env.ssh_services(), 600, entry_platform="windows")
        status, script = call("/" + win["_entry_locator"])
        self.assertEqual(status, 200, script)
        self.assertIn(b"FRP_BOOTSTRAP_LOCATOR", script)
        self.assertNotIn(b"bt1.", script)
        self.assertIn(b"Get-FileHash", script)

    @unittest.skipUnless(__import__("shutil").which("pwsh"), "PowerShell unavailable")
    def test_windows_agent_claim_verified_by_python_allocator(self):
        ps = "$ErrorActionPreference='Stop'; . ./windows/lib/FrpCrypto.ps1; . ./windows/lib/FrpBootstrap.ps1; $id=New-FrpEcdsaIdentity; New-FrpEntryClaim -Action request -Locator " + self.locator + " -MachineId machine-win -Hostname host-win -PrivatePem $id.PrivatePem -PublicPem $id.PublicPem"
        result = subprocess.run(["pwsh","-NoProfile","-Command",ps], cwd=ROOT,
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        claim=json.loads(result.stdout)
        status,pending=self.a.request_entry_approval(claim)
        self.assertEqual(status,200,pending)
        self.assertEqual(pending["status"],"pending")
        self.assertNotIn("enrollment_code",pending)

    def test_approval_and_possession_required(self):
        code, pending = self.request()
        self.assertEqual(code, 200, pending)
        self.assertEqual(pending["status"], "pending")
        self.assertNotIn("enrollment_code", pending)
        self.assertEqual(self.redeem(pending["challenge"])[0], 403)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-a", self.fp)[0], 200)
        self.assertEqual(self.redeem(pending["challenge"], key=self.other_key)[0], 403)
        code, result = self.redeem(pending["challenge"])
        self.assertEqual(code, 200, result)
        self.assertEqual(result["enrollment_code"], self.enrollment["id"] + "." + self.enrollment["secret"])
        self.assertEqual(self.redeem(pending["challenge"])[0], 403)
        code, again = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(again["status"], "approved")
        self.assertEqual(self.redeem(again["challenge"])[0], 200)

    def test_locator_and_retired_handle_cannot_redeem(self):
        self.assertFalse(self.a.short_url_bootstrap_available(self.ticket["_short_handle"]))
        self.assertIsNone(self.a._credential_for_stage1(self.ticket["_short_handle"]))
        for credential in (self.raw, self.locator):
            body = json.dumps({"ticket":credential,"machine_id":"machine-a","hostname":"host-a"}).encode()
            self.assertEqual(self.a.redeem_bootstrap(body)[0], 403)

    def test_approval_is_exact_key_and_machine(self):
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(self.other_key, self.other_pub, "machine-b")[0], 200)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-a", self.other_fp)[0], 403)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-a", self.fp)[0], 200)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-b", self.other_fp)[0], 403)
        self.assertEqual(self.request(self.other_key, self.other_pub, "machine-b")[0], 403)

    def test_enroll_requires_approved_key_and_signed_body(self):
        code, pending = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-a", self.fp)[0], 200)
        self.assertEqual(self.redeem(pending["challenge"])[0], 200)
        eid, secret = self.enrollment["id"], self.enrollment["secret"]
        payload = {"machine_id":"machine-a","hostname":"host-a","services":self.env.ssh_services(),
                   "mgmt_pubkey":self.pub,"mgmt_alg":MOD.MGMT.MGMT_ALG,
                   "operation_id":"a"*32}
        def enroll(key=None, body=None):
            raw = json.dumps(payload, separators=(",",":")).encode() if body is None else body
            ts = str(int(time.time()))
            headers = {}
            if key:
                headers["X-Entry-Key-Proof"] = MOD.MGMT.sign_message(
                    key, MOD.ZT.entry_enroll_message(eid, ts, raw))
            sig = MOD.hmac_hex(secret, ts + "\n" + raw.decode())
            return self.a.enroll(eid, ts, sig, raw, headers=headers)
        self.assertEqual(enroll()[0], 403)
        self.assertEqual(enroll(self.other_key)[0], 403)
        code, result = enroll(self.key)
        self.assertEqual(code, 200, result)
        self.assertEqual(enroll(self.key)[0], 200)
        self.assertEqual(self.request()[0], 403)

    def test_expired_revoked_and_bad_signature(self):
        self.assertEqual(self.request(key=self.other_key)[0], 403)
        code, pending = self.request()
        self.assertEqual(code, 200)
        record, path = self.a.load_bootstrap(self.ticket["id"])
        record["revoked_at"] = MOD.utc_now_iso()
        self.a.save_bootstrap(path, record)
        self.assertEqual(self.a.approve_entry_request(self.ticket["id"], "machine-a", self.fp)[0], 403)
        self.assertEqual(self.redeem(pending["challenge"])[0], 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
