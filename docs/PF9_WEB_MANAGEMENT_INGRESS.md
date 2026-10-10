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

A product-owned configuration writer, Administration UI and rollout
coordinator must separately prove effective revision, authenticated administrator authority,
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

## Opt-in read-only configuration file bootstrap (B3 follow-on)

The Web service now supports the optional `--management-acl-file`
command-line argument. Without that argument, the established default
**OFF** policy and legacy behavior are unchanged. The service does not
fetch settings, auto-enable a restrictive policy or watch for hot reloads.

A host or product operator may *prepare* a strictly versioned and private
UTF-8 JSON configuration in an offline staging context:

```json
{
  "schema_version": 1,
  "web": {
    "enabled": true,
    "revision": "owner-approved-revision-001",
    "sources": [
      {"cidr": "192.0.2.10/32", "name": "management-station"}
    ]
  },
  "trusted_proxy_cidrs": []
}
```

Only the exact fields shown above are supported. `sources` may contain
up to 128 entries with optional `name` and UTC-epoch `expires_at`;
`trusted_proxy_cidrs` may contain up to 16 verified and unique networks.
When `enabled=false`, the `sources` list should be empty.
SSH rules, arbitrary commands, credentials, hostnames and unknown JSON
keys are not accepted as a Web policy. The file path must be absolute,
the final file must be regular, have only one hard link, be owned by
root or the Web service UID, and have no group/other permission bits.
Symbolic links, unsafe modes, duplicate keys, malformed UTF-8/JSON,
unbounded files (above 16 KiB), and invalid/unsupported CIDRs are
rejected before the Web listener starts. The file is opened without
following the final symbolic link and parsed from the verified file
descriptor; there is no read/write API for the running HTTP service.

**No deployment or permission change is authorized by this source.**
Actual operator selection of a policy file and restart of a managed
Web listener is a separate privileged operation. Before such an action,
the product/installer must independently verify the current management
source, maintenance console, appropriate secure proxy provenance,
durable rollback timer, exact revision, active-probe read-back and
two-persona acceptance. A restrictive Web policy also protects
`/healthz`, so platform health probes must be explicitly considered in
the rollout plan. The host SSH allowlist is not implemented here.

The additively expanded native acceptance contract is:
`python3 tests/test-v30-web-management-ingress.py -q` and
`python3 tests/test-v30-web-management-ingress-config.py -q`,
including real isolated HTTP assertions plus CLI argument dispatch
without starting any installed or production Web service.

## Read-only Administrator policy status

An authenticated, current **Admin** Web session can read
`GET /api/v1/admin/management-ingress/status` to see the *effective
in-memory* Web ingress policy after service startup, not a submitted
or pending draft. The endpoint returns:

- `web.status`: `DISABLED` (default), `ENABLED` (a validated
  policy is injected), or `UNAVAILABLE` (explicit policy unknown);
- `web.policy_revision`, configured `source_count`, and
  `trusted_proxy_count`, without raw networks or the policy file;
- `ssh_host.status=UNAVAILABLE`, `ssh_host.enforcement_supported=false`,
  `apply_available=false`, and
  `configuration_mutation_supported=false`.

Anonymous calls require a valid full Web session and return HTTP 401;
a current Read Only/Operator session receives HTTP 403. The internal
Web application dispatch also enforces Admin-only read access. All
requests remain subject to the ingress guard itself, so an explicitly
unavailable policy cannot be bypassed by using this status endpoint.
Neither GET nor any other route creates, edits, saves or applies a
source allowlist, host SSH firewall rule, recovery timer, or credentials.
This is a product-native read path, not a declaration of a completed
Administrative settings UI or a host-safe rollout.
