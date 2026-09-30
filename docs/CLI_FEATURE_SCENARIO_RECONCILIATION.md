# Data Relay Link — Feature ↔ CLI ↔ Operator Workflow Reconciliation

> **Document role:** Canonical non-destructive audit contract for product capability ↔ public CLI ↔ operator workflow coherence
> **Executor:** ChatGPT
> **Scope:** feature/CLI/workflow completeness, uniqueness, discoverability, terminology, procedure, structure, safety contract, recovery guidance, and audit cleanup
> **Target:** v2.4 and later until superseded
> **Execution boundary:** this audit is **runtime non-destructive**. It never changes Data Relay Link product state.
> **Release relationship:** release qualification may consume a completed reconciliation result, but candidate installation/lifecycle qualification belongs to release/FULL_USER_E2E workflows
> **Companion:** `CLI_EXHAUSTIVE_AUDIT.md`

## 1. Exact execution trigger

The following requests are **immediate execution commands**, not requests for a plan:

~~~text
CLI, 기능, 시나리오의 연계성을 테스트 진행
CLI 기능 시나리오 연계성 테스트
CLI-기능-시나리오 연계 테스트
기능과 CLI와 시나리오 매핑 테스트
Feature CLI Scenario reconciliation
Feature CLI Operator Workflow reconciliation
CLI product-surface reconciliation
GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해
Github에서 CLI_FEATURE_SCENARIO_RECONCILIATION 찾아서 테스트 진행해
CLI_FEATURE_SCENARIO_RECONCILIATION 테스트 진행해
~~~

### Deterministic document resolution

Do not begin with broad/global GitHub code search, unrelated repository search, host discovery, CI inspection, or release preparation.

~~~text
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md
ACTIVE_WORKTREE=/home/aella/datarelay-link-current
~~~

Resolution order:

1. identify `datarelay-labs/datarelay-link`;
2. resolve `/home/aella/datarelay-link-current`;
3. read the exact canonical path from the active branch/worktree;
4. if that exact path is absent locally, resolve the same path from Git history or the same GitHub repository;
5. only if the canonical repository/path itself changed may repository history be used to locate its successor.

Do **not** wander through unrelated repositories, hosts, similarly named files, or broad GitHub code search results.

Once this document resolves, start the audit immediately. Do not stop to propose a plan.

### Meaning of Scenario

`Scenario` means an **operator workflow audit scenario**: verify that a user can discover and understand the complete CLI lifecycle from one step to the next.

It does **not** mean executing live state-changing operations.

### Hard non-destructive boundary

Runtime use is read-only. Do not execute commands that create, modify, delete, reset, revoke, release, apply, rollback, restore, update, uninstall, restart, pause/resume, synchronize, issue credentials/tickets, change policy, change endpoint allocation, or otherwise persist product state.

Mutation-bearing workflow steps are audited through public help/`?`/Tab/menu, catalog/parser/source enumeration, active documentation, and deterministic isolated tests.

Do not install, upgrade, uninstall, reboot, provision, repair, recover, or search for replacement Server/Agent hosts.

Do not substitute FULL_USER_E2E, an installation/lifecycle test, a generic CLI smoke test, or historical evidence.

### Continuous execution / finding accumulation rule

A finding is **not a stop condition**.

For every finding:

1. preserve evidence;
2. classify it;
3. add it to the current run finding ledger;
4. remember it for final reporting;
5. immediately continue every remaining independent non-destructive check.

Do not patch product code during the active audit.

Do not stop to update GitHub Issue when a finding appears. Intermediate findings remain in the run evidence ledger.

Stop only the specific check that cannot safely continue. Mark only that check `BLOCKED` or `NOT_RUN` with the exact reason and continue all other independent checks.

Update the active `[AI Work]` GitHub Issue **once, after the audit has exhausted all executable checks and final counters/summary are complete**.

### Maximum-safe parallel execution — hard gate

Independent checks must run in parallel whenever their prerequisites are satisfied and they do not share unsafe mutable state.

Do not wait for one slow isolated suite, document scan, parser/catalog enumeration, or read-only runtime probe to finish when other independent checks are runnable.

Preserve the `BLACK_BOX_FIRST` phase boundary: retain public/runtime discovery evidence before post-hoc source/parser enumeration. Within each allowed phase, start all independent lanes immediately.

Parallelize at minimum when applicable:

- independent read-only `drlink` help/`?`/show/status/version/diagnostic/test-explain probes;
- FCS workflow audits that depend only on already-captured discovery and do not mutate runtime state;
- active-document/example/terminology scans;
- catalog, parser, hidden/alias, destructive-metadata, and role-surface enumeration after black-box evidence is frozen;
- independent deterministic isolated test files/suites, including long-running MCP/TLS/configuration/recovery suites;
- evidence classification and ledger construction that write to separate lane files.

Serialize only when technically required by:

- the black-box-before-source phase dependency;
- a true test prerequisite;
- a shared temporary path, port, fixture, database, lock, or other state that the isolated tests themselves do not safely namespace;
- one interactive TTY/session that cannot be used concurrently without corrupting evidence;
- final aggregation of counters/evidence.

