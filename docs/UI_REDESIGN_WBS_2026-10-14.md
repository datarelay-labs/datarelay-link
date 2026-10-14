# DataRelay Link — Exclusive UI redesign WBS and acceptance contract

2026-10-14 / revision 1. ONE roadmap #184, ACTIVE Work Packet #182, existing Draft PR #206. This document and its machine-readable index are an appendix of #184, not a second work queue.

## Owner-mandated P0 exclusive scope

**Implement all retained competitor UI findings and all promised visual/workflow changes before doing any other work.**

`PRIORITY=P0_EXCLUSIVE_UI_REDESIGN` / `EXCLUSIVE=true` / `IMPLEMENTER=CHATGPT_CHAT` / `NEXT_TASK=UXR-1.1`

The previous Foundation-package-only scope and recurring research-first/M2/M3 fallback wording no longer select work. Do not repeat completed competitor research or RC41 migration. Existing source behavior remains reusable evidence, NOT accepted visual improvement. The first visible batch is V1 Servers true-empty/list/detail/actions, then V2 connected setup/service flow, then V3 access/Home/Activity. UXR-5 visual/security and UXR-7 deployment checks apply within EVERY batch, not only at the end.

No unrelated Core/Agent, OS/backup, general CI cleanup, other product work or replacement designs while this scope is open. A minimal direct prerequisite is allowed ONLY with a named WBS dependency, exact affected change/test, and immediate return to that task. During a genuine wait, continue other eligible UI WBS, not unrelated roadmap work. No plan/report/test-count-only stopping when safe authorized UI work remains. Commit/push normal fast-forward per coherent unit and preserve existing WIP.

**Release of this scope lock requires all required UI WBS accepted with evidence and owner acceptance, or a subsequent explicit owner scope change.** Approval/platform/tool dependencies do not auto-remove requirements. If only blocked UI work remains, report the verified blocker, preserve unfinished work and keep the lock; do not invent a task or silently switch projects.

### Scope boundaries and dependencies

Foundation owns shared login, Users/MFA, System Management and visual components/tokens. Link owns resource/workflow composition. Reuse Foundation; do not fork common pages or mutate another product. Existing Core/API/CLI semantics, RBAC/CSRF/session safety, per-plane authority, reservations and state are preserved.

**UI-06 remains mandatory** in UXR-6 because it was previously promised. The distinct-reviewer Core/schema/permission design needs explicit approval before its privileged implementation. This priority instruction is not blanket approval for a new authorization model. Design and ordinary other UI work may proceed; a fake one-actor approval or an Unsupported label cannot close UI-06. Final closure stays open if its required dependency is unresolved.

Production, destructive actions, credential/permission changes, publication, merge and product release remain separately governed. Existing dev preview is the authorized UI target; preserve its account, Core state, TLS and rollback candidate. Never commit proprietary RC41 code/tars/compiled bundle or secrets to public Git/Actions. Retry a prior denial with the original tool/target under current permission; do not bypass a repeated current denial.

### Evidence and completion semantics

Each task tracks independently: SPEC_BOUND -> IMPLEMENTED -> DEV_DEPLOYED -> BROWSER_VERIFIED -> ACCEPTED. A prior source APPLIED, 474 tests, a package installation, standalone HTML/PDF, DOM snapshot or HTTP200 does not prove browser/visual acceptance. An image alone does not prove the mutation/role result.

For every item retain source reference, code commit, affected test command/results, deployed source HEAD and served JS/CSS/asset hashes, actual route/actor/data/theme/viewport, before-after evidence, interaction/API effects, remaining deviations and owner feedback. Design/governance tasks use saved/read-back/approval evidence rather than fake screenshots. UI source and fixture tests support actual browser evidence; they cannot substitute for genuine Agent traffic or two independent users.

Required cases: true0/1/10/50, pending/quarantined, existing100/101 boundary, stale/unknown/malformed; loading/401/403/5xx/timeout/filtered-zero/partial/late reply. Roles: Admin/Operator/Read Only, independent permitted sessions. Viewports:1440x900,1280x800,375x812,320x568; light/dark. Iterative reruns may be affected/pairwise; final applicable route/role/data coverage has no silent skip. Whole-product CLI/Full User E2E/release gates remain separate and are never inferred from this UI acceptance.

PASS means the specific row criteria plus required real evidence; zero wrong-target/unauthorized/secret-leak/data-integrity defects and zero undisposed UI deviations. Missing evidence remains OPEN. The plan checker validates index/coverage/closure structure, not the truth of an uninspected screenshot.

## Milestones

| Milestone | Required outcome / exit |
|---|---|
| **UXR-0 Evidence and exclusive execution baseline** | Every retained source/finding/promise mapped; obsolete priorities archived; no WIP overwritten. |
| **UXR-1 V1: complete Servers screen** | True-empty/list/selected-detail/actions form ONE mounted product screen; all old default clutter removed; context and authority preserved. |
| **UXR-2 V2: first server to usable service** | Supported platform -> install/detect -> review -> publish -> narrow policy -> connection information; no false completion or ID re-entry. |
| **UXR-3 V3: Access rules and selected-resource explanation** | Focused input and exact relationships, separate policy/transport outcomes, truthful Remote/Internet/AI semantics and contextual diagnosis. |
| **UXR-4 V3: Home, Activity, discovery and Administration** | Useful next actions; every historical selected feature retained in contextual layout; common Foundation UI not duplicated. |
| **UXR-5 Shared visual, responsive, accessibility and security** | All affected screens satisfy Foundation styles, data/role/theme/viewport/keyboard criteria with genuine browser evidence. |
| **UXR-6 Mandatory UI-06 distinct-reviewer request** | Approved durable Core contract and real requester/different reviewer/expiry/revoke/audit proof; approval dependency remains explicit. |
| **UXR-7 Private dev delivery and user acceptance** | Same-source served assets, before-after interaction proof, all route/UXE cases, real usability observations and owner acceptance; no unreviewed omission. |

## UXR-0 — Evidence and exclusive execution baseline

Milestone PASS: Every retained source/finding/promise mapped; obsolete priorities archived; no WIP overwritten.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-0.1 Research and proposal inventory** | Bind original 19-product history, later 13-product audit, all CUI/G/UX/UI/UXB/UXE, PDF and illustrative HTML; no new research loop. | Compare exact source revisions, SHA256 and identifier sets; retain source URLs/license/REA limits. | Every source and finding has a disposition and WBS; zero unmapped promises. Source APPLIED is not browser acceptance. | entry; `docs/COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md` |
| **UXR-0.2 OLD to NEW capability inventory** | Map all 20 routes plus shell actions to retained routes/drawers/review or explicit non-adoption; remove duplicate entries, not capability. | Diff actual route/action lists before/after; check legacy aliases and negative-scope decisions. | No supported action orphaned; every removed default element has a tested new destination. | UXR-0.1; `web/src/uxb-navigation.ts` |
| **UXR-0.3 Rejected baseline and dataset** | Record owner screenshot, source/assets, role, data scope, theme, viewport and measured task baseline. Never invent observations. | Same-condition captures: real zero, 1/10/50 rows, pending, partial, stale/error and existing 100-row boundary; distinguish fixtures. | Before evidence identifies source/role/data/viewport; missing real observations remain unverified. | UXR-0.1; `docs/UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md` |
| **UXR-0.4 Preserve ongoing V1 implementation** | Preserve workflow-servers.tsx, its test and dirty journey-roadmap edit. Reuse current component before inventing another; bind actual route. | Inspect WIP hashes/diff, import and route mount; do not stage/reset another task's files. | Existing WIP intact; tests target the actual Servers route, not an isolated demo helper. | UXR-0.1; `web/src/workflow-servers.tsx`, `web/tests/workflow-servers.test.mjs`, `web/src/main.tsx` |
| **UXR-0.5 Exclusive roadmap and executable plan guard** | Update existing #184, #182 and NEXT_CHAT_START; only this UI scope until accepted. Archive obsolete bodies instead of retaining conflicting scheduling. | Read back GitHub bodies; check coverage/dependencies/evidence; negative tests remove mapping, turn exclusivity off or fake completion. | All canonical records agree; validator rejects omission and false closure; plan PASS is not product PASS. | UXR-0.1; `scripts/check-ui-redesign-plan.py`, `docs/ui-redesign-plan.json` |

