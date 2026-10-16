# Data Relay Link v2.4.0 — CLI-only Full Functional E2E (100 scenarios)

> **Status:** Independent, executable CLI-only user test contract. **Not** Full User E2E / MCP / AI qualification.
> **Source:** `docs/FULL_USER_E2E_SCENARIOS.md` (all 116 original IDs and headings preserved in its canonical document).
> **Product baseline:** v2.4.0 **includes** AI Access and MCP Bridge; they are excluded **only from this test profile**, not removed from the product.
> **Executor:** current owner-selected runtime (default `CHATGPT_CHAT`); current explicit instruction overrides historical Codex-only text.
> **Canonical Full User E2E SHA256:** `60f93f0119545d712c9d73440c8c8dad4db5caad34206785c4b7df5bd54ca259`
> **Generation:** `python3 tools/generate_cli_only_e2e_contract.py --write`; `--check` verifies no source drift.
> **Safety:** preserve current authorization, exact live platform/tool refusals, other actors, host ownership and management access; never reroute a denied effect.
> **Candidate:** do not infer installed Source HEAD from a Git checkout; record each installed Server/Agent's provenance.

## 1. Scope and complete original-ID traceability

- **Canonical parent:** 116 scenarios (13 U, 15 O, 20 A, 20 S, 15 C, 24 P, 9 X).
- **CLI-only:** 100 retained original IDs, including mixed IDs with only the specifically excluded AI/MCP substeps removed.
- **Excluded AI/MCP-only:** U-007, U-011, O-013, O-014, A-006, C-006, P-011, X-001, X-002, X-003, X-004, X-005, X-007, X-008, X-009, X-010. Record `EXCLUDED_AI_MCP`, **never PASS**.
- **Mixed IDs, non-AI parts mandatory:** U-009, U-013, A-004, A-007, A-009, A-011, A-012, A-016, S-017, S-024, C-015, P-023, P-024.
- The existing `tools/cli_only_e2e_inventory.py` is the authoritative 116-ID ledger initializer. Every scenario heading and applicable requirement from the parent is retained below, not only linked indirectly. The precise excluded substeps are described at the affected headings; no other steps may be excused for being in a mixed ID.
- Direct CLI, help/`?`, menu, REPL, Tab and wizard UX, installers/upgrade/uninstall, configuration bundle, Remote/Internet Access, real SSH/SCP/HTTP/HTTPS/TCP, proxy application traffic, host lifecycles, policy ALLOW/DENY, failure/recovery, all available-host concurrency and real performance remain in scope.
- Each direct-user PASS needs **actual public** drlink command, observed effects, truthful exit codes and full evidence. CLI-only evidence never grants full 116-scenario User E2E PASS or a v2.4.0 release gate. Full User E2E still requires genuine AI/MCP tests, full release gates and two complete same-HEAD passes.

## 2. Start eligibility: no global test-start gate

1. Resolve `datarelay-labs/datarelay-link`, read `AGENTS.md`, `.engineering/project.yaml`, current installed candidate identities and this entire executable contract before the first user action.
2. Inspect branch/HEAD/dirty status, active owners and existing RUN_ID/processes **once**. Do not start a competing actor, repin its candidate, edit its owned state or replace its evidence. Use independent safe resources/hosts. A live actor owns only its own mutable scope, not the entire lab.
3. **There is no global LAB_GO** or `phase-state.json`, universal host-GO, AI/MCP/OAuth readiness, FCS completion, whole CI wait, newly created VM/snapshot or repeated owner permission required to begin an independently runnable CLI scenario.
4. Dirty worktree: never build a falsely qualified candidate from uncommitted source. Continue public CLI observations against a truthfully pinned existing installation, with its actual `INSTALLED_HEAD`; only exact matching candidate evidence may become candidate PASS.
5. Missing prerequisite blocks only the dependent action. `ENVIRONMENT_BLOCKER` must mean demonstrated host/topology/required external resource unavailability, not a personal preference, stale report, absent release SLO or unstarted setup work.
6. Historical platform/tool refusal is **evidence to re-check under present policy**, not a permanent ban. An actual current denial remains binding for that **exact operation**: do not bypass it by changing executor, sandbox, host, command, identity, permissions or route. Record tool, host, attempted command, literal error and impact, continue independent checks. High-risk production/credential/permission/release effects still need their own authority.
7. Separate the functional Server (`frp-e2e-server`) from the owner-assigned public DNS/hostname Server (`frp-release-server`) when applicable. Ordinary CLI, lifecycle, traffic, concurrency and performance use the functional Server; public hostname/DNS-specific substeps use the approved DNS target. Missing DNS affects only those substeps.
8. All claims require **actual public CLI actions** through `drlink`; helper scripts can orchestrate/measure/record but cannot replace a user-role discovery path, a real confirmation or actual application traffic. Every per-host prerequisite and effect must be observed directly. Interactive PTY/TTY is required **only for an operation whose public CLI contract needs it**; a failed TTY tool blocks its interactive criterion alone. Do not turn CI, source inspection or scripted PASS into user E2E PASS.

