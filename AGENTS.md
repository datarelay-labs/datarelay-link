# Data Relay Link — Working Rules

Canonical standards: https://github.com/datarelay-labs/engineering-system

Read `AGENTS.md` and `.engineering/project.yaml` at task start. Only read
`.engineering/tests.yaml` for relevant implementation tests and
`.engineering/release.yaml` when working on release artifacts. Do not load
other standards, histories, work packets or old test reports without a reason.

## Start work instead of processing paperwork

- **Execution authority precedence:** explicit current owner request > ACTIVE Work Packet > execution profile > repository defaults.
- **Execution profile authority:** `.engineering/execution-profile.yaml` selects the implementer (normally CHATGPT_CHAT). The owner can explicitly select Codex to execute E2E. No other runtime is assumed.
- On `dev-drlink` resolve `/home/aella/datarelay-link-current`, not the historical default working directory. If a specific existing worktree/run was assigned, use it. Read the latest next action and actual Git/CI state **once**; continue the first unfinished task.
- If a Codex E2E is running, **continue it**. Never interrupt, duplicate, repin HEAD or modify its worktree. Put independent fixes in a separate worktree. Keep one Issue #165 Work Packet, and update it only when a meaningful state changes.
- Ordinary source edits, focused tests, git commits/push and Issue/PR updates **do not** require extra project-written approval forms, LAB_GO, phase-state files, repeated packet lint, coordinator signatures or unrelated release checks. Classify true external/environment blockers only.
- Test only the affected change first. Run expensive CI/whole suites at suitable integration or release points, not on each small finding. Do not stop executable work to produce interim reports. Preserve others' modifications.

## Public product and user tests

- Actual installed `drlink help commands` and the tested HEAD define public CLI truth, then the current CLI Master/reference documents. Do not use an old FRP or other-repository copy as a command oracle.
- `docs/FULL_USER_E2E_SCENARIOS.md` is the authoritative **116-ID** live user contract. An E2E request starts the independent runnable criteria immediately without a prerequisite FCS, global lab readiness or preliminary code audit.
- `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` is a separate read-only FCS audit. A CLI audit never authorizes product mutation.
- Codex Direct User and AI-assisted User must remain **distinct roles** with actual public command/traffic receipts and authentic first advice. Under `docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md`, one isolated session per role can perform multiple scenarios with new per-scenario evidence. Never count a test wrapper or parser as an acting human-equivalent user.
- Assigned disposable test hosts already have owner authorization within the recorded scope; do not repeatedly ask for permission. A genuine platform/tool denial, including B014, remains binding **for that exact effect**. Do not bypass it through a different executor, host or command. Continue unaffected scenarios.
- Keep product security/fail-closed functionality, real negative tests, independent Direct/AI outcomes, exact Source HEAD, true 3,600-second soak and **two complete Full User E2E PASS runs on the same HEAD** before release. Do not turn a BLOCKED/NOT_RUN result into PASS.

## Implementation and release

- Make small correct source fixes with deterministic RED→GREEN regression evidence. Do not edit a frozen E2E candidate. After a full E2E run, freeze findings, fix, and rerun on the new source as necessary.
- Real production, outside-scope destructive effects, credentials/permission changes, merge, irreversible publication and release require their applicable separate authority. Source/CI success never grants it.
- Never replace actual platform security decisions, expose secrets, discard immutable receipts, or claim qualified release without evidence.

## Direct audit triggers

`CLI 기능 시나리오 연계성` → `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md`.
`CLI 전수 감사` → `docs/CLI_EXHAUSTIVE_AUDIT.md`.
`AI 지원 명령 전수 감사` → `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
`Full User E2E` → `docs/FULL_USER_E2E_SCENARIOS.md`.
Execute the selected contract rather than creating a new checklist.