## UXR-1 — V1: complete Servers screen

Milestone PASS: True-empty/list/selected-detail/actions form ONE mounted product screen; all old default clutter removed; context and authority preserved.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-1.1 Actual-route data-state model** | Separate true complete/unfiltered empty, loading, unavailable, no-match, partial and stale. No error-to-empty coercion. | RED mounted-route tests against current UI: 401/403/5xx/timeout/partial/late replies and normal zero. | Each state correct; failed/incomplete fetch never shows first-use empty; no target mutation without valid selection. | UXR-0.4; `web/src/main.tsx`, `web/src/workflow-servers.tsx` |
| **UXR-1.2 First-server screen** | One Servers title, short connection diagram, Add server primary, existing-Agent secondary; no toolbar/sort/filter/Table-Cards or targetless forms. | Mounted empty states for all three roles, keyboard and Add/existing-Agent navigation. | One dominant authorized next action; zero metadata/plan/admission/lifecycle forms; links reach real routes. | UXR-1.1; `web/src/workflow-servers.tsx`, `web/src/uxb-navigation.ts` |
| **UXR-1.3 Compact server inventory** | One title and toolbar; six default columns: Server, Agent connection, Approval, Services, Last observed, Action. Remove repeated headings/caveats. | 1/10/50 and 100/101-boundary datasets, unknown service counts, partial scope; desktop screenshots. | Six default columns; one compact toolbar; no invented total/service count; OS/name readable. | UXR-1.1; `web/src/workflow-servers.tsx`, `web/src/uxb-host-detail.ts` |
| **UXR-1.4 Preserve compact filters/search/sort** | Keep admission/connection, loaded-only typed search, review/name sort, chips/reset, saved admission and paging; advanced syntax in Filters/help. | Existing G11/12/15/17 and Host search/saved-view regressions plus mounted filter/reset/return. | All prior behavior retained, actor scope unchanged, no-match not denial; no stacked default control wall. | UXR-1.3; `web/src/uxb-host-search.ts`, `web/src/uxb-host-sort.ts`, `web/src/uxb-host-filter-chips.ts` |
| **UXR-1.5 Selected server detail** | Overview/Services/Activity/Settings, bounded allowed fields and related services. Remove raw object dumps and duplicated management sections. | Valid/missing/ambiguous ID; actor change; related-service errors; keyboard open/close. | Exact authorized server only; each tab works; no secrets or unauthorized by-ID fetch. | UXR-1.3; `web/src/workflow-servers.tsx`, `web/src/uxb-host-detail.ts` |
| **UXR-1.6 Contextual metadata edit** | Settings -> Edit details -> Review -> explicit Apply using selected ID; remove targetless form/ID re-entry. | Changed target/input invalidates plan; label/tags/blank-clear; cancel; exact receipt/audit. | Correct current target applied once; no manual ID transfer, stale Apply or false success. | UXR-1.5; `web/src/main.tsx::ManagedHostMetadataPanel`, `web/src/main.tsx::GuidedApplyPanel` |
| **UXR-1.7 Approval/quarantine/lifecycle actions** | Pending -> Review; disconnected -> Diagnose; eligible no-service -> Publish; separate dangerous Actions with visible impact. | Wrong target/revision/confirmation, expiry, double submit, API/role denials; identity/reservation regressions. | No unauthorized/wrong-target effects; original preview and confirmations retained; quarantine not described as terminating existing sessions. | UXR-1.5; `web/src/main.tsx::ManagedHostAdmissionPanel`, `web/src/main.tsx::ManagedHostLifecyclePanel` |
| **UXR-1.8 Return context and focus** | Preserve selected ID/filter/scroll/focus across detail/edit/service/audit and cancel/back; remove restart/retype behavior. | Browser list -> detail -> edit/audit -> back, refresh and actor switch. | Same authorized context restored; no private-state leak or stale reply overwriting current intent. | UXR-1.5; `web/src/workflow-servers.tsx`, `web/src/uxb-navigation.ts` |
| **UXR-1.9 Truthful concise status** | Separate approval/trust/Agent connection/Core health/heartbeat; short icon+label with Technical details. Remove broad Healthy and caveat paragraphs. | Missing/malformed/old timestamps, bool/0/1 flags, connected-untrusted/pending/quarantined. | Unknown never healthy/disconnected; distinct facts visible without long default prose. | UXR-1.3; `web/src/uxb-host-detail.ts`, `web/src/uxb-health-state.ts` |
| **UXR-1.10 Coherent V1 product integration** | Replace current default route with empty/list/detail/actions together; Table default plus optional preserved preference. | Actual route mount, affected suites, private dev asset parity, before/after interaction review. | V1-A/B/C visible in product; old default forms absent; no lost feature; helper-only success insufficient. | UXR-1.2, UXR-1.4, UXR-1.6, UXR-1.7, UXR-1.8, UXR-1.9; `web/src/main.tsx`, `web/src/workflow-servers.tsx` |

## UXR-2 — V2: first server to usable service

Milestone PASS: Supported platform -> install/detect -> review -> publish -> narrow policy -> connection information; no false completion or ID re-entry.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-2.1 Focused supported platform chooser** | Separate Add server task with local OS icons, supported platforms only and collapsed advanced options. | Enumerate actual platform contract; keyboard and platform-change cases. | Only supported choices; flow not appended to list; necessary advanced capabilities retained. | UXR-1.10; `web/src/p0-enrollment.tsx` |
| **UXR-2.2 Single-use invitation and expiry** | Preserve actor+role+platform+TTL exact intent, one-time display and safe copy. No automatic reissue or secret logs. | Existing issuance tests, double click, late response, user/role/form changes, copy denial and expiry. | One explicit issue; no stale credential; no secret in search/history/telemetry. | UXR-2.1; `web/src/p0-enrollment.tsx` |
| **UXR-2.3 Install/detect and recovery** | Copy/install/detected/approval/connected are distinct states; bounded supported polling and in-step timeout/error/expiry recovery. | Regression delays/out-of-order errors plus actual permitted Agent detection; reload/interruption. | No false install/connection success; no duplicate issue or automatic approval on retry. | UXR-2.2; `web/src/p0-enrollment.tsx` |
| **UXR-2.4 Detected-server review and approval** | Show exact server identity; review trust/admission independently; advance only on current valid Core APPLIED/revision. | Wrong host/operation/stale revision; approved-but-not-connected; real permitted approval. | Exact receipt drives approval; detection/trust/connectivity remain separate; no silent preapproval. | UXR-2.3; `web/src/p0-enrollment.tsx` |
| **UXR-2.5 Server -> service -> rule continuity** | Next Publish service, prefilled selected identity, narrow rule and test context. Preserve four security stages within simplified flow. | Linked mounted journey, back/cancel/reload, actor eligibility. | No ID copying or menu hunting; publish/allow/verify are distinct authoritative effects. | UXR-2.4; `web/src/uxb-navigation.ts`, `web/src/uxb-remote-service.tsx` |
| **UXR-2.6 Actionable service catalog** | Type icon/name/owner/endpoint, separate policy and transport states; preserve explicit Card/Table preference, search and facets. | 0/1/10/50/partial cases, malformed identity, actor preference and existing G13/G19 tests. | Correct resource actions and scope; no Enabled=reachable; no automatic preference change or lost filters. | UXR-1.10; `web/src/main.tsx::ResourceWorkspace`, `web/src/uxb-resource-cards.ts` |
| **UXR-2.7 Protocol-specific usable actions** | SSH Copy command; safe verified HTTP(S) Copy/Open; TCP Copy endpoint; Test & explain/Details. No fake browser terminal. | Escaping, unsafe schemes/host/port, missing username, clipboard failure, stale endpoint. | Confirmed safe output; no automatic shell execution or invented endpoint; explicit failure/unsupported state. | UXR-2.6; `web/src/uxb-service-detail.ts`, `web/src/main.tsx` |
| **UXR-2.8 Publish service focused form** | Selected server prefilled, name/type/internal target+port first; advanced options collapsed; diagram marks proposed vs confirmed address. | Port/address validation, selected target switch, absent allocator response, keyboard/error labels. | No known ID re-entry; only relevant fields; public endpoint final only after Core confirmation. | UXR-2.5; `web/src/uxb-remote-service.tsx` |
| **UXR-2.9 Service review and lifecycle** | Linked diff/tests/impact/typed confirmation; retain create/edit/disable/release semantics; no always-open Change Plan. | Stale/expired preview, failed tests, busy/double submit, cancel, ambiguous response and audit. | Exactly one intended valid change; cancel no effect; disable does not silently release reservation. | UXR-2.8; `web/src/uxb-remote-service.tsx`, `web/src/main.tsx::GuidedApplyPanel` |
| **UXR-2.10 Coherent V2 acceptance** | Complete first server through connection information and next test; preserve truthful untested state. | Real authorized linked user scenario plus failed/retry path; distinguish fixture evidence. | No false success, duplicate issue, wrong target or lost context; deployed V2 matches tested build. | UXR-2.7, UXR-2.9; `web/src/p0-enrollment.tsx`, `web/src/uxb-remote-service.tsx` |