A blocked or slow lane does not pause other lanes. Tool/safety rejection in one lane must be recorded there while equivalent or independent lanes continue.

Each parallel lane writes separate evidence first; merge only after the lane completes so concurrent writers cannot corrupt the finding ledger.

Required execution evidence:

~~~text
PARALLEL_EXECUTION=MAXIMUM_SAFE
PARALLEL_LANES_STARTED=
MAX_SIMULTANEOUS_ACTIVE_LANES=
SERIAL_IDLE_WITH_RUNNABLE_WORK=NO
AVOIDABLE_SERIAL_WAIT_COUNT=0
~~~

A run that intentionally leaves independent runnable checks idle while waiting on another check is execution-incomplete and must not claim terminal PASS until those checks are exhausted.

~~~text
AUDIT_PROFILE=CLI_FEATURE_SCENARIO_RECONCILIATION
AUDIT_SEMANTICS=FEATURE_CLI_OPERATOR_WORKFLOW
FIRST_ACTION=EXECUTE
CANONICAL_REPO=datarelay-labs/datarelay-link
CANONICAL_PATH=docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md
PUBLIC_DRLINK_ONLY_FOR_USER_SCENARIOS=YES
BLACK_BOX_FIRST=YES
POST_HOC_HIDDEN_SURFACE_ENUMERATION=YES
RUNTIME_MUTATION_DURING_AUDIT=NO
DESTRUCTIVE_COMMAND_EXECUTION=NO
PRODUCT_SOURCE_EDITS_DURING_AUDIT=NO
INTERMEDIATE_GITHUB_ISSUE_UPDATE=NO
FINAL_GITHUB_ISSUE_UPDATE=YES
PARALLELIZE_INDEPENDENT_CHECKS=MAXIMUM_SAFE
SERIAL_IDLE_WITH_RUNNABLE_WORK=FORBIDDEN
RETAIN_EVIDENCE=YES
FULL_USER_E2E_SUBSTITUTE=NO
ENVIRONMENT_PROVISIONING=NO
HOST_INVENTORY_DISCOVERY=NO
INSTALL_OR_UPGRADE_DURING_AUDIT=NO
~~~

## 2. What this test proves

FULL_USER_E2E asks whether representative users can complete real journeys with real traffic and real state changes.

This reconciliation asks whether **every supported product capability has one coherent, current, discoverable public CLI lifecycle and a complete operator workflow** without changing assigned runtime product state.

It must find defects such as:

- feature exists but no usable CLI exists;
- CLI exists but no current product feature justifies it;
- two public commands claim the same operation;
- hidden/legacy compatibility grammar remains parser/backend reachable;
- correct command exists but help/menu/completion cannot discover it;
- installer/diagnostics/update/error output recommends obsolete syntax;
- create/configure syntax exists but inspect/test/delete/recovery is not coherently discoverable;
- Server and Agent use conflicting nouns or lifecycle ownership;
- state/status/version surfaces contradict one another;
- destructive subvariants have missing or unsafe confirmation/risk contracts;
- a workflow requires memorized syntax, hidden selectors, or backend knowledge.

The target question is:

> **Does every supported Data Relay Link capability map to one current, discoverable, non-duplicated public CLI lifecycle that an operator can follow from discovery through recovery without relying on legacy or hidden grammar?**

This audit proves **workflow-contract coherence**. Live mutation behavior belongs to FULL_USER_E2E or dedicated isolated regression tests.

## 3. Authority and conflict rule

Use the authority order in `DOCUMENTATION_INDEX.md`.

Primary inputs:

1. `PRODUCT_MASTER.md` — supported product model and lifecycle.
2. `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md` — canonical CLI/AI behavior.
3. `CLI_REFERENCE.md` — canonical direct grammar.
4. `Data Relay Link CLI Information Architecture.md` — current menu/UX.
5. active operator docs, installer/help text, generated guidance, diagnostics/update/recovery text.
6. current already-available Server/Agent runtime discovery and behavior, when assigned and reachable.

Runtime existence does not make a command canonical.
A hidden parser path is not acceptable merely because it works.
A stale document cannot override the current product authority.
For unreleased/greenfield v2.4, do not invent compatibility requirements.

## 4. Onboarding — active repository

On `dev-drlink`, resolve the active worktree from:

~~~text
/home/aella/datarelay-link-current
~~~

Before audit execution:

1. read `AGENTS.md`;
2. read `.engineering/project.yaml`;
3. resolve the active worktree and record repository/branch/HEAD for documentation/source correlation;
4. read this document from the active worktree;
5. identify only the Server/Agent runtime surfaces that are already assigned and available for this audit;
6. do not discover, provision, install, upgrade, or repurpose additional hosts;
7. do not inspect or wait for CI unless the user separately requested release/CI work.

## 5. Audit context

Record:

~~~text
RUN_ID=
START_UTC=
REPOSITORY=
BRANCH=
REPO_HEAD=
WORKTREE=
WORKTREE_CLEAN=
ACTIVE_WORK_PACKET=
SERVER_RUNTIME=AVAILABLE|UNAVAILABLE
SERVER_HOST=<assigned existing host or N/A>
SERVER_PRODUCT_VERSION=<if available>
SERVER_SOURCE_HEAD=<if available>
AGENT_RUNTIME=AVAILABLE|UNAVAILABLE
AGENT_HOST=<assigned existing host or N/A>
AGENT_PRODUCT_VERSION=<if available>
AGENT_SOURCE_HEAD=<if available>
~~~

Runtime HEAD equality is informative for correlation, not a reason to install a different candidate during this audit.

If an applicable Server or Agent runtime is unavailable, mark only runtime-dependent checks `BLOCKED_RUNTIME_UNAVAILABLE` and continue the feature/CLI/document/operator-workflow reconciliation that remains executable.

Create:

~~~text
e2e-reports/cli-feature-scenario-reconciliation-<UTC-RUN-ID>/
~~~

Use mode 0700, secret-bearing files 0600, and a unique audit run identifier. Do not use the audit identifier to create product resources.

## 6. Runtime non-destructive gate

Runtime observation is supporting evidence, not an environment-preparation task.

For each already-assigned runtime used by this audit:

1. identify role/availability without discovering or repurposing hosts;
2. execute only read-only discovery/status/help/test-explain operations whose non-mutating contract is known;
3. do not execute mutation-bearing commands merely to prove existence, rejection, confirmation, or cleanup;
4. do not create audit-prefixed product resources;
5. do not alter shared product state to obtain cleaner evidence;
6. when non-destructive behavior is uncertain, inspect help/catalog/parser/source/tests instead of running the command.

Runtime health warnings, stale installed HEAD, disconnected Agent state, pending transactions, or unrelated pre-existing resources do **not** stop the reconciliation and do not authorize repair/recovery.

If another test owns a runtime, continue source/document/read-only checks and mark only conflicting runtime observations `NOT_RUN_SHARED_STATE`.

## 7. Build the feature inventory first

Do **not** start from the command list.

Inventory at minimum:

~~~text
Server identity / public settings / deployment mode
Enrollment: Zero-Touch / Manual / Bulk
Managed Host lifecycle / grouping / inspection
Network Object / Network Group
Service Object / Service Group
Permission Object / Permission Group
Remote Service / Fixed TCP
Remote Access / Internet Access
AI Identity / AI credential lifecycle / AI Access / AI Access Log
MCP public TLS / certificate lifecycle / OAuth approval-denial
ConfigurationBundle
Revision / audit / diff / rollback
Backup / validate / restore
Diagnostics / support bundle
Product update / Relay Engine check-update
Agent pause / resume / restart / autostart / synchronize
Version / release / provenance reporting
Uninstall / reinstall where applicable
~~~

For every feature create a row:

~~~text
FEATURE_ID=
FEATURE=
PRODUCT_AUTHORITY=
SUPPORTED=YES|NO
EXPECTED_ROLE=SERVER|AGENT|BOTH|INSTALLER
EXPECTED_LIFECYCLE=
CANONICAL_CLI=
MENU_PATH=
INSTALLER_OR_GENERATED_PATH=
EXPECTED_SCENARIO=
~~~

Expected **operator workflow contract** normally covers:

~~~text
DISCOVER
CREATE_OR_CONFIGURE_SYNTAX
SHOW_OR_INSPECT
TEST_OR_EXPLAIN
EDIT_OR_ENABLE_DISABLE_SYNTAX
REFERENCES_OR_DEPENDENCIES
DELETE_RESET_REVOKE_SYNTAX
RECOVER_GUIDANCE
~~~

State-changing stages are verified through discoverability, grammar, role ownership, confirmation/risk metadata, dependency semantics, failure guidance, and isolated tests. They are not executed on assigned runtime state.

A feature is not complete merely because one mutation command exists.

## 8. Build the runtime CLI inventory independently

Capture on Server and Agent:

~~~text
drlink help
drlink ?
drlink show ?
drlink set ?
drlink unset ?
drlink test ?
drlink system ?
drlink help commands
drlink help workflows
~~~

Also capture:

- command-specific `?` and help;
- REPL Tab completion;
- guided menu trees;
- installer completion output;
- generated enrollment lifecycle instructions;
- diagnostics recommendations;
- update recommendations;
- role/privilege error recovery text.

Every discovered runtime/public command or variant gets:

~~~text
CLI_PATH=
ROLE=
DISCOVERED_BY=
DOCUMENTED=YES|NO
PRODUCT_FEATURE=
RUNTIME_ONLY=YES|NO
DUPLICATE_OF=
LEGACY_OR_COMPATIBILITY=YES|NO
RUNTIME_OBSERVABLE=YES|NO
MUTATION_PATH_AUDIT=DISCOVERY_ONLY|READ_ONLY_EXECUTED|ISOLATED_TEST_EVIDENCE
SCENARIO_ID=
EVIDENCE=
~~~

## 9. Black-box first, source enumeration second

Preserve public discovery results before source inspection.

