# Data Relay Link — CLI ↔ Feature ↔ Scenario Reconciliation

> **Document role:** Canonical executable test contract for product capability ↔ public CLI ↔ real operator scenario reconciliation
> **Executor:** ChatGPT
> **Scope:** completeness, uniqueness, discoverability, terminology, procedure, structure, safety, recovery, evidence, and cleanup
> **Target:** v2.4 and later until superseded
> **Release gate:** independent from FULL_USER_E2E and mandatory before final Full User E2E PASS1/PASS2
> **Companion:** `CLI_EXHAUSTIVE_AUDIT.md`

## 1. Exact execution trigger

The following request is an **immediate execution command**, not a request for a plan:

~~~text
CLI, 기능, 시나리오의 연계성을 테스트 진행
~~~

Equivalent requests include:

~~~text
CLI 기능 시나리오 연계성 테스트
CLI-기능-시나리오 연계 테스트
기능과 CLI와 시나리오 매핑 테스트
Feature CLI Scenario reconciliation
CLI product-surface reconciliation
~~~

When triggered, resolve this file from the active repository and execute it immediately.

Do not substitute FULL_USER_E2E, a generic CLI smoke test, or historical evidence.

~~~text
AUDIT_PROFILE=CLI_FEATURE_SCENARIO_RECONCILIATION
FIRST_ACTION=EXECUTE
PUBLIC_DRLINK_ONLY_FOR_USER_SCENARIOS=YES
BLACK_BOX_FIRST=YES
POST_HOC_HIDDEN_SURFACE_ENUMERATION=YES
PRODUCT_SOURCE_EDITS_DURING_AUDIT=NO
RETAIN_EVIDENCE=YES
UPDATE_ACTIVE_AI_WORK_ISSUE=YES
FULL_USER_E2E_SUBSTITUTE=NO
~~~

## 2. What this test proves

FULL_USER_E2E asks whether representative users can complete real journeys with real traffic.

This reconciliation asks whether **every supported product capability** has one coherent, current, discoverable public CLI lifecycle and a complete operator scenario.

It must find defects such as:

- feature exists but no usable CLI exists;
- CLI exists but no current product feature justifies it;
- two public commands mutate the same thing;
- hidden/legacy compatibility grammar still executes;
- correct command exists but help/menu/completion cannot discover it;
- installer/doctor/update/error output recommends an obsolete command;
- create works but inspect/test/delete/recovery cannot be completed;
- Server and Agent use conflicting nouns or lifecycle ownership;
- state/status/version surfaces contradict each other;
- destructive subvariants bypass confirmation.

## 3. Authority and conflict rule

Use the authority order in `DOCUMENTATION_INDEX.md`.

Primary inputs:

1. `PRODUCT_MASTER.md` — supported product model and lifecycle.
2. `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md` — canonical CLI/AI behavior.
3. `CLI_REFERENCE.md` — canonical direct grammar.
4. `Data Relay Link CLI Information Architecture.md` — current menu/UX.
5. active operator docs, installer output, generated guidance, diagnostics/update/recovery text.
6. installed exact-candidate runtime discovery and behavior.

Runtime existence does not make a command canonical.
A hidden parser path is not acceptable merely because it works.
A stale document cannot override the current product authority.
For unreleased/greenfield v2.4, do not invent compatibility requirements.

## 4. Onboarding — active repository

On `dev-drlink`, resolve the active worktree from:

~~~text
/home/aella/datarelay-link-current
~~~

Before mutation:

1. read `AGENTS.md`;
2. read `.engineering/project.yaml`;
3. load the single active matching GitHub `[AI Work]` Work Packet;
4. verify repository, branch, HEAD, remote sync, and worktree status;
5. read this document from the active worktree;
6. record installed Server/Agent candidate identities;
7. inspect exact-head CI, but never substitute CI for this audit.

## 5. Candidate preflight

Record:

~~~text
RUN_ID=
START_UTC=
REPOSITORY=
BRANCH=
REPO_HEAD=
WORKTREE=
WORKTREE_CLEAN=
PR=
ACTIVE_WORK_PACKET=
SERVER_HOST=
AGENT_HOST=
SERVER_PRODUCT_VERSION=
SERVER_SOURCE_HEAD=
AGENT_PRODUCT_VERSION=
AGENT_SOURCE_HEAD=
DEPLOYMENT_MODE=
RELEASE_CHANNEL=
~~~

Prefer one Server and one Agent on the same installed content.

If installed content differs from repository HEAD, record it explicitly. Findings remain useful but must not be presented as exact-HEAD findings for a newer candidate.

Create:

~~~text
e2e-reports/cli-feature-scenario-reconciliation-<UTC-RUN-ID>/
~~~

Use mode 0700, secret-bearing files 0600, and a unique audit resource prefix.

## 6. Collision / ownership gate

Before mutation:

1. list active E2E/audit processes;
2. identify shared-state tests;
3. capture pre-existing state for any shared host to be mutated;
4. use namespaced resources wherever possible;
5. record non-prefixed resources that guided flows may create;
6. never delete a resource only because its name looks temporary.

