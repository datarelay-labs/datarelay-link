## 2026-10-14 continuation — cross-cutting UXR-5 development deployment

Exact deployed Web source: `971f35e250a3a724803478ed68091cf61e6786fc`; private RC41 bundle SHA256 `53558225b27f7973544a81c7e48c17fff5876aea51e09027a7c08ac09dab2f08`; active development candidate `dev-installed-971f35e2`.

- UXR-5.1 standardized readable heading/focus behavior and a 44px minimum for primary interaction controls. The responsive RED run found real 35.5–40px major actions; the product CSS was fixed rather than weakening the gate.
- UXR-5.2 moved nonessential implementation evidence under one keyboard-readable **Technical details** disclosure while destructive/truncated/required-test warnings remain visible.
- UXR-5.3 added a local-asset regression gate. The deployed preview serves index, app, both CSS files, favicon and local DataRelay logo with HTTP 200 and bytes identical to the active candidate; CSP remains same-origin.
- UXR-5.4 production `View` browser coverage passed across Home, Servers, Setup, Services, Policies, Access, Activity and error state at 1440×900 / 1280×800 / 375×812 / 320×568 in light/dark.
- UXR-5.5 fixed eleven unnamed visible Policy/Access controls. Full responsive/accessibility browser **2/2 PASS** verifies names, dialog focus containment/return and shared text contrast >= 4.5:1.
- UXR-5.6: Core auth **12/12**, MFA policy **5/5**, Web session **5/5**, synthetic independent Admin/Operator/Read Only Shell **3/3**, selected directly guarded Web API effects **6/6**. The existing development account was not reset or replaced merely to obtain a live-login test.
- UXR-5.7: mounted Servers async **35/35** and additional async/pagination **68/68** PASS, covering timeout/retry, actor and route change, superseded response, pending load-more and 100/101 boundaries.
- The exact-head private builder passed its Web suites and disposable install. Development pointer changed atomically from `dev-installed-1c90e9ef` to `dev-installed-971f35e2`. The preview database, TLS certificate and TLS key hashes are unchanged before/after promotion. Anonymous session remains HTTP 401.

UXR-5.1–5.7 are **DEV_DEPLOYED**, not ACCEPTED. Live authenticated browser acceptance remains intentionally open because no existing credential was exposed or reset. Production, merge, release and customer state are untouched. Next dependency: **UXR-6.1 UI06 contract/approval boundary**.

---

## 2026-10-14 continuation — V3 Access, Home and Activity development deployment

Exact deployed Link source: `1c90e9ef0029fe53340f5bf2793eac60cf8da011`. UXR-3.1–3.11 and UXR-4.1–4.10 are source-complete and deployed to the approved development preview, while live-user acceptance remains open.

- Access now presents Remote / Internet / AI as distinct planes, keeps basic rule editing separate from advanced exact-name entry, displays prepared SET/DELETE intent, retains Core Preview → required tests → typed Apply, separates current/draft/preview evidence, and preserves focused bounded graph/policy/Audit pivots.
- Policy authorization, transport testing and observed live-use evidence are visibly distinct. The selected-service diagnosis preserves a safe return target, shows the Core next action, and labels the browser receipt time instead of inventing a server observation timestamp or network probe.
- Home makes next tasks dominant, places fleet counts under evidence disclosure, and exposes only observed enabled services without claiming reachability. Activity is a six-column human-readable list with one bounded selected event.
- Global Search retains old aliases and now exposes a keyboard-readable “What changed in navigation?” help panel. Saved Views, shell preferences, Foundation Administration and operational detail paths remain intact.
- Focused source tests: Access/Policy **153/153 PASS**; Home/Audit/Saved Views/Search/Admin/operations **163/163 PASS**; Journey **437/437 PASS**; P0 **44/44 PASS**.
- Private RC41 bundle `439ad4de4d7181f9aba4c41a0c8b193cad29bbc1b05b41c802788242f2f6fd4b`, Foundation `46ddb60`, ten private archives; activation moved only the approved development pointer from `dev-installed-df12fde7` to `dev-installed-1c90e9ef`.
- Served preview `https://221.139.249.111:19044`: all five assets HTTP 200 and match the installed candidate; app.js `def05ce30033073d4807fee067b276c6a6c2aee8826565323dde6e4c687bd642`, styles.css `0c31801485e67f1875af4417e454459b514bf30aaab3e7e45637e0ec4eeb071e`, anonymous session **401**.

No UXR-3/4 task is marked ACCEPTED from fixture/source/deployment evidence. Actual authenticated roles, real traffic/Agent, all route/viewports and owner acceptance remain later UXR-5/7 evidence. Next source task: **UXR-5.1**.

