# Data Relay Link — Product Master

> **Document role:** Canonical product charter and product-level specification
> **Status:** Normative living document
> **Target release:** v2.4.0 development; stable qualification pending
> **Primary CLI:** `drlink`
> **CLI/AI SSOT:** `docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`
> **Version governance:** `docs/VERSION_POLICY.md`

Current project version: **3.0.0**

Development builds must display an identity equivalent to `3.0.0-dev+g<shortsha>`
(with exact Source HEAD shown separately), not plain `3.0.0`.
Current pinned Relay Engine (FRP): **v0.71.0**

## 1. Product definition

Data Relay Link is a lightweight secure connectivity gateway for isolated and restricted networks.

> **Secure Connectivity for Isolated Networks**

Core principle:

> **Do not connect entire networks. Relay only the connections that are actually needed.**

Product planes:

```text
Remote Access     outside → approved internal Remote Service
Internet Access   managed/protected source → approved outside destination
AI Access         authenticated AI Identity → approved target permissions
```

Management-surface principle:

```text
Data Relay Link Core
├── complete local CLI                         always available
├── Optional Full Web Management              separately installable
└── integration adapters such as MCP          separately bounded
```

The Core is headless and fully operable without a Web UI. The CLI remains a complete
administrative surface and recovery path throughout the product line.

Version-generation rule:

```text
Data Relay Link 2.x
= headless Core + complete CLI as the only full human management surface
= Full Web Management not part of the stable supported surface

Data Relay Link 3.0+
= same headless Core + complete CLI
+ separately installable Optional Full Web Management
```

When the 3.0 Web Management package is installed, it provides full supported management
capability plus dashboard, visualization, policy explanation, and guided troubleshooting;
it is not a reduced read-only companion and it does not become authoritative state.

Data Relay Link 3.0 also freezes one cross-surface management contract: CLI, Web, and
Management MCP/Plugin are projections of the same Core Management Service. The Web API is
not the Plugin backend, the optional Plugin/relay remains transport/binding only, and
target-OS AI permissions never imply DRLink management authority. Canonical details live
in `MANAGEMENT_SURFACE_CONTRACT.md`.

## 2. Product family

```text
Data Relay
├── Data Relay Control
│   Control what data moves.
└── Data Relay Link
    Control what can connect.
```

This document covers Data Relay Link only.

## 3. v2.4 public foundation

The active v2.4 public model is frozen by the CLI/AI Master.

```text
Managed Host / DRLink Agent

Network Object / Network Group
Service Object / Service Group
Permission Object / Permission Group

AI Identity
Remote Service

Remote Access
Internet Access
AI Access

BLACKLIST / WHITELIST

ConfigurationBundle
```

The earlier intermediate model based on neutral generic Objects, Managed Endpoint, Published Service, Service Preset, ordered first-match ALLOW/DENY Rules, and AI Principal is superseded.

Implementation storage or internal helper names must not redefine the public model.

## 4. Canonical product identity

```text
Product         Data Relay Link
CLI             drlink
Prompt          drlink>
Config          /etc/drlink/
State           /var/lib/drlink/
Upstream relay  official fatedier/frp
```

FRP is an internal/upstream relay-engine dependency, not the product identity.

Product version and Relay Engine version are independent.

## 5. Target scale

Scale is generation-specific.

### Data Relay Link 2.x

```text
1–5 hosts       extremely simple
10–30 hosts     normal CLI operating range
30–50 hosts     upper supported design range
>50 hosts       no 2.x scale claim without separate qualification
```

### Data Relay Link 3.0

```text
1–10 hosts      extremely simple
10–50 hosts     normal Web or CLI operating range
50–100 hosts    fully supported management target
>100 hosts      no stable support claim until separately measured and qualified
```

The 3.0 100-host target is achieved by bounded management architecture around the existing
single-Server/SQLite Core, not by turning Data Relay Link into a large fleet-management
or network-overlay platform.

Data Relay Link 3.0 does not require PostgreSQL, Redis, Kubernetes, a message broker, or
a distributed control plane merely to satisfy the 100-host target.

