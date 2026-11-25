#!/usr/bin/env python3
"""Fresh client with no private CA must still run the advertised Zero-Touch line.

Stock TLS verification fails when the enrollment host
presents the project private CA. The advertised command has to succeed on that
same client via the approved initial -k; subsequent downloads verify TLS.
"""
from __future__ import annotations

import hashlib
import json
import shlex
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import frp_zero_touch as zt  # noqa: E402

TICKET = "A3xK9mP2"


def _openssl(args, **kwargs):
    subprocess.run(
        ["openssl", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **kwargs,
    )


def _make_ca_and_leaf(directory: Path):
    ca_key = directory / "ca.key"
    ca_crt = directory / "ca.crt"
    server_key = directory / "server.key"
    server_csr = directory / "server.csr"
    server_crt = directory / "server.crt"
    ext = directory / "san.cnf"
    _openssl(
        [
            "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(ca_key), "-out", str(ca_crt),
            "-days", "2", "-subj", "/CN=drlink-fresh-client-ca",
        ]
    )
    _openssl(
        [
            "req", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(server_key), "-out", str(server_csr),
            "-subj", "/CN=127.0.0.1",
        ]
    )
    ext.write_text("subjectAltName=IP:127.0.0.1\n", encoding="utf-8")
    _openssl(
        [
            "x509", "-req", "-in", str(server_csr),
            "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
            "-out", str(server_crt), "-days", "2", "-extfile", str(ext),
        ]
    )
    return ca_crt.read_text(encoding="utf-8"), server_crt, server_key


def _free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _verify_orphan_allocator_ca_recovery(tmp, origin, installer_url, installer, ca_pem):
    """Exercise the actual installer helpers against qualified HTTPS metadata."""
    old_key = tmp / "old-ca.key"
    old_ca = tmp / "old-ca.crt"
    _openssl([
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(old_key), "-out", str(old_ca),
        "-days", "2", "-subj", "/CN=old-unclaimed-drlink-ca",
    ])
    new_ca = tmp / "replacement-ca.crt"
    new_ca.write_text(ca_pem, encoding="utf-8")
    bundle = tmp / "qualified-agent.sh"
    bundle.write_text(installer, encoding="utf-8")
    expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca_pem)).hexdigest()
    scenarios = (
        ("orphan", None, {}, True),
        ("corrupt-orphan", None, {}, True),
        ("committed", "etc/frp/client-state.json", {}, False),
        ("pending", "etc/frp/enroll-pending.json", {}, False),
        ("identity", "etc/frp/client-identity.key", {}, False),
        ("server", "etc/drlink/config.json", {}, False),
        ("runtime", "usr/local/bin/drlink", {}, False),
        ("unknown", "etc/drlink/.unknown", {}, False),
        ("symlink", None, {}, False),
        ("bad-pin", None, {"FRP_ALLOCATOR_CA_SHA256": "a" * 64}, False),
        ("bad-source", None, {"FRP_EXPECTED_SOURCE_REF": "c" * 40}, False),
    )
    for name, marker, overrides, success in scenarios:
        root = tmp / ("case-" + name)
        ca = root / "etc/drlink/allocator-ca.crt"
        ca.parent.mkdir(parents=True)
        machine_id = root / "etc/frp/client-id"
        machine_id.parent.mkdir(parents=True)
        machine_id.write_text("test-machine-id\n")
        if name == "symlink":
            ca.symlink_to(old_ca)
        elif name == "corrupt-orphan":
            ca.write_text("invalid old CA residue\n")
        else:
            ca.write_bytes(old_ca.read_bytes())
        if marker:
            target = root / marker
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("preserve even incomplete or corrupt evidence\n")
        before = ca.read_bytes()
        env = {
            **os.environ,
            "FRP_CLIENT_TEST_ROOT": str(root),
            "FRP_TEST_UNAME_S": "Linux",
            "FRP_BOOTSTRAP_LOCATOR": TICKET,
            "FRP_ALLOCATOR_URL": origin + "/enroll",
            "ALLOCATOR_URL": origin + "/enroll",
            "FRP_ALLOCATOR_CA_FILE": str(new_ca),
            "FRP_ALLOCATOR_CA_SHA256": expected,
            "FRP_INSTALLER_URL": installer_url,
            "FRP_BUNDLE_FILE": str(bundle),
            "FRP_EXPECTED_SOURCE_REF": "b" * 40,
            "FRP_EXPECTED_SOURCE_HEAD": "b" * 40,
            "FRP_EXPECTED_RELEASE_CHANNEL": "development",
            **overrides,
        }
        ran = subprocess.run(
            [
                "bash", "-c",
                'set -euo pipefail; . "$1"; '
                'frp_client_recover_orphan_allocator_ca "$ALLOCATOR_URL"; '
                'frp_bootstrap_allocator_ca "$ALLOCATOR_URL"',
                "bash", str(ROOT / "lib/frp-client-common.sh"),
            ],
            env=env, capture_output=True, text=True,
        )
        if (ran.returncode == 0) != success:
            raise AssertionError(f"{name}: unexpected result {ran.returncode}\n{ran.stdout}\n{ran.stderr}")
        if ca.read_bytes() != (new_ca.read_bytes() if success else before):
            raise AssertionError(f"{name}: allocator CA preservation/replacement failed")
        if marker and not (root / marker).exists():
            raise AssertionError(f"{name}: protected state was removed")
        if name == "symlink" and not ca.is_symlink():
            raise AssertionError("symlink was replaced")
    print("ORPHAN_ALLOCATOR_CA_RECOVERY=PASS")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="drlink-fresh-ca-"))
    httpd = None
    try:
        ca_pem, server_crt, server_key = _make_ca_and_leaf(tmp)
        port = _free_port()
        origin = "https://127.0.0.1:%s" % port
        installer_url = origin + "/artifacts/agent/bootstrap-client.sh"
        installer = (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "echo SENTINEL_ENTRY\n"
            'test -n "${FRP_ALLOCATOR_CA_FILE:-}"\n'
            'test -f "$FRP_ALLOCATOR_CA_FILE"\n'
            'test -f "$FRP_BUNDLE_FILE"\n'
            'test "$FRP_EXPECTED_SOURCE_REF" = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
            f'test "$FRP_INSTALLER_URL" = "{installer_url}"\n'
            'openssl x509 -in "$FRP_ALLOCATOR_CA_FILE" -noout >/dev/null\n'
            "if [[ \"$*\" == *--insecure* || \"$*\" == *curl\\ -k* ]]; then\n"
            "  echo insecure >&2\n"
            "  exit 9\n"
            "fi\n"
            "echo FRESH_CLIENT_TRUST_OK\n"
        )
        digest = hashlib.sha256(installer.encode("utf-8")).hexdigest()
        sums = "%s  agent/bootstrap-client.sh\n" % digest
        script = zt.render_short_url_bootstrap_script(
            origin + "/enroll",
            hashlib.sha256(ssl.PEM_cert_to_DER_cert(ca_pem)).hexdigest(),
            None, installer_url, entry_locator=TICKET, ca_pem=ca_pem,
        )
        if "--insecure" in script or "curl -k" in script:
            raise SystemExit("stage-1 script disables TLS verification")
        if "--cacert" not in script or "FRP_ALLOCATOR_CA_FILE" not in script:
            raise SystemExit("same-origin stage-1 script does not pin the private CA")

        bodies = {
            "/%s" % TICKET: script.encode("utf-8"),
            "/artifacts/SHA256SUMS": sums.encode("utf-8"),
            "/artifacts/manifest.json": json.dumps({"qualification_status":"PASS", "channel":"development", "immutable_source_ref":"b"*40, "artifacts":[{"relative_path":"agent/bootstrap-client.sh", "source_head":"b"*40, "sha256":digest}]}).encode(),
            "/artifacts/agent/bootstrap-client.sh": installer.encode("utf-8"),
            "/healthz": b"ok\n",
            "/ca.crt": ca_pem.encode(),
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = self.path.split("?", 1)[0]
                body = bodies.get(path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        httpd = HTTPServer(("127.0.0.1", port), Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(server_crt), keyfile=str(server_key))
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        bare_url = origin + "/" + TICKET
        bare = subprocess.run(
            ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", bare_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if bare.returncode == 0:
            raise SystemExit("stock curl trusted a private CA; regression is invalid")
        combined = (bare.stderr or "") + (bare.stdout or "")
        if "unable to get local issuer certificate" not in combined.lower():
            raise SystemExit("stock curl failed for a different reason: %s" % combined)

        health = subprocess.run(
            ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", origin + "/healthz"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if health.returncode == 0:
            raise SystemExit("stock healthz curl trusted a private CA")

        command=zt.render_entry_command(origin.split("://",1)[1],TICKET,"linux")
        assert command=="curl -kfsS "+bare_url+"|sudo bash"
        # Execute the displayed command unchanged.
        ran = subprocess.run(
            ["bash", "-lc", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        output = (ran.stdout or "") + (ran.stderr or "")
        if ran.returncode != 0 or "FRESH_CLIENT_TRUST_OK" not in ran.stdout:
            raise SystemExit(
                "advertised command failed rc=%s\n%s" % (ran.returncode, output)
            )
        if "unable to get local issuer certificate" in output.lower():
            raise SystemExit("advertised command still failed private-CA trust")
        _verify_orphan_allocator_ca_recovery(tmp, origin, installer_url, installer, ca_pem)
        # The direct stage-1 still enforces immutable candidate provenance.
        (tmp / "ca.crt").write_text(ca_pem)
        for key, value in (("FRP_EXPECTED_SOURCE_HEAD", "c"*40),
                           ("FRP_EXPECTED_RELEASE_CHANNEL", "stable")):
            rejected = subprocess.run(
                (["sudo","-n","env",key+"="+value,"bash","-c",script] if os.geteuid()!=0 else ["bash","-c",script]), capture_output=True, text=True,
                env={**os.environ, key:value,
                     "FRP_ALLOCATOR_CA_FILE":str(tmp / "ca.crt")},
            )
            if rejected.returncode == 0 or "SENTINEL_ENTRY" in rejected.stdout:
                raise SystemExit("mismatched candidate identity executed installer: " + key)
        bodies["/artifacts/agent/bootstrap-client.sh"] = b"#!/bin/bash\necho SENTINEL_EXECUTED\n"
        denied = subprocess.run(["bash", "-lc", command], capture_output=True, text=True)
        if denied.returncode == 0 or "SENTINEL_EXECUTED" in denied.stdout:
            raise SystemExit("unqualified installer executed before verification")
        print("FRESH_CLIENT_TRUST_BOOTSTRAP=PASS")
        return 0
    finally:
        if httpd is not None:
            httpd.shutdown()
        subprocess.run(["rm", "-rf", str(tmp)], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
