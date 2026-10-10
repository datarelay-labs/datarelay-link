# Data Relay Link 3.0 — Automation API and Signed Event Webhooks

> Status: **Development implementation; not a 3.0 GA or release qualification claim.**
> Product authority: `PRODUCT_MASTER.md` and `MANAGEMENT_SURFACE_CONTRACT.md`.
> This page documents current v3.0 source behavior, not a future promised API.

## Isolation boundaries

The optional Web Management HTTP API (`/api/v1`) is a private browser contract.
The separate **Public Automation API** (`/api/automation/v1`) authenticates
non-human **Service Accounts** and invokes the existing Core Management
Service. It does not reuse Web operator sessions, cookies, CSRF, or MCP actors.
The standalone Automation service can operate without the optional Web process;
the same endpoint may be hosted by the optional Web listener.

Current development implementation permits **allowlisted OBSERVE/TEST**
Core calls: inventory list/get, health, connection diagnosis, policy test, audit
query, live access, Job list/get, and **Temporary Access Change Plan preview**
(`drlink_temporary_access_preview`). A Service Account with explicit
`management-temporary-access` permission can request a short-lived
actor/Server/revision-bound plan; plan creation does **not** change policy
authorization and cannot be applied through the Automation API. Plans remain
bound to the creating principal across Core surfaces. No arbitrary operation,
shell execution, policy mutation, recovery, or staged update is reachable via
this adapter. Change Plan mutations with durable idempotency remain a separate
future implementation/qualification step.

## Local administration / lifecycle

An authenticated **Admin** in Web Management uses **Administration →
Integrations**. Service Account create displays a random Bearer exactly once.
Stored credentials are SHA-256 digests; authenticated API operations retain
service-account actor attribution and a bounded request count.

- Create: `POST /api/v1/service-accounts` with `name`,
  `permissions`, optional timezone-aware `expires_at`.
- Inventory (no secrets): `GET /api/v1/service-accounts`.
- Rotate: `POST /api/v1/service-accounts/rotate` with `account_id`.
  Existing credentials are invalidated atomically.
- Revoke: `POST /api/v1/service-accounts/revoke` with `account_id`.

All four endpoints are protected by Web Admin authorization and normal Web
session/CSRF validation. There is no dependency on external IdP or MCP.

## Automation HTTP

The independent server entrypoint is
`/usr/local/lib/drlink/drlink-automation.py`; service
`drlink-automation.service`. The installed unit listens on **127.0.0.1:8742**
and is opt-in. Non-loopback bind requires explicit TLS certificate and key;
do not expose cleartext Bearer credentials on a network.

Example against a deliberately loopback-only listener:

```sh
curl --fail-with-body -sS -X POST http://127.0.0.1:8742/api/automation/v1/drlink_inventory_list \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $DRLINK_AUTOMATION_TOKEN" \
  -d '{"resource_type":"managed-host","limit":10}'
```

The standalone API caps request bodies at 16 KiB, concurrent handlers at 16
and requests at **120/minute per Service Account** across workers; an excess
returns HTTP 429. Invalid/revoked credentials return 401; refused operations
return 403. Read-only Core permission checks still apply after authentication.
The embedded Web listener has a separate existing 64-KiB request limit.
The standalone listener requires a single bounded decimal `Content-Length`,
rejects duplicate Authorization/Content-Length, all `Transfer-Encoding`,
and absolute-form API targets, and closes unconsumed rejected request bodies
to avoid ambiguous persistent-connection framing.

Standalone Automation errors return both a human-readable `error` and a
stable machine-readable `code`. Supported categories include
`INVALID_REQUEST` (400), `UNAUTHENTICATED` (401),
`OPERATION_DENIED` (403), `NOT_FOUND` (404),
`METHOD_NOT_ALLOWED` (405), `PAYLOAD_TOO_LARGE` (413),
`RATE_LIMITED` (429), `CAPACITY_EXCEEDED` (503), and
`INTERNAL_ERROR` (500). The codes deliberately do not expose bearer
material, internal exception text, or protected Core operation details.
The standalone API still admits only the documented OBSERVE/TEST allowlist;
Temporary Access preview may persist a Change Plan, never apply a policy change.

## Signed event Webhooks

Web Admin **Integrations** manages named HTTPS subscriptions with selected event
classes: `attention`, `security.lifecycle`, `policy.change`,
`managed_host.lifecycle`. Webhook endpoints must be DNS hostnames on TLS/443
(no IP literals, userinfo, URL query, URL fragment or unsupported ports).

- `GET /api/v1/webhooks`: subscriptions and bounded delivery counts, no secrets.
- `POST /api/v1/webhooks`: create and display a random signing secret once.
- `POST /api/v1/webhooks/rotate`: replace signing secret.
- `POST /api/v1/webhooks/disable`: stop the subscription and fail queued work.

The administration inventory and creation boundary admit at most **200 named
subscriptions**, including disabled records. Overflow creates no additional
delivery sink, signing material, or audit receipt; the limit prevents a webhook
from receiving events while being invisible in the bounded Web inventory.
Disabled subscriptions remain in the inventory and count toward the limit;
this development contract does not silently delete their records or authorize
a new destructive removal operation.

The signing secret is encrypted in SQLite with a separate private Fernet key at
`/var/lib/drlink/webhook-signing.key` (mode 0600); the key is included as
an optional protected file in the canonical backup/restore state-path contract.
Keep the key and SQLite backup together. A missing/unsafe key fails closed.
The feature requires the `python3-cryptography` package.

Each event has a stable `event_id`, schema version, event class and sanitized
nonsecret metadata. Delivery sends `X-DRLink-Event-ID` and
`X-DRLink-Signature: sha256=<HMAC-SHA256 of exact JSON bytes>`; receiver
must verify the HMAC and deduplicate the event ID. Event `data` includes a
source audit row ID and a resource fingerprint, **not arbitrary raw audit
identifiers**. No application payload or stored credential is included.

Core audit events are staged by an idempotent persisted cursor into the local
bounded outbox. The optional `drlink-webhook-delivery.timer` runs a bounded
`drlink-webhook-delivery.service` tick about every 30 seconds **only when
explicitly enabled**:

```sh
sudo systemctl enable --now drlink-webhook-delivery.timer
sudo systemctl status drlink-webhook-delivery.timer
```

Outbound delivery requires public DNS answers; all candidate IPs must be global.
TCP dials the chosen validated IP and TLS verifies the configured DNS hostname.
No redirects; HTTPS response 2xx accepts the event. Failed attempts use bounded
backoff and at most five tries, with terminal failure visible in delivery counts.
At most 1,000 pending/leased events are retained; completed history is capped
at 5,000 and pruned after 30 days. Full queues preserve the audit cursor for
later processing. **Webhook delivery is never a policy-enforcement dependency.**

## Qualification / remaining integration work

Development regressions exercise authenticated real loopback HTTP, independent
Automation HTTP, secret lifecycle, real local TLS/HMAC delivery, SSRF denial,
audit cursor idempotency and queue backpressure. Release closure still requires
all affected full platform/package tests, complete same-HEAD real-user E2E,
prior-stable upgrade validation, native CI, exact source artifacts and owner
release acceptance. Current read-only Automation scope must not be advertised
as the full planned 3.0 mutation contract.
