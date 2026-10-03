# Data Relay Link — Documentation Index

> **Purpose:** Identify the authoritative specification for each product area and prevent historical/internal documents from being mistaken for the current public contract.
> **Target:** v2.4.0 development

## Authority order

When documents disagree, use this order:

1. `PRODUCT_MASTER.md` — product charter and product-level decisions.
2. `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md` — canonical CLI and AI-assisted configuration behavior.
3. `VERSION_POLICY.md` — version, release-channel, provenance, tag, and release-line rules.
4. Area-specific canonical documents listed below.
5. Exact-HEAD implementation and retained qualification evidence.

Historical documents and internal storage names never override the public SSOT.

External copies, Project/chat attachments, exported snapshots, and same-named documents outside the active repository are reference-only and never override the repository SSOT or exact-candidate runtime. Pre-v2.4 CLI snapshots using the retired Clients/Services root model or retired direct-command families are not valid v2.4 validation inputs.

## Canonical product and CLI specifications

| Area | Canonical document |
|---|---|
| Product model / scope | `PRODUCT_MASTER.md` |
| CLI + AI configuration | `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md` |
| Direct CLI grammar | `CLI_REFERENCE.md` |
| Guided CLI / UX | `Data Relay Link CLI Information Architecture.md` |
| ConfigurationBundle | `CONFIGURATION_BUNDLE.md` |
| Internet Access datapath/security | `CONTROLLED_EGRESS.md` |
| Security / trust boundaries | `SECURITY.md` |
| Version governance | `VERSION_POLICY.md` |
| Release qualification | `RELEASE_CHECKLIST.md`, `RELEASE_VALIDATION.md` |
| Feature ↔ CLI/AI ↔ Operator Workflow reconciliation | `CLI_FEATURE_SCENARIO_RECONCILIATION.md` |
| Exhaustive direct CLI audit | `CLI_EXHAUSTIVE_AUDIT.md` |
| Exhaustive AI-assisted command audit | `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md` |
| Internal control-plane/schema history | `CONTROL_PLANE_ARCHITECTURE.md` |

## Operator lifecycle documents

| Task | Document |
|---|---|
| Install Server / Agent | `INSTALLATION.md` |
| Upgrade / release channels | `UPGRADE.md` |
| Remote Service + Remote Access operation | `REMOTE_ACCESS.md` |
| AI Identity / AI Access / MCP | `AI_ACCESS_MCP.md` |
| Troubleshooting | `TROUBLESHOOTING.md` |
| Deployment topology | `DEPLOYMENT_MODES.md` |
| Windows Agent details | `WINDOWS_CLIENT.md` |
| macOS Agent details | `MACOS_CLIENT.md` |

## Audit execution documents

| Trigger / audit | Canonical document |
|---|---|
| Full real-user E2E / `FULL_USER_E2E` | `FULL_USER_E2E_SCENARIOS.md` |
| Feature ↔ CLI/AI ↔ Operator Workflow reconciliation | `CLI_FEATURE_SCENARIO_RECONCILIATION.md` |
| Direct public CLI exhaustive audit | `CLI_EXHAUSTIVE_AUDIT.md` |
| AI-assisted command / ConfigurationBundle / MCP exhaustive audit | `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md` |
| Combined request such as `CLI 및 AI지원 명령을 전수 감사해줘` | Read and execute both audit documents against the same exact candidate |

These are executable audit contracts. An unqualified trigger starts execution immediately; it is not a request to merely summarize the documents. Direct CLI and AI-assisted lanes may run in parallel when they do not share destructive state. Findings from either lane can block candidate freeze.

## Qualification and evidence documents

These documents are useful for qualification but do not redefine product semantics:

- [`FULL_USER_E2E_SCENARIOS.md`](FULL_USER_E2E_SCENARIOS.md) — canonical real-user black-box product-quality contract. It resolves deterministically from `datarelay-labs/datarelay-link/docs/FULL_USER_E2E_SCENARIOS.md`, starts immediately on an unqualified trigger, exercises novice/manual-free user workflows with real traffic/lifecycle/failure/recovery/performance/concurrency, accumulates findings without pausing, and updates the active Work Packet once after the run is exhausted.
- `CLI_FEATURE_SCENARIO_RECONCILIATION.md` — canonical non-destructive Product feature ↔ canonical CLI + AI-assisted support ↔ operator-workflow coherence audit. It deterministically resolves the Data Relay Link canonical path, uses runtime only for read-only evidence, never mutates product state, accumulates findings without pausing, and updates the active Work Packet only after the audit is fully exhausted. State-changing lifecycle qualification remains FULL_USER_E2E scope.
- `CLI_EXHAUSTIVE_AUDIT.md` — trigger-driven black-box audit of public CLI syntax, usability, safety, workflow closure; it invokes the dedicated reconciliation contract when structural product-surface qualification is required
- `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md` — trigger-driven natural-language → AI-generated command/bundle/MCP audit with real execution and self-recovery checks
- `HUMAN_UX_ADVERSARIAL_E2E.md`