After that, perform post-hoc catalog/parser enumeration for:

- public aliases;
- root-bypass aliases;
- hidden command entries;
- hard-coded legacy top-level handlers;
- executable obsolete resources;
- parser paths absent from catalog;
- catalog paths absent from public discovery;
- active documentation examples using retired grammar.

Source inspection is reconciliation evidence only; never use it to make a user scenario pass.

Record:

~~~text
PUBLIC_COMMAND_ENTRY_COUNT=
PUBLIC_ALIAS_PATH_COUNT=
ROOT_BYPASS_ALIAS_COUNT=
HIDDEN_COMMAND_ENTRY_COUNT=
HIDDEN_EXECUTABLE_PATH_COUNT=
PARSER_ONLY_PATH_COUNT=
DOC_ONLY_PATH_COUNT=
~~~

For unreleased greenfield v2.4:

~~~text
LEGACY_COMPATIBILITY_PATH_COUNT=0
ROOT_BYPASS_ALIAS_COUNT=0
HIDDEN_EXECUTABLE_OBSOLETE_PATH_COUNT=0
~~~

unless an explicit current product decision says otherwise.

## 10. Feature ↔ CLI ↔ Operator Workflow ledger

For every feature reconcile all three dimensions. `Scenario` here means an operator workflow contract, not a live mutation sequence.

| Feature | Canonical CLI | Runtime/read-only evidence | Discovery | Operator workflow audit | Result |
|---|---|---|---|---|---|
| Internet Access rule | set/show/test/unset internet-access | read-only runtime + source/tests | help/?/menu | discover create syntax → show → explain → discover edit/reset/recovery | PASS/FAIL |

Allowed dispositions:

~~~text
FEATURE_WITH_CANONICAL_CLI
FEATURE_INSTALLER_ONLY_JUSTIFIED
FEATURE_NO_CLI_GAP
CLI_RUNTIME_ONLY
CLI_WITHOUT_PRODUCT_FEATURE
CLI_DUPLICATE_PATH
CLI_LEGACY_OR_COMPATIBILITY_PATH
DISCOVERY_GAP
SCENARIO_BLOCKED
SCENARIO_DEAD_END
TERMINOLOGY_DRIFT
PROCEDURE_DRIFT
STRUCTURE_DRIFT
STATE_SEMANTICS_DRIFT
CONFIRMATION_METADATA_DRIFT
ERROR_EXIT_STATUS_DRIFT
DOC_EXAMPLE_NONCANONICAL
ROLE_SURFACE_DRIFT
EMPTY_STATE_SILENCE
NEXT_ACTION_STALE
CLEANUP_RESIDUE
DOC_RUNTIME_MISMATCH
~~~

No row may be left without a disposition.

## 11. Terminology consistency

Search Product Master, CLI, menu, installer, diagnostics, errors, and runtime output for conflicting names.

Explicitly check:

~~~text
Managed Host      vs Client / Endpoint
DRLink Agent       vs Client
Remote Service     vs generic Service / Published Service
Network Object     vs generic Object
Service Object     vs Service Profile / Preset as public resource
Permission Object  vs legacy capability/profile nouns
AI Identity        vs AI Principal
Remote Access      vs legacy ACL
Internet Access    vs Egress / Controlled Egress
BLACKLIST/WHITELIST vs ordered first-match ALLOW/DENY
Data Relay Link    vs user-facing FRP product identity
~~~

Flag obsolete nouns, ambiguous selectors, two names for one current object, one name for different objects, and backend/internal names exposed to operators.

## 12. Procedure consistency

For each major capability prove that the operator can discover and understand this workflow contract:

~~~text
DISCOVER
→ CREATE / CONFIGURE SYNTAX
→ SHOW / INSPECT
→ TEST / EXPLAIN
→ EDIT / ENABLE / DISABLE SYNTAX
→ REFERENCE / DEPENDENCY FAILURE GUIDANCE
→ DELETE / RESET / REVOKE SYNTAX
→ RECOVER GUIDANCE
~~~

Read-only stages may be exercised on an assigned runtime. State-changing stages are **not executed there**; validate them through help/`?`/menu/completion, catalog/parser/source reconciliation, active documentation, and deterministic isolated tests.

A workflow is a dead end when the next required step is undiscoverable, output points to legacy/internal syntax, or a later lifecycle stage requires information earlier public surfaces never expose.

Also flag:

- create/configure syntax exists but no usable selector for show/delete is exposed;
- delete/revoke syntax requires an ID list/show does not expose;
- recovery exists only in source/internal tooling;
- “reconfigure” is shown without an exact supported public action;
- a state-changing step can be understood only by actually running it on live product state.

## 13. Structure consistency

Canonical direct roots:

~~~text
show
set
unset
test
system
menu
help
exit
~~~

Look for extra root verbs, duplicate action/resource orderings, asymmetric set/unset, Server settings at unrelated roots, or Server-only nouns on Agent.

Server menu:

~~~text
Managed Hosts
Network Objects
Service Objects
Remote Access
Internet Access
AI Access
System
Help
Exit
~~~