## UXR-3 — V3: Access rules and selected-resource explanation

Milestone PASS: Focused input and exact relationships, separate policy/transport outcomes, truthful Remote/Internet/AI semantics and contextual diagnosis.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-3.1 Distinct policy-plane purpose** | Remote server/service, Internet source network/FQDN/port, AI identity/permission/provider; task-first choice. | Per-plane selectors/API and cross-plane/role negatives; Internet without Agent path. | No semantics/privilege transfer or Web-login identity substituted for network source. | UXR-1.10; `web/src/p0-access-policy.tsx`, `web/src/uxb-core-choices.tsx` |
| **UXR-3.2 Basic rule editor and advanced disclosure** | Source/target/service-or-permission/purpose first; advanced JSON/draft separate; existing authoritative workflow retained. | Basic and advanced paths, incomplete references, purpose persistence vs screen-only facts. | Normal task requires no JSON; advanced supported behavior remains; no second policy engine. | UXR-3.1; `web/src/p0-access-policy.tsx::GuidedPolicyJourney` |
| **UXR-3.3 Prepared set/delete intent** | Always show name/plane/source/target/selector/enabled/expiry/AI paths and NOT APPLIED; destructive delete impact explicit. | G06 set/delete, invalid expiry, absent values and AI optional paths. | Summary matches current form in BOTH modes; no missing value coercion; impact visible in review. | UXR-3.2; `web/src/p0-access-policy.tsx` |
| **UXR-3.4 Diff/tests/impact/typed Apply** | Preserve saved regression tests, bounded blast radius, current plan and one-shot confirmation; no generic Save bypass. | Expired/reused plan, wrong phrase, failing tests, async old intent, duplicate POST and reply loss. | Unsafe/stale plan cannot Apply; one valid effect; no invented complete impact or silent retry. | UXR-3.3; `web/src/p0-access-policy.tsx`, `web/src/uxb-impact-evidence.ts` |
| **UXR-3.5 Current/draft/preview context** | Explicit Core snapshot, proposed draft, preview time/revision labels; no browser-only authority or graph publish on click. | G05 current/proposed switch, stale revision/reply and mismatch. | Every view labeled with real evidence context; Live never implies verified reachability. | UXR-3.1; `web/src/p0-access-policy.tsx` |
| **UXR-3.6 Focused relationship visualization** | Selected resource/source/rule focus, keyboard nodes and details; preserve bounded matching beyond old 16-row display; no whole-network decoration. | G01 after-index16 match, 400 snapshot, truncation, invalid edges and no-match. | Only evidenced edges/nodes; truthful loaded counts; no-match is not DENY; selected item discoverable. | UXR-3.5; `web/src/p0-access-policy.tsx::AccessEvidenceExplorer` |
| **UXR-3.7 Policy versus actual transport** | Separate policy source->rule->destination and public endpoint->Agent->target; allow Allowed + Not tested. | Allowed with absent transport, denied with historical flow, disconnected Agent and missing telemetry. | Policy allow never becomes connection success; untested segments clear; no guessed source identity. | UXR-3.6; `web/src/p0-access-policy.tsx`, `web/src/uxb-host-detail.ts` |
| **UXR-3.8 Exact Host/policy/Audit graph pivots** | Selected service to known owning Host, same-plane exact policy and bounded audit context/back. | Existing UI02/G03/G18/G22 regressions; duplicate/missing/unloaded IDs; actual click-through and return. | Only unique authorized identity linked; no new by-ID authority; no manual ID transfer. | UXR-3.6; `web/src/p0-access-policy.tsx`, `web/src/uxb-audit-context.ts` |
| **UXR-3.9 Compact policy triage preservation** | Keep state/expiry filters, cards/table, sort/chips/reset, AI source/provider/permission and safe name/description. | G09/G20/G21/G23..27/G29; malformed times/flags/objects, partial search and preferences. | All accepted findings retained without default control wall; missing is not Never/Disabled; no secret values. | UXR-3.2; `web/src/main.tsx::PolicyWorkspace`, `web/src/uxb-policy-table-display.ts` |
| **UXR-3.10 Private policy views and verified context** | Keep G28 saved policy filter and safe prefilled draft; UI preference is not a grant. | Reopen, actor switch, unknown/legacy payload and graph->editor context. | Correct actor filter restored; no implicit grant or silently deleted unsupported entry. | UXR-3.9; `web/src/uxb-saved-views.tsx`, `web/src/uxb-saved-views.tsx` |
| **UXR-3.11 Why denied / diagnose selected service** | Contextual supported checks, observation time and next remediation route; preserve unknown/partial evidence. | Real authorized allow/deny traffic where available; absent checks, errors and diagnostic return. | Explain evidenced reason without JSON; no guessed root cause or single-port false health; target preserved. | UXR-3.7, UXR-3.8; `web/src/p0-access-policy.tsx`, `web/src/uxb-doctor.tsx` |

## UXR-4 — V3: Home, Activity, discovery and Administration

