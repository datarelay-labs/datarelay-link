# Servers UI implementation checkpoint — 2026-10-14

## Follow-up: stale observations and incomplete related services

Source commit: `3e00e6d5475d7a7dce3de25f505d862a0a6935fa`. This follow-up preserves both preceding commits (`06bd16e8`, `6d9dfec4`) and the original UI work. It does not modify `main.tsx`, management forms, Core APIs, credentials, permissions, product data or preview assets.

- Reproduced and fixed two independent read-only UI bugs: stale Agent observations kept current-success styling; an explicitly incomplete related-service page could claim that no services existed. Both mounted regressions were RED, then **2/2 GREEN**.
- Added nine mounted browser assertions covering real production timeout handling with a virtual browser clock, superseded refresh responses, four incomplete-page markers, exact service navigation, stale status and incomplete related-service evidence.
- Corrected the obsolete source-route assertion to the actual `View -> ServerRoute` mount. The failing selected-target and lifecycle guards remain present and failing; no guard was removed or skipped.
- Actual product-source browser suite: **32/33 PASS, 1 RED** (selected metadata panel still asks for a Host ID). Registered UI Journey suite: **425/426 PASS, 1 RED** (missing lifecycle plan/receipt validator). These are NOT a full PASS. The executed product-source SHA256 matches this commit; a later test-title-only clarification changes no assertion or fixture behavior.
- Re-ran the full App/Shell/sidebar-return check after the read-only fixes: **3/3 roles PASS**, three fresh server inventory reads per role and zero POSTs. These remain synthetic sessions, not actual user qualification.
- Expanded viewport coverage to **32/32 PASS**: 0/1/10/50 records × 1440×900 / 1280×800 / 375×812 / 320×568 × light/dark. No page-wide overflow, undersized controls under the existing 44px check tolerance, runtime errors or fixture POSTs. All data are synthetic and the visual harness mounts the production View, not the deployed authenticated shell.
- Evidence is retained under `/home/aella/drlink-validation/ui-uxr1-resume-20261014`; hashes and source identity are in the follow-up entry of `docs/ui-redesign-servers-evidence-20261014.json`.

### Current unresolved gate

The normal selected-server metadata/admission correction through `Remote_Desktop_Commander.start_process` on the same dev-drlink worktree was rejected before execution again in this continuation: “요청의 보안 상태를 결정하지 못해 이 도구 요청은 OpenAI에 의해 차단되었습니다.” The diagnostic composite was separately rejected by the platform. Neither request was rerouted or encoded. Independent read-only UI code, tests and ordinary Git commands executed normally.

**UXR-1.6 / UXR-1.7 stay blocked, so coherent UXR-1.10 and its dependent private build/deployment remain unqualified. The existing development preview is deliberately NOT UPDATED.** No server configuration or additional blanket implementation approval has been identified as a remedy. A future continuation may reassess current conditions and retry normally; this continuation must not repeatedly route around the denial.

Planning state remains **8 source-implemented / 3 blocked / 55 spec-bound; 0/66 accepted**. Other WBS are not silently waived, including UXR-6, live role/Agent evidence, real novices and owner acceptance. The exclusive UI lock remains in force.

---

- Repository: `datarelay-labs/datarelay-link`; exclusive roadmap #184; ACTIVE packet #182; Draft PR #206.
- Source checkpoint: `06bd16e843083d46d8a136d4aa0830069dc7faa6`. This is **not** an accepted, deployed or release-qualified UI.
- Original source HEAD: `cebb6284cb55a45e435214a9ce870947fe4a0ad1`.
- Worktree: `/home/aella/datarelay-link-worktrees/drl3-foundation-rc41-consumer-20261013` (detached); push ref `feat/drl3-ux-saved-admission-pfci`.
- No competitor research, Core API/authorization change, preview account reset, production deployment, merge or release.

## Implemented source, not acceptance

| WBS | Source result |
| --- | --- |
| UXR-0.4 | Reused both supplied WIP files and preserved the original 39-line roadmap addition exactly. Original SHA evidence below. |
| UXR-1.1 | Actual `App → Shell → View → ServerRoute` wiring; loading/unavailable/empty/filter-zero/partial/stale distinctions; abort/generation guards and actor-keyed state. |
| UXR-1.2 | First-server screen with one Admin Add server primary action, illustrative connection diagram and existing-Agent route; no page-bottom management forms. |
| UXR-1.3 | Six compact columns with explicit column-header semantics. Missing service count is Not reported, never a fabricated zero. |
| UXR-1.4 | Existing loaded-scope search, approval/connection filters, sorting, chips, reset, cards, saved-view draft and manual 100/101 paging retained. |
| UXR-1.5 | Detail only for a uniquely observed selected row; Overview/Services/Activity/Settings, bounded facts and authorized action entry points. The management-panel consumers remain unfinished under UXR-1.6/1.7. |
| UXR-1.8 | Actor-bound in-memory display choices, fresh GET on return, selected tab/filter restoration, closed-detail preservation, keyboard tabs/focus containment and trigger return. Records/plans/credentials are not cached as navigation state. |
| UXR-1.9 | Connection, admission, trust, Agent heartbeat and Core activity remain separate. Missing values remain unknown; previous observations lose current-success styling. |

