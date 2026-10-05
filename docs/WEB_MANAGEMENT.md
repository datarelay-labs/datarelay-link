# Data Relay Link — Optional Full Web Management

> **Status:** Planned Data Relay Link 3.0.0 design specification
> **Target release:** **3.0.0**
> **Roadmap:** DRL3-0 through DRL3-8 in `DATA_RELAY_ROADMAP.md`
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
- New 3.0 authoritative management state is never Web-only: operator/role state and saved
  policy-test state require a supported CLI or ConfigurationBundle management/recovery path.
- Operational Job state that can block/recover work requires CLI inspection/cancel/recovery
  capability even when its richer progress visualization is Web-specific.
- Web-only persistence is limited to non-security operator preferences such as Saved Views.

## 3. Goals

1. Reduce operator dependence on memorized CLI grammar.
2. Make Agent enrollment and first usable connection a guided workflow.
3. Make policy construction understandable before Apply.
4. Make allow/deny decisions explainable after Apply.
5. Make operation of 1–100 Managed Hosts practical without becoming a fleet platform.
6. Preserve the same safety, audit, concurrency, and fail-closed semantics across CLI and Web.
7. Keep production runtime small when the Web package is installed and unchanged when it is not.
8. Prevent unsafe policy changes with regression tests and blast-radius preview.
9. Make effective access and connection failures explainable without raw-log archaeology.

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

### 6.5 Management Scalability Layer

3.0 adds bounded logical management modules around the existing Core:

```text
Command Service
  security-relevant validation / Change Plan / authoritative mutation

Query Service
  bounded read-only queries / filtering / pagination

Derived Read Models
  rebuildable dashboard/inventory summaries; never recovery authority

Job Engine
  durable/bounded operation state for work that waits on Agents or multiple resources

Agent RPC Worker Pool
  concurrency limits / timeouts / backpressure / truthful per-target results

Operational State Aggregator
  heartbeat/runtime/health summaries without converting presence churn into config revisions

Audit/History Query Layer
  indexed bounded history and revision access
```

These are logical boundaries and may coexist in one process/package. 3.0 does not require
microservices, Redis, a broker, or an external database.

Hard scale rules:

- no SQLite write transaction waits for browser input or Agent RPC;
- no browser N-per-Host polling pattern;
- multi-Host work goes through bounded jobs, not unbounded threads;
- timestamp-only operational refresh is coalesced and does not create configuration revisions;
- read models can be deleted/rebuilt from authoritative Core state;
- relay enforcement remains available when Web/Query/Job components are degraded.

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

### 7.1 Draft Workspace

Web Management may hold a non-authoritative Draft Workspace for multi-resource work.

A Draft can:

- create/edit/delete proposed resources in memory or bounded ephemeral Core-owned draft state;
- generate the canonical Change Plan;
- render the current-versus-proposed diff;
- run embedded validation and saved policy regression tests;
- compute blast radius;
- render a proposed Effective Access Graph overlay;
- export/copy an equivalent ConfigurationBundle where safe.

Cancel produces zero authoritative mutation. Apply always returns through the normal
revision-bound Change Plan transaction. A Draft is never reconciled continuously and is
never a second desired-state database.

### 7.2 3.0 persistence classes

New management state is classified before schema work:

**Authoritative management state**
- Web operator identities and role assignments;
- saved policy regression-test definitions;
- any security-relevant Web configuration explicitly promoted to Core state.

This state is revision/audit aware where applicable and included in product backup/restore.

**Operator preference state**
- Saved Views and non-security UI preferences.

It may be persisted locally and backed up, but never affects policy without an explicit
authoritative operation.

**Operational state**
- browser sessions;
- active/background Job state;
- transient Attention aggregation.

This state must fail/recover truthfully after restart. Running jobs do not become
authoritative configuration and must not silently resume after restore.

**Derived state**
- dashboard/inventory/read-model summaries and caches.

Derived state is rebuildable from authoritative/operational sources and is never a
backup or restore authority.

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

Initial roles:

```text
Admin
  full supported management, security policy, restore/certificate, operator administration

Operator
  enrollment, Managed Hosts, Remote Services, diagnostics, synchronization,
  normal lifecycle and other explicitly delegated non-administrative operations

Read Only
  dashboard, inventory, audit, revisions, health, explain/test; no state mutation
```

Role checks are enforced by the Core management operation, not only by hiding Web controls.

Operator identity belongs to Core management state. It must not live only in browser
local storage or a Web-only database.
A local privileged bootstrap flow creates the first Web operator. Exact CLI grammar is
left to the implementation-phase CLI design, but plaintext passwords, bootstrap secrets,
or reusable session tokens must never be stored in normal audit or browser storage.

For password-backed local operators, require at least 8 characters including at least one
uppercase letter, one lowercase letter, and one digit; special characters are allowed but
not mandatory. Store only a modern salted password KDF and enforce bounded login rate
limits. TOTP MFA is available per operator but is **disabled by default**. A Web Admin
may enable or disable MFA for each Web operator from the Users page. Enabling MFA revokes
that operator's active browser sessions; the next successful password authentication enters
a user-owned enrollment flow that displays the TOTP seed only to that user, verifies a
current TOTP, then displays one-time recovery codes once. Recovery codes are stored only as
verifiers/hashes, and TOTP seed material follows protected credential handling. Disabling
MFA clears the enrolled factor/recovery codes and revokes active sessions so stale factors
do not remain authoritative. WebAuthn/passkeys or other factors may be added later.

The first privileged bootstrap creates a recovery Admin with MFA disabled. MFA policy is
then managed per user by Web Admins rather than being forced during bootstrap. Local
recovery remains available for isolated operation and does not depend on an external IdP.

SSO/OIDC/IdP integration is **not part of Data Relay Link 3.0**. Web administration and
CLI/Core recovery must not depend on an external identity provider.

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

Primary navigation uses task-oriented groups instead of exposing every page as a root item:

```text
Overview
Infrastructure
  Managed Hosts
  Remote Services
  Objects & Groups
  Connect Agent
Access Control
  Access Operations
  Policies
  Draft Workspace
Operations
  Jobs
  Version Drift
  Revisions
Observability
  Audit
  Doctor
  Health
  Search
  Saved Views
Administration
  Users
  System
```

