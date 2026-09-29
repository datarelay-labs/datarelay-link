# Data Relay Link — CLI Exhaustive Audit

> **Document role:** Canonical exhaustive audit contract for the public `drlink` CLI
> **Executor:** ChatGPT
> **Scope:** Human-operated CLI usability, syntax, discoverability, workflow closure, safety, recovery, and cross-surface consistency
> **Target:** v2.4 and later until superseded
> **Product authority:** `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`, `CLI_REFERENCE.md`, `Data Relay Link CLI Information Architecture.md`
> **Companion:** `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`

## 1. Execution triggers

When the user asks, without narrowing scope:

- `CLI 전수 감사해줘`
- `CLI 명령 전수 감사해줘`
- `drlink CLI 전수 감사`
- `CLI 전체 UX 감사`
- or an equivalent request to exhaustively audit the CLI

execute this document immediately.

When the user asks:

- `CLI 및 AI지원 명령을 전수 감사해줘`
- `CLI와 AI 지원 명령 전수 감사`
- or equivalent wording that requests both human CLI and AI-assisted command auditing

execute **this document and `AI_ASSISTED_COMMAND_EXHAUSTIVE_AUDIT.md`** against the same candidate and environment.

Do not answer with a plan-only response and do not ask for confirmation when designated test systems are available.

~~~text
AUDIT_PROFILE=CLI_EXHAUSTIVE_AUDIT
EXECUTOR=ChatGPT
FIRST_ACTION=EXECUTE
PUBLIC_DRLINK_ONLY=YES
PRODUCT_SOURCE_EDITS_DURING_AUDIT=NO
RETAIN_EVIDENCE=YES
UPDATE_ACTIVE_AI_WORK_ISSUE=YES
~~~

## 2. What this audit is

This is a black-box user audit of the installed public `drlink` experience.

The audit answers:

- Can a user discover the right command without reading implementation code?
- Are words, nouns, singular/plural forms, IDs, names, and roles understandable?
- Does each advertised command actually work?
- Does a workflow close end-to-end using only public CLI?
- Can a user recover from incomplete syntax, a wrong command, a wrong menu state, or a missing prerequisite?
- Are destructive operations fail-closed and explicit?
- Do TTY and non-TTY forms preserve the documented safety contract?
- Are Server and Agent views consistent enough that a user can understand current state?
- Do help, `?`, menu, one-shot commands, and REPL behavior describe the same product?
- Does Ctrl+C cancel cleanly without internal traceback?
- Are empty states and successful changes visible rather than silent?

Do not use implementation source, internal APIs, SQL, registry files, or hidden helper commands to make a scenario pass. They may be inspected later to diagnose a recorded defect, but not as the user path being audited.

## 3. Candidate and environment preflight

Before mutation:

1. resolve the product repository/worktree and active AI Work Packet;
2. record branch, exact product HEAD, provenance/content HEAD where applicable, and worktree cleanliness;
3. inspect exact-head CI but do not substitute CI for this audit;
4. discover suitable test hosts from the development server's SSH inventory;
5. identify at least one Server and one Agent running the same candidate content;
6. record existing active E2E/audit processes and avoid destructive collision;
7. create a unique evidence root and resource prefix;
8. use disposable/namespaced resources for mutations.

If the installed build does not match the intended candidate, record that fact before proceeding. Do not claim candidate findings from an older install.

Recommended evidence root:

~~~text
e2e-reports/cli-exhaustive-audit-<UTC-RUN-ID>/
~~~

## 4. Audit method

For every applicable scenario, exercise all relevant public forms:

1. discovery through `help`, `?`, menu, and top-level command hints;
2. canonical shell one-shot, normally `sudo drlink ...` when privileged state is required;
3. interactive `sudo drlink` REPL;
4. guided wizard/menu where one exists;
5. incomplete syntax;
6. a natural typo, singular/plural variation, or old/general product term where relevant;
7. empty-state behavior;
8. success-state behavior;
9. failure/recovery behavior;
10. cleanup.

A command that returns RC=0 but prints a user-visible ERROR is a UX/API-contract finding and must not be silently treated as success.

## 4.1 Exhaustive command coverage ledger

The scenario matrix is not sufficient by itself to claim an exhaustive audit. Before execution, build a **command coverage ledger** from the union of:

1. every public command/resource/subcommand documented by `CLI_REFERENCE.md` and the CLI/AI Master;
2. every command/resource/subcommand exposed by the installed candidate through `help`, `?`, role-specific completion/discovery, and command-specific help.

For every inventory entry, record exactly one disposition:

