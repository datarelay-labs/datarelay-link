# Direct + AI User Test Protocol (runtime-neutral; historical filename retained)

**Status:** Supplemental to the canonical 15 FCS and 116 Full User E2E scenarios. This document does not create an extra test-start gate.

## Reuse distinct user-role sessions, not a new agent per scenario

An auditor knows the canonical coverage inventory; the **acting users must not** receive the source, internal test oracle, another actor's results or private credentials. For **FULL_USER_E2E/FCS_FULL** only, start genuinely **different fresh** owner-selected-runtime actor contexts for:

- **DIRECT_USER:** discovers and operates the real public `drlink` CLI without AI advice.
- **AI_OPERATOR:** pursues the **same business goal** and equivalent independent starting state; asks an AI Adviser for help and follows safe public guidance.
- **AI_ADVISER:** separate **tool-free** owner-selected-runtime support persona, fed only the AI User's actual goal and public CLI output, never source or Direct User results.

**One fresh context per role per RUN_ID is enough for a full AI-included run.** Each actor may continue its **own existing working native session** for later scenario turns; a different role must never inherit that context. Record a new prompt, raw JSONL segment, `thread.started` / `turn.completed` and observed public effects **for every scenario**. Do not reuse the same event file for two scenarios. For a scenario specifically evaluating a first-time user, create a new clean context for that scenario. Same-role continuation saves hundreds of duplicate startups without merging Direct and AI knowledge.

The AI Adviser may continue its own separate context across scenarios, receiving only AI-user goals and observed public output. The **first Adviser answer for each scenario** means the first completed `agent_message` within that scenario's new JSONL event segment. Save those original bytes exactly, including SHA256. No adviser tools, files, SSH, MCP or browser use. On advice errors, follow up with only the new public error. An unsupported/incorrect answer remains a genuine AI failure.

## Execute real tests and retain only meaningful evidence

- Freeze the `RUN_ID`, exact tested/installed Source HEAD, scenario ID, role, neutral goal and equivalent baseline **when that scenario begins**. Use distinct namespaced state or legitimate restoration; Direct changes cannot satisfy AI outcomes.
- Users use normal public CLI/menu/help/Tab/wizards and, in Full User E2E, real authorized application traffic. A shell script may collect measurements/receipts, but **is not the acting user**.
- Full E2E may perform authorized state-changing lifecycle work on the already approved disposable hosts. CLI FCS remains NON-DESTRUCTIVE. `LAB_GO`, historical `phase-state.json`, full seven-host readiness, completion of FCS, repeated approval matrices and old preflight reports **never veto independent runnable scenarios**.
- Continue each existing working native session under normal platform review; start a new independent role context only when required by the selected test contract. Do not prescribe a new batch launcher or force all user tests into read-only mode. The Adviser remains tool-free. Platform/tool refusals apply unchanged to the **specific** denied effect. Do not reroute a denial.
- Keep private scenario-scoped raw event receipts, authentic first AI response bytes, goal/baseline/source hashes, real commands/outcomes and `ledger/scenario-results.tsv` (exact 116 IDs) or `ledger/fcs-results.tsv` (15 IDs). Avoid new checklists, duplicated Work Packets, extra launcher frameworks and approval records.
- `tools/validate_codex_dual_role_pairs.py` optionally checks **structure**: correct distinct role identities, separate per-scenario events, first AI reply bytes, goal/baseline/source equality, coverage and honest results. Its PASS **never constitutes actual user testing or product PASS**; the auditor checks authentic public effects and actor separation.

## Immediate evidence checkpoint, no extra approval workflow

When an actor completes one real scenario, **write its scenario-results.tsv disposition promptly** with observed Direct/AI outcomes and the authentic event paths. Never leave the complete 116-row ledger at NOT_RUN while real independent scenarios finish; the absence of required adviser or user evidence makes that scenario incomplete, not PASS. Maintain just the existing private ledgers and transcripts—no extra files/forms per scenario—and **never use a checkpoint as final release PASS**. The auditor freezes and verifies the same evidence only once after all safe runnable work is exhausted.

## What never changes

This full Direct+AI role-separation protocol **does not apply** to `CLI_ONLY_E2E` (100 retained non-AI/MCP parent IDs) or `FCS_CLI_ONLY` (13 Direct-only FCS). Do not create a tool-free AI Adviser, collect first-AI-answer receipts, or block those scopes waiting for an AI/MCP actor. It remains mandatory for the **full** v2.4.0 Full User E2E/FCS release gates; MCP is included in the product.

Do not leak credentials, use oracle/source answers in acting-user contexts, fake a result, impersonate an actor with replay scripts or bypass platform denials. A genuinely **current** denied operation (including B014 if renewed on the same tool/target) blocks only that criterion; other real tests continue. Actual real traffic, negatives/recovery, platform qualification, 3,600-second soak and **two complete same-HEAD Full User E2E PASS** release gates remain required. Release stays HOLD until independently supported; no merge, tag, release or production deployment without separate owner authorization.