The sidebar should keep the number of root-level choices small and group pages by operator
workflow. This follows the same general information-architecture direction used by current
zero-trust/admin products: consolidate analytics/logs/troubleshooting under an observability
area, keep resources/network inventory together, keep policy work together, and keep
identity/system administration separate from day-to-day operations. Product/internal names
should not become top-level navigation merely because they are implementation modules.

"Objects & Groups" contains Network, Service, and Permission resources without merging
their semantics. "Policies" contains Remote Access, Internet Access, and AI Access as
separate policy families within one access-control workspace; their identity/permission
semantics remain distinct inside the page.

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

Typical attention items include an offline/flapping Managed Host, a DEGRADED Remote
Service, repeated meaningful policy denial, version drift, a policy/runtime generation
mismatch, certificate expiry, backup readiness failure, failed background job, or an
expiring unused enrollment.

Attention is deduplicated/coalesced by affected resource and condition. Repeated state
flapping must not generate an alert storm.

The browser consumes aggregated summary endpoints or a bounded event stream. It must not
refresh one endpoint per Managed Host or Remote Service.

Do not add a time-series database merely to draw dashboard graphs. Initial charts and
counts derive from bounded current state, derived read models, and audit/event aggregates.

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

DRL3-3 implements Zero-Touch issuance through the existing Server allocator authority rather
than a Web-specific credential store. Issuance is Admin-only, TTL remains bounded by the
existing Zero-Touch 24-hour ceiling, and Linux/macOS/Windows guidance uses qualified
Server-local installer artifacts plus the existing allocator CA trust contract. The
credential-bearing install command is returned only by the issuance response; ordinary
Web enrollment history exposes lifecycle/status/expiry metadata only and cannot recover
that command or bootstrap credential.
 Manual Enrollment reuses the existing interactive Enrollment Code format: Linux/macOS
use a display-once Enrollment Code plus a separate pinned-CA install command that does not
embed the code; the default TTL is 10 minutes and the existing 30-day maximum remains in
force. Windows Manual Enrollment is not introduced by Web; Windows continues to use the
existing Zero-Touch path.

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

DRL3-3 exposes two Admin-only Managed Host lifecycle operations through actor/revision-bound
Core Change Plans:

- **Revoke trust** — typed `REVOKE`; marks the current management identity revoked and
  disconnected so it cannot authenticate/claim new work. The Managed Host inventory record,
  Remote Services, and public port reservations remain. Re-enrollment is required to
  establish trust again.
- **Retire Managed Host** — typed `RETIRE`; delegates to canonical
  `unset_managed_host` semantics. Preview shows owned Remote Services/port cleanup, and
  reference checks run before plan issuance and again under the expected revision at Apply.
  If a policy, group, Remote Service destination, or other supported Core reference still
  depends on the Host, retirement fails closed with no mutation.

These operations are deliberately distinct; Web must never label trust revocation as
deletion or imply that retirement uninstalls software on the remote Host.

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

Remote Service create/edit/delete uses a Core Change Plan followed by a target-bound Agent Management Job. The Web Apply response is `QUEUED`, not success. The owner Agent must claim the signed job with its enrolled management identity, execute the existing Agent-side Remote Service Core operation, and complete the Job before Web may show a terminal outcome. A disconnected or stale owner is blocked before enqueue, and runtime `DEGRADED` remains visible even when the configuration Job itself completed.

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
Apply.

### 19.1 Blast Radius Preview

Every security-relevant Draft/Change Plan shows a human-readable impact preview from the
Core evaluator:

- access broadened / narrowed;
- affected rules and referenced resources;
- affected Managed Hosts / Remote Services / destinations represented by current inventory;
- expected effective decision changes;
- newly reachable and newly blocked modeled flows where deterministically known;
- references that will be added or removed.

The preview must distinguish facts computed from current authoritative inventory from
estimates/unknowns. It must never imply that unobserved traffic has been exhaustively
enumerated.

Broadening and destructive changes require explicit confirmation using the same Core
impact result as the CLI.

### 19.2 Time-bounded Temporary Access — P1 Must Ship

The Policy Builder can add an explicit expiry to supported Remote / Internet / AI Access
rules or assignments without introducing a full access-request workflow.

3.0 UX is intentionally limited to:
- set, change, or clear a TTL/exact expiration and render canonical `expires_at`;
- show remaining validity and expired state in policy lists/details;
- include expiry in Draft, diff, blast-radius, audit, ConfigurationBundle, backup/restore,
  and policy-test views;
- warn near expiry only through the local Attention model;
- never rely on a browser timer for enforcement.

Expiration automatically denies **new authorization** at or after the server-authoritative
expiry. 3.0 does not add recurring access windows, automatic renewal, requester/approver
workflow, or automatic deletion of the rule as an enforcement requirement.

The UI states active-connection semantics separately and must not imply an already-
established connection was terminated merely because a temporary grant expired.

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

### 20.1 Saved Policy Regression Tests

Operators can save critical expected policy outcomes:

```text
source + destination + service/permission + plane
→ expected ALLOW or DENY
```

Tests are evaluated by the same Core policy engine. Required tests run against a proposed
Change Plan before security-relevant Apply. A failed required assertion blocks Apply
until the configuration or expected test is explicitly corrected.

Tests are versioned/audited management state and must survive backup/restore.

DRL3-4 persists saved assertions in the authoritative SQLite management schema so normal
backup/restore preserves them. Definition create/edit/delete uses actor/Server/revision-bound
Core Change Plans; Decision Trace, list, and run are query-only and must not create
configuration or operational metadata. Required enabled tests are executed against the
**proposed** state during security-relevant guided policy preview and are executed again
immediately before Apply. Any required mismatch or evaluator error blocks Apply with zero
authoritative mutation.

### 20.2 Effective Access Graph

The graph answers:

- who/what can reach this resource;
- what can this source reach;
- which Object/Group/rule path produces the effective decision;
- which relationships would change under the current Draft.

Graph edges are derived from current Core identity/object/policy/Remote Service state.
The graph is not a general network-discovery or packet-topology system.

A Draft overlay visibly separates current access from proposed additions/removals.
Selecting a path opens the underlying resource/rule and its Decision Trace.

DRL3-4 implementation contract:
- GET /api/v1/policy/graph is a query-only Web projection of the Core Effective
  Access Graph and requires the same policy-test authority as Decision Trace;
- graph construction is bounded to the 100-Host product target and returns explicit
  node/edge/path/host limits plus truncation metadata;
