# Data Relay Link UI Redesign — UXR-7 Acceptance Status

This record separates source/browser-fixture evidence from genuine user acceptance. Synthetic sessions, screenshots, HTTP 200, or a private development preview do not constitute product Browser PASS.

## Exact development candidate

- Current branch source HEAD: 1e50c66cccc486df163b220fded71d486d5c7d78.
- Private RC41 Web bundle SHA256: 53558225b27f7973544a81c7e48c17fff5876aea51e09027a7c08ac09dab2f08.
- Private development candidate: dev-installed-1e50c66c.
- Approved development preview location is intentionally redacted from public repository evidence. Private operator evidence retains the real endpoint.
- Served index.html, app.js, styles.css, foundation.css, favicon.svg and the DataRelay logo are HTTP 200 and byte-identical to the selected candidate.
- Anonymous /api/v1/session remains 401.
- This is a private development preview, not production or release promotion.

## UXR-7.3 — visual fidelity

Existing source-mounted browser evidence is regression evidence only.

Two retained, same-name Server matrices contain 32 observations each:
4 viewports (1440x900, 1280x800, 375x812, 320x568) × light/dark × 0/1/10/50 records. Both matrices report:

- page-wide overflow: 0
- visible controls below the existing 44px target check: 0
- browser runtime errors: 0
- fixture product writes: 0

Older matrix observation manifest SHA256:
fde3201624a754453e9555625c32e240e461d904df8833f1aa438dea543789e3

Current UXR-5 matrix observation manifest SHA256:
6cab53564b291c536422f1fdb3f838f66b76e3c285e06d266e0d74954a9370c1

These screenshots mount real production React routes with synthetic authorized GET data. They are not authenticated-user evidence.

### Blocking evidence

UXR-7.3 explicitly requires comparison against the retained PDF3–5 source material and actual interactions. The current repository and accessible Project file search contain no PDF3–5 artifacts; only roadmap references to them are available. No replacement source is invented.

The private preview currently has one enabled Web operator record: admin / Admin. No Operator or Read Only preview accounts are provisioned. No credential is read, reset, created, or copied for this check.

Therefore UXR-7.3 remains BLOCKED, not PASS:

1. PDF3–5 source visuals must be supplied or restored to the authorized project evidence set.
2. A permitted authenticated browser session is needed to compare deployed routes rather than fixture DOM/screenshots.

## UXR-7.4 — 20 routes + shell, three roles

UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md already enumerates the 20 current route/task candidates plus Shell and explicitly requires genuine Admin, Operator and Read Only sessions.

Current authoritative preview census is only one Admin operator. Creating, resetting or changing authentication/roles is a separate security-sensitive operation and is not performed for test convenience.

Thus real three-role Browser acceptance is BLOCKED. Existing unit, SSR, Playwright fixture and source-route tests remain supplemental and must not be entered into the ledger as real executions.

## UXR-7.6 — real novice usability

Five independent humans are mandatory. ChatGPT, scripted browsers, generated personas, repeated runs by one person, or implementation participants do not count.

The exact measurement protocol and empty five-person ledger are in UI_REDESIGN_NOVICE_USABILITY_PROTOCOL_2026-10-14.md. Until five genuine participants complete the tasks, UXR-7.6 is BLOCKED.

## UXR-7.7 — exact-head UI CI/review closure

At the start of this acceptance tranche, PR #206 exact HEAD 3b8dd162 exposed two real CI defects:

1. public metadata hygiene rejected a live development-preview IP retained in public UI evidence documents;
2. macOS regenerated dist/bootstrap-client.sh and dist/bootstrap-server.sh, proving checked-in generated bundles were stale.

Both were corrected without changing runtime policy/authorization:

- public evidence now uses non-routable/redacted preview references;
- public metadata scan passes with zero live IPv4/fingerprint/non-documentation IPv6 findings;
- current bundle generation is deterministic on repeated execution;
- generated client/server bundles are synchronized to current source.

The repair HEAD is 1e50c66cccc486df163b220fded71d486d5c7d78.
GitHub CI must reach terminal status on this exact head before UXR-7.7 can be closed. No earlier CI result is reused.

## Remaining acceptance boundary

No WBS is promoted to ACCEPTED from this document. Genuine role sessions, PDF3–5 visual source evidence, five real novices, UI-06 two-person approval implementation/real two-user proof, final owner acceptance and release authority remain separate gates.