## 3. Per-run state, ownership, lifecycle and evidence

- Generate one private persistent `RUN_ID` directory outside `/tmp`, mode 0700; secret-bearing evidence mode 0600. Initialize **116 original ledger rows** (100 CLI-only + 16 exclusions) using:

  `python3 tools/cli_only_e2e_inventory.py init --run-root <PRIVATE_RUN_ID> --source-head <FULL_40_CHARACTER_GIT_SHA>`

- Record per action `RUN_ID`, scenario/substep/repeat, actual host and role, Source/Installed HEAD, public exact command, stdout/stderr (redacted), exit code, UTC start/end, observed service/traffic effect, SHA256 of receiver payload if applicable, and run-owned cleanup result.
- Before each host's first **mutating** CLI test, inventory previous actors' immutable evidence and resources. Clean **only resources of the current run or expressly disposable test-owned resources**, via documented public lifecycle paths. Do not delete other worker resources, customer data, management tunnels/SSH, preserved previous-run evidence, or globally reset a host merely to obtain a label. If a clean-install scenario really requires a clean host, use an independently owner-authorized disposable host; inability to obtain it blocks **that** fresh-install scenario, not all existing-installed behavior.
- Preserve persistent client identity, Service IDs, allocated public ports, security policy and rollback state according to each scenario. Include genuine negative tests and recovery; valid pre-existing tests are not repeated merely for different ledger IDs when direct same-run evidence legitimately satisfies both.
- When a candidate mismatch exists, record stale runtime as correlation only. After fixes freeze old evidence; install a new immutable qualified candidate on a separately authorized host and re-run affected conditions at its exact HEAD.
- Any currently denied Functional Server uninstall (historically B014) or other high-risk native effect must be re-evaluated on the **same authorized tool/target under current policy**. If the current attempt is denied, retain the precise denial and leave only the dependent test blocked; never alter route or use an alternative actor to defeat it.

## 4. Real topology, timing and performance

- Run real User, Operator, Administrator, Incident Responder and Platform Maintainer missions through the visible CLI. Vary fresh/existing/stale state, command order, direct/REPL/wizard presentation, selector/role/negative input, previous failed mutation, and recovery wherever applicable. Capture genuine public `drlink` behavior before looking at implementation.
- Use actual suitable Linux/Windows/macOS Agent and target hosts where present; preserve native OS and all-host limitation receipts. Do not require hypothetical host tiers or an unrelated extra VM.
- Functional load requires **60-second warmup**, **300-second steady state for every applicable case**, and **P-013 3,600-second functional soak** once representative real application data paths work. **P-019 8h/24h is optional until explicitly selected.**
- Exact labels retained for machine audit: `WARMUP=60s`, `STEADY_STATE_EACH_CASE=300s`, `SOAK=3600s`, `EXTENDED_SOAK=8h`, `ENDURANCE_SOAK=24h`; only the last two require explicit selection.
- Run independent persistent workloads via managed `tmux`/systemd/equivalent when a connection cannot guarantee process lifetime. Retain PID/session, start/end UTC, real 60/300/3600-second samples and terminal results; do not claim elapsed PASS from an active PID or timer.
- Measure receiver-confirmed 1KiB/64KiB/1MiB and stream/full-duplex goodput, checksum, CPS, 4/16/64+ connections, p50/p95/p99 latency, CPU/RSS/FD, mixed applications, denied traffic, saturation and function-under-load collision/recovery. Apply existing approved numeric SLOs without weakening them. **Unknown numeric SLO** is `MEASURED_NOT_QUALIFIED` for numeric qualification only, never justification to skip runnable functional measurements or hide actual errors.

