# Data Relay Link — Internet Access / Controlled Egress

> **Document role:** Protocol and security behavior for the Internet Access plane
> **Status:** v2.4.0 target architecture; implementation qualification pending
> **Policy model:** BLACKLIST / WHITELIST Internet Access policy using the shared v2.4 control plane
> **Public SSOT:** `PRODUCT_MASTER.md` + `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`

## 1. Purpose

Internet Access is Data Relay Link's controlled outbound connectivity plane.

It allows protected/restricted hosts to reach only explicitly approved Internet destinations through a Data Relay Link server.

`Controlled Egress` remains the technical capability name. The normal CLI/resource name is `Internet Access`.

## 2. Base flow

```text
Protected host
    ↓
HTTP_PROXY / HTTPS_PROXY
    ↓
Data Relay Link Internet Access gateway
    ↓
source + destination + protocol/port policy
    ↓
approved Internet destination
```

The base HTTP/HTTPS path remains agentless on the protected host.

### 2.1 Protected-host proxy configuration

The normal user journey is to configure standard application proxy settings on the protected host to point at the Data Relay Link Internet Access endpoint. Data Relay Link must not require its Remote Access Agent on that host merely for HTTP/HTTPS Internet Access.

Representative shell configuration:

```bash
export http_proxy=http://<DRLINK_SERVER>:<INTERNET_ACCESS_PORT>
export https_proxy=http://<DRLINK_SERVER>:<INTERNET_ACCESS_PORT>
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
proxy_bypass="${no_proxy:-}"
if [ -n "${NO_PROXY:-}" ]; then
  proxy_bypass="${proxy_bypass:+${proxy_bypass},}${NO_PROXY}"
fi
proxy_bypass="${proxy_bypass:+${proxy_bypass},}127.0.0.1,localhost"
export no_proxy="$proxy_bypass"
export NO_PROXY="$proxy_bypass"
```

Merge and preserve the pre-existing `no_proxy` and `NO_PROXY` bypass entries needed for management endpoints or internal services, append localhost, then export the same merged list under both casings so application precedence cannot drop an existing bypass.

Applications that use an application-specific standard proxy setting may use that instead, but it must resolve to the same Data Relay Link endpoint. For example, APT may use its normal `Acquire::http::Proxy` / `Acquire::https::Proxy` configuration when required by the target distribution/application behavior.

A per-command proxy override such as `curl -x ...` is useful for diagnostics, but it is not sufficient evidence that the protected-host user workflow works as designed.

## 3. Policy authority

The authoritative policy is not `egress-control.json`.

v2.4.0 target authority:

```text
/var/lib/drlink/drlink.db
```

Internet Access uses Network Objects/Groups, Service Objects/Groups, and the shared BLACKLIST / WHITELIST policy model.

Example semantics:

```text
No Policy / No Rules -> effective ALLOW
BLACKLIST + matching enabled Rule -> DENY
BLACKLIST + no match -> ALLOW
WHITELIST + matching enabled Rule -> ALLOW
WHITELIST + no match -> DENY
```

Rules are not ordered and do not carry per-rule ALLOW/DENY actions. Enforcement can be disabled without deleting the configured Mode or Rules.

## 4. Destination types

Supported target architecture:

```text
FQDN
public Host IP
public CIDR
compatible Object Group
```

FQDN remains the preferred mode for services whose addresses change through DNS/CDN infrastructure.

A public IP/CIDR rule is explicit policy, not a bypass around FQDN security.

Runtime security order for Internet Access:

```text
parse request
→ canonicalize authority (hostname or IP literal)
→ resolve once if hostname
→ validate candidate IP safety (any unsafe ⇒ deny all)
→ evaluate canonical Internet Access policy using hostname + candidate IPs
→ connect only to the authorized candidate set (no re-resolve)
```

A CIDR/IP destination rule may authorize a hostname when a validated resolved
address falls inside that selector. Authorization of one candidate never widens
authorization to other candidates outside the allowed IP/CIDR scope.

FQDN rules continue to authorize the requested hostname's validated address set.
FQDN rules never authorize a direct IP literal merely because DNS for that FQDN
could produce the address.

Internet Access v2.4 has a TCP/HTTP/HTTPS CONNECT datapath only. UDP Service
Objects cannot be selected by Internet Access.

## 5. Source types

Internet Access Source accepts context-valid Host/Network Objects and compatible Object Groups.

The base agentless HTTP/HTTPS proxy observes network source identity. Per-host cryptographic identity is not invented where the protected application is simply using a standard proxy.