~~~text
DOCUMENTED=YES|NO
DISCOVERED_RUNTIME=YES|NO
ROLE=SERVER|AGENT|BOTH
EXECUTION_DISPOSITION=
  EXECUTED_PASS
  EXECUTED_FAIL
  NOT_APPLICABLE_ROLE
  NOT_RUN_SHARED_STATE
  BLOCKED_ENVIRONMENT
  DOC_RUNTIME_MISMATCH
SCENARIO_ID=<CLI-xxx or dedicated command check>
EVIDENCE=<path/reference>
~~~

Rules:

- Every documented or runtime-discovered public command must receive a disposition. No blank entries are allowed.
- `EXHAUSTIVE_AUDIT=PASS` is forbidden while any inventory entry lacks a disposition.
- A documented command that is absent from runtime discovery is `DOC_RUNTIME_MISMATCH`, not `NOT_APPLICABLE`.
- A runtime-discovered public command that is absent from canonical documentation is also `DOC_RUNTIME_MISMATCH`.
- A command that exists in documentation but is rejected by the installed public CLI must be executed far enough to capture that mismatch; do not silently omit it from the audit.
- Commands whose safe mutation cannot be executed because another active test owns shared state may use `NOT_RUN_SHARED_STATE`, but their help/discovery/safety contract must still be inspected.
- The ledger must explicitly include System history/revision/audit/diff/apply/restore/update/certificate/credential/support paths and any compatibility command still exposed by the candidate.
- Do not assume a plausible command such as `system rollback` exists merely because a document mentions it. If documentation lists it but exact runtime discovery does not, record `DOC_RUNTIME_MISMATCH` and preserve the contradiction as a finding.

At finalization report:

~~~text
COMMAND_INVENTORY_TOTAL=
COMMANDS_EXECUTED_PASS=
COMMANDS_EXECUTED_FAIL=
COMMANDS_DOC_RUNTIME_MISMATCH=
COMMANDS_NOT_APPLICABLE_ROLE=
COMMANDS_NOT_RUN_SHARED_STATE=
COMMANDS_BLOCKED_ENVIRONMENT=
COMMANDS_WITHOUT_DISPOSITION=0
~~~

## 4.2 Product feature ↔ CLI surface reconciliation — mandatory release gate

Before scenario execution, build a second ledger from the **product feature model**, not from the CLI. This prevents an internally consistent CLI from passing while product functionality is missing, duplicated, obsolete, or unreachable.

Use the union of:
1. Product Master features and supported lifecycle operations;
2. CLI/AI Master public behavior;
3. current Server and Agent menu/workflow surfaces;
4. installed candidate runtime discovery.

For every product capability, record:

~~~text
FEATURE=
PRODUCT_AUTHORITY=
EXPECTED_ROLE=SERVER|AGENT|BOTH|INSTALLER
CANONICAL_CLI=
RUNTIME_CLI=
MENU_PATH=
DISPOSITION=
  FEATURE_WITH_CANONICAL_CLI
  FEATURE_INSTALLER_ONLY_JUSTIFIED
  FEATURE_NO_CLI_GAP
  CLI_RUNTIME_ONLY
  CLI_WITHOUT_PRODUCT_FEATURE
  CLI_DUPLICATE_PATH
  CLI_LEGACY_OR_COMPATIBILITY_PATH
  CLI_SCENARIO_BLOCKED
  DOC_RUNTIME_MISMATCH
EVIDENCE=
~~~

Mandatory reconciliation rules:

- A product feature requiring normal operator control must have an actionable public path or an explicitly justified non-CLI lifecycle such as installation.
- Every runtime public command must map to exactly one current product capability.
- Duplicate commands for the same operation require an explicit product reason; compatibility alone is not sufficient for a greenfield/unreleased surface.
- Hidden commands and aliases are part of the audit if a user can execute them.
- Count all aliases, root-bypass aliases, hidden parser entries, and executable obsolete resources.
- Compare `show`, `set`, `unset`, and `test` symmetry where the resource model implies it.
- Compare direct CLI, guided menu, help, completion, and role-specific surfaces.
- A command's suggested next step must itself be a current canonical command or a precise documented installer/lifecycle action.
- Empty lists must explicitly report that no items exist.
- Status/version/provenance surfaces may differ in detail, but must not contradict one another.
- Obsolete product terms or semantics must not leak through hidden commands, diagnostics, errors, examples, or compatibility paths.
- For destructive commands, cancellation/no-confirmation must never be reported as successful mutation; exit status must be automation-safe.
- Exercise at least one complete workflow per major capability: discover → create/change → show → test/explain where applicable → reference/safety failure → cleanup.
- `FULL_USER_E2E` does not substitute for this reconciliation. Full User E2E validates real journeys and traffic; this gate validates product-model-to-CLI completeness and uniqueness.

At finalization report:

