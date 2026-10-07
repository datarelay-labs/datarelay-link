#!/usr/bin/env python3
"""P1: Internet Access IP/CIDR/UDP runtime parity (Priority 8A)."""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
sys.path.insert(0, str(ROOT / "server"))

from drlink_control_plane import ControlPlane, ControlPlaneError  # noqa: E402
import drlink_runtime_policy as RP  # noqa: E402
import drlink_v24 as v24  # noqa: E402
import frp_egress_control as EG  # noqa: E402
from drlink_v24_bundle import apply_v24_plan, prepare_v24_plan  # noqa: E402


SRC = "10.20.30.40"
PUBLIC_A = "8.8.8.8"
PUBLIC_B = "8.8.4.4"
PUBLIC_OUTSIDE = "1.1.1.1"


def _server_root(tmp: str) -> None:
    Path(tmp, "etc/drlink").mkdir(parents=True, exist_ok=True)
    Path(tmp, "etc/drlink/config.json").write_text('{"role":"server"}\n', encoding="utf-8")


class InternetRuntimeParityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="drlink-p8a-")
        _server_root(self.tmp)
        os.environ["FRP_DEPLOY_TEST_ROOT"] = self.tmp
        os.environ["DRLINK_CONFIRM"] = "yes"
        self.plane = ControlPlane(self.tmp)
        v24.ensure_v2_schema(self.plane.conn)
        v24.set_network_object(self.plane, "office", type="ip", value=SRC, oneshot=True)
        v24.set_network_object(self.plane, "exact-ip", type="ip", value=PUBLIC_A, oneshot=True)
        v24.set_network_object(
            self.plane, "cidr-block", type="cidr", value="8.8.8.0/24", oneshot=True
        )
        v24.set_network_object(self.plane, "api-fqdn", type="fqdn", value="api.example", oneshot=True)
        v24.set_service_object(self.plane, "https", type="tcp", port=443, oneshot=True)
        v24.set_service_object(self.plane, "http", type="tcp", port=80, oneshot=True)
        v24.set_service_object(self.plane, "dns-udp", type="udp", port=53, oneshot=True)
        v24.set_service_object(self.plane, "ssh-tcp", type="tcp", port=22, oneshot=True)

    def tearDown(self):
        self.plane.close()
        for key in ("FRP_DEPLOY_TEST_ROOT", "DRLINK_CONFIRM"):
            os.environ.pop(key, None)

    def _whitelist_rule(self, name: str, destination: str, service: str = "https") -> None:
        v24.set_access_rule(
            self.plane,
            "internet",
            name,
            mode="whitelist",
            source="office",
            destination=destination,
            service=service,
            enabled=True,
            oneshot=True,
        )

    def _blacklist_rule(self, name: str, destination: str, service: str = "https") -> None:
        v24.set_access_rule(
            self.plane,
            "internet",
            name,
            mode="blacklist",
            source="office",
            destination=destination,
            service=service,
            enabled=True,
            oneshot=True,
        )

    def test_00_no_policy_gateway_denies_without_outbound_connect(self):
        self.plane.compile_runtime()
        cfg_path = Path(self.tmp) / "etc/drlink/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["egress_conn_log_file"] = str(
            Path(self.tmp) / "var/log/drlink/egress/connections.jsonl"
        )
        Path(self.tmp, "var/log/drlink/egress").mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg) + "\n", encoding="utf-8")

        attempted: list[str] = []

        def resolve(host: str) -> list[str]:
            self.assertEqual(host, "api.example")
            return [PUBLIC_A]

        def connect_fn(ip, port, hostname, timeout):
            del port, hostname, timeout
            attempted.append(ip)
            raise AssertionError("No Policy must not attempt an outbound connection")

        gw_path = ROOT / "server" / "frp-egress-gateway.py"
        spec = importlib.util.spec_from_file_location("frp_egress_gateway_no_policy_guard", gw_path)
        GW = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(GW)

        cache = GW.PolicyCache(cfg_path)
        gw = GW.GatewayState(cache, resolve_fn=resolve, connect_fn=connect_fn)
        sock, decision = GW._authorize_and_connect(
            gw,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            method="CONNECT",
            protocol="https",
        )
        self.assertIsNone(sock)
        self.assertEqual(decision["decision"], EG.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])
        self.assertEqual(attempted, [])

    def test_00_no_policy_gateway_fails_closed_without_connect(self):
        """Fresh v2.4 must not turn the default 0.0.0.0 proxy listener into an open proxy."""
        self.plane.compile_runtime()
        attempted: list[tuple[str, int, str]] = []

        def resolve(host: str) -> list[str]:
            self.assertEqual(host, "api.example")
            return [PUBLIC_A]

        def connect_fn(ip, port, hostname, timeout):
            del timeout
            attempted.append((ip, int(port), hostname))
            raise AssertionError("outbound connect must not run when Internet Access has No Policy")

        gw_path = ROOT / "server" / "frp-egress-gateway.py"
        spec = importlib.util.spec_from_file_location("frp_egress_gateway_no_policy", gw_path)
        GW = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(GW)

        cfg_path = Path(self.tmp) / "etc/drlink/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["egress_conn_log_file"] = str(
            Path(self.tmp) / "var/log/drlink/egress/connections.jsonl"
        )
        Path(self.tmp, "var/log/drlink/egress").mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg) + "\n", encoding="utf-8")

        cache = GW.PolicyCache(cfg_path)
        gw = GW.GatewayState(cache, resolve_fn=resolve, connect_fn=connect_fn)
        sock, decision = GW._authorize_and_connect(
            gw,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            method="CONNECT",
            protocol="https",
        )
        self.assertIsNone(sock)
        self.assertEqual(decision["decision"], EG.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])
        self.assertEqual(attempted, [])

    def test_01_direct_ip_literal_explicit_allow(self):
        self._whitelist_rule("allow-ip", "exact-ip")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname=PUBLIC_A,
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(decision["decision"], RP.DECISION_ALLOW)
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A])
        self.assertTrue(decision["is_ip_literal"])

    def test_02_direct_ip_literal_fqdn_rule_does_not_authorize(self):
        self._whitelist_rule("allow-fqdn", "api-fqdn")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname=PUBLIC_A,
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(decision["decision"], RP.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])

    def test_03_unsafe_literals_denied(self):
        self._whitelist_rule("allow-ip", "exact-ip")
        for bad in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "fc00::1"):
            with self.assertRaises(EG.EgressError):
                EG.validate_resolved_addresses([bad])
            # Even if a caller skipped validate, policy still requires public Host/CIDR;
            # evaluate against unsafe literal with candidate must not widen FQDN rules.
            decision = RP.authorize_internet(
                self.plane,
                source_ip=SRC,
                hostname=bad,
                port=443,
                protocol="https",
                candidate_ips=[bad],
            )
            self.assertEqual(decision["decision"], RP.DECISION_DENY, msg=bad)

    def test_04_cidr_via_hostname_allow(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(decision["decision"], RP.DECISION_ALLOW)
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A])

    def test_05_cidr_mismatch_deny(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_OUTSIDE],
        )
        self.assertEqual(decision["decision"], RP.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])

    def test_06_mixed_dns_candidates_filtered(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A, PUBLIC_OUTSIDE],
        )
        self.assertEqual(decision["decision"], RP.DECISION_ALLOW)
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A])
        self.assertNotIn(PUBLIC_OUTSIDE, decision["authorized_candidates"])

    def test_07_blacklist_rejected(self):
        rev = self.plane.current_revision()
        with self.assertRaises(ControlPlaneError) as ctx:
            self._blacklist_rule("block-cidr", "cidr-block")
        self.assertIn("WHITELIST", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev)

    def test_08_fqdn_rule_authorizes_all_safe_candidates(self):
        self._whitelist_rule("allow-fqdn", "api-fqdn")
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A, PUBLIC_B],
        )
        self.assertEqual(decision["decision"], RP.DECISION_ALLOW)
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A, PUBLIC_B])

    def test_09_no_reresolve_uses_injected_candidates(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        calls = {"n": 0}

        def resolve(host: str) -> list[str]:
            calls["n"] += 1
            if calls["n"] == 1:
                return [PUBLIC_A]
            return [PUBLIC_OUTSIDE]

        # Runtime authorize consumes the provided candidate list once; a second
        # resolve must not change the authorized set.
        first = list(resolve("api.example"))
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=first,
        )
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A])
        second = list(resolve("api.example"))
        self.assertEqual(second, [PUBLIC_OUTSIDE])
        self.assertEqual(decision["authorized_candidates"], [PUBLIC_A])
        self.assertEqual(calls["n"], 2)

    def test_10_udp_direct_rule_rejected(self):
        rev = self.plane.current_revision()
        with self.assertRaises(ControlPlaneError) as ctx:
            v24.set_access_rule(
                self.plane,
                "internet",
                "bad-udp",
                mode="whitelist",
                source="office",
                destination="api-fqdn",
                service="dns-udp",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("TCP/HTTP/HTTPS CONNECT", str(ctx.exception))
        self.assertIn("UDP", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev)
        self.assertIsNone(self.plane._get_rule("internet", "bad-udp"))

    def test_11_udp_group_rejected_atomically(self):
        v24.set_service_group(self.plane, "mixed", members=["https", "dns-udp"], oneshot=True)
        rev = self.plane.current_revision()
        with self.assertRaises(ControlPlaneError) as ctx:
            v24.set_access_rule(
                self.plane,
                "internet",
                "bad-udp-group",
                mode="whitelist",
                source="office",
                destination="api-fqdn",
                service="mixed",
                enabled=True,
                oneshot=True,
            )
        self.assertIn("UDP", str(ctx.exception))
        self.assertEqual(self.plane.current_revision(), rev)
        self.assertIsNone(self.plane._get_rule("internet", "bad-udp-group"))

    def test_12_bundle_udp_rejected(self):
        rev = self.plane.current_revision()
        yaml_text = """configurationBundle:
  context: server
  serviceObjects:
    - name: dns-udp
      type: udp
      port: 53
  networkObjects:
    - name: office
      type: ip
      value: %s
    - name: api-fqdn
      type: fqdn
      value: api.example
  internetAccess:
    mode: whitelist
    enforcement: enabled
    rules:
      - name: bundle-udp
        source: office
        destination: api-fqdn
        service: dns-udp
        enabled: true
""" % SRC
        with self.assertRaises(Exception) as ctx:
            plan = prepare_v24_plan(self.plane, yaml_text)
            apply_v24_plan(self.plane, plan, confirm=True)
        msg = str(ctx.exception)
        self.assertTrue("UDP" in msg or "udp" in msg.lower(), msg)
        self.assertEqual(self.plane.current_revision(), rev)
        self.assertIsNone(self.plane._get_rule("internet", "bundle-udp"))

    def test_13_public_test_runtime_parity(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        self._whitelist_rule("allow-fqdn", "api-fqdn", service="http")

        def resolve(host: str) -> list[str]:
            return [PUBLIC_A]

        cidr = v24.evaluate_selector_policy(
            self.plane,
            "internet",
            source_name="office",
            destination_name="api.example",
            service_name="https",
            resolve_fn=resolve,
        )
        self.assertEqual(cidr["result"], "ALLOW")
        self.assertEqual(cidr["authorized_candidates"], [PUBLIC_A])

        fqdn = v24.evaluate_selector_policy(
            self.plane,
            "internet",
            source_name="office",
            destination_name="api-fqdn",
            service_name="http",
            resolve_fn=resolve,
        )
        self.assertEqual(fqdn["result"], "ALLOW")

        ip_test = v24.evaluate_selector_policy(
            self.plane,
            "internet",
            source_name="office",
            destination_name=PUBLIC_A,
            service_name="https",
        )
        # Representative IP destination token with CIDR rule covering PUBLIC_A.
        self.assertEqual(ip_test["result"], "ALLOW")

        with self.assertRaises(ControlPlaneError) as ctx:
            v24.evaluate_selector_policy(
                self.plane,
                "internet",
                source_name="office",
                destination_name="api-fqdn",
                service_name="dns-udp",
            )
        self.assertIn("UDP", str(ctx.exception))

    def test_14_gateway_connects_only_authorized_candidates(self):
        self._whitelist_rule("allow-cidr", "cidr-block")
        self.plane.compile_runtime()

        attempted: list[str] = []
        connected = {"ip": None}

        def resolve(host: str) -> list[str]:
            return [PUBLIC_A, PUBLIC_OUTSIDE]

        def connect_fn(ip, port, hostname, timeout):
            del hostname, timeout
            attempted.append(ip)
            if ip != PUBLIC_A:
                raise OSError("should not connect unauthorized candidate")
            connected["ip"] = ip
            return socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if "frp_egress_gateway" in sys.modules:
            del sys.modules["frp_egress_gateway"]
        gw_path = ROOT / "server" / "frp-egress-gateway.py"
        spec = importlib.util.spec_from_file_location("frp_egress_gateway", gw_path)
        GW = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(GW)

        cfg_path = Path(self.tmp) / "etc/drlink/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg.update(
            {
                "egress_listen_addr": "127.0.0.1",
                "egress_listen_port": 0,
                "egress_conn_log_file": str(
                    Path(self.tmp) / "var/log/drlink/egress/connections.jsonl"
                ),
            }
        )
        Path(self.tmp, "var/log/drlink/egress").mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg) + "\n", encoding="utf-8")

        orig_validate = GW.EG.validate_resolved_addresses
        GW.EG.validate_resolved_addresses = lambda ips: [str(ip) for ip in ips]
        try:
            cache = GW.PolicyCache(cfg_path)
            gw = GW.GatewayState(cache, resolve_fn=resolve, connect_fn=connect_fn)
            sock, decision = GW._authorize_and_connect(
                gw,
                source_ip=SRC,
                hostname="api.example",
                port=443,
                method="CONNECT",
                protocol="https",
            )
            self.assertIsNotNone(sock)
            self.assertEqual(decision.get("decision"), EG.DECISION_ALLOW)
            self.assertEqual(decision.get("authorized_candidates"), [PUBLIC_A])
            self.assertEqual(attempted, [PUBLIC_A])
            self.assertEqual(connected["ip"], PUBLIC_A)
            sock.close()
        finally:
            GW.EG.validate_resolved_addresses = orig_validate

    def test_15_parse_authority_accepts_public_ip_literal(self):
        host, port = EG.parse_authority_host_port("%s:443" % PUBLIC_A)
        self.assertEqual((host, port), (PUBLIC_A, 443))

    def test_16_managed_host_whitelist_nat_source_fails_closed(self):
        managed_ip = "10.20.30.41"
        nat_ip = "198.51.100.41"
        self.plane.upsert_client(
            "managed-source-client",
            label="managed-source",
            hostname="managed-source",
            addresses=[{"address": managed_ip, "active": True}],
        )
        v24.set_access_rule(
            self.plane,
            "internet",
            "allow-managed",
            mode="whitelist",
            source="managed-source",
            destination="api-fqdn",
            service="https",
            enabled=True,
            oneshot=True,
        )

        direct = RP.authorize_internet(
            self.plane,
            source_ip=managed_ip,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(direct["decision"], RP.DECISION_ALLOW)
        self.assertEqual(direct["authorized_candidates"], [PUBLIC_A])

        nat = RP.authorize_internet(
            self.plane,
            source_ip=nat_ip,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(nat["decision"], RP.DECISION_DENY)
        self.assertEqual(nat["authorized_candidates"], [])

        unrelated = RP.authorize_internet(
            self.plane,
            source_ip=nat_ip,
            hostname="other.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(unrelated["decision"], RP.DECISION_DENY)

    def test_17_disabled_enforcement_is_deny_all(self):
        self._whitelist_rule("allow-fqdn", "api-fqdn")
        v24.set_policy_enforcement(self.plane, "internet", False, confirm=True)
        decision = RP.authorize_internet(
            self.plane,
            source_ip=SRC,
            hostname="api.example",
            port=443,
            protocol="https",
            candidate_ips=[PUBLIC_A],
        )
        self.assertEqual(decision["decision"], RP.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])
        self.assertIn("DISABLED", decision["reason"])

    def test_18_gateway_does_not_connect_without_matching_whitelist_source(self):
        self.plane.upsert_client(
            "managed-source-client",
            label="managed-source",
            hostname="managed-source",
            addresses=[{"address": "10.20.30.41", "active": True}],
        )
        v24.set_access_rule(
            self.plane,
            "internet",
            "allow-managed",
            mode="whitelist",
            source="managed-source",
            destination="api-fqdn",
            service="https",
            enabled=True,
            oneshot=True,
        )
        self.plane.compile_runtime()

        attempted: list[str] = []

        def resolve(host: str) -> list[str]:
            self.assertEqual(host, "api.example")
            return [PUBLIC_A]

        def connect_fn(ip, port, hostname, timeout):
            del port, hostname, timeout
            attempted.append(ip)
            raise AssertionError("connect must not run for unmatched WHITELIST source")

        gw_path = ROOT / "server" / "frp-egress-gateway.py"
        spec = importlib.util.spec_from_file_location("frp_egress_gateway_nat_guard", gw_path)
        GW = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(GW)

        cfg_path = Path(self.tmp) / "etc/drlink/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["egress_conn_log_file"] = str(
            Path(self.tmp) / "var/log/drlink/egress/connections.jsonl"
        )
        Path(self.tmp, "var/log/drlink/egress").mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps(cfg) + "\n", encoding="utf-8")

        cache = GW.PolicyCache(cfg_path)
        gw = GW.GatewayState(cache, resolve_fn=resolve, connect_fn=connect_fn)
        sock, decision = GW._authorize_and_connect(
            gw,
            source_ip="198.51.100.41",
            hostname="api.example",
            port=443,
            method="CONNECT",
            protocol="https",
        )
        self.assertIsNone(sock)
        self.assertEqual(decision["decision"], EG.DECISION_DENY)
        self.assertEqual(decision["authorized_candidates"], [])
        self.assertEqual(attempted, [])


if __name__ == "__main__":
    unittest.main()