Agent menu:

~~~text
Remote Services
Agent
Configuration
System
Help
Exit
~~~

Direct CLI and menu may differ in presentation, never in product model.

## 14. Discoverability

Compare root help, `?`, action `?`, command `?`, `help commands`, workflows, Tab, menu, errors, installer output, and generated output.

Flag when:

- System help advertises a command missing from `system ?`;
- lifecycle variants hide behind a generic placeholder;
- canonical command works only if memorized;
- stale command is recommended by installer/update/doctor;
- menu exposes a capability direct CLI cannot discover;
- direct CLI exposes unsupported legacy behavior.

## 15. Symmetry and variants

Where meaningful compare:

~~~text
show
set
unset
test
~~~

For policy families also cover:

~~~text
mode
enforcement enabled|disabled
rules
policy reset
test/explain
~~~

Credential/certificate behavior-changing subcommands are separate inventory entries. Family-level parsing alone is not coverage.

## 16. Role and privilege

Run representative **read-only** Server-only commands on Agent and Agent-only commands on Server when assigned surfaces are available.

Expected: correct role, no traceback, no mutation.

Run selected read-only commands without required privilege where safe.

Expected: privilege/readability error is identified as such, canonical next action is given, and user-visible ERROR returns non-zero.

For mutation-bearing wrong-role or privilege cases, inspect parser/catalog/error contracts and isolated tests instead of executing them on assigned runtime state.

Wrong-role, unknown-command, or RC=0 for a privilege ERROR is a defect.

## 17. Empty state / success state

Every major empty list must visibly say none/zero configured.

RC=0 with no output is a defect unless silence is explicitly defined.

For read-only runtime commands, verify success/failure exit status directly.

For mutation commands, verify success/cancel/failure messaging and exit-status contracts through catalog/parser/source and deterministic isolated tests. Do not create or delete live state merely to observe those messages.

Required contract:

- mutation success says what changed;
- cancellation says no change;
- failure is non-zero;
- `ERROR` + RC=0 is a defect.

## 18. Status / version / provenance consistency

Compare:

~~~text
show status
system status
system info where applicable
system diagnostics
system version
menu banner
installer completion output
support-bundle public metadata where safe
~~~

Flag contradictions such as healthy current DB vs missing legacy registry, healthy vs unavailable without explanation, plain release version vs development `-dev+g<sha>`, or incompatible Bundle SHA semantics.

Formatting may differ. Meaning must not contradict.

## 19. Safety / destructive confirmation

Inventory every operation that can delete/reset state, widen access, cause DENY ALL/outage, remove credentials/keys/certificates, restore/rollback, uninstall, or release reservations.

For every destructive subvariant record:

~~~text
COMMAND=
INTENDED_EFFECT=
CATALOG_DESTRUCTIVE=
CATALOG_RISK=
CATALOG_CONFIRMATION=
DOCUMENTED_TTY_YES_CONTRACT=
DOCUMENTED_TTY_NO_CONTRACT=
DOCUMENTED_NON_TTY_CONTRACT=
ISOLATED_TEST_COVERAGE=
EXIT_STATUS_CONTRACT=
~~~

Do not trust parent-command metadata for a destructive child variant.

**Do not execute destructive variants on assigned runtime during this audit, including "answer No" probes.** Audit confirmation behavior from catalog/parser/source plus deterministic isolated test coverage.

Required contract:

- explicit TTY confirmation where applicable;
- default No;
- No/cancel applies no change;
- non-TTY fails closed unless documented automation approval exists;
- no mutation before confirmation;
- automation-safe exit status.

Missing isolated regression coverage for a security-sensitive/destructive contract may itself be a finding.

## 20. Mandatory operator workflow audit scenarios

These FCS entries are **workflow-reconciliation scenarios**, not live state-changing E2E scenarios.

## FCS-001 — First Server discovery
Read-only help/menu/status/version → discover Server settings → verify next actions and feature reachability.

## FCS-002 — Enrollment / Managed Host
Discover Zero-Touch / Manual / Bulk syntax and semantics → verify list/show selectors and Managed Host inspection → audit revoke/remove syntax, confirmation, references, and recovery guidance. Do not issue/revoke enrollment.

## FCS-003 — Objects / Groups
Discover Network/Service/Permission create/edit syntax → list/show → group/reference model → protected delete/dependency contract → recovery guidance. Do not create/delete Objects or Groups.

## FCS-004 — Agent Remote Service
Discover Agent surface → create/edit/disable/delete syntax → inspect existing read-only state if available → verify duplicate/dependency/endpoint semantics through docs/source/tests. Do not mutate Remote Services.

## FCS-005 — Remote Access
Discover dependencies → mode/rule grammar → show → read-only test/explain → discover enforcement/edit/reset syntax → verify dependency/recovery contract. Do not modify policy.

## FCS-006 — Internet Access
Same non-destructive workflow audit plus object/protocol validity, BLACKLIST/WHITELIST semantics, and absence of ordered-rule semantics. Do not modify policy.

