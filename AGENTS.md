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

### Data Relay Link active-worktree resolution

On `dev-drlink`, the process current working directory is **not** authoritative for selecting the active Data Relay Link worktree. The historical main worktree `/home/aella/datarelay-link-dev` may be on an older branch and must not cause the agent to stop, re-plan, or search GitHub before a User E2E run.

The machine-level active-worktree pointer is authoritative:

~~~text
/home/aella/datarelay-link-current
DATARELAY_LINK_CURRENT_WORKTREE=/home/aella/datarelay-link-current
~~~

For Data Relay Link work, especially any User E2E trigger:

1. if `/home/aella/datarelay-link-current` resolves and contains `AGENTS.md`, `.engineering/project.yaml`, and the requested canonical document, immediately use that worktree;
2. do not infer the target worktree from the initial shell cwd or from `/home/aella/datarelay-link-dev`;
3. do not compare multiple historical worktrees or GitHub branches merely to decide where to start;
4. do not stop to ask which worktree is current when the pointer resolves successfully;
5. only perform fallback discovery when the pointer is missing, broken, or lacks the requested canonical file.

For `FULL_USER_E2E`, resolve the canonical contract deterministically:

~~~text
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/FULL_USER_E2E_SCENARIOS.md
ACTIVE_WORKTREE=/home/aella/datarelay-link-current
CANONICAL_CONTRACT=/home/aella/datarelay-link-current/docs/FULL_USER_E2E_SCENARIOS.md
~~~

If the active-worktree path exists, use it immediately. If it is absent, resolve the same path in the same GitHub repository/branch before any broader fallback. Do not wander through unrelated repositories or similarly named files.

Requests such as `FULL_USER_E2E 수행해`, `Full User E2E`, `GitHub에서 FULL_USER_E2E 문서 찾아서 수행해`, and equivalent wording are immediate execution triggers. Once the canonical document resolves, read the entire current contract end-to-end before starting any E2E action, then execute that contract exactly. Do not invent a substitute checklist, skip to a convenient wrapper, or treat a script/harness/CI PASS as primary user evidence. Wrappers and automation are supporting execution/evidence only; ChatGPT must perform the contract's required persona-led public-surface actions itself.

For FULL_USER_E2E, that document's `FULL_USER_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL` contract takes precedence over the generic implementation/change-classification rules below. A User E2E request is not an implementation task and must not be delayed by engineering-change classification, branch archaeology, broad GitHub search, source review, or release-qualification work unless the user explicitly requests those activities. Record findings during the run and continue all independent checks; do not update the active Work Packet for each intermediate finding. Update it once after the full executable run is exhausted and final evidence/counters are frozen.

## CLI authority hard gate

Current v2.4 public direct CLI grammar is action-first:

~~~text
drlink <ACTION> <RESOURCE> [TARGET] [VALUE]
~~~

Current top-level action families are `show`, `set`, `unset`, `test`, and `system`, plus `menu`, `help`, and `exit`.

For current CLI truth, use this order only:
1. exact candidate runtime `drlink help commands`;
2. `docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`;
3. `docs/CLI_REFERENCE.md`;
4. repository `docs/Data Relay Link CLI Information Architecture.md` for current guided-menu/UX structure only.

Project/chat attachments, copied snapshots, archived docs, old screenshots, and same-named documents outside the active repository are **never CLI authority** unless they are explicitly proven to match the current repository HEAD. Pre-v2.4 snapshots that use the retired Clients/Services root model or retired client/create/revoke/release/top-level diagnostic command families must be ignored for product decisions, audits, and E2E expectations.

If an external snapshot conflicts with the current runtime or repository SSOT, fail closed against the snapshot rather than reinterpreting the product.

## Execution rules

