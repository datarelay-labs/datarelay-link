# Owner-observed native E2E execution playbook — Codex and ChatGPT Chat

> **Scope:** Data Relay Link CLI-only E2E and Full User E2E. **Operational runbook**, not an additional go/no-go gate, new scenario contract, authorization, or release waiver.
>
> **Executor authority:** current explicit owner request → current ACTIVE Work Packet → `.engineering/execution-profile.yaml` → repository policy. The default implementer is `CHATGPT_CHAT`. Codex executes a selected lane **only when explicitly assigned**.
>
> **Normative scenario contracts:** `docs/CLI_ONLY_E2E_SCENARIOS.md` (100 retained CLI IDs + 16 AI/MCP exclusions) and `docs/FULL_USER_E2E_SCENARIOS.md` (116 original IDs); `docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md` only for Full User E2E. This document does **not** change their conditions.
>
> **Owner purpose (2026-10-25):** Preserve the real execution method that got owner-operated Codex running and producing actual CLI/user receipts. Future ChatGPT Chat runs must execute the same *operational principles* directly through their connected tools, instead of creating false blockers, waiting for a synthetic lab gate, or delegating to an unnecessary runtime.

## 1. Verified observation — distinguish what actually worked from what was assumed

Read these as **dated observations**, not permanent process IDs, proven test PASS, or standing authorization.

| Observation | Evidence / precise meaning |
| --- | --- |
| Interactive owner-operated Codex | On `dev-drlink` (2026-10-24), live `tmux` session `codex`; child process used `codex -s danger-full-access -a on-request` (PID 2954908, started 03:18:40 UTC). An active tool process and the tmux pane were verified; the process was not inferred merely from an app-server daemon. |
| Current, independently owned test run | `/home/aella/drlink-validation/cli100-owner-20261024T0330Z-2a5c7741/`, candidate source `2a5c7741d040a55ba1550b8e8e293b9f03a15ab4`, one `ledger/scenario-results.tsv` containing **all 116 original rows** (100 CLI-only + 16 `EXCLUDED_AI_MCP`). |
| Native execution, not only a harness | Real public `drlink` commands, interactive REPL/TTY, genuine Server/Agent upgrade, install/uninstall, HTTP/SSH/Fixed TCP application observations, failure/rollback, repetitions, load/soak and receiver evidence were written to timestamped, run-private files. |
| Live progress (snapshot at 2026-10-24 15:47 UTC) | CLI 100: 25 PASS, 19 FAIL, 44 IN_PROGRESS, 2 PARTIAL, 6 FAIL_PRECONDITION, 3 MEASURED_NOT_QUALIFIED, 1 NOT_RUN (optional P-019); separate 16 excluded. `findings.json`: 17 OPEN. **This is NOT a finished E2E or release PASS.** |
| Prior broken launch | Initial `codex-cli-only-issue165-20261022/START_CODEX.sh` used `codex exec -C "$WT" -s workspace-write --add-dir "$RUN" --json -o ... - < ...`; its effective non-interactive `approval_policy=never` made ordinary connected Desktop Commander / GitHub operations fail with `MCP tool call requires approval, but approval policy is never`. An initial 81 rows were overclassified as tooling-blocked. |
| Prior documented correction | `OWNER_RESUME_AUTO_APPROVED.md` recorded normal `codex exec --approve-for-me` review and a successful connected read-only `start_process` action. It did **not** lift safety restrictions or retroactively qualify earlier IDs. |

**Important safety boundary:** The observed `-s danger-full-access` is a fact about the owner's session, **not a recommended default, a transferable permission, or permission to bypass a denied action**. `-a on-request` means normal approval is still considered. For any new run, use only an approved execution profile and current platform review. No sandbox flag, runtime change, alternate SSH target, GitHub Actions job, or tool substitution may be used to circumvent a *specific current* denial.

## 2. Why the earlier ChatGPT / Codex orchestration stalled