- Blast Radius separately reports result limits, total-vs-returned bounded counts, and
  explicit `truncated_by` reasons so a bounded preview is never presented as exhaustive;
- Internet destinations that would require live DNS during visualization are reported as
  UNKNOWN rather than causing the graph to perform network I/O or invent a decision;
- graph paths use the canonical Remote/Internet/AI policy evaluators, including AI
  path-required fail-closed semantics;
- Guided Change preview and Configuration Draft Workspace both evaluate current and
  rollback-only proposed state, then return added/removed/unchanged relationships and
  deterministic decision changes;
- only DENY -> ALLOW is labeled newly reachable and only ALLOW -> DENY is labeled
  newly blocked; UNKNOWN transitions remain explicit unknown/decision-change evidence;
- required Saved Policy Regression Tests run against proposed state during both guided
  and Configuration Draft preview and are re-run immediately before security-relevant
  Apply;
- the graph remains policy/inventory visualization only and is not exposed as a new
  Plugin/MCP capability in this slice.

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

Audit is generated through the shared Core audit architecture. Web Management is a
query/exploration surface over the central indexed SQLite history and owns no Web-only
audit store. It never reads raw per-plane audit spools directly.

The versioned event envelope has three logical streams:

~~~text
CONTROL
ACCESS_DECISION
SECURITY_LIFECYCLE
~~~

Audit Explorer filters by time, stream/type, stable event ID, actor and delegated identity,
originating surface, resource, operation, revision, result/reason, correlation/request/
session ID, policy/matched rule, access broadened/narrowed, and bounded source/destination
metadata where applicable.

Revision detail shows schema-redacted before/after summaries, Change Plan impact, runtime
activation, actor/interface attribution, and related events. Failed mutations remain
visible even when no new revision commits.

Access-decision detail stores only metadata Data Relay Link legitimately observes: source
identity/address as applicable, destination/service, allow/deny, matched policy/rule,
reason code, and bounded session/connection identifiers/timing. It never stores or shows
application payloads, TLS contents, credentials, tokens, private keys, or sensitive URL
query strings as normal audit fields.

The UI uses bounded cursor pagination and manual filtered NDJSON export over the same
versioned Core schema. Export is audited. The Core writes each export as a mode-0600,
schema-versioned artifact under `/var/lib/drlink/audit-exports/`, hard-bounded to 50000
events / 64 MiB. Web exposes only the resulting metadata/path; it has no audit-artifact
download endpoint. The Audit/Attention surfaces also expose ingestion lag, oldest pending
event age, spool-capacity/high-water state, and audit-degraded health without pretending
un-ingested events are already queryable. Continuous SIEM/S3/syslog/webhook streaming is
not a 3.0 GA dependency.

Active-local defaults are 365 days for CONTROL and SECURITY_LIFECYCLE, 90 days for
ACCESS_DECISION, and 500000 total events. Supported configuration bounds are 1–3650 days
and 1000–5000000 events. Age retention is split by category. Capacity pruning removes only
the oldest ACCESS_DECISION rows, at most 100000 per explicit run, and never silently
deletes CONTROL/SECURITY_LIFECYCLE rows to satisfy capacity. If protected history keeps
the database over capacity, the UI reports attention required. Retention configuration,
retention execution, and export execution are CONTROL-audited with the authenticated
actor/interface and do not create a configuration revision. The UI offers no arbitrary
audit-row edit/delete.

Diff and rollback reuse Core revision semantics. Backup/restore preserves retained event
identity/order and revision links; restore completion becomes a new lifecycle event after
restored state is authoritative.

3.0 adds no dedicated Auditor role. Admin / Operator / Read Only reuse the same redacted
audit query/export authorization unless later field demand proves a specialized role is
needed.

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

### 23.1 Connection Diagnosis

Connection Diagnosis is a guided correlation workflow, not a raw-log viewer.

For the selected flow it evaluates the applicable chain:

```text
input/source identity
→ policy mode/rule match
→ Managed Host / Agent presence
→ Remote Service configuration
→ runtime verification / endpoint allocation
→ target reachability or configured health-check result
→ DNS / Internet destination validation where applicable
→ recent bounded decision/activity evidence
```

It must identify which layer is proven healthy, failed, unknown, or not applicable.

Examples:

- no policy match under WHITELIST → policy failure;
- policy ALLOW + Agent disconnected → Agent/lifecycle failure;
- policy ALLOW + Agent connected + target health failure → target/network failure;
- no observed connection activity → clearly state that DRLink cannot prove the attempt
  reached the relevant data path instead of inventing a policy diagnosis.

### 23.2 Health collection at 100-host scale

Health views reuse existing heartbeat, runtime verification, configured health-check, and
recent activity signals.

Rules:

- the browser never launches one probe per row;
- probes/checks are server/Agent-side and globally bounded;
- configured periodic checks use concurrency/rate limits and jitter;
- unconfigured target health remains UNKNOWN/N/A rather than being silently probed;
- timestamp-only health/presence refresh is operational state, not a config revision;
- repeated flapping is coalesced before entering Attention Center.

### 23.3 Live Access Visibility — P1 Must Ship

The Web UI provides a bounded current-use view for each access plane, using only state the
product can actually prove.

Required fields when available include:
- access plane;
- Managed Host / Remote Service / destination;
- source identity/address;
- start time/duration when actually known;
- current policy/runtime revision;
- connection/session/job identifier only where the product owns one;
- status such as ACTIVE, CLOSING, ENDED, UNKNOWN;
- an explicit fidelity label: EXACT_PER_CONNECTION, AGGREGATE, or UNKNOWN.

3.0 does not require packet capture, payload inspection, session recording, or browser
polling that scales one request per Host.

### 23.4 Emergency New-Access Cutoff — P1 Must Ship

Normal policy edits continue to apply to **new** authorization and do not silently kill
established sessions. Emergency Cutoff is a separate reversible security override with
stronger confirmation and audit.

The 3.0 cutoff contract must:
- stop new authorization immediately at the selected supported scope;
- preserve normal operator policy so clearing the cutoff does not require reconstructing
  previous rules;
- provide at least one useful resource-level cutoff per access plane where current Core
  identity/resource semantics support it safely, plus a plane-level fallback;
- show the exact consequence before Apply, including that existing sessions may remain;
- expose active/recovered state in relevant resource, Attention, and Diagnosis views;
- use the same Core authorization/revision/audit/runtime path as other security mutations.

