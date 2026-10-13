# Data Relay Link v2.4 — CLI-only Full Functional E2E

**Authority:** Current owner request, 2026-10-13. Repository datarelay-labs/datarelay-link, PR #178.
**Canonical parent:** `docs/FULL_USER_E2E_SCENARIOS.md`, all **116 original scenario IDs** and original criteria are preserved unchanged.
**Machine inventory:** `tools/cli_only_e2e_inventory.py` dynamically derives the original headings, requirements, CLI scope and private result ledger.
**Boundary:** This is **CLI-only E2E**, NEVER a Full User E2E PASS, AI-supported operation, ChatGPT Plugin acceptance or MCP qualification.

## 1. Scope — exclude only AI support and MCP

Execute **every applicable non-AI/MCP subcriterion** from the canonical Full User E2E: functional setup, installation, upgrade, uninstall/deletion, non-AI security and policies, wrong-context cases, negative testing, recovery, normal operations, interactive menu/wizard/Tab, user journeys, real traffic, concurrency, performance, stress and sustained stability. Preserve original expected results, sequence variations, repetitions and source identity rules.

The *entirely* excluded 16 **AI/MCP-only** original IDs are: U-007, U-011, O-013, O-014, A-006, C-006, P-011, X-001, X-002, X-003, X-004, X-005, X-007, X-008, X-009, X-010. Record `EXCLUDED_AI_MCP`, **not** PASS, NOT_APPLICABLE or a fabricated environmental blocker. These are still mandatory in their original Full User E2E, not in this separate owner's CLI-only scope.

**Mixed original IDs remain in scope:** U-009, U-013, A-004, A-007, A-009, A-011, A-012, A-016, S-017, S-024, C-015, P-023, P-024. Drop **only** AI advisers/mirrors, AI Identities/AI Access, MCP-only TLS/OAuth/tool calls, Plugin artifacts and AI traffic. Keep ordinary CLI hostname/DNS/TLS/Zero-Touch, non-AI Network/Service Objects and references, non-AI backup/restore, all direct-user traceability and all non-AI concurrency/load/collision variants. `REMOVED_SUBSTEPS` documents exceptions; an unrelated failure cannot be excused by a mixed ID. If other scenarios embed AI/MCP tests, omit only those narrowly while retaining every independent CLI criterion.

Original groups retained: **U** published SSH/TTY/SCP/HTTP/HTTPS/Custom TCP/Fixed TCP, LAN relay, Internet Access via real configured proxy, user continuity, hostname/Zero-Touch; **O** discovery, help/Tab/menu/wizard, enrollment, Agent lifecycle, update, configuration bundle, diagnostics, reboot and uninstall; **A** non-AI policy/object/reference/audit/backup/revision/bundle, fresh Server install/removal, state-preserving upgrade/recovery, actual CLI traceability; **S** security allows/denies, fail-closed policy, atomicity, invalid inputs, network/race/target outages, recovery and real runtime effects; **C** all available-host parallel work and real traffic, storage races and restart storms; **P** real throughput/CPS/concurrency/p50/p95/p99/soak/stress, recovery and stability; **X** excluded Plugin/MCP cross-repository acceptance only. A missing host blocks only its dependent criteria; it does not globally stop others, though all-host C-001 must truthfully reflect missing hosts.

## 2. Immediate start, not a global readiness gate

**There is no global LAB_GO**, no universal `phase-state.json`, all-seven-host-GO, AI-test-completion, MCP/OAuth acceptance, unrelated FCS audit, or interference-free **full CI** wait required to execute a separately authorized CLI scenario. Read actual branch/HEAD/dirty state and current Codex/tmux/SSH/processes **once**. Continue an existing running authorized Direct Codex actor; do not duplicate that session, actor, host mutation or RUN_ID. Test on independent safe hosts while CI or other actors execute. A blocked host does **not** block supported tests elsewhere. Keep current tool/platform refusals binding for the **exact denied operation**; never change sandbox, security policy, identity or route to bypass it. Specifically preserve B014 forbidden Functional Server uninstall and any previously refused SFTP/certificate/native effect. No new generic owner confirmation is needed for already authorized disposable test hosts.

If the repository checkout is dirty or an installed binary is at a different HEAD, do **not** rebuild/fabricate candidate qualification; independently authorized public CLI scenarios on an already pinned installed version can continue with truthful version evidence. A version mismatch never qualifies the requested candidate as passed. Codex implements and tests product fixes after evidence freeze, then installs the authorized candidate and retests; no source edit inside an active frozen user test.

## 3. Per-host pretest cleanup, not blanket reset

Authorized estate: FUNCTION_PERFORMANCE_SERVER=`frp-e2e-server` for **all non-AI/MCP tests**; Ubuntu `frp-e2e-client`, AWS `frp-e2e-aws`, Rocky `frp-e2e-rocky8` / `frp-e2e-rocky9-rescue` and Windows `frp-e2e-windows` for supported Agent, protocol, OS, load and recovery criteria. `frp-release-server` is the owner-fixed MCP/DNS Server and is **not** an alternate target for a denied functional operation; only non-MCP DNS-only actions explicitly owner assigned there can be performed.

**Pretest per-host:** prospectively inventory only `RUN_ID`-tagged services, traffic processes, resources, created policies, test identities, generated files and ports which THIS CLI-only run owns. Attempt cleanup of those prior owned resources **using public supported product paths**, record command, exit code and actual result. A new run has none: record `NO_OWNED_RESOURCES`, do not invent a cleanup. Never delete customer/user data, other workers' state, management SSH/tunnels, legacy backup archives or frozen evidence. For inaccessible hosts or a refused cleanup, mark dependent scenario `BLOCKED_ENVIRONMENT` / `BLOCKED_TOOLING` / `BLOCKED_PLATFORM_DENIAL` with exact evidence and reason; continue independent hosts and nonconflicting tasks. Do not perform host-wide uninstall or reset merely to satisfy a cleanliness label. Actual prior denied effects may not be retried through another command/actor/host.

