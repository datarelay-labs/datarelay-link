# Data Relay Link Roadmap

> **Role:** Forward-looking product roadmap and implementation ordering
> **Product authority:** `PRODUCT_MASTER.md`
> **Version authority:** `VERSION_POLICY.md`
> **3.0 Web/management design:** `WEB_MANAGEMENT.md`
> **Current 2.x CLI authority:** `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`
> **Rule:** actual exact-HEAD implementation and qualification evidence override status snapshots in this document.

## 1. Roadmap model

This roadmap separates **product generations** from historical implementation tasks.

```text
2.x
= headless Core
= CLI is the only complete human management surface
= bounded integrations such as MCP may exist

3.0+
= same headless Core and complete CLI
+ Optional Full Web Management
+ management scalability and operator-safety layer
```

The old DL-0..DL-15 sequence described how the v2.4 foundation was built. Those steps are
no longer future roadmap phases and must not be used to restart already-implemented work.

## 2. Product generations
### Data Relay Link 2.x

Primary outcome:

> Securely relay only approved connections while remaining lightweight, headless, and
> fully manageable through `drlink`.

Supported design center:

- single Data Relay Link Server;
- embedded SQLite control-plane authority;
- official relay engine;
- Managed Host / Agent identity;
- Remote Service;
- Remote / Internet / AI Access;
- ConfigurationBundle and Change Plan;
- revision/audit/runtime generation;
- CLI as the complete human administration surface.

### Data Relay Link 3.0

Primary outcome:

> Keep the 2.x Core intact while making deployment, policy management, troubleshooting,
> and operation of up to 100 Managed Hosts practical through an optional full Web
> management surface.

3.0 is an operator-experience and management-scale generation, not a new relay engine or
network architecture.

## 3. 2.x baseline
The following are **implemented foundation**, subject to final qualification of the exact
release candidate rather than future redesign:

```text
SQLite SSOT + migrations
immutable Managed Host / Agent identity
Network / Service / Permission Objects and Groups
Managed Host address inventory
Agent-owned Remote Services
BLACKLIST / WHITELIST Remote Access
BLACKLIST / WHITELIST Internet Access
AI Identity + AI Access / MCP Bridge
revision / audit / runtime generation
backup / restore / migration
canonical CLI
ConfigurationBundle + shared Change Plan
bounded Zero-Touch enrollment issuance
runtime rollback / fail-closed safety
```

Do not reopen these foundations merely to implement Web Management. A 3.0 design that
requires replacing them is a foundation-change proposal and requires an explicit product
architecture decision.

## 4. v2.4 release closure

**Status:** Active qualification/release closure. Not yet a stable-release claim in this
roadmap.

Remaining work is release closure, not architecture invention:
- exact candidate integration and governance;
- CLI/feature/workflow reconciliation on the exact candidate;
- Full User E2E and real application qualification;
- supported platform/topology evidence;
- artifact/provenance/checksum/SBOM integrity;
- final same-HEAD qualification gates;
- immutable v2.4.0 publication only after all mandatory gates pass.

The active `[AI Work] v2.4.0 Release Closure` packet and exact release branch are the
authority for detailed current closure state.

## 5. 2.x maintenance after v2.4

Allowed within 2.x:

```text
PATCH  backward-compatible defect/security fixes
MINOR  backward-compatible Core/CLI/integration features
```

Not allowed in a 2.x stable line:

```text
Full supported Web Management product surface
Web becoming required for Core operation
alternate authoritative management database
```

## 6. Data Relay Link 3.0 product outcome
A successful 3.0 operator can:

1. install/enroll a Managed Host without learning CLI grammar;
2. understand all Managed Hosts, Remote Services, policies, and health from one UI;
3. build policy and see its impact before Apply;
4. prove expected allow/deny behavior with saved policy regression tests;
5. answer "why is this connection blocked?" without reading raw logs;
6. see who/what currently has effective access to a resource;
7. diagnose whether failure is identity, policy, Agent, runtime, target, DNS, or network;
8. perform safe bounded operations across groups of Hosts;
9. understand revision history and safely recover from a bad change;
10. operate up to 100 Managed Hosts without requiring an external DB or orchestration stack.

Web Management remains optional. The same product remains fully operable through Core +
CLI when `drlink-web` is absent or stopped.

## 7. 3.0 scale contract

Qualified management target:

```text
1–10 hosts     extremely simple
10–50 hosts    normal operating range
50–100 hosts   fully supported 3.0 management target
>100 hosts     no stable support claim until separately measured/qualified
```
100 is a qualification target, not a reason to turn the product into a fleet platform.

3.0 keeps:

- one Data Relay Link Server;
- SQLite as authoritative state;
- no PostgreSQL/MySQL/Redis requirement;
- no Kubernetes requirement;
- no message broker requirement;
- no distributed control plane.

Scale is achieved through bounded management work, not infrastructure multiplication.

## 8. Feature-admission and scope-freeze rule

A feature enters 3.0 GA only when it satisfies all of these:

1. directly improves deploy/configure/explain/troubleshoot/operate workflows;
2. has clear value at the 1–100-host target;
3. reuses existing Core identity/policy/state semantics;
4. does not turn Link into SASE, RMM, SIEM, PAM, or fleet orchestration;
5. has an objective acceptance test;
6. cannot be added later with equal value and no foundation rework.

After **DRL3-0 Scope Freeze**, new ideas default to 3.1+ unless they close a security,
correctness, or architecture-blocking gap in the accepted 3.0 contract.

## 9. 3.0 architecture invariants
The following are frozen unless an explicit foundation decision changes them:

```text
SQLite = authoritative control-plane state
CLI = complete administration + recovery path
Web = optional presentation/management surface
Agent-owned state = mutated by Agent through authenticated RPC
Change Plan = shared mutation semantics
policy engine = single implementation
revision/audit = shared across CLI/Web/Bundle
runtime artifacts = derived state
```

3.0 adds a **Management Scalability Layer** as logical modules, not mandatory
microservices:

```text
Command Service
Query Service / Read Models
Bounded Job Engine
Agent RPC Worker Pool
Operational State Aggregator
Audit / history query layer
```

### 9.1 First-class audit logging contract

Audit is a Core security/operations capability shared by CLI, Web, ConfigurationBundle,
AI-assisted operations, Agent RPC, and system lifecycle paths. It is not a Web-only
activity feed and it is not generic debug logging.

