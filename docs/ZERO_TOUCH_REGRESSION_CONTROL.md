# Zero-Touch regression root causes and release-prevention contract

> **Contract ID:** `ZT-P0-CONTRACT-20261026`
> **Applies to:** Data Relay Link v2.4 development and all later onboarding changes.
> **Authority:** Product Master + CLI/AI Master; the current contract in this file governs the Zero-Touch user-journey acceptance tests. Prior version-specific evidence is historical, never acceptance for a different installed Source HEAD.
> **Scope:** single and bulk compact bootstrap commands, interactive guided CLI, TLS trust, token issuance, Server/Agent target projection, generated installers, actual external-user E2E.
> **Tracking:** [PR #305](https://github.com/datarelay-labs/datarelay-link/pull/305), [Issue #165](https://github.com/datarelay-labs/datarelay-link/issues/165). A Draft PR or machine-only PASS is not installed-product acceptance.

## Fixed customer entry design (2026-11-24)

**ZT-P0-CONTRACT-20261026 — fixed six-character entry target (owner revision 2026-11-24).** The customer starts with one OS-native command, one HTTPS authority (FQDN or IP), and one six-character root-path file locator. Public and private HTTPS use the same target form. No preinstalled DataRelay software, inline configuration, separate enrollment ID, fingerprint, artifact hash, or installer body in the customer command. All subsequent configuration, downloads, verification, installation, recovery and enrollment belong to the multi-stage Bootstrap; their size and count are unrestricted. The locator is not an enrollment credential. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for exact target templates, the independent enrollment requirement, the explicit initial-transport risk and actual acceptance status. This is a design target, not installed-product qualification.

### Command fields (normative)

| Item | Linux/macOS | Windows (administrator PowerShell) |
|---|---|---|
| Downloader | `curl` | `curl.exe` |
| Download options | `-kfsS` | `-kfsS` |
| Protocol | `https://` | `https://` |
| Server authority | FQDN or IP, with configured port if required | Same |
| Bootstrap filename | `/` followed by one six-character locator | Same |
| Execute downloaded Bootstrap | `\|sudo bash` | `iex(...\|Out-String)` |

The only variable fields are Server authority and Bootstrap filename. Select the OS at Server issuance; all other syntax is fixed by the platform template. Public and private HTTPS use identical fields. No enrollment credential, hash, certificate, installer URL, configuration or other argument in the entry command. Acceptance compares these fields and exact template, not total command length.

Linux/macOS:

```bash
curl -kfsS https://remote.xdr.ooo/A3xK9m|sudo bash
```

Windows (administrator PowerShell):

```powershell
iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9m|Out-String)
```

The examples use a fictitious locator and are not installed-product qualification. The Server selects the OS-specific response at issuance. Permit exactly `[A-Za-z0-9_-]{6}` in the root-path locator, collision-check atomically, reserve existing routes, expire and rate-limit lookups. No second customer command or extra customer-supplied argument. Internal enrollment protocol remains separate.

### Stage boundary and security scope

1. Stage 0: fixed native fetch/execute template, identical for public/private certificates. The operator sends the command through the established customer communication channel. `-k` explicitly disables TLS peer certificate authentication for this initial download. It does not establish server identity or protect against an active replacement response. Later checks cannot retroactively authenticate executed code. This risk must remain visible; do not present the template as security-qualified or silently mark the existing security gate PASS.
2. Stage 1: small, platform-specific entry file; handle ordinary truncated-script cases, clear failure/success output, subsequent artifact retrieval, temporary file cleanup, and retry without destructive side effects. Subsequent files, manifests, scripts and installer payloads have no arbitrary size or count cap. Do not embed long-lived keys or raw enrollment secrets in the publicly retrievable entry file.
3. Stage 2: validate downstream artifacts and use authenticated connections. Establish actual downstream trust independently where required; a CA learned solely from an unauthenticated response is not independently verified. Keep TLS exceptions local to Stage 0; do not change OS trust or disable management-plane TLS validation.
4. Stage 3: redeem a separate high-entropy, expiring, one-time enrollment credential after authorization; bind the authorized identity and destination, consume atomically, preserve existing identity/ports on retries. The six-character locator is only a routing index: knowing it must not grant enrollment. An independent authorization mechanism (e.g. operator approval bound to an agent key, or existing authenticated enrollment context) must be designed and tested; do not claim fully autonomous secure enrollment from the locator alone.

### Acceptance

- Clean Linux, macOS, Windows: one exact OS template, same for public/private HTTPS, no extra customer-supplied arguments. Numeric IP or FQDN; validate the allowed fields and exact invocation.
- Same entry command can be retried after interruption; success requires actual installed identity, authenticated enrollment and working service, not a shell exit code alone. Server-side lookup, capacity, collisions, expiry and concurrent redemption are tested.
- Actual OS runs, installer integrity, independent enrollment authorization, signed service routing and external E2E remain required. The initial unverified execution risk remains a security qualification failure unless separately dispositioned under the applicable release authority. No network attack detection feature is in scope.

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
| FQDN/IP, public/private HTTPS | Exact fixed six-character entry template; actual installation and separately authenticated enrollment | Native OS E2E |
| Invalid/expired locator or unavailable endpoint | No enrollment; clear failure or retry guidance; do not infer success from pipeline exit | Server lookup + retry tests |
| Replacement initial response | Unverified Stage 0 is a recorded security risk; not an authenticated-download PASS | Security qualification |
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
- **Real negative/positive:** public/private entry flow, six-character locator lookup, independent enrollment authorization, one-time binding, service lifecycle, 6000 preservation and 6001 real external SSH. HTTPS :443 behind 6002 may remain legitimately down and must be recorded honestly.
- **User gate:** execute U-009, O-002, A-018 and relevant CLI-008/FCS-002 as actual personas. No silently skipped prerequisite or preexisting config reset. For v2.4 release, both complete 116-ID Full User E2E PASS runs must be on one frozen, installed, verified HEAD.
- **Observability:** redact all raw `bt1`, short handles, OAuth codes and private keys; retain mode, endpoint/status, exit codes and provenance. Do not retain a readable one-time credential in evidence.

## Disposition / known remaining work

PR #222 contains isolated source and targeted tests, but live Server/Agent upgrades and public :6001 end-to-end acceptance remain separate. The connected DRLink MCP exposes Managed Hosts and, only when AI Access separately authorizes it, the Server itself (Server-self target, PR #237). Whether it can mutate Server-only Network Objects or perform Server deployment depends on that authorization and the execution profile in effect; record the actual capability from receipts, not from this document. A service intentionally not listening on LAN :443 must not be marked an HTTPS relay regression. Mark these outcomes `NOT_RUN`, `BLOCKED_TOOLING`, or `FAIL` from actual receipts; never PASS from a code review.
