# Data Relay Link — Working Rules

Canonical standards: https://github.com/datarelay-labs/engineering-system

Read `AGENTS.md` and `.engineering/project.yaml` at task start. Only read
`.engineering/tests.yaml` for relevant implementation tests and
`.engineering/release.yaml` when working on release artifacts. Do not load
other standards, histories, work packets or old test reports without a reason.

## Managed Engineering System minimum (not an extra E2E gate)

- **Execution profile authority:** `.engineering/execution-profile.yaml` selects the runtime; packets bind `EXECUTION_PROFILE` and `EXECUTION_PROFILE_REVISION`. Historical prose, memory and retired adapters do not select an implementer. A continue/resume instruction authorizes the selected runtime to implement, test, audit and perform ordinary authenticated Git/GitHub work directly; no additional magic phrase, alternate-runtime handoff or optional coordinator tool is required.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction governs, then the fresh Work Packet, then the execution profile and repository rules. Historical Issue comments and prior handoffs are evidence only and never execution authority. Bind the owner-selected target repository; cross-project references never retarget work unless the owner explicitly includes or switches projects. Read and lint the selected packet with `python3 tools/context_epoch.py packet-lint --body-file <file> --expect-target-repo <bound-owner/repo>` and verify actual branch/HEAD/worktree. For runnable-now selection use `python3 tools/work_admission.py eligible --request-json <facts.json>`; the JSON supplies the freshly read packet `body`, absolute `profile_root`, owner-bound `expected_target_repo`, observed checkout `observed_head` (full SHA), `observed_branch` and absolute `observed_worktree` matching `profile_root`, observed `issue_state` (OPEN/CLOSED), `dependencies_ready` boolean and `waiting_for` array. Derive those facts from current evidence. Under explicit owner scope, repair missing/stale/contradictory packet state from repository evidence instead of treating coordination defects as a reason to stop. Select by owner priority, dependencies, PRIORITY and branch context; multiple independent lanes do not require a new confirmation. Implement, test and audit directly in coherent batches. Make measurable progress in the same turn; a plan/status message is not execution. After a bounded packet/PR/test phase completes, immediately return to roadmap scheduling and execute the next eligible task. During machine-observable waits, preserve state and advance independent work instead of polling. Keep going until the requested roadmap/release objective is complete, no safe authorized runnable work remains, or a genuine owner decision/credential/approval or irreconcilable blocker is required. Do not end a repository-level continue merely because one bounded task completed.
- **Product execution ownership / supervisor fallback:** the bound product repository context owns normal product implementation, testing, roadmap scheduling, and routine Issue/PR lifecycle. Engineering System is the control plane for shared policy, adoption, watchdog/re-entry, and systemic recovery; it must not become a shadow product coordinator while the product context is healthy. Create a new Work Packet only for a genuinely independent durable workstream, not for each finding or micro-step. If repeated plan-only/no-progress behavior, wrong-repository/runtime selection, stale coordination that does not self-heal, uncontrolled Issue proliferation, or repeated identical blockers show a systemic failure, repair canonical policy/tooling first when applicable, repair only the minimum adopted/product coordination state needed, verify the product context is runnable again, and return execution ownership to it. Never mutate an actively progressing owner-authorized worker dirty worktree or create a competing implementation lane merely to recover coordination.
- **Next-chat bootstrap fast path:** on a repository-level continue/resume, perform one bounded authoritative Work Packet lookup. If no open ACTIVE packet exists, do not loop on orientation, history reconstruction, or repeated packet search. Reconcile the repository roadmap/release and actual Git/PR state once; when runnable work exists, create/reactivate exactly one truthful Work Packet and make measurable progress in the same turn. If nothing is runnable, report the concrete wait/terminal condition. `NO_ACTIVE_PACKET` is a scheduling input, not a blocker.
- **Verified next-chat resume:** a successful durable handoff is not re-executed in the fresh chat. Re-read the authoritative Issue plus mutable repo/worktree/HEAD/profile facts once; if they still match, enter the persisted Next Action immediately without transcript reconstruction, unchanged packet rewrites, repeated lint/preflight, or plan-only orientation. Revalidate/rewrite only on an actual mutable-fact or owner-intent change.
- For ordinary authenticated GitHub Issue/PR coordination, re-read current packet intent and subject branch/HEAD before writing and reconcile stale or ambiguous outcomes. Ordinary repository work does not require `worker_adapter.py` or a trusted signer. Stronger trusted boundaries apply only to effect classes identified by the execution profile or stricter project policy: production, destructive, credential/permission change, irreversible publication and release authority. Follow `standards/SECURITY.md` for those effects.

- Use `standards/DESIGN.md` only when a change genuinely bears a material design decision; it is not a routine test-start gate.
- Use `standards/OPERATIONS.md` only for production-impacting failures; owner-scoped disposable test exercises do not require a fresh incident form.

## Data Relay Link E2E fast path

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

- **CLI-only E2E / CLI 단독 E2E:** immediately execute the separate §docs/CLI_ONLY_E2E_SCENARIOS.md§ with its original-ID result ledger. Exclude ONLY AI support and MCP; do not require full-lab GO, AI E2E, finished whole CI, or all hosts online before independent eligible public CLI actions. Genuine denied effects stay denied for that operation; continue other host/functional/performance lanes.
`CLI 기능 시나리오 연계성` → `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md`.
`CLI 전수 감사` → `docs/CLI_EXHAUSTIVE_AUDIT.md`.
`AI 지원 명령 전수 감사` → `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
`Full User E2E` → `docs/FULL_USER_E2E_SCENARIOS.md`.
Execute the selected contract rather than creating a new checklist.
