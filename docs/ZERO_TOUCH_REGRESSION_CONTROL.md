# Zero-Touch regression root causes and release-prevention contract

> **Contract ID:** `ZT-P0-CONTRACT-20261026`
> **Applies to:** Data Relay Link v2.4 development and all later onboarding changes.
> **Authority:** Product Master + CLI/AI Master; the current contract in this file governs the Zero-Touch user-journey acceptance tests. Prior version-specific evidence is historical, never acceptance for a different installed Source HEAD.
> **Scope:** single and bulk compact bootstrap commands, interactive guided CLI, TLS trust, token issuance, Server/Agent target projection, generated installers, actual external-user E2E.
> **Tracking:** [P0 Draft PR #222](https://github.com/datarelay-labs/datarelay-link/pull/222), [Issue #165](https://github.com/datarelay-labs/datarelay-link/issues/165). A Draft PR or machine-only PASS is not installed-product acceptance.

## Normative short-only contract (2026-11-24)

**ZT-P0-CONTRACT-20261026 — short-only target (owner revision 2026-11-24).** One URL, one opaque one-time ticket, one immutable authenticated enrollment manifest. Single and bulk enrollment, CLI, UI and AI guidance share one launcher per OS. No inline configuration, installer body, encoded package or embedded verification program. At the reference origin `remote.xdr.ooo` with a 22-character handle, final acceptance requires Linux/macOS <= 100 characters and Windows <= 200 characters, with the same size budget for equivalent numeric-IP origins. Longer authorities may add only their literal URL length. Private CA and numeric IP remain supported through independently established trust (OS trust or a qualified, independently authenticated bootstrap verifier); never trust a fingerprint obtained solely from an unauthenticated endpoint. If no trusted short path is available, fail before collecting services and ticket issuance. Windows must verify stage-1 before execution; all platforms must preserve artifact integrity, one-time enrollment, signed destination and fail-closed behavior. This is the mandatory target, not a claim that current installed renderers meet it. No exception budget for inline trust programs. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md`.

- The Server keeps immutable enrollment inputs and qualified installer references/digests in an authenticated manifest, bound to the one-time handle, expiry, platform and intended Server. GET does not consume; successful enrollment consumes atomically and binds the first machine. The manifest is data, not executable code; no private key or long-lived credential is embedded.
- Bootstrap code and validation logic are delivered by an independently authenticated distribution/trust path, not repeated in the operator command. Public HTTPS must verify stock trust and the exact `/i/invalid-qualification-probe` response `404 bootstrap unavailable`; do not follow credential-bearing redirects. Private CA: verify the independently supplied CA fingerprint without any credential, validate certificate IP SAN, then use strict TLS (e.g. `--cacert`); a pre-established trusted verifier can do these operations internally. A hash from the same unauthenticated download is not independent trust. No TLS weakening or global CA installation.
- Download completely before executing; failed or empty downloads must fail without invoking installation. Windows must retain independent stage-1 hash/signature verification before PowerShell execution. Verify immutable installer SHA256 before execution. Do not use a bare pipeline that masks fetch errors.
- Verify signed LAN destinations, stable service identity and reserved public endpoint. SSH account authentication is not an enrollment prerequisite.
- **Release blocker:** current renderers and existing compatibility/security tests are not evidence of the revised length target. Replace the inline verifier with a trusted short bootstrap mechanism, then require the exact generated command length on every OS, public DNS and numeric-IP paths, single/bulk and all public surfaces. Never increase a length cap to make a test pass. Preserve immutable historical receipts in Git history rather than presenting prior command shapes as supported alternatives.

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
| Qualified real DNS + DRLink `/i/` 404 signature | Short command within the revised reference bounds on Linux/macOS/Windows; TLS verified; real ticket installation succeeds | `tests/test-zero-touch-operator-command-bound.py`; `tests/test-zero-touch-short-url.sh`; U-009/O-002 real external E2E |
| Explicit `bootstrap_hostname`, expired/wrong certificate | Generated command may exist, but stock client fetch MUST fail; no unsafe bypass or consumed ticket | TLS negative suite + clean external client |
| Generic HTTPS 404 or unrelated web application | Refuse false short-URL discovery, no ticket | Qualification probe negative test |
| DNS configured but no public trusted `/i/` route | Use CA-pinned numeric IP route when the local Server certificate and CA qualify; otherwise fail before collecting services, no default long command | IP fallback and original default-no-long tests |
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
