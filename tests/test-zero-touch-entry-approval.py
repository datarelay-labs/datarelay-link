#!/usr/bin/env python3
"""Automatic first-claim enrollment: isolated allocator, real P-256 signatures."""
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
        return self.a.request_entry_registration(payload)

    def redeem(self, challenge, key=None, pub=None, machine="machine-a"):
        key = key or self.key
        pub = pub or self.pub
        payload = {"locator": self.locator, "machine_id": machine,
                   "hostname": "host-a", "public_key": pub, "nonce": challenge,
                   "timestamp": int(time.time())}
        payload["signature"] = MOD.MGMT.sign_message(
            key, MOD.ZT.entry_claim_message("redeem", payload))
        return self.a.redeem_entry_registration(payload)

    def test_real_https_route_automatic_registration_and_verified_stage(self):
        import frp_pki
        pki = frp_pki.ensure_pki(self.env.root / "pki", "127.0.0.1")
        # The real allocator serves entry + authorization. A harmless fixture
        # installer is served under the same TLS endpoint, with a real digest.
        handler = MOD.make_handler(self.a)
        payload = b'#!/bin/bash\n[[ -n "$FRP_BOOTSTRAP_LOCATOR" && -z "${FRP_BOOTSTRAP_TICKET:-}" ]] || exit 9\nprintf STAGE_VERIFIED\n'
        from unittest import mock
        artifact_root = self.env.root / "qualified-artifacts"
        agent = artifact_root / "agent"
        agent.mkdir(parents=True)
        (agent / "bootstrap-client.sh").write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        head = "a" * 40
        (artifact_root / "manifest.json").write_text(json.dumps(dict(
            drlink_version="2.4.0", frp_version="0.71.0", source_head=head,
            immutable_source_ref=head, channel="development", qualification_status="PASS",
            artifacts=[dict(artifact_type="agent-installer", platform="linux", architecture="any",
                            relative_path="agent/bootstrap-client.sh", source_head=head, sha256=digest)])))
        patch = mock.patch.object(MOD.QA, "installed_root", return_value=artifact_root)
        patch.start()
        self.addCleanup(patch.stop)
        class FixtureHandler(handler):
            def do_GET(inner):
                if inner.path == "/artifacts/agent/bootstrap-client.sh":
                    return inner._send_bootstrap_headers(200, "text/plain", payload)
                if inner.path == "/artifacts/SHA256SUMS":
                    return inner._send_bootstrap_headers(200, "text/plain",
                        hashlib.sha256(payload).hexdigest() + "  agent/bootstrap-client.sh\n")
                return super().do_GET()
        http = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(pki["server_crt"], pki["server_key"])
        http.socket = context.wrap_socket(http.socket, server_side=True)
        authority = "127.0.0.1:%s" % http.server_port
        origin = "https://" + authority
        cfg = json.loads(self.env.cfg.read_text())
        cfg.update(allocator_public_url=origin + "/enroll",
                   client_installer_url=origin + "/artifacts/agent/bootstrap-client.sh",
                   windows_client_installer_url=origin + "/artifacts/agent/bootstrap-client.ps1",
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
        self.assertEqual(call("/ZT000000")[0], 404)
        self.assertEqual(call("/" + self.locator + "?platform=windows")[0], 404)
        status, script = call("/" + self.locator)
        self.assertEqual(status, 200, script)
        self.assertIsNone(self.raw)
        self.assertNotIn(b"bt1.",script)
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
        self.assertEqual(pending["status"], "approved")
        config_path = self.env.root / "etc/drlink/config.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps(cfg))
        env = dict(os.environ, FRP_DEPLOY_TEST_ROOT=str(self.env.root), FRP_AUDIT_LOG="/audit.jsonl")
        args = ["python3", str(ROOT/"tools/frp-enrollments"), self.ticket["id"]]
        detail = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(detail.returncode, 0, detail.stderr)
        self.assertIn(self.fp, detail.stdout)
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
            cfg["bootstrap_hostname"] = "bootstrap.example.test" if platform == "macos" else ""
            cfg.pop("public_hostname", None)
            config_path.write_text(json.dumps(cfg))
            result = subprocess.run(["python3", str(ROOT/"tools/frp-create-client"),
                "--one-line","--platform",platform,"--client-name","fixture-"+platform],
                env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            pattern = (r"iex\(curl\.exe -kfsS https://" + re.escape(host) +
                       r"/([A-Za-z0-9_-]{8})\|Out-String\)" if platform == "windows" else
                       r"curl -kfsS https://" + re.escape(host) +
                       r"/([A-Za-z0-9_-]{8})\|sudo bash")
            commands = [line for line in result.stdout.splitlines() if re.fullmatch(pattern,line)]
            self.assertEqual(len(commands), 1, result.stdout)
            self.assertNotIn("bt1.", result.stdout)
            self.assertNotIn("/i/", result.stdout)
            locator = re.fullmatch(pattern,commands[0]).group(1)
            self.assertEqual(self.a._entry_active_ticket(locator)[0]["entry_approval"]["platform"],platform)
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
        status,pending=self.a.request_entry_registration(claim)
        self.assertEqual(status,200,pending)
        self.assertEqual(pending["status"],"approved")
        self.assertNotIn("enrollment_code",pending)

    def test_linux_agent_claim_and_retry_key(self):
        claim_path = self.env.root / "claim.json"
        script = """
set -euo pipefail
source lib/frp-common.sh
source lib/frp-client-common.sh
frp_client_identity_key_path() { printf '%s' "$TEST_KEY"; }
frp_entry_claim_payload request "$TEST_LOCATOR" machine-a host-a '' "$TEST_CLAIM"
"""
        env = dict(os.environ, FRP_MGMT_AUTH_PY=str(ROOT/"lib/frp_mgmt_auth.py"),
                   TEST_KEY=str(self.key), TEST_LOCATOR=self.locator, TEST_CLAIM=str(claim_path))
        first = subprocess.run(["bash","-c",script],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(first.returncode,0,first.stderr)
        claim=json.loads(claim_path.read_text())
        status,pending=self.a.request_entry_registration(claim)
        self.assertEqual(status,200,pending)
        self.assertEqual(pending["fingerprint"],self.fp)
        self.assertEqual(claim_path.stat().st_mode & 0o777,0o600)
        self.assertEqual(pending["status"], "approved")
        # The same on-disk key, not a newly generated identity, signs redemption.
        redeem_script=script.replace("request", "redeem").replace("host-a ''", 'host-a "$TEST_CHALLENGE"')
        env["TEST_CHALLENGE"]=pending["challenge"]
        again=subprocess.run(["bash","-c",redeem_script],cwd=ROOT,env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(again.returncode,0,again.stderr)
        status,result=self.a.redeem_entry_registration(json.loads(claim_path.read_text()))
        self.assertEqual(status,200,result)
        self.assertEqual(result["enrollment_code"],self.enrollment["id"]+"."+self.enrollment["secret"])

    def test_rate_limit_is_bounded_and_resets(self):
        for _ in range(60):
            self.assertFalse(self.a.entry_rate_limited("192.0.2.1",now=120))
        self.assertTrue(self.a.entry_rate_limited("192.0.2.1",now=120))
        for n in range(540):
            self.assertFalse(self.a.entry_rate_limited("source-"+str(n),now=120))
        self.assertTrue(self.a.entry_rate_limited("another",now=120))
        self.assertFalse(self.a.entry_rate_limited("another",now=180))
        self.assertEqual(len(self.a._entry_rate_sources),1)

    def test_expiry_and_paired_revocation_fail_closed(self):
        status,pending=self.request()
        self.assertEqual(status,200)
        record,path=self.a.load_enrollment(self.enrollment["id"])
        record["revoked_at"]=MOD.utc_now_iso()
        MOD.atomic_write_json(path,record,mode=0o600)
        self.assertEqual(self.request()[0],403)
        ticket,path=self.a.load_bootstrap(self.ticket["id"])
        ticket["expires_at"]=int(time.time())-1
        self.a.save_bootstrap(path,ticket)
        self.assertEqual(self.request()[0],403)
        self.assertEqual(self.redeem(pending["challenge"])[0],403)

    def test_linux_install_recovery_against_real_allocator(self):
        """Actual installer and registry transaction, isolated filesystem and FRP stub."""
        import frp_pki
        pki = frp_pki.ensure_pki(self.env.root / "install-pki", "127.0.0.1")
        http = ThreadingHTTPServer(("127.0.0.1", 0), MOD.make_handler(self.a))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(pki["server_crt"], pki["server_key"])
        http.socket = ctx.wrap_socket(http.socket, server_side=True)
        origin = "https://127.0.0.1:%d" % http.server_port
        cfg = json.loads(self.env.cfg.read_text())
        cfg.update(allocator_public_url=origin + "/enroll",
                   tls_ca_cert=str(pki["ca_crt"]), bootstrap_dir=str(self.a.bootstrap_dir))
        self.env.cfg.write_text(json.dumps(cfg))
        self.a.reload_cfg_if_changed()
        threading.Thread(target=http.serve_forever, daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        _, enrollment, ticket = self.a.issue_bootstrap_ticket([], 600, entry_platform="linux")
        client = self.env.root / "client"
        (client/"etc/frp").mkdir(parents=True)
        (client/"usr/local/bin").mkdir(parents=True)
        (client/"usr/local/lib/drlink").mkdir(parents=True)
        frpc=client/"usr/local/bin/frpc"
        frpc.write_text("#!/bin/sh\nexit 0\n")
        frpc.chmod(0o755)
        machine="aabbccddeeff00112233445566778899"
        env = dict(os.environ, FRP_CLIENT_TEST_ROOT=str(client),
                   FRP_CLIENT_LIB=str(ROOT/"lib/frp-client-common.sh"),
                   FRP_SKIP_DOWNLOAD="1", FRP_SKIP_SYSTEMD="1",
                   FRP_TEST_HOSTNAME="entry-test", FRP_TEST_MACHINE_ID=machine,
                   FRP_ALLOCATOR_URL=origin+"/enroll",
                   FRP_ALLOCATOR_CA_SHA256=pki["fingerprint"],
                   FRP_ALLOCATOR_CA_FILE=str(pki["ca_crt"]),
                   FRP_BOOTSTRAP_LOCATOR=ticket["_entry_locator"], FRP_ZERO_TOUCH="1")
        env.pop("FRP_BOOTSTRAP_TICKET",None)
        # Inject interruption after server commit. Resume must reuse local key,
        # cached authenticated response, and the original enrollment operation.
        first_env=dict(env, FRP_CLIENT_HOOK_CRASH_AFTER_ENROLL="1")
        with tempfile.TemporaryFile(mode="w+") as log:
            proc=subprocess.Popen(["bash",str(ROOT/"install-client.sh")],cwd=ROOT,
                                  env=first_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            try:
                proc.wait(timeout=35)
                log.seek(0); output=log.read()
                self.assertNotIn("Waiting for the Server operator", output)
                self.assertIn("simulated crash after enrollment commit",output)
                self.assertNotEqual(proc.returncode,0,output)
            finally:
                if proc.poll() is None:
                    proc.kill();proc.wait()
        stored_before=json.loads(self.env.registry.read_text())["clients"][machine]
        key_before=(client/"etc/frp/client-identity.key").read_bytes()
        retry=subprocess.run(["bash",str(ROOT/"install-client.sh")],cwd=ROOT,env=env,
                             stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=40)
        self.assertEqual(retry.returncode,0,retry.stdout+retry.stderr)
        self.assertEqual((client/"etc/frp/client-identity.key").read_bytes(),key_before)
        stored_after=json.loads(self.env.registry.read_text())["clients"][machine]
        self.assertEqual(stored_after.get("mgmt_fingerprint"),stored_before.get("mgmt_fingerprint"))
        self.assertEqual(stored_after.get("services"),stored_before.get("services"))
        self.assertEqual(len(json.loads(self.env.registry.read_text())["clients"]),1)

    @unittest.skipUnless(__import__("shutil").which("pwsh"), "PowerShell unavailable")
    def test_windows_install_against_real_allocator(self):
        """Actual Windows Agent modules under Linux pwsh, isolated state."""
        import frp_pki
        pki=frp_pki.ensure_pki(self.env.root/"win-pki","127.0.0.1")
        http=ThreadingHTTPServer(("127.0.0.1",0),MOD.make_handler(self.a))
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(pki["server_crt"],pki["server_key"])
        http.socket=ctx.wrap_socket(http.socket,server_side=True)
        origin="https://127.0.0.1:%d"%http.server_port
        cfg=json.loads(self.env.cfg.read_text())
        cfg.update(allocator_public_url=origin+"/enroll",tls_ca_cert=str(pki["ca_crt"]),
                   bootstrap_dir=str(self.a.bootstrap_dir))
        self.env.cfg.write_text(json.dumps(cfg))
        self.a.reload_cfg_if_changed()
        threading.Thread(target=http.serve_forever,daemon=True).start()
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        _,_,ticket=self.a.issue_bootstrap_ticket([],600,entry_platform="windows")
        client=self.env.root/"windows-client"
        env=dict(os.environ, FRP_WINDOWS_ROOT=str(client), FRP_ALLOCATOR_CA_FILE=str(pki["ca_crt"]),
                 FRP_BOOTSTRAP_LOCATOR=ticket["_entry_locator"],
                 TEST_ALLOCATOR=origin+"/enroll",TEST_CA=pki["fingerprint"])
        # Linux pwsh cannot exercise WinPS/Schannel. Use the existing explicit
        # curl transport option, still with CA and hostname validation. The
        # default .NET transport requires separate native Windows evidence.
        if os.name!="nt":
            import shutil
            binary=shutil.which("curl")
            self.assertIsNotNone(binary)
            bin_dir=self.env.root/"win-test-bin"
            bin_dir.mkdir()
            (bin_dir/"curl.exe").symlink_to(binary)
            env["PATH"]=str(bin_dir)+os.pathsep+env["PATH"]
            env["FRP_WINDOWS_FORCE_CURL"]="1"
            env.pop("FRP_WINDOWS_FORCE_DOTNET_HTTP",None)

        ps="""$ErrorActionPreference='Stop'
foreach($mod in @('FrpPaths.ps1','FrpLock.ps1','FrpCrypto.ps1','FrpTls.ps1','FrpState.ps1','FrpDraft.ps1','FrpConfig.ps1','FrpProcess.ps1','FrpShim.ps1','FrpAutostart.ps1','FrpBootstrap.ps1','FrpV24.ps1','FrpAiExecutor.ps1')) { . (Join-Path (Get-Location) ('windows/lib/'+$mod)) }
Initialize-FrpCryptoTypes
Initialize-FrpDirectories
$rc=Invoke-FrpZeroTouch -AllocatorUrl $env:TEST_ALLOCATOR -CaSha256 $env:TEST_CA -BootstrapLocator $env:FRP_BOOTSTRAP_LOCATOR -SkipStart -SkipDownload
exit $rc
"""
        with tempfile.TemporaryFile(mode="w+") as log:
            proc=subprocess.Popen(["pwsh","-NoProfile","-NonInteractive","-Command",ps],cwd=ROOT,
                                  env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            try:
                proc.wait(timeout=40)
                log.seek(0); output=log.read()
                self.assertNotIn("Waiting for the Server operator", output)
                self.assertEqual(proc.returncode,0,output)
                machine=(client/"state/client-id").read_text().strip()
                fp=MOD.MGMT.pubkey_fingerprint((client/"state/client-identity.pub").read_text())
            finally:
                if proc.poll() is None:
                    proc.kill();proc.wait()
        state=json.loads((client/"state/client-state.json").read_text())
        self.assertEqual(state["machine_id"],machine)
        registry=json.loads(self.env.registry.read_text())["clients"]
        self.assertEqual(len(registry),1)
        self.assertEqual(registry[machine]["mgmt_fingerprint"],fp)

    def test_locator_redacted_in_audit_doctor_support_receipts(self):
        import frp_audit,frp_doctor,frp_support_bundle
        for raw in ("GET /"+self.locator+" HTTP/1.1",
                    "https://remote.example/"+self.locator,
                    MOD.ZT.render_entry_command("remote.example",self.locator,"linux"),
                    MOD.ZT.render_entry_command("remote.example",self.locator,"windows"),
                    "FRP_BOOTSTRAP_LOCATOR="+self.locator):
            for redact in (MOD.ZT.redact_text,frp_doctor.redact,frp_support_bundle.redact_text,
                           lambda x:frp_audit._redact({"message":x})["message"]):
                self.assertNotIn(self.locator,redact(raw))
        for redacted in (frp_audit._redact({"locator":self.locator}),
                         frp_support_bundle.sanitize_json_value({"locator":self.locator})):
            self.assertNotIn(self.locator,json.dumps(redacted))
        self.assertIn("/enroll",frp_doctor.redact("https://remote.example/enroll"))

    def make_legacy(self):
        record, path = self.a.load_bootstrap(self.ticket["id"])
        record["entry_approval"].pop("authorization", None)
        self.a.save_bootstrap(path, record)

    def test_legacy_ticket_not_automatically_promoted(self):
        self.make_legacy()
        self.assertEqual(self.request()[0], 403)

    def test_automatic_first_claim_no_operator(self):
        status, first = self.request()
        self.assertEqual(status, 200, first)
        self.assertEqual(first["status"], "approved")
        self.assertNotIn("enrollment_code", first)
        self.assertEqual(self.request(self.other_key, self.other_pub, "machine-b")[0], 403)
        self.assertEqual(self.redeem(first["challenge"], self.other_key, self.other_pub, "machine-b")[0], 403)
        status, redeemed = self.redeem(first["challenge"])
        self.assertEqual(status, 200, redeemed)
        self.assertEqual(redeemed["enrollment_code"], self.enrollment["id"] + "." + self.enrollment["secret"])
        self.assertEqual(self.redeem(first["challenge"])[0], 403)
        status, retry = self.request()
        self.assertEqual(status, 200, retry)
        self.assertEqual(self.redeem(retry["challenge"])[0], 200)

    def test_existing_machine_key_cannot_be_replaced(self):
        # Establish an existing enrolled identity through the actual protocol.
        status, first = self.request(self.other_key, self.other_pub, "machine-a")
        self.assertEqual(status, 200)
        self.assertEqual(self.redeem(first["challenge"], self.other_key, self.other_pub, "machine-a")[0], 200)
        eid, secret = self.enrollment["id"], self.enrollment["secret"]
        payload = {"machine_id":"machine-a","hostname":"host-a","services":self.env.ssh_services(),
                   "mgmt_pubkey":self.other_pub,"mgmt_alg":MOD.MGMT.MGMT_ALG,
                   "operation_id":"b"*32}
        raw = json.dumps(payload, separators=(",",":")).encode()
        ts = str(int(time.time()))
        headers = {"X-Entry-Key-Proof": MOD.MGMT.sign_message(self.other_key, MOD.ZT.entry_enroll_message(eid, ts, raw))}
        status, result = self.a.enroll(eid, ts, MOD.hmac_hex(secret, ts + "\n" + raw.decode()), raw, headers=headers)
        self.assertEqual(status, 200, result)
        _, _, ticket = self.a.issue_bootstrap_ticket([], 600, entry_platform="linux")
        self.locator = ticket["_entry_locator"]
        self.assertEqual(self.request()[0], 403)
        self.assertEqual(self.request(self.other_key, self.other_pub, "machine-a")[0], 200)

    def test_concurrent_claim_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(self.request)
            b = pool.submit(self.request, self.other_key, self.other_pub, "machine-b")
            self.assertEqual(sorted([a.result()[0], b.result()[0]]), [200, 403])

    def test_locator_and_retired_handle_cannot_redeem(self):
        self.assertIsNone(self.raw)
        stored,_=self.a.load_bootstrap(self.ticket["id"])
        for name in ("_short_handle","short_handle_hash","bt1_wrapped","secret_hash","windows_renderer"):
            self.assertNotIn(name,stored)
        self.assertFalse((Path(self.a.bootstrap_dir)/"handles").exists())
        handle="A"*22
        self.assertFalse(self.a.short_url_bootstrap_available(handle))
        self.assertIsNone(self.a._credential_for_stage1(handle))
        for credential in ("bt1."+self.ticket["id"]+"."+"a"*64,handle,self.locator):
            body=json.dumps({"ticket":credential,"machine_id":"machine-a","hostname":"host-a"}).encode()
            self.assertEqual(self.a.redeem_bootstrap(body)[0],403)

    def test_enroll_requires_approved_key_and_signed_body(self):
        code, pending = self.request()
        self.assertEqual(code, 200)
        self.assertEqual(pending["status"], "approved")
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
        self.assertEqual(self.request()[0],403)
        self.assertEqual(self.redeem(pending["challenge"])[0], 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