## FCS-007 — AI Identity / Credential / Permission / AI Access
Discover identity/credential lifecycle → Permission/AI Access grammar → read-only show/test/log → inspect rejection/recovery contracts from parser/tests. Do not create/rotate/revoke credentials or identities.

## FCS-008 — MCP TLS / Certificate / OAuth
Read-only TLS/certificate status/preflight discovery → OAuth approve/deny grammar → recovery guidance → purge/renew/import/issue risk and confirmation from source/tests. Do not mutate certificate/OAuth state.

## FCS-009 — ConfigurationBundle
Discover export/test/diff/apply grammar → run only non-mutating validation/diff when safe → audit apply/NO CHANGE/stale/invalid/fail-closed behavior through isolated tests. Do not apply a changing bundle.

## FCS-010 — Revision / Audit / Rollback
Read-only revision/audit/show/diff → discover rollback syntax/confirmation → verify rollback safety through isolated tests. Do not create a mutation or rollback.

## FCS-011 — Backup / Restore
Discover backup/validate/restore grammar → read-only readiness/preflight where safe → audit restore confirmation/fail-closed contract through source/tests. Do not create backups or restore state solely for this audit.

## FCS-012 — Agent lifecycle
Discover pause/resume/restart/synchronize/autostart grammar and ownership → inspect status/info/diagnostics/version → verify transitions through isolated tests. Do not change Agent lifecycle state.

## FCS-013 — Update / recovery guidance
Verify Product update and Relay Engine check/update are distinct and discoverable; every recommendation uses canonical grammar. Do not perform state/network-changing update checks.

## FCS-014 — Cross-surface consistency
Server/Agent/menu/help/status/diagnostics/version describe one current model using read-only evidence.

## FCS-015 — Legacy / alias negative reconciliation
Find retired guesses from docs/catalog/source and prove they are absent from public discovery and rejected by parser/isolated tests with canonical guidance. **Do not execute source-enumerated legacy mutation paths on assigned runtime state.**

## 21. Active documentation / generated-output scan

Installer content is inspected as a public guidance surface only. Do not execute a fresh install merely to obtain installer completion text; use current source/help/generated text or already-retained output from the assigned runtime when available.

Scan at minimum:

~~~text
README*
INSTALLATION.md
UPGRADE.md
REMOTE_ACCESS.md
AI_ACCESS_MCP.md
TROUBLESHOOTING.md
DEPLOYMENT_MODES.md
CLI_REFERENCE.md
CLI/AI Master
installer completion output
Agent recovery text
doctor/diagnostics remediation
update recommendations
enrollment output
~~~

Classify examples as `CANONICAL_PUBLIC`, `INSTALLER_ONLY_JUSTIFIED`, `INTERNAL_EXPLICITLY_LABELLED`, `NONCANONICAL_ACTIVE_EXAMPLE`, or `HISTORICAL_IGNORE`.

## 22. Evidence layout

~~~text
<EVIDENCE_ROOT>/
  run.env
  candidate-server.txt
  candidate-agent.txt
  discovery/
  ledger/
    feature-ledger.tsv
    cli-ledger.tsv
    feature-cli-scenario.tsv
    hidden-alias-enumeration.tsv
    docs-example-ledger.tsv
  scenarios/FCS-*.txt
  findings/P0-*.txt
  findings/P1-*.txt
  findings/P2-*.txt
  findings/P3-*.txt
  cleanup/                 # audit-owned temp/process cleanup only; no product-resource cleanup expected
  summary.txt
~~~

Never retain raw Zero-Touch credentials, Enrollment Codes when secret, OAuth codes/tokens, bearer tokens, client secrets, private keys, or protected backup contents.

Redact before durable evidence.

## 23. Severity

- **P0** — destructive/security/data-loss/credential risk; release blocker.
- **P1** — feature/CLI orphan, scenario dead end, runtime-only obsolete behavior, major release-contract failure; release blocker.
- **P2** — material terminology/discoverability/procedure/structure/status/recovery inconsistency.
- **P3** — polish only.

A user-blocking P2 blocks this gate.

## 24. Required counters

