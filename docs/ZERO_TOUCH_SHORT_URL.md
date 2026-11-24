# Zero-Touch Bootstrap: v2.4 current UX and Short URL internals

> **Current contract:** `ZT-P0-CONTRACT-20261026`, [regression causes and release gates](ZERO_TOUCH_REGRESSION_CONTROL.md).
> **Status:** normative for v2.4 development; real installed-product acceptance is still required. This document specifies the only supported new Zero-Touch command generation modes. Previously issued opaque package commands are not supported; newly issued commands always use the short-handle bootstrap.

## Short-only beginner-facing contract

**ZT-P0-CONTRACT-20261026 — short-only information contract (owner revision 2026-11-24).** Zero-Touch carries only the bootstrap invocation, one Server HTTPS URL, and one opaque 22-character one-time enrollment ticket in the URL (or ticket alone if the trusted Server is already configured). The ticket resolves the Enrollment ID; never duplicate it. An independently supplied trust anchor or artifact digest is permitted only when indispensable for first trust or pre-execution integrity and not already available to the trusted verifier. All other data belongs in the authenticated immutable Server enrollment manifest or trusted bootstrap implementation. Single/bulk, CLI/UI/AI and all OS paths obey the same field allowlist; use the shortest safe invocation, not an arbitrary character budget. Private CA/numeric IP requires independently established trust; if no safe short path qualifies, stop before collecting services and ticket issuance. Preserve Windows stage-1 verification before execution, strict TLS, artifact integrity, one-time binding and signed LAN destination. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for the authoritative field table, illustrative command forms and structural acceptance. This is a target, not an installed-product claim.

The required fields, conditional digest exception, precise command examples and server-only manifest fields are defined in the [authoritative information allowlist](ZERO_TOUCH_REGRESSION_CONTROL.md#allowed-command-information-normative). No character limit substitutes for checking that allowlist.

The `/i/<handle>` endpoint selects the immutable authenticated enrollment manifest. The Server owns configuration and ticket state; the authenticated bootstrap implementation owns all validation and installation. Handle-bearing GET does not consume the ticket. Successful enrollment binds the first machine and consumes it atomically. Redact the handle and internal credentials from logs.

For a numeric IP, validate the independently trusted CA and certificate IP SAN before transmitting the handle; use strict TLS such as `--cacert` inside the trusted verifier. Windows additionally checks stage-1 SHA256 or an independently trusted signature before execution. Qualified public HTTPS remains the preferred first-install entrypoint. No inline verifier or alternative larger command is accepted by the revised target. If trust is not ready, stop before issuing a ticket. No SSH account is required for the tunnel; preserve signed LAN destination and public port.

Current installed implementations require migration and exact-HEAD qualification before they can claim this target. See [Zero-Touch regression control](ZERO_TOUCH_REGRESSION_CONTROL.md).

## Install-time TLS readiness (no ticket issued)

A successful Server installation is **not** a declaration that public-DNS
Zero-Touch is ready. On the Server, the installation completion report runs a
read-only Linux Zero-Touch prerequisite check and prints either:

- `Zero-Touch HTTPS readiness: READY (read-only, no ticket issued)`
- `Zero-Touch HTTPS readiness: READY (numeric IP + pinned Private CA; read-only, no ticket issued)`
- `Zero-Touch HTTPS readiness: NOT_READY (no ticket issued)` with the concrete
  certificate/URL problem and recovery action.

Public-DNS Zero-Touch requires independently OS-trusted HTTPS for
`/i/invalid-qualification-probe` (exact `404 bootstrap unavailable`) **and**
for the configured Agent installer URL (authenticated `HEAD 200`; if the
artifact handler rejects HEAD with `405` or `501`, an authenticated, bounded
`GET 200` is accepted instead; redirects and TLS errors remain failures). A valid DNS A record,
matching SAN, or private Data Relay Link CA **alone is insufficient**.
The Server installer does not silently disable TLS verification, issue ACME
certificates, or consider a Private-CA DNS endpoint publicly trusted.
If neither the publicly trusted FQDN nor the independently verified
numeric-IP/Private-CA route is ready, Server/FRP installation can complete,
but **Zero-Touch issuance is blocked**. With a privately issued FQDN leaf,
the Server can retain its existing allocator hostname and use its configured
public IP for the trusted short bootstrap verifier, provided the leaf contains
both SANs. This is not a claim that public FQDN TLS gained OS trust. Run `sudo drlink set enrollment zero-touch`
to repeat the pre-ticket check after correcting public TLS.

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
5. Issue only the short launcher after independently authenticated bootstrap trust is qualified; otherwise return an actionable no-ticket error
6. Issue short-handle commands only; reject obsolete package inputs. Preserve independent interactive Manual Enrollment.

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
- single and bulk enrollment issue only a short handle; obsolete package parsing and issuance have been removed
