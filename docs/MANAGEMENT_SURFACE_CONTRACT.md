# Data Relay Link 3.0 — Management Surface Contract

> **Status:** Normative 3.0 design contract
> **Applies to:** CLI, Optional Full Web Management, MCP/AI integration, and the optional `datarelay-link-plugin`
> **Primary authority:** `PRODUCT_MASTER.md`, `DATA_RELAY_ROADMAP.md`
> **Purpose:** Keep one management meaning across every surface without duplicating product logic.

## 1. Goal

Data Relay Link 3.0 exposes one Core management model through several surfaces:

```text
                         Data Relay Link Core
                                │
                    Core Management Service
                                │
       ┌────────────────────────┼────────────────────────┐
       │                        │                        │
       ▼                        ▼                        ▼
 complete local CLI       Web API adapter        Management MCP adapter
                                 │                        │
                                 ▼                        ▼
                           Web Management          direct MCP clients
                                                        │
                                                        ▼
                                               optional Plugin relay
                                                        │
                                                        ▼
                                                     ChatGPT
```

The surfaces may differ in presentation, but they must not differ in authorization,
policy evaluation, Change Plan semantics, revision/audit behavior, runtime activation,
Agent ownership, recovery truth, or failure behavior.

## 2. Non-goals

This contract does **not**:

- turn the Web `/api/v1` namespace into a public automation API;
- make the optional Plugin/relay part of Core availability;
- require ChatGPT, Web Management, or any external service for CLI/Core recovery;
- make MCP a second policy or authorization engine;
- allow Plugin/relay code to invent, remove, rename, or reinterpret DRLink tools;
- make every CLI/Web capability available through MCP;
- expose secrets, enrollment credentials, private keys, OAuth tokens, or protected
  recovery material through ordinary management tools;
- make active Remote Access connection termination a 3.0 GA requirement;
- add SSO/IdP to 3.0.

## 3. Authority and component boundary

### 3.1 Core owns product semantics

The Core Management Service owns:

- resource validation and reference resolution;
- RBAC / AI Access authorization;
- policy evaluation and policy-test/explain behavior;
- Change Plan generation;
- security impact / blast-radius calculation;
- optimistic concurrency and expected-revision checks;
- state mutation;
- revision and audit generation;
- runtime compile / activate / rollback / verification;
- Agent RPC ownership and truthful offline results;
- Temporary Access expiry evaluation;
- Emergency New-Access Cutoff state;
- bounded management Jobs.

No adapter may reproduce these semantics independently.

### 3.2 Web is a first-party presentation adapter

```text
Browser
  → drlink-web
  → Web API adapter
  → Core Management Service
```

The Web API is initially an internal first-party browser contract. A later public API
decision may promote part of it, but Plugin/MCP must not depend on Web API stability.

Web adds visualization, guided workflows, forms, rich diff/preview, graphs, Attention,
and confirmation UX. It owns no alternate authoritative state.

### 3.3 MCP is a management integration adapter

```text
MCP host
  → authenticated DRLink MCP endpoint
  → Management MCP adapter
  → Core Management Service
```

Management MCP tools are defined by Data Relay Link Server. They are not defined by the
Plugin relay.

Every privileged call is authorized against current identity, current policy, current
revision, and current target/resource context.

### 3.4 Optional ChatGPT Plugin remains transport/binding only

The optional repository `datarelay-labs/datarelay-link-plugin` remains a separate
integration product:

```text
ChatGPT
  → Data Relay Link Plugin package
  → Plugin MCP relay
  → subject's bound DRLink Server /mcp
  → DRLink Server tool discovery + per-call authorization
```

The relay:

- authenticates the Plugin subject;
- resolves only that subject's explicit DRLink Server binding;
- forwards MCP protocol/tool metadata;
- protects upstream credentials;
- performs transport-level audit/health appropriate to the relay.

The relay does **not**:

- call the DRLink Web API as a management backend;
- invent management tools;
- filter tools to create a second authorization policy;
- cache DRLink authorization decisions;
- convert an upstream DENY into ALLOW;
- synthesize product state from relay-local data.

## 4. Surface roles

### 4.1 CLI

The CLI remains:

- the complete local human management surface;
- the complete recovery surface;
- available without Web or Plugin;
- capable of expressing all authoritative 3.0 management state.

A Web-only or Plugin-only authoritative operation is prohibited.

### 4.2 Web

Web is the complete graphical management surface for supported normal administration.
Where an operation is intentionally shell/recovery-only, Web records that classification
in the capability parity ledger.

### 4.3 Plugin/MCP

Plugin/MCP is a **bounded assisted-management surface**, not a second full admin console.

Its highest-value 3.0 uses are:

- inventory and status;
- health and Connection Diagnosis;
- bounded audit/activity lookup;
- policy test/explain;
- Temporary Access preview and controlled apply;
- Live Access Visibility;
- Emergency New-Access Cutoff preview and tightly authorized apply;
- Job inspection and safe diagnostic operations.

Recovery authority, operator-security administration, and other high-risk system lifecycle
operations remain outside the default Plugin surface.

## 5. Management permission boundary

Existing target-OS AI permissions and DRLink management permissions are different trust
domains.

Examples of existing target permissions include:

```text
host-info
process-read
file-read
file-write
file-upload
file-download
command-exec
```

Granting any of those must **never** imply permission to mutate Data Relay Link itself.

DRL3-0 freezes the baseline management permission values below, and DRL3-3 adds
`management-config` for guided Core configuration parity:

```text
management-read
management-diagnose
management-policy-test
management-temporary-access
management-emergency-cutoff
management-job-observe
management-job-run
management-config
```

These names are public 3.0 capability values. They are separate from target-OS permissions
and must not be aliased to `host-info`, `command-exec`, file permissions, or Web roles.

High-impact management permission is never implied by `command-exec`, file write, Admin
display name, Plugin installation, or possession of a relay binding.

## 6. Operation classes

Every Core management operation exposed through an adapter has one operation class.

| Class | Meaning | Typical examples | Plugin default |
|---|---|---|---|
| OBSERVE | Side-effect free bounded read | inventory, health, audit query, live visibility | allowed when AI Access grants management-read |
| TEST | Side-effect free evaluation | policy test, Decision Trace, diagnosis, change preview | allowed when corresponding read/test permission exists |
| CHANGE | Authoritative reversible mutation | metadata, policy, Temporary Access expiry | conditional; requires management mutation permission + Change Plan/apply |
| INCIDENT_CHANGE | High-impact reversible security override | Emergency New-Access Cutoff | disabled by default; explicit dedicated permission + stronger confirmation |
| JOB | Bounded asynchronous operation | diagnostics/support collection, safe fan-out | observe allowed; start/cancel only when separately authorized |
| RECOVERY_AUTHORITY | High-risk recovery/security authority | restore, uninstall, operator/MFA recovery administration | not exposed to Plugin in 3.0 |

An operation's class is part of the Core capability catalog and must not differ between
Web and MCP.

## 7. Shared mutation protocol

Security-relevant state changes use one semantic flow:

```text
intent
  → validate
  → authorize
  → build Change Plan
  → compute impact
  → preview
  → explicit apply
  → expected-revision re-check
  → authoritative transaction
  → revision + audit
  → runtime activate / verify
  → truthful result
```

Web and MCP do not receive special bypasses.

### 7.1 Change Plan binding

A management Change Plan used through MCP must be bound to at least:

- authenticated AI Identity;
- target DRLink Server;
- requested operation/resource;
- expected authoritative revision;
- normalized impact summary;
- short validity window or equivalent stale-plan protection.

A stale, cross-identity, cross-server, or revision-mismatched plan fails closed.

Exact token/identifier representation is DRL3-0 implementation design.

### 7.2 Confirmation

Tool metadata/annotations may help a host such as ChatGPT present confirmation UI, but
host UI is not authorization authority.

