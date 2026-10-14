# DataRelay Link 3.0 — Unified R1–R7 Execution Roadmap

## Accepted visual workflow redesign — 2026-10-14

Owner accepted the revised competitor-screen proposal and requested continuation.
This overrides the previous Foundation-package-only implementation scope for the
Link-owned Web screens below. Foundation shared components/tokens, Core APIs,
authorization, credentials, stored state, production and release gates are unchanged.
Existing Work Packet #182, single roadmap #184 and Draft PR #206 are reused.

Goal: replace the text-heavy menu/form wall with target-first tasks, not a NOC
analytics dashboard. The reviewed HTML proposal is illustrative, not test evidence.
Reuse the existing competitor ledger: NetBird compact resource list, Tailscale
focused add/edit forms, Teleport resource actions, Twingate selected-resource graph.
No vendor code/assets or fabricated traffic/service-count/connection verdicts.

1. **WU1 — Servers & Agents:** true empty onboarding vs loading/error/no match;
   compact loaded-scope status tabs/search/table; selected-server detail with
   Overview/Services/Activity/Settings; existing metadata/admission/lifecycle forms
   appear only for the selected authorized server, never below the empty list.
2. **WU2 — Connect and publish:** focused Agent setup, selected-server service
   publication and usable service cards/actions; preserve exact Preview/Apply guards.
3. **WU3 — Explain a selected service:** contextual source/rule/destination path;
   policy verdict separate from connection testing; no new authority or fake telemetry.
4. **WU4 — Home and visual qualification:** next tasks rather than decorative zero
   metrics; readable Foundation-token typography, responsive and keyboard checks.

No schema migration/new dependency or authorization expansion. Preserve saved views,
advanced filters, pagination, actor scoping and UNKNOWN evidence. Code/static tests
are not genuine two-user E2E. Build proprietary RC41 compiled assets only in private
scratch; deploy only to the already owner-approved development preview on port 19044,
preserving its data/account/TLS and rollback assets. Never commit those bytes publicly.

Acceptance: first empty viewport has one Add server primary action and no targetless
mutation forms; invalid/incomplete inventory never claims empty; selectable rows open
a keyboard-operable detail; dangerous actions retain existing previews/confirmation;
text is disclosed when relevant; live served asset hashes match the tested build.

---


> **2026-10-12 source status pointer:** [40-slot competitor UI adoption crosswalk](COMPETITOR_UI_APPLIED_MATRIX_2026-10-12.md) reconciles historical proposals against the current Draft PR #206. G01–G37 source findings are recorded, with only genuine UI-06 Core-backed independent reviewer still a security-design/authorization gate; real Browser E2E is deferred at owner request. The single execution roadmap remains GitHub Issue #184.

