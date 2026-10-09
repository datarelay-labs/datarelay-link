# PF-9 Link 3.0 — Web Management Ingress Source Guard

**Status:** Product Web source implementation and loopback acceptance candidate.
Work Packet [#196](https://github.com/datarelay-labs/datarelay-link/issues/196).
**Not activated in a running server; not a completed SSH host ACL feature.**

## Scope and authority

The Link 3.0 optional Web service uses the byte-pinned
`datarelay-onprem-security==0.10.0.dev0` Foundation wheel's
`authorize_management`, `ManagementPolicy`, and `resolve_web_source`
primitives. Link does not copy IP-address matching or CIDR algorithms and
does not reuse the FRP remote service ACL as a host management ACL.

- Fresh product Web installations have a **default-disabled** immutable
  `ManagementPolicy()`. Existing /healthz, static sign-in, authenticated
  management API, and login behavior remain unchanged.
- A product-owned, explicitly provided **enabled Web** `SurfacePolicy`
  checks the resolved source at the beginning of **every GET/POST request**,
  before static routing, credential processing, automation API, or
  protected management API dispatch. A denied source receives generic
  HTTP 403 without a session cookie or route dispatch.
- Explicit `management_acl=None` (the product has declared policy
  unavailable) **fails closed**. Invalid policy and CIDR values fail
  during construction, rather than falling back to permissive matching.
- The `ssh` member of the immutable Foundation `ManagementPolicy` is
  intentionally **not enforced** in the Web service. Host SSH enforcement
  requires a separately authorized host/systemd/firewall integration,
  tested out-of-band recovery, timed rollback, and effective read-back.
- There is **no** HTTP endpoint to activate, edit or persist an ACL in
  this source candidate. Request headers cannot change the policy.

## Explicit trusted proxy contract

`create_server(..., management_acl=trusted_policy,
trusted_proxy_cidrs=(...))` injects values only from a product-owned
trusted caller. Do not take these arguments from untrusted user input.

- The direct socket peer is used unless its IP is in the explicit
  `trusted_proxy_cidrs`. `X-Forwarded-For` from other peers is ignored.
- When the immediate peer is trusted as a proxy, a missing, malformed,
  ambiguous or entirely proxy-only `X-Forwarded-For` chain fails closed.
  While Web ingress enforcement is active, duplicate `X-Forwarded-For`
  HTTP header fields are rejected rather than arbitrarily choosing one.
  When the policy is disabled, duplicate headers do not introduce a new
  denial compared with the earlier Web service.
- A proxy must **strip or correctly append and validate incoming
  client-controlled forwarding headers**. An IP allowlist that permits
  only the proxy/loopback address without a configured trusted-proxy
  boundary is not a reliable client allowlist.
- Both IPv4 and IPv6 (including IPv4-mapped addresses) use the common
  Foundation canonical policy; unrestricted `/0` trust configurations
  are rejected.

## Example of an *isolated product-side caller*

This illustrates the code contract, **not** a runtime deployment instruction.

```python
from drlink_foundation_security import (
    FoundationAllowEntry, FoundationManagementPolicy, FoundationSurfacePolicy,
)
from drlink_web_service import create_server

immutable_policy = FoundationManagementPolicy(
    web=FoundationSurfacePolicy(
        enabled=True,
        revision="owner-provided-revision",
        sources=(FoundationAllowEntry("192.0.2.10/32"),),
    ),
)
server = create_server(
    root=temporary_test_root,
    listen="127.0.0.1",
    port=0,
    management_acl=immutable_policy,
)
```

A real product-managed configuration reader and persistence/UI must
separately prove effective revision, authenticated administrator authority,
active-source self-lockout protection, emergency console access, and a
durable rollback deadline **before** enabling a restrictive management
policy on any installed system.

## Evidence and remaining gates

`python3 tests/test-v30-web-management-ingress.py -q` drives an actual
loopback HTTP server using synthetic temporary-root data. It checks
default disabled, explicit missing policy, enabled denial on public
pages, login endpoints and API endpoints, permitted behavior, XFF
spoofing, trusted proxy chain and invalid bootstrap configuration.
Existing Web service, staged-login, shared-wheel, package and user
scenarios remain independent.

**Not established by this source:** an active real operator policy,
host SSH controls, installed nginx/Proxy trust integration, DB-backed
policy revisions, admin settings UI, maintenance recovery, actual
Browser/Full User E2E, release or owner acceptance. Live host, identity,
credential, firewall, service and database operations are outside this
Work Packet.
