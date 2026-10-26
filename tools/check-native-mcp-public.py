#!/usr/bin/env python3
"""Read-only public HTTPS/OAuth smoke for access Native MCP via mcp.xdr.ooo."""
from __future__ import annotations

import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORIGIN = "https://mcp.xdr.ooo"
RESOURCE = ORIGIN + "/access/mcp"
ISSUER = ORIGIN + "/access"
# DO NOT disable TLS verification even in developer tests.
CTX = ssl.create_default_context()


def get_json(path: str) -> dict:
    with urlopen(Request(ORIGIN + path), timeout=10, context=CTX) as response:
        if response.status != 200:
            raise RuntimeError("Unexpected public status for " + path)
        body = json.loads(response.read(32768).decode("utf-8"))
        if not isinstance(body, dict):
            raise RuntimeError("Invalid public MCP metadata")
        return body


def verify() -> None:
    existing = get_json("/.well-known/oauth-protected-resource")
    if existing.get("resource") != ORIGIN + "/mcp":
        raise RuntimeError("The existing /mcp resource changed")
    protected = get_json("/.well-known/oauth-protected-resource/access/mcp")
    if protected.get("resource") != RESOURCE or ISSUER not in protected.get("authorization_servers", []):
        raise RuntimeError("Native protected resource points to the wrong authority")
    alternate = get_json("/access/.well-known/oauth-protected-resource")
    if alternate.get("resource") != RESOURCE:
        raise RuntimeError("Native WWW-Authenticate metadata is incorrect")
    server = get_json("/.well-known/oauth-authorization-server/access")
    if server.get("issuer") != ISSUER:
        raise RuntimeError("Native OAuth issuer is incorrect")
    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        if not str(server.get(key) or "").startswith(ISSUER + "/oauth/"):
            raise RuntimeError("Native OAuth endpoint is not routed: " + key)
    req = Request(RESOURCE,
                  data=b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
                  headers={"Content-Type":"application/json", "Accept":"application/json, text/event-stream"},
                  method="POST")
    try:
        with urlopen(req, timeout=10, context=CTX):
            raise RuntimeError("Unauthenticated Native MCP unexpectedly allowed tools/list")
    except HTTPError as err:
        if err.code != 401:
            raise RuntimeError("Native MCP expected 401, got %s" % err.code) from None
        challenge = err.headers.get("WWW-Authenticate") or ""
        if not challenge.startswith("Bearer ") or ISSUER not in challenge:
            raise RuntimeError("Native MCP WWW-Authenticate is not public/HTTPS")
    print("NATIVE_PUBLIC_TLS=PASS")
    print("NATIVE_RESOURCE_METADATA=PASS")
    print("NATIVE_OAUTH_ISSUER=PASS")
    print("NATIVE_ANONYMOUS_DENY=PASS")
    print("PRIMARY_MCP_RESOURCE_PRESERVED=PASS")
    print("CHATGPT_CUSTOM_MCP_URL=" + RESOURCE)
    print("REAL_CHATGPT_OAUTH_AND_AI_ACCESS=NOT_YET_VERIFIED")


if __name__ == "__main__":
    try:
        verify()
    except (URLError, RuntimeError, ValueError, KeyError) as exc:
        print("NATIVE_PUBLIC_SMOKE=FAIL: " + str(exc), file=sys.stderr)
        raise SystemExit(1)