The current DRL3-5 implementation contract keeps these operations Core-owned:

- `drlink_diagnose_connection` is now a READY TEST operation shared by MCP and Web.
  It correlates current policy evaluation, Managed Host/Agent presence, Remote Service and
  runtime-generation facts, active cutoff state, and bounded recent access-decision
  evidence. Opening diagnosis never changes authoritative state.
- Diagnosis does not launch ad-hoc DNS or target probes from a browser request. Missing
  DNS, target-health, runtime, or activity evidence remains explicit `UNKNOWN`/N/A.
  AI file permissions without concrete path context are reported as unknown context while
  the underlying authorization remains fail-closed.
- `GET /api/v1/live-access` projects the existing bounded Core live-access read model.
  Internet and AI retain their proven fidelity; Remote Access remains `UNKNOWN` until
  supported official-FRP evidence exists.
- Web Emergency Cutoff uses the existing Core preview/apply/clear catalog operations and
  typed `CONFIRM CUTOFF`; it never rewrites normal policy and never claims established
  sessions were terminated.
- Attention Center derives an Emergency Cutoff item from authoritative active cutoff
  rows. Bounded cutoff reads report total/returned counts and truncation explicitly.
- Connection Diagnosis uses Remote Service runtime evidence only when
  `remote_service_meta.status/runtime_verified/pending_allocation/reason` proves it;
  an enabled Published Service without runtime verification remains UNKNOWN rather than
  being displayed as healthy. Verified DEGRADED target/runtime evidence is surfaced as a
  failed layer without launching a new probe.
- Attention Center is a bounded derived view over existing signals: disconnected/stale
  Hosts, DEGRADED Remote Services, canonical runtime-generation mismatch/failure,
  repeated recent access DENYs, version drift, Temporary Access nearing expiry or
  clock-trust failure, audit-spool/high-water degradation, certificate/backup/update
  readiness, failed/saturated Jobs, and active Emergency Cutoff state.
- Audit-spool health inspection is read-only: an absent spool stays absent merely because
  Overview/Attention was opened. Existing spool state is read without modifying its
  sequence/error files.
- `GET /api/v1/emergency-cutoffs` exposes bounded active/recovered cutoff state to the
  Web view; mutation still uses only the existing Core preview/apply/clear operations.

### 23.5 Active connection termination — P2 / conditional

Active termination is **not a 3.0 GA blocker**. It may ship per access plane only where
Data Relay Link owns the lifecycle or the pinned official upstream exposes a deterministic,
supported termination primitive.

Internet Access and AI work may qualify independently because DRLink owns more of those
lifecycles. Remote Access per-connection termination is not required for 3.0 and must not
be inferred from aggregate FRP connection metrics or require an FRP fork.

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

DRL3-3 first exposes the side-effect-free subset through the shared Core boundary:
installed product/Relay Engine provenance, a redacted certificate status view, certificate
hostname preflight, and disaster-recovery backup validation. Certificate responses must
not expose raw persisted TLS state, private-key paths, or private key material. Backup
validation delegates to the same canonical restore validator used by the CLI and never
implies restore authority.

The first artifact-producing Web operations also reuse canonical tools behind the Core
boundary. Protected Server backup creation is Admin-only and writes to
`/var/lib/drlink/backups/`; the browser never supplies an output path or receives archive
contents. Sanitized support-bundle creation is available to Admin/Operator and writes to
`/var/lib/drlink/support-bundles/`, again without archive download through this surface.
Both propagate the authenticated Web actor/interface to the canonical tool environment,
bound output, reject symlink/path escape, and do not create a configuration revision.

Certificate lifecycle is Admin-only for mutation. Web can configure the canonical
hostname/mode/contact-email/ACME-environment intent with typed `APPLY`, issue and activate
AUTO_ACME or PRIVATE_CA material with typed `ISSUE`, import USER_CERTIFICATE PEM material
with typed `IMPORT`, and run renew-if-due with typed `RENEW`. All operations delegate to
`drlink_mcp_tls`; no private-key path, raw TLS state, or PEM is returned. User-certificate
PEM is staged only in a private Core-owned temporary directory, the private key is mode
0600, and the staging files are deleted immediately after canonical import. Canonical
issue/import/renew activation retains or restores previous valid material according to
the existing TLS lifecycle, while Web adds authenticated actor/interface audit attribution.

Update checks for both Data Relay Link product management files and the pinned Relay
Engine reuse the canonical `--check` paths and remain read-only. Admin-only Relay Engine
apply requires typed `UPDATE ENGINE` and delegates to canonical `frp-update`, including
its rollback/RECOVERY_REQUIRED semantics. **Core product self-update apply is intentionally
not exposed from Web in DRL3-3** because it can change Core management files while the
optional Web package remains at its prior build. DRL3-7 closes that gap with Admin-only
typed `UPDATE PRODUCT`: Core creates a bounded root-owned request, activates a fixed
privileged one-shot, stops Web before Core mutation, runs the canonical product updater,
verifies the optional Web package against SHA256 plus the same immutable source ref/HEAD
and release channel, and only then reinstalls/restarts Web. A Core/Web identity mismatch
fails closed with recovery required; CLI/local recovery remains authoritative.

Restore is **Admin-only `RECOVERY_AUTHORITY`**. The browser accepts only a canonical
backup path under `/var/lib/drlink/backups/`, requires successful validation plus explicit
typed `RESTORE`, and Core revalidates again before invoking canonical `frp-restore --yes`.
The restore engine still recalculates access security impact immediately before cutover,
creates a pre-restore snapshot, and rolls back on failure when the previous state is
valid. Web enters maintenance for the restore call, reopens its auth DB afterward, revokes
all restored browser sessions, clears the caller cookie, and requires login again so
operational session state never resumes from backup.

### 24.1 Bounded multi-host operations

Operations across multiple Managed Hosts use the Job Engine and expose per-target state:

```text
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

Initial safe bulk scope:

- run/collect diagnostics;
- synchronize/refresh;
- check Agent/product versions and update availability;
- generate support bundles;
- export inventory;
- bounded metadata/group/tag assignment through normal Change Plan impact checks.

The initial 3.0 scope does not expose broad bulk delete/revoke/release/policy-reset or
unbounded mass update/restart. Those actions require a separate future risk/rollback
contract.

Current DRL3-6 bounded Job implementation:

- the frozen `drlink_diagnostic_job_start` catalog operation is READY for exactly
  `doctor`, `refresh`, and `version-check`; destructive or Remote Service mutation Job
  families cannot be started through this operation;
- target selection resolves immutable trusted Managed Host IDs only and is bounded to
  100 targets. A blank `managed-host` selector means all trusted Hosts only when the
  bounded result is at most 100; `managed-host-group` resolves existing Client Group
  membership and fails closed on empty/untrusted/oversized selection;
- Agent execution uses the existing signed target-bound Management Job claim/complete
  transport. Doctor runs with network probes disabled and returns a bounded redacted
  summary; refresh delegates to canonical Agent synchronization; version-check compares
  local product/Relay Engine versions to the Server-pinned target carried in the Job,
  providing offline-safe update-availability drift without a fleet-wide Internet check;
- public CLI recovery is available as `system jobs`, `system job <JOB-ID>`,
  `system job cancel <JOB-ID>`, and `system jobs recover`. Opaque Job IDs are never
  truncated. Recovery fails restart-interrupted work closed rather than silently
  resuming it;
- Web Jobs provides start/list/detail/per-target progress and cancel. Web cancellation
  is a Core/Web-only operation using the existing Job Engine and
  `management-job-run`; it does not add a new MCP tool or claim running RPC work was
  forcibly terminated;
- queue saturation, target-count limits, worker leases, deadlines, cancellation,
  per-target partial failure, and bounded worker-pool backpressure remain owned by the
  existing Job Engine. No SQLite write transaction spans Agent RPC.

The remaining safe-bulk candidates are implemented through explicit non-overlapping
contracts rather than by widening arbitrary fleet control:

- `support-bundle` is an admitted bounded Agent Job family. Each target Agent creates a
  unique sanitized local archive with the existing Support Bundle builder and returns only
  bounded artifact metadata (path, size, SHA-256, sanitized flag/counts) through the signed
  Job result; archive contents and private material are never relayed through the Server.
- inventory export is a Server-side bounded read artifact, not an Agent Job. Core writes
  allowlisted Managed Host, Remote Service, Managed Host Group, and tag metadata as
  `0600` NDJSON under `/var/lib/drlink/exports/`; 100-host and explicit related-resource
  limits fail closed instead of truncating silently. CLI `system export inventory` and Web
  use the same generator, and Web returns only path/count/hash metadata with no download
  endpoint.
- bounded fleet description/tag/Managed Host Group assignment uses one revision-bound
  Change Plan for at most 100 trusted immutable Managed Host IDs. Preview is rollback-only,
  typed `APPLY` is required, apply is atomic in one SQLite revision, and a stale revision
  fails without partial target mutation. Bulk label/rename is intentionally excluded so
  unique public-name semantics are not weakened.
- Managed Host Group add assignment preserves the canonical single-host behavior:
  assigning a new group name creates that inventory group atomically inside the same Change
  Plan; Managed Host Groups remain inventory-only and are not Network Group policy
  selectors.

With these additions, the initial DRL3-6 safe-bulk scope is covered without adding broad
delete/revoke/release/policy-reset or unbounded update/restart controls.

## 25. Search, filtering, and scale

The qualified 3.0 target is 1–100 Managed Hosts.

The UI provides:

- fast text search by stable identifiers and safe display metadata;
- status/platform/version filters;
- Object/Group/Tag relationship filters;
- policy relationship filters;
- health/attention/recent-problem filters;
- sortable compact tables;
- Saved Views for recurring operational slices such as Offline Hosts, Version Drift,
  DEGRADED Services, or Recent Policy Denies;
- persistent URL query state for shareable non-secret views;
- server-side bounded pagination/cursors rather than loading unbounded history/inventory.

SQLite indexes and bounded server-side queries remain the default. Do not introduce
distributed search or an external index merely for the 100-host target.

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
| Web operator identity / roles | 3.0 CLI management/recovery required | Full Web operator administration for Admin |
| Saved policy regression tests | 3.0 CLI/Bundle lifecycle required | Visual lifecycle + pre-Apply execution |
| Management Jobs | 3.0 CLI inspect/cancel/recovery required | Rich progress/per-target job UX |
| Saved Views / UI preferences | Not required | Web-specific non-security preference |

Implementation must generate/maintain a machine-auditable parity ledger from the current
public capability/catalog model. A new supported CLI management capability cannot be
considered Web-complete until it is either represented in Web Management or explicitly
classified as a CLI-shell-only mechanic with rationale.

## 27. Web API design

Initial browser API namespace:

```text
/api/v1/
```

This namespace is the first-party Web adapter contract, not the ChatGPT Plugin/MCP
management contract. Plugin/MCP reaches the same Core Management Service through the
separate Management MCP adapter defined by `MANAGEMENT_SURFACE_CONTRACT.md`; Plugin code
must not depend on Web endpoint shapes.

API resources mirror product nouns rather than internal table names.

Design rules:

- resource IDs are immutable identifiers; labels are presentation metadata;
- GET operations are side-effect free;
- state changes require explicit mutation methods and revision preconditions;
- mutation preview and commit are separate operations for security-relevant changes;
- structured errors include a stable code, safe message, affected resource, and retry/conflict guidance;
- list endpoints are bounded and support indexed search/filter/pagination for the 1–100-host target;
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

3.0 performance is designed and qualified at 100 Managed Hosts.

Required architecture properties:

- common navigation/list/detail queries are bounded and indexed;
- dashboard/inventory summaries use aggregate/read-model queries rather than N-per-Host calls;
- Web background refresh uses bounded frequency, jitter, and backoff;
- Agent RPC fan-out uses the bounded Job Engine/Worker Pool;
- browser sessions and event streams have hard resource limits;
- audit/history queries use bounded ranges and pagination;
- operational-state writes are coalesced where semantics permit;
- no Web request holds a SQLite write transaction while waiting on browser input or Agent RPC;
- Web/query/job failures cannot starve relay enforcement or CLI recovery.

The Web service has independent CPU/memory/service limits.

DRL3-0 establishes a reproducible reference profile and freezes measurable latency,
resource, saturation, and recovery SLOs after baseline measurement. Do not invent a new
external datastore solely because an unbounded implementation misses those SLOs.

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

This document uses the same phase IDs as the canonical roadmap. Do not maintain a second
Web-only phase plan.

### DRL3-0 — Scope and architecture freeze

Freeze product scope, 100-host qualification model, Management Scalability Layer,
operator/RBAC/authentication model (local TOTP MFA + recovery + session revocation),
Temporary Access expiry semantics, live-access visibility/cutoff capability limits per
plane, parity ledger, Agent RPC/jobs, state boundaries, and SLO methodology. SSO/IdP is
explicitly outside 3.0.

### DRL3-1 — Management Scalability Foundation

Extract/normalize the shared Core management operations, command/query boundaries,
derived read models, bounded Job Engine, Agent RPC Worker Pool, operational aggregation,
Temporary Access expiry primitive/time-trust behavior, bounded per-plane live-access
observation inputs, audit/history query layer, and capability inventory. Prove existing
CLI behavior is unchanged.

### DRL3-2 — Web Platform and Read-Only Operations

Package/service lifecycle, browser auth/session/RBAC, local TOTP MFA + recovery,
session revocation, Overview/Attention, inventory, search/Saved Views,
audit/revision/health read views, version drift, and Core-without-Web regressions.

### DRL3-3 — Guided Configuration and Full Management Parity

Enrollment, Object/Group lifecycle, Agent-owned Remote Service RPC, policy management,
Temporary Access set/change/clear expiry parity, ConfigurationBundle, system operations,
Draft Workspace, Change Plan preview/apply, and complete supported management parity.

### DRL3-4 — Policy Safety, Preview, and Explainability

Policy Simulator/Decision Trace, Time-bounded Temporary Access, Saved Policy Regression
Tests, Blast Radius Preview, Effective Access Graph, and Draft Graph Overlay.

### DRL3-5 — Diagnosis, Health, and Attention

Connection Diagnosis, Live Access Visibility followed by Emergency New-Access Cutoff,
structured Doctor/health, bounded health aggregation, recent decision correlation,
actionable Attention Center, and no diagnostic-side-effect paths. Active connection
termination is conditional by plane and not a 3.0 GA blocker.

### DRL3-6 — Bounded Fleet Operations

Visible Job Engine UX and the approved safe multi-Host operations. No broad destructive
fleet controls.

### DRL3-7 — Audit, Lifecycle, and 100-Host Hardening

Full audit/revision/lifecycle parity, retention/query indexing, backup/restore of 3.0
metadata, resource limits, saturation/backpressure, disconnect storms, read-model rebuild,
Web crash isolation, and 100-host mixed-load qualification.

### DRL3-8 — 3.0 Qualification and Stable Release

Exact-candidate browser Real E2E, security review, parity ledger closure, supported
platform/Agent E2E, 100-host scale gates, failure isolation, and same-HEAD Full Real E2E
release qualification.

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
LOCAL_OPERATOR_MFA=PASS
LOCAL_MFA_TOTP_RECOVERY=PASS
LOCAL_ADMIN_RECOVERY=PASS
SESSION_REVOCATION=PASS
SSO_IDP_DEPENDENCY=NO
ROLE_ENFORCEMENT=PASS
SECRET_REDACTION=PASS
MUTATION_AUDIT_ATTRIBUTION=PASS
AUDIT_FAILED_MUTATION_CAPTURE=PASS
AUDIT_SECRET_REDACTION=PASS
AUDIT_MUTATION_ATOMICITY=PASS
AUDIT_ACCESS_ALLOW_FAIL_CLOSED=PASS
AUDIT_DENY_REMAINS_DENY_ON_LOG_FAILURE=PASS
AUDIT_ENFORCEMENT_DB_READ_ONLY=PASS
SECURITY_IMPACT_CONFIRMATION=PASS
```