## 6. CLI execution contexts

### Server

The DRLink Server manages:

```text
Managed Hosts
Enrollments
Network Objects / Groups
Service Objects / Groups
Permission Objects / Groups
AI Identities
Remote Access
Internet Access
AI Access
AI Access Log
Server ConfigurationBundle
revision/audit/backup/restore/system operations
```

### Agent Host

The Agent Host manages:

```text
Agent lifecycle
Remote Services owned by this Agent
Agent ConfigurationBundle
local diagnostics
```

Remote Service mutation is local to the Agent Host. Server inspection is read-only for Remote Service configuration. Live Agent↔Server catalog synchronization and endpoint allocation are authenticated with the enrolled Agent management identity.

## 7. Managed Host and Agent

A Managed Host is a real host managed through DRLink.

A DRLink Agent is the software installed on that Managed Host.

A Managed Host is usable as a Network Object selector where the policy context allows it, but Managed Host lifecycle remains under Managed Host commands.

## 8. Network Objects

Normal user-created Network Object types:

```text
IP
CIDR
FQDN
```

Registered Managed Hosts also appear as Network Objects of type `Managed Host`.

Network Groups are flat reusable collections.

Internet Access source may use a Managed Host, but the source identity remains address-backed because Controlled Egress is agentless. The observed proxy peer IP must match an eligible active address reported for that Managed Host.

If a BLACKLIST rule's destination and service match but the observed proxy source cannot be proven to be the selected Managed Host, evaluation fails closed with DENY instead of treating the request as unmatched/ALLOW. NAT can therefore make a selective Managed Host source unusable; use an IP/CIDR Network Object representing the proxy-visible source when deterministic NAT-aware policy is required.

Internet Access destination must not use a Managed Host, directly or through a Network Group containing one.

## 9. Service Objects

Service Object types (schema):

```text
TCP
UDP
Fixed TCP
```

The normal public Service Object Wizard presents operator-facing presets:

```text
SSH, HTTP, HTTPS, RDP, Custom TCP, Fixed TCP
```

UDP is not offered in that Wizard. Remote Service remains TCP / Fixed TCP only.

Internet Access v2.4 uses a TCP/HTTP/HTTPS CONNECT datapath only. UDP Service
Objects (and Service Groups containing UDP) cannot be selected by Internet Access
rules; mutation paths reject them fail-closed.

Service Groups are flat reusable collections.

Fixed TCP is not a separate policy hierarchy. It is a Service Object subtype.

## 10. Permission Objects

Permission Objects group DRLink AI-operation permissions such as:

```text
host-info
process-read
file-read
command-exec
file-write
file-upload
file-download
```

Permission Groups collect Permission Objects.

## 11. Remote Service

Remote Service represents real connectivity and is owned by an Agent Host.

```text
Agent Host
+ single destination
+ one Service Object
→ Remote Service
→ stable DRLink endpoint
```

Remote Service supports TCP and Fixed TCP Service Objects. UDP Remote Service is not supported.

When destination is another host, the current Agent Host is the Relay Host.

A policy Rule never creates connectivity.

## 12. Remote Service state and endpoint stability

States:

```text
HEALTHY
DEGRADED
DISABLED
```

Valid configuration plus temporary reachability/runtime failure results in `DEGRADED`, not deletion or configuration failure.

Endpoint reservation remains stable across:

```text
Agent restart
temporary disconnect
disable/enable
same pool-class edit
```

New valid Remote Service created while the Server is unavailable may remain `DEGRADED / Pending allocation` until reconnect.

Offline deletion synchronizes endpoint release after reconnect.

## 13. Fixed TCP

Fixed TCP Service Object defines the destination TCP service port.

When a Remote Service uses Fixed TCP, DRLink allocates the public endpoint from a separate Fixed TCP endpoint pool.

The operator does not choose the external port.

Normal TCP and Fixed TCP pool classes do not overlap, and an existing Remote Service cannot be edited in place across those classes.

## 14. Access Policy model

Three policy families:

```text
Remote Access
Internet Access
AI Access
```