When a concurrent test owns mutable state, mark that step `NOT_RUN_SHARED_STATE` and continue independent checks.

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

Expected lifecycle normally covers:

~~~text
DISCOVER
CREATE_OR_CONFIGURE
SHOW_OR_INSPECT
TEST_OR_EXPLAIN
EDIT_OR_ENABLE_DISABLE
REFERENCES_OR_DEPENDENCIES
DELETE_RESET_REVOKE
RECOVER
CLEANUP
~~~

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

Every runtime command/variant gets:

~~~text
CLI_PATH=
ROLE=
DISCOVERED_BY=
DOCUMENTED=YES|NO
PRODUCT_FEATURE=
RUNTIME_ONLY=YES|NO
DUPLICATE_OF=
LEGACY_OR_COMPATIBILITY=YES|NO
EXECUTABLE=YES|NO
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

## 10. Feature ↔ CLI ↔ Scenario ledger

For every feature reconcile all three dimensions.

| Feature | Canonical CLI | Runtime CLI | Discovery | Real scenario | Result |
|---|---|---|---|---|---|
| Internet Access rule | set/show/test/unset internet-access | runtime paths | help/?/menu | create → show → explain → reset → cleanup | PASS/FAIL |

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

For each major capability prove:

~~~text
DISCOVER
→ CREATE / CONFIGURE
→ SHOW / INSPECT
→ TEST / EXPLAIN
→ EDIT / ENABLE / DISABLE
→ REFERENCE / DEPENDENCY FAILURE
→ DELETE / RESET / REVOKE
→ RECOVER
→ CLEANUP
~~~

A workflow is a dead end when help says what failed but not how to continue, the required next variant is undiscoverable, or output points to legacy/internal syntax.

Also flag:

- create succeeds but no usable selector for show/delete is exposed;
- delete requires an ID that list/show does not expose;
- recovery exists only in source/internal tooling;
- “reconfigure” is shown without the exact supported CLI/menu/installer action.

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

Run representative Server-only commands on Agent and Agent-only commands on Server.

Expected: correct role, no traceback, no mutation.

Run selected commands without required privilege where safe.

Expected: privilege/readability error is identified as such, canonical next action is given, and user-visible ERROR returns non-zero.

Wrong-role, unknown-command, or RC=0 for a privilege ERROR is a defect.

## 17. Empty state / success state

Every major empty list must visibly say none/zero configured.

RC=0 with no output is a defect unless silence is explicitly defined.

Mutation success must say what changed.
Cancellation must say no change.
Failure must be non-zero.
`ERROR` + RC=0 is a defect.

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

Inventory every operation that can:

- delete state;
- reset policy;
- widen access;
- narrow to outage/DENY ALL;
- remove credentials;
- remove keys/certificates;
- restore/rollback;
- uninstall;
- release reservations.

For every destructive subvariant record:

~~~text
COMMAND=
ACTUAL_EFFECT=
CATALOG_DESTRUCTIVE=
CATALOG_RISK=
CATALOG_CONFIRMATION=
TTY_YES_BEHAVIOR=
TTY_NO_BEHAVIOR=
NON_TTY_BEHAVIOR=
MUTATION_BEFORE_CONFIRMATION=
EXIT_STATUS_CONTRACT=
~~~

Do not trust parent-command metadata for a destructive child variant.

Required:

- explicit TTY confirmation;
- default No;
- No/cancel applies no change;
- non-TTY fails closed unless documented automation approval exists;
- no mutation before confirmation;
- automation-safe exit status.

## 20. Mandatory scenario catalog

#

## FCS-001 — First Server discovery
Install/inspect Server → help/menu/status/version → discover Server settings → verify current next actions.

#

## FCS-002 — Enrollment / Managed Host
Discover enrollment → Zero-Touch and Manual semantics → issue safely → inspect enrollment/Managed Host → revoke/remove → cleanup.

#

## FCS-003 — Objects / Groups
Network, Service, Permission: create → list/show → group → references → protected delete → dependency cleanup → delete.

#

## FCS-004 — Agent Remote Service
Discover Agent → create → inspect endpoint/state → duplicate protection → edit/disable where supported → delete.

#

## FCS-005 — Remote Access
Dependencies → mode/rule → show → test/explain → enforcement toggle → reset → cleanup.

#

## FCS-006 — Internet Access
Same lifecycle plus object/protocol validity and no ordered-rule semantics.

#

## FCS-007 — AI Identity / Credential / Permission / AI Access
Identity → credential lifecycle discovery → reject nonexistent Identity mutation → permissions → rule → test → log → cleanup.

#

## FCS-008 — MCP TLS / Certificate / OAuth
Topology prerequisite → TLS/certificate status/preflight → OAuth approve/deny discovery → actionable Direct→single443 recovery → destructive purge confirmation.#

## FCS-009 — ConfigurationBundle
Export → test → diff → changing apply with confirmation → same-state NO CHANGE → invalid bundle fail closed → cleanup.

#

