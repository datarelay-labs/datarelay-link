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

When resuming a workstream, resolve this repository first, load only its single matching active AI Work Packet, verify actual branch/HEAD/state, and continue from the coherent Next Action.

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

Requests such as `FULL_USER_E2E 수행해`, `Full User E2E`, `GitHub에서 FULL_USER_E2E 문서 찾아서 수행해`, and equivalent wording are immediate execution triggers. Once the canonical document resolves, execute it without a plan-only pause.

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

- The current managed execution profile authorizes `IMPLEMENTER=CHATGPT_CHAT`; provider/runtime selection is profile state, not a core invariant. Cursor remains retired/prohibited under this profile. Treat the Work Packet as durable coordination state, verify the target repository/branch/HEAD before mutation, and use ordinary authenticated Git/GitHub operations for normal repository work. Every ACTIVE Work Packet create or material update must immediately pass `python3 tools/context_epoch.py packet-lint --body-file <exact-body>` before implementation continues. Re-read and lint the exact authoritative packet again immediately before any implementation adapter, session, or process is started or resumed; any BLOCK result, including `IMPLEMENTER_INVALID`, forbids execution. A repository-level continue/resume request that resolves to one runnable `IMPLEMENTER=CHATGPT_CHAT` packet authorizes ChatGPT Chat to continue implementation directly; do not require an additional magic phrase such as `directly edit`, do not delegate implementation to the retired Cursor runtime, and do not require high-risk trusted-signing machinery for ordinary source/test/config/document changes or ordinary authenticated GitHub Issue/PR coordination. Reserve trusted external-write/approval machinery for explicitly high-risk boundaries such as production, destructive operations, credentials/permissions, irreversible publication, or a stricter project-specific contract.
- For ordinary authenticated GitHub Issue/PR coordination, freshly re-read the authoritative Work Packet and subject branch/HEAD immediately before the write and reject stale intent, branch, or subject state. Do not require `worker_adapter.py` or the trusted signer for those normal coordination writes. Use `python3 tools/worker_adapter.py evaluate --request-json <facts.json>` only for an effect explicitly classified by this system or a stricter project policy as a high-risk external write (for example production, destructive, credential/permission-boundary, irreversible-publication, or equivalent). For those high-risk effects proceed only on `APPLIED`; `STALE_WORKER` authorizes no write and ambiguous outcomes must be reconciled before retry.
- **Execute useful work continuously.** **Execution authority precedence:** the current explicit owner instruction for this workstream governs first, then the freshly read current ACTIVE Work Packet body, then current repository rules. Historical Issue comments, prior handoffs, chat history/memory, old Work Packet versions, and retired adapter text are evidence only and never execution authority. When the current packet says `IMPLEMENTER=CHATGPT_CHAT`, do not probe, restore, wait for, or launch any alternate or retired implementation adapter. Before any implementation starts or resumes, require a fresh authoritative Work Packet read and `python3 tools/context_epoch.py packet-lint` PASS; a BLOCK result such as `IMPLEMENTER_INVALID` makes the packet non-runnable and forbids implementation/session launch. Implement in coherent small/medium batches, validate locally with the cheapest relevant tests, and keep going while a safe authorized next action exists. Use fast CI for quick integration feedback when useful; reserve full qualification/release CI for a stable candidate. If a workstream is waiting on machine-observable CI/review/deploy or another external condition, record/yield that wait and return to repository-level scheduling; switch to the highest-priority dependency-eligible independent ACTIVE Work Packet/worktree when safe instead of polling or stopping. For a repository-level continue/resume with no branch/workstream named, choose the single trusted runnable packet marked as the current implementation lane (for example QUEUE_STATE=IMPLEMENTATION/IMPLEMENTING); yielded/waiting/deferred predecessor packets must not compete with it. When a successor starts while predecessor integration/qualification is intentionally deferred, pause/yield the predecessor instead of leaving multiple equivalent ACTIVE implementation candidates. The single-matching-ACTIVE-packet rule selects one packet for the current branch/workstream; it does not serialize unrelated repository work behind a waiting packet. Once one runnable packet is selected and authorized, a progress/status message alone is not execution: make measurable progress in the same turn and continue until a real stop condition. Measurable progress may be reproduction, bounded investigation that resolves a material uncertainty, deterministic validation, repository mutation, or an authorized external state transition; do not force a code/config mutation when investigation or validation is the correct next action. Stop only for a real owner decision/credential, an irreconcilable blocker, a status-only request, or a completed bounded outcome.
- Classify the change and affected domains/contracts/security/operations.
- Apply `standards/DESIGN.md` for material design-bearing changes.
- Apply `standards/OPERATIONS.md` for production-impacting failures and preserve evidence before mutation.
- Inspect affected implementation/tests, make the smallest correct change, and run the cheapest affected deterministic validation first.
- Do not duplicate equivalent native/shared CI or run expensive downstream qualification after a blocking deterministic failure.
- Add durable regression coverage for bugs when practical.
- Never weaken validation or claim PASS from unexecuted, blocked, historical, or different-HEAD evidence.
- Before merge or terminal completion, resolve every actionable review finding with revalidation or an evidence-backed disposition.
- Do not keep a coding-agent session alive polling CI/review/external waits; persist concise state and yield to coordinator/automation.
- If mandatory engineering context is missing or contradictory, fail closed instead of guessing.