Each has:

```text
Mode        BLACKLIST | WHITELIST
Enforcement ENABLED | DISABLED
Rules
```

Initial state:

```text
No Policy
No Rules
Effective access = ALLOW
```

BLACKLIST:

```text
enabled Rule match → DENY
no match           → ALLOW
```

WHITELIST:

```text
enabled Rule match → ALLOW
no match           → DENY
```

There is no rule ordering and no per-rule ALLOW/DENY action.

Deleting the last Rule preserves Mode. Policy Reset removes Mode and Rules and restores initial ALLOW.

Disabling enforcement preserves Mode/Rules but makes policy effective ALLOW ALL. AI authentication remains mandatory.

## 15. AI Identity and AI Access

AI Access source is a verified AI Identity.

Interactive AI:

```text
OAuth Authorization Code
→ verification
→ binding
→ VERIFIED
```

Automation / Custom AI:

```text
OAuth Client Credentials
→ verification
→ binding
→ VERIFIED
```

A display name alone is never authentication.

Authentication and AI Access authorization are separate.

For the v2.4.0 target, the server-side MCP Bridge is included as part of AI Access. MCP is an integration layer over this identity and permission model; it does not introduce a separate public `AI Principal` model.

Stable v2.4.0 qualification is blocked until real ChatGPT Plus interactive user authentication is proven end to end. The required owner/UI evidence is: OAuth Authorization Code/consent completes through the public MCP endpoint, ChatGPT discovers the exposed tools, one authorized operation succeeds, and one intentionally out-of-scope operation is denied by current AI Access policy. Machine-side SDK/HTTP conformance alone does not satisfy this gate. Because retained owner/UI JSON is external evidence, it is not terminal release authority by itself; stable attestation also requires the independently administered `stable-release-owner-ui` GitHub Environment approval gate.

## 16. Human, AI, ConfigurationBundle, and Web convergence

Current v2.4 configuration input styles share the same semantics:

```text
Human Guided Wizard
AI complete one-shot CLI
ConfigurationBundle
```

All converge on one Change Plan.

Data Relay Link 3.0 Optional Full Web Management is an additional presentation/input
surface, not an alternate mutation engine:

```text
CLI / Wizard ────────────┐
AI-generated CLI ────────┤
ConfigurationBundle ─────┼→ canonical Change Plan → authoritative transaction
Optional Web Management ─┘
```

Web actions must reuse the same validation, reference resolution, policy-impact,
confirmation, concurrency, revision/audit, runtime generation, activation, and
verification contracts as the CLI. Agent-owned operations remain Agent-owned; a
Server-hosted Web UI may request them only through an authenticated management/RPC
path and must report offline or unsupported operations truthfully.

Human Wizard draft/inline Objects remain non-authoritative until final Apply. Cancel leaves no partial state.

AI one-shot commands for a new resource must be complete. Missing dependencies are not silently created.

## 17. ConfigurationBundle

Use one-shot CLI for one independent resource.

Use ConfigurationBundle for multiple dependent resources.

Atomicity is local to the current CLI context:

```text
Server Bundle
Agent Bundle
```

There is no single distributed Server+multi-Agent transaction.

Bundle omission means unchanged. `state: absent` means explicit deletion/reset. Same desired state means `NO CHANGE`.

## 18. Runtime apply safety

Mutation pipeline:

```text
parse
validate
resolve
Change Plan
diff/security impact
confirmation
candidate authoritative transaction
runtime generation
activation
verification
success
```

Critical activation failure restores prior authoritative and runtime state where possible.

If restoration itself fails, output must truthfully report incomplete rollback and operator attention required.

A valid but unreachable Remote Service is a `DEGRADED` operational state and is not treated as critical configuration failure.

## 19. Reference protection

Referenced:

```text
Network Objects / Groups
Managed Hosts
Service Objects / Groups
Permission Objects / Groups
AI Identities
```

cannot be deleted while references remain.

The CLI lists references and applies no change.

## 20. Internet Access security boundary

Internet Access must never become an open proxy.