Rules:

- OBSERVE/TEST require no mutation confirmation.
- CHANGE requires preview before apply.
- INCIDENT_CHANGE requires a dedicated permission and stronger explicit confirmation.
- If the MCP host cannot satisfy the required confirmation contract, the corresponding
  high-impact apply operation remains unavailable through that host.
- CLI/Web use their native confirmation UX over the same Core impact result.

## 8. 3.0 capability projection matrix

Legend:

```text
FULL        supported normal surface
READ        read/observe/test only
CONTROLLED  mutation allowed only with dedicated management permission + preview/apply
COND        conditional on proven per-plane lifecycle support
NO          intentionally not exposed in 3.0
```

| Capability | CLI | Web | Plugin/MCP | Notes |
|---|---:|---:|---:|---|
| Inventory / resource detail | FULL | FULL | READ | bounded queries |
| Health / Doctor | FULL | FULL | READ | no diagnostic mutation from read |
| Connection Diagnosis | FULL | FULL | READ | uses same Core correlation |
| Policy test / Decision Trace | FULL | FULL | READ | same evaluator |
| Effective Access explanation | FULL | FULL | READ | graph visualization remains Web-rich |
| Audit query/detail | FULL | FULL | READ | bounded query; secrets redacted |
| Bulk NDJSON audit export | FULL | FULL | NO | avoid large artifact transport through chat |
| Temporary Access preview | FULL | FULL | READ | before/at/after expiry semantics |
| Temporary Access set/change/clear | FULL | FULL | CONTROLLED | dedicated management permission |
| Live Access Visibility | FULL | FULL | READ | EXACT / AGGREGATE / UNKNOWN |
| Emergency New-Access Cutoff preview | FULL | FULL | READ | impact and active-session limitation shown |
| Emergency New-Access Cutoff apply/clear | FULL | FULL | CONTROLLED | dedicated high-impact permission + confirmation |
| Active connection termination | COND | COND | NO | P2/conditional; not 3.0 GA blocker |
| Job status/result | FULL | FULL | READ | bounded |
| Safe diagnostic Job start | FULL | FULL | CONTROLLED | only approved job families |
| Broad/destructive fleet actions | NO | NO | NO | outside 3.0 |
| ConfigurationBundle test/diff | FULL | FULL | READ | no secret distribution |
| ConfigurationBundle apply | FULL | FULL | NO by default | may be separately designed later |
| Backup status/validate | FULL | FULL | READ | no protected archive contents |
| Backup create | FULL | FULL | NO | default Plugin exclusion |
| Restore | FULL | FULL | NO | recovery authority |
| Product/Relay update mutation | FULL | FULL where supported | NO | lifecycle authority |
| Certificate/private-key mutation | FULL | FULL where supported | NO | credential/security authority |
| Web operator / role / MFA administration | FULL | FULL | NO | management-security authority |
| Enrollment secret issuance/display | FULL | FULL | NO | protected credential workflow |
| Support-bundle generation | FULL | FULL | CONTROLLED | only if output transport/redaction contract is safe |

The matrix is a minimum contract. DRL3-0 may make Plugin exposure narrower, but may not
silently broaden high-risk operations.

## 9. Feature-specific interaction contract

### 9.1 Temporary Access

Preferred user flow:

```text
"Give contractor-a SSH access to customer-a for 2 hours"
  → MCP resolves current resources/policy
  → Temporary Access preview Change Plan
  → shows scope + exact expiry + impact
  → explicit apply
  → Core revision/audit
  → result includes expiry and safe resource identifiers
```

The Plugin does not implement timers. Core policy evaluation owns expiry.

### 9.2 Live Access Visibility

Plugin and Web read the same Core operational observations.

A result must state fidelity:

```text
EXACT_PER_CONNECTION
AGGREGATE
UNKNOWN
```

The Plugin must not phrase AGGREGATE or UNKNOWN data as an exact session list.

### 9.3 Emergency New-Access Cutoff

Preferred assisted flow:

```text
"Block new access to customer-a now"
  → preview cutoff scope
  → show what new authorization becomes denied
  → show active-session limitation
  → explicit high-impact confirmation
  → apply dedicated cutoff state
  → audit + runtime verify
```

Clearing the cutoff restores the underlying normal policy because the cutoff did not
rewrite that policy.

Active connection termination is a separate conditional operation and is not implied.

### 9.4 Audit and Diagnosis

Plugin/MCP may query bounded redacted audit and diagnosis results, then explain them in
natural language.

The Plugin must not:

- fetch arbitrary unbounded history;
- receive protected payloads;
- substitute relay-local logs for authoritative DRLink audit;
- claim a root cause when Core reports UNKNOWN.

## 10. Web / Plugin experience relationship

Web and Plugin complement each other; neither embeds the other.

Use ChatGPT/Plugin for:

- natural-language intent;
- cross-resource read/diagnosis;
- assisted preview;
- concise explanations;
- carefully bounded approved actions.

Use Web for:

- dense inventory;
- visual policy authoring;
- graph relationships;
- long audit/history exploration;
- multi-step administration;
- recovery/system/security administration;
- rich progress views.

A safe MCP result may include immutable resource IDs and, when Web is installed and a
non-secret canonical route exists, an optional Web deep link. The operation must remain
understandable and usable without that link.

## 11. Plugin relay compatibility contract

The existing optional Plugin architecture remains valid for 3.0 management tools because
the relay passes upstream MCP tool discovery/calls through.

When DRLink Server adds management tools:

1. the Server owns the tool schema/annotations/security metadata;
2. `tools/list` exposes only tools the Server chooses to advertise under its protocol
   contract;
3. the relay passes the tool metadata through unchanged;
4. the relay passes `tools/call` to the subject's bound Server;
5. DRLink Server performs current per-call authorization;
6. relay binding does not grant management permission by itself.

No Plugin release should require copying Core management semantics into relay source.

## 12. Failure and independence rules

- Web down → CLI/Core/MCP enforcement semantics remain available as designed.
- Plugin relay down → direct CLI/Web/Core remain unaffected.
- Plugin not installed → no Core capability is lost.
- Web not installed → no Plugin/MCP Core capability depends on it.
- MCP host cannot confirm a high-impact operation → operation is unavailable through that
  host, not silently auto-applied.
- AI Identity loses permission between preview and apply → apply fails.
- policy/revision changes between preview and apply → apply fails stale/conflict.
- Agent becomes unavailable → Agent-owned operation returns truthful blocked/unavailable;
  no false success.

DRL3-3 Agent-owned Remote Service mutation uses the existing enrolled-Agent signed
management transport plus target-bound Management Jobs. The Server queues work only for
an immutable Managed Host ID; an Agent may claim and complete only its own target row.
The Agent lifecycle worker executes the existing Agent-side Remote Service Core operation,
then reports the terminal Job result. An unreachable Agent therefore cannot produce a
successful completion; work remains non-terminal until claimed or fails through the Job
execution/deadline contract. Server-side desired state alone never implies Agent runtime
HEALTHY.
- Emergency cutoff runtime activation cannot be verified → report failure/degraded state
  and follow the Core rollback/recovery contract.

## 13. DRL3-0 frozen management catalog

The exact admitted Management MCP tool names are:

```text
drlink_inventory_list
drlink_inventory_get
drlink_health
drlink_diagnose_connection
drlink_policy_test
drlink_audit_query
drlink_temporary_access_preview
drlink_temporary_access_apply
drlink_live_access
drlink_emergency_cutoff_preview
drlink_emergency_cutoff_apply
drlink_emergency_cutoff_clear
drlink_job_list
drlink_job_get
drlink_diagnostic_job_start
```

Their required permission, operation class, Plugin exposure, input schema, and MCP
annotations are defined by `lib/drlink_management_catalog.py`. The catalog is Core data;
the Plugin relay must pass descriptors through rather than maintaining a copied list.