> **ONE CURRENT EXECUTION ROADMAP:** [GitHub Issue #184 — DataRelay Link 3.0 R1–R7](https://github.com/datarelay-labs/datarelay-link/issues/184).
> This file is a **repository-local index, not an additional task queue**. The old UXB-00..06, UXB-06F, L-CI-0..4 and B1–B5 per-feature execution lists are **superseded** as roadmaps by #184. Their historical code, tests, source investigations, review evidence and mandatory acceptance contracts are retained in Git history and the named canonical documents; **do not delete/reimplement verified completed functionality**.
> **Latest owner priority, 2026-10-11 (supersedes old implementation-first text below):**
> **P0-1 FIRST: analyze actual competitor UI screens and user click paths**, with dated official images/videos, exact provenance, role/empty/error/focus behavior when observable, current DRLink gap and license. Consider/use REA (Ghidra/Hopper/MCP) **only when needed and actually available/authorized/licensed**; never copy proprietary assets/code or claim REA used if not.
> **P0-2 SECOND: select Adopt/Adapt/Reject gaps from that evidence, then directly implement approved, source-original DRLink UI changes**, RED→GREEN test/build on the current branch and update existing PR #206. Repeat analysis → selection/application; source-only test is not installed Browser/User E2E.
> Evidence & current G-01 initial selection: `docs/COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md`. Single canonical schedule remains GitHub Issue #184 and ACTIVE Work Packet #182; no duplicate roadmap.
> **Owner P0 override (2026-10-11):** The existing single GitHub #184 now schedules
> **ALL applicable competitor-informed UX-1..8 and UI-01..06** ahead of unrelated
> phases as C-UX-A→B→C→D. UI-06 (single-reviewer time-bounded access request)
> is owner-required but requires an actual canonical Core request/decision
> contract; it is not implicitly implemented by Temporary Access alone.
> UI-02 Core-observed Remote Service→owning Host source was implemented in existing
> Draft PR #206 at `192677cf`; it is still unqualified by real 3-role/320px/375px Browser E2E.
> This is **a priority/status pointer, never a separate implementation queue**.
> Product authority: `PRODUCT_MASTER.md`, `WEB_MANAGEMENT.md`, `MANAGEMENT_SURFACE_CONTRACT.md`, `DATA_RELAY_ROADMAP.md`, `WEB_SAAS_UX_SYSTEM.md`. DRLink Core/CLI retains authorization authority; Web is optional, SQLite is the one Core datastore, Remote / Internet / AI remain separate security planes.
> Link Product Foundation B2–B6 coordinator [#207](https://github.com/datarelay-labs/datarelay-link/issues/207) now points to the same issue. Foundation's separate cross-product [#87](https://github.com/datarelay-labs/datarelay-product-foundation/issues/87) is **not** a second Link implementation queue.

## Large work blocks (actual status is always the latest exact HEAD / CI / worktree)

| Block | Scope / existing owners | Source status vs outstanding acceptance |
| --- | --- | --- |
| **R1 — Preserve work & PF9 ACL preflight** | #196 / Draft #197 | Five original WIP files are already committed as `444b87c1`, tree clean; native affected ACL/MFA/Web tests PASS. Linux CI remains FAIL in inherited protected Client/Core enrollment path; no real Web/SSH ACL activation |
| **R2 — B2 shared Administration + PF-CI modern UX** | #191/#193 + #182/#183 + #206 | Common Administration, Saved Host admission filter, grouped Host detail and *bounded loaded-only* typed Host Search are source implemented; cross-branch Web/Core/API compatibility and actual Browser/roles remain OPEN |
| **R3 — B3 Web MFA and management ACL** | #188/#189 + #196/#197 | Password→separate OTP default OFF, byte-pinned Foundation ingress evaluator and read-only Admin status are source implemented; installed Web/SSH source enforcement, proxy trust, recovery & rollback NOT VERIFIED |
| **R4 — B4 connectivity & operations** | #200/#201 | Product-owned DNS, time and cert diagnostics in source; proxy/CA/SMTP/Webhook authentic outcomes/negative cases still unqualified |
| **R5 — B5 backup / restore / offline upgrade** | #202/#203 + #204/#205; **#198/#199 HOLD** | Configuration diff and offline byte-level preflight source-only; real isolated restore/upgrade/signer proof missing. Protected #199 generated bootstrap scope must not be changed or rerouted |
| **R6 — Core 3.0 functional & 100-host hardening** | #135/#168 | Core/Agent jobs, audit, Webhooks and Access Hygiene source/fixtures exist; independent signed Agent Canary/Health/failure/rollback, CLI Direct+AI feature/scenario ledger and exact-head native CI still required |
| **R7 — B6 genuine users ×2 and release** | Browser / CLI / Full User E2E contracts | Directly observed Admin/Operator/Read Only Browser PASS → two real users PASS1/PASS2 same **installed immutable HEAD** → freeze → native CI/hash/SBOM/provenance/public smoke → owner acceptance and separately authorized release. **NOT VERIFIED** |

Do not reimplement already source-delivered L-CI saved filter/detail/typed search (Draft #206). Typed search can operate only on **loaded, authorized Core projection**; unsupported `tag:`, `group:`, `ip:`, unobserved data and partial pagination must not fabricate a fleet-wide zero or healthy result. Source/SSR/test success does **not** qualify a live user experience.

## R2 scoped source and integration evidence retained from commit `db09e331`

- On this isolated #206 source candidate, `08791676` corrected a real Host table vs detail discrepancy: untrusted truthy `connected` / unrelated lifecycle/status text had been displayed as confirmed connectivity. Both now consume the same Core Boolean / SQLite 0/1 tri-state mapping, **Connected / Disconnected / UNKNOWN**. Before-fix regression RED; after-fix Host detail 6/6, Web Journey 90/90, UX source 56/56, P0 11/11, Foundation Admin 6/6, Core Query 24/24, Web bundle 6/6, Web build, secret and metadata scans PASS **on the corresponding source HEAD**. These are not Browser or Full User E2E.
- Read-only stacked PR integration found real overlapping files: #206 sits on #183; #193 Foundation source shares #183 but overlaps `web/src/main.tsx`, `web/package.json`, compiled assets and UX tests. Core #168 head `96246f91` and Web source share older `153e3dd4` and have additional source/generated-bundle conflicts. **No auto-merge or tree overwrite**; reconcile conflict-by-conflict on an independently authorized coherent candidate and rerun its native/real-user qualification.
- Both parent #183 and child #206 Linux native CI have independently failed with `allocator rejected enrollment: enrollment could not be committed to Core` after dual-role restore. This predates the Typed Host Search/Host status fixes. Previous denied Client test and browser/preview routes are not rerouted; integrated R2, genuine 3-role acceptance and 100-Host page completeness remain OPEN.

## UI-06 single-reviewer Temporary Access — design gate (PROPOSED, not implemented)

- **Owner-required goal:** one requester asks for time-bounded access to an existing, explicitly identified WHITELIST rule; **one different, Core-authorized reviewer** approves or denies, with trustworthy expiration and audit. Do not treat current single-actor `drlink_temporary_access_preview/apply` as this workflow.
- **Non-goals:** no second Web authorization authority, generic workflow engine, automatic approval, new credential issuance, shared-secret review links, second datastore, network-wide grant, or cross-plane implicit permission.
- **Candidate Core contract, pending owner/security approval:** a durable request ID bound to exact requester identity, access plane, immutable target rule identity, purpose, requested expiry, state and revision; a Core-derived reviewer authorization decision (never a caller-selected reviewer role), distinct reviewer identity, one atomic decision, actual applied Core Change Plan and an explicit denial/expiry/cancellation state. API names and persistence schema are **not yet authorized public contracts**.
- **Trust and lifecycle:** Core is sole policy authority. Enforce no self-review, fail-closed unknown roles, CSRF/session binding, replay/idempotency, compare-and-swap revision, bounded clock/TTL and exact target matching. Requester cannot apply a grant. Approval requires current Core policy-safety tests and a short-lived, actor-bound one-shot Change Plan; approval is not proof of effective network reachability.
- **State and operations:** use the existing Core SQLite authority with transactional and crash-safe request/decision/audit writes; record safe actor, target, decision, issue/decision/expiry timestamps and outcome without secrets. Define migration, backup/restore, expiration worker or query-time fail-closed semantics, observability and rollback **before** altering persistent schema or privileges.
- **Required RED→GREEN evidence before Web integration:** requester allowed/denied; authorized single reviewer vs self/unknown/unprivileged; concurrent double decision; stale revision; expired request or plan; exact existing WHITELIST-only rule and plane; retry/replay; mandatory regression failure; applied/denied audit; no grant after deny/expiry; restoring state does not resurrect grants. Run real Admin/Operator/Read Only Browser desktop/375/320px/keyboard and two actual users on the same installed HEAD before release.
- **Execution gate:** design and authorization/persistence changes need explicit owner security acceptance. Until then, the Web must present UI-06 as unavailable, **not** reuse single-actor Temporary Access to simulate reviewer approval. Keep one roadmap #184, ACTIVE packet #182 and Draft PR #206.

## Protected worktrees, denial boundaries and release policy

- **Web parent:** `pf5b-foundation-web` (#182/#183) has existing platform-denied uncommitted `tests/test-frp-client.sh`. Preserve unchanged, unstaged, unexecuted. Parent/child Linux native lint fails at `allocator rejected enrollment: enrollment could not be committed to Core`; no CI bypass or alternative test route.
- **Core 3.0:** `v300-drl3-0` (#135/#168) has existing platform-denied uncommitted `tests/test-v30-webhook-delivery.py`. Preserve unchanged, unstaged, unexecuted.
- **B5:** #198/#199 remains an explicit protected generated bootstrap packaging safety hold. No rerun/rebuild/revert/merge of denied target via any tool/host.
- **#206 child branch:** isolated source changes are fast-forward committed through `2f4e1b00`, including the previously dirty Host Search pair. This is still an OPEN/DRAFT Web source candidate stacked on parent #183; do not auto-merge or overwrite the parent/Core/B5 worktrees.
- Real policy activation, SSH/firewall, signer/public key pin, installed Web preview/restart, irreversible restore, production/release and permissions require separate explicit authority and recovery. A proposed roadmap never waives a denial.

## UXE-01..12 authentic user acceptance inventory — ALL NOT VERIFIED

| Scenario | Directly observed operator evidence required |
| --- | --- |
| UXE-01 | Admin first login, Home, every root menu and Help orientation |
| UXE-02 | Real enrollment code and Managed Host pending admission |
| UXE-03 | Approve vs quarantine, operator rights and Core revision |
| UXE-04 | Narrow SSH Remote Service, draft and policy preview |
| UXE-05 | Actual allowed traffic, peer/Agent and evidence readback |
| UXE-06 | Actual denied traffic, Core decision, explanation and audit |
| UXE-07 | Internet Access separate policy and observation |
| UXE-08 | AI Access separate identity/permission policy |
| UXE-09 | Operator activity, jobs, diagnoses and role write limits |
| UXE-10 | Read Only menu visibility and mutation denial |
| UXE-11 | Stale/invalid plan, unknown/partial/no-data and recovery |
| UXE-12 | Desktop 1440px, phone 375/320px, keyboard, Web uninstall/Core isolation |

Before real execution read the **entire** corresponding contracts, especially `UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md`, the original User/Operator/Admin Surface Reconciliation, `CLI_FEATURE_SCENARIO_RECONCILIATION.md`, and `FULL_USER_E2E_SCENARIOS.md`. Use ChatGPT as the actual product user, record exact actor/runtime/source/evidence and repeat source fix → true retest. Script/SSR/API/Playwright green is supporting only; previously denied Browser/preview routes must not be bypassed. Keep `PFCI_DRLINK_HOST_UX_SOURCE_CANDIDATE.md` and the Browser Acceptance Ledger as **evidence**, not a parallel roadmap.

**Explicit exclusions:** MeshCentral RMM remote desktop/terminal/file transfer/recording, MDM/device administration, mass device discovery, thousands-host unbounded operations, second Core datastore, global typed search without authoritative data, implicit admin permission or auto-approval.