3.0 uses one versioned structured event envelope with three logical streams:

~~~text
CONTROL            administrative/configuration mutations and failed attempts
ACCESS_DECISION    Remote / Internet / AI allow-deny and observable connection metadata
SECURITY_LIFECYCLE authentication, enrollment, revoke, backup/restore, update and audit lifecycle
~~~

Every event carries, when applicable: schema version, stable event ID, Server-local
monotonic sequence, UTC time, event type, actor/delegation identity, originating surface,
action, resource identity, result/reason code, correlation/request/session ID, revision
before/after, matched policy/rule, safe before/after summary, and bounded source/destination
metadata.

Product rules:

- CONTROL and SECURITY_LIFECYCLE audit cannot be disabled.
- Successful and failed security-relevant mutations/authentication attempts are recorded.
- A state mutation and its audit record commit atomically. If durable audit persistence
  fails, the mutation fails.
- A would-be ACCESS_DECISION ALLOW is not released until its event is durably enqueued.
  Enqueue/spool failure therefore converts ALLOW to DENY. A policy DENY remains DENY even
  if its audit enqueue also fails; the audit subsystem becomes CRITICAL and surfaces the
  loss counter. Existing established connections are not torn down solely because the
  audit store later degrades.
- Secrets, credentials, bearer tokens, private keys, application payloads, TLS contents,
  and sensitive URL query strings are never normal audit fields.

- Before/after data uses schema-aware allowlisting/redaction, not regex-only scrubbing.
- Audit is append-only through normal product APIs. 3.0 exposes no arbitrary edit/delete;
  expiry occurs only through retention policy.
- Active query history stays in SQLite/Core with bounded time-range queries, cursor
  pagination, indexes, and hard resource limits. Privilege-separated Remote/Internet
  enforcement writes ACCESS_DECISION events first to a bounded durable per-plane spool;
  a Core Audit Ingestor imports them to SQLite in short idempotent batches.
- CLI and Web both provide bounded read/filter/detail access to the same event model.
  Exact additive CLI grammar is frozen in DRL3-0; neither surface may invent its own semantics.
- 3.0 provides manual filtered NDJSON export using the same versioned schema from CLI and
  Web. A separate bounded signed event Webhook may deliver selected Attention/security
  lifecycle events; continuous SIEM/S3/syslog bulk audit streaming remains later-additive.
- Append-only semantics are not described as tamper-proof against a privileged host admin.

Default active-local retention targets:

~~~text
CONTROL + SECURITY_LIFECYCLE   365 days
ACCESS_DECISION                 90 days
TOTAL EVENT CAPACITY            500000 events
~~~

DRL3-7 freezes the supported configuration bounds at 1–3650 days per retention class and
1000–5000000 total events. Age retention is applied independently to
CONTROL/SECURITY_LIFECYCLE and ACCESS_DECISION. Capacity pruning may remove only the
oldest ACCESS_DECISION rows, is bounded to 100000 events per explicit retention run, and
must never silently delete CONTROL or SECURITY_LIFECYCLE rows merely to satisfy capacity.
If protected history keeps the database above the configured capacity, the run reports
ATTENTION_REQUIRED instead of deleting protected history.

Manual filtered NDJSON export is Core-owned, schema-versioned, mode 0600, stored only under
`/var/lib/drlink/audit-exports/`, and hard-bounded to 50000 events / 64 MiB. Web returns
artifact metadata/path only and exposes no archive download endpoint. Retention
configuration, explicit retention execution, and audit export execution are themselves
CONTROL-audited with actor/interface attribution and do not create a configuration
revision.

The product may not silently discard not-yet-expired security audit to recover space.

Backup/restore preserves retained event IDs, ordering, schema versions, and revision links.
Restore completion creates a new lifecycle event after restored state is authoritative.

No dedicated Auditor role is required for 3.0. Admin / Operator / Read Only reuse the
redacted audit query/export authorization model; a specialized role can be added later.

### 9.2 Priority and minimum-scope review

The additional 3.0 security/operations features are intentionally split by priority:

| Priority | Capability | 3.0 release meaning |
|---|---|---|
| P0 security baseline | Per-user local Web MFA capability + session revocation/recovery | MFA capability is required, disabled by default, and Admin-controlled per operator; not a differentiating product feature |
| P1 Must Ship | Time-bounded Temporary Access | Required product-value feature; expiry affects new authorization only |
| P1 Must Ship | Live Access Visibility | Required operations feature; exact/aggregate/unknown fidelity must be explicit |
| P1 Must Ship | Emergency New-Access Cutoff | Required incident-response feature; reversible deny override for new authorization |
| P0 Must Ship | Managed Host Approval / Quarantine | Optional approval gate for newly enrolled Hosts; pre-approved enrollment preserves Zero-Touch automation |
| P0 Must Ship | Managed Update / Staged Rollout | Bounded manual canary/wave Agent rollout with pause-on-failure and canonical rollback where supported |
| P1 Must Ship | Public Automation API + Service Accounts | Supported versioned automation surface with scoped non-human principals and full audit |
| P1 Must Ship | Signed Event Webhook | Generic optional signed HTTPS event delivery with bounded retry/health; direct vendor connectors remain later |
| P1 Must Ship | Access Hygiene Recommendations | Read-only evidence-qualified stale/unused/orphaned/expiring access findings; no automatic mutation |
| P2 stretch | Lightweight JIT Access Request / Approval | One local requester→Admin flow that creates normal Temporary Access; not a GA blocker |
| P2 conditional | Active connection termination | Ship only per plane where deterministic lifecycle control is proven; not a 3.0 GA blocker |

Implementation order follows dependency rather than the table order:

```text
DRL3-0  freeze semantics/bounds
DRL3-1  policy expiry + Host approval + service-account/webhook foundations
DRL3-2  local Web MFA/session baseline + pending-host visibility
DRL3-3  Temporary Access parity + Host approval + Automation API/service-account management
DRL3-4  Temporary Access preview/test UX + optional lightweight JIT request model
DRL3-5  Live Access Visibility → Emergency Cutoff + Access Hygiene + signed Webhook
DRL3-6  bounded staged Agent update rollout
DRL3-7  hardening/recovery/scale for all admitted surfaces
DRL3-7A modern SaaS workspace + DR Control visual parity
DRL3-8  exact-candidate qualification
```