~~~text
CLI_PRODUCT_SURFACE_RECONCILIATION=PASS|FAIL
FEATURE_INVENTORY_TOTAL=
FEATURE_NO_CLI_GAPS=
RUNTIME_ONLY_CLI_COUNT=
DUPLICATE_PUBLIC_PATH_COUNT=
LEGACY_COMPATIBILITY_PATH_COUNT=
ROOT_BYPASS_ALIAS_COUNT=
HIDDEN_EXECUTABLE_PATH_COUNT=
SCENARIO_BLOCKED_COUNT=
STATUS_DOC_RUNTIME_MISMATCH_COUNT=
~~~

A stable candidate requires `CLI_PRODUCT_SURFACE_RECONCILIATION=PASS`. Any P0/P1 or user-blocking P2 found here blocks candidate freeze even if Full User E2E is otherwise green.

## 5. Mandatory scenario matrix

### CLI-001 — Entry, help, and discovery

Audit:

- `help`
- `?`
- `show ?`
- `set ?`
- `unset ?`
- `test ?`
- `system ?`
- `help commands`
- `help workflows`
- every area-specific help page used below.

Verify that discovery exposes every supported canonical path and does not advertise dead commands.

### CLI-002 — Version, status, diagnostics, and role

On Server and Agent, compare:

- version surfaces;
- `show status`;
- `system status`;
- `system info`;
- `system diagnostics`.

Verify version/role/source identity and health vocabulary are mutually understandable.

### CLI-003 — Managed Host discovery and identity

On Server:

- list Managed Hosts;
- inspect one host;
- inspect Agent identity;
- inspect addresses;
- inspect Remote Services;
- try the visible hostname and the visible Managed Host selector when they differ.

Verify output labels identify which value is accepted by subsequent commands. Internal/obsolete `client` terminology must not leak into user errors.

### CLI-004 — Objects and groups

Exercise Network Object/Group, Service Object/Group, Permission Object/Group, and Managed Host Group paths.

For each:

- create namespaced resource;
- show/list;
- inspect references;
- edit where supported;
- attempt deletion while referenced;
- delete in safe dependency order.

Verify Managed Host Group and Network Group are not conflated.

### CLI-005 — Agent local service and Remote Service

On Agent:

- compare `show services` and `show remote-services`;
- create a Remote Service;
- observe public endpoint allocation;
- test duplicate destination/service protection;
- delete the Remote Service;
- create a pending local service through the guided service wizard;
- verify pending changes are visible enough to review;
- discard without apply.

### CLI-006 — Remote Access

Create namespaced source, destination, and service objects; create whitelist rule; show policy; test allowed match; test unmatched/deny behavior where safe; verify references; remove all resources.

### CLI-007 — Internet Access

Repeat the same intent for Internet Access.

Also verify every advertised `show internet` / `test internet` compatibility or management path is executable if it remains public.

### CLI-008 — Enrollment

Audit all supported modes:

- manual;
- Zero-Touch;
- bulk.

Verify:

- `set enrollment ?` discovery;
- mode-specific help;
- one-hour default/TTL semantics;
- optional SSH username behavior;
- one-time command presentation;
- inventory/listing after issue;
- ability to discover the identifier needed for revoke/remove;
- safe cancellation;
- no secret leakage after the one-time display;
- no user-facing legacy double-dash grammar if the canonical public design forbids it.

### CLI-009 — Guided-flow cancellation and menu state

For representative Server and Agent wizards:

- paste a CLI command while the menu expects a number;
- enter an out-of-range number;
- use Back/Cancel;
- press Ctrl+C at a free-text prompt.

Expected: clear recovery, no traceback, no unintended mutation, and return to a usable prompt where appropriate.

### CLI-010 — AI Identity, Permission, and AI Access

Using namespaced resources:

- create/connect an AI Identity far enough to exercise the selected auth path;
- do not invent external OAuth approval;
- create permission object/group;
- attempt authorization with unverified identity and confirm fail-closed behavior;
- test AI Access;
- inspect AI Access log;
- clean up.

### CLI-011 — ConfigurationBundle

Create a reversible namespaced bundle containing multiple dependent resources.

Run:

- export where relevant;
- `test configuration`;
- `system diff configuration`;
- `system apply configuration`;
- same-state reapply.

Mandatory safety variants:

- file input;
- stdin input;
- TTY apply;
- non-TTY apply.

If command metadata says confirmation is required, mutation without that confirmation is a release-blocking finding. NO CHANGE may return safely without a destructive prompt only if that behavior is explicitly defined.

### CLI-012 — Backup, validate, restore

Create a backup, validate it, then enter restore far enough to verify preflight and confirmation behavior.

Expected:

- no internal traceback;
- destructive replacement never occurs before confirmation;
- clear warning about protected contents;
- pre-restore snapshot behavior matches documentation.

### CLI-013 — MCP/TLS/certificate read-only surface