1. **Wrong non-interactive approval policy:** An unattended `codex exec` launched with effective `approval_policy=never`; a normal request for connector permission could never be considered. This is **RUNNER_CONFIGURATION_ERROR**, not proof that all test hosts are blocked. Always check the selected runtime's *actual* approval behavior with a harmless, authorized read-only tool call before relying on its E2E status.
2. **Overbroad blocker propagation:** The earlier protected `chat-cli-r91-*` update refusal was incorrectly applied to separate disposable `codex-r3-*` hosts. A refusal binds **only that effect and target**; a previously unattempted operation is not denied.
3. **No final installed-candidate requalification:** Source, CI and tests moved forward but native installed Server/Agent evidence sometimes remained at older source. A runtime not yet upgraded is `SETUP_PENDING / CURRENT_CANDIDATE_NOT_REQUALIFIED` (reason field), **not automatically `BLOCKED_ENVIRONMENT`**. Complete an authorized candidate preflight / normal update first.
4. **Wrong concept of completion:** 13 historically passed IDs were left `NOT_RUN` against the next candidate; many partial rows were generalized as blockers. An old-source or synthetic PASS is supporting history, not the new source's native PASS. No readiness dashboard/CI green substitutes for real E2E.
5. **Interim-report stop loops:** An active test process and its persistent `RUN_ID` must be resumed and its next actual incomplete substep executed; repeating orientation, CI, 3,600-second soak or an already completed installation wastes time. Report progress without making a report the end of available execution.
6. **Confusing execution runtime with authorization:** `tmux` persists a legitimate long-running process, but cannot grant permissions; a session or plugin appearing online is not an authorization decision. Never claim a platform denial from an untried tool.

See the 2026-10-24 Issue #165 owner audit / remediation comments for contemporaneous evidence, including the initial incorrect blocker classification.

## 3. Non-negotiable bootstrap for every ChatGPT Chat execution

**When the owner says "계속", "ㄱㅅ", or requests CLI E2E, `CHATGPT_CHAT` executes by default** unless the owner explicitly selected an active Codex lane. Do **not** spawn Codex as an unnecessary prerequisite.

1. Resolve `datarelay-labs/datarelay-link`; read **`AGENTS.md` then `.engineering/project.yaml`**. Read the current explicit user request and the latest Issue #165 ACTIVE Work Packet / NEXT action **once**. For a true E2E gate, read its applicable complete canonical user contract before acting; do not preload unrelated documentation.
2. Use connected **Remote Desktop Commander** for `dev-drlink` and the purpose-built **GitHub connector** for repository/Issue/PR. Discover available tools before claiming absence. Do one innocuous same-target read-only call (device list + `hostname` / `pwd` is sufficient) to establish actual current connectivity/review outcome. A previously successful identical action is not a new blocker without changed evidence.
3. Confirm *live ownership*: `tmux ls`, relevant `ps` processes, current run's `CONTINUATION.json`, `ledger/scenario-results.tsv`, last evidence timestamps, and `git status --short --branch` / `git rev-parse HEAD`. The presence of a Codex app-server daemon **does not prove an E2E worker is running**. Never terminate, reconfigure, repin, take over, modify, or duplicate an active independent worker's RUN_ID, test host, shared policy DB, worktree, or fixture.
4. Determine first unfinished **runnable** native scenario from the current run. If a separate owner-authorized ChatGPT execution is required while Codex is still active, allocate genuinely independent authorized hosts, namespaced objects, worktree and RUN_ID; do not touch the live Codex lane. **Status-only requests must remain read-only.**
5. Check immutable source artifact / manifest digest, release channel, and actual installed `drlink system version` on each relevant Server/Agent. **A merge-commit SHA and the deliberately embedded content-source SHA can differ**, as documented in `docs/VERSION_POLICY.md`; do not invent a mismatch. A Git checkout, CI success, or package help output is not installation proof.
6. **No global launch veto:** `LAB_GO`, all-host readiness, AI/MCP/OAuth readiness, an unrelated OS or CI, an old `phase-state.json`, and arbitrary new checklists are not prerequisites for an independently executable CLI-only scenario. Fulfill ordinary missing preparation on approved disposable hosts; record genuinely unavailable subcriteria individually.
7. Execute the actual public `drlink` menu/help/Tab/REPL/wizards and true client traffic as the acting user. The test driver may transport, timestamp, hash and measure observations but **cannot substitute for user interaction or mark PASS by itself**.

**Connected-tool rule:** A tool call that fails under normal review is reported with `tool + exact target + attempted effect + actual error + affected scenario`. Distinguish **tool not discovered**, **device offline**, **call not attempted**, **approval-policy misconfiguration**, **permission error**, **current platform refusal**, **missing setup**, and **product FAIL**. Never convert them wholesale to `BLOCKED_ENVIRONMENT` or claim that every other lane is blocked.

## 4. When Codex is explicitly selected: preserve the owner's successful session model

This section is a **reproduction reference**, not an instruction to launch a second worker now.

