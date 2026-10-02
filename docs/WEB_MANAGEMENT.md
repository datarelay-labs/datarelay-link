# Data Relay Link — Optional Full Web Management

> **Status:** Planned Data Relay Link 3.0.0 design specification
> **Target release:** **3.0.0**
> **Roadmap:** Phase DL-16
> **Version boundary:** 2.x = CLI is the only complete human management surface; 3.0 = first Full Web Management generation
> **Product authority:** `PRODUCT_MASTER.md`
> **Control-plane authority:** `CONTROL_PLANE_ARCHITECTURE.md`
> **Current CLI authority:** `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`
> **Design rule:** Web Management is optional infrastructure with full management capability, not a Core dependency.

## 1. Purpose

Data Relay Link must remain secure, recoverable, and fully operable without a Web UI.
At the same time, normal operators should not need to understand the CLI grammar to:

- enroll an Agent;
- create and relate Objects and Groups;
- publish a Remote Service;
- build Remote/Internet/AI Access policy;
- understand why a connection was allowed or denied;
- inspect health, revisions, audit, and operational failures;
- perform supported lifecycle, backup, restore, and update tasks.

Optional Full Web Management exists to make those workflows discoverable and visual
without introducing a second control plane.

## 2. Product contract
The capability relationship is:

```text
CLI management capability ⊆ Optional Web Management capability
```

This means functional parity, not one Web button for every shell grammar token.
CLI mechanics such as `help`, `menu`, shell completion, and `exit` map to native Web
navigation/help patterns rather than literal command replicas.

Required invariants:

- Core startup, relay enforcement, Agent connectivity, CLI, backup/restore, and recovery never depend on Web Management.
- Uninstalling or stopping Web Management does not change effective policy or authoritative state.
- Web Management can perform every supported management task that is meaningful in a browser.
- Web-specific value is dashboard, visualization, guided workflow, correlation, and explanation.
- Web Management never becomes an alternate source of policy truth.

## 3. Goals

1. Reduce operator dependence on memorized CLI grammar.
2. Make Agent enrollment and first usable connection a guided workflow.
3. Make policy construction understandable before Apply.
4. Make allow/deny decisions explainable after Apply.
5. Give 1–50-host environments a useful operational dashboard without a monitoring platform.
6. Preserve the same safety, audit, concurrency, and fail-closed semantics across CLI and Web.
7. Keep production runtime small when the Web package is installed and unchanged when it is not.

## 4. Non-goals

Optional Full Web Management is not:

- a replacement for the CLI;
- a second policy engine;
- a second authoritative database;
- a central SaaS or multi-server fleet manager;
- a SIEM, APM, time-series monitoring, or reporting platform;
- a generic third-party plugin framework;
- a reason to add Kubernetes, Redis, PostgreSQL, Elasticsearch, or similar mandatory services;
- a browser-based path that bypasses Agent ownership or security-impact confirmation.

## 5. Architecture overview

```text
Browser
   │
   ▼
drlink-web
HTTP/API adapter + compiled static UI
   │
   ▼
Shared Core Application Service
   ├── validation / reference resolution
   ├── Change Plan / policy explain
   ├── concurrency / confirmation contract
   ├── authoritative SQLite transaction
   ├── revision / audit
   └── runtime compile / activate / verify
```

The shared Core Application Service should be a local library/application layer, not
a mandatory new network daemon. CLI, Web backend, ConfigurationBundle, and integration
adapters call the same typed operations.

This avoids:

- a second network hop for local CLI work;
- a mandatory management daemon just to keep CLI working;
- duplicated validation/policy code;
- direct UI writes to SQLite.

## 6. Component model

### 6.1 Core

Core remains authoritative for:

- identities and Objects/Groups;
- policy modes/rules and policy evaluation;
- Agent/Managed Host state;
- Remote Service inventory/projection;
- Change Plan generation;
- SQLite transactions;
- revision/audit;
- runtime generation and activation;
- backup/restore and lifecycle invariants.

### 6.2 Web backend

`drlink-web` is an optional service that provides:

- browser authentication/session handling;
- a versioned HTTP API for the bundled frontend;
- request/response mapping to the shared Core Application Service;
- CSRF/session protection;
- streaming or polling of bounded operational events;
- static frontend asset delivery;
- no authoritative Web-only persistence.

