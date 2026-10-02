# Data Relay Link — User E2E Test Scenarios

> **Document role:** Single canonical final User E2E execution contract — role-based real operation + exhaustive Direct CLI + exhaustive AI-assisted parity + performance/concurrency
> **Canonical repository:** `datarelay-labs/datarelay-link`
> **Canonical path:** `docs/FULL_USER_E2E_SCENARIOS.md` (single canonical entry point)
> **Active worktree:** `/home/aella/datarelay-link-current`
> **Operator runbook:** Acting personas do not consult manuals/runbooks during FULL_USER_E2E; Appendix A is historical-only and the auditor may use canonical documents only after runtime discovery to reconcile omissions.
> **Product:** Data Relay Link
> **Target:** v2.4 and later until superseded
> **Primary CLI:** drlink
> **CLI/AI authority:** docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md
> **Integrated predecessors:** docs/CLI_EXHAUSTIVE_AUDIT.md + docs/AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md (their mandatory coverage is absorbed here; they are not separate prerequisites for a User E2E run)
> **Release validation:** docs/RELEASE_VALIDATION.md
> **Release checklist:** docs/RELEASE_CHECKLIST.md
> **Status:** Normative living document


### Continuous execution and finding accumulation

A single finding, mismatch, scenario failure, or test failure MUST NOT stop the suite. Record the finding and its evidence, then continue every remaining check that is safe and independent. Exhaust all executable checks before the suite reports its aggregate result.

Stop or skip only the specific downstream check when continuing it would be unsafe, would corrupt shared state/evidence, requires an unavailable mandatory dependency or explicit owner action, or is technically impossible because its prerequisite failed. Mark that check `BLOCKED` or `NOT_RUN` with the exact reason and continue all other independent checks. Do not remediate product/source findings inline during a frozen audit pass; finish the pass first, then remediate findings as one phase and rerun the required pass.

## 1. Purpose and execution trigger

This document defines the exhaustive real-user E2E suite for Data Relay Link.

When the user asks for any of the following without explicitly narrowing scope:

- 사용자 E2E
- 사용자 E2E 테스트
- Full User E2E
- Full User E2E 테스트 시작
- User E2E
- 전체 E2E
- 전수 사용자 테스트
- FULL_USER_E2E 수행해
- GitHub에서 FULL_USER_E2E 문서 찾아서 수행해
- Github에서 FULL_USER_E2E 찾아서 테스트 진행해

the default interpretation is:

~~~text
PROFILE=FULL_USER_E2E
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/FULL_USER_E2E_SCENARIOS.md
FULL_USER_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL
RUN_ALL_MANDATORY_ROLE_SCENARIOS=YES
RUN_ALL_MANDATORY_FAILURE_RECOVERY_SCENARIOS=YES
RUN_ALL_MANDATORY_PERFORMANCE_SCENARIOS=YES
USE_REAL_PUBLIC_PRODUCT_PATHS=YES
USE_ACTUAL_PUBLIC_DRLINK_CLI=YES
RETAIN_EVIDENCE=YES
CURRENT_CONFIGURED_TEST_HOSTS_ONLY=YES
NEW_TEST_HOST_PROVISIONING_REQUIRED=NO
ACTING_PERSONA_MANUAL_FREE=YES
MANDATORY_REPEAT_AND_SEQUENCE_PERMUTATION=YES
FUNCTION_UNDER_LOAD_COLLISION=MANDATORY
~~~

A targeted E2E request may run a subset only when the user explicitly names the scope.

A release-qualification request uses this full suite plus the exact-HEAD double-pass rule in docs/RELEASE_VALIDATION.md.

### 1.1 User E2E execution ownership

FULL_USER_E2E is executed and independently evaluated by **ChatGPT**, not by Cursor.

This is a hard ownership rule:

~~~text
USER_E2E_EXECUTOR=ChatGPT
USER_E2E_FINAL_AUDITOR=ChatGPT
CURSOR_MAY_EXECUTE_FULL_USER_E2E=NO
CURSOR_MAY_DECLARE_USER_E2E_PASS=NO
~~~

FULL_USER_E2E never chooses or starts an implementation agent. Product remediation is a separate post-run Engineering workflow and must use the implementer authorized by the active Work Packet and `AGENTS.md`. The repository default is ChatGPT Chat; Cursor remains disabled unless the owner explicitly reactivates it for that Work Packet.

The required loop is:

~~~text
ChatGPT
→ pin exact candidate HEAD/build
→ execute FULL_USER_E2E to exhaustion
→ freeze evidence and final findings
→ update the active Work Packet once

If implementation change is required after the run:
  Engineering workflow
  → use the currently authorized implementer from AGENTS.md / Work Packet
  → implement the bounded fix
  → run implementation-level deterministic tests
  → report exact branch/HEAD/evidence

ChatGPT
→ independently verify the implementation result
→ rerun every affected User E2E scenario
→ rerun any invalidated broader/full pass required by this document
→ make the final E2E PASS/PARTIAL/FAIL determination
~~~

Implementation-agent output may be supporting evidence for static/source review, isolated deterministic checks, or remediation verification, but it does **not** substitute for ChatGPT's requested persona-led User E2E execution.

A Cursor session must never be treated as the executor of an unqualified request such as:

~~~text
사용자 E2E
사용자 E2E 테스트
Full User E2E
User E2E
전체 E2E
전수 사용자 테스트
~~~

If ChatGPT cannot execute a mandatory scenario because the real environment is unavailable, the result is `BLOCKED_ENVIRONMENT`; the scenario must not be delegated to Cursor merely to obtain PASS.

Historical PASS results, synthetic tests, unit tests, Docker-only results, Cursor-run results, or results from another Git HEAD do not replace a requested real User E2E run by ChatGPT.

If product code, dependencies, generated runtime artifacts, or the tested build changes during a full pass, record the new HEAD/build identity and invalidate the affected pass. For final release qualification, the double-pass counter resets as defined by the release validation policy.

## 1.2 Immediate-execution contract (hard gate)

An unqualified User E2E trigger means **execute now**. Do not spend a turn reviewing the repository, proposing a plan, asking which hosts to use, re-auditing old evidence, or waiting for Cursor.

Resolve the execution contract deterministically before any test work:

~~~text
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/FULL_USER_E2E_SCENARIOS.md
ACTIVE_WORKTREE=/home/aella/datarelay-link-current
~~~

Resolution order:

1. use `/home/aella/datarelay-link-current/docs/FULL_USER_E2E_SCENARIOS.md` when present;
2. if absent, resolve `docs/FULL_USER_E2E_SCENARIOS.md` in `datarelay-labs/datarelay-link` on the active branch/ref;
3. only if the canonical repository/path itself changed may repository history be used to locate its successor;
4. never begin with broad GitHub search, unrelated repository discovery, historical-worktree comparison, CI inspection, or release preparation.

Once the canonical document resolves, start execution immediately.

~~~text
FIRST_ACTION=DISCOVER_TEST_HOSTS_AND_EXECUTE
PLAN_ONLY_RESPONSE=FORBIDDEN
PRE_E2E_CODE_REVIEW=FORBIDDEN
PRE_E2E_CURSOR_HANDOFF=FORBIDDEN
HISTORICAL_PASS_AS_CURRENT_EVIDENCE=FORBIDDEN
PRODUCT_CODE_FIX_DURING_RUN=FORBIDDEN
PRODUCT_DOC_OR_TEST_CONTRACT_EDIT_DURING_ACTIVE_RUN=FORBIDDEN
CANDIDATE_REBUILD_DURING_RUN=FORBIDDEN
TEST_RECOVERY_DURING_RUN=ALLOW
TEST_HOST_STATE_RECOVERY_ONLY=YES
CONTINUE_AFTER_INDEPENDENT_FAILURE=YES
PARALLELIZE_INDEPENDENT_LANES=MAXIMUM_SAFE
INTERMEDIATE_GITHUB_ISSUE_UPDATE=NO
FINAL_GITHUB_ISSUE_UPDATE=YES
~~~

### 1.2.1 Human black-box execution lock

FULL_USER_E2E is a **real human-operation black-box exercise**. It is not a release audit, code audit, source review, or automated-harness run.

For an unqualified FULL_USER_E2E request:

~~~text
FULL_USER_E2E_MODE=HUMAN_BLACK_BOX
REINTERPRET_AS_RELEASE_QUALIFICATION=FORBIDDEN
USER_ROLE_EXECUTION=REQUIRED
SCRIPTED_USER_SCENARIO_EXECUTION=FORBIDDEN
WRAPPER_SCRIPT_AS_PERSONA=FORBIDDEN
AUTOMATED_HARNESS_ROLE=SUPPLEMENTAL_ONLY
SOURCE_INSPECTION_DURING_ACTIVE_DISCOVERY=FORBIDDEN
HARNESS_DEBUGGING_DURING_ACTIVE_DISCOVERY=FORBIDDEN
SERIAL_HAPPY_PATH_FIRST=FORBIDDEN
REALISTIC_OPERATOR_MISTAKES=REQUIRED
REAL_MULTI_HOST_PARALLELISM=REQUIRED
~~~

ChatGPT must behave like real Users, Operators, and Administrators:

- launch the installed public `drlink` surface and use menu, `?`, `help`, Tab, one-shot commands, REPL, and guided wizards as an operator would;
- copy identifiers/endpoints/commands from product output and use them in the next step;
- paste product-generated install/bootstrap commands as a real user would;
- make realistic mistakes and recover only from user-visible guidance;
- exercise wrong input, blank input, Back/Cancel, duplicate creation, stale copied identifiers, invalid references/ports/CIDRs/FQDNs, and concurrent operations;
- use real SSH/HTTP/HTTPS/TCP/application traffic rather than substituting internal checks;
- use disposable test credentials/tickets exactly as the product presents them when required by the real workflow; do not distort or skip the workflow because credentials are involved.

During the active discovery run, do **not** inspect implementation source, test source, SQLite/internal state, private APIs, hidden helper commands, or harness code to explain a failure. Record the user-visible result and continue. Source/harness investigation belongs to the post-E2E engineering phase.

Automated test suites and orchestration scripts may run concurrently as supporting evidence, process management, or metric collection, but never as the User E2E executor. Parallelism means concurrent persona-led user/operator/admin lanes; a shell/Python wrapper that replays scenario commands is not a persona and cannot produce User E2E PASS evidence:

~~~text
AUTOMATED_HARNESS_PASS != USER_E2E_PASS
AUTOMATED_HARNESS_FAIL != PRODUCT_FAIL
SCRIPT_OR_WRAPPER_PASS != USER_PERSONA_PASS
~~~

If automation/tooling cannot perform one user action, classify only that dependent scenario as `BLOCKED_TOOLING` and immediately continue all independent lanes. Do not spend the full run repeatedly trying to overcome one automation limitation when other user scenarios can execute.

### Tooling isolation — TTY and GitHub

Remote-execution tooling is not product behavior.

For persistent REPL, menu/wizard navigation, Tab completion, interactive confirmation, and other TTY-sensitive user flows:

1. prefer connector-native or otherwise explicitly authorized interactive terminal/PTY access;
2. do not repeatedly attempt shell-level PTY emulation when the execution tool or safety layer rejects it;
3. record only the affected lane as `BLOCKED_TOOLING_TTY` and continue all independent user, AI, traffic, lifecycle, performance, and regression lanes;
4. deterministic PTY regression tests remain supporting evidence and never substitute for the real persona TTY lane;
5. a mandatory TTY persona lane that remains blocked prevents aggregate FULL_USER_E2E PASS, but it is not a product defect by itself.

For final GitHub Work Packet reporting, use the general GitHub Issue update path (`update_issue`) against the active `[AI Work]` Issue, read the current body first, replace only the bounded final-report section, and read back the Issue to verify the current RUN_ID/HEAD/result. Do not depend on PR-conversation comment APIs for normal Issue reporting.

A GitHub write failure does not change the product-test result. Record `GITHUB_REPORT_STATUS=BLOCKED_TOOLING`, retain frozen evidence, and retry the final sync separately. The test execution may be finished while reporting sync remains incomplete.

~~~text
TTY_TOOLING_STATUS=PASS|BLOCKED_TOOLING_TTY|NOT_APPLICABLE
TTY_PERSONA_COVERAGE=PASS|PARTIAL|NOT_APPLICABLE
GITHUB_REPORT_STATUS=PASS|BLOCKED_TOOLING
GITHUB_REPORT_READBACK=PASS|FAIL|NOT_RUN
~~~

### 1.2.2 Product-test-only execution scope

FULL_USER_E2E tests product functionality, resilience, concurrency, and performance through real user/operator/admin workflows. It is deliberately broad as a **product test**, while code review, implementation diagnosis, security/compliance audit, and unrelated engineering review remain outside the active run.

FULL_USER_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL
ENGINEERING_CODE_AUDIT=OUT_OF_SCOPE
SECURITY_COMPLIANCE_AUDIT=OUT_OF_SCOPE
PRODUCT_BEHAVIOR_RECOVERY_PERFORMANCE=IN_SCOPE

Execution rules:

- test only what the user/operator/admin is trying to accomplish with the product;
- do not add unrelated audits, advisory commentary, architecture review, or extra review work;
- authentication, TLS, credentials, access policy, ALLOW/DENY, and permissions are tested only as normal product functions: discover and perform the public product action through CLI/AI-visible guidance and record whether it works;
- a product functional, recovery, concurrency, or performance failure remains a product-test finding; do not branch into code/security/compliance review during the active run;
- remain inside the designated disposable test environment and current-run resources;
- continue every independent functional/performance/recovery lane after recording a failure.

The legacy S-* identifiers below are retained only for functional failure/recovery traceability.
### 1.2.3 Mandatory parallel-start gate

After host discovery, start every independent lane the available topology permits. Do not finish one platform end-to-end before beginning the others unless shared state makes serialization technically necessary.

At minimum, attempt these lanes in parallel when applicable:

- C-001 all available supported hosts online;
- C-002 multi-host enrollment;
- Server read/discovery through public `drlink`;
- Agent read/discovery through public `drlink`;
- guided/menu/TTY usability;
- invalid-input, duplicate-name, reserved-token, and reference corner cases;
- platform-specific installation/enrollment;
- baseline real application traffic;
- AI-assisted parity;
- independent baseline performance/load generation.

"Parallel" means concurrent real execution on separate hosts/resources, not merely planning multiple scenarios or running them sequentially under one wrapper.

Execution starts by reading the development server's `~/.ssh/config` and probing the configured hosts. Do not require the operator to restate hostnames already present there.

Host assignment is dynamic. The currently configured/reachable test estate is the hard resource budget: FULL_USER_E2E must not require provisioning a new VM, cloud instance, physical host, or external load generator to become executable or PASS-eligible. Additional isolated processes/services on existing hosts may increase pressure only when they remain faithful to the product behavior being measured; logical clients must never be reported as distinct physical hosts.

1. classify reachable SSH-config hosts by OS, installed DRLink role, network reachability, available target services, and whether destructive testing is safe;
2. assign **two suitable hosts to server-side roles** when two usable server hosts exist: one primary control/server candidate and one secondary server-side target/recovery/upgrade/failover test host according to the scenario;
3. assign all remaining suitable hosts to Agent, Relay Agent, protected client, external user, load generator, target-service, and cross-platform roles;
4. use Linux, macOS, Windows, Rocky/Amazon Linux or other configured hosts wherever their platform makes a scenario applicable;
5. mark only genuinely unavailable capabilities `BLOCKED_ENVIRONMENT`; never invent PASS.

Host discovery itself is infrastructure setup, not product validation. Product configuration, lifecycle, inspection, policy, diagnostics, recovery, and PASS evidence remain public-`drlink`-CLI-only.

## 1.3 One integrated test, three execution dimensions

Every applicable functional/operational intent is exercised across these dimensions rather than treated as three unrelated audits.

### 1.3.1 Use-case and command exhaustion contract — feature-complete and command-complete

FULL_USER_E2E is organized around **real product use cases**, but it is also explicitly command-complete. Executing a command once only to satisfy a checklist does not count as feature coverage; every applicable public command and behavior-changing variant must be functionally used inside a real scenario and receive a final disposition.

Every current product capability and every applicable public CLI command/variant must be exercised inside at least one end-to-end use case with observable user value, authoritative state verification, and real behavior/traffic where applicable.

Required traceability for every use case:

~~~text
PRODUCT_CAPABILITY
-> USER/OPERATOR/ADMIN_GOAL
-> SCENARIO_ID
-> PRECONDITION/TOPOLOGY
-> PUBLIC_CLI_COMMANDS_AND_VARIANTS
-> STATE_TRANSITIONS
-> REAL_TRAFFIC_OR_REAL_EFFECT
-> NEGATIVE/RECOVERY_VARIANTS
-> DIRECT_CLI_RESULT
-> AI_ASSISTED_MIRROR_RESULT
-> EVIDENCE
~~~

Canonical use-case families for the current v2.4 product include at minimum:

~~~text
UC-01  Fresh Server deployment, identity, public hostname/bootstrap identity, diagnostics
UC-02  Managed Host onboarding: Zero-Touch, Manual Enrollment, Bulk Enrollment, multi-platform
UC-03  Direct-host Remote Access: SSH plus SCP/SFTP and endpoint discovery
UC-04  Application publishing: HTTP, HTTPS, Custom TCP, Fixed TCP
UC-05  Relay Host to LAN target without Agent
UC-06  Remote Access policy lifecycle: No Policy, BLACKLIST, WHITELIST, disable/re-enable
UC-07  Internet Access policy and real applications: curl/wget/git/apt/vendor API
UC-08  AI/MCP onboarding, authentication, TLS, authorization, ALLOW/DENY, file/exec capabilities
UC-09  Objects/Groups/Managed Host Groups, references, duplicate/ambiguous selectors
UC-10  Day-2 Remote Service lifecycle: create/show/edit/disable/enable/delete/synchronize
UC-11  Configuration-as-Code: export/test/diff/apply/idempotence/cross-context split
UC-12  Revisions/audit/history/rollback and concurrent administrator changes
UC-13  Backup/validate/restore and disaster recovery
UC-14  Product update, Relay Engine check/update, prior-version upgrade, failed-update recovery
UC-15  Agent pause/resume/restart/autostart/uninstall/reinstall/offline edits/reconnect
UC-16  MCP public TLS/certificate lifecycle and OAuth credential approval/revoke/rotate/configure
UC-17  Support/diagnostics/support-bundle and operator troubleshooting
UC-18  Multi-host concurrency, races, endpoint allocation contention, restart/reconnect storm
UC-19  Performance/load/soak while control-plane operations and policy mutation continue
UC-20  Failure/adversarial operation: invalid input, DNS/TLS/network/target/server/runtime failures
~~~

These families are an index over the detailed U-*, O-*, A-*, S-*, C-* and P-* scenarios below; they do not replace those scenarios.

Required completion gate:

~~~text
PRODUCT_CAPABILITY_COVERAGE=100%
USE_CASE_COVERAGE=100%
COMMANDS_WITHOUT_USE_CASE=0
PUBLIC_COMMAND_VARIANTS_WITHOUT_USE_CASE=0
USE_CASES_WITHOUT_REAL_EFFECT_VERIFICATION=0
USE_CASES_WITHOUT_NEGATIVE_OR_RECOVERY_VARIANT=0
~~~

If runtime discovery reveals a public capability not represented by the catalog above or detailed scenarios below, add it to the current run as a runtime-discovered use case immediately. Do not defer execution merely because the document is stale.

### 1.3.2 Mandatory repetition and sequence-permutation contract

A single successful execution never closes a high-risk state-changing workflow. FULL_USER_E2E must repeat operations with different starting state, order, concurrency, and recovery conditions so accidental one-shot success cannot hide stale-state, idempotency, race, or lifecycle defects.

Minimum repetition policy, constrained to the currently configured test hosts:

~~~text
READ_ONLY_COMMANDS=AT_LEAST_2_CONTEXTS: IDLE + UNDER_LOAD_OR_CONCURRENT_MUTATION
STATE_CHANGING_COMMANDS=AT_LEAST_3_EXECUTIONS_FROM_NAMESPACED_OR_RESET_STATE
CREATE_EDIT_DISABLE_ENABLE_DELETE_LIFECYCLE=AT_LEAST_3_CYCLES
ENROLLMENT_FLOWS=AT_LEAST_2_FRESH + 1_INVALID_RETRY_REUSE_OR_EXPIRY_VARIANT
RESTART_RECONNECT_RECOVERY=AT_LEAST_3_CYCLES_WHERE_SAFE
RACE_CONTENTION_CASES=AT_LEAST_3_ROUNDS
FAILURE_INJECTION_RECOVERY=AT_LEAST_2_INJECT_RECOVER_CYCLES
PERFORMANCE_POINT_SAMPLES=AT_LEAST_3_AFTER_WARMUP_WHERE_MEASURABLE
AI_HIGH_RISK_WORKFLOW_MIRROR=AT_LEAST_2_EQUIVALENT_STARTING_STATES_WHERE_APPLICABLE
~~~

Repetition must vary at least one meaningful dimension rather than replaying identical commands blindly: fresh/existing/stale state; alternate lifecycle order; one-shot/REPL/wizard surface; Direct/AI execution; idle/loaded system; single/concurrent writer; host/platform/role; normal/cancel/interrupted/retry path; or valid boundary/invalid boundary+1.

Every repeated state-changing scenario records `REPEAT_INDEX`, `STARTING_STATE`, `SEQUENCE_VARIANT`, `CONCURRENT_BACKGROUND_ACTIVITY`, and whether the final authoritative state matches intent.

Required gate:

~~~text
MANDATORY_REPEAT_COVERAGE=100%
STATE_CHANGING_COMMANDS_BELOW_REPEAT_MINIMUM=0
LIFECYCLE_REPEAT_GAPS=0
RACE_ROUNDS_BELOW_MINIMUM=0
RECOVERY_REPEAT_GAPS=0
~~~

### 1.3.3 Manual-free operator and deliberate-mistake contract

The acting User, Operator, Administrator, Incident Responder, and Platform Maintainer must complete the run without consulting the product manual, runbook, scenario command examples, CLI/AI Master, source code, test code, or hidden state. They may use only the installed product's public UX plus AI assistance grounded in the same user-visible information.

~~~text
ACTING_PERSONA_MANUAL_ACCESS=FORBIDDEN
ACTING_PERSONA_RUNBOOK_ACCESS=FORBIDDEN
ACTING_PERSONA_SOURCE_ACCESS=FORBIDDEN
ACTING_PERSONA_ALLOWED_DISCOVERY=DRLINK_ENTRY|MENU|QUESTION_MARK|HELP|HELP_COMMANDS|TAB|WIZARD|ERROR_OUTPUT|STATUS_OUTPUT
AI_INPUT_DEFAULT=NATURAL_LANGUAGE_GOAL_PLUS_USER_VISIBLE_CLI_OUTPUT_ONLY
AUDITOR_CANONICAL_DOC_RECONCILIATION=POST_HOC_ONLY
~~~

Deliberately inject realistic mistakes across all roles. At minimum, when the relevant surface exists, cover wrong role/context, shell-vs-REPL/menu/wizard confusion, privilege mistakes, blank/typo/case/reserved/duplicate/ambiguous/stale selectors, malformed or out-of-range addresses/ports/URLs/TTLs/files/Bundles/stdin, wrong dependency/order, referenced-object deletion, repeated apply/delete/create, stale revisions, cancel/back/interruption, expired/reused enrollment, wrong hostname/server URL, omitted optional fields, wrong SSH username assumption, revoked credentials, wrong AI permission, DNS/TLS/target/Agent/Server/network failures, and concurrent same-name/same-object/last-slot/delete-vs-traffic/edit-vs-traffic/restart-vs-mutation races.

Mistakes must stay inside the designated test estate. Recovery must come from public CLI guidance and/or AI assistance using only user-visible output; source-level knowledge does not count.

Required gate:

~~~text
DELIBERATE_MISTAKE_CLASSES_APPLICABLE=
DELIBERATE_MISTAKE_CLASSES_EXECUTED=
DELIBERATE_MISTAKE_COVERAGE=100%
RECOVERY_USING_ONLY_CLI_OR_AI=100%
UNDOCUMENTED_KNOWLEDGE_REQUIRED=0
~~~

### Dimension A — Direct CLI role operation

ChatGPT acts as **User, Operator, and Administrator** and performs realistic end-to-end work using only public `drlink` control-plane interfaces. During those workflows it must grade:

- real functional result and real application traffic;
- command discoverability from `?`, `help`, menu, Tab, wizard and error output;
- shell one-shot vs persistent `drlink>` REPL behavior;
- Server/Agent role placement and privilege guidance;
- terminology clarity and consistency;
- output/status consistency across related commands;
- command-to-command workflow continuity: output from one step must provide usable identifiers/endpoints/next actions for the next;
- confirmation, expected accept/reject behavior, reference handling, and visible state/result;
- error quality and recovery without source inspection;
- all documented **plus runtime-discovered** public command families.

Build a fresh documented/runtime command union for the tested candidate and give **every inventory entry a disposition**. Completion requires:

~~~text
COMMANDS_WITHOUT_DISPOSITION=0
PUBLIC_CLI_COMMAND_COVERAGE=100%
PUBLIC_CLI_SURFACE_COVERAGE=100%
~~~

The integrated run must retain the semantic coverage formerly identified as CLI-001..CLI-020: status/version/diagnostics; Managed Host discovery; Remote Service lifecycle; Remote Access; Internet Access; enrollment; ConfigurationBundle; backup/restore; AI Identity/Permission/AI Access; MCP; Managed Host Group; terminology; error recovery; empty states; status consistency; help/menu/Tab/wizard discovery; role/privilege boundaries; destructive confirmation; cleanup/evidence. Existing U/O/A/S scenarios below add real user traffic and lifecycle depth and are not replaced by this list.

### Dimension B — AI-assisted parity of the same work

For **every applicable Direct CLI semantic intent and every applicable end-to-end use case**, repeat the **same user goal** through AI support. Give the AI the natural-language intent first; when product-specific detail is needed, provide only the same user-visible CLI/help/menu/wizard/error/status output available to the acting operator. Do not give the AI the manual, runbook, CLI/AI Master, expected syntax, scenario oracle, source code, or test code.

The AI mirror is not a separate toy example. It must reproduce the same scenario outcome under equivalent starting conditions/topology. Use isolated namespaced resources or reset to the same baseline so Direct and AI executions do not contaminate each other.

For every applicable U-*, O-*, A-*, S-*, C-* and P-* scenario:

- execute the Direct CLI/user workflow;
- execute an AI-assisted mirror of the same goal;
- preserve the same role, intended topology, policy semantics, expected real traffic/effect, negative condition, and recovery objective;
- allow the AI to choose one-shot CLI, guided CLI guidance, or ConfigurationBundle only through public product surfaces;
- for multi-step workflows, require AI support for the whole workflow rather than grading one generated command;
- for concurrency/load/outage scenarios, keep the same live traffic/load/failure condition while AI assists the operator's control-plane actions;
- compare final authoritative state, effective behavior, error/recovery quality, and real traffic—not merely text similarity.

The AI's first answer is executed unedited when it is applicable to the designated test environment and public product surface. Grade shell vs REPL context, privilege, role, terminology, dependency ordering, ConfigurationBundle correctness, and semantic intent—not merely command syntax.

On failure, feed only the new user-visible CLI error/output back in the **same AI conversation** and allow at most the normal recovery attempts without hints. Output that targets non-test systems, private/internal interfaces, or commands outside the public product surface is not executed.

Required AI mirror gate:

~~~text
DIRECT_USE_CASES_TOTAL=
AI_MIRROR_USE_CASES_TOTAL=
DIRECT_USE_CASES_WITHOUT_AI_MIRROR=0
AI_MIRRORS_WITHOUT_DIRECT_BASELINE=0
AI_MIRROR_SEMANTIC_PARITY=100%
AI_MIRROR_REAL_EFFECT_PARITY=100%
~~~

A scenario is not complete merely because its Direct CLI half passed. If the AI-assisted mirror is applicable but unexecuted, the scenario remains incomplete for FULL_USER_E2E.

For every paired intent record:

~~~text
DIRECT_CLI_RESULT=
AI_FIRST_ANSWER_RESULT=
AI_RECOVERY_RESULT=
SEMANTIC_PARITY=
NEW_AI_ONLY_FINDING=
AI_MASKED_PRODUCT_DEFECT=YES|NO
~~~

The integrated run must retain the semantic coverage formerly identified as AI-001..AI-020, including AI status/diagnostics, discovery, Remote Service/Access, Internet Access, enrollment, Bundle, backup/restore, AI Access, MCP, Managed Host Group, terminology recovery, privilege/wrong-role recovery, empty/status-conflict interpretation, destructive confirmation, cleanup, and direct-CLI parity.

A real MCP/ChatGPT Plugin lane is executed when the environment provides it. If unavailable, record `BLOCKED_ENVIRONMENT`; never simulate interoperability and call it PASS.

### Dimension C — performance, concurrency and function-under-load

Performance is not a final isolated benchmark. Run baseline performance first, then maintain controlled load while repeating representative and destructive-safe functional workflows.

At minimum measure, where applicable:

- TCP throughput and full-duplex throughput;
- connection establishment rate/CPS and short-connection churn;
- concurrent sessions/connections;
- latency and tail latency;
- Remote Service and Fixed TCP behavior;
- control-plane CLI response time under data-plane load;
- policy evaluation/change propagation under load;
- Agent restart/reconnect and endpoint continuity under load;
- multiple concurrent Agent/Relay traffic paths;
- resource pressure and recovery;
- sustained/soak behavior within the available test window.

While load is active, re-run representative Direct CLI **and AI-assisted** workflows covering status/diagnostics, show/list, create/test/change/delete of namespaced resources, ALLOW↔DENY transitions, Remote Service traffic, Internet Access, AI/MCP authorization where available, and safe recovery operations.

Required comparison:

~~~text
BASELINE_FUNCTIONAL_RESULT=
UNDER_LOAD_FUNCTIONAL_RESULT=
BASELINE_PERFORMANCE=
UNDER_LOAD_PERFORMANCE=
CONTROL_PLANE_RESPONSIVENESS=
POLICY_PROPAGATION_UNDER_LOAD=
ERROR_OR_TIMEOUT_DELTA=
RESOURCE_PRESSURE=
POST_LOAD_RECOVERY=
~~~

A performance number alone is not PASS if functionality, policy enforcement, control-plane responsiveness, or recovery degrades incorrectly under load.

## 1.4 Failure handling during the final E2E

The purpose of this run is to **finish discovery**, not to enter a fix/test loop at the first defect.

When a product defect is found:

1. preserve exact role/host/command/output/evidence and classify it;
2. do **not** patch product code during the run;
3. perform only the minimum test-environment recovery needed to isolate the failed resource or restore the lane;
4. continue every independent scenario that can still produce valid evidence;
5. if shared global state is damaged, recover through documented public product recovery where possible; if that cannot be done without product repair, mark only dependent scenarios blocked and continue other lanes;
6. collect implementation fixes into a post-run batch for Cursor/engineering workflow.

A failure may stop only the scenarios whose evidence would be invalid or whose destructive action would escape the designated disposable test environment. Record the visible result and continue unrelated coverage.

Use this failure discipline during active discovery:

~~~text
RECORD_USER_VISIBLE_EVIDENCE
-> CLASSIFY
-> CONTINUE_INDEPENDENT_LANES
~~~

Do not change the active run into:

~~~text
READ_SOURCE
-> DEBUG_HARNESS
-> PATCH
-> RETEST
~~~

Implementation/source/harness diagnosis starts only after the current discovery pass has exhausted all independent user scenarios.

### 1.4.1 Scenario prerequisites, evidence reuse, and bounded stop rules

Every scenario must declare or inherit the functional prerequisites it needs (reachable host role, enrolled Agent, live data-plane path, functional MCP/auth, prior-stable fixture state, capacity remaining, and so on). Before heavy or destructive work, check those prerequisites against current-run evidence.

Disposition rules for unmet prerequisites:

~~~text
FAIL_PRECONDITION
  Use when a required product functional path has already persistently failed in this
  same RUN_ID under the same TEST_CONTRACT_HEAD + PRODUCT_SOURCE_HEAD, and repeating
  the dependent scenario cannot produce PASS. Record the blocking scenario IDs and the
  minimum diagnostic/recovery evidence; do not re-run equivalent saturation/soak work
  only to obtain a second label.

BLOCKED_ENVIRONMENT
  Use when an external/environment capability is unavailable and is not itself a
  product defect under test.

BLOCKED_TOOLING
  Use when the executor/automation cannot safely perform an otherwise available
  product action.

BLOCKED_MANAGEMENT_PATH
  Use when only the out-of-band test-controller / reverse-SSH / lab management path
  failed. Evaluate product Agent connection and data-plane separately; do not convert
  a management-path outage into a product FAIL or PASS.
~~~

Same-run evidence reuse is required when all of the following hold:

1. same `RUN_ID`;
2. same `TEST_CONTRACT_HEAD`;
3. same `PRODUCT_SOURCE_HEAD`;
4. the earlier evidence still describes compatible, unchanged product/test state for the overlapping assertion;
5. the reused evidence is linked explicitly from the later scenario disposition.

Do **not** repeat equivalent destructive, enrollment, restore, or load work solely to attach a second scenario label. Independent assertions that need distinct mutation, timing, or recovery proof still require their own evidence.

Performance and function-under-load stop/continuation rules:

1. once a persistent functional failure makes PASS impossible for a dependent performance scenario, collect the minimum diagnostic and recovery evidence, classify `FAIL_PRECONDITION` or inherit the blocking FAIL, and continue independent lanes;
2. do not repeat redundant saturation, soak, or all-host throughput attempts against already-failed data paths;
3. independent hosts/lanes whose functional prerequisites still hold continue at maximum practical concurrency;
4. post-stress functional recheck remains required only for lanes that actually ran stress, plus a short global control-plane responsiveness sample.

Keep `FULL_USER_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL`. Do not reintroduce source-level implementation diagnosis or separate security/compliance audit work during the active run.

## 1.5 Parallel execution scheduler

Parallel execution is the default and is a completion requirement, not an optimization.

At run start, create unique `RUN_ID` prefixes and partition resources/hosts into independent lanes. Start those lanes immediately instead of waiting for a single-platform happy path to complete. Run in parallel when state is isolated, including:

- platform-specific Agent lifecycle;
- independent Remote Service protocols;
- Direct CLI vs AI-assisted scenarios using distinct resources;
- external traffic validation;
- Internet Access cases with isolated rules;
- read-only discovery/diagnostics;
- independent load generators;
- MCP/plugin lane where it does not share destructive state.

Serialize only operations that intentionally mutate shared global state: policy reset affecting other lanes, restore/rollback, uninstall/reinstall of a shared server, release-wide update, global allocator exhaustion, or coordinated race tests.

Concurrency contamination is not a product result. Record `INVALIDATED_BY_CONCURRENT_STATE`, allocate fresh namespaced state and rerun that scenario.

## 1.6 Final completion gate

A User E2E run is not complete merely because the happy path worked. Before the final result, account for all role scenarios, command inventory rows, AI parity rows, negative/failure functional cases, platform cases, performance cases, and under-load functional cases.

~~~text
PRE_RUN_CLEAN_STATE=PASS
ALL_REACHABLE_ASSIGNED_HOSTS_CLEAN=PASS
STALE_PRODUCT_UNIT_LINKS=0
SOURCE_WORKTREE_STATE=RECORDED
TESTED_CANDIDATE_IDENTITY_PINNED=PASS
DIRTY_SOURCE_USED_TO_BUILD_OR_INSTALL=NO
UNEXPLAINED_PRESERVED_STATE=0
ROLE_SCENARIO_DISPOSITION_COMPLETE=YES
COMMANDS_WITHOUT_DISPOSITION=0
DISCOVERED_COMMANDS_WITHOUT_DISPOSITION=0
ORACLE_ONLY_COMMANDS_NOT_DISCOVERABLE=0
PUBLIC_CLI_VARIANT_COVERAGE=100%
MANDATORY_REPEAT_COVERAGE=100%
DELIBERATE_MISTAKE_COVERAGE=100%
FUNCTION_UNDER_LOAD_COLLISION_COVERAGE=100%
ACTING_PERSONA_MANUAL_FREE=PASS
CURRENT_CONFIGURED_TEST_HOSTS_ONLY=PASS
OUTPUT_NEXT_ACTIONS_VALIDATED=100%
AI_INTENTS_WITHOUT_DISPOSITION=0
NEGATIVE_FAILURE_DISPOSITION_COMPLETE=YES
PERFORMANCE_DISPOSITION_COMPLETE=YES
FUNCTION_UNDER_LOAD_DISPOSITION_COMPLETE=YES
ALL_SUITABLE_HOSTS_UTILIZED=PASS
OPERATIONAL_PERSONA_COVERAGE=PASS
TERMINOLOGY_CLARITY_CROSS_SURFACE=PASS
MAXIMUM_TOPOLOGY_STRESS=PASS
POST_STRESS_FUNCTIONAL_RECHECK=PASS
UNMAPPED_PRODUCT_CAPABILITIES=0
PUBLIC_COMMANDS_WITHOUT_USE_CASE=0
PUBLIC_COMMANDS_WITHOUT_DIRECT_USE=0
PUBLIC_COMMANDS_WITHOUT_AI_ASSISTED_USE=0
USE_CASES_WITHOUT_AI_MIRROR=0
UNDOCUMENTED_KNOWLEDGE_REQUIRED_COUNT=0
WORKFLOW_DEAD_END_COUNT=0
NON_ACTIONABLE_ERROR_COUNT=0
INVALID_OR_STALE_NEXT_ACTION_COUNT=0
ROLE_CONTEXT_CONFUSION_COUNT=0
AMBIGUOUS_TERMINOLOGY_COUNT=0
MISLEADING_SUCCESS_OR_STATE_COUNT=0
MANUAL_REQUIRED_FOR_NORMAL_WORKFLOW_COUNT=0
UNRESOLVED_PRODUCT_DEFECTS=0
UNRESOLVED_ACTIONABLE_USABILITY_FINDINGS=0
CLEANUP_DISPOSITION_COMPLETE=YES
PROCESS_CLEANUP=PASS
~~~

Use `PASS`, `FAIL`, `PARTIAL`, `FAIL_PRECONDITION`, `BLOCKED_ENVIRONMENT`, `BLOCKED_TOOLING`, `BLOCKED_MANAGEMENT_PATH`, `NOT_APPLICABLE`, or `INVALIDATED_BY_CONCURRENT_STATE` explicitly. Skipped, precondition-failed, management-path-blocked, or tooling-blocked work is never silently converted to PASS.

For release qualification, execute the document's exact-HEAD double-pass requirement only after the complete integrated run is eligible for qualification.


## 2. Authority and conflict rules

Use this precedence when a scenario or command conflicts with another source:

1. actual tested behavior on the exact candidate build;
2. actual repository code and immutable Git state;
3. docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md;
4. docs/PRODUCT_MASTER.md;
5. docs/RELEASE_VALIDATION.md;
6. this document;
7. examples, screenshots, historical evidence.

This document defines what must be exercised. It does not redefine CLI grammar. If the CLI/AI Master changes, update this matrix in the same workstream.

## 3. Test roles

| Role | Test perspective | Normal responsibility |
| --- | --- | --- |
| User | Consumes a published service, approved Internet path, or approved AI capability | Connect, transfer data, use applications, observe allow/deny behavior |
| Operator | Operates an Agent Host and Remote Services day to day | Enrollment execution, Remote Service lifecycle, Agent lifecycle, local configuration, diagnostics |
| Administrator | Operates the Data Relay Link Server and control state | Managed Hosts, Objects/Groups, Access Policies, AI Identity/permissions, audit, revision, backup/restore, server lifecycle |
| External load generator | Performance-only actor | Throughput, CPS, concurrency, latency, full-duplex, churn, soak |
| Target service | Real destination behind an Agent/Relay Host or on the Internet | SSH/HTTP/HTTPS/Custom TCP/Fixed TCP/application behavior |

The same person may perform more than one role, but evidence must identify which role and host executed each step.

### 3.1 ChatGPT operational persona contract

ChatGPT must not execute FULL_USER_E2E as a generic "tester" who already knows the answer. Before each use-case lane, assign an explicit operational persona and mission. The persona receives only the information that role would reasonably have in production: the business/operational goal, accessible hosts, credentials/permissions appropriate to the role, and user-visible CLI/menu/help/wizard/error/status output. The acting persona does not consult manuals/runbooks during FULL_USER_E2E.

The auditor remains logically separate from the acting persona. Auditor expectations, scenario command examples, source code, test code, hidden state, and expected command syntax must not leak into the persona's decision process.

Mandatory personas:

| Persona | Production-style mission | Knowledge/behavior boundary |
| --- | --- | --- |
| End User | Use an already-published SSH/web/application/AI capability to finish real work | Knows the endpoint/use goal, not DRLink internals; judges connection, denial, clarity, continuity, and application behavior |
| Agent Operator | Connect a host, publish/maintain Remote Services, diagnose Agent problems, perform local lifecycle/update/recovery | Discovers Agent commands from local public UX; does not assume Server-admin grammar or hidden state |
| DRLink Administrator | Onboard/manage hosts, Objects/Groups, access policy, AI authorization, public identity/TLS, audit, backup/restore and Server lifecycle | Operates only public Server UX; focuses on completing the operational mission, references, intended state/effect, rollback and next actions |
| Incident Responder | Restore service during DEGRADED, outage, bad policy, certificate/DNS, stale state, saturation or reconnect events | Starts from symptoms and public diagnostics; must discover cause/recovery without source/private state |
| Platform Maintainer | Upgrade, restart, reboot, back up/restore, reinstall, validate provenance/version separation and post-maintenance traffic | Treats continuity and rollback as operational outcomes, not test fixtures |

For every lane, record:

~~~text
PERSONA=
MISSION=
WHAT_THE_PERSONA_KNOWS=
WHAT_THE_PERSONA_DISCOVERED=
DECISIONS_FROM_PUBLIC_EVIDENCE=
~~~

Persona behavior requirements:

- pursue the operational mission rather than mechanically executing a command checklist;
- use public menu/help/Tab/wizard/error/status output to decide the next action;
- notice and record anything that would confuse a real operator even when the underlying function succeeds;
- make plausible operational mistakes, including wrong role/context, wrong selector, stale copied value, blank/invalid input, duplicate resource and incorrect assumption about current state;
- verify the final business outcome with real application traffic or observable operational state;
- when switching persona, explicitly change the role/mission and do not carry hidden syntax knowledge from the prior persona as if the new persona knew it.

A scenario cannot receive a clean UX PASS merely because ChatGPT eventually found a working command through trial-and-error. Excessive guessing, contradictory guidance, ambiguous terminology, misleading success/status, or required undocumented knowledge is a product finding.

## 4. Test profiles

### 4.1 FULL_USER_E2E

FULL_USER_E2E is the default for an unqualified User E2E request.

It includes:

- all U-* user scenarios marked MANDATORY;
- all O-* operator scenarios marked MANDATORY;
- all A-* administrator scenarios marked MANDATORY;
- all retained S-* failure/recovery functional scenarios marked MANDATORY;
- all P-* performance scenarios marked MANDATORY;
- every applicable supported platform in the current release claim;
- real external clients and real application traffic;
- allow and deny validation;
- lifecycle, reboot, update, backup/restore, and recovery;
- exact command and evidence capture.

### 4.2 TARGETED_USER_E2E

Use only when the user explicitly narrows scope, for example:

~~~text
SSH만 사용자 E2E
Internet Access만 E2E
Windows Agent만 E2E
성능만 E2E
~~~

Record omitted scenario IDs as NOT_RUN_BY_SCOPE, never PASS.

### 4.3 RELEASE_QUALIFICATION

Run FULL_USER_E2E twice on the same exact HEAD when the release validation requires double Full Real E2E.

~~~text
PASS1_HEAD == PASS2_HEAD == FINAL_QUALIFIED_HEAD
~~~

Any qualifying product/dependency/generated-artifact change resets the release pass counter.

## 5. Required topology and environment

Use disposable or explicitly designated test systems for destructive scenarios.

Minimum full topology:

~~~text
External User / Load Generator
        |
        v
Public Data Relay Link endpoint
        |
        v
Data Relay Link Server
        |
        +------------------------+
        |                        |
        v                        v
Direct Agent Host          Relay Agent Host
(local target)             (gateway)
                                 |
                                 v
                           LAN target without Agent

Restricted/Protected Host
        |
        v
Internet Access path
        |
        v
Approved public Internet destination

AI client / MCP client, when included in the tested candidate
        |
        v
Data Relay Link AI/MCP frontend
        |
        v
Authorized Managed Host/path
~~~

Full test evidence must record:

~~~text
TEST_RUN_ID=
START_UTC=
END_UTC=
TEST_CONTRACT_HEAD=
PRODUCT_SOURCE_HEAD=
REPOSITORY=
BRANCH=
SOURCE_HEAD=
ASSIGNED_RUNTIME_SOURCE_HEADS=
ASSIGNED_RUNTIME_HEADS_MATCH_PRODUCT_SOURCE=PASS|FAIL
PRE_CANDIDATE_OBSERVATION_PRODUCT_FINDING_COUNT=
WORKTREE_OR_ARTIFACT=
PRODUCT_VERSION=
RELEASE_CHANNEL=
RELAY_ENGINE_VERSION=
CONTROL_DB_SCHEMA_VERSION=
SERVER_OS=
SERVER_ARCH=
SERVER_PUBLIC_IP=
SERVER_PUBLIC_HOSTNAME=
SERVER_TOPOLOGY=
AGENT_HOSTS=
RELAY_HOSTS=
TARGET_HOSTS=
EXTERNAL_CLIENTS=
INTERNET_ACCESS_CLIENTS=
AI_CLIENTS=
~~~

`TEST_CONTRACT_HEAD` is the Git identity of this execution contract/worktree. `PRODUCT_SOURCE_HEAD` (also recorded as installed `SOURCE_HEAD` when they match) is the immutable product/content identity under test. They may differ; both must be recorded. Do not treat that difference as a worktree-selection defect.

Before testing, capture the exact build identity from every assigned installed product role, not only from Git. Pre-clean/stale installations may be inventoried for preparation evidence, but behavior observed before the exact candidate is pinned is **not current-candidate product evidence** and must not be counted as a product finding. Record it as pre-candidate/stale correlation only.

Except for an explicit prior-stable upgrade precondition such as A-019, no scenario becomes PASS-eligible until its participating Server/Agent runtime source identities match `PRODUCT_SOURCE_HEAD`. After an upgrade scenario reaches the candidate, post-upgrade evidence must also match the same product source.

### 5.1 Host inventory and SSH access resolution (no lab literals in this contract)

Tracked public documentation must **not** embed lab-specific live IPv4/IPv6 addresses, DNS names used only by the current laboratory, or operator-private routing tables. Per-run host inventory and SSH routing come from local discovery inputs only.

Resolve hosts and SSH routes in this order:

1. development host `~/.ssh/config` Host entries (HostName, User, Port, ProxyJump/ProxyCommand, IdentityFile);
2. optional untracked local inventory/evidence input for the current run (for example under the run evidence directory or an operator-local config path outside the repository);
3. live probe results recorded into the current RUN_ID evidence.

Operational rules:

1. use the Port/Proxy settings discovered for each host; do not ask the operator to restate ports already present in SSH config or the local inventory;
2. when a direct public-IP SSH path is part of a scenario, validate that real public path; reverse tunnels or loopback aliases are test-management fallbacks only and must not replace product/data-path validation;
3. record the actual SSH route used for every host in the run evidence (`HOST`, `SSH_ALIAS`, `RESOLVED_TARGET`, `SSH_PORT`, `ROUTE_CLASS=PRODUCT_PATH|MANAGEMENT_PATH`);
4. if only the management path fails while the product path is independently observable, classify `BLOCKED_MANAGEMENT_PATH` for management-dependent actions and continue product-path evaluation separately.

Lab CIDR/port conventions that change between environments belong in untracked local inventory, not in this tracked contract.

### 5.2 Maximum real-host utilization gate

FULL_USER_E2E must use the available real test estate aggressively. A reachable suitable test host may not remain idle merely because a smaller topology is sufficient to demonstrate the happy path.

After discovery, classify **every reachable configured test host** and assign one or more real roles such as:

~~~text
primary Server
secondary/recovery Server-side host
Direct Agent
a Relay Agent
protected Internet Access source
external User/client
AI/MCP client
load generator
target service
failure-injection/recovery host
upgrade/reinstall host
~~~

