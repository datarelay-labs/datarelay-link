#!/usr/bin/env python3
"""Explicit bounded delivery runner for signed HTTPS event Webhooks.

The transport dials the validated resolved socket address, *not* a second
DNS lookup. TLS authenticates the configured DNS hostname (SNI and hostname
verification). Never follows redirects and never permits local/private IPs.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import ipaddress
import socket
import ssl
from typing import Any, Optional

from drlink_control_db import ControlPlaneError
from drlink_webhooks import WebhookStore, validate_webhook_url

CONNECT_TIMEOUT = 5
MAX_TICK = 10


def resolve_public_target(host: str) -> tuple:
    try:
        candidates = socket.getaddrinfo(
            host, 443, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (OSError, ValueError) as exc:
        raise ControlPlaneError("Webhook destination DNS resolution failed.") from exc
    if not candidates:
        raise ControlPlaneError("Webhook destination DNS returned no addresses.")
    # All candidate addresses must pass; a mixed public/private DNS response
    # cannot be rescued by choosing one apparently safe address.
    for candidate in candidates:
        try:
            address = ipaddress.ip_address(candidate[4][0])
        except (IndexError, ValueError) as exc:
            raise ControlPlaneError("Webhook destination DNS returned an invalid address.") from exc
        if not address.is_global:
            raise ControlPlaneError("Webhook destination resolved to a non-public address.")
    return candidates[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, selected: tuple):
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        super().__init__(hostname, port=443, timeout=CONNECT_TIMEOUT, context=context)
        self.selected = selected

    def connect(self) -> None:
        family, socktype, protocol, _canon, sockaddr = self.selected
        raw = socket.socket(family, socktype, protocol)
        try:
            raw.settimeout(CONNECT_TIMEOUT)
            raw.connect(sockaddr)
            # HTTPSConnection uses the DNS hostname for certificate verification,
            # while TCP uses precisely the address previously validated.
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def send_signed_event(url: str, body_json: str, event_id: str, secret: str) -> int:
    _url, hostname, path = validate_webhook_url(url)
    selected = resolve_public_target(hostname)
    body = body_json.encode("utf-8")
    signature = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    conn = PinnedHTTPSConnection(hostname, selected)
    try:
        conn.request(
            "POST", path, body=body,
            headers={
                "Content-Type": "application/json",
                "X-DRLink-Event-ID": event_id,
                "X-DRLink-Signature": signature,
                "User-Agent": "DataRelayLink-Webhook/3.0",
                "Connection": "close",
            },
        )
        response = conn.getresponse()
        status = int(response.status)
        response.read(512)
        return status
    finally:
        conn.close()


def delivery_tick(root: Optional[str] = None, *, limit: int = MAX_TICK) -> dict[str, int]:
    """Run a bounded independent worker tick. Never affects policy enforcement."""
    # A zero/negative or coerced limit must never silently claim one delivery.
    # Reject before retention, audit-cursor staging, or any outbox mutation.
    if type(limit) is not int or limit < 1:
        raise ControlPlaneError("Webhook delivery limit must be a positive integer.")
    result = {"claimed": 0, "delivered": 0, "failed": 0}
    from drlink_webhook_events import stage_audit_events
    with WebhookStore(root) as store:
        # The independent worker is the only background retention owner.
        # Never delete pending/leased deliveries.
        store.prune_history()
        # A full outbox retains its audit cursor rather than dropping events.
        stage_audit_events(store)
        jobs = store.claim_due(min(MAX_TICK, max(1, int(limit))))
        result["claimed"] = len(jobs)
        for job in jobs:
            try:
                secret = store.signing_secret(job["webhook_id"])
                status = send_signed_event(
                    job["url"], job["payload_json"], job["event_id"], secret,
                )
                if status < 200 or status >= 300:
                    raise ControlPlaneError("Webhook HTTP delivery was not accepted.")
                if store.record_attempt(
                    job["event_id"], lease_token=job["lease_token"], delivered=True
                ):
                    result["delivered"] += 1
            except Exception as exc:
                # Late workers must not overwrite a reclaimed or disabled lease.
                # Only error categories are recorded, never URLs or raw data.
                if store.record_attempt(
                    job["event_id"], lease_token=job["lease_token"],
                    delivered=False, error=type(exc).__name__,
                ):
                    result["failed"] += 1
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="DRLink bounded signed Webhook delivery tick")
    parser.add_argument("--root")
    parser.add_argument("--limit", type=int, default=MAX_TICK)
    args = parser.parse_args(argv)
    result = delivery_tick(args.root, limit=args.limit)
    print("Webhook delivery: claimed=%d delivered=%d failed=%d" % (
        result["claimed"], result["delivered"], result["failed"],
    ))
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
