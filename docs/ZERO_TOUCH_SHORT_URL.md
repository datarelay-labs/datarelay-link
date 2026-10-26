# Zero-Touch Bootstrap: v2.4 current UX and Short URL internals

> **Current contract:** `ZT-P0-CONTRACT-20261026`, [regression causes and release gates](ZERO_TOUCH_REGRESSION_CONTROL.md).
> **Status:** normative for v2.4 development; real installed-product acceptance is still required. This page retains historical v2.1.3 internals for compatibility, not current default behavior.

## Current beginner-facing behavior

The standard `set enrollment zero-touch` journey **defaults to a short, copyable HTTPS launcher** when a real publicly trusted bootstrap endpoint can be qualified. An explicit `bootstrap_hostname` represents operator intent to serve that endpoint; stock-client certificate verification still applies. Without an explicit bootstrap host, a candidate DNS `public_hostname` or `public_url_host` is usable only after stock TLS verification and a test request to `/i/invalid-qualification-probe` returns DRLink's exact `404` body `bootstrap unavailable`. Generic HTTPS websites, certificate errors, redirects and plain-IP identities are not proof of a valid short URL handler.

Example Linux/macOS command **shape** (not a real ticket; the product supplies the handle):

```bash
(drlink_bootstrap=$(curl -fsSL https://bootstrap.example.com/i/<opaque22charhandle>) && printf '%s\n' "$drlink_bootstrap" | sudo bash)
```

Windows downloads `/i/<handle>?platform=windows` and checks its expected stage-1 SHA-256 before PowerShell execution. For the verified `remote.xdr.ooo` benchmark with a 22-character handle, generated commands measured **192 characters Linux/macOS** and **483 characters Windows**; the regression bounds are respectively **<=200** and **<=500**. The lengths vary with DNS name; these are reference-host benchmarks, not a universal ceiling.

**No silent long-command fallback:** when a trusted short URL cannot be qualified, the beginner command fails *before creating any ticket*, explains the DNS/TLS/443/edge-route prerequisite, and does not emit several thousand characters of `zt1`. The advanced backend `frp-create-client --one-line --long-bootstrap` remains available only when the operator explicitly selects the private-CA workflow; it retains CA fingerprint and installer integrity checks. Do not present that internal flag as a separate public `drlink` command.

The `/i/<opaque22charhandle>` handle resolves the internal `bt1.<id>.<secret>` credential. The 256-bit bootstrap secret is hashed at rest; the server retains only the encrypted wrap necessary to emit the stage-1 script (server token, or mode-0600 `bootstrap/bt1-wrap.key` when no token is configured). GET does not bind/consume; successful enrollment consumes atomically. The handle and `bt1` are short-lived credentials: never copy them into unredacted logs.

**SSH usernames are optional connection-hint metadata, not tunnel/enrollment prerequisites.** A guided prompt may be skipped; the backend must not demand or invent a username. For a routed LAN service, the Server and Agent must preserve the signed destination (for example `192.168.219.125:22`) and stable public port, instead of representing that LAN target as Agent `this-host`/127.0.0.1.

See [Zero-Touch regression control](ZERO_TOUCH_REGRESSION_CONTROL.md) for the root-cause table, explicit advanced/private-CA behavior, test matrix, existing-install migration and exact-HEAD live acceptance rules. Historical v2.1.3 `bootstrap_hostname` opt-in and automatic long `zt1` fallback tests do **not** define the v2.4 beginner default.

## Trust boundary

```text
DRLink Agent
   |
   | publicly trusted HTTPS (stock OS trust)
   v
Operator reverse proxy (Caddy / nginx / LB)
   |
   | private / loopback upstream
   v
Data Relay Link allocator
   |
   +-- GET  /i/<opaque>          generic bootstrap script (no ticket consume)
   +-- GET  /ca.crt              Private CA certificate (existing)
   +-- POST /bootstrap/redeem    first-machine bind (existing)
   +-- POST /enroll              enrollment (existing)

after enrollment:

DRLink Agent
   |
   | existing Data Relay Link Private CA
   v
Management plane
```

Data Relay Link does **not** issue, renew, or store the public bootstrap
certificate. The operator owns DNS, public TLS, and the reverse proxy.

## Configuration