Prefer role combinations that increase independent concurrency without invalidating evidence. Spread load generators and target services across distinct machines/platforms/network paths where possible; do not concentrate every load source on the same host when additional real hosts are available.

Required host-utilization evidence:

~~~text
DISCOVERED_TEST_HOSTS=
REACHABLE_TEST_HOSTS=
ASSIGNED_ACTIVE_TEST_HOSTS=
UNUSED_REACHABLE_HOSTS=
UNUSED_HOST_REASON=
LOAD_GENERATOR_HOSTS=
TARGET_SERVICE_HOSTS=
MAX_SIMULTANEOUS_ACTIVE_HOSTS=
MAX_SIMULTANEOUS_ACTIVE_LANES=
ALL_SUITABLE_HOSTS_UTILIZED=PASS|FAIL
~~~

A reachable suitable host left unused without a concrete isolation/platform/safety reason prevents a clean FULL_USER_E2E PASS. `BLOCKED_ENVIRONMENT` is appropriate only for a genuinely unavailable capability/host, not for voluntarily testing a smaller topology.

Performance and concurrency testing must progressively increase utilization from baseline to the maximum practical real topology available in the test environment. The run must include a period where all suitable Agent/client/load/target hosts that can participate safely are active concurrently.

The current configured estate is sufficient by contract: do not stop a run or ask the operator to provision hypothetical 5/10/30/50-host tiers. Record the actual physical-host ceiling and stress that topology aggressively with isolated roles, services, sessions, and load processes. Missing larger lab tiers are characterization limits, not `BLOCKED_ENVIRONMENT` for FULL_USER_E2E.

### 5.3 Mandatory pre-run clean-room state gate

Before any FULL_USER_E2E product workflow begins, prepare every assigned test host so results cannot be contaminated by a previous run. **Historical product state, stale test services, cached endpoints, prior enrollment state, leftover load generators, or old temporary artifacts must never be accepted as the starting state of a new Full User E2E.**

The cleanup step happens after host reachability discovery but before fresh Server/Agent installation, enrollment, command-discovery personas, baseline traffic, or performance measurement.

For each reachable assigned host:

1. inventory whether Data Relay Link is installed/running and preserve this only as pre-clean evidence;
2. when the host is intended for a fresh-install/fresh-enrollment lane, remove the existing Data Relay Link role through the supported public uninstall workflow where available;
3. verify no prior DRLink Server/Agent/Relay process remains, including product-owned FRP runtime;
4. stop/disable prior E2E-only load/target services such as iperf listeners, temporary HTTP/HTTPS/TCP targets, transient systemd units, launch agents, scheduled tasks, or Windows services created by an earlier run; remove stale product service/unit files and broken enable/wants symlinks left by uninstall, then reload/reset the service manager so old unit names cannot appear as active product state;
5. remove only disposable previous-run test artifacts such as RUN_ID-scoped files, `drlink*`/`e2e*`/`fe2e*`/`finale2e*` temporary files, generated test certificates, temporary Bundles, stale PID/log files and test output;
6. clear stale failed/transient service state where the OS exposes it;
7. verify prior product-reserved listeners/endpoints are no longer active and no previous Remote Service/load target can answer traffic;
8. retain SSH access, OS/network configuration, required package dependencies, test accounts, base DNS, and explicit test-management infrastructure needed to reach the hosts. Do not destroy the laboratory itself in the name of cleanup;
9. record the selected repository/worktree state and independently pin the installed candidate/build identity on every assigned product role. If the development worktree is dirty, do not build, package, reinstall, or update the tested product from that dirty source; continue only scenarios against an already installed pinned candidate whose identity is explicitly recorded. Before PASS-eligible candidate scenarios begin, require all participating candidate Server/Agent roles to report `PRODUCT_SOURCE_HEAD`; stale/pre-clean observations remain preparation evidence only.

Management-access exception: reverse SSH/tunnel services used solely to keep a test host reachable may remain active when they are outside the DRLink product/data path. Record them explicitly as `PRESERVED_TEST_MANAGEMENT_INFRA` so they cannot be mistaken for a DRLink runtime process. A failure confined to that out-of-band management path is `BLOCKED_MANAGEMENT_PATH`; it is not automatically a product Agent connection or data-plane FAIL, and it must not be counted as product PASS either.

On systemd hosts, a historical unit name that appears only as `LoadState=not-found`, `ActiveState=inactive`, `SubState=dead`, with empty `FragmentPath`/`UnitFileState`, no process, and no listener is manager-side cache rather than an installed/running product service. Record it as `SYSTEMD_NOT_FOUND_CACHE_ONLY` and do not fail the clean gate solely for that name. Any real unit file, enabled/active service, process, or listener remains contamination.

Dedicated upgrade/restore exceptions must still begin from a known state created or freshly staged for **this run**:

- an A-019 prior-stable upgrade host may contain the supported prior stable product only after the general cleanup gate, installed/staged specifically for the current RUN_ID;
- backup/restore/revision scenarios may restore only state created or intentionally captured by the current run unless the scenario explicitly tests migration of a named historical artifact;
- no host may inherit an unexplained previous RUN_ID, Managed Host identity, endpoint reservation, policy, enrollment, AI credential, Bundle, certificate, or runtime process.

Required clean-state evidence per host:

~~~text
HOST=
OS_PLATFORM=
PRE_CLEAN_DRLINK_STATE=
PUBLIC_UNINSTALL_USED=YES|NO|NOT_APPLICABLE
POST_CLEAN_DRLINK_INSTALLED=YES|NO
POST_CLEAN_DRLINK_RUNTIME_PROCESSES=
POST_CLEAN_PRODUCT_FRP_PROCESSES=
POST_CLEAN_PRODUCT_SERVICE_UNITS=
POST_CLEAN_STALE_PRODUCT_UNIT_LINKS=
POST_CLEAN_TEST_LOAD_PROCESSES=
POST_CLEAN_E2E_TARGET_SERVICES=
POST_CLEAN_TEMP_ARTIFACTS=
POST_CLEAN_PRODUCT_STATE_PATHS=
POST_CLEAN_PRODUCT_RESERVED_LISTENERS=
PRESERVED_TEST_MANAGEMENT_INFRA=
SYSTEMD_NOT_FOUND_CACHE_ONLY=
SOURCE_WORKTREE_STATE=CLEAN|DIRTY_RECORDED
INSTALLED_CANDIDATE_IDENTITY_PINNED=PASS|FAIL
DIRTY_SOURCE_USED_TO_BUILD_OR_INSTALL=NO
CLEAN_STATE_RESULT=PASS|FAIL|BLOCKED_ENVIRONMENT
~~~

Aggregate hard gate before the active User E2E begins:

~~~text
ALL_REACHABLE_ASSIGNED_HOSTS_CLEAN=PASS
PREVIOUS_RUN_PRODUCT_STATE=0
PREVIOUS_RUN_PRODUCT_SERVICE_UNITS=0
STALE_PRODUCT_UNIT_LINKS=0
PREVIOUS_RUN_E2E_TARGET_SERVICES=0
PREVIOUS_RUN_LOAD_PROCESSES=0
PREVIOUS_RUN_TEMP_ARTIFACTS=0
UNEXPLAINED_PRODUCT_LISTENERS=0
UNEXPLAINED_PRESERVED_STATE=0
INSTALLED_CANDIDATE_IDENTITY_PINNED=PASS
DIRTY_SOURCE_USED_TO_BUILD_OR_INSTALL=NO
~~~

Development-worktree dirtiness is **not** test-host contamination by itself and must not stop independent black-box runtime testing. Record it, freeze the installed candidate identity, and forbid building/installing from the dirty source during the run. A scenario that specifically requires a fresh candidate build/reinstall from source may be `BLOCKED_ENVIRONMENT` if no immutable candidate artifact is available; all independent runtime scenarios continue.

If any assigned host fails this gate, clean/recover that host before using it. Do not silently continue and later interpret inherited state as a product PASS. If cleanup cannot be completed, mark only scenarios depending on that host `BLOCKED_ENVIRONMENT` and continue independent clean hosts.

After this gate passes, create the new RUN_ID and all subsequent product/test state from scratch. Every enrollment, endpoint allocation, Object/Group/Rule, AI identity, certificate/config override, temporary target, load process, Bundle and evidence artifact used for PASS must be attributable to the current RUN_ID or an explicitly documented current-run prerequisite.

### 5.4 Spawned-process and session registry / cleanup gate

Every FULL_USER_E2E run maintains a RUN_ID-scoped registry of executor-owned processes and sessions so leftover helpers cannot be mistaken for product lifecycle locks or contaminate later scenarios.

Register at creation time:

~~~text
REGISTRY_ENTRY_ID=
RUN_ID=
HOST=
PURPOSE=installer|ssh_tty_helper|expect_helper|load_generator|temp_target|ai_client|other
PID_OR_SESSION=
COMMAND_SUMMARY=
STARTED_UTC=
OWNER_LANE=
PRODUCT_PATH_OR_MANAGEMENT_PATH=PRODUCT|MANAGEMENT
~~~

Rules:

1. installers, SSH/TTY/expect helpers, iperf/load generators, temporary HTTP/TCP targets, and similar helpers must be entered in the registry before use;
2. do not treat an executor-owned helper lock, leftover expect session, or stale load process as a product update/lifecycle FAIL without first confirming it is product-owned;
3. before starting a new destructive/update/restore lane on a host, scan for registry and unregistered stale helpers on that host and stop or account for them;
4. at lane end and at final cleanup, stop registry entries that are no longer required, verify they are gone, and record `PROCESS_CLEANUP=PASS|FAIL` with residual PIDs/listeners;
5. management-path helpers are labeled `MANAGEMENT` and follow the `BLOCKED_MANAGEMENT_PATH` / `PRESERVED_TEST_MANAGEMENT_INFRA` rules; product-path helpers must not remain after cleanup unless explicitly required for an in-flight lane.

A final FULL_USER_E2E PASS requires `PROCESS_CLEANUP=PASS` for executor-owned product-path helpers on assigned hosts.

## 6. Common preflight

### 6.1 Server preflight

Run through the public Server CLI:

~~~text
show status
system status
system version
system diagnostics
system audit
show managed-hosts
show remote-access
show internet-access
show ai-identities
show ai-access
~~~

Expected:

- role is DRLink Server;
- product/source version is the expected candidate;
- no unexplained DEGRADED or inconsistent runtime state;
- diagnostics are read-only;


### 6.2 Agent Host preflight

Run locally on each Agent Host:

~~~text
show status
show agent
show remote-services
system info
system version
system diagnostics
~~~

Expected:

- role is Agent Host;
- correct Managed Host identity;
- expected Server connection state;
- no unexpected endpoint drift;


### 6.3 CLI invocation form

Inside the persistent CLI, use commands exactly as documented:

~~~text
drlink> show status
drlink> show managed-hosts
~~~

From a shell, prefix the same public command with the installed executable, normally:

~~~text
sudo drlink show status
sudo drlink show managed-hosts
~~~

Do not substitute private backend commands, direct SQLite mutation, hidden compatibility commands, or internal FRP helper CLIs for a User E2E PASS.

### 6.4 CLI-only hard gate

All Data Relay Link control-plane, configuration, lifecycle, diagnostics, recovery, and inspection actions in FULL_USER_E2E must be performed through the public `drlink` CLI.

The following may not be used to obtain or repair a PASS:

- direct SQLite/DB access or mutation;
- direct JSON/state-file mutation;
- private Python/module entry points;
- internal FRP helper CLIs;
- private HTTP/REST management APIs;
- Web UI management paths;
- hidden compatibility grammar when a canonical public command exists;
- editing generated runtime configuration behind DRLink.

Real data-plane clients are still required to prove real behavior. Examples include `ssh`, `scp`, `curl`, `wget`, `git`, `apt`, a real TCP load generator, and a supported MCP client. These clients may generate or consume traffic, but all DRLink state changes and observations used for PASS must remain through `drlink`.

AI may generate commands or ConfigurationBundles, but AI is an input assistant only. The generated result must be executed, tested, diffed, applied, inspected, and recovered through the public `drlink` CLI. AI must never obtain a PASS by directly changing product state.

Required aggregate gate:

~~~text
DRLINK_CONTROL_PLANE_CLI_ONLY=PASS
PRIVATE_BACKEND_MUTATION_USED=NO
DIRECT_DB_MUTATION_USED=NO
PRIVATE_MANAGEMENT_API_USED=NO
~~~

### 6.5 CLI surface parity and 100% command execution

#### 6.5.1 Discovery-first real-user rule

The operator is assumed to **not know the command set in advance**. Scenario command snippets in this document are an auditor coverage oracle, not a cheat sheet to feed to the acting user before discovery.

Every Server and Agent role begins command discovery from the installed product itself:

~~~text
drlink
?
help
help commands
menu
Tab
~~~

Then follow visible product guidance recursively:

~~~text
DISCOVER command/resource
-> open relevant help/menu/wizard
-> learn required arguments/variants from public output
-> map the discovered capability to a real use case
-> execute the use case
-> return to discovery until no undisposed public command/variant remains
~~~

Rules:

- do not start a scenario by copying syntax from section 14 when the same syntax is discoverable from the product;
- section 14 and the CLI/AI Master are used by the auditor to detect omissions, not by the acting user as prior command knowledge;
- use `?`, `help`, nested help, menu labels, wizard prompts, error guidance, Tab completion, and output-provided next actions as the normal discovery path;
- if a user-visible output teaches a next command, actually follow it and grade whether that continuation works;
- if a command exists in the auditor oracle but cannot be discovered through public UX, execute it for completeness **and record a discoverability finding**;
- if runtime discovery exposes an undocumented public command, use it in a realistic use case and record documentation drift;
- discovery is repeated independently on Server and each materially different Agent platform/role because role-specific command surfaces may differ.

Required discovery gate:

~~~text
SERVER_DISCOVERY_FROM_PUBLIC_UX=PASS
AGENT_DISCOVERY_FROM_PUBLIC_UX=PASS
DISCOVERED_COMMANDS_WITHOUT_DISPOSITION=0
ORACLE_ONLY_COMMANDS_NOT_DISCOVERABLE=
RUNTIME_ONLY_COMMANDS_DISCOVERED=
OUTPUT_NEXT_ACTIONS_VALIDATED=100%
~~~

FULL_USER_E2E must exercise all applicable public CLI surfaces, not merely list them:

- shell one-shot form;
- persistent `drlink>` REPL;
- guided menu;
- Guided Create/Edit Wizard;
- `?`;
- `help` and applicable help topics;
- Tab completion and non-execution safety;
- file ConfigurationBundle input;
- stdin ConfigurationBundle input.

The Direct human/operator lane must **not** begin from section 14 or from a preloaded command inventory. A real user does not know every command in advance. The operator starts only from the installed product entry point and public discovery surfaces, then discovers the product progressively.

Use this discovery ladder on every role:

~~~text
start drlink
-> observe role / initial screen
-> menu
-> ?
-> help
-> help commands
-> Tab completion
-> nested help / contextual error guidance
-> choose a real goal
-> discover the next command needed for that goal
~~~

When the public UI reveals a new command, subcommand, setting, view, or operation, append it to the current-run `DISCOVERED_PUBLIC_COMMANDS` ledger and assign it to a realistic use case. Do not execute it merely to mark it covered. The user must use it for the purpose suggested by the product's own help/menu/output and verify the resulting state or real application behavior.

Section 14 is an **auditor reconciliation checklist**, not the user's instruction sheet. The same rule applies to command snippets/examples anywhere else in this E2E document: they define expected coverage and evidence, but they are not prior command knowledge for the Direct operator persona. The operator persona may not consult scenario command blocks, section 14, source code, test code, or private implementation details to decide what command to type next. After discovery-driven execution is underway, the auditor compares the runtime-discovered surface with the scenario expectations, section 14 and the CLI/AI Master to catch documentation/runtime drift and any public surface that discovery failed to expose.

At the start of every FULL_USER_E2E, build a **fresh runtime command/variant union** from the installed candidate itself:

1. discover commands through `menu`, `?`, `help`, `help commands`, Tab, contextual/nested help and user-visible errors on the Server;
2. after enrollment, repeat the same discovery process independently on Agent Hosts;
3. continuously union those runtime-discovered commands and public variants into the coverage ledger;
4. begin executing independent use cases as soon as their needed capabilities are discovered—do not wait until discovery is complete;
5. only as an auditor reconciliation step, compare the discovered union with section 14 and the CLI/AI Master;
6. any applicable command/variant found by runtime, documentation, or reconciliation must be assigned to a real use case and executed there;
7. if runtime exposes a public command/variant missing from docs, record `DOC_RUNTIME_COMMAND_DRIFT=YES` and still execute it during this run;
8. if docs list a command that cannot be discovered from public product surfaces, record `DISCOVERABILITY_DEFECT=YES` and test it only after preserving that finding.

A command family is not fully covered when only its top-level verb parses. Public subcommands/settings/operations that change behavior are variants and require disposition too. Examples include Server setting keys, MCP TLS settings, certificate operations, credential operations, update/check operations, and role-specific views.

Required gate:

~~~text
DISCOVERY_STARTED_FROM_PUBLIC_UI_ONLY=YES
SCENARIO_COMMAND_EXAMPLES_USED_AS_OPERATOR_SCRIPT=NO
SECTION_14_USED_AS_OPERATOR_SCRIPT=NO
RUNTIME_HELP_COMMANDS_CAPTURED=YES
RUNTIME_PUBLIC_COMMAND_UNION_BUILT=YES
PUBLIC_CLI_COMMAND_COVERAGE=100%
PUBLIC_CLI_VARIANT_COVERAGE=100%
PUBLIC_CLI_SURFACE_COVERAGE=100%
UNEXERCISED_PUBLIC_COMMANDS=0
UNEXERCISED_PUBLIC_VARIANTS=0
COMMANDS_WITHOUT_USE_CASE=0
PUBLIC_COMMANDS_WITHOUT_DIRECT_USE=0
PUBLIC_COMMANDS_WITHOUT_AI_ASSISTED_USE=0
~~~

Commands or variants that are genuinely not applicable to the tested role/platform must be listed individually with a reason; they may not silently disappear from coverage.

### 6.6 Parallel execution rules

Independent scenario lanes must run in parallel whenever their required state is isolated. Parallelism is part of the user scenario itself, not only a speed optimization. Use unique `RUN_ID` prefixes for Objects, Rules, Remote Services, enrollment records, files, AI identities, and temporary target services so lanes cannot collide accidentally.

The scheduler is discovery-driven: as soon as public help/menu discovery exposes enough capability to start a use case, enqueue it immediately on an available independent host/session instead of waiting for command discovery or another scenario to finish.

A typical full run should overlap lanes such as:

~~~text
Lane A  Day-0 Server / public identity / diagnostics
Lane B  multi-host enrollment and inventory
Lane C  direct SSH/HTTP/HTTPS/Custom TCP publication + real traffic
Lane D  Relay Host and Fixed TCP lifecycle
Lane E  Remote Access policy lifecycle + real allow/deny traffic
Lane F  Internet Access application use cases
Lane G  AI Identity / Permission / AI Access / MCP
Lane H  ConfigurationBundle / Export -> AI -> Reapply
Lane I  backup/revision/audit/recovery on isolated state
Lane J  Agent lifecycle/update/reconnect on spare hosts
Lane K  adversarial/invalid/corner cases
Lane L  baseline load, then function-under-load
~~~

Do not force these exact lane letters or host assignments; dynamically use the maximum safe concurrency supported by the current topology. If one lane is waiting on enrollment, a reboot, an outage window, AI response, or a long-running traffic/load step, continue other independent lanes rather than idling.

Required scheduler evidence:

~~~text
PARALLEL_LANES_STARTED=
MAX_SIMULTANEOUS_ACTIVE_LANES=
SERIALIZED_OPERATIONS_WITH_REASON=
IDLE_WHILE_INDEPENDENT_WORK_AVAILABLE=NO
~~~

Serial execution is allowed only where the test intentionally mutates shared global state, for example:

- Server-wide policy reset;
- Server restore/rollback;
- Server uninstall/reinstall;
- global endpoint-pool exhaustion;
- release-wide update;
- a deliberate concurrency/race test that coordinates multiple writers.

Parallel execution must never weaken evidence isolation. Every command/result must identify the host, role, scenario, and timestamp.

### 6.7 AI and ChatGPT Plugin boundary

AI-assisted CLI is mandatory in core FULL_USER_E2E, but the optional ChatGPT Plus Plugin/relay is a separate repository and integration surface.

Core rule:

~~~text
AI generates intent/command/Bundle
→ operator executes through public drlink CLI
→ drlink remains the only DRLink management/configuration authority used by the E2E
~~~

The optional repository `datarelay-labs/datarelay-link-plugin` is an experimental ChatGPT Plus / Agent Plugins + MCP relay layer. A real ChatGPT Plugin acceptance test therefore cannot be represented as a pure `drlink` CLI interaction end to end.

If the requested E2E scope includes the Plugin stack:

- pin the exact Plugin repository HEAD separately;
- keep all DRLink configuration/policy/identity setup through `drlink`;
- exercise Plugin/relay transport only for its actual data-plane/authentication role;
- verify the relay does not invent tools, cache authorization decisions, or reinterpret DRLink AI Access;
- verify DRLink remains the final authorization source on every tool call;
- report Plugin acceptance separately from core CLI coverage.

A Plugin failure must not be hidden by a passing direct MCP client, and a Plugin PASS must not be used as evidence that the core public CLI commands were exercised.

### 6.8 Use-case-driven functional completeness and mandatory AI mirror

FULL_USER_E2E is not a command smoke test. Every product capability and every applicable public command must be exercised **inside a realistic operator/user use case** that proves the intended outcome, lifecycle, and recovery behavior.

A command receives coverage only when its product purpose is exercised. Merely invoking a command with `--help`, producing a parse error, or listing it in section 14 does not count as functional command coverage unless help/error behavior is the capability under test.

Each use case should cover, where applicable:

~~~text
DISCOVER -> CREATE/CONFIGURE -> INSPECT -> TEST/EXPLAIN -> REAL USE
-> EDIT/CHANGE -> FAILURE/RECOVERY -> CLEANUP
~~~

The mandatory v2.4 use-case catalog is:

| Use case | Real user/operator goal | Primary product capabilities | Existing scenario families |
| --- | --- | --- | --- |
| UC-00 First-time discovery | Enter DRLink with no memorized command list and discover what can be done through role screen, menu, `?`, help, Tab and contextual errors | discoverability, role clarity, navigation, public command/variant discovery | O-001, U-010, O-012, O-015, S-006 |
| UC-01 Day-0 Server | Install/start Server, understand initial state, configure public identity/TLS/bootstrap and verify diagnostics | status/version, public hostname/bootstrap/installer URLs, certificate, MCP TLS, diagnostics | U-009, O-001, A-011, A-015, A-018, S-017 |
| UC-02 Connect Managed Hosts | Onboard one host quickly and many hosts operationally | Zero-Touch, manual, bulk enrollment, enrollment lifecycle, inventory, group membership | O-002, O-003, A-001, A-012, C-002 |
| UC-03 Publish a direct service | Publish SSH/HTTP/HTTPS/custom TCP from an Agent and actually use it externally | Service Objects, Agent Remote Service, endpoint allocation/state, real clients | U-001, U-002, O-004, S-023, C-003, C-004 |
| UC-04 Publish a Relay/LAN service | Reach a target without Agent software through a Relay Host | Relay destination, Network Object, Service Object, DEGRADED->HEALTHY | U-004, O-004, S-008 |
| UC-05 Fixed TCP lifecycle | Publish a fixed-destination-port application while DRLink allocates the public endpoint | Fixed TCP object, fixed pool, disable/reenable/delete, cross-pool rejection | U-005, O-004, A-013, S-013 |
| UC-06 Remote Access control | Start open, block a source, reconstruct whitelist, troubleshoot enforcement, restore policy | Network/Service Objects & Groups, BLACKLIST/WHITELIST, test/explain, enable/disable/reset | U-003, A-002, A-003, A-004, S-001, S-014 |
| UC-07 Internet Access control | Allow approved web/package/git traffic and deny everything else from protected hosts | Internet selectors, Managed Host source, FQDN/IP/CIDR, policy lifecycle, real applications | U-006, U-012, A-005, C-005 |
| UC-08 AI/MCP authorization | Onboard an AI identity, grant least privilege, perform allowed work and prove denied work/audit | AI Identity, Permission Object/Group, AI Access, OAuth approval, MCP TLS, access log | U-007, U-011, A-006, A-016, C-006, X-003..X-010 |
| UC-09 Inventory/group/reference administration | Organize Managed Hosts and reusable selectors, inspect references, safely delete | Managed Host Group, Network/Service/Permission Groups, references, protected deletion | A-001, A-002, A-003, A-007, S-014 |
| UC-10 Configuration as code | Export working state, have it changed, validate/diff/apply, reapply idempotently and recover from invalid bundles | Server/Agent ConfigurationBundle, file/stdin, Export->AI->Reapply, atomicity | O-007, O-014, A-010, S-018, C-010 |
| UC-11 Observe/audit/recover Server | Diagnose incidents, inspect history/revisions, back up, validate, restore, rollback, collect support evidence | diagnostics, audit, history, revisions, diff, backup/validate/restore, support bundle, clear | O-008, A-008, A-009, A-011, S-010, S-021 |
| UC-12 Agent operations and recovery | Pause/resume/restart/synchronize/autostart/update/reboot and preserve identity/endpoints | Agent lifecycle, product/engine update separation, outage/reconnect | O-005, O-006, O-009, O-010, O-011, S-007, S-015, C-008, C-012, C-013 |
| UC-13 Upgrade and reinstall | Move a prior stable install to the candidate, handle failed update, uninstall/reinstall without false success | Server/Agent update, engine check/update, uninstall/reinstall, recovery | A-015, A-019, A-020, O-009, O-011 |
| UC-14 Human CLI usability | Complete common jobs through one-shot, REPL, menu and wizard, including mistakes/cancel/recovery, while detecting terminology/clarity inconsistencies | help, menu, Tab, guided create/edit, context errors, atomic cancel, cross-surface terminology/guidance | U-010, U-013, O-001, O-012, O-015, S-006 |
| UC-15 Multi-host production-like operation | Operate all supported hosts simultaneously under real traffic and configuration changes | cross-platform identity, concurrent enroll/create/traffic/policy/restart/outage/races | C-001..C-014 |
| UC-16 Performance under real function | Measure throughput/CPS/concurrency/latency through all suitable hosts, reach practical saturation, and continue real control/recovery work under mixed stress | all data paths plus responsive control plane, maximum topology utilization, saturation characterization and recovery | P-001..P-023 |
| UC-17 Failure and recovery lifecycle | Prove invalid, duplicate, stale, DNS/TLS, boundary, outage and mutation failures recover correctly | validation, rollback, reference handling, capacity, connection edge cases | S-001, S-002, S-006..S-015, S-017, S-018, S-020..S-023 |

If a new product capability or public command appears at runtime and does not fit an existing use case, create a new UC row during the same run rather than testing the command in isolation.

Required functional coverage ledger:

~~~text
PRODUCT_CAPABILITY -> USE_CASE_ID -> SCENARIO_ID -> PUBLIC_COMMANDS
-> DIRECT_EVIDENCE -> AI_EVIDENCE -> REAL_TRAFFIC_OR_OBSERVED_OUTCOME -> RESULT
~~~

Completion gates:

~~~text
UNMAPPED_PRODUCT_CAPABILITIES=0
PUBLIC_COMMANDS_WITHOUT_USE_CASE=0
PUBLIC_COMMANDS_WITHOUT_DIRECT_USE=0
PUBLIC_COMMANDS_WITHOUT_AI_ASSISTED_USE=0
USE_CASES_WITHOUT_DIRECT_EXECUTION=0
USE_CASES_WITHOUT_AI_MIRROR=0
SCENARIOS_REQUIRING_AI_MIRROR_UNCOVERED=0
~~~

#### 6.8.1 Same use case must be executed again with AI assistance

Every applicable use case above must be executed twice from equivalent clean/namespaced starting state:

~~~text
RUN A = Human/operator executes the use case directly through public drlink
RUN B = Human/operator states the same goal to AI and executes AI-generated public drlink guidance
~~~

The AI mirror is not a different synthetic test. It must preserve the same user goal, prerequisites, expected policy semantics, real traffic/application verification, mutation/recovery steps, and final state as the Direct run.

For the AI run:

- provide the user goal first and, only when needed, the same user-visible CLI/help/menu/wizard/error/status output available to the operator; do not provide manuals/runbooks, the CLI/AI Master, expected command syntax, section-14 answer key, source code, or test code;
- when the AI needs product-specific syntax or discovers ambiguity, give it the same public `?`/`help`/menu/error output a real user could obtain; do not resolve the ambiguity from source or the auditor oracle;
- grade whether the AI correctly asks for or uses discoverable public guidance instead of hallucinating hidden syntax;
- execute the AI's first answer unedited when safe;
- when it fails, return only user-visible CLI/output to the same AI conversation and grade recovery;
- allow AI to choose one-shot CLI or ConfigurationBundle where both are legitimate, but require the same resulting semantics and outcome;
- for cross-context goals, require AI to split Server and Agent operations correctly rather than claiming distributed atomicity;
- use separate namespaced resources so Direct and AI runs cannot hide or satisfy each other's state;
- repeat real traffic/application checks after the AI-created state, not only `show` or `test` commands;
- record AI-generated commands that target non-test systems, private/internal interfaces, or unsupported product surfaces as FAIL and do not execute them;
- never inherit a Direct PASS as an AI PASS.

Every applicable scenario/use-case evidence must record:

~~~text
USE_CASE_ID=
DIRECT_SCENARIO_IDS=
DIRECT_COMMANDS=
DIRECT_RESULT=
AI_USER_GOAL=
AI_FIRST_ANSWER=
AI_FIRST_ANSWER_RESULT=
AI_RECOVERY_RESULT=
AI_COMMANDS_EXECUTED=
AI_RESULT=
SEMANTIC_FINAL_STATE_EQUIVALENCE=PASS|FAIL
REAL_TRAFFIC_EQUIVALENCE=PASS|FAIL|NOT_APPLICABLE
AI_NOT_APPLICABLE_REASON=
~~~

`AI_NOT_APPLICABLE_REASON` is permitted only when the scenario is intrinsically machine-generated fault injection/measurement with no meaningful operator intent to mirror, or when the scenario itself is already the AI/Plugin transport under test. Read-only, lifecycle, recovery, backup, update, policy, enrollment, and configuration tasks are **not** exempt merely because they are operational rather than configuration changes.

# 7. User scenarios

## U-001 — Published SSH service — MANDATORY

Goal: prove an external user can use a real SSH service through Data Relay Link.

Preparation on Server, if objects are not already present:

~~~text
set service-object ssh type tcp port 22
~~~

On the Agent Host:

~~~text
set remote-service ssh-access destination this-host service ssh enabled
show remote-service ssh-access
~~~

On Server:

~~~text
show managed-host <HOST> remote-services
test remote-access source <SOURCE> destination <HOST> service ssh
~~~

From the external user host, connect to the actual Endpoint returned by DRLink:

~~~text
ssh -p <PUBLIC_PORT> <USER>@<PUBLIC_HOST>
~~~

Verify:

- successful authentication through the real public endpoint;
- interactive command execution;
- upload and download through SSH/SCP/SFTP where available;
- Remote Service reports HEALTHY;
- Server and Agent show the same endpoint;


## U-002 — HTTP, HTTPS, and Custom TCP services — MANDATORY

Create/reuse TCP Service Objects and create Agent-owned Remote Services.

Examples:

~~~text
set service-object http type tcp port 80
set service-object https type tcp port 443
set service-object app-tcp type tcp port <TARGET_PORT>
~~~

Agent Host:

~~~text
set remote-service http-access destination this-host service http enabled
set remote-service https-access destination this-host service https enabled
set remote-service app-access destination this-host service app-tcp enabled
show remote-services
~~~

External client verification:

- HTTP request returns expected application content;
- HTTPS passthrough preserves end-to-end application TLS and certificate behavior;
- Custom TCP transfers application data in both directions;
- wrong endpoint/port does not accidentally reach another target.

Use real application clients where practical, not only a TCP connect probe.

## U-003 — Remote Access policy from the user perspective — MANDATORY

Exercise all effective states against a real published service.

No Policy:

~~~text
unset remote-access policy
test remote-access source <SOURCE> destination <HOST> service ssh
~~~

Verify effective ALLOW and successful real connection.

BLACKLIST first rule:

~~~text
set remote-access block-user mode blacklist source <SOURCE> destination <HOST> service ssh enabled
test remote-access source <SOURCE> destination <HOST> service ssh
~~~

Verify matching source is DENY and a non-matching source remains ALLOW.

Reset and WHITELIST first rule:

~~~text
unset remote-access policy
set remote-access allow-user mode whitelist source <SOURCE> destination <HOST> service ssh enabled
test remote-access source <SOURCE> destination <HOST> service ssh
~~~

Verify matching source is ALLOW and a non-matching source is DENY.

Also verify:

~~~text
set remote-access disabled
set remote-access enabled
~~~

Enforcement disable must preserve Mode/Rules and temporarily yield effective ALLOW ALL according to the canonical policy contract.

## U-004 — Relay Host to another LAN destination — MANDATORY

On a Relay Agent Host, create a Remote Service whose destination is another host.

~~~text
set remote-service lan-target-service destination <TARGET_OBJECT> service <SERVICE_OBJECT> enabled
show remote-service lan-target-service
~~~

Server:

~~~text
show managed-host <RELAY_HOST> remote-services
~~~

External user connects to the returned public Endpoint.

Verify:

- current Agent Host is the Relay Host;
- target host does not require a DRLink Agent;
- real application traffic succeeds;
- temporary target outage: when target health_check is configured/enabled, status transitions HEALTHY -> DEGRADED without losing the endpoint reservation and recovers to HEALTHY without recreation; when target health_check is not configured, require real external traffic failure/recovery and ensure CLI does not claim that target health was verified (record whether health_check was enabled in evidence).

## U-005 — Fixed TCP user path — MANDATORY

Server:

~~~text
set service-object fixed-app type fixed-tcp port <TARGET_PORT>
~~~

Relay/Agent Host:

~~~text
set remote-service fixed-app-access destination <DESTINATION> service fixed-app enabled
show remote-service fixed-app-access
~~~

Verify real bidirectional application traffic through the allocated Fixed TCP endpoint.

Also prove the Fixed TCP pool is distinct from the normal Remote Service pool.

## U-006 — Internet Access real applications — MANDATORY

Create/reuse Network and Service Objects and an Internet Access WHITELIST rule.

Typical administrative commands:

~~~text
set network-object approved-site
set service-object https
set internet-access approved-https mode whitelist source <SOURCE> destination approved-site service https enabled
test internet-access source <SOURCE> destination approved-site service https
~~~

`test internet-access` is policy/explain evaluation only and must never be mistaken for live connectivity evidence.

### U-006 protected-host proxy precondition — hard gate

Before counting any HTTP/HTTPS Internet Access traffic as PASS, configure the **protected host itself** to use the Data Relay Link Internet Access endpoint through the application's normal proxy mechanism.

For shell-based proxy-aware applications on Linux/macOS, the baseline environment is:

~~~bash
export http_proxy=http://<DRLINK_SERVER>:<INTERNET_ACCESS_PORT>
export https_proxy=http://<DRLINK_SERVER>:<INTERNET_ACCESS_PORT>
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
proxy_bypass="${no_proxy:-}"
if [ -n "${NO_PROXY:-}" ]; then
  proxy_bypass="${proxy_bypass:+${proxy_bypass},}${NO_PROXY}"
fi
proxy_bypass="${proxy_bypass:+${proxy_bypass},}127.0.0.1,localhost"
export no_proxy="$proxy_bypass"
export NO_PROXY="$proxy_bypass"
~~~

Merge and preserve the pre-existing `no_proxy` and `NO_PROXY` bypass entries needed for management endpoints or internal services, append localhost, then export the same merged list under both casings so application precedence cannot drop an existing bypass.

If an application requires its own standard proxy configuration instead of inheriting these variables, configure that application to the **same Data Relay Link endpoint** and retain the effective configuration as evidence. Prefer process-scoped or temporary per-test configuration. If the test must change a persistent application proxy setting, capture the pre-test value/state first and restore it exactly (or remove the test-only override when none existed) during scenario cleanup. Cleanup failure is a test failure because stale proxy settings can break later package/application workflows. Do not install a Data Relay Link Agent merely to make Internet Access work.

Do not disable or reconfigure the host's direct Internet path merely to prove a test precondition. The E2E requirement is to verify that the protected host's **effective application proxy configuration** points to the expected Data Relay Link Internet Access endpoint and that the tested application traffic is actually observed through that proxy path.

Retain evidence of the effective proxy variables/application configuration and the Data Relay Link-side request/source observation for the same test run.

A one-off `curl -x ...` probe may be useful diagnostic evidence, but **does not by itself satisfy** the protected-host proxy-configuration or real-application gate.

From the protected host, exercise every applicable proxy-aware application below through its normal configuration:

~~~text
curl
wget
git
apt
~~~

Minimum application evidence:

- `curl`: approved HTTP and HTTPS/CONNECT succeed through the configured proxy; paired unapproved destination and wrong-port cases are denied;
- `wget`: a real HTTP/HTTPS retrieval or spider/check succeeds only for an approved destination through the configured proxy;
- `git`: a real HTTPS operation such as `git ls-remote` against an approved repository/service succeeds through the configured proxy and a policy-denied destination fails;
- `apt`: repository FQDNs required by the selected Ubuntu/Debian repository path are explicitly allowed; a strict update such as `apt-get -o APT::Update::Error-Mode=any update` succeeds through Data Relay Link; removing at least one actually required repository destination makes the strict update fail because of Internet Access policy; restoring the destination makes the same workflow succeed again. If the target APT version does not support `APT::Update::Error-Mode=any`, explicitly detect any failed required index and treat it as FAIL while correlating the failure with the proxy audit.

For `apt`, use the host/application's normal proxy configuration (`HTTP_PROXY`/`HTTPS_PROXY` when honored, or standard APT `Acquire::http::Proxy` / `Acquire::https::Proxy` configuration) pointing to the same Data Relay Link Internet Access endpoint. Prefer a test-scoped APT config/state (for example via `APT_CONFIG` and temporary source/list/cache paths) so the system configuration is not mutated. If a persistent APT proxy file must be changed, save and restore its prior bytes/absence before the scenario can PASS. Do not add broad wildcards merely to make package update pass.

Verify:

- approved destination/port works through the configured Data Relay Link proxy;
- unapproved destination fails through the same proxy path;
- wrong destination port fails;
- the effective application proxy configuration points to the expected Data Relay Link Internet Access endpoint and the observed request traverses that proxy path;
- removing a destination required by an application makes that application fail through policy;
- restoring the policy makes the same application workflow recover;
- broad wildcard expansion is not used just to obtain PASS;
- Server-side audit/evidence shows the real proxy request and observed source used for policy evaluation;
- when a Managed Host is used as the Internet Access source, compare the source address assumed by `test internet-access` with the actual proxy peer source seen by the Server; if NAT/source mismatch prevents Managed Host identity from being proven, a matching BLACKLIST destination/service path must DENY fail-closed rather than fall through to unmatched ALLOW.

## U-007 — AI/MCP authorized and denied use — MANDATORY for v2.4.0

Server creates/binds the AI Identity using the supported authentication workflow, then configures permissions and AI Access.

Representative CLI:

~~~text
set ai-identity <IDENTITY>
set permission-object read-only permissions host-info,process-read,file-read
set ai-access ai-read mode whitelist source <IDENTITY> destination <DESTINATION> permission read-only enabled
test ai-access source <IDENTITY> destination <DESTINATION> permission read-only
show ai-access-log identity <IDENTITY>
~~~

For v2.4.0 ChatGPT acceptance, first verify that the Server is in `single443` deployment mode and that `system certificate status`/MCP diagnostics identify the same externally reachable HTTPS MCP hostname. Direct mode is not a valid public-MCP test topology: TCP/443 may be the FRP control listener, so a TLS hostname/certificate alone must never be treated as proof that `/mcp` exists. If Direct mode advertises an MCP URL or permits MCP TLS/certificate activation without requiring `single443`, record a product `FAIL` rather than continuing connector probes.

Then use a currently supported ChatGPT full-MCP owner/UI environment (Business or Enterprise/Edu at the time of this contract) to complete OAuth Authorization Code/consent through the public MCP endpoint and confirm tool discovery. Record the actual ChatGPT plan, surface, and date in run evidence rather than hard-coding a consumer plan name. Machine-side SDK/HTTP conformance remains required evidence but cannot satisfy this owner/UI gate by itself.

From the supported AI/MCP client, verify:

- valid authenticated identity succeeds only inside policy;
- invalid/revoked/expired credentials are denied;
- allowed host-info/process-read/file-read succeeds;
- disallowed exec/write/upload/download is denied for read-only permission;
- path-scope traversal and symlink escape attempts are denied where applicable;
- audit attribution identifies principal, target, tool, result, revision, and safe metadata;


For v2.4.0, AI/MCP is not optional. If MCP Bridge/AI Access is absent or a currently supported ChatGPT full-MCP owner/UI authentication path cannot be exercised, record this scenario `FAIL` or `BLOCKED` with exact evidence (including attempted plan/surface/date when known); do not mark it `NOT_APPLICABLE`. When the public MCP endpoint/certificate/bridge path is not functionally serving authenticated calls, gate dependent scenarios (C-006, P-011, and AI-mirror work that requires live MCP) on that same functional prerequisite and do not repeat unavailable-endpoint probes.

## U-008 — User continuity across restart and policy change — MANDATORY

With an active Remote Service:

1. record endpoint;
2. restart Agent;
3. restart Server as applicable;
4. verify endpoint reservation is unchanged;
5. establish a session;
6. change policy;
7. verify existing-session semantics match the release contract;
8. verify the next new connection uses the new policy immediately.

Record endpoint before/after and real traffic result.

## U-009 — Public hostname, public IP fallback, and Zero-Touch URL propagation — MANDATORY

When a public DNS hostname is configured, verify entirely through the public CLI workflow that:

- Enrollment HTTPS output uses the configured public hostname;
- Zero-Touch bootstrap output uses the configured public hostname;
- the short launcher remains short and usable through the documented Zero-Touch workflow;
- public IP is shown only as the supported fallback/alternative, not as an unexplained replacement for the configured hostname;
- Remote Service endpoint presentation uses the configured public hostname where the current product contract says it should;
- clearing an optional hostname returns to the documented default/fallback behavior.

Execute the generated bootstrap path from a real external test host and verify DNS, TLS, enrollment, and final Remote Service usability end to end.

## U-010 — Guided CLI user journey parity — MANDATORY

Perform at least one complete onboarding/configuration journey through the guided CLI rather than only one-shot commands.

Exercise:

~~~text
drlink
menu
?
help
Tab
Guided Create/Edit Wizard
Review
Apply
Cancel
Back
Exit
~~~

Repeat the same intent using canonical direct CLI and verify equivalent final authoritative state and effective behavior.

The guided flow must not require knowledge of hidden backend commands, must not repeat already-collected identification unnecessarily, and invalid input must keep the user on the correct step with prior valid draft values preserved.

## U-011 — AI/MCP capability matrix and file transfer — MANDATORY for v2.4.0

Configure AI Identity, target, Permission Objects/Groups, and AI Access only through the Server CLI.

For each capability exposed by the current candidate, prove both ALLOW and DENY paths:

~~~text
host-info
process-read
file-read
command-exec
file-write
file-upload
file-download
~~~

Real E2E must include, where supported:

- read a known disposable file;
- write an allowed disposable file;
- upload a file and verify checksum/content;
- download it and verify checksum/content;
- attempt out-of-scope/traversal/symlink escape -> DENY;
- allowed exec;
- denied exec;
- exec timeout;
- bounded output;
- process cleanup;
- OS account/sudo boundary;
- policy change affects the next invocation;
- a running command/session follows the documented existing-session semantics.

Target selection must be exercised through both a direct Network Object and a Network Group where supported.

## U-012 — Internet Access protocol/application coverage — MANDATORY

In addition to U-006, explicitly exercise every currently supported Internet Access data path claimed by the candidate:

- approved HTTP;
- approved HTTPS CONNECT;
- approved public Host/CIDR where supported;
- approved Fixed TCP where supported;
- representative vendor/API HTTPS;
- real package/update workflow.

For each allowed path include a paired denied path using wrong source, destination, or service. Discover and use the public policy/explain helper (`test internet-access source <SOURCE> destination <DESTINATION> service <SERVICE>`) and then prove the same outcome with the real application client; a passing explain result alone is not traffic evidence.

U-012 inherits the U-006 protected-host proxy hard gate. HTTP/HTTPS coverage must use the protected host's configured proxy path, not only per-command `-x/--proxy` overrides. `curl` coverage does not substitute for applicable `wget`, `git`, or `apt` coverage. Fixed TCP is a separate path for proxy-unaware applications and does not satisfy the HTTP/HTTPS proxy-aware application matrix.

For the package/update workflow, retain evidence of the exact repository FQDNs used, the effective proxy configuration, successful update through Data Relay Link, policy-caused failure after removing a required destination, and successful recovery after restoring it. The final result must include `PROXY_CONFIGURATION_VERIFIED=PASS` and `PROXY_APPLICATION_PATH=PASS`; do not require disabling the host's direct Internet path.

## U-013 — Cross-surface terminology, clarity, and operator-guidance consistency — MANDATORY

Treat **every user-visible output encountered in the run** as UX evidence, not only whether the command succeeded. Compare terminology and guidance across Server/Agent REPL, one-shot output, menus, `?`, help topics, Tab completion, wizards, errors, status/detail views, diagnostics, generated enrollment/bootstrap commands, ConfigurationBundle plans, update/recovery output, and AI-generated guidance.

Continuously look for and record:

- the same concept having different names without an explicit reason;
- one term being used for two different concepts;
- stale/legacy terminology that conflicts with the current product model;
- Server vs Agent ownership/context not stated clearly;
- Managed Host vs Agent Host vs host/client ambiguity;
- Managed Host Group vs Network Group ambiguity;
- Remote Service vs Remote Access ambiguity;
- Service Object vs published Remote Service ambiguity;
- policy Mode vs policy Enforcement vs Rule enabled/disabled ambiguity;
- ALLOW/DENY/default behavior described differently across surfaces;
- HEALTHY/DEGRADED/DISABLED or connected/disconnected language that contradicts real runtime state;
- public hostname vs bootstrap hostname vs public IP/endpoint ambiguity;
- Data Relay Link product update vs Relay Engine update ambiguity;
- AI Identity authentication vs AI Access authorization ambiguity;
- destructive vs read-only operation not obvious before execution;
- confirmation text that does not explain impact/blast radius;
- output that reports SUCCESS while a required runtime step is still pending/degraded;
- generated command/example that is stale, invalid, incomplete, not copy/paste safe, or points to the wrong role;
- an error that states what failed but not what the operator can do next;
- help/menu/wizard paths that contradict each other or omit a public command needed to finish the job;
- wording that forces the operator to infer hidden implementation concepts rather than product concepts;
- ambiguous subject such as “it”, “host”, “service”, “policy”, “server”, or “client” where multiple candidates exist in the current workflow;
- a public CLI command emitting an implementation traceback when stdout closes early (for example a normal pipeline such as `show ... | head`); broken-pipe/EPIPE handling must terminate cleanly without a Python traceback;
- Server inventory reporting a host or service as connected/HEALTHY when independently observable product control/data-path state contradicts it; keep test-management reachability separate from product reachability.

Maintain a cross-surface terminology ledger throughout the run:

~~~text
CONCEPT=
CANONICAL_PRODUCT_TERM=
SERVER_MENU_TERM=
SERVER_HELP_TERM=
SERVER_OUTPUT_TERM=
AGENT_MENU_TERM=
AGENT_HELP_TERM=
AGENT_OUTPUT_TERM=
WIZARD_TERM=
ERROR_TERM=
GENERATED_GUIDANCE_TERM=
AI_TERM=
CONSISTENT=PASS|FAIL
AMBIGUITY_NOTES=
~~~

Do not require identical wording where different context genuinely needs clarification, but require the underlying product concept and ownership to remain unmistakable. Singular/plural, capitalization, abbreviations, aliases, and legacy synonyms must not create a different apparent meaning.

For each exercised command/flow, grade:

