# DRLink v2.4 — P0 E2E Lab & Test-Method Readiness Roadmap

> **Priority:** P0 / FIRST actionable quality-convergence workstream; ahead of any next full qualification run or subsequent release steps.
> **Owner:** CHATGPT_CHAT implements infrastructure preflight/automation and product fixes. Codex performs **TEST-ONLY** when dispatched by the owner, never source edits or release.
> **Status:** PLANNED / prerequisites not yet passed. Preserve prior binding OpenAI/connector safety denials and unrelated DRLink v3 / DP OS Upgrade environments.
> **Coordination:** datarelay-labs/datarelay-link Issue #165 (runnable) and parent release Issue #41 (PAUSED), PR #178 (OPEN).
> **Baseline tested provenance:** 5479d6e544fe01ef0246cfbf8a6f235ccc774163; installed E2E product source was content parent 385a68e4672019b70f93bf216eed6292ee7ed719.
> **Primary evidence:** frozen Codex E2E run `/home/aella/drlink-validation/codex-full-user-e2e-20261010-owner-dispatch/e2e-reviewed-run/codex-reviewed-20261010T085035Z/`. Previous run ledgers under `e2e-reports/full-user-e2e-*` and `/home/aella/drlink-validation/continued-20261010/` remain independent.

## Why this is P0

The official `docs/FULL_USER_E2E_SCENARIOS.md` is the required 4,283-line full user contract at baseline. Its scope, actual CLI/persona-led testing, negative cases and two complete same-HEAD PASS gates must **NOT** be weakened. Historical executions also failed: Codex 2026-10-07 had FAIL12/PARTIAL67; Codex 2026-10-08 had repeated runs with up to 106 environment-blocked cases; 2026-10-10 ChatGPT c06 ledger PARTIAL101 and no AI mirrors; latest 2026-10-10 Codex 116-ID ledger **PASS0, FAIL3, PARTIAL71, BLOCKED_TOOLING21, BLOCKED_ENVIRONMENT7, FAIL_PRECONDITION3, N/A11**. Latest frozen report: **105/105 applicable AI-assisted mirrors unexecuted**, prospective persona/process proof missing, old Server state persisted because cleanroom uninstall was review-denied, 3,601-second load has significant errors and no qualified numeric SLO, MCP public trusted TLS and owner OAuth absent. A failed gate is not proof 116 features are broken, and a historical/other-HEAD test success is not current PASS.

## P0 work packages (implement in priority order; keep independent actionable work moving)

### LAB-P0-01 — Dedicated, reversible, authorized test estate

- Prepare an **owner-approved disposable** v2.4 Server, two independent supported Agent Hosts plus authorized native platform routes, separate target and load roles where available; keep management/OOB SSH distinct from product ports.
- Capture precise host ownership, authorized account, fixed host IDs and OS, ingress rules, port ranges, snapshot/backup IDs, test disposal authority, exclusion boundaries, and reboot ownership in `LAB_OWNERSHIP_AND_APPROVAL.md`.
- Record per-host old product state, database/reservations, service units/listeners, legacy process ownership, temporary target files and immutable installed head in `CLEANROOM_LEDGER.tsv`. The last Codex run left the Server installed, two disconnected records and seven reservations. **Do not retry Server uninstall B014 through any alternative tool, privilege or route.** Gain proper legitimate review/approval or use a separately authorized clean disposable resource.
- Preserve `/root/drlink-e2e-precleanup-20261010/` on the external E2E Server, all historical evidence, SSH management/tunnels, dev-drlink services, DP OS Upgrade, DRLink v3 linux114, and physically excluded Mac.

**Acceptance:** `ALL_REACHABLE_ASSIGNED_HOSTS_CLEAN=PASS`, unexplained state/port/legacy PID zero, snapshot/restore identifiers documented, no denied effect retried, each assigned role has a disposable ownership record.

### LAB-P0-02 — Preflight validation and candidate integrity

- Implement a deterministic **read-only** `PREFLIGHT_STATUS.json` and human checklist against `AGENTS.md`, `.engineering/project.yaml`, the entire canonical Full User E2E contract, official public `drlink` version/status, OS facts, usable SSH+TTY, TCP routes, time sync, mount/disk/RAM/swap capacity and correct native platform assignment.
- Verify bundle SHA256, clean build provenance HEAD and content parent mapping; on *every* participating installed Server/Agent confirm exact supported immutable `PRODUCT_SOURCE_HEAD`. Record pre-candidate observations separately from candidate evidence.
- Check protected test TLS/CA, public MCP trust/real ChatGPT owner OAuth acceptance, source-address policy selectors and genuine review/approval for intended live tests before running affected lanes. Mark exact `NOT_READY` / `BLOCKED_TOOLING` / `BLOCKED_ENVIRONMENT`; no mock acceptances.
- Distinguish readiness preflight (may use scripts) from independent real human CLI action evidence (scripts forbidden as primary proof).

**Acceptance:** deterministic `GO | NOT_READY | BLOCKED` with per-gate reasons and evidence, no run-wide fictitious PASS if mandatory prerequisites are blocked. Independent safely executable diagnostic tests may continue under separately labeled supporting runs.

**Implemented support tooling (post-reboot):** `tools/e2e_lab_readiness.py` with isolated regression `tests/test-e2e-lab-readiness.py` performs approved-alias, read-only host/Source HEAD and ownership-precondition inventory. Provide a private lab-ownership JSON manifest through `--manifest` and durable `--output-dir`; it writes `PREFLIGHT_STATUS.json` and `CLEANROOM_LEDGER.tsv` outside `/tmp`, with exit code 3 when `NOT_READY`. The script cannot approve its own host permissions or override denied effects. Native Windows is not qualified from management reachability alone. This is supporting preflight, **not** a persona test or product readiness PASS.