- **Next-chat bootstrap fast path:** on a repository-level continue/resume, perform one bounded authoritative Work Packet lookup. If no open ACTIVE packet exists, do not loop on orientation, history reconstruction, or repeated packet search. Reconcile the repository roadmap/release and actual Git/PR state once; when runnable work exists, create/reactivate exactly one truthful Work Packet and make measurable progress in the same turn. If nothing is runnable, report the concrete wait/terminal condition. `NO_ACTIVE_PACKET` is a scheduling input, not a blocker.
- **Verified next-chat resume:** a successful durable handoff is not re-executed in the fresh chat. Re-read the authoritative Issue plus mutable repo/worktree/HEAD/profile facts once; if they still match, enter the persisted Next Action immediately without transcript reconstruction, unchanged packet rewrites, repeated lint/preflight, or plan-only orientation. Revalidate/rewrite only on an actual mutable-fact or owner-intent change.
- **Product execution ownership / supervisor fallback:** the bound product repository context owns normal product implementation, testing, roadmap scheduling, and routine Issue/PR lifecycle. Engineering System is the control plane for shared policy, adoption, watchdog/re-entry, and systemic recovery; it must not become a shadow product coordinator while the product context is healthy. Create a new Work Packet only for a genuinely independent durable workstream, not for each finding or micro-step. If repeated plan-only/no-progress behavior, wrong-repository/runtime selection, stale coordination that does not self-heal, uncontrolled Issue proliferation, or repeated identical blockers show a systemic failure, repair canonical policy/tooling first when applicable, repair only the minimum adopted/product coordination state needed, verify the product context is runnable again, and return execution ownership to it. Never mutate an actively progressing owner-authorized worker dirty worktree or create a competing implementation lane merely to recover coordination.
- **Execution profile authority:** `.engineering/execution-profile.yaml` selects the runtime; packets bind `EXECUTION_PROFILE` and `EXECUTION_PROFILE_REVISION`. Historical prose, memory and retired adapters do not select an implementer. A continue/resume instruction authorizes the selected runtime to implement, test, audit and perform ordinary authenticated Git/GitHub work directly; no additional magic phrase, alternate-runtime handoff or optional coordinator tool is required.
- For ordinary authenticated GitHub Issue/PR coordination, re-read current packet intent and subject branch/HEAD before writing and reconcile stale or ambiguous outcomes. Ordinary repository work does not require `worker_adapter.py` or a trusted signer. Stronger trusted boundaries apply only to effect classes identified by the execution profile or stricter project policy: production, destructive, credential/permission change, irreversible publication and release authority. Follow `standards/SECURITY.md` for those effects.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction governs, then the fresh Work Packet, then the execution profile and repository rules. Historical Issue comments and prior handoffs are evidence only and never execution authority. Bind the owner-selected target repository; cross-project references never retarget work unless the owner explicitly includes or switches projects. Read and lint the selected packet with `python3 tools/context_epoch.py packet-lint --body-file <file> --expect-target-repo <bound-owner/repo>` and verify actual branch/HEAD/worktree. For runnable-now selection use `python3 tools/work_admission.py eligible --request-json <facts.json>`; the JSON supplies the freshly read packet `body`, absolute `profile_root`, owner-bound `expected_target_repo`, observed checkout `observed_head` (full SHA), `observed_branch` and absolute `observed_worktree` matching `profile_root`, observed `issue_state` (OPEN/CLOSED), `dependencies_ready` boolean and `waiting_for` array. Derive those facts from current evidence. Under explicit owner scope, repair missing/stale/contradictory packet state from repository evidence instead of treating coordination defects as a reason to stop. Select by owner priority, dependencies, PRIORITY and branch context; multiple independent lanes do not require a new confirmation. Implement, test and audit directly in coherent batches. Make measurable progress in the same turn; a plan/status message is not execution. After a bounded packet/PR/test phase completes, immediately return to roadmap scheduling and execute the next eligible task. During machine-observable waits, preserve state and advance independent work instead of polling. Keep going until the requested roadmap/release objective is complete, no safe authorized runnable work remains, or a genuine owner decision/credential/approval or irreconcilable blocker is required. Do not end a repository-level continue merely because one bounded task completed.
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


## Product audit execution shortcuts

When the user explicitly requests an exhaustive Data Relay Link CLI or AI-assisted command audit, route directly to the canonical audit contract instead of improvising a new checklist:

- `CLI, 기능, 시나리오의 연계성을 테스트 진행`, `CLI 기능 시나리오 연계성 테스트`, `GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해`, or equivalent → deterministically resolve and execute `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` immediately.
- `CLI 전수 감사해줘`, `CLI 명령 전수 감사해줘`, or equivalent → execute `docs/CLI_EXHAUSTIVE_AUDIT.md`.
- `AI 지원 명령 전수 감사해줘`, `AI지원 전수 감사해줘`, or equivalent → execute `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
- `CLI 및 AI지원 명령을 전수 감사해줘`, `CLI와 AI 지원 명령 전수 감사`, or equivalent → execute **both** documents against the same candidate.

These are execution requests, not plan-only requests. For the CLI ↔ Feature ↔ Scenario trigger, deterministically resolve `datarelay-labs/datarelay-link` and `/home/aella/datarelay-link-current/docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md`; do not begin with broad GitHub search or unrelated repository/host discovery. Once resolved, read the entire current canonical contract end-to-end before starting the audit, preserve every execution/evidence/prohibition rule in that document, and only then execute feature inventory → public CLI discovery → operator-workflow reconciliation. An improvised checklist, wrapper, replay script, parser scan, unit/integration suite, or CI run is never a substitute for the contract's primary persona-led lanes, even when it passes. `Scenario` means workflow-coherence audit, not live mutation. Runtime use is read-only; do not create/modify/delete/reset/revoke/apply/rollback/restore/update/uninstall/restart/pause/resume/synchronize product state. Preserve black-box-first information isolation per surface, but within each valid phase start every independent Direct-user persona lane, AI-assisted persona lane, read-only probe, FCS lane, document scan, parser/catalog/metadata audit, and isolated deterministic suite at maximum safe parallelism. Direct and AI-assisted Feature/FCS coverage must both reach 100%. Parallelism must not be implemented by replacing user-role execution with a wrapper script: scripts/harnesses are supplemental evidence/orchestration only. Never idle waiting on one slow lane while independent work is runnable. Record findings in run evidence and continue all independent checks; do not stop the current run for remediation or intermediate GitHub Issue updates. After every executable check in that run is exhausted, freeze counters/evidence, then immediately remediate every actionable in-scope finding using the authorized implementer and start a brand-new complete CLI Feature/Scenario run with a new RUN_ID. Repeat audit -> remediation -> full rerun without returning control to the owner until the latest complete run has zero new/unresolved in-scope defects and zero actionable usability findings, or a genuine human-required blocker is reached. A single clean subset, targeted regression, CI result, or one audit pass does not close this loop. When the current owner intent / active Work Packet is release-quality closure, CLI convergence is followed by the separately governed FULL_USER_E2E gate; before that gate starts, read its entire current canonical contract end-to-end and then use the same execute-to-exhaustion -> report/readback/offboard -> remediate -> complete-rerun closed loop until zero findings. A standalone CLI-only audit request ends after the CLI audit converges and does not by itself authorize state-changing FULL_USER_E2E. Only a release-quality workflow (or an explicit FULL_USER_E2E request) advances into that gate. Only after both required release-quality loops converge may candidate freeze and release qualification begin. FULL_USER_E2E owns state-changing lifecycle and real-traffic qualification.

## Implementation and audit contract

The implementation runtime is selected only by the current managed execution profile and the authoritative Work Packet. Provider/runtime names in prose are descriptive only and never create mutation authority.

Before mutation, the external authenticated GitHub coordinator must verify the current Work Packet, author permission, repository, worktree, branch, exact HEAD, intent revision, change risk, and matching `EXECUTION_PROFILE` / `EXECUTION_PROFILE_REVISION`. A legacy v2 packet may run only through compatibility explicitly accepted by the current profile; a v3 packet must not be required to carry an `IMPLEMENTER` field. The worker-writable repository copy of `python3 tools/implementation_preflight.py check` is never mutation authority. When a stricter project contract requires the pinned helper, use the immutable Engineering System baseline and require its local-binding evidence without treating that helper as authority.

The runtime selected by the execution profile performs implementation, deterministic testing, and terminal audit. Terminal PASS requires current exact-HEAD evidence, required CI/review state, and disposition of actionable findings; self-report alone is never sufficient. HIGH/CRITICAL or production/security-sensitive work requires deeper machine evidence and any applicable human approval. An independent reviewer remains optional defense-in-depth/escalation, not a provider-specific default completion dependency.