```bash
sudo drlink set server bootstrap-hostname bootstrap.example.com
sudo drlink unset server bootstrap-hostname
sudo drlink show status
```

`bootstrap_hostname` is separate from `public_hostname`:

| Field | Meaning |
|---|---|
| `public_hostname` | Published-service access alias (`ssh -p 6000 user@fw.example.com`) |
| `bootstrap_hostname` | Public TLS Zero-Touch short URL entry hostname |

Setting `bootstrap_hostname` does **not** create DNS records, open firewall
ports, configure NAT, invoke ACME, or restart FRP services.

## Operator responsibilities

1. Create DNS for the bootstrap hostname
2. Terminate publicly trusted HTTPS on an operator reverse proxy
3. Renew the public certificate
4. Proxy only the required allocator paths (see below)

## Data Relay Link responsibilities

1. Serve `GET /i/<opaque-ticket>`
2. Validate tickets without consuming them on GET
3. Keep Enrollment Profile server-side
4. Preserve Private CA redeem/enroll flow
5. Prefer short URL generation by default when publicly trusted HTTPS is qualified; otherwise return an actionable no-ticket error
6. Keep explicit advanced `--long-bootstrap` pinned-CA `zt1`, legacy env and manual enrollment working

## Minimum public proxy allowlist

Do **not** proxy `/` wholesale to the allocator.

Required for short-URL bootstrap delivery:

```text
GET /i/<opaque-ticket>
```

Required for the reused enrollment protocol (when clients reach the allocator
through the same public edge, for example private-IP / NAT deployments):

```text
GET  /ca.crt
POST /bootstrap/redeem
POST /enroll
```

Optional health check:

```text
GET /healthz
```

In Direct mode with a publicly reachable allocator (`IP:6099` or equivalent),
the reverse proxy may expose **only** `/i/` and leave redeem/enroll on the
existing Private CA allocator URL embedded in the bootstrap script.

### nginx example

The `/i/<ticket>` path contains a short-lived credential. The copy/paste default
below turns **off** access logging for that location so the raw URI never hits
operator access logs. (Alternatively, an explicitly verified sanitized log
format that rewrites `/i/...` to `/i/<redacted>` is acceptable.)

```nginx
server {
    listen 443 ssl http2;
    server_name bootstrap.example.com;

    # Operator-managed publicly trusted certificate
    ssl_certificate     /etc/ssl/bootstrap.example.com/fullchain.pem;
    ssl_certificate_key /etc/ssl/bootstrap.example.com/privkey.pem;

    location ~ ^/i/[^/?#]+$ {
        # Required default: do not log the raw /i/<ticket> credential URL.
        access_log off;
        proxy_pass https://127.0.0.1:6099;
        proxy_ssl_verify off;   # upstream is project Private CA on loopback
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    # Include these only when the public edge also fronts redeem/enroll:
    location = /ca.crt {
        proxy_pass https://127.0.0.1:6099;
        proxy_ssl_verify off;
        proxy_set_header Host $host;
    }
    location = /bootstrap/redeem {
        proxy_pass https://127.0.0.1:6099;
        proxy_ssl_verify off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
    location = /enroll {
        proxy_pass https://127.0.0.1:6099;
        proxy_ssl_verify off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    location / {
        return 404;
    }
}
```

### Caddy example

If the operator enables Caddy access logging, `/i/<ticket>` **must** be excluded
or redacted. The complete short URL is a short-lived credential; raw URI logging
at the operator edge defeats allocator-side redaction. Data Relay Link does not
manage the reverse proxy — access-log policy remains an operator responsibility.

```caddy
bootstrap.example.com {
    @short_url path_regexp i ^/i/[^/?#]+$
    @allowed {
        path_regexp i ^/i/[^/?#]+$
        path /ca.crt /bootstrap/redeem /enroll /healthz
    }
    # When access logging is enabled, skip or redact @short_url so the ticket
    # never appears in operator logs. Do not log the raw request URI for /i/.
    handle @allowed {
        reverse_proxy https://127.0.0.1:6099 {
            transport http {
                tls_insecure_skip_verify
            }
        }
    }
    handle {
        respond 404
    }
}
```