## 4. Use actual public CLI, lifecycle and traffic; preserve full result schema

User actors run public `drlink help commands`, `drlink` REPL, menu, ?, Tab, wizards, status/show/test, and supported installer/upgrade/uninstaller paths, plus genuine application `SSH`, `SCP`, HTTP, `HTTPS`, Custom/Fixed TCP, curl/wget/git/apt and real protected-host proxy traffic. Scripts may collect logs and measure **but never substitute for direct user actions**. For lifecycle: capture prior state, rollback/backup, supported confirmation, CLI stdout/stderr/exit code, observed state, real application transfer and cleanup, with ownership and installed Source HEAD. Repeat under negative/invalid/conflict/offline/recovery variants, real policy allows/denies, unsafe-reference rejection and correct atomic outcomes. On defect: reproduce -> minimal correct fix -> RED/GREEN -> authorized install/update -> rerun. Never carry PASS between installed versions.

Create durable private `RUN_ID` outside /tmp (0700 directory, 0600 files). Initialize:

`python3 tools/cli_only_e2e_inventory.py init --run-root <PRIVATE_RUN_ID> --source-head <FULL_GIT_SHA>`

The ledger contains 116 parent IDs (100 CLI-scoped, 16 exclusions), parent requirement, `TARGET_HOSTS`, repository `SOURCE_HEAD`, actual installed `INSTALLED_HEAD`, literal `ACTUAL_COMMAND`, `RESULT`, private `EVIDENCE`, `CLEANUP`, `SKIP_REASON`, UTC timestamps, `PERFORMANCE_PROFILE`, `REMOVED_SUBSTEPS` and `NOTES`. Per-substep/repeat/process receipts must also record host, exact command, exit code or `NOT_EXPOSED`, observed effect, receiver SHA256, cleanup and attempted elapsed time. Checkpoint each item promptly, do not update GitHub after every action.

Allowed `RESULT`: NOT_RUN, IN_PROGRESS, PASS, FAIL, PARTIAL, FAIL_PRECONDITION, BLOCKED_ENVIRONMENT, BLOCKED_TOOLING, BLOCKED_PLATFORM_DENIAL, BLOCKED_MANAGEMENT_PATH, MEASURED_NOT_QUALIFIED, EXCLUDED_AI_MCP. An environment blocker is NEVER PASS/NOT_APPLICABLE. `PASS` needs successful real actions, original in-scope criteria, source/install HEAD equality, truthful evidence and verified cleanup. A legitimate CLI observation against installed `40d7c0d9` cannot qualify repository `e4aabe18` as passed.

Report independently `EXECUTABLE_SCOPE_COMPLETE` (all runnable criteria exhausted, others accurately blocked/failed, no silent gaps) versus `ALL_APPLICABLE_CLI_E2E_PASS` (every required CLI criterion PASS, zero unresolved defects/blockers and complete qualified performance). Neither proves Full User E2E PASS, which still needs real AI/MCP and independent complete same-HEAD passes. No PR merge, tag, production deployment or release without separate approval.

## 5. Real performance, stress and long-duration

Never weaken the original profile:

    WARMUP=60s
    STEADY_STATE_EACH_CASE=300s
    SOAK=3600s
    EXTENDED_SOAK=8h
    ENDURANCE_SOAK=24h

Base 3600s `P-013` functional soak is mandatory once functional traffic prerequisites work. P-019 8h/24h profiles remain separately **planned/optional unless selected**; they require their true full duration if selected. Start an independent qualified soak promptly and overlap other safe work. If data-plane prerequisites already genuinely fail or an action is denied, stop only dependent repeats, preserve FAIL_PRECONDITION/blocker and continue other CLI tests.

Test actual 1 KiB/64 KiB/1 MiB files/continuous stream; upstream/downstream/full-duplex receiver-confirmed goodput and SHA256, attempted/successful CPS, latency p50/p95/p99, CPU/RSS/FD, 4/16/64+ connections, churn, mixed-service/all-host fairness, recovery timing, saturation/controlled impairment, and control-plane operations while function-under-load (P-024). Apply existing hardware/topology/performance profile numeric SLOs **without relaxing thresholds**. If no numeric SLO is approved, record `MEASURED_NOT_QUALIFIED` for numeric qualification; functional corruption, policy violation or unexplained restart remains FAIL.

**Persistent process requirement:** start approved real application/load on the assigned server using independent `tmux` or equivalent, not the life of a ChatGPT/SSH connection. Persist run-owned PID, tmux session, command, start UTC/monotonic start, 60/300/3600 sample timestamps, periodic receiver and resource evidence, terminal exit code, redacted logs and end UTC. On reconnection, find that exact process and continue observation; do not duplicate it. A planned timer, active PID or transport disconnect alone NEVER establishes soak PASS. Run 8h/24h only when selected and retain their separate final receipts. No tool/platform refusal is permission to move the denied operation to another route.

## 6. Truthful closeout

Store the original 116-ID scope inventory and live per-host cleanup records. A final CLI-only result includes executable-scope completion and all-applicable-CLI PASS as **different** gates, list every specific FAILED/BLOCKED/PARTIAL/NOT_RUN ID, true evidence location and version, source parity and real soak receipts. The old 104 environmental/2 tooling/10 N/A numbers are a **previous Full User E2E run** and never become this CLI-only run's result. Existing Full User E2E criteria remain unchanged and incomplete. Preserve source/evidence provenance; no unapproved merge, production deployment or release.