Required controls include:

- explicit source/destination/service authorization;
- FQDN normalization and safe DNS handling;
- DNS rebinding resistance;
- SSRF/private/local/metadata destination protection;
- validated exact-IP connection after resolution where applicable;
- safe protocol/port validation;
- fail-closed malformed security state;
- bounded resource/time-out behavior;
- safe audit logs.

These transport/security controls are independent of the BLACKLIST/WHITELIST rule semantics.

## 21. Network responsibility boundary

Data Relay Link does not silently mutate external cloud security groups, customer firewalls, NAT/DNAT, DNS providers, SSH accounts, routes, or application certificates unless a separately approved product feature explicitly says so.

## 22. Backup and restore

Backup/restore must preserve all persistent product state required for recovery, including identity, Objects/Groups, policy, Remote Service reservation/inventory state that belongs on the Server, trust material, and release provenance.

Restore uses validation and the same mutation safety principles as normal Apply.

## 23. CLI model

Server main menu:

```text
Managed Hosts
Network Objects
Service Objects
Remote Access
Internet Access
AI Access
System
Help
Exit
```

Agent Host main menu:

```text
Remote Services
Agent
Configuration
System
Help
Exit
```

Exact command grammar and Wizard/Bundle behavior are defined by the CLI/AI Master and `CLI_REFERENCE.md`.

## 24. Version and release model

The product follows `docs/VERSION_POLICY.md`.

A stable version exists only after qualification of an immutable exact HEAD and creation/publication of the corresponding immutable release artifacts.

The CLI/AI Master does not by itself change release-channel or MCP packaging decisions; those remain governed by the version/release documents and actual qualified build content.

## 25. Testing strategy

Minimum layers:

```text
static/unit
targeted regression
CLI/PTY
feature ↔ canonical CLI/AI-assisted support ↔ operator-workflow reconciliation via `CLI_FEATURE_SCENARIO_RECONCILIATION.md` (runtime non-destructive product-surface audit)
integration
Agent lifecycle
offline/reconnect
runtime activation/rollback
real public CLI scenarios
multi-host Real E2E
double full Real E2E on the same exact HEAD before stable
```

The product-surface reconciliation is executed by `CLI_FEATURE_SCENARIO_RECONCILIATION.md` and is independent from Full User E2E. It inventories every supported feature from this Product Master, maps it to the canonical public CLI/menu lifecycle and AI-assisted operator support, reconciles Direct-user/AI-assisted read-only discovery with catalog/parser/docs/isolated tests, and proves representative operator workflows are discoverable and coherent without legacy, duplicate, or AI-only/direct-only gaps. The reconciliation never changes assigned runtime product state; create/edit/delete/apply/rollback/restore/update/restart/reboot and real traffic belong to Full User E2E.

`FULL_USER_E2E_SCENARIOS.md` is the complementary real-user black-box quality contract. It validates that users who do not know the product or command set in advance can discover, configure, operate, troubleshoot, recover, upgrade, stress, and use the product through supported public UX and real traffic across the claimed platforms/topologies.

A clean PASS from both exhaustive quality contracts on the same supported product candidate establishes:

```text
PRODUCT_QUALITY_CLOSURE=PASS
NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES
NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES
```

This means product-quality work is closed for the covered scope; it does **not** mean the release process is complete. Stable release still follows `RELEASE_VALIDATION.md` and `RELEASE_CHECKLIST.md`, including their exact-HEAD repetition, CI, artifact, provenance, governance, attestation, approval, tagging, and publication requirements.

Critical v2.4 CLI/AI acceptance includes:

- Guided Wizard implementation and Cancel atomicity;
- BLACKLIST/WHITELIST behavior;
- Managed Host selector validation;
- Agent-local Remote Service ownership;
- Relay DEGRADED/reconnect behavior;
- Fixed TCP separate pool;
- UDP rejection;
- AI Identity verification;
- Server/Agent Bundle parity;
- runtime rollback and truthful rollback-failure path;
- role-aware help/error discovery.

### 25.1 Data Relay Link 3.0 acceptance focus