`tls_insecure_skip_verify` applies only to the operator proxy's **loopback**
upstream to the Private CA allocator. DRLink Agents still use stock OS trust to the
public bootstrap hostname. Do not put `curl -k` in client bootstrap commands.


## Ticket lifecycle

```text
GET /i/<ticket>          → no consume, no machine bind
POST /bootstrap/redeem   → first-machine bind
POST /enroll success     → atomic consume / completed_at (single-use)
```

Treat `/i/<opaque-ticket>` as sensitive until used, expired, or revoked.

### v2.4 stable bounded issuance contract

Configuration/deployment intent and ticket issuance are separate. Applying a `ConfigurationBundle` may create enrollment plans but creates **zero** raw Zero-Touch tickets.

Server-enforced limits:

```text
max tickets per issuance request = 10
max active unused tickets        = 10
use count per ticket              = 1
default TTL                       = 1 hour
maximum TTL                       = 24 hours
```

If 3 valid unused tickets already exist, the next issuance may create at most 7.

Each ticket is unique and bound to one intended enrollment context. A reusable shared credential with a count of 10 is not allowed.

Raw ticket/install URL is shown once at issuance. Persistent server state stores the verifier/hash and non-secret lifecycle metadata, not a redisplayable raw ticket.

Successful enrollment atomically consumes the credential so concurrent double-use cannot create two Managed Hosts. Expired/revoked tickets leave the active-unused count. Ticket expiry/revocation never disconnects a DRLink Agent that has already completed enrollment.

Reinstall/recovery never reuses a consumed ticket; use the supported recovery/re-enrollment flow.

YAML fields, hidden CLI flags, or APIs cannot raise these server-side ceilings.

## Archived v2.1.3 Real E2E evidence (historical only)

Recorded Short URL Real E2E (public TLS via operator edge / cloudflared) against
production-equivalent tree `091f9a99b5e8d648099da97457781bcd24980142`. Candidate
`011c8aaa3be833ea411546002f1d4579953a7b86` differs only in tests, docs, version
metadata, release metadata, and checksums — not Short URL production behavior.
Evidence reused by code equivalence; Real E2E was not re-run solely for the
metadata bump.

```text
RELEASE=2.1.3
BASELINE_LINUX=PASS
AMAZON_LINUX_2023=PASS
ROCKY_LINUX_8_10=PASS
PUBLIC_TLS_STOCK_OS_TRUST=PASS
SHORT_URL_GENERATION=PASS
ZERO_TOUCH_ENROLLMENT=PASS
FIRST_MACHINE_BINDING=PASS (automated suite; not in Real E2E harness)
TICKET_SINGLE_USE=PASS (automated suite; not in Real E2E harness)
MULTI_SERVICE=PASS (automated suite; Real E2E used --ssh profile)
MANAGEMENT_ONLY=PASS (automated suite; not in Real E2E harness)
REBOOT_RECONNECT=PASS
INVALID_TLS_FAIL_CLOSED=PASS
ZT1_FALLBACK=PASS
TESTED_PRODUCTION_HEAD=091f9a99b5e8d648099da97457781bcd24980142
CANDIDATE_HEAD=40bc05967ebfd93c3723a8edff206967c4711c35
EVIDENCE_REUSED_BY_CODE_EQUIVALENCE=YES
EVIDENCE_DIRS=
  e2e-reports/short-url-e2e-20260904T153344Z (baseline-linux)
  e2e-reports/short-url-e2e-20260904T153050Z (amazon-linux-2023)
  e2e-reports/short-url-e2e-20260904T153202Z (rocky-linux-8.10)
```

Unit/Docker suite PASS is not a substitute for the Real E2E platform rows above.

## single-443 note

Do **not** replace the Private CA leaf used by `/~!frp` / WSS. Public TLS for
bootstrap terminates on the **operator** reverse proxy. The in-project
single-443 frontend allowlist may forward `/i/...` to the allocator when an
outer edge proxies into it, but that frontend continues to present the project
Private CA identity.

## Failure behavior

If the bootstrap public certificate is invalid/expired/untrusted:

- short URL fetch fails closed under stock OS trust
- no Managed Host is created
- ticket is not completed
- management plane is unaffected
- explicit advanced `--long-bootstrap` with pinned-CA `zt1` still works; the default must not silently select it