- The observed 2026-10-24 owner run used a **persistent interactive** `tmux` session, `codex` with `on-request` approval behavior, and repeated plain-language `테스트 계속 진행해` prompts inside the existing Codex session. The running process, changing scenario ledger, timestamps and actual user effects—not a launch message—established genuine progress.
- A new owner-authorized Codex session may be attached/resumed **only if it is the selected worker**. Inspect existing `tmux` session and active source/RUN_ID first. An illustrative session-management command is `tmux attach -t codex` for an existing owner-controlled session; **do not send input when merely monitoring status**.
- If selecting a new, explicitly authorized interactive Codex process, use the normal **current approved** Codex configuration and an approval mode that can consider legitimate tool calls. `codex -a on-request` is a review-mode example, not a guarantee that a particular tool action will be approved. Do **not** automatically reproduce the observed `danger-full-access` sandbox.
- If an explicitly selected unattended `codex exec` must use connected tools, do not configure effective `approval_policy=never`. The historical correction was `codex exec --approve-for-me` under ordinary review. Verify support for the current installed CLI and actual effect-level approval before running E2E; **neither this flag nor `on-request` overrides security decisions**.
- Ensure the interactive/background worker has an **existing persistent RUN_ID**, attached source candidate, device access, genuine user missions, and a private ledger. A detached process with no evidence progress does not establish an active healthy test.
- No global `dangerously-bypass-approvals-and-sandbox`, permission escalation, unapproved uninstallation or alternate-executor routing around refusals.

## 5. Actual E2E execution and one ledger of truth

1. Select one canonical contract: **CLI-only** = 100 retained original IDs + 16 `EXCLUDED_AI_MCP`; **Full User** = 116 originals, including distinct Direct User / AI User / tool-free AI Adviser evidence under the runtime-neutral dual-role protocol.
2. On a suitable owner-authorized host, create a **persistent private** directory (0700, not `/tmp`) and initialize the existing ledger with:
   `python3 tools/cli_only_e2e_inventory.py init --run-root <PRIVATE_RUN_ID> --source-head <EXACT_40_CHARACTER_SHA>`
   The initializer is an audit tool, not the acting user.
3. For every affected ID/substep, record `RUN_ID`, source and actual installed HEAD, host/role, public command, start/end UTC, real process/TTY, exit status, redacted stdout/stderr, independent receiver/traffic evidence, negative test, meaningful repeat and cleanup. Update the original ID **as its native evidence completes**; never claim its entire parent PASS on one green substep.
4. First pursue runnable short real checks, then relevant repeat/negative/concurrency/real-app and performance checks. Reuse compatible **same RUN_ID + same source/contract + same real effect** evidence rather than redoing already qualified destructive operations. CLI-only requires the specified 60s warmup, 300s steady cases, and real 3,600s P-013 soak as applicable; P-019 8h/24h endurance stays optional unless explicitly selected.
5. Preserve user-scoped sessions/processes when traffic must outlive a connection. Record real terminal exit/receiver payload; a timer running or `IN_PROGRESS` row is **not PASS**. Do not equate CI, unit tests, parser output or synthetic harness PASS to independent user E2E.
6. For normal installed Agent updates, **preserve enrollment** with documented product update / source-controlled upgrade. Do not reinstall/reset merely to cure an old version. A clean-install/uninstall/re-enroll scenario is tested separately on an expressly owned disposable host and preserves all unrelated actors, SSH/OOB management paths and historical evidence.
7. Periodically record only machine-observable current `CONTINUATION.json`, `findings.json`, original ledger and evidence pointers. Classify a scenario `BLOCKED_PLATFORM_DENIAL` **only after a current exact-operation tool refusal**, not an old generic allegation. Use the canonical documented status values; describe `SETUP_PENDING` in a reason field, **not a new status**.

## 6. Safety and blocker decision tree

| Event | Correct response |
| --- | --- |
| Connector not listed | Discover matching connector/action first; if genuinely absent, name exact missing capability, continue any independent Git/doc/read-only work. |
| `MCP tool call requires approval, but approval policy is never` | **Launcher configuration error.** For a *new, properly authorized execution*, correct approval configuration under normal review; do not label hosts blocked and do not override a separate real denial. |
| Device online and harmless read-only call succeeds | Device/tool access exists for **that operation**. Do not later claim no development-server access without a changed result. |
| Source installed on a disposable pair is old | `SETUP_PENDING` for exact-candidate acceptance; inventory/backup, documented read-only preflight, compatible normal candidate update where authorized, verify installed version/identity/real traffic; continue unaffected scenarios. |
| One protected host/effect was refused | Respect the refusal for **that exact effect and target**. Never "solve" it by a different tool, host, runtime, sandbox or credential. Independently owned disposable fixtures are not automatically the same denied target. |
| Malformed configuration, activation, upgrade, backup, rollback or traffic failure | Preserve genuine native **FAIL** evidence, identify reproducible product vs test-harness vs environment issue; do not weaken security or SLO just to mark PASS. |
| External DNS/TLS, Mac access, missing native platform or numerical SLO | Record which original ID/substep truly depends on it. Continue all unrelated real scenarios, record measurements honestly as `MEASURED_NOT_QUALIFIED` where appropriate. |
| CI is green but user E2E is incomplete | CI is **supporting evidence only**; native 100/116 exact-candidate acceptance remains open. |
| Running Codex with current evidence activity | Leave it running, preserve its resources; status query reads only. Execute an independent lane only with owner-specified nonconflicting resources. |