The frontend-facing HTTP API is internal to the optional Web package in its first
release. It is not automatically a supported public automation API. Promoting it to a
stable external API is a separate public-contract decision.

### 6.3 Frontend

The reference implementation is a TypeScript/React single-page application built into
static assets. Node.js is a build-time dependency only; production does not require a
Node.js runtime.

The UI must be usable on a normal desktop browser. Tablet responsiveness is desirable;
phone-first operation is not a requirement for the initial phase.

### 6.4 Agent management path

Server-scoped operations execute locally through the Core Application Service.
Agent-scoped operations use the enrolled Agent's authenticated management/RPC path:

```text
Browser → drlink-web → Core request
                     → authenticated Agent RPC
                     → Agent-owned mutation
                     → result/state sync
                     → Web response
```

The Server never converts Agent-unreachable into success and never mutates a Server
projection to pretend an Agent-local operation completed.

## 7. State and mutation model
All state-changing Web requests follow the same pipeline as the CLI:

```text
read current revision / row version
→ validate
→ resolve references
→ compute policy/security impact
→ build Change Plan
→ preview diff
→ explicit confirmation when required
→ concurrency re-check
→ authoritative transaction
→ revision + audit
→ runtime compile / activate / verify
→ return final result
```

The browser never writes SQLite, runtime JSON, Agent local files, or generated FRP
configuration directly.

A Web preview is revision-bound. If authoritative state changes after preview, Apply
fails with a conflict and requires a fresh preview instead of silently rebasing the
operator's intent.

## 8. Packaging and deployment

Web Management is a separate add-on/plugin package, not a mandatory Core payload.

Conceptual identities:

```text
package/service     datarelay-link-web / drlink-web.service
runtime state       no separate authoritative database
frontend            bundled static assets
Core dependency     one-way: Web depends on Core, Core never depends on Web
```

The exact installer/CLI grammar is defined during implementation and must follow the
then-current CLI authority. The implementation must not require a general dynamic plugin
loader merely to install this first-party add-on.
## 9. Network exposure and transport security

Default:

```text
listen = 127.0.0.1
remote exposure = disabled
authentication = required even on loopback
```

Loopback access supports local browser use or an administrator-controlled SSH tunnel.

Remote listen is opt-in and must fail closed unless an approved TLS configuration is
present. A remote bind must never silently fall back to plaintext HTTP.

Certificate sourcing may use an approved Data Relay Link certificate path or an
operator-provided certificate. The implementation must not weaken TLS verification or
force browser users to accept an undocumented insecure mode.

The Web listener is a management surface and is not multiplexed with Remote Service or
Internet Access data traffic unless a later explicit architecture decision proves that
boundary safe.

## 10. Operator identity and authorization

Web operators are management identities, not Network Objects, Managed Hosts, or AI
Identities.

Initial minimum roles:

```text
Admin       read + supported mutation + lifecycle actions
Read Only   read + dashboard + explain/test, no state mutation
```

Operator identity belongs to Core management state. It must not live only in browser
local storage or a Web-only database.
A local privileged bootstrap flow creates the first Web operator. Exact CLI grammar is
left to the implementation-phase CLI design, but plaintext passwords, bootstrap secrets,
or reusable session tokens must never be stored in normal audit or browser storage.

For password-backed local operators, use a modern salted password KDF and bounded login
rate limits. External identity-provider support is additive later work and must not be a
prerequisite for initial local operation.

## 11. Browser session security

Required baseline:

- random high-entropy session identifiers;
- server-side session validation and revocation;
- HttpOnly cookies;
- SameSite=Strict unless a documented integration requires otherwise;
- Secure cookies whenever TLS is used;
- CSRF protection for state-changing requests;
- bounded session lifetime and idle timeout;
- login throttling without account-enumeration leakage;
- restrictive Content Security Policy;
- no secret values in URLs, browser history, analytics, or frontend logs.

One-time enrollment/install credentials may be displayed only according to their
existing one-time/TTL rules. The Web UI must make their credential nature visible.

## 12. UX principles

The Web UI optimizes for operators who understand the network task but do not know the
Data Relay Link CLI.