3.0 extends product-quality closure with Web and management-scale evidence.

At minimum, the exact candidate must prove:

```text
Core + CLI remain complete without Web
Web management capability parity
Admin / Operator / Read Only authorization
shared Change Plan semantics across CLI/Web/Bundle
Policy Simulator / Decision Trace parity
saved policy regression tests
blast-radius accuracy
effective-access graph accuracy
connection-diagnosis workflow
Agent RPC ownership / no false remote success
bounded multi-host Job Engine
dashboard/search/audit bounds
100-host control-plane and mixed-operation scale
Web failure isolation from relay enforcement
3.0 backup/restore and lifecycle
real-browser user journeys
```

The 100-host scale gate is a management-plane qualification. It does not require 100
physical hosts for every functional assertion; scale/saturation may use controlled
simulated Agents, while real supported-platform Agents and real traffic remain mandatory
for functional claims.

## 26. Non-goals

Data Relay Link is not:

```text
VPN
full network overlay
SASE/SWG
DLP platform
large fleet orchestrator
Web UI as a mandatory Core/CLI dependency
Web-only authoritative state or database-heavy management plane
generic open proxy
transparent full-network bridge
```

## 26.1 Operator documentation set

The repository maintains task-oriented operator guides derived from the canonical specifications:

```text
DOCUMENTATION_INDEX.md
INSTALLATION.md
UPGRADE.md
REMOTE_ACCESS.md
AI_ACCESS_MCP.md
WEB_MANAGEMENT.md
TROUBLESHOOTING.md
```

These guides make existing normative behavior easier to find. They do not override the Product Master, CLI/AI Master, Version Policy, Security specification, or exact release qualification evidence.

## 27. Documentation ownership

```text
DATA_RELAY_ROADMAP.md
  forward-looking product generation, phase ordering, scope freeze, and implementation dependency plan

DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md
  authoritative 2.x CLI/AI public behavior

Data Relay Link CLI Information Architecture.md
  derived menus/discovery/UX

CLI_REFERENCE.md
  derived direct command reference

CONFIGURATION_BUNDLE.md
  derived Bundle contract

CONTROL_PLANE_ARCHITECTURE.md
  internal architecture/schema history; public semantics must remain consistent with the Master

WEB_MANAGEMENT.md
  Data Relay Link 3.0 Optional Full Web Management architecture, UX, security, feature, and acceptance contract

VERSION_POLICY.md / RELEASE_CHECKLIST.md / RELEASE_VALIDATION.md
  version and qualification governance
```

No other document may redefine the public CLI/AI model independently.

## 28. Decision log

### 2026-09 — Final v2.4 CLI/AI model freeze

**Decision:** Adopt the Managed Host + Network/Service/Permission Object + AI Identity + Agent-local Remote Service + BLACKLIST/WHITELIST model as the v2.4 public CLI/AI contract.

**Supersedes:** the intermediate Managed Endpoint / Published Service / Service Preset / ordered first-match ALLOW-DENY / AI Principal public model.

### 2026-09 — Fixed TCP

**Decision:** Fixed TCP is a Service Object subtype. External endpoint allocation occurs when a Remote Service uses it, from a separate Fixed TCP endpoint pool.

### 2026-09 — Context-local Bundle atomicity

**Decision:** ConfigurationBundle atomicity is scoped to the current Server or Agent CLI context, not distributed across contexts.

### 2026-10 — Managed Host Internet source identity under NAT

**Decision:** Keep Managed Host as an Internet Access source selector, but define it as address-backed because Controlled Egress remains agentless. Runtime identity exists only when the observed proxy peer IP matches an eligible active address reported for that Managed Host.

**Security consequence:** In BLACKLIST mode, when destination and service match a Managed-Host-sourced rule but that source identity cannot be proven, Data Relay Link denies fail-closed rather than treating the connection as unmatched/ALLOW. NAT-aware deployments that need deterministic source policy should use the proxy-visible IP/CIDR.

**Reason:** Do not invent per-host cryptographic identity for an agentless proxy, and do not let source-identity ambiguity silently broaden access.