~~~text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS|FAIL
FEATURE_INVENTORY_TOTAL=
FEATURE_NO_CLI_GAPS=
FEATURE_WITHOUT_DISCOVERABLE_CLI_COUNT=
CLI_WITHOUT_PRODUCT_FEATURE_COUNT=
RUNTIME_ONLY_CLI_COUNT=
DUPLICATE_PUBLIC_PATH_COUNT=
PUBLIC_ALIAS_PATH_COUNT=
LEGACY_COMPATIBILITY_PATH_COUNT=
ROOT_BYPASS_ALIAS_COUNT=
HIDDEN_EXECUTABLE_PATH_COUNT=
PARSER_ONLY_PATH_COUNT=
DOC_ONLY_PATH_COUNT=
DISCOVERY_GAP_COUNT=
SCENARIO_BLOCKED_COUNT=
SCENARIO_DEAD_END_COUNT=
TERMINOLOGY_DRIFT_COUNT=
PROCEDURE_DRIFT_COUNT=
STRUCTURE_DRIFT_COUNT=
STATE_SEMANTICS_DRIFT_COUNT=
CONFIRMATION_METADATA_DRIFT_COUNT=
DESTRUCTIVE_CONFIRMATION_GAP_COUNT=
ERROR_WITH_ZERO_RC_COUNT=
EMPTY_STATE_SILENCE_COUNT=
NEXT_ACTION_STALE_COUNT=
DOC_EXAMPLE_NONCANONICAL_COUNT=
ROLE_SURFACE_DRIFT_COUNT=
STATUS_DOC_RUNTIME_MISMATCH_COUNT=
CLEANUP_RESIDUE_COUNT=            # audit-owned temp/process residue only
RUNTIME_MUTATION_ATTEMPT_COUNT=
PARALLEL_LANES_STARTED=
MAX_SIMULTANEOUS_ACTIVE_LANES=
SERIAL_IDLE_WITH_RUNNABLE_WORK=YES|NO
AVOIDABLE_SERIAL_WAIT_COUNT=
UNRESOLVED_P0=
UNRESOLVED_P1=
UNRESOLVED_USER_BLOCKING_P2=
~~~

When this audit is explicitly being consumed by a separate release-qualification workflow, that workflow may additionally write the machine-readable exact-HEAD record below. A normal reconciliation trigger does not install/freeze a candidate merely to satisfy this record:

~~~text
e2e-reports/release-qualification/cli-feature-scenario.json
~~~

Minimum JSON contract:

~~~json
{
  "schema_version": 1,
  "gate": "CLI_FEATURE_SCENARIO_RECONCILIATION",
  "final_status": "PASS",
  "repo_head": "<40-char exact HEAD>",
  "end_head": "<same HEAD>",
  "head_unchanged": true,
  "cleanup_status": "PASS",
  "feature_inventory_total": 1,
  "counters": {
    "feature_no_cli_gaps": 0,
    "feature_without_discoverable_cli_count": 0,
    "cli_without_product_feature_count": 0,
    "runtime_only_cli_count": 0,
    "duplicate_public_path_count": 0,
    "public_alias_path_count": 0,
    "legacy_compatibility_path_count": 0,
    "root_bypass_alias_count": 0,
    "hidden_executable_path_count": 0,
    "discovery_gap_count": 0,
    "installer_guidance_mismatch_count": 0,
    "destructive_confirmation_gap_count": 0,
    "error_with_zero_rc_count": 0,
    "scenario_blocked_count": 0,
    "scenario_dead_end_count": 0,
    "cleanup_residue_count": 0,
    "runtime_mutation_attempt_count": 0,
    "avoidable_serial_wait_count": 0
  },
  "parallel_execution": "MAXIMUM_SAFE",
  "parallel_lanes_started": 1,
  "serial_idle_with_runnable_work": false,
  "evidence_root": "<retained evidence directory>"
}
~~~

`scripts/check-pre-release-exhaustive-gates.py --gate cli-feature-scenario`
must validate this record against the current Git HEAD before release qualification can proceed.

For unreleased greenfield v2.4, every applicable gap/drift/legacy/duplicate/dead-end/cleanup counter must be zero for PASS.

## 25. PASS / FAIL

PASS requires:

1. every supported feature has one actionable justified public CLI lifecycle;
2. every runtime/public command maps to a current feature;
3. no unjustified duplicate mutation path;
4. no compatibility/root-bypass/obsolete hidden executable grammar;
5. every required lifecycle variant is publicly discoverable;
6. no terminology/procedure/structure contradiction affecting user understanding;
7. no operator workflow dead end;
8. destructive variants have coherent fail-closed confirmation/risk contracts with isolated regression evidence;
9. ERROR exit statuses are automation-safe;
10. empty states are explicit;
11. status/version/provenance is coherent;
12. active docs/generated guidance are canonical;
13. `RUNTIME_MUTATION_ATTEMPT_COUNT=0`;
14. audit-owned temporary process/file residue is zero;
15. `PARALLEL_EXECUTION=MAXIMUM_SAFE`, `SERIAL_IDLE_WITH_RUNNABLE_WORK=NO`, and `AVOIDABLE_SERIAL_WAIT_COUNT=0`;
16. unresolved P0/P1/user-blocking P2 = 0;
17. no unresolved actionable usability/product-improvement finding remains. A P2/P3 observation may remain only when it is explicitly dispositioned as non-actionable for the current supported product scope.

Anything else is FAIL or explicitly BLOCKED.

A workflow is not `BLOCKED` merely because this audit refuses to execute its mutation. Mutation is intentionally out of scope; judge that workflow step from discoverability/contract/test evidence.

## 26. Failure continuation

When finding a defect:

- preserve exact evidence;
- classify it;
- continue independent scenarios;
- do not patch product code during the active run;
- do not allow one failure to hide unrelated defects.

Stop only when continuing creates unacceptable safety/security/environment risk.

## 27. Offboarding — mandatory

Offboarding must remain non-destructive to product state.

Because this audit must not create product resources, there is no product-resource cleanup phase.