## FCS-010 — Revision / Audit / Rollback
Mutation → revision/audit → inspect/diff → rollback safety → no cross-plane divergence.

#

## FCS-011 — Backup / Restore
Backup → validate → restore preflight → TTY/non-TTY confirmation → no mutation on refusal.

#

## FCS-012 — Agent lifecycle
Pause → status → resume → synchronize → autostart discovery → diagnostics/update guidance.

#

## FCS-013 — Update / recovery guidance
Product update and Relay Engine check/update distinct; every recommendation uses canonical grammar.

#

## FCS-014 — Cross-surface consistency
Server/Agent/menu/help/status/diagnostics/version describe one current model.

#

## FCS-015 — Legacy / alias negative testing
Probe retired natural guesses and source-enumerated hidden paths. Obsolete grammar must reject with canonical guidance rather than execute compatibility behavior.

## 21. Active documentation / generated-output scan

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
  cleanup/
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
CLEANUP_RESIDUE_COUNT=
UNRESOLVED_P0=
UNRESOLVED_P1=
UNRESOLVED_USER_BLOCKING_P2=
~~~For unreleased greenfield v2.4, every applicable gap/drift/legacy/duplicate/dead-end/cleanup counter must be zero for PASS.

## 25. PASS / FAIL

PASS requires:

1. every supported feature has one actionable justified public lifecycle;
2. every runtime public command maps to a current feature;
3. no unjustified duplicate mutation path;
4. no compatibility/root-bypass/obsolete hidden executable grammar;
5. every required lifecycle variant is publicly discoverable;
6. no terminology/procedure/structure contradiction affecting user understanding;
7. no scenario dead end;
8. destructive variants fail closed correctly;
9. ERROR exit statuses are automation-safe;
10. empty states are explicit;
11. status/version/provenance is coherent;
12. active docs/generated guidance are canonical;
13. cleanup residue is zero;
14. unresolved P0/P1/user-blocking P2 = 0.

Anything else is FAIL or explicitly BLOCKED.

## 26. Failure continuation

When finding a defect:

- preserve exact evidence;
- classify it;
- continue independent scenarios;
- do not patch product code during the active run;
- do not allow one failure to hide unrelated defects.

Stop only when continuing creates unacceptable safety/security/environment risk.

## 27. Offboarding — mandatory

Offboarding is part of the test.

On every mutated Server and Agent:

1. enumerate audit-prefixed resources;
2. enumerate non-prefixed resources created by guided defaults;
3. remove in safe dependency order;
4. remove temporary bundles/backups after evidence derivation;
5. delete secret-bearing temporary artifacts;
6. verify no audit-owned endpoint reservation remains.

Then verify no audit `drlink` process, pending update/restore transaction, test listener/service, or audit lock/pid remains.

Capture final state:

~~~text
show status
show managed-hosts
show remote-services on each mutated Agent
show remote-access
show internet-access
show ai-identities
show network-objects / groups
show service-objects / groups
show permission-objects / groups
system diagnostics
~~~

Audit-prefix residue count must be zero.
For any retained shared resource, preserve proof it existed before the run.

## 28. GitHub reporting — mandatory

Update the active `[AI Work]` issue before declaring completion.

Include:

~~~text
RUN_ID=
REPO_HEAD=
INSTALLED_SERVER_HEAD=
INSTALLED_AGENT_HEAD=
FINAL_STATUS=
EVIDENCE_ROOT=
CLEANUP_STATUS=
RELEASE_BLOCKERS=
COUNTER_SUMMARY=
NEXT_ACTION=
~~~

For each P0/P1/P2 include feature, CLI path/output, role/host, inconsistency, user impact, evidence, and remediation boundary.

Never paste secrets.

## 29. Handoff after FAIL

After the audit is exhausted:

1. freeze evidence;
2. update Work Packet;
3. create remediation slices P0 → P1 → user-blocking P2 → P3;
4. add durable regression tests;
5. install a clean exact Server + Agent candidate;
6. rerun this document with a **new RUN_ID**;
7. only a fresh PASS on the changed candidate clears the gate.

## 30. Relationship to other tests

#

## CLI_EXHAUSTIVE_AUDIT

This document is the canonical deep **Feature ↔ CLI ↔ Scenario** reconciliation contract.

`CLI_EXHAUSTIVE_AUDIT.md` may invoke this document for its structural/product-surface gate while adding broader human CLI UX/adversarial coverage.

#

## FULL_USER_E2E

FULL_USER_E2E remains separate.

Final qualification order:

~~~text
deterministic/unit/targeted tests
→ install exact candidate
→ CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
→ other exact-head release gates
→ FULL_USER_E2E PASS1
→ FULL_USER_E2E PASS2
→ release
~~~

Any CLI/product/documentation-surface change after reconciliation PASS invalidates that PASS.

## 31. Minimal operator trigger

The human only needs to say:

~~~text
CLI, 기능, 시나리오의 연계성을 테스트 진행
~~~

The executor must find this document in the active repository and immediately start Section 4 onboarding and Section 5 preflight.