### 2026-10 — Data Relay Link 3.0 Optional Full Web Management

**Decision:** Keep the entire 2.x line as the headless generation where CLI is the only complete human management surface. Data Relay Link 3.0.0 is the first stable release target with a separately installable Full Web Management surface. The 3.0 Core remains headless and fully operable through the CLI when Web Management is absent or stopped.

**Versioning rule:** This MAJOR boundary is an intentional product-generation decision, even though an optional Web package could otherwise be implemented in a backward-compatible way. The new supported browser management experience is what distinguishes the 3.x generation from 2.x.

**Capability rule:** Web Management must cover the supported management capabilities available through the CLI and add dashboard, visualization, policy simulation/decision trace, guided installation/enrollment, audit exploration, and troubleshooting workflows.

**Architecture rule:** Web Management owns no alternate authoritative state. CLI, Web, ConfigurationBundle, and integration adapters converge on the same Core domain/change-plan, validation, authorization, revision/audit, runtime-generation, and verification paths. Agent-owned mutations remain Agent-owned and may be requested remotely only through authenticated management/RPC.

**Security/lightweight rule:** The Web package is optional, disabled/uninstalled by default, has no separate database, and cannot become a dependency for Core startup, enforcement, CLI recovery, backup/restore, or upgrade.

### 2026-10 — Data Relay Link 3.0 100-host management boundary

**Decision:** Qualify Data Relay Link 3.0 for up to 100 Managed Hosts on the existing
single-Server + SQLite Core before considering any external database or distributed
management architecture.

**Management architecture:** Add bounded command/query separation, rebuildable read
models, an operational-state aggregator, a bounded Job Engine, and an Agent RPC Worker
Pool as logical management modules. These modules may remain in one local process/package.

**Operator-safety scope:** 3.0 GA includes Draft Workspace, saved policy regression
tests, Blast Radius Preview, Effective Access Graph, Connection Diagnosis, Attention
Center, version drift, searchable audit/revisions, Saved Views, bounded safe multi-Host
jobs, offline-capable local Web-admin MFA, time-bounded Temporary Access, bounded
live-access visibility with an emergency new-access cutoff workflow, Managed Host
admission/quarantine, bounded staged Agent updates, a separate public Automation API with
scoped Service Accounts, signed generic webhook notifications, and read-only Access Hygiene.

**Scope discipline:** Full JIT/access-request approval, session recording, browser
terminals, device-posture/MDM, broad discovery, SIEM/reporting, external HA/multi-region
control, and large-fleet orchestration are not 3.0 goals. Native Email/Slack/Teams
notification adapters beyond the required generic signed webhook, SSO/IdP integration,
SAML/LDAP/SCIM provisioning, GitOps locking, and continuous external audit/SIEM streaming
remain later/demand-driven.

A bounded one-step local JIT request/approval that reuses Temporary Access is P2 stretch only; multi-stage identity governance remains excluded.

**Reason:** Improve day-to-day operation and troubleshooting without changing Data Relay
Link into a different product category or forcing repeated Core redesign.

### 2026-10 — 3.0 competitive baseline essentials

**Decision:** Keep the selected 3.0 additions small and priority-separated rather than
treating them as one feature bundle.

**P0 security baseline — Local Web MFA capability:** Password-backed Web administration
supports offline-capable local TOTP MFA per operator, bounded/revocable browser sessions,
and local recovery. MFA is disabled by default and a Web Admin enables it per user. The
user completes their own TOTP enrollment on the next password sign-in and receives
one-time recovery codes directly; the Admin never receives the user's TOTP seed.
SSO/OIDC/IdP integration is excluded from 3.0; the product remains fully operable in
isolated environments without external identity infrastructure.

**P1 product value — Temporary Access:** Add server-authoritative expiry to supported
Remote / Internet / AI Access grants. Expiration automatically denies new authorization
and is visible/audited. Scope stops at set/change/clear expiry, policy evaluation,
CLI/Bundle/Web parity, preview/test, backup/restore, and Attention. No requester/approver
workflow, recurring schedule, automatic renewal, or implicit active-session termination.

