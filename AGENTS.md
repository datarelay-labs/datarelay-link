# Repository Engineering Rules

This repository follows the canonical Engineering System:
https://github.com/datarelay-labs/engineering-system

## Context budget

Always read:
1. `AGENTS.md`
2. `.engineering/project.yaml`

Read only when relevant:
- `.engineering/tests.yaml` for implementation/debugging/testing
- `.engineering/release.yaml` for release/version/artifact work
- one task-relevant Engineering System standard plus only the product/spec/ADR/runbook material required by the change

Use the minimum sufficient context and reasoning. Expand only for a concrete blocker, failed check, or unresolved design question. Do not preload all standards, Wiki pages, archives, historical discussions, or old agent transcripts.

When resuming, reconcile current owner intent, priority, dependencies and branch context; select eligible work and verify actual repository state before acting.

## Execution rules

- For `project.user_facing: true`, require Surface Reconciliation and Full User E2E on the same exact candidate. Before either named gate, read its entire current repository-local contract and execute it as the applicable User/Operator/Admin persona on the actual public surface. Drivers and scripts may support real actions, never substitute synthetic PASS. Follow `standards/USER_ACCEPTANCE.md`; do not restart the complete gate after every individual fix. Close findings with affected reruns, then one fresh complete confirmation.
- **Next-chat bootstrap fast path:** perform one bounded lookup when resuming durable work. With no ACTIVE packet, inspect current roadmap/Git/PR facts once and enter safe owner-authorized work; create or repair one packet when continuity needs it, not as a permission prerequisite. `NO_ACTIVE_PACKET` is a scheduling input, not a blocker.
- **DataRelay Atlas context bootstrap:** When the bound repository is under `datarelay-labs/` and a connected MCP/app named `DataRelay Atlas` exposes `bootstrap_datarelay_context`, perform one bounded bootstrap after resolving the exact repository and any current Work Packet relied on, before substantive implementation on a repository-level continue/resume or first entry into a durable workstream. Pass the exact repository and the workstream only when known. Reuse a fresh same-repository/workstream result in the current chat; do not repeat per turn, commit, or status check. Atlas is derived context only and never grants execution, permission, completion, or release authority. If the connector/tool is absent, authentication fails, the result is stale/`UNKNOWN`, or the call fails, continue immediately from canonical Git/GitHub/local evidence without retry loops, runtime switching, or asking the owner to repair Atlas. Direct Atlas/MCP-only questions may call the requested scoped tool without this bootstrap.
- **Verified next-chat resume:** re-read the current Issue and mutable repo/worktree/HEAD/profile once; if unchanged, enter the persisted Next Action immediately. Do not replay handoff validation, rewrite unchanged state or reconstruct transcripts. Revalidate only changed facts.
- **Product execution ownership / supervisor fallback:** the product context owns product work. Engineering System owns shared policy, adoption and systemic recovery, including uncontrolled Issue proliferation. Repair only what restores product autonomy, then return ownership. Never mutate an actively progressing owner-authorized worker dirty worktree or create a competing product lane.
- **Execution profile authority:** `.engineering/execution-profile.yaml` selects the runtime unless the current explicit owner instruction overrides it. A continue/resume request authorizes direct implementation, testing, audit and ordinary Git/GitHub work; no additional magic phrase or alternate-runtime handoff is required. Historical prose and retired adapters do not select a runtime. Before claiming missing tools or access, discover the connected task-relevant tools and attempt a minimal authorized action when exposed. Reuse successful same-session, same-target, same-action evidence unless a fresh failure or scope change invalidates it. Report the exact attempted operation and observed error; unattempted is not denied. Existing approvals and explicit tool denials remain binding.
- For ordinary authenticated GitHub Issue/PR coordination, re-read the intended target, branch/HEAD and any packet relied on before writing; reconcile ambiguous outcomes before retrying. Stronger trusted boundaries apply only to effect classes production, destructive, credential/permission change, irreversible publication and release authority, or stricter project policy; follow `standards/SECURITY.md`.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction governs, then the fresh Work Packet, execution profile and repository rules. Historical Issue comments and prior handoffs are evidence only and never execution authority. Bind the owner-selected repository and verify actual branch/HEAD/worktree before mutation; cross-project references never retarget work without explicit owner scope. Implement, test and audit in coherent batches; make measurable progress in the same turn. Repair stale coordination state within owner scope instead of stopping. Advance independent work during machine-observable waits instead of polling; after a bounded task return to roadmap priority. While this turn can execute, continue until the requested roadmap/release objective is complete, no safe runnable work remains, genuine owner input is needed, or a real platform/tool/safety boundary stops execution. Attempt the next safe authorized action before giving a progress-only report, and reselect roadmap work after each verified batch. If work remains when this turn ends, preserve actual progress and the precise Next Action and report the incomplete state without claiming background execution. `tools/work_admission.py disposition` is an optional pure scheduling diagnostic; its `FINAL_ALLOWED` value cannot control the lifecycle of a ChatGPT response. Status-only requests are exempt.
- Classify the change and affected domains/contracts/security/operations.
- Apply `standards/DESIGN.md` for material design-bearing changes.
- Apply `standards/OPERATIONS.md` for production-impacting failures and preserve evidence before mutation.
- Inspect affected implementation/tests, make the smallest correct change, and run the cheapest affected deterministic validation first.
- Do not duplicate equivalent native/shared CI or run expensive downstream qualification after a blocking deterministic failure.
- Add durable regression coverage for bugs when practical.
- Never weaken validation or claim PASS from unexecuted, blocked, historical, or different-HEAD evidence.
- Before merge or terminal completion, resolve every actionable review finding with revalidation or an evidence-backed disposition.
- Preserve machine-observable wait state and continue independent authorized work; use a watcher when useful.
- Repair missing or contradictory coordination context within current owner scope; otherwise block only the affected action with concrete evidence.