SSO/IdP integration is not required by or implied by this priority model.

## 10. DRL3-0 — Scope and architecture freeze

**Goal:** remove design ambiguity before feature implementation.

Required:
- generation/scale contract frozen;
- Management Scalability Layer boundaries frozen;
- Web authentication/RBAC model frozen, including offline-capable local MFA, local recovery, browser-session lifetime/idle timeout, and revocation; SSO/IdP integration is excluded from 3.0;
- Temporary Access data model and expiry semantics frozen, including supported policy scopes, set/change/clear operations, clock-failure behavior, and explicit non-termination of established sessions;
- live-access visibility granularity and Emergency New-Access Cutoff semantics frozen per access plane, with exact-vs-aggregate-vs-unknown visibility and official-FRP/no-fork limits explicit;
- shared management-operation contract frozen through `MANAGEMENT_SURFACE_CONTRACT.md`, including CLI/Web/MCP surface projection, operation risk classes, Change Plan/confirmation semantics, Plugin-safe scope, and explicit high-risk exclusions;
- 3.0 additive CLI/Bundle contract for Web operators, saved policy tests, and Job recovery frozen;
- capability parity ledger format frozen;
- authoritative vs preference vs operational vs derived state boundaries frozen;
- Agent RPC/job semantics frozen;
- browser-internal Web API vs supported Public Automation API boundary frozen;
- Service Account identity/credential/management-permission lifecycle frozen;
- Managed Host Approval / Quarantine states, pre-approved enrollment semantics, and access/job denial behavior frozen;
- staged Agent update rollout canary/wave/failure-pause/rollback bounds frozen;
- signed event Webhook event classes, signature/secret lifecycle, queue/retry/resource bounds, and health semantics frozen;
- Access Hygiene evidence-quality and read-only recommendation rules frozen;
- lightweight JIT request/approval stretch semantics frozen as a one-step Temporary Access producer with no GA dependency;
- 3.0 GA / 3.1+ / out-of-scope matrix frozen;
- cross-document contract gate defined for Product Master / Version Policy / Roadmap /
  Control Plane Architecture / Web Management / Management Surface Contract / AI Access MCP;
- performance measurement profile and SLO methodology frozen;
- audit taxonomy/envelope, attribution/delegation, redaction, retention/storage bounds,
  mutation atomicity, per-plane durable-spool/Audit-Ingestor boundary, enqueue high-water
  behavior, ingest/checkpoint recovery, NDJSON export, and recovery frozen.

The DRL3-0 performance profile must define reproducible scale dimensions for at least:

```text
Managed Hosts          1 / 10 / 50 / 100
Remote Service count   representative per-Host distributions
Object/Group count     representative small/normal/high inventory
Policy Rule count      representative small/normal/high rule sets
Audit history depth    bounded current + large-history query cases
Audit ingest rate      idle / normal / burst across Remote/Internet/AI
Audit spool backlog    empty / recovering / near-high-water
Web sessions           single + concurrent operator cases
Agent RPC jobs         single-target + fan-out + saturated queue
Lifecycle events       normal heartbeat + 100-Host reconnect/flap storm
Mixed workload         dashboard/search + audit ingest/query + policy test + mutation + jobs
```

Exact latency/resource SLO numbers are frozen from measured baseline/reference hardware,
not guessed before measurement. The test dimensions themselves are part of the scope
freeze so later implementation cannot redefine the workload to make qualification pass.

Acceptance:

```text
another engineer/agent can implement DRL3-1 without inventing
state ownership, async behavior, security boundaries, or product scope
```

No frontend-first implementation before this gate.

## 11. DRL3-1 — Management Scalability Foundation

**Goal:** make the existing Core safe for concurrent CLI/Web/MCP and 100-host operations.

Implement logical boundaries for:

- typed Core Application/Management Service;
- Web API adapter, public Automation API adapter, and Management MCP adapter as separate projections over that same Core service; the Plugin/relay must not depend on the Web API and automation clients must not depend on the browser API;
- Managed Host admission state plus fail-closed admission evaluator shared by Remote/Internet/AI access and mutating Agent Jobs;
- local Service Account principals, hashed display-once token verifiers, expiry/rotation/revocation, and permission binding for Automation API;
- bounded webhook delivery queue/event sink with signed versioned events, dedupe IDs, retry/backoff, and delivery-health state;
- bounded Access Hygiene read model that can prove STALE_OR_UNUSED / ORPHANED / ACTION_REQUIRED or report UNKNOWN_EVIDENCE;
- command/query separation;
- bounded read-only connections and server-side filtering/pagination;
- query-plan/index review for common Host/Service/status/version/policy/audit/job views;
- rebuildable derived read models for dashboard/inventory summaries;
- cursor/keyset-style bounded history/job pagination where offset growth would be wasteful;
- bounded Management Job Engine for operations that wait on Agents or multiple resources;
- Agent RPC worker pool with concurrency/backpressure/timeouts;
- operational-state aggregation/coalescing, including bounded per-plane live-access
  observation inputs with explicit EXACT / AGGREGATE / UNKNOWN fidelity;
- Temporary Access schema/evaluator primitive (`expires_at`) and fail-closed time-trust behavior;
- Managed Host approval state and pre-approval binding without changing immutable Host identity;
- local Service Account principal/credential state mapped only to management permissions;
- bounded signed-Webhook outbox/delivery state that is not mutation or enforcement authority;
- Access Hygiene derived-query primitives with evidence-quality markers;
- optional lightweight JIT request state that can only produce the existing Temporary Access semantics;
- Core Audit Event Service and versioned audit schema migration;
- durable per-plane ACCESS_DECISION spools that preserve enforcement-service DB read-only
  privilege;
- bounded Audit Ingestor with event-id dedupe, committed per-source checkpoints,
  ingestion-lag/high-water health, and short batch transactions;
- indexed bounded audit/history queries;
- migration/convergence contract for legacy `audit_events`, `ai_activity`, and connection
  JSONL surfaces;
- capability parity inventory generated from the supported public model.

Existing AI-job primitives may share low-level utilities only when semantics fit. Management
jobs must not inherit AI Identity/authorization semantics merely to reuse an existing
table or queue.

Hard rules:

- no SQLite write transaction waits on browser input or Agent RPC;
- heartbeat/status refresh does not create configuration revisions unless effective
  configuration/membership changes;
