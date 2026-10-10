# DataRelay Link 3.0 — Unified R1–R7 Execution Roadmap

> **ONE CURRENT EXECUTION ROADMAP:** [GitHub Issue #184 — DataRelay Link 3.0 R1–R7](https://github.com/datarelay-labs/datarelay-link/issues/184).
> This file is a **repository-local index, not an additional task queue**. The old UXB-00..06, UXB-06F, L-CI-0..4 and B1–B5 per-feature execution lists are **superseded** as roadmaps by #184. Their historical code, tests, source investigations, review evidence and mandatory acceptance contracts are retained in Git history and the named canonical documents; **do not delete/reimplement verified completed functionality**.
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

## Protected worktrees, denial boundaries and release policy

- **Web parent:** `pf5b-foundation-web` (#182/#183) has existing platform-denied uncommitted `tests/test-frp-client.sh`. Preserve unchanged, unstaged, unexecuted. Parent/child Linux native lint fails at `allocator rejected enrollment: enrollment could not be committed to Core`; no CI bypass or alternative test route.
- **Core 3.0:** `v300-drl3-0` (#135/#168) has existing platform-denied uncommitted `tests/test-v30-webhook-delivery.py`. Preserve unchanged, unstaged, unexecuted.
- **B5:** #198/#199 remains an explicit protected generated bootstrap packaging safety hold. No rerun/rebuild/revert/merge of denied target via any tool/host.
- **#206 child branch:** `pfci-saved-admission` is an isolated source candidate stacked on Web parent #183; do not auto-merge, rebase or overwrite the parent/Core worktrees.
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