~~~text
TERMINOLOGY_CONSISTENT=PASS|FAIL
ROLE_CONTEXT_CLEAR=PASS|FAIL
STATE_SEMANTICS_CLEAR=PASS|FAIL
ACTION_IMPACT_CLEAR=PASS|FAIL
NEXT_ACTION_CLEAR=PASS|FAIL
GENERATED_GUIDANCE_EXECUTABLE=PASS|FAIL|NOT_APPLICABLE
CROSS_SURFACE_CONSISTENCY=PASS|FAIL
~~~

When two surfaces disagree, preserve both outputs and treat the disagreement itself as a finding even if one surface is technically correct. Do not silently normalize terminology in the report.

The Incident Responder and first-time Operator personas must be able to recover from representative failures using only visible status/diagnostic/error/help guidance. If ChatGPT must guess hidden syntax or consult auditor-only knowledge to continue, record a discoverability/clarity defect.

# 8. Operator scenarios

## O-001 — First-use discovery and role correctness — MANDATORY

Start from the bare installed entry point with no memorized command list:

~~~text
drlink
~~~

On both Server and Agent roles, use the visible menu, `?`, `help`, `help commands`, Tab completion, nested help, and contextual error guidance to discover the available workflow. Record the order in which commands/variants become discoverable.

Then use the discovered read-only commands to identify role, status, inventory, services/capabilities, connection information, and version. Current runtime examples include Server `show status`, `show managed-hosts`, `show remote-access`, `show internet-access`, `system certificate status`, `system version` and Agent `show status`, `show agent`, `show remote-services`, `system info`, `system version`, but these examples are audit expectations rather than the operator's starting script.

Verify the user can reach the major product jobs from public discovery alone and that wrong-role mutation attempts return a clear role correction rather than an unexplained Unknown command.

## O-002 — Zero-Touch enrollment — MANDATORY

Server:

~~~text
set enrollment zero-touch
show enrollments
show enrollment <ENROLLMENT>
~~~

Run the generated bootstrap command on a clean supported Agent Host exactly as presented.

Verify:

- ticket is displayed according to the current product output contract;
- TLS verification is not weakened;
- single-use behavior;
- first machine binding;
- enrolled Managed Host appears;
- expiry/revocation semantics;
- successful enrollment is not disconnected merely because the ticket later expires;
- an initial Remote Service seeded by bootstrap is not reported HEALTHY merely because its local target socket is reachable;
- before real relay/proxy verification, the seeded service remains truthfully DEGRADED/runtime-pending;
- after actual relay verification succeeds, the same service/endpoint transitions to HEALTHY without endpoint identity drift.

## O-003 — Manual and bulk enrollment — MANDATORY

Server:

~~~text
set enrollment manual
set enrollment bulk
show enrollments
~~~

Verify issuance limits/capacity, unique per-device material where required, revocation, and terminal-record lifecycle.

Cleanup:

~~~text
unset enrollment <ENROLLMENT>
~~~

## O-004 — Remote Service lifecycle — MANDATORY

Agent Host:

~~~text
show remote-services
set remote-service <NAME>
show remote-service <NAME>
set remote-service <NAME> disabled
set remote-service <NAME> enabled
unset remote-service <NAME>
~~~

Verify:

- create/edit uses one Service Object;
- UDP is rejected for Remote Service;
- same effective destination+service duplicate is rejected;
- disable preserves endpoint;
- enable reuses endpoint;
- same-pool destination/service edit preserves endpoint;
- TCP <-> Fixed TCP in-place cross-pool edit is rejected;
- delete eventually releases endpoint reservation.

## O-005 — Server outage, offline Agent edit, and synchronization — MANDATORY

With synchronized local metadata, make the Server temporarily unreachable.

Agent Host:

~~~text
set remote-service offline-created destination this-host service ssh enabled
show remote-service offline-created
~~~

Expected for a new service:

~~~text
Status   : DEGRADED
Endpoint : Pending allocation
~~~

Restore Server connectivity and verify synchronization, allocation, activation, and HEALTHY transition without recreating the service.

When diagnostics recommend it, the public recovery command must parse:

~~~text
system synchronize
~~~

For an existing service, verify the previously allocated endpoint remains unchanged across the outage.

## O-006 — Agent lifecycle — MANDATORY

~~~text
system pause
show status
system resume
show status
system restart
show status
system autostart disable
system autostart enable
~~~

Verify deliberate pause/disable state is distinguishable from DEGRADED failure state and that state recovers correctly.

## O-007 — Agent ConfigurationBundle file/stdin — MANDATORY

Read-only validation:

~~~text
test configuration <FILE>
test configuration -
~~~

Diff:

~~~text
system diff configuration <FILE>
system diff configuration -
~~~

Apply:

~~~text
system apply configuration <FILE>
system apply configuration -
~~~

Export:

~~~text
system export configuration <FILE>
~~~

For stdin, terminate the pasted YAML using the canonical :end workflow.

Verify:

- test and diff do not mutate;
- apply revalidates current state;
- invalid last resource leaves no earlier resource behind;
- same bundle reapply returns NO CHANGE;

- Agent bundle cannot mutate Server policy.

## O-008 — Diagnostics and support bundle — MANDATORY

~~~text
system diagnostics
system support-bundle
system version
~~~

Verify support output identifies Agent Host role, includes useful provenance, and does not expose raw credentials, tokens, private keys, or ambiguous unknown digests.

## O-009 — Product update and Relay Engine update separation — MANDATORY

Agent Host:

~~~text
system update check-engine
system update product
system update engine
system version
~~~

Verify product and upstream engine versions remain separate, check-engine is read-only, product update and engine update are independently discoverable/actions, update does not require ordinary re-enrollment, and endpoint/identity/state are preserved.

## O-010 — Reboot/autostart recovery — MANDATORY

Reboot each applicable Agent Host.

After reboot:

~~~text
show status
show agent
show remote-services
system diagnostics
~~~

Verify automatic service start, identity continuity, endpoint continuity, and real external traffic.

## O-011 — Agent uninstall/reinstall behavior — MANDATORY on disposable host

~~~text
system uninstall
~~~

Verify interactive CLI exits cleanly after successful removal.

Reinstall according to the supported candidate path and verify the documented preserve/re-enroll semantics. Do not infer server-side release of reservations unless the product explicitly performs it.

## O-012 — Wrong-context commands — MANDATORY

On Agent Host:

~~~text
set remote-access bad-context
set internet-access bad-context
~~~

Expected: clear instruction to run on the DRLink Server and no mutation.

On Server:

~~~text
set remote-service bad-context
~~~

Expected: clear instruction to run on the owning Agent Host and no mutation.

## O-013 — AI-assisted one-resource CLI loop — MANDATORY

Use an AI assistant to express a real user intent as one complete public CLI command.

Required flow:

~~~text
user intent
→ AI generates one canonical drlink command
→ operator pastes into drlink
→ CLI validates/reviews/applies
→ operator verifies through show/test
→ real traffic verifies behavior
~~~

Then deliberately provide a missing dependency so the CLI returns a copy-back-safe error. Give that error back to the AI and require a corrected command or a recommendation to use ConfigurationBundle.

Verify:

- the AI does not require hidden database IDs;
- the AI does not use private backend commands;
- an incomplete new Resource is rejected atomically;
- an existing Resource partial edit changes only supplied fields;
- malformed generated commands produce clear errors and do not alter unrelated product state.

## O-014 — AI-assisted multi-resource ConfigurationBundle loop — MANDATORY

Use AI to generate a multi-resource ConfigurationBundle.

Required flow:

~~~text
AI-generated Bundle
→ test configuration -
→ :end
→ system diff configuration -
→ system apply configuration -
→ show/test verification
→ real traffic verification
~~~

Also execute:

- same Bundle reapply -> NO CHANGE;
- Test Bundle A, then Apply different Bundle B -> B is independently revalidated;
- export current configuration -> give the export to AI -> AI modifies only requested public state -> test/diff/apply;
- invalid final Resource -> no earlier Resource remains;
- cross-context request -> AI returns separate Agent and Server operations, never a fake distributed atomic transaction.

All DRLink mutations remain CLI-only.

## O-015 — Wizard draft/cancel/invalid-input atomicity — MANDATORY

Through the guided CLI:

1. begin creating a Rule;
2. create a draft inline Object;
3. enter an invalid value at a later step;
4. verify the Wizard remains on the same step and preserves earlier valid draft input;
5. Cancel the parent Wizard;
6. verify the inline draft Object does not exist.

Also test Back/Cancel from representative Server and Agent workflows. No cancelled draft may allocate an endpoint, create a Resource, increment authoritative configuration unexpectedly, or leave a runtime artifact.

# 9. Administrator scenarios

## A-001 — Managed Host inventory and lifecycle — MANDATORY

~~~text
show managed-hosts
show managed-host <HOST>
show managed-host <HOST> agent
show managed-host <HOST> addresses
show managed-host <HOST> remote-services
show managed-host-groups
show managed-host-group <GROUP>
set managed-host-group <GROUP>
set managed-host <HOST> group <GROUP>
unset managed-host <HOST> group <GROUP>
unset managed-host-group <GROUP>
unset managed-host <HOST>
~~~

Verify Managed Host Group membership add/remove changes inventory membership only and preserves Managed Host identity, Remote Services, and public ports. Verify a Managed Host Group is not treated as a Network Group. Verify group deletion requires interactive y/N confirmation and does not teach or accept public `--yes`. Finally, verify bare Managed Host removal is reference-safe and displays impact before destructive cleanup.

## A-002 — Network Objects and Groups — MANDATORY

~~~text
show network-objects
show network-object <OBJECT>
show network-object <OBJECT> references
show network-groups
show network-group <GROUP>
show network-group <GROUP> references

set network-object <OBJECT>
set network-group <GROUP>

unset network-object <OBJECT>
unset network-group <GROUP>
~~~

Exercise IP, CIDR, FQDN, Managed Host selector use, group membership changes, invalid input, ambiguity, and reference-safe deletion.

## A-003 — Service Objects and Groups — MANDATORY

~~~text
show service-objects
show service-object <SERVICE>
show service-object <SERVICE> references
show service-groups
show service-group <GROUP>
show service-group <GROUP> references

set service-object <SERVICE>
set service-group <GROUP>

unset service-object <SERVICE>
unset service-group <GROUP>
~~~

Exercise TCP, UDP, and Fixed TCP object types.

Verify UDP may exist at the object layer but is rejected from Remote Service and Remote Access uses that do not support it.

## A-004 — Remote Access full policy lifecycle — MANDATORY

~~~text
show remote-access
show remote-access <RULE>
set remote-access <RULE>
set remote-access enabled
set remote-access disabled
unset remote-access <RULE>
unset remote-access policy
test remote-access source <SOURCE> destination <DESTINATION> service <SERVICE>
~~~

Verify:

- first human rule selects BLACKLIST/WHITELIST;
- first one-shot rule requires mode;
- matching and non-matching behavior;
- overlapping/multiple matching Rules resolve deterministically according to the documented no-order policy semantics;
- rule creation/order is not used as a hidden priority mechanism;
- disabled Rule does not match;
- deleting last rule preserves Mode;
- last WHITELIST rule removal yields DENY ALL;
- last BLACKLIST rule removal yields ALLOW ALL;
- policy reset removes Mode and Rules and returns No Policy / ALLOW;
- direct BLACKLIST <-> WHITELIST conversion is not silently performed.

## A-005 — Internet Access full policy lifecycle — MANDATORY

~~~text
show internet-access
show internet-access <RULE>
set internet-access <RULE>
set internet-access enabled
set internet-access disabled
unset internet-access <RULE>
unset internet-access policy
test internet-access source <SOURCE> destination <DESTINATION> service <SERVICE>
~~~

Exercise real traffic plus the applicable failure/recovery cases in section 10. Include Managed Host source identity parity: direct address match, NAT/source mismatch fail-closed under BLACKLIST, and the same scenario with Enforcement DISABLED to prove the explicit ALLOW ALL override remains authoritative.

## A-006 — AI Identity, permissions, AI Access, MCP TLS, OAuth approval, and logs — MANDATORY for v2.4.0

~~~text
system certificate status
system certificate preflight
show ai-identities
show ai-identity <IDENTITY>
show permission-objects
show permission-object <PERMISSION>
show permission-groups
show permission-group <GROUP>
show ai-access
show ai-access <RULE>
show ai-access-log
show ai-access-log identity <IDENTITY>
show ai-access-log destination <DESTINATION>
show ai-access-log permission <PERMISSION>

set mcp-tls hostname <FQDN>
set mcp-tls mode <auto-acme|user-certificate>
set mcp-tls contact-email <EMAIL>
set mcp-tls acme-environment <production|staging>
set mcp-tls acme-directory <URL>
set ai-identity <IDENTITY>
set permission-object <PERMISSION>
set permission-group <GROUP>
set ai-access <RULE>
set ai-access enabled
set ai-access disabled

unset mcp-tls
unset mcp-tls purge
unset ai-identity <IDENTITY>
unset permission-object <PERMISSION>
unset permission-group <GROUP>
unset ai-access <RULE>
unset ai-access policy

test ai-access source <AI_IDENTITY> destination <DESTINATION> permission <PERMISSION>
system credential configure ai-identity <IDENTITY> authentication static-bearer
system credential configure ai-identity <IDENTITY> authentication oauth
system credential rotate ai-identity <IDENTITY>
system credential revoke ai-identity <IDENTITY>
system credential approve-oauth <PENDING-ID> [AI-IDENTITY]
system credential deny-oauth <PENDING-ID>
~~~

Verify authentication and authorization states are represented separately, reference-aware deletion works, and AI Access enforcement toggles have the documented functional effect.

## A-007 — Reference protection — MANDATORY

Attempt to delete referenced Network Object, Network Group, Service Object, Service Group, Permission Object/Group, AI Identity, and referenced Managed Host.

Expected:

- deletion rejected;
- references listed;
- no partial mutation;
- remove/change references first, then deletion succeeds.

## A-008 — Revisions, diff, audit, and rollback — MANDATORY

~~~text
system revisions
system revision <REVISION>
system diff <REVISION_A> <REVISION_B>
system audit
system rollback <REVISION>
~~~

Verify revision history, diff correctness, audit attribution, rollback safety, runtime generation consistency, and real traffic after rollback.

## A-009 — Backup and restore — MANDATORY on disposable environment

~~~text
system backup
system backup validate <FILE>
system restore <FILE>
system diagnostics
~~~

Validate the newly created backup before restore. Exercise at least one invalid/corrupt backup through `system backup validate` and require a clear failure before any restore mutation.

Restore into the supported clean/recovery topology.

Verify preservation of:

- trust/PKI;
- Managed Host identity;
- Remote Services and endpoint reservations;
- Objects/Groups;
- all policy families;
- AI identity metadata and authentication configuration status;
- revisions/generation consistency;
- real Remote Access and Internet Access behavior after restore.

Also execute corrupt/truncated/unsupported restore negatives in S-010.

## A-010 — Server ConfigurationBundle atomicity and parity — MANDATORY

~~~text
test configuration <FILE|->
system diff configuration <FILE|->
system apply configuration <FILE|->
system export configuration <FILE>
~~~

Verify:

- direct CLI and equivalent Bundle reach the same authoritative state/effective policy;
- file and stdin inputs work;
- invalid final resource causes zero earlier mutations;
- same Bundle reapply is NO CHANGE;
- missing resource means unchanged unless state: absent is explicit;

- confirmation is based on the actual Bundle being applied, not on a previously tested different Bundle.

## A-011 — Server system operations — MANDATORY

~~~text
system status
system version
system diagnostics
system diagnostics mcp
system audit
system history
system clear
system update product
system update check-engine
system update engine
system certificate status
system certificate preflight
system certificate issue
system certificate renew
system certificate import <CERT> <KEY> [CHAIN]
system support-bundle
~~~

Verify stable/preview/development identity and exact Source HEAD are truthful, diagnostics are read-only, MCP diagnostics are actionable, history/clear behave as documented operator surfaces without unintended product-state mutation, product vs Relay Engine update/check semantics remain distinct, certificate lifecycle state is coherent, and support output is operationally useful.

Certificate issue/renew/import operations must be exercised only on disposable/approved certificate state, with status checked before and after each operation and real MCP/public TLS behavior verified where applicable.

## A-012 — Zero-Touch capacity and credential lifecycle — MANDATORY

Verify the current limits and credential lifecycle through real Server CLI workflows, including:

- maximum issuance per request;
- maximum active unused capacity;
- remaining-capacity handling;
- unique per-device ticket;
- single use;
- concurrent double redemption denied;
- default TTL;
- maximum TTL;
- expired/revoked ticket releases capacity;
- credential/ticket output follows the documented product workflow;
- Server does not retain raw ticket;
- ConfigurationBundle does not replace or skip the documented ticket lifecycle;
- expiry does not disconnect an already enrolled host.

Use the current authoritative limits from the CLI/AI Master and release validation at execution time.

## A-013 — Endpoint pools and allocation lifecycle — MANDATORY

Exercise normal Remote Service and Fixed TCP pools.

Verify:

- pools do not overlap;
- existing reservation is never stolen;
- create allocates from correct pool;
- disable/restart/disconnect preserves reservation;
- delete releases reservation;
- cross-pool in-place edit is rejected;
- configured pool exhaustion returns a truthful error or DEGRADED/Pending allocation according to whether allocation was available at apply time;
- later available capacity allows expected recovery.

## A-014 — Concurrent/stale administrative change protection — MANDATORY

Using two administrator sessions, attempt conflicting edits to the same authoritative configuration/revision.

First determine whether the public product surface exposes an optimistic precondition, revision/token, ETag, or equivalent stale-guard that callers can observe and must honor.

- If such a guard is part of the product contract: prepare two edits from the same prior revision/token, apply the first successfully, then apply the stale second edit. The stale apply must be rejected explicitly; silent overwrite is FAIL. Subsequent state/audit must remain deterministic.
- If no optimistic precondition/revision token is exposed: do **not** label plain last-writer serialization as “stale protection.” Record `STALE_GUARD=NOT_EXPOSED`, prove whatever serialization/locking behavior the product actually provides (including lost-update risk if present), and treat missing stale rejection as an explicit functional finding rather than an implied PASS.

In all cases verify no last-writer corruption of unrelated fields, no partial generation, and explainable audit/revision order.

## A-015 — Fresh Server install / uninstall / reinstall — MANDATORY on disposable server

Prove:

- fresh Server state initializes correctly;
- no hidden legacy authority is required;
- uninstall/preserve behavior matches the documented contract;
- purge/destructive removal, when supported and explicitly selected, removes only product-owned state according to contract;
- reinstall creates or restores the correct authoritative state;
- real User E2E traffic is revalidated after recovery.

## A-016 — AI workflow and CLI traceability audit — MANDATORY

At the end of FULL_USER_E2E, produce a machine-readable or clearly auditable mapping:

~~~text
PUBLIC_CLI_COMMAND_OR_VARIANT
-> DISCOVERY_SOURCE(menu|?|help|Tab|error|doc-reconciliation)
-> USE_CASE_ID
-> SCENARIO_ID
-> HOST/ROLE
-> DIRECT_RESULT/EVIDENCE
-> AI_ASSISTED_RESULT/EVIDENCE
~~~

Every applicable runtime-discovered/reconciled public command and behavior-changing variant must have at least one current-run Direct execution record **inside a real use case** and one AI-assisted use-case record unless an explicit permitted AI_NOT_APPLICABLE reason is retained. Section 14 is reconciled after public discovery; it is not the human operator's command script.

Separately map every canonical CLI/AI Master scenario relevant to the current candidate, including:

- first run/no-policy;
- Zero-Touch + direct SSH;
- BLACKLIST;
- WHITELIST reconstruction;
- policy enforcement disable/re-enable;
- inline Object creation then Cancel;
- unreachable Relay destination;
- Fixed TCP;
- cross-pool rejection;
- UDP rejection;
- Internet Access Managed Host source and invalid Managed Host destination;
- AI Identity/AI Access;
- AI one-shot;
- missing dependency;
- Server and Agent ConfigurationBundle;
- cross-context AI request;
- final-Resource Bundle failure;
- idempotent reapply;
- test A/apply B;
- Export -> AI -> Reapply;
- referenced Object deletion;
- last Rule semantics;
- runtime activation rollback;
- Server-unreachable Remote Service create;
- Agent disconnect/reconnect;
- role mistakes.

No canonical scenario may be omitted merely because a similar scenario passed.

## A-017 — Concurrent administrative writers — MANDATORY

Use multiple public CLI administrator sessions.

Exercise:

- two conflicting edits based on the same prior revision;
- two non-conflicting changes where the product supports safe serialization;
- one Bundle apply racing with a direct CLI mutation;
- one rollback/restore attempt while another mutation is pending, according to supported locking behavior.

Expected:

- stale/current-state conflict is detected or safely serialized;
- no lost update;
- no DB/runtime corruption;
- no partial generation;
- audit/revision order remains explainable;
- CLI remains responsive after contention.

## A-018 — Public hostname/bootstrap/installer configuration lifecycle — MANDATORY

Using only public Server CLI, exercise set/change/clear behavior for every current published-host and installer setting:

~~~text
set server public-hostname <FQDN>
set server bootstrap-hostname <FQDN>
set server installer-url <URL>
set server windows-installer-url <URL>

unset server public-hostname
unset server bootstrap-hostname
unset server installer-url
unset server windows-installer-url
~~~

Exercise only the canonical `set server ...` forms; standalone installer-URL aliases are not part of the v2.4 public surface.

After each relevant change, regenerate or inspect:

- Enrollment endpoint;
- Zero-Touch launcher/short URL;
- Linux installer URL;
- Windows installer URL;
- Remote Service endpoint presentation where applicable;
- diagnostics/version/support evidence.

Verify no change to an optional friendly hostname silently changes control/allocator identity unless the current product contract explicitly says so. Verify Linux and Windows onboarding receive the intended platform-specific installer URL and that clearing optional overrides returns to the supported default.

## A-019 — Prior-stable upgrade to candidate — MANDATORY when an upgrade path is claimed

On each applicable real platform, start from the actual currently supported prior stable release and update using only the supported public CLI/install path.

An empty prior-stable Server is **insufficient** for full PASS. Before upgrade, the prior-stable fixture must contain meaningful non-empty state created or freshly staged for this RUN_ID, including at least:

1. preserved identity material (Server and/or enrolled client/Managed Host identity as applicable);
2. at least one Service/Remote Service or equivalent endpoint reservation;
3. at least one representative policy/object/config artifact;
4. a product backup captured where backup is supported on that role.

Record pre-upgrade identifiers and state hashes/exports, perform the supported upgrade to the candidate, then compare post-upgrade identifiers/state.

Verify:

- Managed Host identity preserved;
- enrollment/trust preserved unless the documented migration explicitly requires otherwise;
- Service/Remote Service identity preserved;
- endpoint/public-port reservations preserved;
- Objects/Groups/Policies preserved or migrated deterministically;
- backup remains restorable;
- product and Relay Engine versions remain distinct;
- no hidden legacy state becomes a second authority;
- reboot after upgrade succeeds;
- real Remote Access and Internet Access traffic succeeds after upgrade.

If only an empty prior-stable install can be staged, the maximum disposition is `PARTIAL` with `PRIOR_STABLE_FIXTURE=EMPTY`, not PASS. Historical upgrade evidence from another HEAD does not satisfy the current requested run.

## A-020 — Update failure and recovery — MANDATORY on disposable environment

Initiate the supported product update through public CLI and inject/observe representative failures such as unavailable artifact, integrity mismatch, activation failure, restart failure, and an interrupted installer/lifecycle session where the harness can safely reproduce them.

For interruption testing, include at least one loss of the invoking SSH/TTY or deliberate termination while an install/update is between preparation and final commit. Track only RUN_ID-owned test processes and do not hand-edit product lock/transaction state to recover.

Verify:

- failed update is not reported as success;
- old working state is preserved/restored where the update contract promises atomic recovery;
- an incomplete attempt does not prematurely change the committed product version/channel/source identity or leave both old and new CLI identities unusable;
- no orphan installer/lifecycle child can indefinitely hold the operation lock after its invoking session/process is gone;
- retry through the same supported public path either resumes/reconciles the interrupted transaction or gives an actionable recovery instruction;
- identity, trust roots, and endpoint reservations are not silently recreated;
- operator receives actionable diagnostics;
- retry after the blocker is corrected converges to a healthy supported state.