### LAB-P0-03 — Prospective first-time user/AI role isolation

- The auditor executor **first reads the entire 4,283-line contract end-to-end** in bounded chunks and manages the canonical 116 scenario IDs, 18 use cases and public-command coverage oracle.
- Before each user action, create `RUN_ID`, role, natural-language mission, permitted hosts and starting state and record public CLI discoverability evidence. The user/Operator/Admin/Responder/Maintainer persona does **not** receive scenario answers, source, private DB, parser, docs or test harness commands as an oracle.
- For each applicable intent provide **an independent fresh AI advisor context** containing only natural-language user goal plus the same public `drlink` menu/help/Tab/wizard/error/status output. Log first AI answer, any public/unmodified safe command, same-conversation recovery and *actual effect* on namespaced equivalent initial state. No hidden answer-key leakage or retrofitting.
- Register each executor-owned process/session *at creation* (host, pid/session, role, UTC, purpose, management/product) and archive complete transcripts as they happen; snapshots assembled after execution cannot qualify as prospective persona evidence.
- Tests can be simulated or scripted **only** for supporting static/unit/measurement evidence, not to impersonate a real actor.

**Acceptance:** `AI_MIRRORS_WITHOUT_DIRECT_BASELINE=0`, `DIRECT_USE_CASES_WITHOUT_AI_MIRROR=0`, documented knowledge isolation, prospective evidence intact, all in-scope complete once user states truly verified.

### LAB-P0-04 — Separate stable soak from controlled faults and saturation

- Define a validated baseline with OS/host topology and traffic correctness. For steady-mode user workload use contract's **60s warmup, 300s measurable steady windows, 3600s soak**. Capture CPU, RSS, FD, connection/CPS/goodput, p50/p95/p99, per-path errors and recovery with times/IDs.
- **Independently label** intentional restart, policy, enable/disable, outage, collision, overload/64-worker saturation and fault periods. Keep mandatory real concurrency, fault/recovery and cross-service continuity tests: segregating results is not exempting them.
- Differentiate connection resets *expected for the targeted service* from interruptions of unrelated services (F007), failed checksum read vs actual payload corruption, accepted sender bytes vs receiver-verified data, transient post-restart recovery vs a true unattended service-health PASS.
- Declare numeric SLO/profile explicitly when legitimately approved. If missing, `MEASURED_NOT_QUALIFIED` is required, never invented SLO PASS.

**Acceptance:** baseline and fault timelines correlate with commands and remote effects; soak success has no unexplained restart, unbounded leak, integrity/error or policy fault; high-load failures and unrelated path failures dispositioned separately.

### LAB-P0-05 — Native qualification, repeatability and release gate

- Test the actual assigned native Windows/Rocky hosts only when approved; Docker/mocked runner output cannot qualify native/full-user behavior. Preserve binding Windows extraction, Rocky bootstrap and transfer denials.
- Build fresh `RUN_ID` ledger, full command/variant coverage, every affected scenario and independent AI mirror. Derive final JSON/Markdown/Issue counters **from the ledger**, validate SHA256 and read back Issue #165 once after execution.
- Qualified release requires **two complete passes on the same frozen qualified product HEAD** after code fixes; reboot, extra CI, preliminary smoke, historical c06 traffic and partial 3600s data cannot replace these.
- CLI Feature/Scenario Reconciliation is separate and **runtime non-destructive**: Codex must reread all current `docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` (1,423 lines baseline), audit FCS-001..FCS-015, stop, then CHATGPT_CHAT directly fixes defects.

**Acceptance:** `PASS1=PASS2=PASS` on exact immutable candidate, no mandatory unexecuted scenario/command/AI lane, no safety/tooling/management blockers, owner accepts release separately. Until then `RELEASE=HOLD`.

## Dependencies, resourcing and restart sequencing

1. Current owner priority **starts this LAB-P0 readiness workstream first**; preserve any already-confirmed ChatGPT E2E bugfix edits as safe, separately labeled WIP. Do not release code from a dirty/uncorroborated build. No overlapping Codex source mutation.
2. The owner is enlarging **dev-drlink** disk and RAM and plans a restart. Before host shutdown: save/commit scoped authorized v2.4 work, preserve all cleanroom/baseline/legacy worktree metadata and evidence, check system service autostart, capture boot/mount/memory/swap and device baselines. Do not stop unrelated active jobs or reboot on behalf of the owner.
3. After restart: verify OS disk/LVM/filesystem size (host currently Ubuntu ext4-on-LVM), memory, time sync, SSH/remote MCP reachability, datarelay services, tunnels and Git origin/branch/cleanliness; do **not** re-run old denied shared Server uninstall. Refresh read-only lab inventory and `PREFLIGHT_STATUS.json`.
4. Then CHATGPT_CHAT resumes E2E bugfix and approved cleanroom work; next Codex CLI FCS test only after the updated candidate is consistently deployed and CLI-run prerequisites are met. Product qualification reruns after changes on the new HEAD.

## Explicit stop conditions

- Unauthorized destructive cleanup, production/credential/security control mutation, prior platform-safety denied effect, release/tag/merge/publish: **STOP affected action only** and record exact approval/tool error.
- Never discard, force-reset, auto-merge, delete stale worktree branches, truncate 4,283-line contract or replace first-time persona by harness.
- A reboot interruption is a host operation event, **not** evidence of E2E PASS or completion of the five-phase quality roadmap.