**P1 operations value — Live Access Visibility:** Show bounded current-use state each
access plane can actually prove. Exact per-connection state, aggregate state, and UNKNOWN
must be distinguished rather than normalized into false precision.

**P1 incident response — Emergency New-Access Cutoff:** Provide an explicit reversible
security override that immediately denies new authorization at supported scopes without
rewriting the operator's normal policy intent. Existing active work is terminated only
where Data Relay Link or the pinned official upstream exposes a proven supported lifecycle.

**P0 trust baseline — Managed Host Approval / Quarantine:** Add an optional
Server policy that can place newly enrolled Managed Hosts into `PENDING_APPROVAL`. Pending
Hosts may authenticate enough to report bounded identity/status but cannot receive normal
Remote / Internet / AI Access or management Jobs until an Admin approves them. A
pre-approved enrollment may activate immediately so Zero-Touch automation remains
possible. Rejection/revocation is audited and never silently rebinds identity.

**P0 operations baseline — Managed Update / Staged Rollout:** Extend the bounded Job Engine
to perform manual staged Agent updates against qualified immutable artifacts. A rollout
supports an explicit canary set or first wave, bounded wave size/concurrency, per-target
progress, automatic pause on failure threshold, and canonical per-Agent rollback where the
existing updater supports it. No recurring scheduler or unattended maintenance-window
engine is required for 3.0.

**P1 integration value — Public Automation API + Service Accounts:** Add a separately
versioned supported automation API over the same Core Management Service. It is not the
browser-internal Web API and is not the MCP adapter. Local Service Accounts are distinct
non-human management principals with least-privilege management permissions, display-once
credentials, revocation/rotation, optional expiry, rate/resource bounds, and complete audit
attribution. No external IdP is required.

**P1 operations value — Signed Event Webhook:** Add one generic optional HTTPS event
Webhook channel backed by the local Attention/Audit event boundary. Delivery is bounded,
retryable, idempotency-friendly, secret-safe, HMAC/signature protected, observable, and
must never block Core enforcement or mutation commit. Slack/Teams/Email-specific connectors
remain later adapters over this generic contract.

**P1 hygiene value — Access Hygiene Recommendations:** Use existing audit, policy graph,
credential/session metadata, and inventory state to surface read-only recommendations such
as stale Hosts, unused standing access, orphaned references, expiring credentials, and
long-lived grants. Every recommendation must state evidence quality and must not auto-lock,
auto-delete, or rewrite policy in 3.0.

**P2 stretch — Lightweight JIT Access Request / Approval:** If implementation capacity
remains after P0/P1 completion, add one local requester -> Admin approve/deny flow that
materializes a normal time-bounded Temporary Access grant with reason, TTL, actor, and
audit. No multi-stage approval graph, delegation engine, recurring entitlement review,
external ChatOps/Jira/ServiceNow dependency, or automatic renewal is part of this stretch
scope. This capability is not a 3.0 GA blocker.

**P2/conditional — Active connection termination:** Per-connection kill is not a 3.0 GA
requirement for Remote Access and must not require an FRP fork. It may ship per plane where
lifecycle ownership and deterministic termination are already proven.

**P0 admission baseline — Managed Host Approval / Quarantine:** Newly enrolled Hosts may
remain Pending Approval, explicit pre-approved enrollment is supported for controlled
automation, and Quarantine denies new access without rewriting normal policy or collapsing
trust revoke/retire semantics.

**P0 lifecycle baseline — Bounded Staged Managed Agent Updates:** Add manual rollout over
the canonical rollback-capable Agent updater with immutable target, bounded target set,
canary gate, bounded concurrency, halt-on-failure, and truthful per-target rollback. This
is not generic RMM or recurring patch scheduling.

**P1 automation value — Public Automation API + scoped Service Accounts:** Keep the bundled
Web API private and expose a separate versioned Automation API adapter over the same Core
Management Service. Local non-interactive Service Accounts receive explicit management
permissions and display-once, hashed, revocable/rotatable tokens.