Agent ownership:

```text
AGENT_MUTATION_USES_AUTHENTICATED_RPC=PASS
AGENT_OFFLINE_FALSE_SUCCESS=0
AGENT_LOCAL_STATE_NOT_SERVER_WRITTEN=PASS
REMOTE_SERVICE_WEB_PARITY=PASS
```

Operator UX and policy safety:

```text
ENROLLMENT_GUIDED_E2E=PASS
DRAFT_WORKSPACE_ATOMICITY=PASS
POLICY_BUILDER_E2E=PASS
POLICY_DENY_REASON_DISCOVERABLE=PASS
DECISION_TRACE_MATCHES_CORE=PASS
POLICY_REGRESSION_GATE=PASS
BLAST_RADIUS_ACCURACY=PASS
EFFECTIVE_ACCESS_GRAPH_ACCURACY=PASS
CONNECTION_DIAGNOSIS=PASS
TEMPORARY_ACCESS_EXPIRY=PASS
TEMPORARY_ACCESS_CLOCK_FAIL_CLOSED=PASS
LIVE_ACCESS_VISIBILITY=PASS
LIVE_ACCESS_FIDELITY_LABEL=PASS
EMERGENCY_NEW_ACCESS_CUTOFF=PASS
EMERGENCY_CUTOFF_POLICY_PRESERVATION=PASS
ACTIVE_CONNECTION_TERMINATION_GA_REQUIRED=NO
REMOTE_ACCESS_TERMINATION_CLAIM_TRUTHFUL=PASS
ATTENTION_DEDUPLICATION=PASS
SAVED_VIEWS=PASS
VERSION_DRIFT_ATTENTION=PASS
AUDIT_DRILLDOWN=PASS
AUDIT_STREAM_FILTERING=PASS
AUDIT_CURSOR_PAGINATION=PASS
AUDIT_RETENTION_BOUNDS=PASS
AUDIT_NDJSON_EXPORT=PASS
AUDIT_BACKUP_RESTORE_CONTINUITY=PASS
AUDIT_INGEST_LAG_ATTENTION=PASS
AUDIT_SPOOL_BACKPRESSURE=PASS
DOCTOR_DRILLDOWN=PASS
BACKUP_RESTORE_WEB_E2E=PASS
UPDATE_LIFECYCLE_WEB_E2E=PASS
```

Fleet operations, failure isolation, and scale:

```text
BOUNDED_JOB_ENGINE=PASS
RPC_WORKER_BACKPRESSURE=PASS
BULK_SAFE_ACTION_SCOPE=PASS
HEALTH_COLLECTION_BOUNDS=PASS
NO_BROWSER_N_PER_HOST_POLLING=PASS
NO_SQLITE_TXN_WAITING_ON_AGENT_RPC=PASS
WEB_RESOURCE_LIMITS=PASS
WEB_QUERY_BOUNDS=PASS
WEB_RESTART_SESSION_BEHAVIOR=PASS
CORE_ENFORCEMENT_UNDER_WEB_FAILURE=PASS
READ_MODEL_REBUILD=PASS
100_HOST_CONTROL_PLANE_SCALE=PASS
100_HOST_MIXED_OPERATION_LOAD=PASS
```