Milestone PASS: Useful next actions; every historical selected feature retained in contextual layout; common Foundation UI not duplicated.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-4.1 Purpose-first Home** | Core-observed first-use vs configured/unknown; Remote/Internet and supported AI cards with one next prerequisite. | All setup states/roles and purpose paths; resume failed stage. | No decorative zero dashboard, invented completion flag or Agent requirement for Internet. | UXR-2.10; `web/src/uxb-home.tsx`, `web/src/main.tsx::CommandCenter` |
| **UXR-4.2 Actionable attention and health** | Bounded real counts/time/scope and direct target/job/policy action; separate management health from services. | G37 partial/unknown/count/time and every item click/back. | All items actionable and true; no dead KPI, fabricated traffic/risk or failure-to-healthy-zero. | UXR-4.1; `web/src/uxb-home.tsx`, `web/src/uxb-health-state.ts` |
| **UXR-4.3 Useful services and recent work** | Authorized services/recent changes; retain personal starting page; actor-scoped preference only if supported. | Empty/stale/error feeds, actor change, actual service/change actions. | No demo feed or invented popularity; correct destination; preference preserved. | UXR-4.1; `web/src/uxb-home.tsx`, `web/src/uxb-start-page.ts` |
| **UXR-4.4 Readable Activity and selected event** | Who/what/when/result list; selected bounded detail, actual correlation/timeline and related target/back. | G07 whitelist/redaction, malformed event, keyboard, partial/empty/error. | Exact event only; no expanded all-event card wall, raw-log default or fake session replay. | UXR-1.8; `web/src/main.tsx::AuditExplorer`, `web/src/uxb-audit-context.ts` |
| **UXR-4.5 Audit time/paging/refresh/export** | Retain UTC presets, applied query/cursor, actor/result/time context, same-query refresh and authorized export/retention. | G08/G22/G36, back/reload/paging, retention/API denial. | Exact current query/page preserved; no retention completeness claim or unauthorized purge. | UXR-4.4; `web/src/uxb-audit-presets.ts`, `web/src/uxb-audit-refresh.ts` |
| **UXR-4.6 Saved Views complete preservation** | Search/sort/type/chips/reset/25-row pages/reopen; keep legacy unsupported entries with truthful states. | G30..35, 0/25/26/100 rows, actor changes and partial Core pages. | All six findings retained; private scope correct; no raw secret or false total/permission. | UXR-1.4; `web/src/uxb-saved-views.tsx`, `web/src/uxb-saved-views-page.ts` |
| **UXR-4.7 Search and migration aliases** | Ctrl/Cmd+K, type-labeled exact results, old/new names and contextual help; What changed tour link. | G18/old names, keyboard, ambiguous/unloaded IDs, role boundaries. | All existing routes discoverable; only exact authorized targets open; no private/secret leakage. | UXR-1.5; `web/src/uxb-navigation.ts`, `web/src/uxb-global-search-target.ts` |
| **UXR-4.8 Task-oriented common shell** | Home plus four groups, single title, breadcrumb, sticky header, theme/collapse preferences and icon+text nav. | All routes, legacy aliases, collapsed menu, theme/session refresh, tour dismiss/reopen. | Bounded hierarchy and preferences intact; no minor-feature root explosion or icon-only meanings. | UXR-1.10; `web/src/uxb-navigation.ts`, `web/src/main.tsx::Shell` |
| **UXR-4.9 Foundation Administration integration** | Canonical four groups; routine/advanced/destructive; available vs unsupported vs role-denied. Reuse login/Users/MFA/System/Integrations common components. | Actual task catalog, API roles, supported/unsupported states and Web-vs-MCP TLS labels. | No duplicated Foundation UI or authority; all supported tasks reachable and restrictions accurate. | UXR-4.8; `web/src/foundation-administration.ts`, `web/src/main.tsx::SystemAdministrationWorkspace` |
| **UXR-4.10 Operational detail/help preserved** | Health/Doctor/jobs/cancel/version/revisions/export/support/integration status concise with detail; existing UI only. | Existing receipt tests; actual read-only paths; absent tools/malformed job/cert/Webhook replies. | Pending/Unknown/Failed truthful; capabilities retained; no unrelated Core/OS/backup redesign or unsafe action. | UXR-4.9; `web/src/uxb-doctor.tsx`, `web/src/uxb-versions.tsx`, `web/src/uxb-revisions.tsx` |

## UXR-5 — Shared visual, responsive, accessibility and security

Milestone PASS: All affected screens satisfy Foundation styles, data/role/theme/viewport/keyboard criteria with genuine browser evidence.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-5.1 Readable Foundation visual system** | Foundation typography/spacing/tokens; title about24px, body14-16px, support12-13px, primary targets >=44px; no parallel design system. | Computed styles and before/after both themes/desktop viewports. | Measured targets met or explicit reviewed token deviation; no tiny/clipped labels or density wall. | UXR-1.3; `web/dist/styles.css`, `Foundation shared components` |
| **UXR-5.2 Disclosure and semantic labels** | Short 1-2-line default explanations, icon+label+color; accessible Technical details; critical impact remains in confirmation. | Default-absence and detail expansion assertions; actual read/review flow. | No permanent implementation prose; no color-only state or hidden essential warning. | UXR-1.9; `web/src/main.tsx`, `web/dist/styles.css` |
| **UXR-5.3 Complete offline/local assets** | Brand/logo/favicon/icons/help/styles/fonts render from same-origin approved private bundle; fix actual preview 404s. | Served URL/MIME/SHA, visual rendering and network-offline check. | Every referenced asset valid/rendered; no runtime CDN or private package source exposed by static route. | UXR-1.10; `web/dist/index.html`, `lib/web-project-files.manifest` |
| **UXR-5.4 Responsive all affected screens** | 1440x900/1280x800/375x812/320x568, light/dark; usable full-screen mobile detail and bounded table overflow. | Actual browser resize, menus, forms/review/errors and explicit Card/Table preference. | No page overflow or clipped critical action; no forced preference switch; all primary flows usable. | UXR-1.10; `web/dist/styles.css`, `web/src/workflow-servers.tsx` |
| **UXR-5.5 Keyboard/focus/accessibility** | Enter/Space/Esc, focus trap+restore, labels/errors/status announcements and text contrast >=4.5:1. | Keyboard-only flow, accessibility tree and manual focus/contrast review. | Zero unresolved serious/blocking accessibility findings; all actions named and reachable, primary targets44px. | UXR-1.10; `web/src/main.tsx`, `web/dist/styles.css` |
| **UXR-5.6 Role and session safeguards** | Preserve Admin/Operator/Read Only, CSRF/session/MFA/redaction; no reset of owner's login to make testing convenient. | Independent permitted sessions, actual login/MFA when configured, expiry, role change and direct denied API effect checks. | No unauthorized mutation/secret leak; current account/TLS/state preserved absent separate approval. | UXR-1.10; `web/src/uxb-web-session.ts`, `lib/drlink_web_auth.py` |
| **UXR-5.7 Bounded async/stale robustness** | Retain paging/100-host limits, responsive loading and interrupted flow recovery; no unsupported scale work. | Out-of-order errors, stale actors, navigation during request, double submit and 100/101 fixtures. | No stale effect/lost input/unbounded fetch; timings recorded honestly, no invented improvement rate. | UXR-1.10; `web/src/uxb-menu-evidence.ts`, `web/src/main.tsx` |

## UXR-6 — Mandatory UI-06 distinct-reviewer request

Milestone PASS: Approved durable Core contract and real requester/different reviewer/expiry/revoke/audit proof; approval dependency remains explicit.

**Current source status — 2026-10-14 KST:** UXR-6.1 is owner/security approved; UXR-6.2, UXR-6.3 and UXR-6.4 are source **IMPLEMENTED** with focused Core/Web security regressions. UXR-6.5 genuine two-user deployed proof remains **OPEN**. No UXR-6 task is promoted to ACCEPTED by source tests alone.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-6.1 Mandatory UI06 contract and approval** | Retain genuine requester/different reviewer/target/duration/expiry/revoke/audit; document minimal Core threat/schema/rollback design. Explicit security approval required. | Review current Core, concrete transaction/roles and owner decision scope. | Approved exact contract before privileged implementation; otherwise APPROVAL_REQUIRED, not excluded/completed; UI-only lock stays. | UXR-3.4; `docs/WEB_USER_JOURNEY_UX_ROADMAP.md`, `Core contract decision` |
| **UXR-6.2 Durable distinct-reviewer Core integration** | After UXR6.1 approval only: minimal persisted request/decision authority, no parallel frontend datastore/workflow engine. | Migration/rollback, distinct reviewer/self-review, target/duration bounds, transaction/audit tests. | Survives restart; unauthorized/self-review denied; no grant beyond approved target/expiry. | UXR-6.1; `Core implementation selected by approved UXR-6.1` |
| **UXR-6.3 Requester/reviewer real UI** | Pending/approved/rejected/expired/revoked, resource/purpose/requested-vs-approved duration/history; actual API, not placeholder approvals. | Real request/list/detail/review paths, wrong actor and stale target. | Different authorized personas execute real review; state/duration exactly match Core. | UXR-6.2; `UI integration selected by approved UXR-6.1` |
| **UXR-6.4 Review concurrency/expiry/revoke safety** | Atomic decision, replay protection, enforced expiry and bounded revocation with coherent audit. | Concurrent/repeated decisions, expired approval, stale revision, unauthorized revoke and access after expiry. | At most one valid decision; Core denies expired access; each effect traceable; no client-badge-only expiry. | UXR-6.2; `Approved Core request/decision and UI` |
| **UXR-6.5 Two-user UI06 proof** | Same candidate requester plus independent reviewer exercise approve/reject/expiry/revoke and authoritative readback. | Genuine two-user actions and negative authorization path; preserve evidence/source identity. | All agreed behavior proved; one actor or mocked response cannot close UI06; no silent waiver. | UXR-6.3, UXR-6.4; `UI06 browser/API/audit evidence` |