**P1 notification value — Signed Generic Webhook:** Promote one optional generic HTTPS
webhook sink using the Core event boundary, versioned JSON, stable event IDs, per-endpoint
signing secret, bounded retry/backoff, and local Attention on delivery degradation. Delivery
is never an enforcement dependency; native Email/Slack/Teams adapters remain later.

**P1 hygiene value — Access Hygiene:** Reuse audit + Effective Access Graph evidence to
identify stale/unused/orphaned/action-required access with explicit UNKNOWN_EVIDENCE when
coverage is incomplete. 3.0 recommendations never auto-revoke or auto-delete access.

**P2 stretch — Lightweight JIT:** A one-step request/reviewer flow may materialize the
existing Temporary Access grant if it requires no new identity/workflow platform. It is not
a 3.0 GA blocker.

**Not promoted:** SSO/IdP, multi-stage JIT governance, device posture/MDM, session recording,
credential vaulting, payload replay, SCIM, generic RMM, and general identity governance
remain outside 3.0.

**Reason:** These additions close repeated day-2 operator expectations while reusing the
existing Core, policy, audit, Attention, Job, and update foundations instead of changing
Data Relay Link into PAM, SASE, an identity platform, or an RMM product. Exact surface and
acceptance contracts are frozen in `docs/COMPETITIVE_EXPANSION_3_0.md`.

### 2026-10 — First-class audit logging contract

**Decision:** Audit logging is a first-class Core security/operations capability, not a
Web-only activity feed.

**Model:** One versioned event envelope with CONTROL, ACCESS_DECISION, and
SECURITY_LIFECYCLE logical streams. Attribution covers CLI, Web, ConfigurationBundle,
AI-assisted operations, Agent RPC, and system lifecycle activity.

**Safety:** Successful state-changing operations commit CONTROL audit atomically with
their authoritative transaction and fail when durable audit persistence fails. Failed
security-relevant attempts remain failed if their separate audit write also fails, and the
product reports CRITICAL audit-degraded health. A would-be ACCESS_DECISION ALLOW does not
proceed unless its secret-safe event is durably enqueued; a DENY remains DENY if audit
enqueue also fails. Audit excludes secrets, credentials, application payloads, TLS contents,
and sensitive URL query strings.

**Architecture/Storage:** CONTROL and Core lifecycle events use the Core Audit Event
Service; successful CONTROL mutations remain in the same SQLite transaction as revision
and state. Privilege-separated Remote/Internet enforcement keeps `drlink.db` read-only and
durably appends ACCESS_DECISION events to bounded per-plane spools. A Core Audit Ingestor
imports those events into SQLite in short idempotent batches with committed checkpoints.
SQLite remains the single query/history store; the spool is durable transport, not a
second policy authority.

**UX:** Audit uses bounded indexed queries, cursor pagination, retention/storage
guardrails, backup/restore continuity, CLI/Web query parity, Audit/Revision Explorer, and
manual filtered NDJSON export from CLI and Web in 3.0. DRL3-7 defaults retained local
history to 365 days for CONTROL/SECURITY_LIFECYCLE and 90 days for ACCESS_DECISION with a
500000-event capacity; capacity pruning is ACCESS_DECISION-only. Manual export is a
Core-owned mode-0600 NDJSON artifact under `/var/lib/drlink/audit-exports/`, bounded to
50000 events / 64 MiB, and is not exposed through a Web download endpoint.

**Scope:** 3.0 includes a bounded generic signed event Webhook for selected
Attention/security lifecycle events. Continuous bulk audit/SIEM/S3/syslog streaming,
destination-specific Email/Slack integrations, session recording, payload capture, and a
SIEM/reporting platform remain later/out of scope. Append-only product semantics do not
justify a tamper-proof claim against a privileged host administrator.

## 29. Master rule

Before adding a feature, ask:

> Does this make Data Relay Link better at safely and simply connecting only the services or destinations that are actually needed?

Then preserve:

> **Simple to deploy. Simple to understand. Safe to operate. Lightweight by design.**
