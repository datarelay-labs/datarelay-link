# DataRelay Link 3.0 — Consolidated Web UX and release delivery roadmap (B1–B5)

> **Replaced:** the former 830-line historical UXB-00..06 / UXB-06F chronological roadmap. Git history and existing acceptance contracts retain earlier investigation/evidence, but **do not schedule implementation from prior dated snapshots**.
>
> **Canonical live schedule:** [GitHub Roadmap #184](https://github.com/datarelay-labs/datarelay-link/issues/184). This file is the repo-readable version of that schedule; if this isolated #206 Web branch is behind active Core, reconcile source-HEAD evidence before any integrated claim.
>
> **Owner product constraints:** `PRODUCT_MASTER.md`, `WEB_MANAGEMENT.md`, `MANAGEMENT_SURFACE_CONTRACT.md`, `DATA_RELAY_ROADMAP.md`; common style: `WEB_SAAS_UX_SYSTEM.md` and Control/Product Foundation; signed Agent/CLI and release contracts remain authoritative. **One Server + SQLite, optional Web, complete CLI, Remote / Internet / AI planes separate.**

## Baseline and protected state — 2026-10-10

| Ownership | Actual branch / source | Safe status |
| --- | --- | --- |
| Work Packet #182 / parent PR #183 | `feat/v3-pf5b-foundation-administration` @ `870d310d`; parent worktree `pf5b-foundation-web` | OPEN, parent unmerged; **9 dirty additions in `tests/test-frp-client.sh` safety-denied**, preserved and not executed/staged |
| PF-CI Draft PR #206 | `feat/drl3-ux-saved-admission-pfci` @ initial `e808bf54`; isolated `pfci-saved-admission` | Parent #183 stacked baseline, initially clean, source-only implementation |
| Core Work Packet #135 / PR #168 | `fix/v300-roadmap-qualification-convergence` @ last verified `96246f91`; separate `v300-drl3-0` | **49 dirty additions in `tests/test-v30-webhook-delivery.py` safety-denied**, preserved |
| Foundation candidate #191 / PR #193, scope #179 / PR #180 | separate open branches | Review/input only; do not recreate, auto-merge or transplant into #206 |

**Already implemented, no duplicate coding:**
1. Workflow-first Home / Connections / Access / Activity & Health / Administration, 4-step setup, resource context and diagnosis, progressive Administration (#183).
2. Session/CSRF state, UI→Core read/preview/write contracts, bounded paginated read models, revision/history/export/job validation (#183).
3. **Host Saved Views with optional per-user admission enum**, admission-only and legacy text compatible (#206).
4. **Positive-list grouped Host detail** with UNKNOWN/SQLite 0/1 connectivity, activity/diagnosis actions (#206).
5. P0/P1 Core Host admission, bounded Agent update jobs, audit, Automation API, signed Webhooks, Access Hygiene source suites (#135); signed/live rollout and two-user E2E not yet qualified.

**Inherited CI failure classification:** parent #183 lint run `37956615105` and child #206 lint run `38022147889` both fail the native Full local non-Docker suite with exactly `allocator rejected enrollment: enrollment could not be committed to Core`, after dual-role restore checks. Child #206 changes only Web source, assets, tests and documentation, so this **is not introduced by typed/personal Host UX**. Prior explicit platform denial of the original Client test, browser/Chromium/Playwright and preview login/restart remains binding. No fixture edit, bypass or alternate-host retry; Linux gate stays FAIL until genuinely qualified.

## Execution blocks

### B1 — Native CI diagnosis and typed, evidence-qualified Host search (active)

**Owner:** existing #206 isolated worktree; do not change #183/#135 worktrees.

- Record exact inherited Linux CI errors on both parent and child, compare paths and test phase; inspect Client/Core config **read-only**. When a narrow source repair would require previously forbidden Client regression actions, keep it blocked, not silently green.
- **Current Core fact table:** `lib/drlink_management_service.py` provides `managed-host` `id/name/hostname/status/trust_status/admission_state/connected/agent_platform/agent_version`. The server's inventory `query` searches only the **name expression**, with bounded cursor/limit; the Web has separately loaded paginated Core records.
- Implement **only** a local, explicit, allowlisted typed filter on authorized records observed in the current Web session: `name:`, `host:`, `hostname:`, `id:`, `status:`, `trust:`, `admission:`, `os:`, `platform:`, `version:`, `connected:` (where concrete Core field observed). Respect existing Core role/session/CSRF and 1–100-host target.
- Unsupported `tag:`, `group:`, `ip:` or other unknown fields are **NOT AVAILABLE**, not a false 0/healthy or a broad global search. UNKNOWN per-Host values and partial pagination are visible; malformed typed input leaves observed rows unchanged rather than an invented empty result. No new Core APIs/metadata discovery, permission changes or Saved View backend.
- RED→GREEN pure helper tests, all Web Journey / UX source tests, build and static scans; commit existing branch and maintain independent PR/CI evidence. **Never call synthetic/SSR a user E2E.**

**Exit:** Source-ready scoped typed search and per-user Saved View compatibility; no false fleet-wide claim; CI failure classified inherited and still unresolved if denied path required.

### B2 — Web/Core/Foundational integration and review (P0 / pending)

Reconcile current #206 atop the existing #183 Web UX stack, then #191/#193 Foundation candidate and actual #135 Core API state without overwriting other worktrees or copying P0/P1 code. Verify per-user saved preferences, 3 roles, CSP/CSRF, Host approval/quarantine, Core-backed activity/diagnosis, partial pages, missing/invalid evidence, 100-host performance, error states and policy separation. Only propose a stack migration/merge after native CI and security review; this document alone is not merge approval.

**B2 scoped progress (2026-10-10; source only, NOT integration complete):**
- On the clean #206 worktree, `08791676` fixed a genuine Web/Core parity bug: the Host table and drawer previously treated arbitrary truthy `connected` or an unrelated lifecycle/status string as confirmed connectivity, while the Host detail projection correctly recognized only Core Boolean/SQLite `0/1`. Both now reuse one `Connected / Disconnected / UNKNOWN` fact with no new API, role, permission, data source or Agent effect. RED→GREEN shared-fact regression, Host detail 6/6, Web Journey 90/90, UX source 56/56, P0 11/11, Foundation Admin 6/6, Core Query 24/24, offline bundle 6/6, Web build, Secret Scan and Public Metadata PASS. These are **not browser or user E2E**.
- Read-only PR stack comparison: #206 remains a child of #183; separate #193 (Foundation candidate `53f7ccdd`) shares parent `870d310d` but **both edit** `web/src/main.tsx`, `web/package.json`, compiled assets and UX source tests. #168 Core `96246f91` and Web #206 share older source `153e3dd4`, with additional source/generated-bundle conflicts. Do **not** auto-merge or overwrite independently owned branches. A coherent candidate needs explicit conflict-by-conflict source reconciliation and fresh regression on a new exact HEAD.
- Parent #183 and child #206 exact native Linux CI both independently end at `allocator rejected enrollment: enrollment could not be committed to Core` after dual-role restore. This **predates the #206 Host UI work**, not a proven Typed Host Search bug. The previously safety-denied Client test and Web preview/browser routes remain blocked without rerouting. B2 is **PARTIAL**; real Admin/Operator/Read Only, 100-Host pagination and full Foundation/Core integration remain open.


### B3 — Hands-on Admin / Operator / Read Only acceptance (P0 / environment blocked)

**Canonical pre-read, in full:** `UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md`, current User/Operator/Admin Surface Reconciliation, `FULL_USER_E2E_SCENARIOS.md`; historical UXE-01..12 acceptance preserved below. On one authorized, coherent Web/Core+Agent candidate, directly use Admin/Operator/Read Only at desktop 1440 / 375 / 320 and keyboard. Five independent novice-user observations; actual Host approval/quarantine, text/admission/typed searches, partial/UNKNOWN, real permit/deny network, recent activity, Access diagnosis, session failures and invalid/stale plans. No wrapper, static HTTP probe or fake UI success can substitute. If existing preview/Chrome/login tool safety is denied, request owner-authorized execution, not another path.

### B4 — Signed Agent, CLI/AI and machine release prerequisites (P0, independent #135)

On exact candidate installed Server+Agent, require separately authorized signer/pin and disposable Host; real Canary/Health/wave halt/rollback and fail-closed behavior, Automation Apply atomicity, Direct+AI CLI Feature/Scenario **100% persona-led** ledger, audit/recovery/security/100-host saturation, Windows/macOS/Linux/Engineering CI and deterministic SHA256/SBOM/provenance. Do not bypass denied Client/Automation test writing. Synthetic scale ≠ real Agent.

### B5 — Frozen same-HEAD double Full User E2E + release (last, owner approval)

Browser PASS → actual User E2E PASS1+PASS2, two distinct users at identical HEAD → freeze → native CI / source identity / signed provenance / public smoke / owner acceptance. No automatic merge of #183/#206/#168 or production, tag, signer, release without explicit authorizations.

## Actual-user UXE-01..12 acceptance inventory (NOT PASS)

| Scenario | Operator evidence to collect |
| --- | --- |
| UXE-01 | Admin first login, Home and all root menu explanations |
| UXE-02 | Agent enrollment code and managed Host admission/pending |
| UXE-03 | Approve vs quarantine with legitimate rights and Core revision |
| UXE-04 | Publish narrow SSH Remote Service; draft and policy preview |
| UXE-05 | True allowed traffic, actual counterparty observation |
| UXE-06 | True denied traffic, exact Core decision/why/audit evidence |
| UXE-07 | Internet Access uses separate policy semantics and evidence |
| UXE-08 | AI Access uses separate identity/permission semantics |
| UXE-09 | Operator activity, jobs, diagnostics and read/write role boundaries |
| UXE-10 | Read Only menu, access to observables, blocked mutation |
| UXE-11 | Wrong/expired/stale plan, offline/unknown/partial pages and recovery |
| UXE-12 | 1440/375/320, keyboard, Web absent/uninstalled Core isolation |

Each row requires authenticated direct user evidence and a full contract pre-read, not an implied result. Historical detailed source studies, including the 19-product official-doc matrix and UXB-06F prior iteration logs, are recoverable from Git history before this rewrite. [PF-CI Host source candidate](PFCI_DRLINK_HOST_UX_SOURCE_CANDIDATE.md) and [browser acceptance ledger](UXB_06F_B2_BROWSER_ACCEPTANCE_LEDGER.md) retain their separate non-merged acceptance scopes.

**Explicit exclusions:** MeshCentral RMM terminal, desktop, file transfer/recording, MDM and device-rights, bulk discovery, thousand-host orchestration, new Core data stores, hidden client permissions, false `tag:/group:/ip:` facet results, false release PASS.