## UXR-7 — Private dev delivery and user acceptance

Milestone PASS: Same-source served assets, before-after interaction proof, all route/UXE cases, real usability observations and owner acceptance; no unreviewed omission.

| WBS | Required change / removal | Verification | Exact PASS | Dependencies / implementation anchors |
|---|---|---|---|---|
| **UXR-7.1 Reproducible private UI candidate** | Exact RC41 pins, current source, all JS/CSS/brand assets, source/hash receipt and usable rollback; no proprietary public artifact. | Affected suites, ten package digests, deterministic twice-build and install/static parity. | Current source and complete assets match; no stale private-copy build or secret/private TAR committed publicly. | UXR-1.10; `tools/build-private-link-foundation-rc41-web.py` |
| **UXR-7.2 Approved dev HTTPS deployment** | Apply coherent screen batches to existing authorized preview; preserve admin/TLS/Core data and previous candidate. No production effect. | Served JS/CSS/source SHA, reachability/login route, anonymous API denial, process endpoint and rollback integrity. | Owner reaches intended preview; served assets equal tested source; existing state preserved. | UXR-7.1; `Existing authorized dev preview and build receipt` |
| **UXR-7.3 Per-batch real visual fidelity** | Same data/role/theme/viewport before-after and actual interactions; verify every default removal and new destination. | PDF3-5 comparison on V1 then V2 then V3; record/fix deviations and rerun affected checks. | Zero undisposed visual deviation; source/assets/screens/interactions bound together; HTML/PDF/DOM alone insufficient. | UXR-7.2; `docs/UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md` |
| **UXR-7.4 20-route and three-role browser acceptance** | All current routes+shell; applicable data/theme/viewport states, supported actions and API denials. | Read whole current browser contract; execute normal logged-in flows; record each case and blockers. | All applicable cases evidenced; no unexplained skip, secret leak, unauthorized effect or inaccessible main action. | UXR-5.4, UXR-5.5, UXR-5.6, UXR-7.3; `docs/UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md` |
| **UXR-7.5 All UXE meanings and same-head user journeys** | Retain historical/current UXE01..12 meanings, real Agent allow/deny, Internet/AI, Web rollback/isolation and same-head independent users; read entire relevant contracts first. | Actual authorized lab/UI scenarios with exact Web/Core/Agent identity; no mocked traffic/SSR substituted for real evidence. | All UI-linked scenarios proved; full-product CLI/Full User E2E and release are not inferred or waived by UI acceptance. | UXR-7.4, UXR-2.10, UXR-3.11, UXR-6.5; `docs/FULL_USER_E2E_SCENARIOS.md`, `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` |
| **UXR-7.6 Real novice usability measurements** | Five independent novices; identical before-after tasks; discovery time, clicks, wrong menus and assistance recorded; no fake personas. | Find next action, pending review, service publication, explanation and return. Predeclare10s discovery target. | All complete applicable tasks without raw-ID transfer/unprompted help; >=4/5 find first next action within10s; failures corrected and real results retained. | UXR-7.3; `Usability evidence in existing ledger` |
| **UXR-7.7 Exact-head UI CI and review closure** | All affected suites/RC41/build/review; only minimal direct WBS prerequisites, not unrelated CI cleanup. | Inspect actual job logs/review threads, separate inherited vs new, bind exact candidate. | UI-related checks green; actionable UI findings resolved; unrelated failures still reported and global release not falsely green. | UXR-7.1; `tests/run-all.sh`, `.github/workflows/foundation-rc41-consumer.yml` |
| **UXR-7.8 Final no-omission acceptance and scope unlock** | All required WBS including UI06, removed clutter and retained capabilities reconciled; owner feedback and source-identical final review. | Run plan integrity and closure checks; compare every PASS criterion to actual evidence/defects. | Every required item accepted, no unresolved UI defect/deviation and owner acceptance OR explicit later owner scope change. Otherwise exclusive lock stays; no automatic merge/release. | UXR-7.5, UXR-7.6, UXR-7.7; `docs/ui-redesign-plan.json`, `GitHub184`, `GitHub182` |

## No-omission source register

- `docs/COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `360cfd07729609bd1ddda9f1461bf5ea248ae3b8e78c8f01c024cb913464f08e`
- `docs/COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `469a3cb071ae4a16d362032d16f50885dade85277180de058ab21060da5bc9cc`
- `docs/WEB_UX_COMPETITIVE_AUDIT_2026-10.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `2bdf53aac57375038f19a16477f0b74255ea3d6ee407762bcd98ab9ba24937a0`
- `docs/WEB_SAAS_UX_SYSTEM.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `c92c139771436afffdc3b842523082ccf02c6741b98cd1a6e1156fc63b0c8def`
- `docs/WEB_P0_UX_IMPLEMENTATION.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `5a41fee57a6967b7b8c25c80bb1474bf8668af6a86050e388fab3f64da066a42`
- `docs/PFCI_DRLINK_HOST_UX_SOURCE_CANDIDATE.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `4af3707fbd839b3efd1b92d6a6b4089cbcc9735eb0363f5470d97a2b6a66d23a`
- `docs/HUMAN_UX_ADVERSARIAL_E2E.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `bb24688ac9c4ed7bef4e19c463e7e65dd89c596a284d3997b2b271aefbf0f3c1`
- `docs/UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `e3003e2c2542d7396907439544f2922733dc664fd021e4d0fee6e933c76ef50a`
- `docs/WEB_USER_JOURNEY_UX_ROADMAP.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `542ac2c68a3bfb8f6ab50c0831ba89a6fe66fe59317cfa37dcfb0be26c92b3ea`
- `docs/DATA_RELAY_ROADMAP.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `5cad585c315b1cfce058ecfe92e86f82eadc6d2a63fbac2b5bf0d77d23056470`
- `docs/FOUNDATION_RC41_LINK_CONSUMER.md` @ `914d5c459a99d6e4cfae28f6b51468fa73a80c3a`; SHA256 `20732d1539906ccea4d19cb4f8a6ba8fb7a38249d558f9482883c6827ec80ac4`
- `docs/WEB_USER_JOURNEY_UX_ROADMAP.md` @ `c14b3c0b044504ee8d20fe806d95541a7bd69573`; SHA256 `75c885b7812868ba7a4eb8c2aeacf83e0dcef9b4d8a39f8eb7eb111f58be9a7a`; Original19
- `DRLink_UI_Reanalysis_Decision_20261014.pdf`; SHA256 `10dc9a02f969b4268d77bd2a439d055ba1fd0a2827b77ebdf77b5531eb4ff300`; Five pages, all decisions restated; attachment not required at resume
- `DRLink_Workflow_UI_Proposal.html`; Eight illustrative screens, no API/acceptance evidence
- `#184#issuecomment-6159404029;#182#issuecomment-6159409064`; Existing fidelity contract and next action

### All19 original vendor findings, retained verbatim as historical evidence

These are earlier observations, not a fresh vendor login or version audit. Original URLs/licenses/REA limits stay in their source ledgers.