A Managed Host source selector is therefore address-backed, not cryptographic. It matches only when the proxy peer source IP equals an eligible active address reported for that Managed Host. If a BLACKLIST rule otherwise matches destination and service but this Managed Host source identity cannot be proven, the request is denied fail-closed instead of falling through to BLACKLIST unmatched/ALLOW. NAT may make a selective Managed Host selector ambiguous; use an IP/CIDR selector for the proxy-visible source when that topology must be represented explicitly.

## 6. HTTP

For approved HTTP requests:

1. Parse the absolute target safely.
2. Canonicalize the host.
3. Match source/destination/protocol/port policy.
4. Resolve and validate destination when DNS is required.
5. Connect only to a validated address.
6. Relay application traffic without expanding authorization beyond the matched rule.

Malformed or ambiguous requests fail closed.

## 7. HTTPS CONNECT

For HTTPS proxying:

```text
Application
  ↓
CONNECT approved.example.com:443
  ↓
Data Relay Link policy + DNS/security validation
  ↓
validated exact destination IP
  ↓
end-to-end TLS between application and destination
```

Base Internet Access does not terminate application TLS.

## 8. SNI / host binding

Where the implementation can observe TLS SNI for CONNECT validation, the requested CONNECT host and observed SNI must not be allowed to diverge in a way that bypasses destination policy.

If the implementation cannot safely bind the request to the expected destination identity, fail closed.

## 9. ECH

If Encrypted ClientHello prevents required destination/SNI validation in a security path that depends on it, the connection must not silently bypass the check. The implementation may deny the affected connection unless another verified binding mechanism is available.

## 10. DNS resolution

Destination DNS is resolved by the Data Relay Link server for policy/security decisions.

Preferred sequence:

```text
resolve
→ validate every candidate IP
→ select a validated exact IP
→ connect to that exact IP
```

Policy validation and connection must not use unrelated DNS resolutions that permit rebinding between check and use.

## 11. SSRF and special-address protection

Internet Access must reject unsafe destinations by default, including as applicable:

```text
loopback
private/RFC1918 where the Internet plane must not reach private targets
link-local
multicast
reserved/special-use
IPv6 loopback/link-local/ULA where unsafe
cloud metadata endpoints
169.254.169.254
```

Example:

```text
allowed.example.com
→ DNS returns 169.254.169.254
→ DENY
```

The exact special-address classification must use maintained platform/library semantics and regression tests.

## 12. DNS rebinding resistance

A host that resolves to an allowed public IP during policy evaluation and then to a blocked local address during connection must not succeed.

The validated address is the address actually connected to.

## 13. FQDN canonicalization

At minimum normalize/validate:

```text
case
trailing dot
IDNA/Punycode handling
empty labels
invalid labels
wildcard boundary semantics
public suffix safety where wildcard rules are supported
```

Ambiguity fails closed.

## 14. IP literals

Direct IP literals are allowed only through explicit Host/public Network policy and corresponding safety checks.

An IP literal does not inherit an FQDN allow merely because DNS could map that FQDN to the IP.

Loopback, private, link-local, metadata, multicast, reserved, and other unsafe
literals remain denied regardless of policy.

## 15. Protocol and port

Rules match protocol/port explicitly.

Examples:

```text
HTTPS/443
HTTP/80
TCP/443
```

A destination Object alone never implies all ports.

## 16. Wildcards

If controlled FQDN wildcard support is retained, it is narrow and boundary-aware.

Acceptable concept:

```text
*.githubusercontent.com
```

Unsafe broad forms such as generic public-suffix-wide authorization are rejected.

## 17. Fixed TCP

Fixed TCP supports approved applications that cannot use HTTP/HTTPS proxy semantics.

It must reuse the same Internet Access authorization authority and may not maintain an independent permissive destination list.

Conceptual flow:

```text
protected host
→ Data Relay Link fixed listener
→ source authorization
→ configured destination Object / protocol / port
→ validated destination
→ TCP relay
```

Fixed TCP cannot bypass unsafe destination checks or the effective Internet Access policy outcome.

## 18. Rule timing

Canonical behavior:

> **Policy changes apply immediately to new connections.**

An existing established proxy/TCP connection is not implicitly terminated solely because a later policy edit would deny a new connection.

## 19. Rule creation safety

New Internet Access rules are created disabled at the bottom.

Enabling or moving a rule runs:

```text
context validation
shadow/conflict analysis
policy-impact analysis
access-broadening confirmation when required
```