## 35. Testing strategy

Minimum layers:

1. Core application-service unit tests.
2. CLI regression tests proving extraction did not alter public behavior.
3. Web API authorization/validation/concurrency tests.
4. Frontend component/workflow tests.
5. Browser E2E for primary operator journeys.
6. Server↔Agent authenticated RPC E2E for Agent-owned mutations.
7. policy-regression/blast-radius/access-graph parity tests against the Core evaluator.
8. security tests for CSRF, session, role, secret, TLS, and unsafe input handling.
9. Job Engine/RPC backpressure, timeout, cancellation, and disconnect-storm tests.
10. 10/50/100-host inventory and mixed-operation scale tests.
11. Web/query/job failure-isolation and read-model rebuild tests.
12. real-user E2E with a user who does not rely on CLI knowledge.

Browser E2E must include both successful and denied/blocked flows. Scale qualification
must mix heartbeat/status activity, dashboard/search/audit reads, policy explain, bounded
Agent jobs, and at least one configuration mutation without policy drift or false success.

A UI that only proves happy-path CRUD does not satisfy the product goal.

## 36. Design-gate summary

**Goal:** complete optional graphical administration and troubleshooting without weakening
the lightweight headless Core.

**Non-goals:** central SaaS, alternate database, monitoring platform, or CLI replacement.

**Affected public contract:** Data Relay Link 3.0 Web UX, management identity/roles,
optional package lifecycle, and browser-visible equivalents of supported management
capability. The 2.x CLI contract remains fully supported and the current v2.4 CLI grammar
is unchanged by this design.

**State/migration impact:** future implementation adds Core-owned operator identity,
local MFA metadata, Temporary Access expiry, Emergency New-Access Cutoff state, and Web
configuration/session metadata with ordered SQLite migration. Live access observations
remain operational/derived rather than policy authority. Existing identity/Object/policy/
Remote Service data remains authoritative and is not copied into a Web schema.
Disabling/uninstalling Web Management preserves all Core state.

**Security/operations impact:** a privileged management listener is added only when the
optional package is installed. Loopback is default; remote exposure requires explicit
TLS, local authentication + MFA, and revocable bounded sessions. A local recovery path
remains available and 3.0 has no SSO/IdP dependency. Temporary grants expire in Core
policy evaluation; Emergency New-Access Cutoff is separately confirmed/audited and never
overclaims active-session termination. Web service health and resource limits remain independent from relay
enforcement.

**Architecture boundary:** CLI, Web, ConfigurationBundle, and adapters share one Core
application/change-plan path. Agent-owned mutations remain Agent-owned via authenticated
RPC. The Management Scalability Layer adds bounded query/read-model/job/aggregation
modules without replacing SQLite authority or relay architecture.

**Scale impact:** 3.0 qualifies management behavior at 100 Managed Hosts while preserving
single-Server operation and Web/Core failure isolation.

**Acceptance:** section 34 plus the exact implementation-phase regression/Real E2E suite.

## 37. Implementation decisions intentionally left flexible

These choices may be finalized during DRL3-0/DRL3-1 without changing this product contract:

- exact first-party package/install command grammar;
- FastAPI versus an equivalent small supported Python HTTP adapter;
- Vite versus an equivalent static frontend build tool;
- SSE versus conservative polling for individual live views;
- exact operator-identity schema columns and session storage implementation;
- protected local TOTP seed/recovery-code storage details consistent with the fixed local
  MFA semantics;
- exact cutoff-state table/schema and per-plane live-access adapter where product
  semantics above remain unchanged;
- exact TLS certificate sourcing among approved product/operator-managed options.

Changing the authority model, making Web mandatory, adding alternate authoritative
storage, bypassing Agent ownership, or weakening security confirmation is not an
implementation detail and requires a new architecture decision.
## 38. Competitive pattern review and scope decisions

The 3.0 design was re-reviewed against current official product documentation on
2026-10-03. The goal is to adopt proven operator workflows without importing competitor
architecture or expanding Data Relay Link into another product category.

| Product/pattern | Data Relay Link decision |
|---|---|
| Tailscale visual policy editor, tests, preview | Adopt visual policy management, saved regression tests, and pre-Apply preview |
| Tailscale GitOps mode | Defer; ConfigurationBundle remains the current portable configuration artifact |
| Cloudflare policy tester / activity logs | Adopt impact preview and decision drill-down; no analytics platform |
| Twingate Access Graph | Adopt Effective Access Graph tied to actual DRLink policy/resource semantics |
| Twingate path-based troubleshooting | Adopt Connection Diagnosis that separates policy from data-path/target failures |
| Teleport inventory/version visibility | Adopt Agent/platform/version drift and attention |
| Teleport/Twingate role separation | Adopt Admin / Operator / Read Only; avoid role proliferation |
| NetBird Control Center / draft visualization | Adopt current-vs-draft graph overlay and fast relationship navigation |
| NetBird notifications | Design internal attention/event boundary; external channels move to later 3.x |
| Zscaler health/diagnostics | Adopt bounded health aggregation and drill-down; no application-discovery platform |
| Boundary worker health separation | Keep component health explicit; do not create controller/worker cluster architecture |
| Tailscale configuration audit / network flow separation | Adopt separate control and access streams, policy diffs, and exportability |
| Cloudflare admin / Access / Gateway log separation | Adopt actor/interface/request correlation and policy-decision drill-down; no analytics platform |
| Twingate actor/action/target JSON audit schema | Adopt versioned structured envelope and export-safe schema |
| Teleport audit event codes + session correlation | Adopt stable event/result identity and correlation; session recording remains excluded |
| StrongDM activities vs resource queries | Adopt management-vs-access streams and CLI filtering; no replay capture |
| Zscaler admin old/new values + request ID | Adopt safe before/after summaries and request correlation |
| Boundary sinks + sensitive-field controls | Adopt bounded local sink semantics and schema-aware redaction |
| NetBird audit + traffic events | Adopt searchable management/access separation on SQLite; no analytics datastore |
| ngrok audit/log export + Traffic Inspector | Adopt exportability only; do not add payload/body inspection or request replay |
| Tailscale external identity + MFA + recovery admin | Adopt local MFA/session recovery patterns only; SSO/IdP is excluded from 3.0 |
| Cloudflare MFA + bounded/revocable sessions | Adopt local MFA/session lifetime/revocation for Web admin; do not proxy application identity |
| Twingate Admin MFA + Ephemeral Access | Adopt local MFA and time-bounded policy access; defer access-request workflow |
| Teleport SSO/MFA + access/session TTL | Adopt MFA/TTL patterns only; SSO and full identity-governance/session-recording scope are excluded from 3.0 |
| Boundary active session list/cancel | Adopt live-access visibility and new-access cutoff; active termination only where DRLink/upstream owns the lifecycle |
| Zscaler authentication/idle timeout + session termination policy | Adopt local session/temporary-access lifetime semantics without broad ZTNA/SWG expansion |
| OpenZiti external identity + fine-grained permissions | Reinforces RBAC value only; SSO/IdP and clustered overlay-controller scope are not adopted for 3.0 |
| NordLayer SSO/MFA + posture | Adopt the MFA pattern only; SSO and posture/MDM remain outside DRLink 3.0 |