| Product | Historical observation | Retained adoption decision | Original source |
|---|---|---|---|
| **Tailscale** / mesh ZTNA | Device-centric Machines → Add device; visual rule form for source, destination, port; policy-test tab | Give users named tasks and a basic rule builder with pre-save regression testing | [Device setup](https://tailscale.com/docs/features/access-control/device-management/how-to/set-up), [Visual editor](https://tailscale.com/docs/reference/visual-editor) |
| **NetBird** / self-hosted ZTNA | Control Center maps user/peer/group/policy to resource; Live/Draft review and deploy, including incomplete-change warnings | Effective-access diagram tied to actual Core facts; keep review/test before mutation; do not copy browser-only draft persistence as authority | [Control Center](https://docs.netbird.io/manage/control-center), [Draft mode](https://netbird.io/knowledge-hub/control-center-draft-mode) |
| **Twingate** / resource ZTNA | Setup order Remote Network → Resource → Connector → Client; Resource/User detail access graph; role-aware Admin UI | Setup checklist, resource-focused “who can access it?”, explicit roles | [Quick Start](https://www.twingate.com/docs/quick-start), [Resources](https://www.twingate.com/docs/resources), [Admins](https://www.twingate.com/docs/admins) |
| **Firezone** / self-hosted-resource ZTNA | Quickstart: Site → Gateway → Resource → Policy → Client; default-deny explicitly explained | “First useful connection” journey, dependency-aware steps, teach deny-by-default up front | [Quickstart](https://www.firezone.dev/kb/quickstart) |
| **Cloudflare One** / SSE | Replaced product-name navigation with task-oriented labels, guided menu migration on login, old/new term search and contextual settings; streamlined policy builders | Rename labels to real tasks; search aliases; one “What changed?” tour; no backend contract changes | [Navigation update](https://developers.cloudflare.com/changelog/post/new-cloudflare-one-navigation-and-product-experience/), [Changelog](https://developers.cloudflare.com/cloudflare-one/changelog/) |
| **Teleport** / infra access | Resource-first Web UI, active sessions and access-request/review interfaces, distinguished per client tool | Task-centered resource details and reviewer context; do not falsely advertise recording/requests where unavailable | [Web UI](https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/) |
| **StrongDM** / PAM | Admin UI separates Access, Resources, Audit and Principals; Access Requests page has Catalog/Requests tabs and purpose/duration (Enterprise) | Access-first catalog, inline purpose/expiry, clear Operator vs Administrator tasks, explicit edition caveat | [Admin guide](https://docs.strongdm.com/admin), [Requests](https://docs.strongdm.com/users/access-requests) |
| **HashiCorp Boundary** / self-managed access | Target/host catalog organization; 8-step beginner tutorial covers Admin console, first target and connections | First-use guided tour with concrete target and next action, but do not copy Boundary internal scope model | [Community quickstart](https://developer.hashicorp.com/boundary/tutorials/get-started-community) |
| **BeyondTrust PRA** / privileged remote access | Explicitly separates /appliance (host config), /login (administration), and access console (operator work); ordered setup | Separate first-use operation, account/security settings and advanced appliance recovery | [Getting started](https://docs.beyondtrust.com/pra/rs/docs/privileged-remote-access-getting-started) |
| **Microsoft Entra Private Access** / enterprise ZTNA | Quick Access guided connector→app/forwarding→client workflow, then per-app segmentation | Offer first access in minimum safe steps, then explain a more granular per-service policy | [Quick Access](https://learn.microsoft.com/en-us/entra/global-secure-access/quickstart-quick-access), [Per-app](https://learn.microsoft.com/en-us/entra/global-secure-access/quickstart-per-app-access) |
| **ZeroTier** / managed mesh | New Central quickstart focuses on creating a network, joining and approving two devices, verifying connectivity | “Set up and test” as one continuous user goal; distinct authorization vs connected state | [Quickstart](https://docs.zerotier.com/quickstart/), [New Central](https://docs.zerotier.com/new-central/) |
| **Netmaker** / self-hosted network | Annotated admin UI, sensible network form defaults, consolidated Gateway/Remote Access setup | Minimize irrelevant fields for defaults and make effective route/host selection explicit | [UI guide](https://docs.netmaker.io/docs/references/user-interface), [Gateway guide](https://docs.netmaker.io/docs/features/gateways) |
| **NordLayer** / SASE admin | Documented nav simplification, form redesign, responsive/WCAG improvements, descriptive renaming and tabs | Plain-language labels, accessible dialogs and mobile-friendly administration forms | [Control Panel changelog](https://help.nordlayer.com/docs/control-panel-2) |
| **JumpCloud** / identity/admin | Simplified renamed Admin Portal navigation and New Admin Checklist; policies grouped into Info/Assignments/Conditions/Action | Contextual checklist, human-readable field groups and migration/search for old labels | [Navigation](https://jumpcloud.com/support/updated-admin-portal-navigation), [Policy editor](https://jumpcloud.com/support/configure-a-conditional-access-policy) |
| **Palo Alto Strata Cloud Manager** / SASE | Simplified consistent left-side navigation and unified workflow for network data, onboarding and insights | Consistent group titles, task-to-evidence drill-down; avoid copying SOC-scale telemetry | [First Look](https://origin-docs.paloaltonetworks.com/strata-cloud-manager/getting-started/overview/first-look) |
| **Zscaler ZPA** / private app | Application dashboards have bounded time filters and drill-down into app usage | Show observation time and source, drill into a failing application, not an unexplained zero | [Applications dashboard](https://help.zscaler.com/zpa/viewing-applications-dashboard) |
| **Appgate SDP** / on-prem SDP | Policies UI distinguishes access entitlements, admin privileges, client controls, DNS and deny conditions | Preserve distinct DRLink policy planes and make protected effect explicit | [Using policies](https://support.appgate.com/docs/using-policies-v6-5) |
| **OpenZiti ZAC** / self-hosted SDP | Browser-based Ziti Admin Console to configure and explore controller networks | Self-contained admin interface and discoverable infrastructure concepts; no assumption of feature equivalence | [Ziti Admin Console](https://openziti.io/docs/learn/quickstarts/zac/) |
| **Netskope Private Access** / private app | Private-app setup/troubleshooting docs and a context-specific Troubleshooter listing checks and solutions; vendor warns single-port health checks can mislead | One-click “Why can't I connect?” from a resource with fidelity/partial-evidence warnings | [Private Access FAQs](https://docs.netskope.com/en/private-access-faqs), [App definition](https://docs.netskope.com/en/create-a-private-app-definition) |

### Combined22 vendor references to implementation

19 original products overlap the later13 audit; MeshCentral/Pomerium/Grafana are additional retained references. This is not22 new studies.

| Vendor | WBS |
|---|---|
| Tailscale | UXR-2.1, UXR-3.2 |
| NetBird | UXR-1.3, UXR-3.5, UXR-3.6 |
| Twingate | UXR-3.8, UXR-2.5 |
| Firezone | UXR-2.5, UXR-2.6, UXR-4.3 |
| Cloudflare One | UXR-4.7, UXR-4.8 |
| Teleport | UXR-2.3, UXR-2.7, UXR-6.3 |
| StrongDM | UXR-6.3, UXR-4.4 |
| HashiCorp Boundary | UXR-1.5, UXR-2.5 |
| BeyondTrust PRA | UXR-4.9 |
| Microsoft Entra Private Access | UXR-2.5, UXR-3.1 |
| ZeroTier | UXR-2.3, UXR-2.4 |
| Netmaker | UXR-2.8, UXR-3.2 |
| NordLayer | UXR-5.1, UXR-5.4, UXR-5.5 |
| JumpCloud | UXR-4.1, UXR-4.7, UXR-4.9 |
| Palo Alto Prisma Access / Strata | UXR-4.2 |
| Zscaler ZPA | UXR-4.5, UXR-3.11 |
| Appgate SDP | UXR-3.1, UXR-5.6 |
| OpenZiti ZAC | UXR-4.8, UXR-5.3 |
| Netskope | UXR-3.11, UXR-4.2 |
| MeshCentral | UXR-1.4, UXR-1.5 |
| Pomerium | UXR-2.7 |
| Grafana | UXR-3.10, UXR-4.6 |

### All CUI-001..040 reference decisions

40 ledger slots are not40 actual authenticated screens. CUI027/028 are historical crosswalk assignments. Rejected ideas stay explicitly NOT_ADOPTED, not hidden unfinished features.

| Reference | Vendor/idea | Disposition | WBS |
|---|---|---|---|
| CUI-001 | NetBird: Selected peer/policy and Current/Draft | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.5, UXR-3.6, UXR-4.2 |
| CUI-002 | Tailscale: Basic rules/tests/advanced | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.2, UXR-3.3, UXR-3.4 |
| CUI-003 | Twingate: Resource graph and exact policy/Host | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.6, UXR-3.8 |
| CUI-004 | Teleport: Distinct requester/reviewer | GATED_REQUIRED: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9, UXR-6.1, UXR-6.2, UXR-6.3, UXR-6.4, UXR-6.5 |
| CUI-005 | StrongDM: Requests/duration/history | GATED_REQUIRED: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-6.1, UXR-6.2, UXR-6.3, UXR-6.4, UXR-6.5 |
| CUI-006 | Cloudflare One: Actor/time/result audit filters | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.4, UXR-4.5 |
| CUI-007 | StrongDM: Selected event details | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.4 |
| CUI-008 | HashiCorp Boundary: Session broker/recording | NOT_ADOPTED: No Link session broker/recording; preserve existing bounded observation only. | UXR-0.2 |
| CUI-009 | Palo Alto: Audit UTC shortcuts | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.5 |
| CUI-010 | Zscaler: Investigation ranges, not vendor SLA | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. Vendor-specific retention/analytics SLA not adopted. | UXR-4.5 |
| CUI-011 | Palo Alto: NOC traffic/risk analytics | NOT_ADOPTED: No authoritative corresponding traffic/risk telemetry; fake/decorative NOC analytics rejected. | UXR-0.2 |
| CUI-012 | NetBird: Policy state filter | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-013 | Firezone: Service type/configuration filters | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-2.6 |
| CUI-014 | Firezone: Resource detail | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.8, UXR-4.7 |
| CUI-015 | Firezone: Preferred starting page | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.1, UXR-4.3 |
| CUI-016 | NetBird: Host sort | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-1.4 |
| CUI-017 | NetBird: Mesh-specific peer/IP sorting | NOT_ADOPTED: Different mesh model; no invented IP/group/topology relation. | UXR-0.2 |
| CUI-018 | NetBird: Heartbeat versus last seen | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-1.9 |
| CUI-019 | NetBird: Host filter chips | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-1.4 |
| CUI-020 | Teleport: Global search -> exact resource | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.8, UXR-4.7 |
| CUI-021 | Pomerium: Safe SSH connection copy | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-2.7 |
| CUI-022 | Teleport: Resource cards/table | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-1.10, UXR-2.6 |
| CUI-023 | Teleport: Expiry/duration triage | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-024 | Teleport: Read-only policy review | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-025 | Teleport: Policy -> Audit | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.8, UXR-4.5 |
| CUI-026 | NetBird: Policy name sort | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-027 | NetBird: Policy reset/chips, legacy assigned slot | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. Historical crosswalk association, not a newly observed screen. | UXR-3.9 |
| CUI-028 | NetBird: Source/target facts, legacy assigned slot | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. Historical crosswalk association, not a newly observed screen. | UXR-3.9 |
| CUI-029 | NetBird: AI source/provider columns | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-030 | NetBird: AI reference filters | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-031 | Grafana: Saved policy query | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.10 |
| CUI-032 | NetBird: Safe rule name/description | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-3.9 |
| CUI-033 | Grafana: View name search | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-034 | Grafana: View newest/oldest | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-035 | Grafana: View target type | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-036 | NetBird: View reset | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-037 | NetBird: View chips | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-038 | NetBird: 25-row paging | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.6 |
| CUI-039 | NetBird: Same-scope refresh | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.5 |
| CUI-040 | NetBird/Twingate: Home scoped evidence drilldown | ADOPT_PRESERVE_AND_VERIFY: Retain original source-supported concept, integrate and revalidate; not historical browser PASS. | UXR-4.2 |

### All G-01..37 plus prior/new promises

| Requirement | WBS |
|---|---|
| G-01 | UXR-3.6 |
| G-02 | UXR-3.2, UXR-3.4 |
| G-03 | UXR-3.8 |
| G-04 | UXR-6.1, UXR-6.2, UXR-6.3, UXR-6.4, UXR-6.5 |
| G-05 | UXR-3.5 |
| G-06 | UXR-3.3, UXR-3.4 |
| G-07 | UXR-4.4 |
| G-08 | UXR-4.5 |
| G-09 | UXR-3.9 |
| G-10 | UXR-2.7 |
| G-11 | UXR-1.4 |
| G-12 | UXR-1.4 |
| G-13 | UXR-2.6 |
| G-14 | UXR-4.1, UXR-4.3 |
| G-15 | UXR-1.4 |
| G-16 | UXR-1.9 |
| G-17 | UXR-1.4 |
| G-18 | UXR-4.7, UXR-3.8 |
| G-19 | UXR-2.6, UXR-1.10 |
| G-20 | UXR-3.9 |
| G-21 | UXR-3.9 |
| G-22 | UXR-3.8, UXR-4.5 |
| G-23 | UXR-3.9 |
| G-24 | UXR-3.9 |
| G-25 | UXR-3.9 |
| G-26 | UXR-3.9 |
| G-27 | UXR-3.9 |
| G-28 | UXR-3.10 |
| G-29 | UXR-3.9 |
| G-30 | UXR-4.6 |
| G-31 | UXR-4.6 |
| G-32 | UXR-4.6 |
| G-33 | UXR-4.6 |
| G-34 | UXR-4.6 |
| G-35 | UXR-4.6 |
| G-36 | UXR-4.5 |
| G-37 | UXR-4.2 |
| UX-1 | UXR-3.6, UXR-3.7, UXR-3.8, UXR-3.11 |
| UX-2 | UXR-1.6, UXR-2.8, UXR-3.2, UXR-3.4 |
| UX-3 | UXR-1.2, UXR-2.1, UXR-2.2, UXR-2.3, UXR-2.4, UXR-2.5 |
| UX-4 | UXR-1.9, UXR-3.5, UXR-4.2 |
| UX-5 | UXR-3.8, UXR-4.4, UXR-4.5 |
| UX-6 | UXR-4.9, UXR-5.6 |
| UX-7 | UXR-5.4, UXR-5.5, UXR-7.4 |
| UX-8 | UXR-1.1, UXR-1.4, UXR-4.6, UXR-4.7, UXR-5.2, UXR-5.7 |
| UI-01 | UXR-3.6, UXR-3.7 |
| UI-02 | UXR-3.8 |
| UI-03 | UXR-1.8, UXR-2.5, UXR-3.8, UXR-3.10 |
| UI-04 | UXR-1.10, UXR-4.1, UXR-4.9 |
| UI-05 | UXR-2.9, UXR-3.4 |
| UI-06 | UXR-6.1, UXR-6.2, UXR-6.3, UXR-6.4, UXR-6.5 |
| UXB-00 | UXR-0.1, UXR-0.2, UXR-0.5 |
| UXB-01 | UXR-4.7, UXR-4.8 |
| UXB-02 | UXR-4.1, UXR-4.2 |
| UXB-03 | UXR-2.10, UXR-3.1, UXR-3.4 |
| UXB-04 | UXR-1.8, UXR-3.8, UXR-3.11 |
| UXB-05 | UXR-4.9, UXR-5.2 |
| UXB-06 | UXR-7.4, UXR-7.5, UXR-7.6, UXR-7.8 |
| V1-A | UXR-1.1, UXR-1.2 |
| V1-B | UXR-1.3, UXR-1.4, UXR-1.9 |
| V1-C | UXR-1.5, UXR-1.6, UXR-1.7, UXR-1.8, UXR-1.10 |
| V2-A | UXR-2.1, UXR-2.2, UXR-2.3, UXR-2.4, UXR-2.5 |
| V2-B | UXR-2.6, UXR-2.7, UXR-2.8, UXR-2.9, UXR-2.10 |
| V3-A | UXR-3.1, UXR-3.2, UXR-3.3, UXR-3.4, UXR-3.5, UXR-3.6, UXR-3.7, UXR-3.8, UXR-3.9, UXR-3.10, UXR-3.11 |
| V3-B | UXR-4.1, UXR-4.2, UXR-4.3, UXR-4.4, UXR-4.5 |
| WU1 | UXR-1.10 |
| WU2 | UXR-2.10 |
| WU3 | UXR-3.11 |
| WU4 | UXR-4.1, UXR-5.4, UXR-7.8 |
| UX-P1-A | UXR-1.4 |
| UX-P1-B | UXR-1.4 |
| UX-P1-C | UXR-1.5 |

### Preserve both UXE numbering versions

Same UXE numbers changed meaning between the original and current document. Both versions are retained; matching numeric labels alone is not coverage.

| Versioned scenario | Meaning | WBS |
|---|---|---|
| LEGACY19-UXE-01 | New Admin logs in and locates “Add Agent” without instructions  /  Can discover action and distinguish on-prem install roles | UXR-7.5 |
| LEGACY19-UXE-02 | New Admin registers Linux Agent, reviews admission, approves with explicit confirmation  /  Shows installation/waiting/trust/connection as separate states | UXR-7.5 |
| LEGACY19-UXE-03 | Same Admin publishes only SSH service, creates narrow Remote WHITELIST and tests it  /  One understandable path; Core outcome confirmed and runtime evidence reported honestly | UXR-7.5 |
| LEGACY19-UXE-04 | An intentionally denied source tries to connect  /  A single “Why denied?” workflow shows truthful reason, policy and next action; no false ALLOW | UXR-7.5 |
| LEGACY19-UXE-05 | Admin sets Internet Access (protected source to approved external destination)  /  Correct distinct plane and selector semantics | UXR-7.5 |
| LEGACY19-UXE-06 | Admin defines AI Identity permission and tests AI Access  /  Permission Object/Group semantics, not Remote/Internet port confusion | UXR-7.5 |
| LEGACY19-UXE-07 | Operator reviews Jobs, pending changes and Activity evidence  /  Finds evidence without navigating obscure internals or elevating permissions | UXR-7.5 |
| LEGACY19-UXE-08 | Read Only attempts admin-only action; Admin tests local MFA/recovery path  /  View affordances and Core denial match; no secret disclosure | UXR-7.5 |
| LEGACY19-UXE-09 | Fresh/no-data or Core temporarily unavailable  /  Honest empty vs error vs UNKNOWN; visible recovery guidance | UXR-7.5 |
| LEGACY19-UXE-10 | Repeat UXE-01..09 on desktop, **375px and 320px**, keyboard and accessible focus  /  No critical action clipped or inaccessible; dialogs, tables, error/help and onboarding work | UXR-7.5 |
| LEGACY19-UXE-11 | Change plan proposed then modified, tests fail, preview expires and wrong confirmation entered  /  No stale-plan Apply, hidden bypass, silent save, unauthorized effect or erroneous success | UXR-7.5 |
| LEGACY19-UXE-12 | Offline install/reinstall, original Web/Core/CLI regression  /  No CDN/new infrastructure dependency; Web remains optional and not authoritative | UXR-7.5 |
| CURRENT-UXE-01 | Admin first login, Home, every root menu and Help orientation | UXR-7.5 |
| CURRENT-UXE-02 | Real enrollment code and Managed Host pending admission | UXR-7.5 |
| CURRENT-UXE-03 | Approve vs quarantine, operator rights and Core revision | UXR-7.5 |
| CURRENT-UXE-04 | Narrow SSH Remote Service, draft and policy preview | UXR-7.5 |
| CURRENT-UXE-05 | Actual allowed traffic, peer/Agent and evidence readback | UXR-7.5 |
| CURRENT-UXE-06 | Actual denied traffic, Core decision, explanation and audit | UXR-7.5 |
| CURRENT-UXE-07 | Internet Access separate policy and observation | UXR-7.5 |
| CURRENT-UXE-08 | AI Access separate identity/permission policy | UXR-7.5 |
| CURRENT-UXE-09 | Operator activity, jobs, diagnoses and role write limits | UXR-7.5 |
| CURRENT-UXE-10 | Read Only menu visibility and mutation denial | UXR-7.5 |
| CURRENT-UXE-11 | Stale/invalid plan, unknown/partial/no-data and recovery | UXR-7.5 |
| CURRENT-UXE-12 | Desktop 1440px, phone 375/320px, keyboard, Web uninstall/Core isolation | UXR-7.5 |

## Mandatory OLD -> NEW removals and retained capability boundaries

Default zero-host screen: no search/sort/filter/Table-Cards or targetless metadata/plan/admission/lifecycle form. Metadata moves to selected Server Settings; change plan to Review; approval/quarantine/lifecycle to selected Actions with impact/confirmation. Long Core/heartbeat prose moves to accessible Technical details, not deletion of essential safety. Table default and optional preference survive; role restrictions and truthful unknown values survive. Current broad Healthy is scoped to the actual management observation, not Agent/service success.

Maintain all20 existing routes: overview, hosts, services, enrollments, setup, policies, access, objects, drafts, health, hygiene, audit, jobs, revisions, versions, views, doctor, system, users, integrations; plus shell/search. Discover newly present actions during browser census rather than assuming the list never changes. Four Foundation groups: Access & security; Platform & network; Lifecycle & recovery; Operations & audit. Existing certificate/backup/update/retention/export/Service Account/Webhook/Doctor UIs remain accessible at appropriate advanced/role/confirmation destinations, but redesign does not authorize dangerous operations.

Do not copy competitor code/branding/proprietary or copyleft assets without a separate license decision. Do not add NOC chart catalogs/fake telemetry, mesh IP assumptions, session broker/recording, browser terminal, RMM/MDM/discovery, unbounded fleets, a second datastore/policy engine or runtime CDN. Rejected concepts remain documented; accepted portions of mixed findings are preserved.

## Current implementation status and continuation

All66 new WBS acceptance states start SPEC_BOUND. Existing functionality is reused; no visible redesign is claimed complete by this planning update. Preserve uncommitted docs/WEB_USER_JOURNEY_UX_ROADMAP.md, web/src/workflow-servers.tsx and web/tests/workflow-servers.test.mjs. They were observed on entry; presence is not default-route integration proof.

First implementation: UXR-1.1 mounted actual-route state RED tests, then UXR-1.2..10 as one V1 screen. Use the existing WIP after verifying identity/ownership; no competing component. Update private dev preview after coherent batch, inspect asset identity and real screen/click outcomes; fix findings and continue V2/V3. Only minimal directly named prerequisites may interrupt. Do not ask the owner to do engineering verification as a substitute for available tools, and do not ask another blanket implementation permission.

Run `python3 scripts/check-ui-redesign-plan.py` for plan integrity. Run `python3 scripts/check-ui-redesign-plan.py --closure` for completion structure; it MUST FAIL while acceptance evidence is absent. Status/evidence must be honestly audited; no invented percentages/times or elapsed-date promises. Full owner acceptance is distinct from ordinary commits, product merge and release.