UXR-5 style/disclosure/responsiveness work is partial cross-cutting implementation, not completion of all affected product screens.

## Earlier checkpoint checks (source 06bd16e8; superseded counts above)

| Check | Result / limitation |
| --- | --- |
| Original WIP baseline | 12 tests: 10 PASS, 2 RED (unmounted route, missing styles). |
| Original actual-route Chromium baseline | 18 tests: 3 PASS, 15 RED. |
| Current actual-route Chromium | **24 tests: 23 PASS, 1 RED**. Remaining RED is the unbound metadata panel. Synthetic API fixtures, not live Core/user acceptance. |
| Current App/Shell/sidebar/return navigation | **3/3 roles PASS** (Admin, Operator, Read Only); three fresh host inventory reads each, zero POSTs. Sessions and GET responses are explicit loopback fixtures. |
| Current visual/read-only matrix | **16/16 PASS**: 1440×900, 1280×800, 375×812, 320×568 × light/dark × 0/10 records. No page-wide overflow, controls under 44px, runtime errors or product POSTs. These are mounted View screenshots, not all-20-route live acceptance. |
| Existing Administration / P0 / Journey regressions | **20 + 42 + 412 PASS**. |
| New server deterministic tests | **12/14 PASS**; legacy route-string expectation and missing lifecycle validation helper remain RED. No failed guard was deleted or relaxed. |
| Registered combined Journey gate | **424/426 PASS, 2 RED**. New server guards are included in the ordinary `test:journey` script. |
| UI roadmap integrity | **16/16 PASS**; 66 WBS, 40 CUI, 37 gaps, 22 vendors and 24 UXE meanings retained. |
| CSS parser / whitespace | PASS, no CSS warning. Also repaired a pre-existing literal `\n` before a media query. |

Private logs and screenshots: `/tmp/drlink-ui-resume-20261014`; this directory is owner-only. Run/log identity is summarized in `docs/ui-redesign-servers-evidence-20261014.json`. Browser driver is pinned in the existing private development cache, not added as a production dependency.

## Verified platform block — do not bypass

The selected-host metadata/admission/lifecycle-panel correction request was rejected **twice**, including an unchanged normal retry, by `Remote_Desktop_Commander.start_process` on `dev-drlink` (`cbaef4d2-a1fb-4356-a4ee-877314afb44e`).

Exact tool response: “요청의 보안 상태를 결정하지 못해 이 도구 요청은 OpenAI에 의해 차단되었습니다.”

The affected request targeted the selected-server panel integration in `web/src/main.tsx`, lifecycle preview/receipt validators in `web/src/workflow-servers.tsx`, and the matching server test integration. It did **not** execute. No alternate tool, encoded command or alternate target was used to apply it. Later independent read-only state, navigation, CSS and browser work was executed normally; the denied action remains pending.

Impact: UXR-1.6 and UXR-1.7 remain blocked. UXR-1.10 cannot be complete, so the private candidate build/development deployment and dependent UXR-2 onward are not started. A new continuation must reassess current conditions and retry the affected ordinary action normally; this is not a permanent ban. If denied again, do not bypass it.

## Development preview — deliberately unchanged

Read-only TLS-verified checks used the existing approved certificate, not an insecure TLS option. No accounts, data, services, listeners or PKI changed.

- Approved preview: `https://221.139.249.111:19044`.
- `app.js`, `styles.css`, `foundation.css`: HTTP 200; served hashes equal the original preview files and the resume baseline.
- Anonymous `/api/v1/session`: HTTP 401.
- This new source checkpoint is **NOT DEPLOYED**. The failing target-binding regression is a prerequisite, not a deployable feature.
- Existing rollback/data/certificate files remain untouched. No proprietary compiled bundle is committed.

## Original WIP preserved

- Roadmap addition (original and retained): `4773fce4237cbba31bff689898bde890ca186fa9e39bcbfc7a3cb93970590f9f`.
- Original `workflow-servers.tsx`: `ce6e65d6ec421b614051d237aeaf05104b8ac703f752bab604790436de850a37`.
- Original `workflow-servers.test.mjs`: `6b21ae5ab5efd5a5413f31f45a68f55ceb3288165cb629e0a7ff85f27a5e321e`.
- Original copies remain under the private `preserved-wip` directory, and the integrated source is now committed.

## Continue, in order

1. Retry the blocked UXR-1.6 selected-host panel correction under current tool conditions; do not rerun research or rebuild the already implemented first-server page.
2. Complete UXR-1.7 using existing Core preview/confirmation/revision/expiry and exact receipt contracts. Keep the RED tests until correct implementation passes.
3. The legacy route-string expectation is now corrected. Pass the remaining selected-metadata and lifecycle regressions plus their affected tests; do not repeat the completed read-only work.
4. Finish coherent UXR-1.10; build the private exact-HEAD RC41 candidate, deploy only to the already approved preview, and verify served asset hashes plus actual login/browser interactions.
5. Continue the remaining #184 dependencies in order. Keep UXR-6 explicit-reviewer authority, all-20-route live evidence, five real novice users and owner acceptance mandatory.

**Acceptance: 0/66. Exclusive UI scope remains locked. Source implementation and fixture-browser PASS do not unlock it.**