Audit:

- MCP TLS status;
- MCP-specific diagnostics if advertised;
- certificate status/preflight;
- endpoint/authentication reporting.

Do not issue/import/renew a real certificate during shared active E2E unless the host is dedicated for that mutation.

### CLI-014 — System lifecycle and maintenance safety

Audit help and fail-closed behavior for:

- update;
- pause/resume/restart on Agent;
- autostart;
- support bundle;
- uninstall;
- restore;
- destructive group/host removal.

Actual restart/uninstall may be skipped only when it would interfere with concurrent designated testing; record the limitation.

### CLI-015 — Natural-language command guesses

Try common user terms:

- client / clients;
- host / hosts;
- service / services;
- policy / policies;
- config / configuration;
- status / version / diagnostics / backup.

Expected: canonical suggestion or useful compatibility behavior, not a silent generic dump.

### CLI-016 — Empty-list and success-message consistency

For every major list surface, verify an empty result visibly says no items exist.

For successful mutation/delete/revoke, verify the user receives an explicit success/result line.

### CLI-017 — Cross-surface state consistency

Compare the same resource/state across:

- Server `show services`;
- Server Managed Host Remote Services;
- Agent `show services`;
- Agent `show remote-services`;
- `show status`;
- `system status`;
- `system diagnostics`.

Do not require identical formatting, but flag semantics that make an active/healthy resource appear pending, unavailable, or degraded without explanation.

### CLI-018 — Role-boundary errors

Run representative Server-only commands on Agent and Agent-only commands on Server. Repeat once without required privilege when safe.

Expected: the error tells the user what role/privilege is actually required and does not misidentify the current host.

### CLI-019 — Destructive confirmation contract

For every public command whose help declares `Risk` or `Confirmation`:

- verify interactive confirmation;
- verify negative/cancel path;
- verify non-TTY fails closed unless an explicit public approval mechanism is documented;
- verify no mutation precedes confirmation.

### CLI-020 — Cleanup and audit evidence

Remove only resources owned by this audit and only when no concurrent lane still references them.

Record:

~~~text
RUN_ID=
PRODUCT_HEAD=
CONTENT_HEAD=
SERVER_HOST=
AGENT_HOST=
SCENARIOS_PASS=
SCENARIOS_PARTIAL=
SCENARIOS_FAIL=
SCENARIOS_BLOCKED=
RELEASE_BLOCKERS=
CLEANUP_STATUS=
EVIDENCE_ROOT=
~~~

## 6. Finding classification

Use:

- **P0** — safety/security/destructive confirmation violation or data-loss risk; release blocker.
- **P1** — functional/procedural blocker in a supported public workflow; release blocker unless explicitly out of scope.
- **P2** — material usability, discoverability, terminology, status-consistency, or recovery problem.
- **P3** — polish that does not materially impede a normal user.

Record the exact command, user-visible output, role, host, candidate identity, and cleanup result.

## 7. Audit discipline

During the audit:

- do not patch product code;
- do not repair the installed product by hand;
- do not use private APIs/DB edits to make a scenario pass;
- continue independent scenarios after failures;
- preserve evidence;
- use the active GitHub `[AI Work]` issue for consolidated findings.

After the audit is exhausted, implementation fixes may be handed to Cursor in bounded slices. After every product change, re-run affected scenarios on the new exact candidate.

## 7.1 Secret-safe evidence handling

Audit evidence must not turn one-time or long-lived credentials into durable logs.

Before collecting evidence:

~~~text
umask 077
mkdir -m 700 <EVIDENCE_ROOT>
~~~

Rules:

- Never store raw Zero-Touch tickets/install credentials, enrollment nonces, OAuth authorization codes, bearer tokens, client secrets, private keys, or raw protected backup contents in ordinary audit transcripts.
- Redact secret material **before** writing durable evidence or GitHub comments. Preserve only non-secret metadata needed for proof, such as operation type, timestamp, expiry, resource name/ID when non-secret, exit status, and a one-way hash only when comparison is required.
- If a public command displays a one-time credential, capture a redacted transcript such as `<REDACTED_ONE_TIME_CREDENTIAL>`; do not copy the credential into the final report.
- Secret-bearing backup archives or temporary enrollment artifacts created solely for the audit must remain local with restrictive permissions and must be deleted after their scenario no longer requires them.
- If raw secret-bearing evidence is temporarily unavoidable for a local test harness, keep it outside shareable logs under mode 0600/0700, never upload it to GitHub, and destroy it immediately after deriving redacted evidence.
- Evidence retention requirements never override the product security boundary.

## 8. Historical evidence is not a substitute

A prior audit report may be used to select regression targets, but it never counts as a current PASS. Every explicit trigger starts a fresh run against the current candidate.