- derived read models are never recovery authority;
- browser request count must not scale one-for-one with Host count;
- worker saturation queues/rejects safely rather than spawning unbounded work;
- enforcement services never receive SQLite write permission for audit;
- access-event ingestion never performs one SQLite transaction per connection;
- spool saturation converts new ALLOW decisions to DENY before access is granted.

Acceptance includes mixed read/write/RPC load with no policy drift, false success,
unbounded resource growth, or starvation of relay enforcement.

## 12. DRL3-2 — Web Platform and Read-Only Operations

**Goal:** deliver useful Web operations before granting mutation authority.

Required:

- separately installable/stoppable `drlink-web`;
- static production frontend assets;
- local-only listen by default;
- privileged local bootstrap for the first Web Admin;
- authenticated browser sessions;
- Web-admin local security baseline:
  - local recovery Admin remains available;
  - local password-backed operators support offline-capable TOTP MFA, disabled by default and enabled per user by a Web Admin;
  - bounded session lifetime/idle timeout and explicit session revocation;
  - no SSO/IdP dependency in 3.0;
- Admin / Operator / Read Only roles;
- Overview Dashboard and Attention Center;
- Managed Host / Remote Service inventory;
- Object/Group and policy read views;
- Agent/platform/version inventory and version-drift visibility;
- read-only Managed Host admission state and Pending Approval / Quarantined attention;
- read-only Service Account inventory and token health metadata without secret reveal;
- webhook delivery health/backlog visibility without endpoint-secret exposure;
- read-only Access Hygiene findings with evidence-quality labels;
- global search, server-side filters, and Saved Views;
- audit/revision read views;
- Doctor/health read views;
- Web-service health independent from Core health.

No state-changing Web operation is required to pass this phase.

Acceptance must prove Web can be stopped/uninstalled while Core, CLI, enforcement,
Agent connectivity, backup/restore, and recovery remain functional. Authentication
acceptance must also prove MFA defaults OFF, Admin per-user enable/disable, user-owned TOTP enrollment/recovery-code issuance, bounded browser-session lifetime/idle timeout, explicit session revocation, and local recovery with no SSO/IdP dependency.

## 13. DRL3-3 — Guided Configuration and Full Management Parity

**Goal:** make normal administration possible without memorized CLI grammar.

Required workflows:

- guided Agent Zero-Touch/Manual enrollment and installation guidance;
- Admin-only Managed Host Approve / Quarantine / Restore-to-Approved lifecycle plus explicit pre-approved enrollment;
- browser-guided Server management settings after the Core/Web package is installed;
- Managed Host metadata/lifecycle where supported;
- Network / Service / Permission Object and Group lifecycle;
- Remote Service lifecycle through authenticated Agent RPC;
- Remote / Internet / AI Access policy management;
- ConfigurationBundle test/diff/apply/export;
- Temporary Access set/change/clear expiry parity across Core/CLI/Bundle/Web for supported
  Remote / Internet / AI grants;
- system/update/certificate/backup/restore operations where browser-appropriate;
- local Service Account lifecycle and display-once Automation API token issue/rotate/revoke;
- signed generic webhook endpoint/event-family lifecycle and test delivery;
- public `/api/automation/v1/` adapter over the same Core Management Service, separate from bundled Web `/api/v1/`.

For the DRL3-3 update slice, browser-appropriate scope is product + Relay Engine
availability checks and local Relay Engine apply through the canonical rollback-capable
updater. Core product self-update apply waits for DRL3-7 because that phase explicitly
qualifies optional Web package update/uninstall/reinstall compatibility; DRL3-3 must not
create a Core/Web build-skew path merely to claim surface parity.

For Managed Host lifecycle parity, DRL3-3 supports two distinct Admin-only operations:
management-trust revoke keeps the Host inventory/Remote Services/port reservations and
requires re-enrollment, while reference-safe retirement delegates to canonical
`unset_managed_host`, refuses live references, and cleans owned service/port state only
after typed impact confirmation. These meanings must never be collapsed into one generic
delete action.

Add a non-authoritative **Draft Workspace**:
- compose multiple related changes;
- show generated Change Plan;
- run validation/tests before Apply;
- cancel with zero authoritative mutation;
- Apply through the same atomic/revision-bound Core path as CLI/Bundle.

A Web page must never become the only way to perform a supported management operation.

## 14. DRL3-4 — Policy Safety, Preview, and Explainability

**Goal:** prevent policy mistakes before they become outages.

Mandatory:

### Policy Simulator / Decision Trace
Use the Core evaluator. Never reimplement policy semantics in frontend code.

### Saved Policy Regression Tests
Operators can persist expected allow/deny assertions for critical flows.

Security-relevant policy Apply runs required tests against the proposed Change Plan.
A failed required assertion blocks Apply until the change or test expectation is
explicitly corrected.

### Blast Radius Preview
Before Apply show:
- access broadened / narrowed;
- affected rules;
- affected Managed Hosts / Remote Services / destinations;
- expected effective-decision changes;
- newly reachable or newly blocked flows represented by available inventory.

### Effective Access Graph
Show the explainable path between identity/source, Groups/Objects, policy rules, Remote
Service/destination, and effective access.

The graph is a policy/inventory visualization, not a general network topology mapper.

### Draft Graph Overlay
When a Draft Workspace is open, visually distinguish current effective access from the
proposed state.

### Time-bounded Temporary Access — P1 Must Ship
Remote / Internet / AI Access rules or assignments may carry an explicit `expires_at`
(or equivalent TTL input) where that policy family supports it.

3.0 minimum scope:
- set, change, and clear one expiration;
- expiry is server-authoritative and audited; browser timers are display only;
- expired grants deny new authorization automatically without an operator cleanup step;
- remaining validity is visible in CLI/Web and in preview/diff;
- expiration uses the same Core evaluator as normal policy, not a second scheduler-only
  policy path;
- ConfigurationBundle/backup/restore preserve expiry semantics;
- a large/ambiguous server-clock anomaly fails closed for temporary grants.

Explicitly excluded from the core Temporary Access primitive:
- multi-stage requester/approver governance or a separate entitlement engine; the P2
  lightweight local one-step request/approval stretch, if implemented, only materializes
  this same Temporary Access grant;
- recurring/scheduled windows;
- automatic renewal/extension;
- policy cleanup as an enforcement dependency;
- implicit termination of already-established connections.