Rules:

1. Prefer task language over command grammar.
2. Show relationships before raw IDs; keep immutable IDs available in details.
3. Preview impact before Apply.
4. Explain deny/allow results in product terms.
5. Never hide the distinction between configuration state and runtime/health state.
6. Make destructive lifecycle meanings explicit: disable, release, revoke, reset, delete,
   rollback, restore, and uninstall are not interchangeable.
7. Keep default-deny/fail-closed states visually distinct from ordinary operational
   degradation.
8. Do not require users to inspect raw logs to answer "why is this blocked?"

## 13. Information architecture

Primary navigation:

```text
Overview
Managed Hosts
Remote Services
Objects & Groups
Access Policies
AI Access
Enrollments
Audit & Revisions
Health & Troubleshooting
System
```

"Objects & Groups" contains Network, Service, and Permission resources without merging
their semantics.

"Access Policies" contains Remote Access and Internet Access as separate policy families.
AI Access remains separate because identity, permission, and authentication differ.

Contextual detail pages should cross-link related entities. Example:

```text
Managed Host
├── identity / status / addresses
├── Remote Services
├── matching Network Object projection
├── relevant Access rules
├── recent decisions/events
└── Agent lifecycle / diagnostics
```
## 14. Overview dashboard

The dashboard is operational, not a generic infrastructure-monitoring product.

Required summary:

- Server/Core health and active revision;
- Managed Hosts total / connected / stale / disconnected;
- Remote Services healthy / degraded / disabled;
- Remote Access, Internet Access, and AI Access enforcement/mode summary;
- recent ALLOW/DENY decision counts when safely available from bounded audit data;
- active/expiring enrollment count;
- update, backup, and certificate attention where applicable;
- a Needs Attention queue with direct drill-down.

Typical attention items include an offline Managed Host, a DEGRADED Remote Service,
a denied required destination, a policy/runtime generation mismatch, certificate
expiry, backup readiness failure, or an expiring unused enrollment.

Do not add a time-series database merely to draw dashboard graphs. Initial charts and
counts derive from bounded current state and audit/event aggregates.

## 15. Agent enrollment and installation journey

The Web UI makes Agent enrollment a first-class guided workflow from platform selection
through enrollment issuance, bootstrap guidance, enrollment progress, and first
successful Managed Host connection.
Required enrollment UX:

- Zero-Touch and Manual Enrollment are clearly separated.
- TTL, remaining validity, used/revoked/expired state, and active-unused limits are visible.
- Secret-bearing enrollment material is display-once and never recoverable from normal history.
- Successful enrollment automatically transitions to the Managed Host detail view.
- Failed bootstrap/enrollment shows safe diagnostics without exposing secret material.
- Platform-specific guidance exists for Linux, Windows, and macOS where supported.
- The user can proceed directly from enrollment to Remote Service and policy setup.

The UI may provide copy actions for generated bootstrap guidance, but copying does not
change credential lifetime or security semantics.

## 16. Managed Hosts

List view requires:

- search by label, hostname, immutable ID, and address where safe;
- status filters;
- tag/group/object relationship filters where applicable;
- last-seen and lifecycle state;
- problem/attention indicators.

Detail view requires:

- immutable identity and operator metadata;
- current and reported addresses;
- Agent version/platform;
- connected/stale/disconnected state;
- Remote Services;
- relevant policy relationships;
- recent audit/decision activity;
- supported Agent lifecycle and diagnostic actions.

The UI must not imply that label or hostname is the immutable identity.

## 17. Objects and Groups

Web Management provides complete supported lifecycle for:

- Network Objects and Network Groups;
- Service Objects and Service Groups;
- Permission Objects and Permission Groups.

Forms must expose the actual product type constraints rather than generic key/value
editors. Invalid combinations are rejected before preview and again by Core.

Reference-aware deletion shows the blocking references and links directly to them.
There is no cascade-delete shortcut around the Core reference-protection contract.

## 18. Remote Services

Remote Service pages show both configuration and effective runtime state:

```text
name / immutable identity
owner Managed Host
target mode and target
Service Object
public endpoint / reservation
enabled state
HEALTHY / DEGRADED / DISABLED
last verification or synchronization state
related Remote Access policy
```