## 5. Dispositions and truthfully separate completion gates

Allowed outcomes: `NOT_RUN`, `IN_PROGRESS`, `PASS`, `FAIL`, `PARTIAL`, `FAIL_PRECONDITION`, `BLOCKED_ENVIRONMENT`, `BLOCKED_TOOLING`, `BLOCKED_PLATFORM_DENIAL`, `BLOCKED_MANAGEMENT_PATH`, `MEASURED_NOT_QUALIFIED`, `EXCLUDED_AI_MCP`; `P-019` may remain `NOT_RUN` when unselected. Always distinguish `BLOCKED` vs `FAIL`, the product cause vs management/tool limitations, candidate qualification vs valid installed-version behavior, functional PASS vs unqualified numeric SLO.

- `EXECUTABLE_SCOPE_COMPLETE`: every safe runnable original CLI-only criterion has a supported result or a concrete, attributable dependency-specific blocking record. No missing substeps hiding behind a completed parent row.
- `ALL_APPLICABLE_CLI_E2E_PASS`: every required CLI-only criterion and its native/traffic/performance conditions is qualified PASS on the exact candidate, with no unresolved mandatory defect or blocker. Optional profiles are identified separately.
- Neither status implies `FULL_USER_E2E_PASS`, AI/MCP acceptance, a production deployment, a release, merge/tag or owner acceptance.
- A tool or platform failure should be attempted/recorded as a bounded concrete operation and **must not be inflated into a global blocker**. Close out run-owned resources via public paths and report which original IDs remain FAIL/PARTIAL/BLOCKED/NOT_RUN.

## 6. Non-AI/MCP scenario matrix: exact preserved original requirements

The following bodies are extracted from the current canonical Full User E2E. They retain original IDs, titles, assertions, negative/recovery/performance requirements and order, except explicit AI/MCP-only scenarios/substeps. Headings in the source remain authoritative; if the source changes, regenerate and review the diff rather than silently using a stale copy.

### Preserved original shared execution criteria

### 1.3.2 Mandatory repetition and sequence-permutation contract

A single successful execution never closes a high-risk state-changing workflow. CLI_ONLY_E2E must repeat operations with different starting state, order, concurrency, and recovery conditions so accidental one-shot success cannot hide stale-state, idempotency, race, or lifecycle defects.

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
~~~

Repetition must vary at least one meaningful dimension rather than replaying identical commands blindly: fresh/existing/stale state; alternate lifecycle order; one-shot/REPL/wizard surface; Direct CLI execution; idle/loaded system; single/concurrent writer; host/platform/role; normal/cancel/interrupted/retry path; or valid boundary/invalid boundary+1.

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

The acting User, Operator, Administrator, Incident Responder, and Platform Maintainer must complete the run without consulting the product manual, runbook, scenario command examples, private CLI Master, source code, test code, or hidden state. They may use only the installed product's public UX; this direct-only profile does not include an AI Adviser.

~~~text
ACTING_PERSONA_MANUAL_ACCESS=FORBIDDEN
ACTING_PERSONA_RUNBOOK_ACCESS=FORBIDDEN
ACTING_PERSONA_SOURCE_ACCESS=FORBIDDEN
ACTING_PERSONA_ALLOWED_DISCOVERY=DRLINK_ENTRY|MENU|QUESTION_MARK|HELP|HELP_COMMANDS|TAB|WIZARD|ERROR_OUTPUT|STATUS_OUTPUT
AUDITOR_CANONICAL_DOC_RECONCILIATION=POST_HOC_ONLY
~~~

