# Zero-Touch Bootstrap: v2.4 current UX and Short URL internals

> **Current contract:** `ZT-P0-CONTRACT-20261026`, [regression causes and release gates](ZERO_TOUCH_REGRESSION_CONTROL.md).
> **Status:** normative for v2.4 development; real installed-product acceptance is still required. This document specifies the only supported new Zero-Touch command generation modes. Previously issued opaque package commands are not supported; newly issued commands always use the short-handle bootstrap.

## Current beginner-facing behavior

The standard `set enrollment zero-touch` journey **defaults to a short, copyable HTTPS launcher**. A publicly trusted `bootstrap_hostname` or independently qualified `public_hostname` / `public_url_host` uses stock OS trust and DRLink's exact invalid-handle `404 bootstrap unavailable` probe. **DNS is optional:** when no qualified public short-URL hostname exists, a numeric-IP bootstrap endpoint with the verified local Private CA and matching IP SAN is an eligible compact route. This endpoint may be derived from the Server's configured public IP even when the allocator URL remains an FQDN, but only if the local Server leaf is signed by that CA and covers **both** the FQDN and numeric IP. In that route the Agent receives only the public CA first, checks its DER SHA256 against the issuer's command, and sends its one-time handle only after strict CA-verified HTTPS succeeds. Neither a generic HTTPS 404 nor an arbitrary IP address constitutes bootstrap trust.

Example Linux/macOS command **shape** (not a real ticket; the product supplies the handle):

```bash
(drlink_bootstrap=$(curl -fsSL https://bootstrap.example.com/i/AAAAAAAAAAAAAAAAAAAAAA) && printf '%s\n' "$drlink_bootstrap" | sudo bash)
```

Windows downloads `/i/<handle>?platform=windows` and checks its expected stage-1 SHA-256 before PowerShell execution. For the verified `remote.xdr.ooo` benchmark with a 22-character handle, generated commands measured **192 characters Linux/macOS** and **483 characters Windows**; the regression bounds are respectively **<=200** and **<=500**. The lengths vary with DNS name; these are reference-host benchmarks, not a universal ceiling.

**No silent long-command fallback:** the beginner CLI qualifies the public-DNS or Private-CA numeric IP bootstrap **before collecting services** and before issuing a ticket. If neither is safe, it reports the missing certificate/IP-SAN or public-TLS prerequisites. There is no legacy fallback or opaque package decoder. Unsafe bootstrap endpoints fail before ticket issuance.

**Private-CA numeric IP threat boundary:** on Linux/macOS, a public `/ca.crt` is retrieved through an unauthenticated initial TLS socket and accepted *only* if its DER SHA256 equals the operator-pinned fingerprint. All handle-bearing requests then use `curl --cacert` and verify the certificate's IP SAN. On Windows the certificate-only GET uses `curl.exe --insecure` because the OS does not yet trust that CA; this GET contains **no handle or secret**. The pinned fingerprint must match before a separate strict `--cacert` request downloads stage-1, and stage-1 is SHA256-checked before execution. No credential-bearing download disables TLS validation. The IP reference lengths are bounded separately from the public-DNS baseline: Linux/macOS <=900 characters, Windows <=1500 characters for a typical IPv4 host with a 22-character handle.

The `/i/AAAAAAAAAAAAAAAAAAAAAA` handle resolves the internal `bt1.<id>.<secret>` credential. The 256-bit bootstrap secret is hashed at rest; the server retains only the encrypted wrap necessary to emit the stage-1 script (server token, or mode-0600 `bootstrap/bt1-wrap.key` when no token is configured). GET does not bind/consume; successful enrollment consumes atomically. The handle and `bt1` are short-lived credentials: never copy them into unredacted logs.

**Zero-Touch never asks for, accepts or stores an SSH login username.** The tunnel needs only its target host and port; SSH authentication belongs to the SSH client. For a routed LAN service, the Server and Agent must preserve the signed destination (for example `192.168.219.125:22`) and stable public port, instead of representing that LAN target as Agent `this-host`/127.0.0.1.

See [Zero-Touch regression control](ZERO_TOUCH_REGRESSION_CONTROL.md) for the root-cause table, explicit advanced/private-CA behavior, test matrix, existing-install migration and exact-HEAD live acceptance rules. Legacy long-form command syntax is unsupported and is not part of the current CLI.

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
public IP for the first CA-pinned bootstrap stage, provided the leaf contains
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
5. Prefer short URL generation by default when publicly trusted HTTPS is qualified; otherwise return an actionable no-ticket error
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