Create/edit/enable/disable/release/delete operations follow current ownership rules.
When initiated from the Server Web UI, Agent-owned changes execute through authenticated
Agent management/RPC and report unreachable/offline outcomes truthfully.

The UI must distinguish "configured correctly but target unreachable" from invalid
configuration and from policy denial.
## 19. Access Policy builder

Remote Access, Internet Access, and AI Access keep their distinct semantics.

For Remote/Internet policy the UI explicitly shows:

```text
Mode         BLACKLIST | WHITELIST
Enforcement  ENABLED | DISABLED
Rules        unordered named match records
Effective default implied by current mode
```

The UI must not invent ordered-rule or per-rule ALLOW/DENY semantics.

Rule forms use selectable Objects/Groups and explain invalid selector contexts before
Apply. Changes show a human-readable security-impact preview:

- access broadened;
- access narrowed;
- affected rules/resources;
- effective decision changes;
- references that will be added or removed.

Broadening and destructive changes require explicit confirmation using the same Core
impact result as the CLI.

## 20. Policy Simulator and Decision Trace

This is a primary Web Management feature, not an optional visualization.

The simulator consumes the same explain/test engine used by the public `test` behavior.
It does not reimplement policy evaluation in TypeScript.

Inputs use real flow concepts: source, destination, service or permission, access plane,
and any required identity context.
Trace output includes:

- normalized input;
- source/destination Object matches;
- Service/Permission matches;
- current policy mode and enforcement;
- all matching enabled rules;
- final BLACKLIST/WHITELIST decision;
- relevant Remote Service and reachability state for Remote Access;
- source-identity ambiguity/fail-closed reason where applicable;
- safe actionable explanation.

Example presentation:

```text
Result: DENY

Source
  203.0.113.50 → no selected source match

Policy
  Mode: WHITELIST
  Matching enabled rules: none

Final
  DENY because WHITELIST requires at least one enabled matching rule
```

Simulation must be clearly labeled as policy explanation. Real connectivity tests are a
separate operation and must not be implied by a simulated PASS.

Recent real ALLOW/DENY activity may link into the same Decision Trace view when the
audit/runtime evidence contains enough bounded input to reproduce an explanation.

## 21. AI Access
AI Access Web Management includes:

- AI Identity inventory and verification state;
- Permission Object/Group relationships;
- destination/path-scope relationships where applicable;
- AI Access mode, enforcement, and rules;
- bounded AI Access log exploration;
- authentication state and safe re-authorization guidance.

Web Management never treats an AI display name as authentication and never exposes raw
OAuth client secrets or bearer tokens through normal detail views.

## 22. Audit and revisions

Audit Explorer supports filtering by:

- time range;
- operator/actor;
- resource type and identity;
- operation;
- revision;
- result;
- access broadened/narrowed;
- policy family.

Revision detail shows the bounded before/after summary, Change Plan impact, runtime
activation result, and related audit events.

Diff and rollback use the existing Core revision semantics. The UI must not implement a
Web-only rollback mechanism.

## 23. Health and troubleshooting

Health & Troubleshooting presents `doctor`/health information as structured checks:

```text
PASS     healthy
WARN     attention recommended
FAIL     action required
UNKNOWN  cannot prove safely
```

Each failed check must link to the affected entity and give a safe explanation before
suggesting a mutation.

Priority troubleshooting journeys include:

- Managed Host disconnected/stale;
- Agent installed but not enrolled;
- Remote Service DEGRADED;
- public endpoint allocated but target unreachable;
- Remote Access denied;
- Internet Access denied;
- AI Access authentication or authorization denied;
- policy/runtime revision mismatch;
- certificate/TLS problem;
- backup/restore readiness problem;
- update/provenance mismatch.

Suggested fixes that change state must enter the normal preview/impact/confirmation
pipeline. A diagnostic card must never mutate state merely because it is opened.

## 24. System and lifecycle

Web Management covers meaningful browser equivalents for supported CLI system operations,
including:

- product/relay version and provenance;
- Server/Agent health;
- synchronization where applicable;
- product and Relay Engine update workflow;
- certificate status/lifecycle where supported;
- ConfigurationBundle test/diff/apply/export;
- backup creation/validation/restore;
- revision diff/rollback;
- support bundle generation;
- safe service/lifecycle operations.