Deliberately inject realistic mistakes across all roles. At minimum, when the relevant surface exists, cover wrong role/context, shell-vs-REPL/menu/wizard confusion, privilege mistakes, blank/typo/case/reserved/duplicate/ambiguous/stale selectors, malformed or out-of-range addresses/ports/URLs/TTLs/files/Bundles/stdin, wrong dependency/order, referenced-object deletion, repeated apply/delete/create, stale revisions, cancel/back/interruption, expired/reused enrollment, wrong hostname/server URL, omitted optional fields, wrong SSH username assumption, revoked credentials, DNS/TLS/target/Agent/Server/network failures, and concurrent same-name/same-object/last-slot/delete-vs-traffic/edit-vs-traffic/restart-vs-mutation races.

Mistakes must stay inside the designated test estate. Recovery must come from public CLI guidance using only user-visible output; source-level knowledge does not count.

Required gate:

~~~text
DELIBERATE_MISTAKE_CLASSES_APPLICABLE=
DELIBERATE_MISTAKE_CLASSES_EXECUTED=
DELIBERATE_MISTAKE_COVERAGE=100%
RECOVERY_USING_ONLY_CLI=100%
UNDOCUMENTED_KNOWLEDGE_REQUIRED=0
~~~

### 1.4.1 Scenario prerequisites, evidence reuse, and bounded stop rules

Every scenario must declare or inherit the functional prerequisites it needs (reachable host role, enrolled Agent, live data-plane path, prior-stable fixture state, capacity remaining, and so on). Before heavy or destructive work, check those prerequisites against current-run evidence.

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

Keep `CLI_ONLY_E2E_SCOPE=PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL_NO_AI_MCP`. Do not reintroduce source-level implementation diagnosis or separate security/compliance audit work during the active run.

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
- Custom TCP transfers application data in both directions during an ordinary full-duplex session;
- wrong endpoint/port does not accidentally reach another target.

For v2.4, do not use an EOF-response protocol that requires client write-half-close preservation as the required Custom TCP acceptance client. The pinned official FRP 0.71.0 does not support that response-after-EOF semantic through its TCP proxy:

~~~text
CUSTOM_TCP_HALF_CLOSE=UNSUPPORTED_FRP_0_71_0
~~~

This is a scoped transport limitation, not a waiver of the mandatory ordinary Custom TCP real-traffic test above.

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

Remote Access enforcement disable must preserve Mode/Rules and temporarily yield effective ALLOW ALL according to the canonical Remote Access contract.


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

For shell-based proxy-aware applications on Linux/macOS, run the applicable U-006/U-012 application probes in a **dedicated subshell/process** so the parent shell's proxy environment is unchanged when the scenario ends:

~~~bash
(
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

  # Execute the required curl/wget/git/apt probes and evidence capture here.
)
~~~

Merge and preserve the pre-existing `no_proxy` and `NO_PROXY` bypass entries needed for management endpoints or internal services, append localhost, then export the same merged list under both casings so application precedence cannot drop an existing bypass. The dedicated subshell/process is **mandatory** for these shell-based qualification probes; do not export the test proxy variables directly into a long-lived operator/test shell. Exiting or interrupting the dedicated process must leave the parent shell's `http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `no_proxy`, and `NO_PROXY` states unchanged.

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
- when a Managed Host is used as the Internet Access source, compare the source address assumed by `test internet-access` with the actual proxy peer source seen by the Server; if NAT/source mismatch prevents Managed Host identity from being proven, the WHITELIST rule must not match and the request must DENY fail-closed.


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
PUBLIC_TERM=
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

The Incident Responder and first-time Operator personas must be able to recover from representative failures using only visible status/diagnostic/error/help guidance. If an operator must guess hidden syntax or consult auditor-only knowledge to continue, record a discoverability/clarity defect.

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
system update product
system update engine
system version
~~~

Server (read-only upstream release inspection):

~~~text
system update check-engine
system version
~~~

Verify product and upstream engine versions remain separate, Server check-engine is read-only, Agent product and engine updates are independently discoverable/actions, update does not require ordinary re-enrollment, and endpoint/identity/state are preserved. The Agent must not advertise a Server-only check-engine action; an Agent invocation must give an actionable Server-only explanation without changing Agent state.


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
- Remote Access policy reset removes Mode and Rules and returns No Policy / ALLOW; Internet Access reset return No Policy / DENY;
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