Acceptance requires CLI/Web policy-test parity and no discrepancy between graph/preview
and the Core evaluator, including before/at/after-expiry cases.

## 15. DRL3-5 — Diagnosis, Health, and Attention

**Goal:** make "why does this not work?" a first-class product workflow.

Connection Diagnosis correlates, where applicable:

```text
identity / source
policy match and mode
Agent presence
Remote Service configuration
runtime verification
public endpoint
target reachability / configured health check
DNS / Internet Access destination validation
recent decision/audit evidence
```
The result identifies the failed layer and gives a safe next action.

Health design:

- reuse existing Agent heartbeat/runtime/health-check signals;
- no browser-originated N-per-host health polling;
- configured target probes are bounded and rate/concurrency limited;
- status aggregation is independent from configuration revisions;
- flapping is coalesced into meaningful attention rather than alert storms.

### Live Access Visibility — P1 Must Ship

3.0 provides a bounded current-use view rather than forcing operators to infer active use
from historical audit alone.

Minimum scope:
- current count/state by access plane and relevant Managed Host / Remote Service /
  destination when available;
- bounded recent/active metadata already observable by Data Relay Link;
- explicit quality label: EXACT_PER_CONNECTION, AGGREGATE, or UNKNOWN;
- no packet/payload capture and no session recording;
- no browser-originated per-Host polling fan-out.

### Emergency New-Access Cutoff — P1 Must Ship

Emergency Cutoff is an explicit reversible security override, separate from normal policy
editing. It must immediately deny **new authorization** at each supported cutoff scope
without destroying or silently rewriting the operator's normal policy configuration.

Required 3.0 behavior:
- at least one useful resource-level cutoff per access plane where the current object model
  can express it safely, plus a plane-level fallback;
- clear preview of what becomes blocked and whether active work is affected;
- same Core authorization/revision/audit path as other security mutations;
- visible active/recovered state and explicit operator restore action;
- no claim that already-established sessions were terminated unless termination was proven.

### Active connection termination — P2 / conditional, not a GA blocker

Active termination may ship for a plane only where Data Relay Link owns that lifecycle or
the pinned official upstream exposes a deterministic supported termination primitive.
Internet Access and AI work may qualify independently. Remote Access per-connection kill is
not required for 3.0 GA and must not require an FRP fork.

Attention Center must prioritize:

- disconnected/stale Managed Hosts;
- DEGRADED Remote Services;
- policy/runtime revision mismatch;
- repeated meaningful policy denies;
- version drift;
- certificate/backup/update readiness;
- failed/incomplete jobs;
- temporary access nearing expiry when operator action is useful;
- audit-spool/high-water degradation;
- Emergency New-Access Cutoff activation;
- Managed Host Pending Approval / Quarantined state;
- high-confidence Access Hygiene findings;
- staged Agent update halt/failure;
- webhook delivery degradation/backlog.

A signed generic HTTPS webhook sink **is required for 3.0 GA**. Native Email/Slack/Teams adapters remain later-additive and must reuse the same event envelope. Webhook delivery failure is never an enforcement dependency.

### Access Hygiene Recommendations — P1 Must Ship

Attention also derives read-only hygiene findings from bounded authoritative/audit evidence:
stale Hosts, long-unused standing access, orphaned references, expiring credentials/tokens,
and long-lived or never-used grants where retained evidence can actually prove that claim.
Each finding carries evidence quality/observation window and a safe next action. 3.0 never
auto-locks, auto-deletes, or rewrites access because of a hygiene recommendation.

### Signed Event Webhook — P1 Must Ship

3.0 provides one optional generic HTTPS event channel for selected Attention and security
lifecycle events. Each delivery uses a stable event ID and versioned secret-safe payload,
is signed with a per-endpoint protected secret, and has bounded queue/retry/backoff and
observable last-success/failure state. Webhook failure cannot block policy enforcement,
Core mutation commit, CLI recovery, or local Attention visibility. Direct Email/Slack/
Teams adapters and continuous SIEM/audit streaming remain later additions.

## 16. DRL3-6 — Bounded Fleet Operations

**Goal:** make 50–100-host operation efficient without becoming RMM.

Job Engine + Worker Pool powers multi-host actions with visible queued/running/success/
failed/cancelled state.
3.0 safe bulk operations may include:

- diagnostics/Doctor collection;
- synchronize/refresh;
- version inventory / update-availability check;
- support-bundle generation;
- bounded metadata/group/tag assignment with normal impact checks;
- inventory export;
- **Managed Update / Staged Rollout** for qualified Agent artifacts: explicit target set,
  optional canary/first wave, bounded wave size/concurrency, per-target progress, automatic
  pause on configured failure threshold, and canonical per-Agent rollback where supported.

Explicitly exclude broad destructive or unbounded fleet actions from 3.0:

```text
bulk delete
bulk revoke
bulk release
bulk policy disable/reset
unbounded all-at-once update/restart or arbitrary software deployment outside the staged-rollout contract
```

Any future high-impact bulk operation requires its own risk, rollback, and qualification
contract.

## 17. DRL3-7 — Audit, Lifecycle, and 100-Host Hardening

**Goal:** complete full management parity and prove bounded behavior at target scale.

Required:

- searchable Audit Explorer across CONTROL / ACCESS_DECISION / SECURITY_LIFECYCLE;
- cross-surface actor attribution for CLI/Web/Bundle/AI/Agent RPC/System;
- safe before/after summaries plus revision diff/rollback correlation;
- allow/deny reason and matched-rule correlation;
- bounded time-range/cursor pagination and stable event IDs;
- indexes for actual Web/CLI audit query patterns;
- split retention and storage-capacity guardrails;
- manual filtered NDJSON export with stable schema versioning;
- audit of retention/export configuration and export execution;
- no-silent-loss regression for CONTROL mutation audit plus ALLOW fail-closed behavior
  when ACCESS_DECISION durable enqueue is unavailable;
- durable-spool crash/restart, duplicate-ingest, checkpoint, lag, high-water, and recovery
  regressions;
- mixed-load verification that audit ingestion does not starve configuration writers,
  relay enforcement, or CLI recovery;