For adoption or managed upgrades, follow `standards/ADOPTION.md`, preserve project-specific/stricter rules, and qualify the result deterministically.

Tool-specific adapters may change syntax but must not weaken these rules.

## Implementation and audit contract





The selected runtime performs implementation, deterministic testing, and terminal audit. Terminal PASS requires current exact-HEAD evidence, required CI/review state, and disposition of actionable findings; self-report alone is never sufficient. HIGH/CRITICAL or production/security-sensitive work requires deeper machine evidence and any applicable human approval. Codex or another independent reviewer is optional defense-in-depth/escalation, not a default completion dependency.

---

## Data Relay Link E2E fast path

- **Required native E2E execution playbook:** for any CLI-only/Full User E2E start, resume, or runner-debug task, read `docs/OWNER_CODEX_E2E_EXECUTION_PLAYBOOK.md` after the two always-read governance files and the selected scenario contract. Preserve the owner's working interactive Codex/real public-CLI/116-row ledger method; execute directly with connected tools when `CHATGPT_CHAT` is selected. Do not repeat the historical `approval_policy=never` noninteractive runner error, generalize a denied operation into a global blocker, or substitute CI/harness evidence for native E2E. Observed `danger-full-access` flags are historical evidence, never default permission or a safety bypass.

- **Execution rule:** The **current explicitly owner-selected implementer** owns authorized CLI-only and Full User E2E end to end; when not overridden, `.engineering/execution-profile.yaml` selects `CHATGPT_CHAT`. Historic Codex-only instructions and older Issue text never override the current owner request. Run available public CLI scenarios, record commands/exit codes/effects, then freeze evidence -> fix -> focused regression -> authorized candidate retest as appropriate. Reuse an existing live actor **only when that actor remains selected for its specific active lane**; never duplicate, repin, kill, mutate or steal its worktree/RUN_ID. Protect existing platform denials, legitimate production/credential/release boundaries and distinct full Direct/AI-role evidence. `packet-lint` and `work-admission` are diagnostics, not permission switches.