Exercise real traffic plus the applicable failure/recovery cases in section 10. Internet Access is WHITELIST-only: prove direct Managed Host source-address match can ALLOW an approved flow, NAT/source mismatch fails closed to DENY, No Policy is DENY, BLACKLIST configuration is rejected, and Enforcement DISABLED preserves Mode/Rules while producing DENY ALL.


## A-007 — Reference protection — MANDATORY

Attempt to delete referenced Network Object, Network Group, Service Object, Service Group, and referenced Managed Host.

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

A known-invalid restore archive must fail before offering live replacement confirmation. Restored backup-time host presence and proxy verification are stale: require fresh Agent runtime verification and actual SSH/HTTP/TCP traffic recovery on the preserved identities/endpoints before accepting restored health.

Restore into the supported clean/recovery topology.

Verify preservation of:

- trust/PKI;
- Managed Host identity;
- Remote Services and endpoint reservations;
- Objects/Groups;
- all policy families;
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
system audit
system history
system clear
system update product
system update check-engine
system update engine
system support-bundle
~~~

Verify stable/preview/development identity and exact Source HEAD are truthful, diagnostics are read-only, history/clear behave as documented operator surfaces without unintended product-state mutation, product vs Relay Engine update/check semantics remain distinct, and support output is operationally useful.



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

Use the current authoritative limits from the current v2.4.0 CLI Reference and release validation at execution time.


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


## A-016 — Direct CLI workflow and traceability audit — MANDATORY

At the end of CLI_ONLY_E2E, produce a machine-readable or clearly auditable mapping:

~~~text
PUBLIC_CLI_COMMAND_OR_VARIANT
-> DISCOVERY_SOURCE(menu|?|help|Tab|error|doc-reconciliation)
-> USE_CASE_ID
-> SCENARIO_ID
-> HOST/ROLE
-> DIRECT_RESULT/EVIDENCE
~~~

Every applicable runtime-discovered/reconciled public command and behavior-changing variant must have at least one current-run Direct execution record **inside a real use case**. Section 14 is reconciled after public discovery; it is not the human operator's command script.

Separately map every canonical current v2.4.0 CLI Reference scenario relevant to the current candidate, including:

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
- missing dependency;
- Server and Agent ConfigurationBundle;
- final-Resource Bundle failure;
- idempotent reapply;
- test A/apply B;
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

Before the first mutation, capture the current values of all four settings. The scenario may exercise clear/unset behavior, but **cleanup is part of PASS**: before leaving A-018, restore every setting to its exact pre-scenario value (including an originally configured `bootstrap_hostname` and installer URLs) and re-read the resulting onboarding output. A scenario that leaves the Server in its temporary cleared/test value is FAIL because it contaminates later Zero-Touch and provenance tests.

After each relevant change, regenerate or inspect:

- Enrollment endpoint;
- Zero-Touch launcher/short URL;
- Linux installer URL;
- Windows installer URL;
- Remote Service endpoint presentation where applicable;
- diagnostics/version/support evidence.

Verify no change to an optional friendly hostname silently changes control/allocator identity unless the current product contract explicitly says so. Verify Linux and Windows onboarding receive the intended platform-specific installer URL and that clearing optional overrides returns to the supported default. After cleanup, verify the restored Zero-Touch command mode matches the pre-scenario mode (short URL versus pinned-CA fallback) rather than merely checking that the fields are syntactically present.


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

Half-close remains mandatory on any release surface that claims it. For v2.4 Custom TCP, the response-after-EOF write-half-close subcase is NOT_APPLICABLE by explicit product contract because the pinned official FRP 0.71.0 TCP proxy does not preserve that semantic.

~~~text
CUSTOM_TCP_HALF_CLOSE=UNSUPPORTED_FRP_0_71_0
CUSTOM_TCP_HALF_CLOSE_E2E=NOT_APPLICABLE
~~~

Record this scoped limitation with the official-FRP isolation evidence. Long-lived Custom TCP, ordinary bidirectional traffic, normal close, abrupt close/recovery, idle behavior, cleanup, and new-connection correctness remain mandatory.