- schema-aware secret/credential/payload redaction regressions;
- read-model rebuild/recovery;
- backup/restore including new 3.0 Core-owned management metadata;
- Web update/uninstall/reinstall semantics;
- session/operator identity recovery;
- Web/API resource limits, including the supported Public Automation API and Service Account rate/permission boundaries;
- Managed Host approval/pre-approval/quarantine recovery and identity-continuity regressions;
- signed Webhook queue/retry/signature/secret-rotation/failure-isolation regressions;
- Access Hygiene evidence-quality/no-auto-mutation regressions;
- staged Agent update canary/wave/pause/rollback and partial-failure recovery regressions;
- Agent disconnect/reconnect storms;
- Job Engine saturation/backpressure tests;
- DB lock/contention tests;
- Web crash/restart isolation;
- dashboard/search/policy-test load at 100-host inventory size;
- Automation API rate/idempotency/concurrency/resource-limit and Service Account token lifecycle tests;
- webhook queue crash/restart/backoff/secret-rotation/dead-letter Attention tests;
- Managed Host admission state recovery/backup/restore and cross-plane fail-closed tests;
- Access Hygiene evidence-window/pruning/UNKNOWN_EVIDENCE correctness tests;
- staged Agent update canary/halt/resume/rollback and mixed-job saturation tests.

No new external datastore may be introduced merely to pass the 100-host target. If
measured evidence proves SQLite insufficient, that is a new architecture decision, not
an implementation shortcut.

## 17A. DRL3-7A — Modern SaaS Workspace and DR Control Visual Parity

**Goal:** replace the remaining NOC-style management-console presentation with a modern
task-oriented SaaS workspace while preserving Core/CLI authority and capability parity.

Canonical UX authority: `docs/WEB_SAAS_UX_SYSTEM.md`.

Required:

- authenticated Web shell uses the same visual foundation as Data Relay Control:
  Inter/system typography, semantic light/dark surface tokens, 8 px controls/cards,
  260 px expanded / 57 px collapsed navigation, 58 px sticky header, neutral borders,
  bounded 1440 px content canvas, DataRelay green brand accent, and matching primary/
  secondary/status color semantics;
- default authenticated workspace is light, with Control-compatible dark theme available;
- sidebar is collapsible and task-oriented rather than a flat NOC menu;
- root navigation remains bounded to Overview plus Infrastructure, Access Control,
  Operations, Observability, and Administration;
- utility capabilities such as Search, Saved Views, troubleshooting, enrollment, and
  Draft Workspace move toward contextual actions/workspaces instead of multiplying root
  navigation;
- sticky top header carries page identity, health/attention context, global search entry,
  refresh/theme/account actions, matching the Control shell hierarchy;
- Overview evolves from KPI-only cards into an actionable Command Center: posture,
  attention, recent activity/change, and access relationships before raw tables;
- list pages use SaaS list/detail patterns with compact tables, bounded filters, detail
  drawers/pages, tabs, contextual actions, empty states, and skeleton/loading treatment;
- Access workspace converges Remote / Internet / AI Access around an access relationship
  view, policy test/explain, draft/change preview, and Temporary Access context without
  merging their security semantics;
- authenticated page style and component density remain visually consistent with DR Control
  even though DRLink remains a separate product and does not import Control runtime code;
- responsive behavior preserves desktop-first operations and keyboard accessibility;
- package and browser regressions prove visual assets/navigation remain present after Web
  install/reinstall and that visual modernization does not create a Core dependency.

Acceptance evidence includes:

```text
DR_CONTROL_VISUAL_TOKEN_PARITY=PASS
SAAS_SHELL_PARITY=PASS
BOUNDED_ROOT_NAVIGATION=PASS
COLLAPSIBLE_SIDEBAR=PASS
LIGHT_DARK_THEME=PASS
COMMAND_CENTER_OVERVIEW=PASS
CONTEXTUAL_WORKSPACE_NAV=PASS
WEB_PACKAGE_VISUAL_PARITY=PASS
BROWSER_REAL_USER_UX=PASS
```

This slice is release-bearing UX work. Any product/UI change after DRL3-7A invalidates
DRL3-8 exact-candidate browser evidence and must be re-qualified on the new HEAD.

## 17B. DRL3-7B — First-Time Operator Usability and Workflow-First UI

**Owner review (2026-10-09):** The PF-5B/P0 development Web is substantially
better visually, but menu names and where to begin remain confusing.
**The current UI is an intermediate baseline, not the final target UI.**

**Canonical new UX roadmap:** `docs/WEB_USER_JOURNEY_UX_ROADMAP.md`.
**Survey basis:** 19 vendor official documentation sources (on-prem/open-source
and commercial ZTNA, PAM, private-resource access); no authenticated-tenant
exhaustive visual audit or completed new-user study is claimed.

DRL3-7B is an explicit follow-up to the DRL3-7A shell and the P0 Access
Explanation / Guided Policy / Agent Enrollment source implementations.
Its priority is **how a novice completes a real workflow**, not more widgets:

- **UXB-01 / P0:** five understandable root destinations (Home, Connections,
  Access, Activity & Health, Administration); contextual plain-language task
  labels, old-to-new global search aliases, breadcrumbs and actor-aware help.
  Keep canonical Core resource identities, CLI/API names and the Foundation
  four-group shared Administration metadata intact.
- **UXB-02 / P0:** first-login and already-configured Home journeys from
  server readiness through Agent admission, a narrowly published Remote
  Service, policy preview/test/apply and a verified access check. Resume
  context; no fake success, silent pre-approval or persisted secrets.
- **UXB-03 / P0:** one continuous “publish and allow connection” task,
  keeping Remote / Internet / AI access semantics independent, with typed
  confirmation, Core-authoritative preview and required policy regression.
- **UXB-04 / P1:** resource detail → why denied → Core decision trace →
  relevant rules/audit and evidence freshness without a speculative graph.
- **UXB-05 / P1:** routine versus advanced/dangerous Administration,
  consistent empty/loading/UNKNOWN/permission states and in-place glossary.
- **UXB-06 / release gate:** real Admin/Operator/Read Only browser flows,
  320px/375px/desktop usability, first-time-user observations, source/role
  security regression and offline Web compatibility on one frozen candidate.

