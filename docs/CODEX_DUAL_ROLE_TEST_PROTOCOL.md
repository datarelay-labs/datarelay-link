# DRLink — Codex dual-role Direct CLI + AI-assisted scenario protocol

**Owner-approved execution model for datarelay-labs/datarelay-link Issue #165.**
**State:** Protocol prepared, NOT executed; cleanroom preflight remains NOT_READY. This is an execution supplement, never a replacement for the full canonical contracts.

## 1. Authority and scope

- **Codex executes both roles itself** for every applicable feature and workflow: (a) Direct CLI User/Operator and (b) AI-assisted User/Operator who consults **a Codex AI-adviser persona**. One Codex executor owns all role executions and final audit; it does not delegate user actions to ChatGPT, a shell replay script, a different model, a third-party AI, or an external assistant.
- Codex auditor must read the ENTIRE current `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` (15 FCS-001..015, including runtime-discovered feature/command union) and the ENTIRE current `docs/FULL_USER_E2E_SCENARIOS.md` (116 scenarios) before starting the respective audit, as required by each contract. User and AI-adviser contexts must **not** receive the canonical contract or any source/test/internal oracle.
- **CLI FCS is strictly runtime NON-DESTRUCTIVE:** public `drlink` help/menu/Tab/status/show/read-only tests may be executed; mutating command grammar, confirmation, risk and recovery are inspected, never applied on assigned product state. **Full User E2E is a separate future test**, using authorized real operations/traffic only after legitimate lab GO; same Direct/AI pairing applies.
- Codex is **TEST ONLY**: no product/doc/test-source modification, commit, push, CI source fix, merge, tag, release, host replacement, or bypassing a prior tool/safety denial. ChatGPT Chat owns remediation.

## 2. One Codex test owner, three knowledge-separated Codex actor contexts

The parent **CODEX_AUDITOR** reads the canonical contract and has the 15/116 coverage oracle. It starts **fresh Codex threads**, under ONE locked RUN_ID, for each applicable FCS/feature or E2E scenario pair:

1. **CODEX_DIRECT_USER:** Fresh first-time User/Operator/Admin/Responder/Maintainer thread. Input is ONLY user role, neutral business goal, authorized test target, and allowed public product starting surface. Acts through ordinary `drlink` CLI/menu/help/wizard and (only in separate E2E) authorized application traffic, without AI advice. Record how the goal was discovered, actual commands, errors and effects.
2. **CODEX_AI_OPERATOR:** Different fresh first-time operator thread with the **same business goal, role, equivalent starting topology/policy/state**, but instructed to seek help from AI before choosing public CLI commands. Receives no DIRECT_USER commands/results/answer key.
3. **CODEX_AI_ADVISER:** Different fresh Codex AI-support thread, prompted **only with the AI operator's natural-language request and the exact public CLI output the AI operator has already seen**. It cannot inspect repository files, canonical manuals, implementation, parser, test code, auditor ledger, source-state, private credentials or another actor's conversation. Preserve its **first answer exactly**. If advice is safe and within the public product surface, the AI operator attempts it **unchanged** and verifies real public effect; for FCS mutation-bearing advice, inspect public grammar and negative/confirmation UX **without mutating runtime**. On error, supply the **new public output only** to the SAME AI_ADVISER thread for recovery.

All three personas are **Codex**; "AI-assisted" does not mean an outside AI provider or independent ChatGPT account. Fresh means a new context, not `codex exec resume` or `fork` from the auditor/Direct thread. Within an AI scenario, continue the SAME adviser thread to preserve multi-step recovery. Every actor is forbidden to read privileged context. A mere prompt claiming isolation without separately recorded actor inputs/threads is NOT sufficient evidence: unprovable or contaminated separation = PARTIAL/BLOCKED_TOOLING, never PASS.

Codex CLI 0.160.0 supports a fresh `codex exec` thread, `--cd`, `--skip-git-repo-check`, `--sandbox read-only`, `--json`, `--output-last-message`, and `codex exec resume <thread-id>`. For the read-only FCS, use new non-repository actor directories under a **persistent run root** (NOT `/tmp`), least-privilege sandbox and prompts passed via stdin (not command-line arguments). Actor evidence is persisted privately with exact session/thread ID and caller input SHA256. The AI adviser is text-only and must not access terminals or filesystem; the AI operator alone tests CLI guidance through an approved public session. A wrapper may launch Codex actor threads and collect transcripts, but must not replay the scenario or count itself as a user.