Irreversible or high-impact actions require explicit confirmation and clear consequences.

## 25. Search, filtering, and scale

The target remains 1–50 Managed Hosts. The UI optimizes this range with:

- fast text search;
- status filters;
- Object/Group filters;
- policy relationship filters;
- recent-problem filters;
- sortable compact tables;
- persistent URL query state for shareable non-secret views.

Do not introduce large-fleet pagination infrastructure, distributed search, or an external
index solely for this phase. Server-side bounded queries against the authoritative store
are sufficient unless measured evidence proves otherwise.

## 26. Functional parity matrix

Every supported management capability must be classified during implementation:

| Capability family | CLI | Web target |
|---|---|---|
| Managed Host inventory/lifecycle | Required | Full functional parity |
| Enrollment | Required | Guided full parity |
| Network Object/Group | Required | Full parity |
| Service Object/Group | Required | Full parity |
| Permission Object/Group | Required | Full parity |
| Remote Service | Agent CLI | Full parity through Agent RPC where remotely supported |
| Remote Access policy | Required | Full parity + visual explain |
| Internet Access policy | Required | Full parity + visual explain |
| AI Identity / AI Access | Required | Full parity + auth-state UX |
| ConfigurationBundle | Required | Test/diff/apply/export UX |
| Audit / revisions / diff / rollback | Required | Full parity + explorer |
| Doctor / health / support bundle | Required | Full parity + structured visualization |
| Backup / restore | Required | Full parity with stronger confirmation UX |
| Update / certificate / lifecycle | Required where supported | Browser-equivalent supported actions |

Implementation must generate/maintain a machine-auditable parity ledger from the current
public capability/catalog model. A new supported CLI management capability cannot be
considered Web-complete until it is either represented in Web Management or explicitly
classified as a CLI-shell-only mechanic with rationale.

## 27. Web API design

Initial browser API namespace:

```text
/api/v1/
```

API resources mirror product nouns rather than internal table names.

Design rules:

- resource IDs are immutable identifiers; labels are presentation metadata;
- GET operations are side-effect free;
- state changes require explicit mutation methods and revision preconditions;
- mutation preview and commit are separate operations for security-relevant changes;
- structured errors include a stable code, safe message, affected resource, and retry/conflict guidance;
- list endpoints are bounded and support search/filter appropriate to the 1–50-host target;
- secrets are omitted or represented only by non-sensitive status metadata;
- Web responses do not expose SQLite schema or internal FRP implementation names.

A typical security-relevant flow is:

```text
POST /api/v1/change-plans
→ preview + impact + expected revision

POST /api/v1/change-plans/{id}/apply
→ concurrency re-check + authoritative mutation
```

Exact endpoint naming is implementation detail until the Web API is promoted to a public
external contract.
## 28. Reference implementation stack

Preferred initial implementation:

```text
Backend     Python
HTTP layer  FastAPI or equivalent small ASGI adapter
Frontend    React + TypeScript
Build       Vite or equivalent static build
Runtime     Python service + static assets
Database    existing Data Relay Link SQLite only
```

Framework choice is subordinate to the architectural invariants. If dependency review
shows a smaller supported stack provides the same security and maintainability, it may be
substituted without changing the product contract.

Production must not require:

```text
Node.js server
PostgreSQL
Redis
Elasticsearch
Kubernetes
external message broker
```

For near-real-time status, prefer bounded Server-Sent Events or conservative polling.
Do not add a message broker solely for browser refresh.

## 29. Error and conflict model

The UI distinguishes at least:

```text
VALIDATION_ERROR
REFERENCE_BLOCKED
REVISION_CONFLICT
AUTHENTICATION_REQUIRED
AUTHORIZATION_DENIED
AGENT_UNREACHABLE
CLIENT_ACTION_REQUIRED
RUNTIME_ACTIVATION_FAILED
ROLLBACK_INCOMPLETE
ENVIRONMENT_BLOCKER
```
Errors preserve the Core result. The Web layer may improve explanation but must not turn
a failure, pending action, or partial rollback into a green success state.

