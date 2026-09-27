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