## 3. Same-feature, same-scenario paired execution

For **every applicable FCS-001..FCS-015**, every runtime-discovered feature and CLI command/variant, and each applicable Full E2E scenario:

1. Freeze `PAIR_ID`, `FEATURE_ID`, `FCS_ID` or `E2E_SCENARIO_ID`, user role, neutral natural-language **goal SHA256**, initial topology/permissions **baseline SHA256**, pinned repository/installed content HEAD and approved permissions **before** either role acts.
2. Execute the Direct user path and AI-assisted user path independently. Both must cover the **same feature, same intended result, same negative/error/recovery variants and comparable starting condition**. When mutations are legitimately authorized in future Full E2E, use distinct namespaces or restore the same approved disposable snapshot; never let Direct changes leak into AI inputs.
3. Capture public CLI help/menu/TTY discovery, command/exit/result, **first AI response**, advice-followed/blocked decision, actual effect/traffic (Full E2E), multi-turn recovery and prospective timestamps. No source/manual/known syntax may be smuggled into user/adviser messages.
4. Compare outcomes and usability, not just syntax. AI advice that is wrong, unsafe, undiscoverable, for the wrong Server/Agent role or produces different effective behavior is **AI_RESULT=FAIL/PARTIAL**, even if Direct succeeds. No AI adviser or no actor context isolation means **AI_RESULT=NOT_RUN/BLOCKED_TOOLING** and **FINAL_RESULT cannot be PASS**.
5. Respect a single audit lock and one final GitHub Issue #165 write/readback after the whole safely runnable audit finishes; do not create duplicate Work Packets or edit historical frozen Codex E2E evidence.

## 4. Required durable evidence and acceptance

Store under `/home/aella/drlink-validation/codex-dual-role/<RUN_ID>/`, private and outside `/tmp`. Each run owns independent per-actor input/output/session receipts, `AI_FIRST_ANSWERS`, process registry, canonical feature/FCS inventory and paired ledger. Never retain unredacted credentials in any actor brief or published report.

`ledger/codex-dual-role-pairs.tsv` **minimum columns**:

```text
PAIR_ID  SCENARIO_ID  FEATURE_ID  ROLE
AUDITOR_CODEX_THREAD  DIRECT_CODEX_THREAD  AI_OPERATOR_CODEX_THREAD  AI_ADVISER_CODEX_THREAD
DIRECT_GOAL_SHA256  AI_GOAL_SHA256  DIRECT_BASELINE_SHA256  AI_BASELINE_SHA256
DIRECT_SOURCE_HEAD  AI_SOURCE_HEAD
DIRECT_RESULT  AI_RESULT  FINAL_RESULT
DIRECT_EVIDENCE  AI_FIRST_ANSWER_EVIDENCE  AI_FIRST_ANSWER_SHA256  AI_OPERATOR_EVIDENCE
BLOCK_REASON
```

The auditor MUST maintain existing canonical `ledger/fcs-results.tsv` (15 unique FCS rows) and `ledger/scenario-results.tsv` (116 E2E rows, when in Full E2E), *in addition* to this pairing evidence. Every applicable feature/command/scenario has a Direct and AI-assisted row pair with genuine independent Codex thread IDs, identical paired goal/baseline hashes and corresponding first-answer evidence. No `FINAL_RESULT=PASS` is allowed with missing role, AI first answer, authentic public effect, current-HEAD integrity or safety authorization. The pair-ledger supporting validator can establish **consistency** but cannot itself prove that Codex really acted as an independent user, that the AI adviser was knowledge-isolated or that the product passed E2E. Evidence or actor-origin uncertainty is a blocker, not an opportunity to replace the lane with a script.

**Required consistency check (after both actor transcripts, before final issue report):**

`python3 tools/validate_codex_dual_role_pairs.py --mode fcs --pairs <RUN_ID>/ledger/codex-dual-role-pairs.tsv --feature-inventory <RUN_ID>/ledger/feature-ledger.tsv --evidence-root <RUN_ID> --expected-head <40-hex-installed-SOURCE_HEAD>`

