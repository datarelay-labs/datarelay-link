# Zero-Touch regression root causes and release-prevention contract

> **Contract ID:** `ZT-P0-CONTRACT-20261026`
> **Applies to:** Data Relay Link v2.4 development and all later onboarding changes.
> **Authority:** Product Master + CLI/AI Master; the current contract in this file governs the Zero-Touch user-journey acceptance tests. Prior version-specific evidence is historical, never acceptance for a different installed Source HEAD.
> **Scope:** single and bulk compact bootstrap commands, interactive guided CLI, TLS trust, token issuance, Server/Agent target projection, generated installers, actual external-user E2E.
> **Tracking:** [P0 Draft PR #222](https://github.com/datarelay-labs/datarelay-link/pull/222), [Issue #165](https://github.com/datarelay-labs/datarelay-link/issues/165). A Draft PR or machine-only PASS is not installed-product acceptance.

## Normative short-only contract (2026-11-24)

**ZT-P0-CONTRACT-20261026 — short-only information contract (owner revision 2026-11-24).** Zero-Touch carries only the bootstrap invocation, one Server HTTPS URL, and one opaque 22-character one-time enrollment ticket in the URL (or ticket alone if the trusted Server is already configured). The ticket resolves the Enrollment ID; never duplicate it. An independently supplied trust anchor or artifact digest is permitted only when indispensable for first trust or pre-execution integrity and not already available to the trusted verifier. All other data belongs in the authenticated immutable Server enrollment manifest or trusted bootstrap implementation. Single/bulk, CLI/UI/AI and all OS paths obey the same field allowlist; use the shortest safe invocation, not an arbitrary character budget. Private CA/numeric IP requires independently established trust; if no safe short path qualifies, stop before collecting services and ticket issuance. Preserve Windows stage-1 verification before execution, strict TLS, artifact integrity, one-time binding and signed LAN destination. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for the authoritative field table, illustrative command forms and structural acceptance. This is a target, not an installed-product claim.


### Allowed command information (normative)

| Item | Requirement | Representation / length |
|---|---|---|
| Bootstrap invocation | Required; fixed platform-approved invocation and minimal download/execute safety syntax | No serialized configuration or inline verifier |
| Server HTTPS URL | Required for a new machine; omit only when an authenticated Server is already configured | `https://` (8), literal DNS/IP authority (variable), `/i/` (3), ticket (22) |
| Enrollment ticket | Required once; opaque Base64URL handle encoding 128 bits of randomness | 22 characters, maps to the server-side Enrollment ID; no separate ID or raw internal credential |
| Independent trust anchor / digest | Conditional only; omit if independently available to the verifier. Required when security would otherwise be lost; never fetch an anchor from the same unauthenticated channel | SHA-256 64 hex or 43 unpadded Base64URL characters; only the necessary, typed CA pin and/or stage-1 digest, not arbitrary metadata |

The three required logical items are invocation, Server address and ticket. The last two normally form a single URL argument. Any conditional digest is independently supplied, scoped to its purpose, and consumed by a trusted verifier. Platform is selected by the launcher (no extra user-entered platform data); URL routing syntax is fixed, not an extensible configuration query. No CLI argument for Enrollment ID, service/host settings, installer URL/version, FRP options, credentials, manifest body, certificate body or executable verification code.

### Illustrative command shapes (not deployed syntax)

For the example authority `remote.xdr.ooo` (14 characters) and a fictitious 22-character ticket, the URL is 47 characters. The examples are design references, not promises of installed executables or acceptance on a clean machine.

- Public HTTPS, Bash/Zsh, complete nonempty fetch before execution (95 characters):
  `s=$(curl -qfsS https://remote.xdr.ooo/i/AAAAAAAAAAAAAAAAAAAAAA)&&[ -n "$s" ]&&sudo bash <<<"$s"`
- Public HTTPS, POSIX-shell alternative (106 characters):
  `s=$(curl -qfsS https://remote.xdr.ooo/i/AAAAAAAAAAAAAAAAAAAAAA)&&[ -n "$s" ]&&printf '%s\n' "$s"|sudo bash`
- Already trusted/installed verifier with Server URL (66 characters): `sudo drlink enroll https://remote.xdr.ooo/i/AAAAAAAAAAAAAAAAAAAAAA`
- Already trusted/installed verifier and preconfigured Server (41 characters): `sudo drlink enroll AAAAAAAAAAAAAAAAAAAAAA`
- Illustrative independently verified Windows bootstrap executable (68 characters): `drlink-bootstrap.exe https://remote.xdr.ooo/i/AAAAAAAAAAAAAAAAAAAAAA`

Public shell forms require authenticated HTTPS, no redirect, a qualified stage-1, and verified subsequent installer. The Windows helper example is conditional on its independent verification/availability and preserves pre-execution stage-1 verification. Do not claim a fresh Windows/Private-CA machine can run a preinstalled-helper example. Do not make a bare download pipe or unverified remote execution an alternative. Conditional digests add only the exact typed argument syntax and digest length; no universal size ceiling or entitlement to extra bytes.

### Server-side manifest information

Keep these fields in authenticated immutable data bound to the ticket, not operator command text:

| Group | Fields |
|---|---|
| Enrollment identity | Enrollment ID, ticket reference (not raw secret in logs), issuer/Server ID, expiry, first-machine binding and single-use state (transactional state maintained separately) |
| Agent identity and metadata | Requested Agent/Managed Host name, label/group/tags, permitted platform and enrollment profile |
| Connection and trust | Allocator/relay endpoints, transport, CA/certificate references and fingerprints, policy references |
| Artifact integrity | Qualified installer URL, exact immutable source/version, SHA-256 digest, manifest authentication/signature and required stage-1 integrity metadata |
| Remote Services | Service/Network Object IDs, service type, target host/port, reserved public endpoint and signed destination |
| Runtime | Required configuration, capabilities and transport parameters; generate persistent private keys locally on Agent, never embed long-lived private credentials |

### Structural regression oracle

- Compare actual emitted commands against an explicit fixed platform invocation template and the exact allowlisted URL/ticket fields; reject every extra argument, assignment, query/config value, inline code or duplicated ID outside the fixed minimal invocation. Conditional digest arguments are accepted only by the independently trusted verifier and only when needed. No general-purpose shell/script escape hatch.
- Compare rendered byte count to that exact template plus literal permitted data; do not use an arbitrary global or route-specific maximum as the pass condition. A new template requires review of every added token and proof that it is necessary for safety or compatibility.
- Test single and bulk issuance, CLI/UI/AI presentation, all OS/trust routes, positive/negative field injection, independent trust, credential secrecy, failure exit, Windows pre-execution integrity, manifest validation and actual external enrollment. Fail before ticket issuance if a supported safe template cannot be selected. Preserve historical receipts only in Git history.

- The Server keeps immutable enrollment inputs and qualified installer references/digests in an authenticated manifest, bound to the one-time handle, expiry, platform and intended Server. GET does not consume; successful enrollment consumes atomically and binds the first machine. The manifest is data, not executable code; no private key or long-lived credential is embedded.
- Bootstrap code and validation logic are delivered by an independently authenticated distribution/trust path, not repeated in the operator command. Public HTTPS must verify stock trust and the exact `/i/invalid-qualification-probe` response `404 bootstrap unavailable`; do not follow credential-bearing redirects. Private CA: verify the independently supplied CA fingerprint without any credential, validate certificate IP SAN, then use strict TLS (e.g. `--cacert`); a pre-established trusted verifier can do these operations internally. A hash from the same unauthenticated download is not independent trust. No TLS weakening or global CA installation.
- Download completely before executing; failed or empty downloads must fail without invoking installation. Windows must retain independent stage-1 hash/signature verification before PowerShell execution. Verify immutable installer SHA256 before execution. Do not use a bare pipeline that masks fetch errors.
- Verify signed LAN destinations, stable service identity and reserved public endpoint. SSH account authentication is not an enrollment prerequisite.
- **Release blocker:** current renderers and existing compatibility/security tests are not evidence of the revised information contract. Replace the inline verifier with a trusted short bootstrap mechanism, then enforce the exact allowed-field and fixed-template grammar on every OS, public DNS and numeric-IP path, single/bulk and all public surfaces. No character budget can authorize an extra field. Preserve immutable historical receipts in Git history rather than presenting prior command shapes as supported alternatives.

## Historical Agent self-target recovery contract

An earlier installed Agent may retain `127.0.0.1` in `client-state.json`
for an originally signed LAN service, even after the Server has correctly
migrated the destination Network Object. Re-reading that stale file or selecting
the only visible LAN Network Object is **not** a valid recovery algorithm.

The Server's authenticated, client-scoped Remote Service status response carries
an additive per-service `authoritative_target` projection (destination name,
optional bound Client ID, Service Object, target IP/port, and target mode).
An Agent may correct an old bootstrap **only** when all of the following hold:

- The exact Remote Service row is `enrollment_seed=1`, not deleted or operator-modified.
- The Server-authenticated response matches the original public endpoint and Service Object.
- The routed Network Object name is the deterministic enrollment target for
  the Server-provided IP and agrees with the refreshed signed Agent catalog.
- The Server-provided target port agrees with its signed Service Object.
- The old Agent destination is demonstrably self-bound; neither an unrelated
  Managed Host nor an already-routed operator choice may be overwritten.

Before applying a corrected runtime route, the Agent clears its stale
`HEALTHY`/verification state and requires fresh FRP apply/Server acknowledgement.
A concurrent operator edit, missing authenticated ACK, conflicting catalog, or
ambiguous binding must remain unchanged/fail closed. The source-level RED→GREEN
regression is `tests/test-enrolled-routed-target-parity.py`; installed
Server/Agent exact-HEAD :6001 SSH and :6002 HTTPS reachability remain separate
real-environment acceptance requirements.

## Reproducible acceptance matrix

| Scenario | Expected output/behavior | Actual gate |
|---|---|---|
| Qualified real DNS + DRLink `/i/` 404 signature | Short command matching the allowed-field grammar on Linux/macOS/Windows; TLS verified; real ticket installation succeeds | `tests/test-zero-touch-operator-command-bound.py`; `tests/test-zero-touch-short-url.sh`; U-009/O-002 real external E2E |
| Explicit `bootstrap_hostname`, expired/wrong certificate | Generated command may exist, but stock client fetch MUST fail; no unsafe bypass or consumed ticket | TLS negative suite + clean external client |
| Generic HTTPS 404 or unrelated web application | Refuse false short-URL discovery, no ticket | Qualification probe negative test |
| DNS configured but no public trusted `/i/` route | Use a trusted numeric-IP verifier only when independent trust qualifies; otherwise fail before collecting services, no ticket | IP fallback and original default-no-long tests |
| Private-CA-only / numeric IP with matching Server certificate IP SAN | Short launcher via independent trust; CA verified before credential retrieval; Windows stage-1 verified before execution; otherwise no ticket | IP/private-CA issuer + Windows PowerShell negative/positive regression |
| Optional SSH user blank | End-to-end enrollment/tunnel functions; no misleading account inference | Guided and backend user journey |
| LAN SSH remote 6001 | Signed target `192.168.219.125:22`, correct Network Object, preserve 6001, real external SSH banner and session | Server/Agent projection + remote actual traffic |
| LAN HTTPS remote 6002 with target 443 intentionally down | Configuration references consistent, do not fabricate HTTPS PASS; DEGRADED is truthful until listener starts | Server/Agent state inspection |
| Legacy Agent/Server upgrade | Repair only exact mismatched enrollment seed, preserve operator modifications and ports | `tests/test-enrolled-routed-target-parity.py`; upgrade + installed E2E |
| Server config temporarily cleared during A-018 | Restore exact original settings, then compare generated mode with *current default contract* | A-018 lifecycle, U-009 recheck |

## Release gate and evidence obligations

**Document-only, mock-only, unit-only, source-only, CI-only and historical recorded PASS must never close these user requirements.** The release gate requires:

- **Local focused checks:** `python3 tests/test-zero-touch-operator-command-bound.py`, `python3 tests/test-zero-touch-guided-preflight.py` (real public `drlink` preflight-before-identity across Linux/Windows/macOS), `bash tests/test-zero-touch-short-url.sh`, `python3 tests/test-enrolled-routed-target-parity.py`, `python3 tests/test-cli-inventory-selection-journey.py` and `python3 tests/test-zero-touch-doc-contract.py` (the documentation consistency check).
- **Artifact closure:** `bash tests/test-change-closure-artifacts.sh` at the exact product source HEAD; reject `DERIVED_BUNDLE_STALE` or checksum/manifest drift.
- **Installed candidate:** record `drlink system version` Source HEAD for Server and Agent and exact bundle SHA256; external new-user command generated from the actual installed Server, not a copied example or source runner.
- **Real negative/positive:** trusted public TLS, real `/i/<handle>` redemption, one-time binding, service lifecycle, 6000 preservation and 6001 real external SSH. HTTPS :443 behind 6002 may remain legitimately down and must be recorded honestly.
- **User gate:** execute U-009, O-002, A-018 and relevant CLI-008/FCS-002 as actual personas. No silently skipped prerequisite or preexisting config reset. For v2.4 release, both complete 116-ID Full User E2E PASS runs must be on one frozen, installed, verified HEAD.
- **Observability:** redact all raw `bt1`, short handles, OAuth codes and private keys; retain lengths, mode, endpoint/status, exit codes and provenance. Do not retain a readable one-time credential in evidence.

## Disposition / known remaining work

PR #222 contains isolated source and targeted tests, but live Server/Agent upgrades and public :6001 end-to-end acceptance remain separate. The connected DRLink MCP exposes Managed Hosts and, only when AI Access separately authorizes it, the Server itself (Server-self target, PR #237). Whether it can mutate Server-only Network Objects or perform Server deployment depends on that authorization and the execution profile in effect; record the actual capability from receipts, not from this document. A service intentionally not listening on LAN :443 must not be marked an HTTPS relay regression. Mark these outcomes `NOT_RUN`, `BLOCKED_TOOLING`, or `FAIL` from actual receipts; never PASS from a code review.