## 20. Object changes

Object/Object Group mutation can change Internet Access without changing a Rule row.

Example:

```text
external2 before:
  google.com
  naver.com

after:
  google.com
  naver.com
  openai.com
```

If an enabled ALLOW rule references `external2`, adding `openai.com` is access broadening and requires impact analysis/confirmation.

## 21. Shadowing

Overlapping rules are valid.

Example:

```text
10 allow-web   internal1 → external2 → HTTPS/443 → ALLOW
20 block-openai internal1 → openai    → HTTPS/443 → DENY
```

If `openai` becomes a member of `external2`, rule 20 can become shadowed. The operator is warned before the effective behavior is broadened.

## 22. Test/explain

Canonical example:

```text
test internet-access 10.10.10.20 google.com 443 https
```

The result should show:

```text
Source Network Object matches
Destination Network Object matches
Service Object matches
DNS/security validation
Policy Mode / Enforcement
Enabled Rule match / no match
Final effective action
```

`test` is policy explanation unless explicitly documented as a live connection test.

## 23. Audit

Record bounded metadata such as:

```text
timestamp
source address
requested host/address
destination port/protocol
matched rule
action
safe failure reason
configuration revision
```

Do not log application payloads, proxy credentials, destination TLS contents, or sensitive URL query strings by default.

## 24. Resource protection

The gateway applies reasonable:

```text
connect timeout
idle timeout
maximum concurrency
header/request size limits
defensive parsing
rate/resource protections where needed
```

Failure to allocate or validate resources must not convert into an allow bypass.

## 25. Runtime compilation

Internet Access runtime policy is compiled from the SQLite revision and activated atomically.

System status must report the active revision.

A DB/runtime revision mismatch is not healthy.

## 26. Backup and restore

Internet Access policy is backed up through the consistent control-plane SQLite snapshot.

Derived runtime files are regenerated after restore and are not the recovery authority.

## 27. Legacy transition

Legacy `internet-profile`, Egress Profile, and authoritative `egress-control.json` semantics are development-history concepts and are not the v2.4.0 target control model.

The implementation phase migrates or replaces them without dual authoritative state.

## 28. Real E2E

Minimum final qualification includes:

```text
approved HTTP destination                  PASS
approved HTTPS CONNECT                     PASS
unapproved destination                     DENY
wrong destination port                     DENY
unapproved source                          DENY
public Host/CIDR explicit policy            PASS where supported
loopback/private/link-local/metadata       DENY
DNS rebinding-style attempt                 DENY
IP literal bypass                           DENY
wildcard boundary bypass                    DENY
malformed CONNECT                           DENY
BLACKLIST / WHITELIST semantics             PASS
Enforcement disable/enable                   PASS
object-change impact                        PASS
restart                                     policy preserved
backup/restore                              policy preserved
DB/runtime mismatch                         fail closed / surfaced
```

Real application qualification includes `curl`, `wget`, `git`, `apt`, and representative vendor/API HTTPS use cases where applicable.

For final E2E, prove the complete proxy user path without disrupting the host's existing direct Internet connectivity:

```text
protected host configured with standard proxy settings pointing to Data Relay Link
→ effective proxy configuration verified
→ approved curl/wget/git/apt traffic observed through Data Relay Link
→ unapproved destination / wrong port is denied through the same proxy path
→ remove an actually required application destination
→ the corresponding application workflow fails through policy
→ restore policy
→ the same application workflow succeeds again
```

`curl` alone does not satisfy the real-application matrix when `wget`, `git`, and `apt` are applicable to the selected qualification host. Policy/explain output alone is never live traffic evidence. The evidence must retain the effective proxy endpoint/configuration, application result, and Data Relay Link audit/source observation proving that the tested request traversed the configured proxy. Do not disable or reconfigure the host's direct Internet path merely to manufacture a test precondition.

For APT specifically, qualify a real repository/update workflow using explicitly allowed repository FQDNs. Do not use broad wildcard authorization merely to obtain PASS. Use strict update failure semantics such as `apt-get -o APT::Update::Error-Mode=any update`; if that option is unavailable, explicitly detect any failed required index and count it as FAIL even when APT exits 0. Remove at least one destination actually required by that update path, correlate the failed required index with the Data Relay Link proxy DENY audit, then restore that destination and prove recovery.

Fixed TCP remains the separate solution for proxy-unaware applications and is not a substitute for the HTTP/HTTPS proxy-aware application qualification above.
