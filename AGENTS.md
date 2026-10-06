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

- **Product execution ownership / supervisor fallback:** the bound product repository context owns normal product implementation, testing, roadmap scheduling, and routine Issue/PR lifecycle. Engineering System is the control plane for shared policy, adoption, watchdog/re-entry, and systemic recovery; it must not become a shadow product coordinator while the product context is healthy. Create a new Work Packet only for a genuinely independent durable workstream, not for each finding or micro-step. If repeated plan-only/no-progress behavior, wrong-repository/runtime selection, stale coordination that does not self-heal, uncontrolled Issue proliferation, or repeated identical blockers show a systemic failure, repair canonical policy/tooling first when applicable, repair only the minimum adopted/product coordination state needed, verify the product context is runnable again, and return execution ownership to it. Never mutate an actively progressing owner-authorized worker dirty worktree or create a competing implementation lane merely to recover coordination.
- **Next-chat bootstrap fast path:** on a repository-level continue/resume, perform one bounded authoritative Work Packet lookup. If no open ACTIVE packet exists, do not loop on orientation, history reconstruction, or repeated packet search. Reconcile the repository roadmap/release and actual Git/PR state once; when runnable work exists, create/reactivate exactly one truthful Work Packet and make measurable progress in the same turn. If nothing is runnable, report the concrete wait/terminal condition. `NO_ACTIVE_PACKET` is a scheduling input, not a blocker.
- **Verified next-chat resume:** a successful durable handoff is not re-executed in the fresh chat. Re-read the authoritative Issue plus mutable repo/worktree/HEAD/profile facts once; if they still match, enter the persisted Next Action immediately without transcript reconstruction, unchanged packet rewrites, repeated lint/preflight, or plan-only orientation. Revalidate/rewrite only on an actual mutable-fact or owner-intent change.
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

## Implementation and audit contract





The selected runtime performs implementation, deterministic testing, and terminal audit. Terminal PASS requires current exact-HEAD evidence, required CI/review state, and disposition of actionable findings; self-report alone is never sufficient. HIGH/CRITICAL or production/security-sensitive work requires deeper machine evidence and any applicable human approval. Codex or another independent reviewer is optional defense-in-depth/escalation, not a default completion dependency.
