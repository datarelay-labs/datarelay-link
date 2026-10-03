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
- A new auditable access decision must not proceed if its audit record cannot be durably
  enqueued. Existing established connections are not torn down solely because the audit
  store later degrades; the condition becomes CRITICAL health/attention.
- Secrets, credentials, bearer tokens, private keys, application payloads, TLS contents,
  and sensitive URL query strings are never normal audit fields.

- Before/after data uses schema-aware allowlisting/redaction, not regex-only scrubbing.
- Audit is append-only through normal product APIs. 3.0 exposes no arbitrary edit/delete;
  expiry occurs only through retention policy.
- Active audit stays in SQLite/Core with bounded time-range queries, cursor pagination,
  indexes, and hard resource limits.
- CLI and Web both provide bounded read/filter/detail access to the same event model.
  Exact additive CLI grammar is frozen in DRL3-0; neither surface may invent its own semantics.
- 3.0 provides manual filtered NDJSON export using the same versioned schema from CLI and
  Web. Continuous SIEM/S3/syslog/webhook streaming remains later-additive.
- Append-only semantics are not described as tamper-proof against a privileged host admin.

Default active-local retention targets:

~~~text
CONTROL + SECURITY_LIFECYCLE   180 days
ACCESS_DECISION                 30 days
~~~

DRL3-0 freezes supported configuration bounds, storage-capacity guardrails, migration,
and exact failure behavior. The product may not silently discard not-yet-expired security
audit to recover space.

Backup/restore preserves retained event IDs, ordering, schema versions, and revision links.
Restore completion creates a new lifecycle event after restored state is authoritative.

No dedicated Auditor role is required for 3.0. Admin / Operator / Read Only reuse the
redacted audit query/export authorization model; a specialized role can be added later.

## 10. DRL3-0 — Scope and architecture freeze

**Goal:** remove design ambiguity before feature implementation.

Required:
- generation/scale contract frozen;
- Management Scalability Layer boundaries frozen;
- Web authentication/RBAC model frozen;
- shared management-operation contract frozen;
- 3.0 additive CLI/Bundle contract for Web operators, saved policy tests, and Job recovery frozen;
- capability parity ledger format frozen;
- authoritative vs preference vs operational vs derived state boundaries frozen;
- Agent RPC/job semantics frozen;
- Web API internal/public boundary frozen;
- 3.0 GA / 3.1+ / out-of-scope matrix frozen;
- cross-document contract gate defined for Product Master / Version Policy / Roadmap /
  Control Plane Architecture / Web Management;
- performance measurement profile and SLO methodology frozen;
- audit taxonomy/envelope, attribution/delegation, redaction, retention/storage bounds,
  mutation atomicity, access-path audit failure behavior, NDJSON export, and recovery frozen.

The DRL3-0 performance profile must define reproducible scale dimensions for at least:

```text
Managed Hosts          1 / 10 / 50 / 100
Remote Service count   representative per-Host distributions
Object/Group count     representative small/normal/high inventory
Policy Rule count      representative small/normal/high rule sets
Audit history depth    bounded current + large-history query cases
Web sessions           single + concurrent operator cases
Agent RPC jobs         single-target + fan-out + saturated queue
Lifecycle events       normal heartbeat + 100-Host reconnect/flap storm
Mixed workload         dashboard/search + policy test + mutation + jobs
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
- command/query separation;
- bounded read-only connections and server-side filtering/pagination;
- query-plan/index review for common Host/Service/status/version/policy/audit/job views;
- rebuildable derived read models for dashboard/inventory summaries;
- cursor/keyset-style bounded history/job pagination where offset growth would be wasteful;
- bounded Management Job Engine for operations that wait on Agents or multiple resources;
- Agent RPC worker pool with concurrency/backpressure/timeouts;
- operational-state aggregation/coalescing;
- indexed bounded audit/history queries;
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
- worker saturation queues/rejects safely rather than spawning unbounded work.

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
- Admin / Operator / Read Only roles;
- Overview Dashboard and Attention Center;
- Managed Host / Remote Service inventory;
- Object/Group and policy read views;
- Agent/platform/version inventory and version-drift visibility;
- global search, server-side filters, and Saved Views;
- audit/revision read views;
- Doctor/health read views;
- Web-service health independent from Core health.

No state-changing Web operation is required to pass this phase.

Acceptance must prove Web can be stopped/uninstalled while Core, CLI, enforcement,
Agent connectivity, backup/restore, and recovery remain functional.

## 13. DRL3-3 — Guided Configuration and Full Management Parity

**Goal:** make normal administration possible without memorized CLI grammar.

Required workflows:

- guided Agent Zero-Touch/Manual enrollment and installation guidance;
- browser-guided Server management settings after the Core/Web package is installed;
- Managed Host metadata/lifecycle where supported;
- Network / Service / Permission Object and Group lifecycle;
- Remote Service lifecycle through authenticated Agent RPC;
- Remote / Internet / AI Access policy management;
- ConfigurationBundle test/diff/apply/export;
- system/update/certificate/backup/restore operations where browser-appropriate.

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

Acceptance requires CLI/Web policy-test parity and no discrepancy between graph/preview
and the Core evaluator.

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

Attention Center must prioritize:

- disconnected/stale Managed Hosts;
- DEGRADED Remote Services;
- policy/runtime revision mismatch;
- repeated meaningful policy denies;
- version drift;
- certificate/backup/update readiness;
- failed/incomplete jobs.

External Email/Slack/Webhook notification channels are **not required for 3.0 GA**.
The internal event model must allow them to be added later without redesign.

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
- inventory export.

Explicitly exclude broad destructive fleet actions from 3.0:

```text
bulk delete
bulk revoke
bulk release
bulk policy disable/reset
unbounded bulk update/restart
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
- no-silent-loss/fail-closed regression for mutation and new-access audit persistence;
- schema-aware secret/credential/payload redaction regressions;
- read-model rebuild/recovery;
- backup/restore including new 3.0 Core-owned management metadata;
- Web update/uninstall/reinstall semantics;
- session/operator identity recovery;
- Web/API resource limits;
- Agent disconnect/reconnect storms;
- Job Engine saturation/backpressure tests;
- DB lock/contention tests;
- Web crash/restart isolation;
- dashboard/search/policy-test load at 100-host inventory size.

No new external datastore may be introduced merely to pass the 100-host target. If
measured evidence proves SQLite insufficient, that is a new architecture decision, not
an implementation shortcut.

## 18. DRL3-8 — 3.0 Qualification and Stable Release

Required exact-candidate evidence includes:

```text
CORE_WITHOUT_WEB=PASS
CLI_FULL_CAPABILITY=PASS
WEB_CAPABILITY_PARITY=PASS
CLI_AUDIT_QUERY_EXPORT=PASS
WEB_AUTH_RBAC=PASS
WEB_POLICY_EXPLAIN_PARITY=PASS
DRAFT_WORKSPACE_ATOMICITY=PASS
POLICY_REGRESSION_GATE=PASS
BLAST_RADIUS_ACCURACY=PASS
EFFECTIVE_ACCESS_GRAPH_ACCURACY=PASS
CONNECTION_DIAGNOSIS=PASS
ATTENTION_DEDUPLICATION=PASS
SAVED_VIEWS=PASS
VERSION_DRIFT_ATTENTION=PASS
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
Dashboard + Attention Center
Inventory + search/filter/Saved Views
Guided enrollment
Draft Workspace / Change Plan preview
Policy Builder
Policy Simulator / Decision Trace
Saved Policy Regression Tests
Blast Radius Preview
Effective Access Graph
Connection Diagnosis
Audit / Revision Explorer
manual filtered NDJSON audit export
bounded safe fleet jobs
100-host qualification
```
### Design now, implement after 3.0 unless required by evidence

```text
external Email/Slack/Webhook notifications
temporary rule TTL / temporary access
external IdP/SSO for Web administrators
GitOps/locked-editor workflow
continuous external audit/SIEM streaming
scheduled recurring operations
additional specialized operator roles
```

These later capabilities must reuse 3.0 event, identity, Change Plan, and job boundaries.

## 20. Explicitly out of 3.0 scope

Do not add merely because competitors provide them:

```text
full JIT/access-request approval system
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
The 3.0 scope was re-reviewed against current official product patterns on 2026-10-02.

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