For adoption or managed upgrades, follow `standards/ADOPTION.md`, preserve project-specific/stricter rules, and qualify the result deterministically.

Tool-specific adapters may change syntax but must not weaken these rules.


## Product audit execution shortcuts

When the user explicitly requests an exhaustive Data Relay Link CLI or AI-assisted command audit, route directly to the canonical audit contract instead of improvising a new checklist:

- `CLI, 기능, 시나리오의 연계성을 테스트 진행`, `CLI 기능 시나리오 연계성 테스트`, `GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해`, or equivalent → deterministically resolve and execute `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` immediately.
- `CLI 전수 감사해줘`, `CLI 명령 전수 감사해줘`, or equivalent → execute `docs/CLI_EXHAUSTIVE_AUDIT.md`.
- `AI 지원 명령 전수 감사해줘`, `AI지원 전수 감사해줘`, or equivalent → execute `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
- `CLI 및 AI지원 명령을 전수 감사해줘`, `CLI와 AI 지원 명령 전수 감사`, or equivalent → execute **both** documents against the same candidate.

These are execution requests, not plan-only requests. For the CLI ↔ Feature ↔ Scenario trigger, deterministically resolve `datarelay-labs/datarelay-link` and `/home/aella/datarelay-link-current/docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md`; do not begin with broad GitHub search or unrelated repository/host discovery. Once resolved, immediately execute feature inventory → public CLI discovery → operator-workflow reconciliation. `Scenario` means workflow-coherence audit, not live mutation. Runtime use is read-only; do not create/modify/delete/reset/revoke/apply/rollback/restore/update/uninstall/restart/pause/resume/synchronize product state. Preserve black-box-first information isolation per surface, but within each valid phase start every independent Direct-user persona lane, AI-assisted persona lane, read-only probe, FCS lane, document scan, parser/catalog/metadata audit, and isolated deterministic suite at maximum safe parallelism. Direct and AI-assisted Feature/FCS coverage must both reach 100%. Parallelism must not be implemented by replacing user-role execution with a wrapper script: scripts/harnesses are supplemental evidence/orchestration only. Never idle waiting on one slow lane while independent work is runnable. Record findings in run evidence and continue all independent checks; do not stop for remediation or intermediate GitHub Issue updates. After every executable check is exhausted, freeze counters/evidence and update the active `[AI Work]` Issue once with the consolidated result. FULL_USER_E2E owns state-changing lifecycle and real-traffic qualification.

## ChatGPT implementation and audit contract

ChatGPT Chat is the default implementer for this repository when the authenticated active Work Packet authorizes the exact repository/worktree/branch/scope.

Before mutation, the external authenticated GitHub coordinator must verify the current Work Packet, author permission, repository, worktree, branch, exact HEAD, intent revision, change risk, and `IMPLEMENTER=CHATGPT_CHAT`. The worker-writable repository copy of `python3 tools/implementation_preflight.py check` is never mutation authority. Use the helper source from the immutable pinned Engineering System baseline through the isolated trusted launcher, capture the no-follow worktree identity, and require `IMPLEMENTATION_LOCAL_BINDING=PASS` with `MUTATION_AUTHORITY=NO`.

ChatGPT Chat performs implementation, deterministic testing, and terminal audit. Terminal PASS requires current exact-HEAD evidence, required CI/review state, and disposition of actionable findings; self-report alone is never sufficient. HIGH/CRITICAL or production/security-sensitive work requires deeper machine evidence and any applicable human approval. Codex or another independent reviewer is optional defense-in-depth/escalation, not a default completion dependency.