**Security never changes:** Production, unapproved destructive work, credentials, permission changes, irreversible publication, merge/release and any genuine platform denial remain under their applicable approvals. This playbook changes orchestration discipline, not permissions.

## 7. Freeze → fix → qualify, without repeating a month's work

- On the selected testing lane, exhaust independently runnable original-ID criteria and **freeze** all raw evidence and the 100/116 original ledger before editing the frozen candidate. Preserve each observed FAIL and OPEN finding.
- Classify every actionable finding (product bug / test harness / compatibility / external prerequisite). For a product bug, reproduce a specific RED failure, fix root cause in a separate authorized worktree, run focused GREEN and affected genuine public CLI E2E, then commit/push and check current exact-head CI once at a meaningful integration point.
- Product source change invalidates the old candidate's full qualification. Run **new-candidate affected acceptance**, then final complete user confirmation at a frozen exact HEAD. Do not restart an expensive whole suite after each small code fix.
- Final release gate is **two fully complete Full User E2E PASS runs on the same exact candidate HEAD**, plus the other published product release requirements. The observed owner CLI-only run, even if all 100 applicable IDs later PASS, does not count as Full User E2E release acceptance.
- Keep Issue #165 ACTIVE Work Packet/NEXT action consistent with actual CodeX/ChatGPT ownership, repository branch/HEAD, installed content source, unresolved original IDs, findings and links to run-private evidence (never raw secrets).

## 8. Future ChatGPT Chat starting contract — action, not a status loop

> **On any future owner-authorized DataRelay Link E2E request:** Read the repository `AGENTS.md`, `.engineering/project.yaml` and this playbook. Select the execution owner by the current user instruction (default ChatGPT Chat; explicitly selected Codex otherwise). Read the relevant complete native scenario contract. Find current live session/owners and previous original-ID ledger **once**. Connect normally to `dev-drlink` using the available connected tools; verify a harmless same-tool read-only command before diagnosing access. If a separate Codex actor is active, preserve its branch/hosts/RUN_ID. Use the existing candidate and actual `drlink` product installation, or safely prepare a qualified immutable candidate on expressly owned disposable resources. Start with the first independently runnable remaining **real public-CLI and receiver-confirmed user scenario**, not LAB_GO, architecture review, an AI Adviser in CLI-only, CI reruns, or new checklists. Record exact operations and effects in the existing 116-row ledger. Only a current specific denied action is blocked; continue other independent ones. Freeze failures → fix → targeted native retest → final exact-HEAD qualification. Do not stop just because an interim report was produced. Never bypass current safety decisions.

## 9. Source of the observations

- [DRLink Issue #165 — original E2E / owner remediation history](https://github.com/datarelay-labs/datarelay-link/issues/165), particularly 2026-10-24 comments `6369044487` (root-cause audit) and `6369181908` (CLI100 execution packet).
- Private, owner-scoped (do not publish raw logs or credentials): `/home/aella/drlink-validation/codex-cli-only-issue165-20261022/START_CODEX.sh`, `OWNER_RESUME_AUTO_APPROVED.md`, and `/home/aella/drlink-validation/cli100-owner-20261024T0330Z-2a5c7741/{CONTINUATION.json,findings.json,ledger/scenario-results.tsv}`.
- Actual live `dev-drlink` `tmux`/process observations on 2026-10-24, not an assumed historical running state.
- Repository authoritative files: `AGENTS.md`, `.engineering/project.yaml`, `.engineering/execution-profile.yaml`, `docs/CLI_ONLY_E2E_SCENARIOS.md`, `docs/FULL_USER_E2E_SCENARIOS.md`, `docs/CODEX_DUAL_ROLE_TEST_PROTOCOL.md`, `docs/VERSION_POLICY.md`, `docs/UPGRADE.md`.

**Maintainer rule:** This document is part of the **execution onboarding** for future Link E2E. Update it only from reproducible, exact-scope observations; never transform a temporary process, manual intervention or observed sandbox setting into a universal authorization or PASS.