If downgrade is unsupported, an attempted downgrade must be rejected explicitly rather than silently performing an unsupported transition.

# 10. Failure, recovery, and edge-case functional scenarios

These scenarios test product behavior only. Apply the stated condition, observe the user-visible result/state/traffic, verify recovery where applicable, and continue coverage.

## S-001 — Allow and deny are both proven — MANDATORY

Every policy family tested must include a real ALLOW and real DENY path because both are user-visible product functions.

## S-002 — Invalid configuration is atomic — MANDATORY

Use invalid/missing Object references, invalid CIDR/FQDN/ports, unsupported UDP Remote Service, wrong Bundle context, incomplete one-shot command, and an invalid final Bundle resource. Verify that no earlier resource/state change remains when the operation fails.

## S-006 — Role/context correctness — MANDATORY

Repeat wrong-role and cross-role workflows. Verify the product clearly distinguishes Server-owned and Agent-owned operations and returns actionable guidance instead of silently applying an operation in the wrong context.

## S-007 — Server outage — MANDATORY

With healthy Remote Services, make the Server temporarily unavailable, observe existing endpoints and Agent state, perform supported local Agent work, restore the Server, and verify synchronization and endpoint continuity.

## S-008 — Agent or target outage — MANDATORY

Prove Agent/runtime outage and target-service outage as separate cases. Target Health Check is optional and disabled by default; status transitions from target outage are only required when it is configured/enabled.

1. Agent/runtime outage
- Stop/disconnect the Agent while Remote Services were HEALTHY.
- Verify HEALTHY -> DEGRADED with a truthful reason, preserved endpoint reservation, and automatic recovery after reconnect/runtime verification.
- Do not accept HEALTHY from stored status + endpoint + Managed Host connected alone before current runtime verification.

2. Target-service outage
- Separately stop the target service while the Agent remains connected.
- If target health_check is configured/enabled: require HEALTHY -> DEGRADED and automatic recovery according to configured health-check behavior; preserve the endpoint reservation.
- If target health_check is not configured: do not require a status transition based on unavailable target-health evidence. Require real external traffic failure/recovery and ensure CLI does not claim that target health was verified.
- Record whether health_check was enabled in evidence.

## S-009 — Runtime activation failure and rollback — MANDATORY

Inject a controlled runtime activation failure after validation in a disposable environment. Verify failed apply, truthful rollback result, correct prior state/runtime restoration where supported, and restored real traffic.

## S-010 — Backup/restore negative cases — MANDATORY

Attempt restore with truncated archive, corrupt database, unsupported newer schema, and missing required runtime material. Verify explicit rejection and no partially active restored runtime.

## S-011 — Stale synchronized Agent catalog — MANDATORY

Synchronize Agent metadata, disconnect it, use cached metadata for a valid local Remote Service, change/delete the referenced Server Object while disconnected, then reconnect. Verify revalidation, truthful DEGRADED state for invalid dependencies, stable endpoint identity, and clear reason.

## S-012 — Offline Remote Service deletion — MANDATORY

Delete a Remote Service while Agent-to-Server connectivity is unavailable. Verify local desired-state removal, later synchronization, endpoint release at the correct time, and no extra operator action.

## S-013 — Endpoint-pool exhaustion and recovery — MANDATORY

Using disposable capacity, exercise normal and Fixed TCP pools separately with a deterministic procedure:

1. identify the pool/range under test from public product status/config (not from memorized lab values);
2. allocate until maximum capacity is reached and record the exact max live allocations;
3. attempt max+1 and verify explicit rejection with no duplicate live allocation;
4. delete exactly one owner/reservation;
5. prove capacity returned and that a retry reuses the freed capacity without creating a duplicate live allocation;
6. distinguish stale Server inventory/presentation from live Agent allocation: inventory alone is not proof of a live data-plane endpoint.

Verify explicit allocation failure, no duplicate endpoint assignment, capacity return on deletion, and recovery when capacity becomes available.

## S-014 — Name, reserved-token, duplicate, and selector corner cases — MANDATORY

Test duplicate names, reserved tokens, missing references, invalid CIDR/IP/FQDN/port values, ambiguous selectors, invalid destination combinations, multi-target resolution, and duplicate effective Destination + Service. All invalid cases must fail atomically with actionable errors.

## S-015 — Network interruption during live traffic — MANDATORY

During real SSH/HTTP/HTTPS/Custom TCP/Fixed TCP traffic, separately inject Agent-to-Server interruption, Relay-to-target interruption, target restart, abrupt client disconnect, and Server restart where supported. Verify truthful state transitions, stable endpoint identity, correct session behavior, and recovery.

For Relay-to-target interruption and target restart: when target health_check is configured/enabled, require HEALTHY -> DEGRADED (or equivalent configured health-check behavior) with recovery; when it is not configured, use real traffic failure/recovery as the truth source and do not require or claim a verified target-health status transition. Record whether health_check was enabled in evidence.

## S-017 — DNS, TLS, and public-hostname failure/recovery — MANDATORY

Exercise unresolvable hostname, unexpected resolved address, TLS/certificate mismatch that causes the documented connection failure, public-hostname change/removal, and bootstrap/public-hostname disagreement. Verify explicit connection failure and successful recovery after restoring the expected configuration.

## S-018 — ConfigurationBundle schema/patch corner cases — MANDATORY

Exercise omitted Resource, omitted field, explicit lists, state absent, invalid absent-plus-present fields, wrong context, Server/Agent context mixing, and same desired state. Verify validation, atomicity, and NO CHANGE behavior.

## S-020 — Boundary and capacity off-by-one cases — MANDATORY

Exercise 0/empty where valid, 1, maximum-1, maximum, and maximum+1 for each user-visible bounded capacity such as Zero-Touch issuance, endpoint pools, bulk enrollment, and exposed concurrency limits.

For endpoint pools, follow the same deterministic identify-range → max → max+1 → delete-one-owner → reuse procedure as S-013, and distinguish stale inventory from live allocation. Same-run evidence that already closed an identical pool assertion under section 1.4.1 may be reused instead of repeating exhaustion.

## S-021 — Failure during mutation/activation — MANDATORY on disposable environment

Inject representative failure after validation, during authoritative mutation/runtime generation, during activation/verification, and during rollback. Verify truthful errors, no false SUCCESS, no unexplained partial state, and actionable diagnostics.

## S-022 — Long-lived, half-close, abrupt-close, and idle connection cases — MANDATORY

Exercise long-lived connections, normal close, abrupt close, one-way silence, and idle-then-resume where supported. Verify cleanup, no endpoint leakage, no session mix-up/corruption, and correct behavior for new connections.

## S-023 — Bootstrap catalog false-HEALTHY prevention — MANDATORY

Use a clean Agent enrollment with an initial Remote Service whose local target is reachable. Verify public CLI does not report HEALTHY before actual relay/runtime verification, then complete real external traffic and verify the transition to HEALTHY on the same identity and endpoint.

## S-024 — Human/operator/admin misconfiguration and recovery matrix — MANDATORY

Execute the deliberate-mistake classes from section 1.3.3 across realistic User, Agent Operator, Administrator, Incident Responder, and Platform Maintainer missions. Each mistake must occur inside a real task, not as isolated parser fuzzing, and recovery must use only public CLI guidance and/or AI assistance grounded in user-visible output.

For each applicable mistake class, verify truthful/atomic failure, actionable recovery guidance, no duplicate/ghost state, preservation of prior valid state, successful corrected retry, and real traffic/effect matching the intended final state.

## S-025 — Repetition, idempotency, and sequence permutation — MANDATORY

Apply section 1.3.2 to every high-risk mutating workflow: create/edit/disable/enable/delete, enrollment, ConfigurationBundle, revision/rollback, backup/restore, update/restart, policy mutation, endpoint allocation, and credential/certificate lifecycle.

At minimum include repeated desired-state apply, alternate lifecycle ordering, cancel/interruption followed by retry, stale identifier/revision followed by rediscovery, repeated delete/revoke/rollback, conflicting independent mutation before retry, and selected operations while representative traffic is active. Any duplicate resource, leaked reservation, stale success, silent overwrite, false idempotence, or non-deterministic authoritative state is FAIL.

# 11. Parallel and simultaneous multi-host scenarios

Parallel multi-host execution is a mandatory part of FULL_USER_E2E, not only a performance optimization.

## C-001 — All applicable test hosts online simultaneously — MANDATORY

Bring every available supported-platform test host online at the same time.

Target matrix:

~~~text
Ubuntu 24
Windows 10
Rocky Linux 8
Rocky Linux 9
Amazon Linux 2023
macOS Apple Silicon
~~~

Each applicable host must simultaneously maintain:

- Managed Host identity;
- Agent connection;
- at least one Remote Service where the platform supports it;
- correct Server inventory;
- independent endpoint identity.

Required gate:

~~~text
ALL_TEST_HOSTS_SIMULTANEOUSLY_ONLINE=PASS
HOST_IDENTITY_CROSS_TALK=0
ENDPOINT_COLLISIONS=0
~~~

A missing environment is BLOCKED_ENVIRONMENT, not a synthetic PASS.

## C-002 — Parallel enrollment across all hosts — MANDATORY

Issue independent Zero-Touch/manual enrollment material as appropriate and enroll multiple platform hosts concurrently.

Verify:

- identities remain unique;
- each enrollment binds to the intended host;
- no ticket crosses hosts;
- capacity accounting is correct;
- concurrent same-ticket redemption is denied;
- all successful hosts appear correctly in Server inventory.

## C-003 — Parallel Remote Service creation and endpoint allocation — MANDATORY

On multiple Agent Hosts at the same time, create normal TCP and Fixed TCP Remote Services.

Verify:

- unique endpoint allocation;
- correct pool selection;
- no duplicate/overlapping reservation;
- no lost service registration;
- Server/Agent views converge;
- traffic reaches only the intended target.

## C-004 — Simultaneous real traffic on all hosts — MANDATORY

Generate real user traffic to every available host concurrently.

Include a mix of:

- SSH;
- HTTP;
- HTTPS;
- Custom TCP;
- Fixed TCP;
- Relay Host traffic.

Verify per-host correctness and aggregate correctness. One failing host cannot be hidden by aggregate throughput.

## C-005 — Parallel Internet Access from multiple protected sources — MANDATORY

Generate approved and denied outbound traffic concurrently from multiple protected sources/Managed Hosts.

Verify source-specific policy isolation, destination/port enforcement, and absence of cross-source policy leakage.

## C-006 — Parallel AI/MCP identities and calls — MANDATORY for v2.4.0

Prerequisite gate: the public MCP/auth path must be functionally serving authenticated calls for this RUN_ID. If the public MCP endpoint, certificate/bridge activation, or authentication prerequisite is not functional, classify C-006 (and dependent AI concurrency work) with the blocking functional disposition without repeated probes. Do not thrash unavailable MCP connectivity to manufacture additional evidence.

When the prerequisite holds, use multiple authenticated AI identities/sessions concurrently against different and overlapping target/permission scopes.

Verify:

- per-call authorization is evaluated independently;
- no cached ALLOW leaks into a later DENY;
- audit attribution remains correct;
- one identity cannot inherit another identity's session or permissions.

## C-007 — Policy mutation while all-host traffic is active — MANDATORY

While all-host traffic is active:

1. change Remote Access and/or Internet Access policy through Server CLI;
2. keep representative existing sessions alive;
3. start new sessions immediately before/after Apply.

Verify current contract for existing sessions and prove new connections use the new policy immediately without cross-host inconsistency.

## C-008 — Simultaneous Agent restart/reconnect storm — MANDATORY

Restart or disconnect multiple/all Agent Hosts together, then restore connectivity.

Measure:

- reconnect success;
- time to inventory convergence;
- endpoint preservation;
- pending allocation recovery;
- Server CPU/RSS/FD;
- no duplicate identities or endpoint reallocations.

## C-009 — Server outage with all Agents active — MANDATORY

With multiple Agents and real traffic active, interrupt Server availability.

On selected Agents, perform supported offline create/edit/delete operations through CLI. Restore Server and verify all Agents converge correctly, including stale-reference revalidation and deferred endpoint release/allocation.

## C-010 — Parallel ConfigurationBundle apply — MANDATORY

Apply independent Agent Bundles on multiple hosts concurrently while a Server Bundle is tested/applied through the Server CLI.

Verify context isolation:

~~~text
Server Bundle -> Server atomicity only
Agent Bundle  -> one Agent Host atomicity only
~~~

No implementation may pretend that the cross-host operation is one distributed atomic transaction.

## C-011 — Concurrent destructive/race cases — MANDATORY

Coordinate deliberate races:

- same Zero-Touch ticket redeemed twice;
- same endpoint-pool capacity contested by concurrent creates;
- same referenced Object deleted while another session tries to use it;
- same policy revision edited by two administrator sessions;
- service deletion synchronization racing with new allocation.

Expected outcome must be deterministic and leave no duplicate endpoint, orphaned resource, lost update, or incorrect final state.

## C-012 — All-host simultaneous reboot recovery — MANDATORY on disposable/approved hosts

Reboot all applicable Agent test hosts within the same test window.

After recovery, use CLI on every host plus Server CLI inventory to verify:

- autostart;
- identity continuity;
- endpoint continuity;
- policy continuity;
- real traffic;
- no host requires manual re-enrollment unless explicitly documented.

## C-013 — Parallel Agent update/restart convergence — MANDATORY on disposable/approved hosts

Update or restart multiple applicable Agent Hosts within the same maintenance window while the Server remains active.

Verify:

- each host preserves identity;
- endpoints remain mapped to the correct host/service;
- hosts reconnect independently;
- one failed host does not corrupt another host's state;
- Server inventory converges without duplicates;
- real traffic resumes per host.

## C-014 — Parallel mixed lifecycle operations — MANDATORY

Across different Agent Hosts at the same time perform a controlled mix of:

- create Remote Service;
- edit same-pool target/service;
- disable/enable;
- delete;
- synchronize;
- diagnostics;
- real user connection attempts.

Verify isolation between hosts and deterministic final state. A lifecycle operation on one host must not release, rename, or reassign another host's endpoint.

## C-015 — Parallel role-and-mistake storm — MANDATORY

Use the maximum safe concurrency available on the current hosts and overlap independent real-world mistakes and recovery work: stale/conflicting Administrator changes, wrong-selector Agent Operator recovery, long-lived/short-lived End User traffic during independent service lifecycle changes, Incident Responder outage diagnosis while normal work continues elsewhere, and AI-assisted work in parallel with a Direct lane on isolated namespaced state.

Run at least three rounds with rotated roles/hosts when topology allows. Per-lane timestamps must prove the overlap rather than infer it.

# 12. Performance test contract

Performance testing is part of FULL_USER_E2E.

The current product documents do not define universal numeric throughput/CPS/latency SLOs for every hardware/network combination. Therefore:

- always measure and retain metrics;
- always compare against a same-environment direct-path baseline when technically possible;
- apply numeric PASS thresholds only from an explicitly selected performance profile/SLO;
- if no numeric thresholds are defined, report PERFORMANCE_NUMERIC_QUALIFICATION=MEASURED_NOT_QUALIFIED rather than inventing a PASS threshold;
- functional failures under load are always FAIL regardless of numeric SLO.

Required performance evidence:

~~~text
PERF_PROFILE=
LOAD_GENERATOR_HW=
SERVER_HW=
AGENT_HW=
TARGET_HW=
NETWORK_RTT_DIRECT_MS=
NETWORK_RTT_RELAY_MS=
NIC_SPEED=
DURATION=
CONCURRENCY=
CPS_TARGET=
PAYLOAD_PROFILE=
THROUGHPUT_UP_MBIT_S=
THROUGHPUT_DOWN_MBIT_S=
THROUGHPUT_BIDIR_UP_MBIT_S=
THROUGHPUT_BIDIR_DOWN_MBIT_S=
CONNECT_P50_MS=
CONNECT_P95_MS=
CONNECT_P99_MS=
REQUEST_P50_MS=
REQUEST_P95_MS=
REQUEST_P99_MS=
ERROR_RATE=
RECONNECT_RATE=
SERVER_CPU_AVG_MAX=
SERVER_RSS_AVG_MAX=
SERVER_FD_AVG_MAX=
AGENT_CPU_AVG_MAX=
AGENT_RSS_AVG_MAX=
AGENT_FD_AVG_MAX=
DROPPED_CONNECTIONS=
DATA_INTEGRITY_ERRORS=
~~~

Default full-run durations unless the selected performance profile overrides them:

~~~text
WARMUP=60s
STEADY_STATE_EACH_CASE=300s
SOAK=3600s
~~~

The mandatory soak is a quality gate, but it is **not a serial end-of-run wait**. Start it as soon as a stable representative traffic/topology baseline exists and overlap independent persona, recovery, read-only, AI-assisted, and isolated-load lanes whenever state isolation permits. Do not leave runnable work idle merely because the soak clock is running.

Preferred test data profiles:

~~~text
small request/response
1 KiB
64 KiB
1 MiB
continuous stream
large file transfer
~~~

Use checksums for file-transfer integrity where applicable.

## P-001 — Direct-path baseline — MANDATORY

Measure the same target service without Data Relay Link, from the same load generator and network path where feasible.

Record throughput, connection latency, CPS, CPU, and error rate.

If a comparable direct path is impossible due to the isolated-network design, record BASELINE_UNAVAILABLE with the exact reason; do not fabricate a comparison.

## P-002 — Remote Access one-way throughput: User -> target — MANDATORY

Generate sustained upload/request traffic through a Remote Service public endpoint.

Measure:

- application goodput;
- server and Agent CPU/RSS;
- retransmission/error symptoms;
- data integrity.

Use SSH/SCP, HTTP upload, or an iperf3/custom TCP target through a DRLink TCP Remote Service as appropriate.

## P-003 — Remote Access one-way throughput: target -> User — MANDATORY

Generate sustained download/response traffic through the same public path.

Measure the same metrics independently from P-002.

## P-004 — Remote Access simultaneous full-duplex throughput — MANDATORY

Generate traffic in both directions at the same time.

A suitable TCP test service may use iperf3 bidirectional mode or an equivalent full-duplex harness published through a DRLink Remote Service.

Record independent upstream and downstream goodput plus aggregate resource usage.

## P-005 — Connection establishment rate / CPS — MANDATORY

Measure new successful connections per second through the public endpoint.

Ramp connection rate through the selected performance profile until the configured target or observed saturation/failure boundary.

Record:

- attempted CPS;
- successful CPS;
- failed/time-out connections;
- connect p50/p95/p99;
- Server/Agent CPU, memory, and FD usage;
- recovery after the load stops.

Do not convert a saturation point into a product defect unless it violates an approved performance profile or functional safety contract.

## P-006 — Concurrent active connections — MANDATORY

Hold increasing numbers of simultaneous established connections.

At minimum exercise several tiers including low, moderate, and high concurrency relative to the selected target profile.

Verify:

- no endpoint cross-talk;
- no data corruption;
- new policy evaluation still works for new connections;
- process remains responsive;
- diagnostics and show commands remain usable;
- cleanup returns resources.

## P-007 — Connect/request latency — MANDATORY

Measure TCP connect and application request latency through:

- direct Remote Service;
- Relay Host Remote Service;
- Fixed TCP Remote Service;
- HTTPS passthrough where applicable.

Record p50/p95/p99, not only averages.

## P-008 — Mixed-service workload — MANDATORY

Run simultaneous traffic across multiple service types, for example:

- SSH interactive/transfer;
- HTTP;
- HTTPS;
- Custom TCP;
- Fixed TCP.

Verify one hot service does not corrupt endpoint identity or policy behavior of another.

## P-009 — Multi-host scale — MANDATORY

Exercise the product across the **currently configured real test estate only**. Do not require or request new VMs/hosts merely to satisfy a synthetic fleet-size tier.

Mandatory physical-topology points are:

~~~text
1_HOST_BASELINE
2_HOST_SIMULTANEOUS_WHEN_AT_LEAST_2_SUITABLE_HOSTS_EXIST
N_HOST_MAXIMUM = EVERY_SUITABLE_REACHABLE_CURRENT_TEST_HOST
~~~

If the product can safely create additional independent logical services/sessions/clients on those same hosts, use them to increase connection/service pressure, but report them separately from physical host scale. A missing hypothetical 5/10/30/50-host lab is not a FULL_USER_E2E blocker.

At each available physical-topology point measure:

- healthy Agent connectivity;
- inventory/show response time;
- Remote Service count;
- policy evaluation correctness;
- endpoint allocation;
- CPU/RSS/FD;
- reconnect storm behavior.

The goal is to validate the documented few-to-few-dozen operating model, not to claim unsupported fleet scale.

## P-010 — Internet Access throughput and bidirectional application data — MANDATORY

For an approved destination, measure:

- protected host -> Internet upload/request throughput;
- Internet -> protected host response/download throughput;
- simultaneous request/response where the application permits;
- HTTP/HTTPS CONNECT/application latency;
- policy lookup under load.

Repeat a deny test during load to verify policy behavior remains correct under performance pressure.

## P-011 — AI/MCP performance — MANDATORY for v2.4.0

Prerequisite gate: same functional MCP/auth prerequisite as C-006/U-007. If the public MCP endpoint is not functional for this RUN_ID, do not repeat probes; inherit the blocking disposition and continue independent non-AI lanes.

When the prerequisite holds, measure representative allowed operations:

- host-info/process-read request rate and latency;
- file read/download throughput;
- file write/upload throughput if permitted;
- concurrent AI/MCP sessions;
- authentication/authorization latency;
- audit generation under load.

Also verify denied operations remain denied under concurrent load.

For v2.4.0, MCP absence is a release failure rather than a `NOT_APPLICABLE` condition. Performance measurement may use the qualified machine-side MCP client after the currently supported ChatGPT full-MCP owner/UI authentication gate is satisfied, but it does not replace U-007 owner/UI acceptance.

## P-012 — Connection churn and reconnect storm — MANDATORY

Repeatedly connect/disconnect clients and Remote Service user sessions.

Include:

- external connection churn;
- Agent reconnect storm after temporary Server outage;
- target-service flap;
- enable/disable cycles.

Verify no endpoint reassignment, reservation leak, unbounded FD growth, or stuck DEGRADED state.

## P-013 — Soak / long-duration stability — MANDATORY

Run mixed representative traffic for the configured soak duration; default 3600 seconds.

Collect time-series CPU, RSS, FD, connection count, error count, endpoint state, and policy/audit health.

PASS of functional soak requires:

- no crash/restart loop;
- no unexplained endpoint change;
- policy behavior remains correct;
- no data-integrity error;
- no unbounded resource growth indicating a leak;
- normal recovery after load ends.

Numeric resource ceilings come from the selected performance profile.

## P-014 — Backup/restart/recovery under load — MANDATORY

With active but disposable workload:

- create backup under supported activity;
- restart/reboot components according to scenario;
- restore in the designated recovery test;
- resume load.

Verify no corrupted authoritative state and that post-recovery traffic/policy matches pre-recovery intent.

## P-015 — Aggregate all-host throughput and fairness — MANDATORY

Prerequisite: C-001/C-004 topology with healthy functional data-plane paths on the hosts included in the aggregate measurement. If required host data paths have already persistently failed in this RUN_ID, classify `FAIL_PRECONDITION` (or inherit the blocking FAIL), retain the minimum diagnostic evidence, and do not run another full all-host saturation pass solely for this label.

When prerequisites hold, with C-001/C-004 topology active, run simultaneous throughput from all available test hosts.

Record:

- per-host forward/reverse/full-duplex throughput;
- aggregate Server throughput;
- per-host and aggregate error rate;
- Server and Agent resource usage;
- latency distribution per host;
- fairness/starvation symptoms.

A high aggregate number does not pass if one host is starved, misrouted, or silently failing.

## P-016 — CPS while throughput and policy load are active — MANDATORY

Prerequisite: sustained all-host throughput/policy load prerequisites from P-015 (or equivalent) must hold. If those functional data paths already failed persistently, use `FAIL_PRECONDITION` / evidence reuse per section 1.4.1 rather than inventing a CPS run against broken paths.

When prerequisites hold, run new-connection CPS load while sustained throughput and representative policy checks are already active.

Verify:

- successful CPS;
- connect p50/p95/p99;
- throughput degradation;
- authorization correctness;
- diagnostics responsiveness;
- recovery after load.

## P-017 — Recovery-time performance — MANDATORY

Measure time to recover after:

- Agent restart;
- all-Agent reconnect storm;
- Server restart/outage;
- target-service flap;
- endpoint capacity becoming available.

For target-service flap, apply the same health_check distinction as S-008: status-transition timing to HEALTHY/DEGRADED is in scope only when target health_check is configured/enabled; otherwise measure traffic failure/recovery timing and do not claim verified target-health status.

Record time to:

~~~text
Agent connected
inventory converged
endpoint active
Remote Service HEALTHY
first successful user connection
~~~

Remote Service HEALTHY above requires current runtime verification after Agent restart/reconnect; do not count stored HEALTHY before verification.

## P-018 — Operational commands under load — MANDATORY

While representative traffic is active, run read-only CLI operations:

~~~text
show status
show managed-hosts
show remote-services
test remote-access ...
test internet-access ...
system diagnostics
system audit
~~~

Verify they remain responsive and do not alter traffic.

Run supported backup under activity through:

~~~text
system backup
~~~

and verify backup consistency according to the backup contract.

## P-019 — Extended endurance profiles — OPTIONAL unless explicitly selected

In addition to the mandatory 1-hour FULL_USER_E2E soak, support:

~~~text
EXTENDED_SOAK=8h
ENDURANCE_SOAK=24h
~~~

Use these for overnight/endurance qualification when requested. Results must remain distinct from the mandatory 1-hour soak so historical shorter evidence is not misrepresented as 8h/24h evidence.

## P-020 — Network impairment characterization — MANDATORY when test infrastructure supports controlled impairment

Characterize representative traffic under controlled:

- added latency;
- jitter;
- packet loss;
- bandwidth restriction;
- brief network partition.

Measure throughput, latency, error/reconnect rate, endpoint continuity, and recovery time.

This scenario characterizes resilience; do not invent a numeric PASS threshold when no approved network-impairment SLO exists. Functional and state-integrity failures remain FAIL.

## P-021 — Saturation and post-saturation recovery — MANDATORY

Increase connection/concurrency/load until the selected profile target is reached or a practical saturation boundary is observed.

Verify:

- failure is bounded and explicit;
- policy behavior remains correct under saturation;
- no duplicate endpoint or state corruption;
- control CLI remains recoverable;
- resources return after load;
- service returns to normal without reinstall/re-enrollment.

## P-022 — Control-plane plus data-plane mixed pressure — MANDATORY

While all-host data-plane load is active, concurrently execute through public CLI:

- show/list inventory;
- policy test/explain;
- ConfigurationBundle test/diff;
- audit reads;
- support bundle on a designated host;
- backup on a disposable Server environment.

Measure command latency and verify read-only operations do not mutate state. Any mutating operation must still obey revision and atomicity rules under load.

## P-023 — Maximum available topology mixed-stress operation — MANDATORY

This is the final production-uncertainty stress gate. Use **all suitable reachable test hosts** and the maximum practical independent load sources/targets available in the current environment. The purpose is not to produce a marketing benchmark; it is to discover failures that appear only when multiple real operational activities collide.

If persistent functional data-path failures already make an all-host PASS impossible, collect the minimum mixed-stress diagnostic sample needed to characterize control-plane responsiveness under residual load, classify dependent saturation claims with `FAIL_PRECONDITION` / inherited FAIL per section 1.4.1, and do not repeat full-topology soak/saturation solely for this label. AI/MCP stress elements remain gated on the functional MCP prerequisite.

Ramp progressively from the measured baseline until either:

1. the selected performance profile target is reached and sustained; or
2. a practical saturation boundary is observed in Server, Agent, network, target, or load-generator capacity.

At the high-load stage, overlap as many applicable activities as the real topology supports:

- forward, reverse, and full-duplex Remote Service traffic;
- SSH/SCP/SFTP, HTTP, HTTPS and Custom TCP sessions;
- Fixed TCP and Relay Host traffic;
- high connection churn/CPS plus long-lived connections;
- all-host simultaneous traffic;
- Internet Access allowed and denied application traffic;
- concurrent AI/MCP requests including allowed and denied operations;
- new enrollment and Agent reconnect activity;
- Remote Service create/edit/disable/enable/delete on independent hosts;
- Remote/Internet/AI Access policy reads/tests and selected isolated mutations;
- ConfigurationBundle test/diff and isolated apply;
- diagnostics/audit/history/support-bundle reads;
- backup on the designated disposable Server state;
- one or more controlled Agent restart/reconnect events;
- target-service flap/network impairment on an isolated lane;
- external clients continuing real application work throughout the disturbance.

Do not serialize these merely to make results cleaner when their state is independent. Preserve per-lane evidence so a failure on one path is not hidden by aggregate success.

Record at minimum:

~~~text
MAX_STRESS_ACTIVE_HOSTS=
MAX_STRESS_ACTIVE_LANES=
MAX_STRESS_LOAD_GENERATORS=
MAX_STRESS_TARGETS=
MAX_STRESS_REMOTE_SERVICES=
MAX_STRESS_CONCURRENT_CONNECTIONS=
MAX_STRESS_CPS=
MAX_STRESS_AGGREGATE_THROUGHPUT=
SATURATION_LIMITER=DRLINK_SERVER|AGENT|NETWORK|TARGET|LOAD_GENERATOR|UNKNOWN
SATURATION_EVIDENCE=
MAX_STRESS_AI_MCP_CONCURRENCY=
MAX_STRESS_SERVER_CPU_RSS_FD=
MAX_STRESS_AGENT_RESOURCE_PEAKS=
MAX_STRESS_CONTROL_CLI_P95_P99=
MAX_STRESS_POLICY_PROPAGATION=
MAX_STRESS_ERRORS_TIMEOUTS=
MAX_STRESS_DATA_INTEGRITY_ERRORS=
MAX_STRESS_ENDPOINT_COLLISIONS=
MAX_STRESS_AUTHORIZATION_ERRORS=
POST_SATURATION_RECOVERY_TIME=
POST_STRESS_RESOURCE_RETURN=PASS|FAIL
POST_STRESS_FUNCTIONAL_RECHECK=PASS|FAIL
~~~

Use multiple independent load generators whenever available so the measured boundary is not trivially capped by one generator. When a boundary is observed, identify the limiting component using host/network/resource evidence; do not attribute generator, target, or network saturation to DRLink without evidence.

A saturation boundary is acceptable as a measured characteristic only if failure remains bounded/truthful, authorization and data isolation remain correct, state is not corrupted, endpoints are not duplicated/reassigned incorrectly, the control plane remains recoverable, and the product returns to normal operation after pressure is removed. Any correctness, isolation, integrity, authorization, or recovery failure under stress is a product FAIL regardless of whether a numeric SLO exists.

## P-024 — Continuous function-under-load collision matrix — MANDATORY

Performance work must not be isolated into a quiet benchmark phase. After baseline measurement, keep representative load running while functional scenarios continue on independent resources, using only the currently configured hosts.

Mandatory collision rows when prerequisites hold:

~~~text
THROUGHPUT + SHOW/DIAGNOSTICS/AUDIT
THROUGHPUT + REMOTE_SERVICE_CREATE_EDIT_DISABLE_ENABLE_DELETE_ON_INDEPENDENT_SERVICE
THROUGHPUT + REMOTE_ACCESS_POLICY_ALLOW_DENY_MUTATION_AND_REAL_TRAFFIC_VERIFY
THROUGHPUT + INTERNET_ACCESS_ALLOW_DENY_APPLICATION_CHECK
THROUGHPUT + CONFIG_BUNDLE_TEST_DIFF_AND_ISOLATED_APPLY
THROUGHPUT + BACKUP
THROUGHPUT + AGENT_RESTART_RECONNECT_ON_ISOLATED_HOST
CPS_CHURN + LONG_LIVED_CONNECTIONS + FILE_TRANSFER
CPS_CHURN + ENDPOINT_ALLOCATION_CONTENTION
NETWORK_IMPAIRMENT + READ_ONLY_CONTROL_OPERATIONS + TRAFFIC_RECOVERY
MIXED_PROTOCOL_LOAD + DELIBERATE_INVALID_OPERATOR_INPUT_AND_RECOVERY
MIXED_PROTOCOL_LOAD + AI_ASSISTED_CONTROL_OPERATION_ON_ISOLATED_STATE
~~~

For every row capture idle/baseline behavior, background load/resource state, the concurrent functional or recovery action, command latency and authoritative final state, real traffic effect during/after the action, and post-load recovery/resource return. A row may share a continuous load window with another row, but each functional assertion requires distinct evidence.

Required gate:

~~~text
FUNCTION_UNDER_LOAD_COLLISION_ROWS_APPLICABLE=
FUNCTION_UNDER_LOAD_COLLISION_ROWS_EXECUTED=
FUNCTION_UNDER_LOAD_COLLISION_COVERAGE=100%
FUNCTION_UNDER_LOAD_CORRECTNESS_FAILURES=0_FOR_PASS
POST_COLLISION_RECOVERY=PASS
~~~

# 13. Platform matrix

For FULL_USER_E2E, test every platform currently claimed by the candidate at its actual qualification level.

Current release validation includes this matrix:

~~~text
Ubuntu 24
Windows 10
Rocky Linux 8
Rocky Linux 9
Amazon Linux 2023
macOS Apple Silicon
~~~

For each platform record one of:

~~~text
PASS_REAL
PASS_SYSTEM_SERVICE
PASS_CONTAINER_ONLY
NOT_APPLICABLE
BLOCKED_ENVIRONMENT
FAIL
~~~

Do not upgrade container/userspace evidence into Real E2E PASS.

Where a platform cannot host the Server role, execute its applicable Agent/client scenarios only.

At least one FULL_USER_E2E pass must also prove the entire available matrix concurrently via C-001 through C-012; per-platform serial PASS alone is insufficient for the all-host simultaneous gate.

## 13.1 Topology matrix

FULL_USER_E2E must qualify every topology currently claimed by the candidate. Record unsupported/unclaimed topology explicitly rather than silently skipping it.

At minimum classify:

~~~text
DIRECT_PUBLIC_IP=
PUBLIC_DNS_HOSTNAME=
ENTERPRISE_SINGLE_443=
NAT_DNAT_PRIVATE_SERVER=
RESTRICTED_OUTBOUND_AGENT_NETWORK=
RELAY_HOST_TO_LAN_TARGET=
~~~

Use:

~~~text
PASS_REAL
NOT_APPLICABLE_NOT_CLAIMED
BLOCKED_ENVIRONMENT
FAIL
~~~

Public DNS and hostname behavior must include U-009/A-018. Enterprise single-443 or NAT/DNAT becomes mandatory whenever the current candidate/release documentation claims it as supported. A historical PASS from another HEAD is not current-run evidence.

# 14. Complete CLI coverage list used by E2E

This section mirrors the public v2.4 CLI/AI Master. It is a coverage checklist, not a second grammar authority.

FULL_USER_E2E requires every applicable entry below to be executed through the public CLI at least once and linked to scenario evidence. Presence in this list alone does not count as coverage.

## 14.1 Server show

~~~text
show status

show managed-hosts
show managed-host <HOST>
show managed-host <HOST> agent
show managed-host <HOST> addresses
show managed-host <HOST> remote-services

show managed-host-groups
show managed-host-group <GROUP>

show enrollments
show enrollment <ENROLLMENT>

show network-objects
show network-object <OBJECT>
show network-object <OBJECT> references

show network-groups
show network-group <GROUP>
show network-group <GROUP> references

show service-objects
show service-object <SERVICE>
show service-object <SERVICE> references

show service-groups
show service-group <GROUP>
show service-group <GROUP> references

show remote-access
show remote-access <RULE>

show internet-access
show internet-access <RULE>

show ai-identities
show ai-identity <IDENTITY>

show permission-objects
show permission-object <PERMISSION>

show permission-groups
show permission-group <GROUP>

show ai-access
show ai-access <RULE>

show ai-access-log
show ai-access-log identity <IDENTITY>
show ai-access-log destination <DESTINATION>
show ai-access-log permission <PERMISSION>
~~~

## 14.2 Server set

~~~text
set enrollment zero-touch
set enrollment manual
set enrollment bulk

set server public-hostname <value>
set server bootstrap-hostname <value>
set server installer-url <value>
set server windows-installer-url <value>
set mcp-tls hostname <FQDN>
set mcp-tls mode <MODE>
set mcp-tls contact-email <EMAIL>
set mcp-tls acme-environment <ENVIRONMENT>
set mcp-tls acme-directory <URL>

set managed-host-group <GROUP>
set managed-host <HOST> group <GROUP>

set network-object <OBJECT>
set network-group <GROUP>

set service-object <SERVICE>
set service-group <GROUP>

set remote-access <RULE>
set remote-access enabled
set remote-access disabled

set internet-access <RULE>
set internet-access enabled
set internet-access disabled

set ai-identity <IDENTITY>

set permission-object <PERMISSION>
set permission-group <GROUP>

set ai-access <RULE>
set ai-access enabled
set ai-access disabled
~~~

## 14.3 Server unset

~~~text
unset managed-host <HOST>
unset managed-host <HOST> group <GROUP>
unset managed-host-group <GROUP>
unset enrollment <ENROLLMENT>
unset server public-hostname
unset server bootstrap-hostname
unset server installer-url
unset server windows-installer-url
unset mcp-tls
unset mcp-tls purge

unset network-object <OBJECT>
unset network-group <GROUP>

unset service-object <SERVICE>
unset service-group <GROUP>

unset remote-access <RULE>
unset remote-access policy

unset internet-access <RULE>
unset internet-access policy

unset ai-identity <IDENTITY>

unset permission-object <PERMISSION>
unset permission-group <GROUP>

unset ai-access <RULE>
unset ai-access policy
~~~

## 14.4 Server test

~~~text
test remote-access source <SOURCE> destination <DESTINATION> service <SERVICE>
test internet-access source <SOURCE> destination <DESTINATION> service <SERVICE>
test ai-access source <AI_IDENTITY> destination <DESTINATION> permission <PERMISSION>
test configuration <FILE|->
~~~

## 14.5 Server system

~~~text
system status
system version
system diagnostics
system audit

system revisions
system revision <REVISION>
system diff <REVISION_A> <REVISION_B>
system rollback <REVISION>

system backup
system backup validate <FILE>
system restore <FILE>

system export configuration <FILE>
system diff configuration <FILE|->
system apply configuration <FILE|->

system diagnostics mcp

system certificate status
system certificate preflight
system certificate issue
system certificate renew
system certificate import <CERT> <KEY> [CHAIN]

system update product
system update engine
system update check-engine

system credential rotate ai-identity <NAME>
system credential revoke ai-identity <NAME>
system credential configure ai-identity <NAME> authentication static-bearer
system credential configure ai-identity <NAME> authentication oauth
system credential approve-oauth <PENDING-ID> [AI-IDENTITY]
system credential deny-oauth <PENDING-ID>

system support-bundle
system history
system clear
system uninstall
~~~

## 14.6 Agent Host

~~~text
show status
show agent

show remote-services
show remote-service <NAME>

set remote-service <NAME>
unset remote-service <NAME>

system info
system pause
system resume
system restart

system autostart enable
system autostart disable

system update product
system update check-engine
system update engine
system synchronize

test configuration <FILE|->

system export configuration <FILE>
system diff configuration <FILE|->
system apply configuration <FILE|->

system diagnostics
system support-bundle
system version
system uninstall
~~~

When an Agent help/diagnostic surface recommends system synchronize, the command must parse and be role-correct.

## 14.7 Universal CLI navigation/discovery

These public surfaces must be exercised on both Server and Agent roles where available:

~~~text
menu
help
help commands
?
Tab completion
exit
~~~

Navigation/discovery coverage counts only when exercised interactively in the role-appropriate CLI; printing static help text from documentation is not execution evidence.

## 14.8 External user/application commands

These are not DRLink grammar, but FULL_USER_E2E must use real clients appropriate to the service:

~~~text
ssh / scp / sftp
curl
wget
git
apt
real HTTP/HTTPS client
real Custom TCP client
performance load generator
supported AI/MCP client when applicable
~~~

Use only the commands actually applicable to the target OS/application.

# 15. Conditional ChatGPT Plus Plugin / MCP relay integration lane

This lane applies when the requested E2E scope includes `datarelay-labs/datarelay-link-plugin` or when a release/acceptance claim includes the ChatGPT Plus Plugin/relay path.

It is intentionally reported separately because the Plugin repository is an optional experimental integration layer. Core DRLink must continue to operate without it.

All DRLink state setup remains CLI-only. Plugin transport/authentication is exercised only through its supported integration surface.

## X-001 — Exact cross-repository identity — CONDITIONAL

Record separately:

~~~text
DRLINK_CORE_HEAD=
DRLINK_PLUGIN_HEAD=
PLUGIN_PACKAGE_VERSION_OR_ID=
DRLINK_MCP_ENDPOINT=
RELAY_ENDPOINT=
~~~

Never reuse Plugin evidence from another Core HEAD or vice versa.

## X-002 — Plugin package and MCP declaration — CONDITIONAL

Verify the actual package declares the intended remote Streamable HTTP MCP endpoint and does not embed literal credentials.

Package/relay metadata must not invent tools or redefine DRLink authorization.

## X-003 — OAuth 2.1 / owner-consent flow — CONDITIONAL

Exercise the currently supported Plugin authentication path, including as applicable:

- protected-resource metadata;
- authorization-server metadata;
- Authorization Code;
- PKCE S256;
- DCR/public client behavior;
- owner approval;
- access token;
- refresh/reconnect;
- revoke/disconnect.

Verify public/non-loopback OAuth completes through the supported Plugin workflow and does not silently fall back to an unsupported mock mode.

## X-004 — MCP relay pass-through — CONDITIONAL

Exercise:

~~~text
initialize
tools/list
tools/call
JSON-RPC error path
Mcp-Session-Id continuity
Last-Event-ID where applicable
Accept / Content-Type protocol behavior
~~~

Verify the relay preserves upstream tool schemas/annotations and does not invent, filter, or reinterpret tools.

## X-005 — DRLink policy result passthrough — CONDITIONAL

Configure AI Identity, Permission, destination, and AI Access only through `drlink`.

Through the Plugin/relay path verify per call:

- DRLink ALLOW succeeds;
- DRLink DENY remains denied;
- policy change affects the next call;
- relay does not cache an earlier ALLOW result;
- each Plugin identity/binding receives the policy result associated with its own configured identity.

## X-007 — Core vs Plugin acceptance separation — CONDITIONAL

Final report must distinguish:

~~~text
CORE_CLI_E2E=
DIRECT_MCP_E2E=
CHATGPT_PLUGIN_RELAY_E2E=
~~~

A passing direct MCP test cannot substitute for a Plugin path failure. A Plugin path PASS cannot substitute for unexecuted public `drlink` CLI scenarios.

## X-008 — OAuth concurrency and durable state — CONDITIONAL

Exercise concurrent DCR/authorize/token activity within the Plugin's supported PoC limits.

Verify:

- pending request capacity behaves according to the documented limit;
- unexpired pending owner consent remains available during concurrent activity;
- active refresh-bound clients are not removed by ordinary inactive cleanup;
- restart preserves the documented durable client/refresh/revocation state;
- public/non-loopback OAuth remains on the documented durable workflow.

## X-009 — Plugin OAuth state backup/restore — CONDITIONAL

Use the Plugin repository's supported backup/restore workflow for OAuth state.

After restore/restart, verify the expected reconnect/revoke semantics and resulting operational state.

## X-010 — Real ChatGPT Plus Plugin acceptance — CONDITIONAL when environment is available

If the acceptance claim explicitly includes ChatGPT Plus rather than only protocol interoperability, test the actual ChatGPT Plus Plugin/App installation and tool-use surface.

This is an external-client validation analogous to using real SSH/curl clients; it does not relax the DRLink CLI-only control-plane rule.

Verify end to end:

~~~text
ChatGPT Plus
→ Plugin package
→ OAuth/connect
→ relay
→ DRLink Server MCP
→ DRLink AI Access
→ Managed Host
~~~

Record the exact ChatGPT/Plugin environment and date. If the real ChatGPT surface is unavailable, report BLOCKED_ENVIRONMENT for a ChatGPT-specific claim rather than substituting a generic MCP client and calling it PASS.

# 16. Evidence and result rules

Every scenario result must be one of:

~~~text
PASS
FAIL
PARTIAL
FAIL_PRECONDITION
BLOCKED_ENVIRONMENT
BLOCKED_TOOLING
BLOCKED_MANAGEMENT_PATH
INVALIDATED_BY_CONCURRENT_STATE
NOT_APPLICABLE
NOT_RUN_BY_SCOPE
~~~

Rules:

- PASS requires current-run evidence from the exact candidate build.
- BLOCKED_ENVIRONMENT is not PASS.
- BLOCKED_TOOLING means the test executor/tooling could not perform the real user action; it is not PASS and must block aggregate FULL_USER_E2E PASS for a mandatory applicable scenario.
- NOT_APPLICABLE requires an explicit product/platform reason.
- NOT_RUN_BY_SCOPE is allowed only for an explicitly narrowed request.
- A FULL_USER_E2E aggregate PASS is invalid if any mandatory applicable scenario is FAIL, PARTIAL, FAIL_PRECONDITION, BLOCKED_ENVIRONMENT, BLOCKED_TOOLING, BLOCKED_MANAGEMENT_PATH, INVALIDATED_BY_CONCURRENT_STATE, or NOT_RUN. `INVALIDATED_BY_CONCURRENT_STATE` must be rerun from isolated/namespaced state before final completion.
- A numeric performance PASS is invalid when no approved numeric performance profile/SLO is defined; use MEASURED_NOT_QUALIFIED for the numeric qualification while still reporting functional load-test results.
- A release PASS additionally follows all exact-HEAD and double-pass requirements in docs/RELEASE_VALIDATION.md.

### 16.1 Canonical evidence ledgers and report consistency

The final FULL_USER_E2E report must be generated from retained machine-readable ledgers, not manually re-counted from prose evidence.

Canonical ledgers under the RUN_ID evidence root:

~~~text
ledger/scenario-results.tsv
  SCENARIO_ID  USE_CASE_ID  APPLICABLE  MANDATORY  DIRECT_RESULT  AI_REQUIRED  AI_RESULT  FINAL_RESULT  BLOCK_REASON  EVIDENCE

ledger/findings.tsv
  FINDING_ID  SEVERITY  USER_BLOCKING  STATUS  CLASSIFICATION  SURFACE  EVIDENCE
~~~

Rules:

1. every executed/dispositioned U/O/A/S/C/P/X scenario appears exactly once in `scenario-results.tsv`;
2. every mandatory applicable scenario has explicit Direct result and AI result when AI is required;
3. every finding file has exactly one `findings.tsv` row;
4. scenario/finding totals in the final report and release JSON are recomputed from these ledgers;
5. the GitHub final-report section is generated from the same recomputed values;
6. any mismatch between ledger, summary, release JSON, or GitHub report is `REPORT_CONSISTENCY_FAIL` and prevents a clean final report;
7. evidence is authoritative; regenerate summaries from it rather than editing evidence to fit a previously published summary;
8. a late manual spot-check does not convert an earlier scripted/wrapper-run scenario into actual-user evidence. Invalid persona evidence must be rerun from a clean persona context, and run-wide contamination requires a new RUN_ID.

~~~text
EVIDENCE_LEDGER_SCHEMA=PASS|FAIL
SUMMARY_DERIVED_FROM_LEDGER=YES|NO
REPORT_CONSISTENCY=PASS|FAIL
EVIDENCE_SUMMARY_MISMATCH_COUNT=
AUDITOR_KNOWLEDGE_LEAK_COUNT=
PRIMARY_USER_EVIDENCE_MODE=PERSONA_LED_PUBLIC_UX
~~~

Per scenario retain:

~~~text
SCENARIO_ID=
USE_CASE_ID=
PARALLEL_LANE=
ROLE=
PERSONA=
MISSION=
HOST=
START_UTC=
END_UTC=
SOURCE_HEAD=
PRODUCT_VERSION=
DISCOVERY_PATH=
PUBLIC_GUIDANCE_USED=
DISCOVERED_COMMANDS_VARIANTS=
COMMANDS_EXECUTED=
AI_MIRROR_REQUIRED=YES|NO
AI_MIRROR_RESULT=
REPEAT_INDEX=
STARTING_STATE=
SEQUENCE_VARIANT=
CONCURRENT_BACKGROUND_ACTIVITY=
MISTAKE_INJECTED=
RECOVERY_SOURCE=CLI|AI|TEST_HOST_STATE_RECOVERY|NOT_APPLICABLE
MANUAL_OR_RUNBOOK_CONSULTED=NO
TERMINOLOGY_CONSISTENT=
ROLE_CONTEXT_CLEAR=
STATE_SEMANTICS_CLEAR=
ACTION_IMPACT_CLEAR=
NEXT_ACTION_CLEAR=
GENERATED_GUIDANCE_EXECUTABLE=
EXPECTED=
OBSERVED=
RESULT=
FAILURE_CLASS=
EVIDENCE_PATHS=
NOTES=
~~~

Performance scenarios additionally retain raw machine-readable metrics when possible.

The run must also produce explicit coverage inventories:

~~~text
SCENARIO_TOTAL=
SCENARIO_PASS=
SCENARIO_FAIL=
SCENARIO_BLOCKED=
SCENARIO_BLOCKED_TOOLING=
SCENARIO_NOT_APPLICABLE=
USE_CASES_TOTAL=
USE_CASES_EXECUTED_DIRECT=
USE_CASES_EXECUTED_AI_MIRROR=
USE_CASES_UNEXECUTED=
USE_CASES_WITHOUT_AI_MIRROR=
MANDATORY_REPEAT_COVERAGE=
STATE_CHANGING_COMMANDS_BELOW_REPEAT_MINIMUM=
DELIBERATE_MISTAKE_COVERAGE=
RECOVERY_USING_ONLY_CLI_OR_AI=
FUNCTION_UNDER_LOAD_COLLISION_COVERAGE=
ACTING_PERSONA_MANUAL_FREE=PASS|FAIL
CURRENT_CONFIGURED_TEST_HOSTS_ONLY=PASS|FAIL
DISCOVERED_PUBLIC_COMMANDS_TOTAL=
DISCOVERED_PUBLIC_VARIANTS_TOTAL=
ORACLE_ONLY_COMMANDS_NOT_DISCOVERABLE=
PUBLIC_CLI_COMMANDS_TOTAL=
PUBLIC_CLI_COMMANDS_EXECUTED=
PUBLIC_CLI_COMMANDS_UNEXERCISED=
PUBLIC_CLI_VARIANTS_UNEXERCISED=
PUBLIC_COMMANDS_WITHOUT_USE_CASE=
PUBLIC_COMMANDS_WITHOUT_DIRECT_USE=
PUBLIC_COMMANDS_WITHOUT_AI_ASSISTED_USE=
PUBLIC_CLI_SURFACES_TOTAL=
PUBLIC_CLI_SURFACES_EXECUTED=
DISCOVERABILITY_DEFECTS=
DOC_RUNTIME_COMMAND_DRIFT=
CANONICAL_MASTER_SCENARIOS_TOTAL=
CANONICAL_MASTER_SCENARIOS_EXECUTED=
ALL_TEST_HOSTS_EXPECTED=
ALL_TEST_HOSTS_SIMULTANEOUSLY_ONLINE=
~~~

Any non-zero unexercised applicable use case, public CLI command/variant, command without a real use case, command without Direct functional use, command without required AI-assisted use, applicable use case without its AI mirror, undisposed discovered command, or canonical mandatory scenario prevents FULL_USER_E2E PASS. A command that only parsed or displayed help does not count as functional use unless discovery/help is the capability being tested. A command that exists in the auditor oracle but cannot be discovered through public product UX is a discoverability defect and prevents a clean PASS until dispositioned.

# 17. Final FULL_USER_E2E report

A full run must end with a summary at least equivalent to:

~~~text
PHASE=FULL_USER_E2E
EXECUTOR=ChatGPT
FINAL_AUDITOR=ChatGPT
CURSOR_EXECUTED_USER_E2E=NO
FINAL_STATUS=PASS|PARTIAL|FAIL

ACTIVE_WORKTREE=
WORKTREE_RESOLUTION=PASS|FAIL
TEST_CONTRACT_HEAD=
PRODUCT_SOURCE_HEAD=
ASSIGNED_RUNTIME_SOURCE_HEADS=
ASSIGNED_RUNTIME_HEADS_MATCH_PRODUCT_SOURCE=PASS|FAIL
PRE_CANDIDATE_OBSERVATION_PRODUCT_FINDING_COUNT=
PRE_RUN_CLEAN_STATE=PASS|FAIL
ALL_REACHABLE_ASSIGNED_HOSTS_CLEAN=PASS|FAIL
PRESERVED_TEST_MANAGEMENT_INFRA=
PROCESS_CLEANUP=PASS|FAIL
SOURCE_HEAD=
PRODUCT_VERSION=
RELEASE_CHANNEL=
RELAY_ENGINE_VERSION=

USER_SCENARIOS=PASS|PARTIAL|FAIL
OPERATOR_SCENARIOS=PASS|PARTIAL|FAIL
ADMIN_SCENARIOS=PASS|PARTIAL|FAIL
NEGATIVE_FAILURE_FUNCTIONAL=PASS|PARTIAL|FAIL
PERFORMANCE_FUNCTIONAL=PASS|PARTIAL|FAIL
PERFORMANCE_NUMERIC_QUALIFICATION=PASS|FAIL|MEASURED_NOT_QUALIFIED
MULTI_PLATFORM=PASS|PARTIAL|FAIL
TOPOLOGY_MATRIX=PASS|PARTIAL|FAIL
ALL_TEST_HOSTS_SIMULTANEOUSLY_ONLINE=PASS|PARTIAL|FAIL
ALL_SUITABLE_HOSTS_UTILIZED=PASS|FAIL
REACHABLE_TEST_HOSTS=
ASSIGNED_ACTIVE_TEST_HOSTS=
UNUSED_REACHABLE_HOSTS=
PARALLEL_MULTI_HOST=PASS|PARTIAL|FAIL
OPERATIONAL_PERSONA_COVERAGE=PASS|PARTIAL|FAIL
USE_CASE_COVERAGE=
DISCOVERY_FROM_PUBLIC_UX=PASS|PARTIAL|FAIL
PUBLIC_CLI_COMMAND_COVERAGE=
PUBLIC_CLI_VARIANT_COVERAGE=
PUBLIC_CLI_SURFACE_COVERAGE=
COMMANDS_WITHOUT_USE_CASE=
PUBLIC_COMMANDS_WITHOUT_DIRECT_USE=
PUBLIC_COMMANDS_WITHOUT_AI_ASSISTED_USE=
USE_CASES_WITHOUT_AI_MIRROR=
MANDATORY_REPEAT_COVERAGE=
DELIBERATE_MISTAKE_COVERAGE=
FUNCTION_UNDER_LOAD_COLLISION_COVERAGE=
ACTING_PERSONA_MANUAL_FREE=PASS|FAIL
PRIMARY_USER_EVIDENCE_MODE=PERSONA_LED_PUBLIC_UX
AUDITOR_KNOWLEDGE_LEAK_COUNT=
SCRIPTED_USER_SCENARIO_EXECUTION_COUNT=
AUTOMATED_HARNESS_USER_SUBSTITUTION_COUNT=
TTY_TOOLING_STATUS=PASS|BLOCKED_TOOLING_TTY|NOT_APPLICABLE
TTY_PERSONA_COVERAGE=PASS|PARTIAL|NOT_APPLICABLE
CURRENT_CONFIGURED_TEST_HOSTS_ONLY=PASS|FAIL
ORACLE_ONLY_COMMANDS_NOT_DISCOVERABLE=
DISCOVERABILITY_DEFECTS=
DOC_RUNTIME_COMMAND_DRIFT=
TERMINOLOGY_CLARITY_CROSS_SURFACE=PASS|PARTIAL|FAIL
TERMINOLOGY_MISMATCHES=
AMBIGUOUS_GUIDANCE_FINDINGS=
INVALID_GENERATED_GUIDANCE_FINDINGS=
PARALLEL_LANES_STARTED=
MAX_SIMULTANEOUS_ACTIVE_LANES=
IDLE_WHILE_INDEPENDENT_WORK_AVAILABLE=YES|NO
DRLINK_CONTROL_PLANE_CLI_ONLY=PASS|FAIL
AI_ASSISTED_CLI=PASS|PARTIAL|FAIL
AI_USE_CASE_MIRROR_COVERAGE=
CHATGPT_FULL_MCP_OWNER_UI_PLAN=
CHATGPT_FULL_MCP_OWNER_UI_SURFACE=
CHATGPT_FULL_MCP_OWNER_UI_DATE=
CHATGPT_PLUGIN_INTEGRATION=PASS|PARTIAL|FAIL|NOT_APPLICABLE
CANONICAL_MASTER_SCENARIO_COVERAGE=
UNEXERCISED_PUBLIC_COMMANDS=

REMOTE_ACCESS_REAL_TRAFFIC=
INTERNET_ACCESS_REAL_TRAFFIC=
AI_MCP_REAL_TRAFFIC=
ZERO_TOUCH=
CONFIGURATION_BUNDLE=
BACKUP_RESTORE=
REBOOT_RECOVERY=
UPDATE_RECOVERY=
ENDPOINT_CONTINUITY=

THROUGHPUT_FORWARD=
THROUGHPUT_REVERSE=
THROUGHPUT_BIDIRECTIONAL=
CPS=
CONCURRENT_CONNECTIONS=
CONNECT_P95=
CONNECT_P99=
SOAK=
RESOURCE_STABILITY=
MAXIMUM_TOPOLOGY_STRESS=PASS|PARTIAL|FAIL
FUNCTION_UNDER_LOAD_COLLISION_MATRIX=PASS|PARTIAL|FAIL
MAX_STRESS_ACTIVE_HOSTS=
MAX_STRESS_ACTIVE_LANES=
MAX_STRESS_AGGREGATE_THROUGHPUT=
SATURATION_LIMITER=
POST_SATURATION_RECOVERY_TIME=
POST_STRESS_FUNCTIONAL_RECHECK=PASS|FAIL

UNRESOLVED_P0=
UNRESOLVED_P1=
UNRESOLVED_P2=
UNDOCUMENTED_KNOWLEDGE_REQUIRED_COUNT=
WORKFLOW_DEAD_END_COUNT=
NON_ACTIONABLE_ERROR_COUNT=
INVALID_OR_STALE_NEXT_ACTION_COUNT=
ROLE_CONTEXT_CONFUSION_COUNT=
AMBIGUOUS_TERMINOLOGY_COUNT=
MISLEADING_SUCCESS_OR_STATE_COUNT=
MANUAL_REQUIRED_FOR_NORMAL_WORKFLOW_COUNT=
UNRESOLVED_ACTIONABLE_USABILITY_FINDINGS=
UNRESOLVED_PRODUCT_DEFECTS=
EVIDENCE_LEDGER_SCHEMA=PASS|FAIL
SUMMARY_DERIVED_FROM_LEDGER=YES|NO
REPORT_CONSISTENCY=PASS|FAIL
EVIDENCE_SUMMARY_MISMATCH_COUNT=
SCENARIO_COUNTS=
FINDING_COUNTS=
GITHUB_REPORT_STATUS=PASS|BLOCKED_TOOLING
GITHUB_REPORT_READBACK=PASS|FAIL|NOT_RUN
NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES|NO
NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES|NO
BLOCKERS=
EVIDENCE_ROOT=
~~~

If FINAL_STATUS is not PASS, list the exact failing/blocking scenario IDs.

A clean `FULL_USER_E2E=PASS` also requires no unresolved product defect or actionable usability improvement discovered by the suite. Cosmetic/non-actionable observations may remain only when explicitly dispositioned as non-actionable for the current supported product scope.

### 17.1 GitHub reporting — final only

Do not update the active `[AI Work]` Issue for each intermediate finding. Keep findings in the current RUN_ID evidence while continuing every independent scenario.

After all executable scenarios, command/use-case/AI-mirror coverage, performance/concurrency lanes, recovery checks, and cleanup are exhausted and the final report is frozen, update the active `[AI Work]` Issue once with the consolidated result, evidence root, counters, blockers, and next remediation action if any.

~~~text
INTERMEDIATE_GITHUB_ISSUE_UPDATE=NO
FINAL_GITHUB_ISSUE_UPDATE=YES
~~~

### 17.2 Product-quality closure relationship

FULL_USER_E2E is one of two product-quality closure tests. When the same supported product candidate also has `CLI_FEATURE_SCENARIO_RECONCILIATION=PASS`, the combined result means there is no known in-scope product defect and no unresolved actionable product/usability improvement under the two exhaustive quality contracts.

~~~text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FULL_USER_E2E=PASS
=> PRODUCT_QUALITY_CLOSURE=PASS
=> NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES
=> NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES
~~~

This is a **product-quality closure**, not a release declaration. `PRODUCT_QUALITY_CLOSURE=PASS` does not mean `RELEASE_READY=YES` and does not replace any existing release procedure.

For stable release qualification, FULL_USER_E2E is a mandatory exhaustive gate and is executed twice on the same exact HEAD. Retain machine-readable records at:

~~~text
e2e-reports/release-qualification/full-user-e2e-pass1.json
e2e-reports/release-qualification/full-user-e2e-pass2.json
~~~

Each record must use `gate=FULL_USER_E2E`, `pass_name=PASS1|PASS2`, `final_status=PASS`, exact `git_head=end_head`, and `head_unchanged=true`. It must also carry PASS for the mandatory scenario families and real-traffic/lifecycle gates, zero unexercised public commands/use cases/discoverability defects, and an `evidence_root` pointing to retained evidence.

Release qualification validates these records with:

~~~bash
python3 scripts/check-pre-release-exhaustive-gates.py --gate full-user-e2e-all
~~~

Both FULL_USER_E2E passes and `CLI_FEATURE_SCENARIO_RECONCILIATION=PASS` are mandatory pre-release exhaustive tests. The reconciliation is a runtime non-destructive Feature ↔ CLI/AI ↔ Operator Workflow audit; FULL_USER_E2E owns live state-changing journeys and real traffic. Neither substitutes for the other, and a product/CLI/documentation-surface change invalidates previously retained exact-HEAD evidence.

# 18. Maintenance rule

Whenever a public CLI command, supported platform, topology, Access Policy semantic, Remote Service lifecycle, Internet Access behavior, AI/MCP capability, enrollment workflow, backup/restore behavior, or release gate changes, this document must be reviewed in the same change.

The invariant for future User E2E requests is:

~~~text
USER_E2E_REQUEST
-> ChatGPT is the executor and final auditor; do not delegate User E2E execution to Cursor
-> locate this canonical document at docs/FULL_USER_E2E_SCENARIOS.md
-> capture candidate/build identity only; do not perform a pre-run code review
-> probe all configured test hosts, remove previous-run DRLink state/test services/load processes/temp artifacts, preserve only explicit management access infrastructure, and require the section 5.3 clean-room gate before fresh product activity
-> execute as a human black-box operator; do not reinterpret the request as release qualification
-> discover ~/.ssh/config hosts and untracked local inventory, resolve SSH routes per section 5.1, probe availability/roles, assign topology, and start independent lanes immediately
-> use automated harnesses only as supplemental evidence, never as the User E2E executor
-> execute this document's FULL_USER_E2E profile unless explicitly scoped
-> use real public CLI and real traffic
-> exercise ALLOW and DENY
-> execute performance in every required direction, ramp to the selected target or practical saturation boundary, use multiple load generators where available, identify the actual saturation limiter, and recheck recovery after stress
-> classify every reachable configured test host, assign every suitable host an active role, and use the maximum practical real topology rather than a minimal sufficient topology; never require provisioning additional hosts for FULL_USER_E2E
-> bring all applicable test hosts online simultaneously and execute parallel multi-host gates
-> assign ChatGPT an explicit production persona/mission (End User, Agent Operator, DRLink Administrator, Incident Responder, or Platform Maintainer) for every use-case lane
-> begin each role as a user who does not know the command set: discover through drlink, ?, help, help commands, menu, Tab, wizard/error guidance
-> treat every command snippet in this scenario document and section 14 as an auditor oracle, not prior knowledge for the acting user
-> map every discovered/oracle command and behavior-changing variant into a real use case and exhaust the command ledger through those use cases
-> repeat high-risk state-changing workflows and vary state/order/concurrency/recovery according to section 1.3.2; one successful execution is not sufficient
-> inject realistic User/Operator/Administrator mistakes from section 1.3.3 and recover only through CLI/AI-visible guidance or minimum test-host/test-state recovery
-> start each independent use-case lane as soon as enough public UX has been discovered; do not wait for serial happy-path completion
-> keep all DRLink control/configuration/lifecycle actions CLI-only
-> execute every applicable use case again through AI assistance from the same natural-language goal, using only user-visible CLI/menu/help/wizard/error/status output for recovery; acting personas do not consult manuals/runbooks
-> exercise AI one-shot, AI error-correction, AI ConfigurationBundle, Export->AI->Reapply, and cross-context split workflows
-> continuously audit every user-visible surface for terminology drift, ambiguity, role/context confusion, misleading state, invalid/stale generated guidance, unclear impact, and missing next actions
-> retain evidence
-> report every skipped/blocked scenario honestly
~~~

# Appendix A — historical v2.4 manual runbook status

The former Rick/manual v2.4 runbook has been **fully absorbed into sections 1–18** of this canonical contract.

It is intentionally not retained as a second executable procedure because its fixed hostnames, operator-preparation steps, manual worksheets, and pre-run prerequisites conflict with automatic host discovery and immediate execution.

For FULL_USER_E2E:

~~~text
SECOND_EXECUTABLE_RUNBOOK=NO
FIXED_HISTORICAL_HOSTNAMES=DO_NOT_USE
ASK_OPERATOR_TO_FILL_WORKSHEET=NO
ASK_OPERATOR_TO_CHOOSE_TEST_HOSTS=NO
ASK_OPERATOR_TO_PREPARE_VALUES_ALREADY_DISCOVERABLE=NO
CODE_CHANGE_DURING_ACTIVE_RUN=NO
DOC_OR_TEST_CONTRACT_CHANGE_DURING_ACTIVE_RUN=NO
CANDIDATE_REBUILD_DURING_ACTIVE_RUN=NO
TEST_ENVIRONMENT_RECOVERY_ONLY=YES
CONTINUE_INDEPENDENT_TESTS_TO_EXHAUSTION=YES
~~~

If an external prerequisite cannot be discovered or safely satisfied automatically (for example an unavailable public DNS/TLS integration), classify only that dependent scenario as `BLOCKED_ENVIRONMENT` and continue all independent scenarios. Do not stop the full run to ask for setup unless the user explicitly asks to resolve that external prerequisite.

# Appendix B — deterministic trigger lookup

The canonical file name is deliberately stable. On `dev-drlink`, the machine-level active-worktree pointer is also stable:

~~~text
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/FULL_USER_E2E_SCENARIOS.md
ACTIVE_WORKTREE_POINTER=/home/aella/datarelay-link-current
CANONICAL_CONTRACT=/home/aella/datarelay-link-current/docs/FULL_USER_E2E_SCENARIOS.md
~~~

The process's initial current working directory is not authoritative. In particular, `/home/aella/datarelay-link-dev` is the historical Git main worktree and may intentionally remain on an older branch. Its branch/HEAD must not be used to decide whether FULL_USER_E2E can start.

Treat these as direct execution triggers, case-insensitively and with equivalent Korean/English wording:

~~~text
사용자 E2E
사용자 E2E 테스트
Full User E2E
Full User E2E 테스트 시작
FULL_USER_E2E
User E2E
전체 E2E
전수 사용자 테스트
full user e2e 수행해
GitHub에서 FULL_USER_E2E 문서 찾아서 수행해
Github에서 FULL_USER_E2E 찾아서 테스트 진행해
~~~

On a trigger, the minimum startup sequence is:

~~~text
1. Resolve `/home/aella/datarelay-link-current` and immediately use that directory as the active Data Relay Link worktree when it contains `AGENTS.md`, `.engineering/project.yaml`, and `docs/FULL_USER_E2E_SCENARIOS.md`; record `WORKTREE_RESOLUTION=PASS` and continue. Do not inspect the initial cwd's branch or compare historical worktrees merely to decide where to start. If the exact local canonical file is absent, resolve `datarelay-labs/datarelay-link/docs/FULL_USER_E2E_SCENARIOS.md` on the active branch/ref before any broader fallback; do not perform broad GitHub search or unrelated repository discovery.
2. Open the resolved canonical `docs/FULL_USER_E2E_SCENARIOS.md` as the execution contract; all embedded command examples and section 14 are auditor expectations only and are not used as the acting user's memorized command script.
3. Capture current candidate/build identity without code review. The active worktree's test-contract HEAD and the installed candidate/build identity may differ and must be recorded separately; that difference is not a reason to search for another worktree.
4. Read the development host's ~/.ssh/config and any untracked local run inventory; resolve SSH routes per section 5.1 without using lab literals from this tracked contract.
5. Probe configured hosts in parallel.
6. Classify every reachable configured host, assign every suitable host an intended Server/Agent/Relay/client/target/load-generator/recovery role, and record any unused reachable host with a concrete reason.
7. Execute the section 5.3 clean-room gate on every assigned host: inventory old state, use supported product uninstall for fresh lanes when an immutable candidate artifact is available, stop previous E2E/load runtimes, remove disposable old artifacts and stale/broken product service-unit links, verify product listeners/state are gone, record the development worktree state, pin the installed candidate identity, never build/install from dirty source, and explicitly record preserved management-access infrastructure.
8. Do not start product discovery or create PASS-eligible state until ALL_REACHABLE_ASSIGNED_HOSTS_CLEAN=PASS. Then create the new RUN_ID/current-run test state and open the section 5.4 process/session registry.
9. On every freshly installed/assigned Server/Agent role, start public command discovery in parallel with drlink, ?, help, help commands, menu, Tab and visible wizard/error guidance.
10. Build the runtime command/variant ledger and map discovered capabilities to realistic use-case lanes; section 14 is auditor-only omission detection.
11. Before each lane, assign ChatGPT an explicit End User, Agent Operator, DRLink Administrator, Incident Responder, or Platform Maintainer persona plus a production-style mission; create RUN_ID-scoped namespaced resources and immediately start every independent use-case lane whose prerequisites are discovered.
12. Run Direct CLI, guided/TTY, adversarial, multi-platform enrollment, real-traffic, AI-assisted mirror and performance lanes concurrently at maximum practical utilization of the currently configured hosts; never pause to request new test hosts. Progressively ramp performance toward the selected target or practical saturation boundary. Apply section 1.4.1 prerequisite, evidence-reuse, FAIL_PRECONDITION, and bounded performance-stop rules.
13. Behave like a real operator who has not read the manual: pursue the mission, follow product output/next actions, copy/paste generated commands, make realistic mistakes from section 1.3.3, recover only from user-visible CLI/AI guidance or minimum test-host/test-state recovery, and continuously record terminology/clarity/cross-surface inconsistencies.
14. Continue discovery and use-case execution together until no discovered/oracle command or behavior-changing public variant lacks disposition.
15. Execute each applicable use case again through AI assistance from the same goal and equivalent namespaced starting state, then satisfy the repetition/sequence-permutation minimums from section 1.3.2 for high-risk workflows.
16. If one lane is blocked by tooling/environment/management-path or fails a functional prerequisite, record only that lane as BLOCKED_TOOLING/BLOCKED_ENVIRONMENT/BLOCKED_MANAGEMENT_PATH/FAIL_PRECONDITION as applicable and continue every independent lane immediately.
17. Do not inspect product source, test source, internal DB/state, or harness implementation during active discovery.
18. Run mixed function-under-load, policy-mutation, restart/reconnect, outage, race and all-host scenarios continuously; execute P-024 collision rows while representative load is active, then execute P-023 maximum-topology mixed stress with multiple load processes/generators on the existing test hosts where available and verify post-saturation recovery without redundant saturation against already-failed functional paths.
19. Finish command/use-case/AI-mirror/repetition/mistake/function-under-load disposition, process-registry cleanup and final reporting. Do not modify product code, rebuild the candidate, or start Cursor as part of this trigger. Any implementation/harness diagnosis is a separate post-run engineering action.
20. After the full executable run is exhausted and evidence/counters are frozen, update the active `[AI Work]` Issue once with the consolidated result. Do not perform intermediate per-finding Issue updates.
~~~

No additional planning document, old audit document, historical evidence review, Cursor run, or human host-selection step is a prerequisite.