## S-023 — Bootstrap catalog false-HEALTHY prevention — MANDATORY

Use a clean Agent enrollment with an initial Remote Service whose local target is reachable. Verify public CLI does not report HEALTHY before actual relay/runtime verification, then complete real external traffic and verify the transition to HEALTHY on the same identity and endpoint.


## S-024 — Human/operator/admin misconfiguration and recovery matrix — MANDATORY

Execute the deliberate-mistake classes from section 1.3.3 across realistic User, Agent Operator, Administrator, Incident Responder, and Platform Maintainer missions. Each mistake must occur inside a real task, not as isolated parser fuzzing, and recovery must use only public CLI guidance grounded in user-visible output.

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

Use the maximum safe concurrency available on the current hosts and overlap independent real-world mistakes and recovery work: stale/conflicting Administrator changes, wrong-selector Agent Operator recovery, long-lived/short-lived End User traffic during independent service lifecycle changes, Incident Responder outage diagnosis while normal work continues elsewhere, and direct CLI work in parallel with a Direct lane on isolated namespaced state.

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

The mandatory soak is a quality gate, but it is **not a serial end-of-run wait**. Start it as soon as a stable representative traffic/topology baseline exists and overlap independent persona, recovery, read-only, isolated-load lanes whenever state isolation permits. Do not leave runnable work idle merely because the soak clock is running.

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

If persistent functional data-path failures already make an all-host PASS impossible, collect the minimum mixed-stress diagnostic sample needed to characterize control-plane responsiveness under residual load, classify dependent saturation claims with `FAIL_PRECONDITION` / inherited FAIL per section 1.4.1, and do not repeat full-topology soak/saturation solely for this label.

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
- new enrollment and Agent reconnect activity;
- Remote Service create/edit/disable/enable/delete on independent hosts;
- Remote/Internet Access policy reads/tests and selected isolated mutations;
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
MIXED_PROTOCOL_LOAD + DIRECT_CLI_CONTROL_OPERATION_ON_ISOLATED_STATE
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

For CLI_ONLY_E2E, test every platform currently claimed by the candidate at its actual qualification level.

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

At least one CLI_ONLY_E2E pass must also prove the entire available matrix concurrently via C-001 through C-012; per-platform serial PASS alone is insufficient for the all-host simultaneous gate.

## 13.1 Topology matrix

CLI_ONLY_E2E must qualify every topology currently claimed by the candidate. Record unsupported/unclaimed topology explicitly rather than silently skipping it.

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

This section mirrors the public v2.4.0 direct CLI Reference. It is a coverage checklist, not a second grammar authority.

CLI_ONLY_E2E requires every applicable entry below to be executed through the public CLI at least once and linked to scenario evidence. Presence in this list alone does not count as coverage.

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

unset network-object <OBJECT>
unset network-group <GROUP>

unset service-object <SERVICE>
unset service-group <GROUP>

unset remote-access <RULE>
unset remote-access policy

unset internet-access <RULE>
unset internet-access policy



~~~

## 14.4 Server test

~~~text
test remote-access source <SOURCE> destination <DESTINATION> service <SERVICE>
test internet-access source <SOURCE> destination <DESTINATION> service <SERVICE>
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



system update product
system update engine
system update check-engine


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

These are not DRLink grammar, but CLI_ONLY_E2E must use real clients appropriate to the service:

~~~text
ssh / scp / sftp
curl
wget
git
apt
real HTTP/HTTPS client
real Custom TCP client
performance load generator
~~~

Use only the commands actually applicable to the target OS/application.

# 15. CLI-only provenance and report

Retain the 116-row original-ID inventory and machine-readable ledger from
tools/cli_only_e2e_inventory.py. A qualified PASS requires actual matching
installed Source HEAD, direct user action/traffic evidence and verified cleanup.
Report all 100 CLI-only outcomes and 16 EXCLUDED_AI_MCP outcomes with true
substep, platform, performance and safety dispositions. This does not confer
Full User E2E PASS, AI/MCP acceptance or v2.4.0 release authority.

Refer to docs/CLI_ONLY_E2E_BLOCKER_AUDIT.md for a per-contract assessment of
real prerequisites versus artificial test-start restrictions.