---

## 2026-10-14 continuation — V2 server-to-service journey deployed

Exact deployed Link source: `df12fde730a8f40bb961821888302de90492d7b7`. This continuation implements the UXR-2 source journey without changing Core authorization, enrollment, admission, Remote Service or policy semantics.

- **UXR-2.1:** Add server begins with Linux/macOS/Windows platform cards and collapsed advanced invitation settings.
- **UXR-2.2–2.4:** display-once invitation evidence remains bound to exact operator/role/intent; enrollment detection is keyed by the Core `enrollment_id`, polling is bounded, inventory timeout/retry is explicit, and approval advances only from exact Core plan/revision/receipt evidence. Detection/approval/connection remain separate.
- **UXR-2.5:** mounted browser continuity proves an observed Host flows into the service and rule stages without copying a Host ID, and changing the Host clears dependent service/rule intent.
- **UXR-2.6–2.9:** the Services route removes the targetless editor, separates configuration from policy/transport evidence, adds safe SSH/HTTP(S)/TCP use guidance, focuses publication on the selected Host, hides lifecycle options under disclosure, and preserves existing one-shot Preview/Apply with local-only cancel and ambiguous-outcome retirement.
- Exact-source checks: Setup continuity browser **2/2 PASS**, related service/connection checks **57/57 PASS**, registered Journey **430/430 PASS**. The private RC41 builder independently passed Administration **20/20**, Journey **430/430** and P0 **44/44**.
- Private RC41 bundle: `98dd9d687fbcb75f4e887a6ee96f8f5b8b38e938ad6089de827f5bd3f687fc4a`; Foundation `46ddb60`; 10/10 private archives. `dev-installed-df12fde7` passed read-only verification and atomically replaced only the approved development pointer `dev-installed-50944164`.
- Approved HTTPS preview `https://221.139.249.111:19044` already serves through `dev-installed-current`; all five static assets are HTTP 200 and byte-identical to the installed candidate. `app.js` SHA256 `97ee5a4716519db81c7a90aa0de3436261ceed4ccc3c920dcb19e3fa8b59facc`; `styles.css` `7d134e663acbb348cff238579a001aa67bf8b7c5a03c0bd5be30785a809adf93`; anonymous `/api/v1/session` remains **401**. Existing preview Core data, account, TLS files and rollback candidate were not changed.

UXR-2.1–2.10 are recorded **DEV_DEPLOYED**, not ACCEPTED. Synthetic fixtures do not substitute for a real Agent or independent user. The existing preview account credential was not reset or invented, so authenticated live-browser V2 acceptance remains open. No WBS is accepted from this checkpoint. Next source task: **UXR-3.1**.

---


## 2026-10-14 continuation — selected-server management gate cleared

The previously recorded platform rejection was **not permanent**. A normal retry through the same `Remote_Desktop_Commander.start_process` target and selected worktree succeeded without alternate tooling or authority changes. Current source commit `509441641f5fe3d5220819487c7fea5f813d5ac5` binds metadata, admission and lifecycle actions to the already selected authorized Host and removes manual Host-ID re-entry. Existing Core preview/apply, role, revision, expiry and typed-confirmation contracts remain authoritative.

Verification on this source: Servers deterministic **14/14**, mounted Chromium **35/35**, registered Journey **426/426**, Administration **20/20**, P0 **42/42**, production Web build and `git diff --check` PASS. The two new mounted UXR-1.7 cases prove exact selected-host admission request binding and wrong-target lifecycle preview rejection. These are fixture browser checks, not live-user acceptance.

Private RC41 candidate build PASS: Foundation `46ddb60`, 10/10 private packages, bundle SHA256 `e6b2d7e11552c70c9104fd0cb4b37fc86f210999c4ccc9958bbfa0a0639fb355`. Development candidate `dev-installed-50944164` was verified, atomically selected and the already approved HTTPS preview was restarted against that pointer while preserving the existing preview Core root and TLS files. Served `app.js`, `styles.css`, and `foundation.css` match installed bytes; anonymous `/api/v1/session` remains HTTP 401.

UXR-1.6, UXR-1.7 and source-level UXR-1.10 are now IMPLEMENTED. UXR-7.1 is IMPLEMENTED and UXR-7.2 is DEV_DEPLOYED. **No WBS is promoted to ACCEPTED from these checks.** Authenticated real-browser fidelity, all-route acceptance, real novice evidence, UI-06 and owner acceptance remain open. Next source task is UXR-2.1.

---
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