The command checks complete FCS-001..015 coverage, every supported feature, matching Direct/AI goal/baseline/Source HEAD, independent auditor/Direct/AI operator/AI adviser thread IDs, nonempty public evidence, first AI response SHA, and no false final PASS. For 116 Full User E2E IDs use `--mode full-e2e --scenario-inventory <RUN_ID>/ledger/scenario-inventory.tsv` with the exact 116-ID canonical inventory. It reports structural consistency only, **never** proves that a Codex user actually operated independently or the product passed. A synthetic fixture or offline parser result is not a user test.

## 4.1 Mandatory actor briefing templates (never send the oracle)

The auditor substitutes ONLY the approved role, neutral goal, assigned public endpoint, previous **public** response and scenario-specific read-only constraints. It must store the **actual prompt bytes / SHA and new Codex thread ID** for each actor. Do not paste the canonical docs, FCS-ID expected command steps, feature oracle, generated test script, source, old Direct answer, private database, credentials, or prior agent transcript.

**DIRECT_USER Codex first prompt:**

> You are a first-time DRLink <ROLE> using an already-installed product through its public CLI. Your business goal is: <NEUTRAL_GOAL>. Your assigned approved product entry point is: <PUBLIC_ENTRY>. Discover normal commands only through the public menu/help/Tab/status/error interface. Do not inspect any source, tests, docs, parser or another actor's notes. In CLI Feature/Scenario audit, NEVER execute a mutation; for such steps record the visible grammar, warning, confirmation and recovery. Report your actual public commands, effect or read-only evidence, errors and final status.

**AI_OPERATOR Codex first prompt:**

> You are a different first-time DRLink <ROLE>. Your business goal and starting environment are the same as the Direct user's, but you do NOT know their actions or answers. Before choosing commands, ask an AI assistant in natural language for help using only your own public CLI observations. Follow its first recommended public command unchanged if it is safe and read-only; otherwise record the safety conflict and ask it to recover using only the new public error. Never consult code, manuals, test oracle or the Direct user's transcript. Report the actual CLI output and outcome separately.

**AI_ADVISER Codex first prompt:**

> You are helping a new DRLink <ROLE> accomplish <NEUTRAL_GOAL>. The **only** product information you may use is the following literal PUBLIC CLI/help/menu/status/error output observed by that user: <VERBATIM_PUBLIC_OUTPUT>. Respond as an AI support assistant with a concrete publicly discoverable next CLI step, why it fits this goal and any required role/context or safety warning. Do not use private/internal files, docs, test answers, hidden CLI grammar or external tools. In a non-destructive feature/scenario audit, explain mutation grammar/confirmation but NEVER attempt or instruct bypass of actual runtime restrictions. This is your FIRST answer; later public errors may be fed back in this **same Codex thread**.

These are **three Codex roles within one parent Codex test**, not three different model providers. Newly started actor threads are distinct from the auditor thread. Codex 0.160.0 allows new `codex exec` and continuing the existing adviser with `codex exec resume`; never resume/fork the auditor as a first-time actor. Use least-privilege authorized sandbox and stdin-provided prompts. CLI FCS requires read-only runtime. In Full User E2E, each needed state change still requires proper owner authorization.

## 5. Launch / block gates

**Do NOT launch Codex yet** merely because this protocol is now written. Before test dispatch require: owner-authorized fixes dispositioned; procedure and pairing gate verified; exclusive FCS/E2E lock and RUN_ID; verified tested product/source HEAD; clean owned lab and necessary approvals; genuine native access, MCP TLS/OAuth where applicable; confirmed separate Codex actor contexts and prospective transcript storage; no previous denied security effect retried. Latest lab preflight remains `NOT_READY` (old Server and Windows tunnel among other gates).

The planned sequence remains: ChatGPT fixes preceding E2E defects → ChatGPT completes dual-role method/procedure → legitimate lab GO → Codex runs direct + AI-assisted FCS then separately qualified Full E2E, both TEST ONLY → ChatGPT fixes new findings. Release HOLD until all original gates pass.