Together, a clean `CLI_FEATURE_SCENARIO_RECONCILIATION=PASS` and `FULL_USER_E2E=PASS` on the same supported product candidate constitute `PRODUCT_QUALITY_CLOSURE=PASS`: no known in-scope product defect and no unresolved actionable product/usability improvement remains under the two exhaustive quality contracts. This is not a release declaration; `RELEASE_VALIDATION.md` and `RELEASE_CHECKLIST.md` still govern the existing release procedure.

## Historical / internal compatibility documents

- `OCI_ACCEPTANCE.md` — retired v2.1.1-era operator plan kept only as a tombstone for old links; it is not executable qualification and contains no current CLI contract.

- `SCHEMA_V2_DEPLOYMENT.md` — historical JSON registry schema-v2 deployment material. It is not v2.4 control-plane authority.
- `FRP_UPGRADE.md` — Relay Engine/upstream compatibility and migration detail. FRP/internal helper names in this file are not public Data Relay Link CLI vocabulary.
- `WINDOWS_CLIENT_DESIGN.md` — platform design notes; public command behavior remains governed by the CLI/AI Master.
- `PRIVILEGE_SEPARATION_DEFERRED.md` — deferred privilege-separation record for the current v2.4 target. v2.3.1 was not manufactured.

## Current v2.4 public model

```text
Managed Host / DRLink Agent

Network Object / Network Group
Service Object / Service Group
Permission Object / Permission Group

AI Identity
Remote Service

Remote Access      — BLACKLIST / WHITELIST
Internet Access    — WHITELIST only, deny-by-default
AI Access          — WHITELIST only, deny-by-default

ConfigurationBundle
```

Public command examples should use `drlink`, not internal `frp-*` helpers.

## Engineering development standard

Software-development process, AI-agent workflow, testing strategy, change lifecycle, and release workflow are governed by the canonical Engineering System:

```text
https://github.com/datarelay-labs/engineering-system
```

Product specifications in this repository define **what Data Relay Link must do**. The Engineering System defines **how product changes are designed, implemented, tested, reviewed, released, and operated**.

Engineering System managed-adoption files such as `AGENTS.md` and `.engineering/*` are lifecycle/governance surfaces, not substitutes for the product specifications above. Their adoption or version upgrade must follow the Engineering System adoption workflow rather than being hand-copied as part of a documentation-only change.

## Documentation maintenance rule

A product behavior change is incomplete until the affected canonical document is updated.

A historical/internal document may retain implementation names only when the document clearly labels them as internal or historical and does not present them as current public CLI.

Before release qualification, run a documentation consistency review against the exact candidate HEAD and verify that README, Product Master, CLI Reference, release documents, and generated/help output describe the same behavior.


## Exhaustive audit trigger routing

The following user requests are execution shortcuts:

~~~text
CLI, 기능, 시나리오의 연계성을 테스트 진행
CLI 기능 시나리오 연계성 테스트
GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해
FULL_USER_E2E 수행해
GitHub에서 FULL_USER_E2E 문서 찾아서 수행해
CLI 전수 감사해줘
CLI 명령 전수 감사해줘
AI 지원 명령 전수 감사해줘
AI지원 전수 감사해줘
CLI 및 AI지원 명령을 전수 감사해줘
CLI와 AI 지원 명령 전수 감사
~~~

`CLI, 기능, 시나리오의 연계성을 테스트 진행`, `GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해`, and equivalent wording execute `CLI_FEATURE_SCENARIO_RECONCILIATION.md` immediately. Resolve `datarelay-labs/datarelay-link/docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` deterministically instead of broad-searching GitHub. Immediate execution means feature inventory → public CLI discovery → operator-workflow reconciliation → post-hoc hidden/parser/doc enumeration. Runtime use is read-only; state-changing commands are audited via contract/source/isolated tests. Findings are accumulated and execution continues; GitHub Issue reporting happens once after all executable checks finish.

`FULL_USER_E2E 수행해`, `GitHub에서 FULL_USER_E2E 문서 찾아서 수행해`, and equivalent wording execute `FULL_USER_E2E_SCENARIOS.md` immediately. Resolve `datarelay-labs/datarelay-link/docs/FULL_USER_E2E_SCENARIOS.md` deterministically, use the active-worktree pointer first, do not broad-search unrelated repositories, and execute the full `PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL` profile unless the user explicitly narrows scope. Findings accumulate while all independent lanes continue; the active Work Packet is updated once after the run is exhausted.

CLI-only exhaustive requests execute `CLI_EXHAUSTIVE_AUDIT.md`. AI-only requests execute `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`. FULL_USER_E2E remains responsible for live state-changing journeys.