Revision conflicts return the operator to a refreshed preview/diff. They are not hidden
by automatic retry of a security-relevant mutation.

## 30. Performance and lightweight requirements

Initial targets are intentionally modest and measurable:

- normal navigation should feel interactive on a small DRLink Server;
- list/detail queries are bounded and indexed using the existing control-plane database;
- dashboard aggregation must not block policy enforcement or Agent management;
- Web background refresh uses bounded frequency and backoff;
- browser sessions and event streams have hard resource limits;
- audit queries require bounded time ranges/pagination when data grows;
- no Web request holds a SQLite write transaction while waiting on browser input or Agent RPC.

The Web service must have independent CPU/memory/service limits so a frontend bug or
expensive query cannot starve relay enforcement.

Exact numeric resource budgets should be established from measurement during
implementation rather than invented in this design document.

## 31. Observability

Web Management exposes its own health separately from Core health:

```text
Core Health        healthy / degraded / failed
Web Service        healthy / degraded / stopped
Browser Session    authenticated / expired
Agent RPC          per-host reachable / unavailable
```

A failed Web service is never presented as Core failure.

## 32. Accessibility and interaction

Initial Web Management should support:

- keyboard navigation for primary actions;
- visible focus states;
- labels not dependent on color alone;
- readable error and status text;
- copyable IDs/endpoints without truncation loss;
- confirmation dialogs that state the actual consequence;
- stable deep links for non-secret resource detail pages.

Dense tables may be desktop-oriented, but core workflows must remain understandable
without hover-only interaction.

## 33. Implementation sequence

### WM-0 — Shared Core management interface

- extract/normalize typed application-service operations from existing CLI/domain paths;
- prove CLI behavior remains unchanged;
- expose structured read models, Change Plan preview, apply, and explain results;
- add parity inventory machinery.

### WM-1 — Optional package and read-only Web

- package/service lifecycle;
- authentication/session baseline;
- Overview dashboard;
- Managed Host, Remote Service, Object/Group, policy, audit, revision, and health read views;
- Web-disabled/Core-only regression.

### WM-2 — Safe Server mutations

- Object/Group CRUD;
- enrollment lifecycle;
- Remote/Internet policy builder;
- ConfigurationBundle test/diff/apply;
- security-impact preview, confirmation, revision conflict, and audit attribution.

### WM-3 — Policy Simulator and troubleshooting

- Remote Access Decision Trace;
- Internet Access Decision Trace;
- AI Access explain where applicable;
- recent real decision correlation;
- Doctor/health drill-down and safe remediation entry points;
- no diagnostic-side-effect regressions.

### WM-4 — Agent-scoped full management

- authenticated Agent management/RPC contract for Web-initiated supported operations;
- Remote Service full lifecycle;
- Agent ConfigurationBundle and synchronization;
- supported Agent lifecycle/update/diagnostic actions;
- offline/unreachable truthfulness and retry behavior;
- no Server-side projection mutation pretending to be Agent success.

### WM-5 — Full parity and release qualification

- complete capability parity ledger;
- backup/restore/update/certificate/system workflows;
- Admin/Read Only authorization matrix;
- remote TLS exposure qualification;
- security review;
- Real Web E2E across supported Server/Agent platforms;
- failure-isolation/resource tests;
- documentation and operator usability closure.

## 34. Acceptance and regression criteria

The phase is not complete because pages render. The following observable contracts must
be proven on the exact candidate.

Core independence:

```text
WEB_NOT_INSTALLED_CORE=PASS
WEB_STOPPED_CORE=PASS
CLI_FULL_CAPABILITY_WITHOUT_WEB=PASS
WEB_FAILURE_DOES_NOT_CHANGE_POLICY=PASS
NO_WEB_AUTHORITATIVE_DB=PASS
```
Semantic parity:

```text
CAPABILITY_PARITY_LEDGER=PASS
CLI_WEB_READ_PARITY=PASS
CLI_WEB_CHANGE_PLAN_PARITY=PASS
CLI_WEB_POLICY_EXPLAIN_PARITY=PASS
CLI_WEB_REFERENCE_PROTECTION_PARITY=PASS
CLI_WEB_CONCURRENCY_PARITY=PASS
```

