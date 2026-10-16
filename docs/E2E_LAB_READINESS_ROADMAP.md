# Data Relay Link v2.4 — E2E lab diagnostics (not a launch gate)

> **Status:** Supporting diagnostic reference for owner-assigned test hosts.
> **Authority:** `docs/FULL_USER_E2E_SCENARIOS.md` governs all 116 user scenarios; `docs/E2E_EXECUTION_PROCEDURE.md` specifies live execution and `docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md` defines independent Codex roles.
> **Scope:** Issue #165, independently authorized disposable test hosts, source HEAD/evidence and release HOLD. This file is NOT a prerequisite checklist, phase authorization, or competing Work Packet.

## Execute live tests first

Continue the **currently owner-selected** live run from its real session; protect any other actor's active Codex worktree/RUN_ID. Independently selected CLI-only/FCS runs use their own contract and nonconflicting resources. Do not launch another competing run, force a read-only sandbox, restart completed actors, edit its source HEAD, or repeatedly wait for a new owner authorization already given. `LAB_GO`, legacy `phase-state.json` and global `NOT_READY` are diagnostic statuses, never permission switches. Readiness is diagnostic; no pre-run FCS or repeated seven-host approval sequence is required.

F001 and F007 remain open until genuine exact-HEAD, signed Server/Agent evidence and real unaffected SSH/HTTP/TCP during three Fixed TCP cycles show they are fixed. F004, F005, F006 and D001 also require genuine retest; old source tests and historical findings alone never become E2E PASS. A source defect is fixed **after** freezing the affected E2E run, with focused RED→GREEN regression, and then requalified on a new candidate. Continue all independent safe user tests.

## Owner-assigned routing and disposable-host authority

- `MCP_DNS_SERVER` handles **MCP + DNS/public-hostname tests only**, including public TLS/OAuth, hostname DNS, bootstrap hostname and associated API checks.
- `FUNCTION_PERFORMANCE_SERVER` handles **everything else**: functional Server, CLI, Remote Access, Internet Access, Agent, failure/recovery, performance and Soak. Mixed scenarios route each specific criterion to its matching host without doubling the 116-ID inventory.
- Two-Server separation is **not a new VM guest/snapshot/restore/host-provisioning prerequisite**. Native Windows/Rocky and credentials remain limited to the exact owner-assigned estate.

**Owner decision — every assigned test host may be destroyed:** Within the owner-approved disposable roster, product loss, service interruption and reboot were approved. Before testing each host, inspect its prior DRLink state, clean only eligible test-only state and **verify it is** clean; then deploy the immutable test candidate and execute actual scenarios. Do not demand a fresh owner confirmation merely because a designated test VM may fail. Keep management SSH, unrelated machines and historical evidence intact.

**Safety boundary:** A **current** platform/tool refusal for an exact operation, especially B014 Server uninstall or a native/certificate effect, stays binding; historical refusals are rechecked under the current permissions on the same tool/target: **never retry such an effect under an alternate executor** or route. Mark only dependent scenarios BLOCKED/NOT_RUN and continue independently authorized tests. No production, credentials or permissions changes, publication, merger or release are implied.

## Diagnostics are optional supporting evidence

`tools/e2e_lab_readiness.py` may inventory observed hosts, Source HEAD, reachable public CLI, native platform, public TLS and applicable OAuth. It emits a private `PREFLIGHT_STATUS.json` and `CLEANROOM_LEDGER.tsv`, which can show GO/NOT_READY/BLOCKED and reasons, but never authorizes/vetoes test execution as a global gate. Do not confuse script/readiness PASS with actual independent user actions.

The Codex auditor retains each original actor's JSONL, private role prompts, exact first AI advice, public CLI/traffic evidence, installed Source HEAD, process receipts and canonical `scenario-results.tsv`. Authentic independent Direct User, AI Operator and **tool-free AI Adviser** must cover the same goal and equivalent initial state. An automated script is not a first-time user. Missing actor parity, application traffic, source identity, numeric SLO or native host evidence is not PASS.

Mandatory stable workload evidence includes `WARMUP=60s`, `STEADY_STATE_EACH_CASE=300s` and `SOAK=3600s`; separately classify intended faults, collateral outages, integrity and actual receiver-confirmed throughput. Do not invent SLOs or turn a partially completed soak into a PASS.

## Final release quality remains strict

All **116 canonical IDs** (13 U, 15 O, 20 A, 20 S, 15 C, 24 P, 9 X), independent Direct/AI mirrors, real user traffic, failure/recovery, native applicability, 3600s soak, current Source HEAD/provenance, required CI/qualifications and **two complete same-HEAD Full Real E2E PASS runs** are mandatory before release. `PASS1=PASS2=PASS` is not yet achieved. Until real evidence proves it, `RELEASE=HOLD`. No merge/tag/release/prod deployment without separate owner acceptance.
