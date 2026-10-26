# Zero-Touch regression root causes and release-prevention contract

> **Contract ID:** `ZT-P0-CONTRACT-20261026`
> **Applies to:** Data Relay Link v2.4 development and all later onboarding changes.
> **Authority:** Product Master + CLI/AI Master; the current contract in this file governs the Zero-Touch user-journey acceptance tests. Prior version-specific evidence is historical, never acceptance for a different installed Source HEAD.
> **Scope:** default vs advanced bootstrap command, interactive guided CLI, TLS trust, token issuance, Server/Agent target projection, generated installers, actual external-user E2E.
> **Tracking:** [P0 Draft PR #222](https://github.com/datarelay-labs/datarelay-link/pull/222), [Issue #165](https://github.com/datarelay-labs/datarelay-link/issues/165). A Draft PR or machine-only PASS is not installed-product acceptance.

## What regressed (observed)

The operator requested a short one-line Agent enrollment. The installed Server produced a several-thousand-character pinned-private-CA command with no upfront explanation. The `bootstrap_hostname` value was absent even though `remote.xdr.ooo` had externally trusted HTTPS and a functioning `/i/` handler. The previous default-mode tests deliberately expected this long command and reported PASS. In a separate failure, a Zero-Touch LAN service requested `192.168.219.125` but Server/Agent v2.4 projection labeled it `this-host` (127.0.0.1), causing `AUTHORITATIVE_TARGET_MISMATCH` on 6001/6002. LAN SSH port 22 was reachable from the Agent; LAN HTTPS 443 was not yet running, by operator intent.

## Root-cause chain (do not treat any one patch as complete)

| ID | Actual cause | Old false-positive oracle / blind spot | Required prevention |
|---|---|---|---|
| ZT-RC-01 | Short URL was opt-in only via `bootstrap_hostname`; missing field silently selected multi-kilobyte `zt1` fallback | `tests/test-zero-touch-short-url.sh` positively asserted `zt1` for default missing-host and `public_url_host` cases | Default must qualify public HTTPS or emit a clear error **before ticket issuance**; long pinned-CA launcher only under explicit advanced opt-in |
| ZT-RC-02 | Historical short-URL documentation (v2.1.3 Option B) remained written as the current v2.4 default | CLI/AI Master repeated the old opt-in rule; Product Master did not provide a quantitative operator command contract | Link all product/CLI/QA surfaces to this single current contract; mark v2.1.3 behavior historical |
| ZT-RC-03 | A synthetic configured FQDN and a mocked handle proved URL shape without proving real stock-OS TLS, current `/i/` routing or actual host installation | Unit tests passed when deployed Server `bootstrap_hostname` was absent and real output was long | Test public TLS and the exact DRLink invalid-handle 404 body; run the literal emitted launcher on a clean external Agent; record user-visible bytes and result |
| ZT-RC-04 | Guided, backend `frp-create-client`, CLI/AI advice, and Windows/macOS paths diverged; SSH username was treated as setup input even though the tunnel requires only target address/port | `tests/test-create-zero-touch.sh` still counts an optional SSH prompt as a positive assertion | User may leave SSH login metadata blank. Never block enrollment on it, invent usernames, or require repeated prompts. Guided/direct paths must yield the same usable launcher |
| ZT-RC-05 | Zero-Touch raw LAN target (`local_ip`) was materialized as `this-host` in both Server and Agent catalogs | Bootstrap regression mostly used `127.0.0.1` and checked local reachability/port retention, not signed LAN authority and public external SSH traffic | Preserve exact destination IP/port/immutable Service ID and public port; use a named Network Object for routed LAN targets; mismatch remains fail-closed. Existing-install migration may affect only provably untouched bootstrap seeds |
| ZT-RC-06 | Code tests ran on checkout bytes but installed Server/Agent and embedded `dist/bootstrap-*` sometimes remained older | Functional source PASS mistaken for installed acceptance; CI subsequently flagged `DERIVED_BUNDLE_STALE` | Generate and verify bundles, SHA256SUMS and manifest at candidate HEAD; inspect installed Source HEAD on Server and Agent; run real public CLI and external traffic on those exact bytes |
| ZT-RC-07 | Test-run configuration mutations clear and restore `bootstrap_hostname` | Resetting to the original unset setting was a correct cleanup, but an *unset = silently long* default reappeared in later tests | Always restore original settings and then assert the **current documented default**, rather than reporting PASS because the old long mode returned |

## Normative v2.4 behavior (ZT-P0-CONTRACT-20261026)

1. **Beginner default:** `set enrollment zero-touch` / generated one-line command uses a short, stock-OS-validated HTTPS launcher when a qualifying public bootstrap endpoint is available. The command must be copyable as one line and must not include the multi-kilobyte `zt1` package. The public-domain reference benchmark on `remote.xdr.ooo` is **Linux/macOS <= 200 characters; Windows <= 500 characters** with an opaque 22-character handle. These benchmark limits are not a universal maximum for arbitrary long DNS names.
2. **Trust qualification:** explicit operator-configured `bootstrap_hostname` is an assertion of trusted public-TLS intent; stock-client TLS verification still MUST succeed at actual fetch. Otherwise a DNS `public_hostname`/`public_url_host` may qualify only via real HTTPS verification of `/i/invalid-qualification-probe`, expecting **HTTP 404 + body exactly `bootstrap unavailable`** from DRLink's handler. A generic nginx 404, HTTP 200 default HTML, redirect, invalid/expired certificate, unresolvable DNS or plain IP is not sufficient.
3. **Unqualified default:** show an actionable error describing how to configure trusted HTTPS (public FQDN, DNS, 443, appropriate proxy route and certificate). Do not issue a ticket and do not silently print a 4,000-character command.
4. **Advanced private CA:** `frp-create-client --one-line --long-bootstrap` is a deliberately selected backend/advanced path for private-CA environments. It retains fingerprint-checked CA and installer integrity verification. It is NOT the beginner default and is not a separate public `drlink` grammar.
5. **Three OS paths:** Linux and macOS use a fully downloaded HTTPS bash stage before executing; no `curl -k`, `--insecure` or success on empty download. Windows verifies the exact stage-1 SHA-256 **before** executing PowerShell, preserving one-line copy/paste. When the source server has not qualified trusted TLS, fail closed.
6. **No SSH account prerequisite:** an SSH username is optional connection-example metadata. It is unrelated to Agent enrollment, FRP tunnel identity and target reachability. Never require a guessed/default username or repeat identification unnecessarily; a guided prompt, if exposed, must be skippable.
7. **Signed enrollment and routing:** bootstrap tickets are bounded, one-time and bound to first machine. For another LAN destination, the Server/Agent authoritative reference must represent the exact signed IP or FQDN, not `this-host`. Preserve Service ID, target port, public port and intentional disabled state; a TCP-open local target alone must not mark public service `HEALTHY`.
8. **No false acceptance:** generated installer parity, stock TLS, issued-command bytes, installation, reported Source HEAD, real external SSH/HTTPS traffic, and cleanup are distinct observable gates. Success on a different HEAD, internal-only mock or an unopened destination listener is not interchangeable.

## Reproducible acceptance matrix

| Scenario | Expected output/behavior | Actual gate |
|---|---|---|
| Qualified real DNS + DRLink `/i/` 404 signature | Short command on Linux/macOS/Windows; TLS verified; real ticket installation succeeds | `tests/test-zero-touch-operator-command-bound.py`; `tests/test-zero-touch-short-url.sh`; U-009/O-002 real external E2E |
| Explicit `bootstrap_hostname`, expired/wrong certificate | Generated command may exist, but stock client fetch MUST fail; no unsafe bypass or consumed ticket | TLS negative suite + clean external client |
| Generic HTTPS 404 or unrelated web application | Refuse false short-URL discovery, no ticket | Qualification probe negative test |
| DNS configured but no public trusted `/i/` route | Actionable prerequisite error, no default `zt1` dump | Default-no-silent-long test; CLI guided/direct comparison |
| Private-CA-only / public IP | Explicit `--long-bootstrap` only; fingerprint check unchanged | Advanced fallback suite |
| Optional SSH user blank | End-to-end enrollment/tunnel functions; no misleading account inference | Guided and backend user journey |
| LAN SSH remote 6001 | Signed target `192.168.219.125:22`, correct Network Object, preserve 6001, real external SSH banner and session | Server/Agent projection + remote actual traffic |
| LAN HTTPS remote 6002 with target 443 intentionally down | Configuration references consistent, do not fabricate HTTPS PASS; DEGRADED is truthful until listener starts | Server/Agent state inspection |
| Legacy Agent/Server upgrade | Repair only exact mismatched enrollment seed, preserve operator modifications and ports | `tests/test-enrolled-routed-target-parity.py`; upgrade + installed E2E |
| Server config temporarily cleared during A-018 | Restore exact original settings, then compare generated mode with *current default contract* | A-018 lifecycle, U-009 recheck |

## Release gate and evidence obligations

**Document-only, mock-only, unit-only, source-only, CI-only and historical recorded PASS must never close these user requirements.** The release gate requires:

- **Local focused checks:** `python3 tests/test-zero-touch-operator-command-bound.py`, `bash tests/test-zero-touch-short-url.sh`, `python3 tests/test-enrolled-routed-target-parity.py`, `python3 tests/test-cli-inventory-selection-journey.py` and `python3 tests/test-zero-touch-doc-contract.py` (the documentation consistency check).
- **Artifact closure:** `bash tests/test-change-closure-artifacts.sh` at the exact product source HEAD; reject `DERIVED_BUNDLE_STALE` or checksum/manifest drift.
- **Installed candidate:** record `drlink system version` Source HEAD for Server and Agent and exact bundle SHA256; external new-user command generated from the actual installed Server, not a copied example or source runner.
- **Real negative/positive:** trusted public TLS, real `/i/<handle>` redemption, one-time binding, service lifecycle, 6000 preservation and 6001 real external SSH. HTTPS :443 behind 6002 may remain legitimately down and must be recorded honestly.
- **User gate:** execute U-009, O-002, A-018 and relevant CLI-008/FCS-002 as actual personas. No silently skipped prerequisite or preexisting config reset. For v2.4 release, both complete 116-ID Full User E2E PASS runs must be on one frozen, installed, verified HEAD.
- **Observability:** redact all raw `bt1`, short handles, OAuth codes and private keys; retain lengths, mode, endpoint/status, exit codes and provenance. Do not retain a readable one-time credential in evidence.

## Disposition / known remaining work

PR #222 contains isolated source and targeted tests, but live Server/Agent upgrades and public :6001 end-to-end acceptance remain separate. The connected DRLink MCP currently exposes the Agent only; it cannot mutate Server-only Network Objects or perform Server deployment. A service intentionally not listening on LAN :443 must not be marked an HTTPS relay regression. Mark these outcomes `NOT_RUN`, `BLOCKED_TOOLING`, or `FAIL` from actual receipts; never PASS from a code review.

## Historical notes (not current default)

The original v2.1.3 short URL was an opt-in feature and automatic `zt1` fallback was intentionally preserved for Private CA. Those historical compatibility tests remain useful **only when the advanced fallback is explicitly selected**. Their previously green output explains the regression; it does not override the present owner-selected short-by-default UX.