Security:

```text
LOOPBACK_DEFAULT=PASS
REMOTE_BIND_REQUIRES_TLS=PASS
AUTH_REQUIRED_ON_LOOPBACK=PASS
CSRF_PROTECTION=PASS
SESSION_SECURITY=PASS
ROLE_ENFORCEMENT=PASS
SECRET_REDACTION=PASS
MUTATION_AUDIT_ATTRIBUTION=PASS
SECURITY_IMPACT_CONFIRMATION=PASS
```

Agent ownership:

```text
AGENT_MUTATION_USES_AUTHENTICATED_RPC=PASS
AGENT_OFFLINE_FALSE_SUCCESS=0
AGENT_LOCAL_STATE_NOT_SERVER_WRITTEN=PASS
REMOTE_SERVICE_WEB_PARITY=PASS
```

Operator UX:

```text
ENROLLMENT_GUIDED_E2E=PASS
POLICY_BUILDER_E2E=PASS
POLICY_DENY_REASON_DISCOVERABLE=PASS
DECISION_TRACE_MATCHES_CORE=PASS
AUDIT_DRILLDOWN=PASS
DOCTOR_DRILLDOWN=PASS
BACKUP_RESTORE_WEB_E2E=PASS
UPDATE_LIFECYCLE_WEB_E2E=PASS
```

Failure isolation and scale:

```text
WEB_RESOURCE_LIMITS=PASS
WEB_QUERY_BOUNDS=PASS
WEB_RESTART_SESSION_BEHAVIOR=PASS
CORE_ENFORCEMENT_UNDER_WEB_FAILURE=PASS
TARGET_SCALE_50_HOST_USABILITY=PASS
```

## 35. Testing strategy

Minimum layers:

1. Core application-service unit tests.
2. CLI regression tests proving extraction did not alter public behavior.
3. Web API authorization/validation/concurrency tests.
4. Frontend component/workflow tests.
5. Browser E2E for primary operator journeys.
6. Server↔Agent authenticated RPC E2E for Agent-owned mutations.
7. security tests for CSRF, session, role, secret, TLS, and unsafe input handling.
8. resource/failure-isolation tests.
9. real-user E2E with a user who does not rely on CLI knowledge.

Browser E2E must include both successful and denied/blocked flows. A UI that only proves
happy-path CRUD does not satisfy the product goal.

## 36. Design-gate summary

**Goal:** complete optional graphical administration and troubleshooting without weakening
the lightweight headless Core.

**Non-goals:** central SaaS, alternate database, monitoring platform, or CLI replacement.

**Affected public contract:** Data Relay Link 3.0 Web UX, management identity/roles,
optional package lifecycle, and browser-visible equivalents of supported management
capability. The 2.x CLI contract remains fully supported and the current v2.4 CLI grammar
is unchanged by this design.

**State/migration impact:** future implementation may add Core-owned operator identity,
role, and Web configuration/session metadata with ordered SQLite migration. Existing
identity/Object/policy/Remote Service data remains authoritative and is not copied into a
Web schema. Disabling/uninstalling Web Management preserves all Core state.

**Security/operations impact:** a privileged management listener is added only when the
optional package is installed. Loopback is default; remote exposure requires explicit
TLS and authentication. Web service health and resource limits are independent from
relay enforcement.

**Architecture boundary:** CLI, Web, ConfigurationBundle, and adapters share one Core
application/change-plan path. Agent-owned mutations remain Agent-owned via authenticated
RPC.

**Acceptance:** section 34 plus the exact implementation-phase regression/Real E2E suite.

## 37. Implementation decisions intentionally left flexible

These choices may be finalized during WM-0/WM-1 without changing this product contract:

- exact first-party package/install command grammar;
- FastAPI versus an equivalent small supported Python HTTP adapter;
- Vite versus an equivalent static frontend build tool;
- SSE versus conservative polling for individual live views;
- exact operator-identity schema columns and session storage implementation;
- exact TLS certificate sourcing among approved product/operator-managed options.

Changing the authority model, making Web mandatory, adding alternate authoritative
storage, bypassing Agent ownership, or weakening security confirmation is not an
implementation detail and requires a new architecture decision.