**Status (2026-10-09):** UXB-00 research/roadmap documented; UXB-01..05
**CODE IMPLEMENTED ON ISOLATED DEV WEB SOURCE**, with offline SSR/static/package
qualification only. UXB-06 **ACTUAL USER BROWSER / HUMAN STUDY / RELEASE PENDING**. Earlier P0 technical
components, unit/SSR/Web bundle tests and HTTP preview are not proof of a
novice-friendly UI or browser PASS. Work is scoped to the optional Web
projection; no second Core policy authority, network exposure change, or
unapproved runtime dependency. Any material usability implementation after
DRL3-7A/7B must re-qualify the exact-head DRL3-8 user/browser gates.

**Acceptance target:** A new on-prem Admin can locate Add Agent, configure
only one useful service, grant narrow access, test it, and troubleshoot a
denial *without learning internal menu terminology*; two-user same-HEAD Full
User E2E and owner acceptance remain mandatory. See the new UX roadmap for
mapped routes, human test scenarios, proposed metrics and safety boundaries.

## 18. DRL3-8 — 3.0 Qualification and Stable Release

Required exact-candidate evidence includes:

```text
CORE_WITHOUT_WEB=PASS
CLI_FULL_CAPABILITY=PASS
WEB_CAPABILITY_PARITY=PASS
MANAGEMENT_SURFACE_CONTRACT=PASS
MCP_CORE_SEMANTIC_PARITY=PASS
PLUGIN_WEB_API_DEPENDENCY=NO
TARGET_OS_PERMISSION_IMPLIES_MANAGEMENT_PERMISSION=NO
CLI_AUDIT_QUERY_EXPORT=PASS
WEB_AUTH_RBAC=PASS
WEB_LOCAL_MFA=PASS
WEB_LOCAL_RECOVERY=PASS
WEB_SESSION_TIMEOUT_REVOCATION=PASS
WEB_SSO_IDP_DEPENDENCY=NO
WEB_POLICY_EXPLAIN_PARITY=PASS
DRAFT_WORKSPACE_ATOMICITY=PASS
POLICY_REGRESSION_GATE=PASS
BLAST_RADIUS_ACCURACY=PASS
EFFECTIVE_ACCESS_GRAPH_ACCURACY=PASS
CONNECTION_DIAGNOSIS=PASS
TEMPORARY_ACCESS_EXPIRY=PASS
TEMPORARY_ACCESS_CLOCK_FAIL_CLOSED=PASS
LIVE_ACCESS_VISIBILITY=PASS
LIVE_ACCESS_VISIBILITY_QUALITY_LABEL=PASS
EMERGENCY_NEW_ACCESS_CUTOFF=PASS
EMERGENCY_CUTOFF_POLICY_PRESERVATION=PASS
ACTIVE_CONNECTION_TERMINATION_GA_REQUIRED=NO
FRP_NO_FALSE_PER_CONNECTION_TERMINATION_CLAIM=PASS
ATTENTION_DEDUPLICATION=PASS
SAVED_VIEWS=PASS
VERSION_DRIFT_ATTENTION=PASS
MANAGED_HOST_ADMISSION=PASS
MANAGED_HOST_QUARANTINE_FAIL_CLOSED=PASS
STAGED_AGENT_UPDATE_CANARY=PASS
STAGED_AGENT_UPDATE_HALT_ROLLBACK=PASS
AUTOMATION_API_CORE_PARITY=PASS
SERVICE_ACCOUNT_TOKEN_LIFECYCLE=PASS
SIGNED_WEBHOOK_DELIVERY=PASS
WEBHOOK_FAILURE_ISOLATION=PASS
ACCESS_HYGIENE_READ_ONLY=PASS
ACCESS_HYGIENE_EVIDENCE_QUALITY=PASS
AGENT_RPC_OWNERSHIP=PASS
BOUNDED_JOB_ENGINE=PASS
HEALTH_COLLECTION_BOUNDS=PASS
NO_BROWSER_N_PER_HOST_POLLING=PASS
NO_SQLITE_TXN_WAITING_ON_AGENT_RPC=PASS
```

```text
100_HOST_CONTROL_PLANE_SCALE=PASS
100_HOST_MIXED_OPERATION_LOAD=PASS
WEB_FAILURE_ISOLATION=PASS
AUDIT_REVISION_RECOVERY=PASS
AUDIT_CONTROL_TXN_ATOMICITY=PASS
AUDIT_ACCESS_DURABLE_ENQUEUE=PASS
AUDIT_INGEST_DEDUP_CHECKPOINT=PASS
AUDIT_SPOOL_BACKPRESSURE=PASS
AUDIT_PENDING_SPOOL_BACKUP_RESTORE=PASS
EGRESS_SQLITE_WRITE_ACCESS=NO
BACKUP_RESTORE_3_0=PASS
SECURITY_REVIEW=PASS
BROWSER_REAL_USER_E2E=PASS
MULTI_PLATFORM_AGENT_E2E=PASS
FULL_REAL_E2E_PASS_1=PASS
FULL_REAL_E2E_PASS_2=PASS
PASS1_HEAD==PASS2_HEAD
```

100-host qualification may use simulated/virtual Agents for saturation and state-scale
coverage, but real Agent/platform and real traffic evidence remain mandatory for
functional claims. Synthetic scale evidence never substitutes for real-user correctness.

## 19. 3.0 GA capability matrix

### Must ship

```text
Management Scalability Layer
Full CLI-management parity in Web
Admin / Operator / Read Only
Per-user offline-capable local Web MFA (default OFF)
Dashboard + Attention Center
Inventory + search/filter/Saved Views
Guided enrollment
Draft Workspace / Change Plan preview
Policy Builder
Policy Simulator / Decision Trace
Time-bounded Temporary Access
Saved Policy Regression Tests
Blast Radius Preview
Effective Access Graph
Connection Diagnosis
Live Access Visibility + Emergency New-Access Cutoff
Managed Host Approval / Quarantine
Managed Update / Staged Rollout
Public Automation API + Service Accounts
Signed Event Webhook
Access Hygiene Recommendations
Audit / Revision Explorer
manual filtered NDJSON audit export
bounded safe fleet jobs
Managed Host Approval / Quarantine
bounded staged Managed Agent updates
public Automation API + scoped Service Accounts
signed generic webhook notifications
Access Hygiene / stale-access review (recommendation-only)
100-host qualification
P2 stretch: lightweight one-step JIT Access Request / Approval
```
### Design now, implement after 3.0 unless required by evidence

```text
native Email/Slack/Teams notification adapters beyond the generic signed webhook
GitOps/locked-editor workflow
continuous external audit/SIEM streaming
scheduled recurring operations
additional specialized operator roles
```

