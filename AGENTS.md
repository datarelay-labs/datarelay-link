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

For `FULL_USER_E2E`, the canonical contract must resolve at:

~~~text
/home/aella/datarelay-link-current/docs/FULL_USER_E2E_SCENARIOS.md
~~~

Once that file exists, execute it immediately according to its trigger rules.

For FULL_USER_E2E, that document's `FULL_USER_E2E_SCOPE=FUNCTIONAL_ONLY` contract takes precedence over the generic implementation/change-classification rules below. A User E2E request is not an implementation task and must not be delayed by engineering-change classification, branch archaeology, GitHub document comparison, source review, or release-qualification work unless the user explicitly requests those activities.

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

- `CLI 전수 감사해줘`, `CLI 명령 전수 감사해줘`, or equivalent → execute `docs/CLI_EXHAUSTIVE_AUDIT.md`.
- `AI 지원 명령 전수 감사해줘`, `AI지원 전수 감사해줘`, or equivalent → execute `docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`.
- `CLI 및 AI지원 명령을 전수 감사해줘`, `CLI와 AI 지원 명령 전수 감사`, or equivalent → execute **both** documents against the same candidate.

These are execution requests, not plan-only requests. Follow each document's candidate pinning, black-box constraints, evidence retention, failure-continuation, cleanup, and GitHub reporting rules. Do not repair product code during the active audit; hand bounded fixes to the implementation workflow only after independent scenarios are exhausted.