DRL3-3 adds these Core/Web-only guided configuration operations:

```text
drlink_guided_change_preview
drlink_guided_change_apply
```

They require `management-config`, delegate Managed Host metadata, Object/Group, and
Remote/Internet/AI Access Rule lifecycle validation and mutation semantics to the existing
Core CRUD/Change Plan path, and use `PLUGIN_NO`. They are therefore available to
the first-party Web adapter when authorized but are **not** added to the admitted
Management MCP/Plugin tool list above.

The DRL3-3 Draft Workspace follows the same authority boundary even though Draft CRUD is
Web-only operational state rather than an MCP tool. Browser routes call the Web adapter,
which calls `ManagementCoreService`; the HTTP layer never calls the Draft service or
SQLite directly. Draft Preview issues an opaque Core Change Plan bound to the actor,
Server, exact authoritative revision, Draft ID, and Draft bundle digest. Apply requires
that exact still-pending plan; cross-actor reuse, revision drift, or editing the Draft
after Preview fails closed and requires a fresh Preview. Cancel never mutates
authoritative configuration.

DRL3-0 additionally freezes:

- Change Plan identifiers as short-lived opaque Core-issued IDs bound to authenticated
  identity, DRLink Server identity, normalized operation/resource, expected revision, and
  impact summary;
- stale/cross-identity/cross-server/revision-mismatched Change Plans fail closed;
- OBSERVE/TEST require no mutation confirmation;
- CHANGE requires preview before apply;
- INCIDENT_CHANGE requires the dedicated permission and explicit high-impact confirmation;
- JOB start/cancel is allowed only for explicitly admitted bounded job families;
- RECOVERY_AUTHORITY is never exposed through the 3.0 Plugin surface;
- list/history result limits are server-bounded and cursor/keyset-based where unbounded
  offset growth would be unsafe;
- direct Core MCP and optional Plugin relay qualification remain separate evidence lanes.

Exact serialization details for opaque Change Plan IDs and internal cursor encodings may
remain implementation details as long as these frozen semantics are preserved.

DRL3-3 Zero-Touch enrollment issuance is a first-party Web/Core workflow, not a Management
MCP tool. Non-secret enrollment lifecycle/status may be observed through Web under
`management-read`, but issuing a short-lived credential requires an authenticated local
Web Admin plus `management-config`. Core delegates pair creation, TTL/capacity enforcement,
and bootstrap credential handling to the existing allocator authority. The credential-
bearing install command is display-once in the issuance response and is never returned by
normal enrollment history. Plugin/MCP receives no enrollment credential issuance surface.

## 14. Acceptance

3.0 design/implementation is not surface-coherent until evidence proves:

```text
CORE_OPERATION_AUTHORITY=PASS
CLI_WEB_CORE_SEMANTIC_PARITY=PASS
MCP_CORE_SEMANTIC_PARITY=PASS
PLUGIN_RELAY_TOOL_PASSTHROUGH=PASS
PLUGIN_RELAY_AUTHZ_REINTERPRETATION=NO
PLUGIN_WEB_API_DEPENDENCY=NO
TARGET_OS_PERMISSION_IMPLIES_MANAGEMENT_PERMISSION=NO
TEMPORARY_ACCESS_CROSS_SURFACE_PARITY=PASS
LIVE_ACCESS_FIDELITY_CROSS_SURFACE=PASS
EMERGENCY_CUTOFF_PREVIEW_APPLY_PARITY=PASS
HIGH_RISK_PLUGIN_DEFAULT_EXCLUSION=PASS
STALE_CHANGE_PLAN_FAIL_CLOSED=PASS
PER_CALL_AI_ACCESS_AUTHORIZATION=PASS
CORE_WITHOUT_WEB_PLUGIN=PASS
```

Exact Plugin acceptance remains separate from direct Core MCP acceptance. A passing direct
MCP test does not prove Plugin relay behavior, and a passing Plugin relay test does not
replace CLI/Web/Core qualification.