## Start work instead of processing paperwork

- On `dev-drlink` resolve `/home/aella/datarelay-link-current`, not the historical default working directory. If a specific existing worktree/run was assigned, use it. Read the latest next action and actual Git/CI state **once**; continue the first unfinished task.
- If an existing Codex E2E is running, **do not interrupt, duplicate, repin HEAD or modify its worktree**. An explicit request for ChatGPT to execute an independent audit authorizes a **separate, isolated branch/RUN_ID and nonconflicting resources**, not takeover of that actor. Keep Issue #165 continuity without overwriting other work.
- Ordinary source edits, focused tests, git commits/push and Issue/PR updates **do not** require extra project-written approval forms, LAB_GO, phase-state files, repeated packet lint, coordinator signatures or unrelated release checks. Classify true external/environment blockers only.
- Test only the affected change first. Run expensive CI/whole suites at suitable integration or release points, not on each small finding. Do not stop executable work to produce interim reports. Preserve others' modifications.

## Public product and user tests

- Actual installed `drlink help commands` and the tested HEAD define public CLI truth, then the current CLI Master/reference documents. Do not use an old FRP or other-repository copy as a command oracle.
- `docs/FULL_USER_E2E_SCENARIOS.md` is the authoritative **116-ID** live user contract. An E2E request starts the independent runnable criteria immediately without a prerequisite FCS, global lab readiness or preliminary code audit.
- `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` is a separate read-only FCS audit. A CLI audit never authorizes product mutation.
- For **FULL_USER_E2E**, Direct User and AI-assisted User remain distinct actors with authentic first advice and real command/traffic receipts; `docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md` is a backward-compatible filename for the runtime-neutral role protocol. For **CLI_ONLY_E2E** and `FCS_CLI_ONLY`, no AI Adviser or AI mirror is required. Never count a test wrapper or parser as the acting user.
- Assigned disposable test hosts already have owner authorization within the recorded scope; do not repeatedly ask for permission. An actual **current** platform/tool denial (including B014 when freshly reproduced) remains binding **for that exact effect** and must not be bypassed. An older historical refusal is not permanent: recheck current authorization and retry only normally with the same tool/target, then record any renewed denial. Continue unaffected scenarios.
- Keep product security/fail-closed functionality, real negative tests, independent Direct/AI outcomes, exact Source HEAD, true 3,600-second soak and **two complete Full User E2E PASS runs on the same HEAD** before release. Do not turn a BLOCKED/NOT_RUN result into PASS.

## Implementation and release

- Make small correct source fixes with deterministic RED→GREEN regression evidence. Do not edit a frozen E2E candidate. After a full E2E run, freeze findings, fix, and rerun on the new source as necessary.
- Real production, outside-scope destructive effects, credentials/permission changes, merge, irreversible publication and release require their applicable separate authority. Source/CI success never grants it.
- Never replace actual platform security decisions, expose secrets, discard immutable receipts, or claim qualified release without evidence.

## Direct audit triggers

- **CLI-only E2E / CLI 단독 E2E:** immediately execute the separate `docs/CLI_ONLY_E2E_SCENARIOS.md` with its original-ID result ledger. Exclude ONLY AI support and MCP; do not require full-lab GO, AI E2E, finished whole CI, or all hosts online before independent eligible public CLI actions. Genuine denied effects stay denied for that operation; continue other host/functional/performance lanes.
`CLI 기능 시나리오 연계성` → `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md`.
`CLI 전수 감사` → `docs/CLI_EXHAUSTIVE_AUDIT.md`.
`AI 지원 명령 전수 감사` → `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
`Full User E2E` → `docs/FULL_USER_E2E_SCENARIOS.md`.
Execute the selected contract rather than creating a new checklist.