### 38.1 Review reference set

Official vendor documentation checked/re-checked on 2026-10-03:

- Tailscale Visual Policy Editor / tests / preview: https://tailscale.com/docs/features/visual-editor
- Cloudflare Access policy tester: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/policy-management/
- Cloudflare dashboard/admin activity logs: https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/
- Cloudflare connector health: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-wan/configuration/common-settings/check-tunnel-health-dashboard/
- Twingate troubleshooting / Resource Activity: https://www.twingate.com/docs/how-to-troubleshoot
- Twingate Access Graph / admin-role model: https://www.twingate.com/docs/users
- Teleport Web UI / Instance Inventory: https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/
- Teleport Access Graph: https://goteleport.com/docs/identity-security/policy-connections/
- Teleport role model: https://goteleport.com/docs/get-started/access/
- NetBird Control Center / Draft Mode: https://docs.netbird.io/manage/control-center
- NetBird user roles: https://docs.netbird.io/manage/team/user-roles
- NetBird audit events: https://docs.netbird.io/manage/activity
- Zscaler Private Access Health/Diagnostics index: https://help.zscaler.com/zpa
- HashiCorp Boundary worker status/health: https://developer.hashicorp.com/boundary/docs/concepts/workers
- HashiCorp Boundary read-only/auditor role examples: https://developer.hashicorp.com/boundary/docs/rbac/example-roles
- Tailscale configuration audit logging: https://tailscale.com/docs/features/logging/audit-logging
- Cloudflare admin activity logs: https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/admin-activity-logs/
- Cloudflare Access authentication logs: https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/access-authentication-logs/
- Cloudflare Gateway activity logs: https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/gateway-logs/
- Twingate audit logs: https://www.twingate.com/docs/audit-logs
- Teleport audit events: https://goteleport.com/docs/reference/deployment/monitoring/audit/
- StrongDM audit logs: https://docs.strongdm.com/admin/audit/logs
- Zscaler Private Access audit logs: https://help.zscaler.com/zpa/about-audit-logs
- HashiCorp Boundary event sinks: https://developer.hashicorp.com/boundary/docs/monitor/events/events
- NetBird audit events: https://docs.netbird.io/manage/activity
- ngrok audit logging overview: https://ngrok.com/security
- Tailscale SSO/OIDC/MFA: https://tailscale.com/docs/integrations/identity
- Tailscale independent recovery admin: https://tailscale.com/docs/reference/tailnet-passkey-admin
- Cloudflare MFA: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/mfa-requirements/
- Cloudflare session management/revocation: https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/session-management/
- Twingate Ephemeral Access: https://www.twingate.com/docs/ephemeral-access-to-resources
- Teleport access duration/TTL: https://goteleport.com/docs/identity-governance/access-requests/access-request-configuration/
- Teleport role/session TTL and MFA controls: https://goteleport.com/docs/reference/access-controls/roles/
- HashiCorp Boundary active session cancel: https://developer.hashicorp.com/boundary/docs/targets/sessions/cancel-sessions
- Zscaler Private Access timeout policy: https://help.zscaler.com/zpa/about-reauthPolicy
- OpenZiti v2 OIDC/JWT + permissions overview: https://blog.openziti.io/announcing-openziti-v2-0
- NordLayer access-control SSO/MFA/posture overview: https://nordlayer.com/network-security/access-control/

These links are research evidence, not product authority. Future competitor changes do not
automatically alter 3.0 scope after DRL3-0 freezes it.

### 38.2 Explicit competitive-feature deferrals
The following are intentionally **not** 3.0 GA requirements:

- full JIT/access-request approval workflow;
- session recording;
- browser SSH/RDP terminal;
- credential vault/injection;
- device-posture/MDM platform;
- broad application/network discovery;
- full traffic analytics;
- SIEM/reporting platform;
- external HA/multi-region controller architecture;
- large-fleet rollout/orchestration.

External notification channels, SSO/IdP integration (including OIDC/SAML/LDAP/SCIM),
GitOps editor locking, and continuous external audit/SIEM streaming are not 3.0
requirements and need separate field-demand review before entering a later roadmap.
Full JIT/access-request approval, device posture/MDM, session recording, credential
vault/injection, and payload replay remain outside 3.0.

Local TOTP MFA + recovery, time-bounded Temporary Access, Live Access Visibility,
Emergency New-Access Cutoff, and manual filtered NDJSON audit export are part of 3.0 GA.
Active connection termination is conditional by plane and not a GA blocker.

## 39. 3.0 scope-freeze contract

DRL3-0 is complete only when the roadmap and this design are sufficiently detailed that
implementation does not need to invent product semantics.

After scope freeze:

- a new competitor feature does not enter 3.0 merely because it is attractive;
- a new feature defaults to 3.1+ when it can be added without foundation rework;
- P0/P1 security/correctness gaps may modify 3.0 scope;
- measured scale evidence may modify an implementation detail, but not silently replace
  SQLite authority, Agent ownership, or the single-Core policy engine;
- every accepted scope change updates Product Master, Roadmap, this document, acceptance
  gates, and the active Work Packet before implementation.

This contract exists specifically to prevent late feature discovery from causing repeated
Core/API/UI redesign.