Before completion:

1. verify `RUNTIME_MUTATION_ATTEMPT_COUNT=0`;
2. terminate only audit-owned transient CLI/PTY helper processes;
3. remove only audit-owned temporary local files not retained as evidence;
4. verify no audit-owned test listener/service/lock/pid remains;
5. preserve the evidence directory;
6. do **not** delete/reset/revoke/release/rollback/restore any pre-existing product state.

Capture final read-only state only where useful for correlation.

`CLEANUP_RESIDUE_COUNT` refers only to audit-owned temporary process/file residue. It never authorizes product-resource cleanup.

## 28. GitHub reporting — mandatory, final only

Do not update the active `[AI Work]` Issue while the audit is still executing merely because a finding was discovered.

Keep findings in the current run evidence ledger and continue all independent checks.

After the audit has exhausted every executable non-destructive check, final counters are computed, and evidence is frozen, update the active `[AI Work]` Issue once with the consolidated result.

Include:

~~~text
RUN_ID=
REPO_HEAD=
INSTALLED_SERVER_HEAD=
INSTALLED_AGENT_HEAD=
FINAL_STATUS=
EVIDENCE_ROOT=
CLEANUP_STATUS=
RUNTIME_MUTATION_ATTEMPT_COUNT=
RELEASE_BLOCKERS=
COUNTER_SUMMARY=
NEXT_ACTION=
~~~

For each P0/P1/P2 include feature, CLI path/output or source contract, role/host if applicable, inconsistency, user impact, evidence, and remediation boundary.

Never paste secrets.

## 29. Handoff after FAIL

After the audit is exhausted:

1. freeze evidence;
2. update the active Work Packet with the reconciliation findings;
3. create remediation slices P0 → P1 → user-blocking P2 → P3;
4. add durable regression coverage where appropriate;
5. after remediation, rerun the affected reconciliation scenarios with a **new RUN_ID** against already-assigned applicable runtime surfaces;
6. if release qualification later requires clean exact-candidate installation, that provisioning is performed by the release/FULL_USER_E2E workflow before invoking this audit.

## 30. Relationship to other tests

## CLI_EXHAUSTIVE_AUDIT

This document is the canonical deep **Feature ↔ CLI ↔ Operator Workflow** non-destructive reconciliation contract.

`CLI_EXHAUSTIVE_AUDIT.md` may invoke it for structural/product-surface reconciliation while adding broader CLI UX/adversarial coverage.

## FULL_USER_E2E

FULL_USER_E2E remains separate.

~~~text
CLI_FEATURE_SCENARIO_RECONCILIATION
= non-destructive Feature ↔ CLI ↔ operator-workflow audit
= read-only runtime discovery + source/catalog/parser/docs + isolated deterministic tests

FULL_USER_E2E / release qualification
= live state-changing user journeys
= create/edit/delete/apply/rollback/restore/update/restart/reboot
= real traffic, lifecycle, install/reinstall, platform qualification
~~~

A release workflow may prepare an exact candidate runtime for correlation, but this reconciliation still does not mutate it.

## Product-quality relationship

This reconciliation is one of two product-quality closure tests. Together with a complete `FULL_USER_E2E=PASS` on the same supported product candidate, it means the product has no known in-scope feature/CLI/workflow defect or unresolved actionable usability improvement under these exhaustive contracts.

~~~text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FULL_USER_E2E=PASS
=> PRODUCT_QUALITY_CLOSURE=PASS
=> NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES
=> NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES
~~~

`PRODUCT_QUALITY_CLOSURE=PASS` is **not** `RELEASE_READY=YES`. Actual release qualification, CI, artifacts, provenance, governance, attestation, approvals, tagging, and publication remain governed by `RELEASE_VALIDATION.md` and `RELEASE_CHECKLIST.md`.

## 31. Minimal operator trigger

The human may say simply:

~~~text
GitHub에서 CLI_FEATURE_SCENARIO_RECONCILIATION 문서 찾아서 테스트 진행해
~~~

or:

~~~text
CLI, 기능, 시나리오의 연계성을 테스트 진행
~~~

Resolve `datarelay-labs/datarelay-link/docs/CLI_FEATURE_SCENARIO_RECONCILIATION.md` deterministically and start immediately.

Execution order is fixed:

~~~text
FEATURE INVENTORY
→ PUBLIC CLI DISCOVERY (independent read-only probes in parallel)
→ OPERATOR WORKFLOW RECONCILIATION (independent FCS lanes in parallel)
→ POST-HOC HIDDEN/PARSER/DOC ENUMERATION + ISOLATED SUITES (maximum-safe parallel)
→ COMPLETE ALL INDEPENDENT CHECKS
→ FREEZE EVIDENCE AND COUNTERS
→ ONE FINAL GITHUB ISSUE UPDATE
~~~

Do not turn findings into pauses. Record them and continue.

Do not perform product-state mutation, host discovery, installation, upgrade, uninstall, restart, pause/resume, synchronization, rollback/restore, platform qualification, CI waiting, or release-candidate preparation as part of this trigger.