These later capabilities must reuse 3.0 event, identity, Change Plan, and job boundaries.

## 20. Explicitly out of 3.0 scope

Do not add merely because competitors provide them:

```text
SSO/IdP integration (OIDC/SAML/LDAP/SCIM)
multi-stage/full JIT access-governance system beyond the optional one-step Temporary-Access-backed stretch flow
device-posture/MDM platform
session recording
browser SSH/RDP terminal
credential vault/injection
application discovery/scanning
SIEM/reporting platform
SASE/SWG/CASB/DLP
TLS interception
multi-server SaaS control plane
HA database cluster
PostgreSQL/Redis/Kubernetes requirement
multi-region orchestration
hundreds/thousands-host fleet platform
```

## 21. Competitive-pattern decisions
The 3.0 scope was re-reviewed against current official product patterns through 2026-10-08, expanding the earlier 2026-10-03 baseline.

Adopt the **operator pattern**, not the competitor architecture:

| Pattern observed | 3.0 decision |
|---|---|
| Tailscale visual policy editor, tests, preview | Adopt policy tests, preview, visual builder; defer GitOps |
| Cloudflare policy tester and decision logs | Adopt blast radius and decision drill-down |
| Twingate Access Graph and path-based troubleshooting | Adopt Effective Access Graph + Connection Diagnosis |
| Teleport inventory/RBAC/access graph | Adopt version drift + three-role Web RBAC; exclude session recording/browser terminal |
| NetBird Control Center/draft graph/audit | Adopt graph/draft overlay/searchable audit; no overlay-network expansion |
| Zscaler health/diagnostics patterns | Adopt bounded health aggregation/diagnosis; exclude app discovery/HA platform |
| Boundary worker health/last-seen separation | Adopt explicit component health; no controller/worker cluster architecture |
| Tailscale config audit + separate network-flow logs | Adopt control-plane vs access-event separation, policy diffs, and bounded export |
| Cloudflare admin/access/gateway logs | Adopt actor/interface/request IDs, safe old/new values, and decision-specific views; no analytics platform |
| Twingate versioned actor/action/target JSON | Adopt a versioned envelope and manual NDJSON export; defer continuous delivery |
| Teleport event codes/session correlation | Adopt stable event types and correlation IDs; exclude session recording |
| StrongDM activities/resource-query separation | Adopt management vs access logical streams and CLI filtering; exclude replay capture |
| Zscaler admin old/new values + request IDs | Adopt safe before/after summaries and request correlation |
| Boundary event sinks/redaction | Adopt schema-aware sensitive-field handling and bounded local sinks |
| NetBird audit + traffic event separation | Adopt searchable management/access streams on existing SQLite authority |
| ngrok audit/log export + payload-capable Traffic Inspector | Adopt exportability only; reject payload/body inspection or replay as a DRLink audit requirement |
| Tailscale IdP/MFA and admin-session controls | Adopt the local MFA/session-security baseline only; SSO/IdP is excluded from 3.0 |
| Cloudflare MFA + session duration/revocation | Adopt local MFA/session lifetime/revocation; do not turn DRLink Remote Access into an identity proxy |
| Twingate Admin MFA + Ephemeral Access | Adopt local MFA and operator-set access expiry; permit only a bounded one-step local JIT stretch flow over Temporary Access |
| Teleport SSO/MFA + expiring/JIT access | Adopt MFA/TTL plus only the bounded one-step local JIT stretch flow; SSO and full identity-governance workflow remain excluded |
| Boundary active-session view/cancel | Adopt live-access visibility and new-access cutoff; active termination only where DRLink/upstream owns the lifecycle |
| Zscaler authentication/idle timeout policies | Adopt bounded local session/temporary-access lifetime semantics; avoid SWG/ZTNA platform expansion |
| Tailscale signed Webhooks / NetBird notifications | Adopt one generic signed HTTPS event Webhook; keep direct Email/Slack/vendor adapters later |
| Tailscale Device Approval | Adopt optional Managed Host Approval / Quarantine with pre-approved enrollment |
| Teleport Managed Updates | Adopt bounded manual canary/wave Agent rollout with failure pause and supported rollback; no scheduler/RMM expansion |
| Tailscale OAuth clients / common management APIs | Adopt a separate supported Public Automation API with scoped local Service Accounts |
| Teleport access review / usage evidence | Adopt read-only Access Hygiene recommendations with explicit evidence quality; no automatic access mutation |
| OpenZiti external identity + fine-grained management permissions | Reinforces RBAC value; SSO/IdP and distributed-controller/overlay complexity are not adopted for 3.0 |
| NordLayer SSO/MFA + posture controls | Adopt the MFA pattern only; SSO and device-posture platform remain outside DRLink 3.0 |
| Tailscale Device Approval + pre-approved keys | Adopt explicit Managed Host Pending Approval / Approved / Quarantined admission state and explicit pre-approved enrollment; keep revoke/retire separate |
| Tailscale OAuth clients / NetBird service users + public API | Adopt a separate versioned Automation API adapter with scoped local Service Accounts; do not promote the private Web API |
| Tailscale signed webhooks + NetBird/Twingate notifications | Promote one generic signed HTTPS webhook sink to 3.0 GA; keep native Email/Slack/Teams adapters later |
| Tailscale update visibility + Teleport Managed Updates/canaries | Adopt manual bounded staged Agent rollout with canary + halt-on-failure over the existing rollback-capable updater; no generic RMM or recurring scheduler |
| Twingate usage-based auto-lock/access review | Adopt read-only Access Hygiene recommendations with evidence-quality labels; no automatic revoke/delete |
| Teleport/Twingate JIT access requests | Keep only a one-step Temporary-Access-backed P2 stretch flow; full workflow/governance remains outside 3.0 |

Competitor functionality that does not strengthen Data Relay Link's core operator mission
stays out of the GA scope.

## 22. Roadmap success condition

The roadmap is successful when 3.0 adds full graphical operation and 100-host management
without replacing the proven 2.x Core.

A future feature should be additive to:

```text
SQLite authority
identity/Object model
Remote Service ownership
BLACKLIST / WHITELIST semantics
AI Identity / permission model
Change Plan / revision / audit
backup/migration model
complete CLI administration
```

If a proposed feature requires replacing those foundations, stop and make an explicit
product-generation/architecture decision before implementation.
