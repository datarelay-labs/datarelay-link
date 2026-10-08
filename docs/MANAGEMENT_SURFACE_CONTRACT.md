# Data Relay Link 3.0 — Management Surface Contract

> **Status:** Normative 3.0 design contract
> **Applies to:** CLI, Optional Full Web Management, Public Automation API, MCP/AI integration, and the optional `datarelay-link-plugin`
> **Primary authority:** `PRODUCT_MASTER.md`, `DATA_RELAY_ROADMAP.md`
> **Purpose:** Keep one management meaning across every surface without duplicating product logic.

## 1. Goal

Data Relay Link 3.0 exposes one Core management model through several surfaces:

```text
                         Data Relay Link Core
                                │
                    Core Management Service
                                │
       ┌──────────────────┬─────┴─────┬──────────────────┐
       │                  │           │                  │
       ▼                  ▼           ▼                  ▼
 complete local CLI  Web API adapter  Public Automation  Management MCP
                         │             API adapter         adapter
                         ▼                 │                  │
                   Web Management    Service Accounts     direct MCP clients
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

- make the browser-internal Web `/api/v1` namespace itself the public automation contract; 3.0 uses a separate supported automation namespace/adapter;
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
- bounded management Jobs, including staged Agent update rollout;
- Managed Host approval/quarantine state;
- Service Account authorization for the Public Automation API;
- signed event-Webhook configuration/delivery health;
- Access Hygiene derived recommendations;
- optional lightweight JIT request state that only materializes Temporary Access.

No adapter may reproduce these semantics independently.

### 3.2 Web is a first-party presentation adapter

```text
Browser
  → drlink-web
  → Web API adapter
  → Core Management Service
```

The Web API is an internal first-party browser contract and remains so in 3.0. Public
automation is provided by a separate versioned Automation API adapter over the same Core
Management Service. Plugin/MCP must not depend on either Web endpoint shapes or Automation
API transport details.

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

- call the DRLink Web API or Public Automation API as a management backend;
- invent management tools;
- filter tools to create a second authorization policy;
- cache DRLink authorization decisions;
- convert an upstream DENY into ALLOW;
- synthesize product state from relay-local data.

### 3.5 Public Automation API is a separate supported adapter

```text
Service Account
  → /api/automation/v1
  → Public Automation API adapter
  → Core Management Service
```

The Public Automation API exposes only a versioned allowlisted Core capability subset.
It does not reuse browser cookies/CSRF/session state, does not depend on Web Management
being installed, and does not expose internal Web endpoint shapes as a public contract.
Service Account permissions are management permissions only; credentials are display-once,
revocable/rotatable and optional-expiry, and every call retains service-account actor/audit
attribution. Automation cannot bypass Change Plan, expected revision, confirmation/risk,
Job, reference protection, or recovery exclusions.

Service Account token possession does not imply target-OS AI permissions, MCP/Plugin identity binding, or recovery authority. Restore, operator/MFA recovery, and protected-secret export remain local CLI/Web authority.

## 4. Surface roles

### 4.1 CLI

The CLI remains:

- the complete local human management surface;
- the complete recovery surface;
- available without Web or Plugin;
- capable of expressing all authoritative 3.0 management state.

A Web-only, Public-Automation-API-only, or Plugin-only authoritative operation is prohibited.

### 4.2 Web

Web is the complete graphical management surface for supported normal administration.
Where an operation is intentionally shell/recovery-only, Web records that classification
in the capability parity ledger.

### 4.3 Public Automation API

The Public Automation API is the supported non-interactive management surface for scripts,
CI/CD, and operator-owned integrations. It is narrower than full local recovery authority
and uses scoped Service Accounts rather than human browser sessions or AI Identity.

### 4.4 Plugin/MCP

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

Recovery authority, operator-security administration, Managed Host admission mutation,
Agent rollout start/resume/rollback, Service Account administration, webhook secret/config
mutation, and other high-risk system lifecycle operations remain outside the default Plugin
surface. DRL3-3 Web system status, redacted certificate status, certificate preflight, and
backup validation are Core-owned OBSERVE/TEST operations and are not new Plugin tools.
Backup validation reuses the canonical restore validator with zero authoritative mutation;
restore itself remains `RECOVERY_AUTHORITY`.

### 4.4 Automation API

Automation API is the supported machine-to-machine management surface. It provides a
subset of Core operations selected by explicit Service Account permissions and the public
Automation API contract. It is never authenticated by Web cookies, never exposes display-
once secrets after issuance, and never creates a second authorization or policy engine.

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
`management-config` for guided Core configuration parity plus
`management-recovery` for local Admin-only recovery authority:

```text
management-read
management-diagnose
management-policy-test
management-temporary-access
management-emergency-cutoff
management-job-observe
management-job-run
management-host-approve
management-update
management-webhook
management-automation-admin
management-access-request
management-config
management-recovery
management-host-approve
management-update
management-automation-admin
management-webhook
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
CLI, Web, Public Automation API, and MCP.

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

Web, Public Automation API, and MCP do not receive special bypasses.

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
| Audit retention status | FULL | FULL | READ | 365/90-day defaults; 500000-event default capacity |
| Audit retention configure/run | FULL | FULL | NO | Admin/local authority; CONTROL-audited, revision-neutral |
| Bulk NDJSON audit export | FULL | FULL | NO | Core-owned 0600 artifact; <=50000 events / 64 MiB; no Web download |
| Temporary Access preview | FULL | FULL | READ | before/at/after expiry semantics |
| Temporary Access set/change/clear | FULL | FULL | CONTROLLED | dedicated management permission |
| Live Access Visibility | FULL | FULL | READ | EXACT / AGGREGATE / UNKNOWN |
| Emergency New-Access Cutoff preview | FULL | FULL | READ | impact and active-session limitation shown |
| Emergency New-Access Cutoff apply/clear | FULL | FULL | CONTROLLED | dedicated high-impact permission + confirmation |
| Active connection termination | COND | COND | NO | P2/conditional; not 3.0 GA blocker |
| Job status/result | FULL | FULL | READ | bounded |
| Safe diagnostic Job start | FULL | FULL | CONTROLLED | only approved job families |
| Managed Host approval/quarantine | FULL | FULL | NO by default | dedicated management-host-approve; pre-approved enrollment supported |
| Managed Update / staged rollout | FULL | FULL | NO | bounded Job; dedicated management-update; no arbitrary package execution |
| Public Automation API / Service Accounts | FULL local administration | FULL administration/status | NO | separate adapter/credentials; management-automation-admin controls principal lifecycle |
| Signed Event Webhook | FULL | FULL | READ status only | dedicated management-webhook for config; Plugin cannot receive signing secret |
| Access Hygiene recommendations | FULL | FULL | READ | derived evidence; never auto-mutates |
| Lightweight JIT request/approval | FULL if stretch ships | FULL if stretch ships | NO by default | P2 stretch; dedicated management-access-request; approval creates Temporary Access |
| Broad/destructive fleet actions | NO | NO | NO | outside 3.0 |
| ConfigurationBundle test/diff | FULL | FULL | READ | no secret distribution |
| ConfigurationBundle apply | FULL | FULL | NO by default | may be separately designed later |
| Backup status/validate | FULL | FULL | READ | no protected archive contents |
| Backup create | FULL | FULL | NO | default Plugin exclusion |
| Restore | FULL | FULL | NO | recovery authority |
| Product/Relay update mutation | FULL | FULL where supported | NO | lifecycle authority |
| Certificate/private-key mutation | FULL | FULL where supported | NO | credential/security authority |
| Web operator / role / per-user MFA policy | FULL | FULL | NO | MFA defaults OFF; Admin toggles policy, user self-enrolls; management-security authority |
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

DRL3-7 keeps audit lifecycle authority local to CLI/Web/Core. Retention defaults are
365 days for CONTROL/SECURITY_LIFECYCLE and 90 days for ACCESS_DECISION with a 500000-event
capacity. Capacity pruning is ACCESS_DECISION-only and never silently removes
CONTROL/SECURITY_LIFECYCLE rows. Manual filtered export is schema-versioned and hard-bounded
to 50000 events / 64 MiB, written mode 0600 under `/var/lib/drlink/audit-exports/`.
Web receives only artifact metadata/path and provides no download endpoint. Plugin/MCP may
query bounded audit but receives neither retention mutation nor bulk export authority.

The Plugin must not:

- fetch arbitrary unbounded history;
- receive protected payloads;
- substitute relay-local logs for authoritative DRLink audit;
- claim a root cause when Core reports UNKNOWN.

### 9.5 Managed Host Approval / Quarantine

CLI/Web own normal approval administration. A pending Host remains visible for review but
is not a normal trusted target. Plugin may read bounded pending/approval status when
`management-read` permits it, but approval mutation is not exposed by default. Pre-approved
enrollment is created only through authorized local/admin automation and remains bound to
the immutable enrollment/Host identity.

### 9.6 Managed Update / Staged Rollout

Rollout is a JOB-class operation with explicit target set, immutable artifact/provenance,
canary/first wave, bounded concurrency, and failure-pause policy. CLI/Web can start and
control the rollout with `management-update`; Plugin is limited to status/diagnosis in
3.0. No adapter may turn rollout into arbitrary command/package execution.

The read-only rollout preview may show a recent authenticated Agent lifecycle
heartbeat from stored inventory. A recent report does not prove current network
reachability, installed binary provenance, a qualified signed update artifact, or
rollback readiness. Neither matching version strings nor heartbeat freshness
may enable Apply; staged rollout remains unavailable until the signed Agent
updater, post-update health checks, and rollback are qualified on the exact
candidate.

Rollout recovery must not interpret an expired Worker lease, server restart,
or missed Job deadline as an Agent update success. Those failures halt further
waves and preserve the failure reason in durable Job state. An already HALTED
rollout or a cancelled rollout with an in-flight target cannot be resumed by
changing its pause flag: the operator must inspect the uncertain Agent outcome
and use a new, independently qualified Change Plan. This rule does not certify
that canonical signed Agent update or rollback execution is implemented.

The internal Linux Agent release preflight accepts only a detached ECDSA P-256
signature over the exact Server-local qualified manifest bytes, verified with
a separate caller-pinned release public key (never the Agent enrollment key or
a key embedded in the manifest). Before any update is eligible for execution,
the signed manifest must bind one unique Linux Agent installer entry, a full
immutable Git SHA, release version/channel, SHA-256 and actual downloaded file
size and digest to the requested rollout target. A PASS label or HTTPS
transport without the independent release signature is insufficient. An
installed-runtime preflight also checks the persisted source/version/bundle
identity and critical Agent module hashes; it must not be reported as a live
health check, update completion, or rollback verification.

This cryptographic validation is an internal prerequisite only. Distribution
of the trusted release verification key, signed artifact publication, an
Agent-owned updater execution/health/rollback path, and real Host qualification
are still required before changing the public fail-closed Apply gate. No
production signing key is generated or stored by this preliminary component;
Windows/macOS platform-specific qualification remains separate. The internal
read-only verifier `python3 lib/drlink_v30_agent_artifact.py --help` accepts
manifest, detached signature, pinned release public key, Agent bundle, exact
source HEAD, version, digest and channel; it never installs or rolls back files
and is not a public `drlink` command.

The Server-side **offline signed candidate stage** builds on the existing
qualified artifact manifest and `SHA256SUMS`, without changing the ordinary
v2.4 update behavior. The release owner signs the **exact manifest bytes**
outside the Server; the offline stage only accepts this pre-existing detached
signature, the independently installed ECDSA P-256 release verification public
key, and its operator-pinned SHA-256 public-key fingerprint. The stage verifies
all existing Server-local artifact hashes plus exact Agent SHA/version/channel
and writes a fresh **unpublished** candidate tree containing
`agent/manifest.sig`. This sidecar is addressable at
`/artifacts/agent/manifest.sig` only **after** a separately approved publish
copies the reviewed distribution to the Server. No private release-signing key
may appear in the repository, Agent payload, Server distribution or stage;
the enrollment/machine identity key never serves as a signing root. Never
infer the trusted release key from bytes downloaded with the candidate.

The internal `lib/drlink_v30_signed_distribution.py` APIs
`stage_signed_candidate` and `verify_signed_server_tree` are offline
tools and have no effect on installed Server artifact directories, HTTP
publication, update authority or Agent lifecycle. Staged file contents,
release-key fingerprint, signing provenance, protected key rotation, the
release-controlled publish step, Agent-owned updater execution, and real
health/rollback must all pass separate qualification before staged rollout
Apply becomes available. This feature does not grant permission to publish
artifacts or provision keys.

The Agent-side read-only network preflight is
`lib/drlink_v30_agent_artifact_transport.py`. Only the canonical enrolled
Server HTTPS origin and persisted enrollment CA may be supplied by its
future Agent lifecycle caller; the Server/Job payload cannot select a new
download origin or signing key. The module fetches exactly
`/artifacts/manifest.json`, `/artifacts/agent/manifest.sig`, and
`/artifacts/agent/bootstrap-client.sh` with bounded TLS-verified GETs.
Redirects, missing signatures, untrusted TLS certificates, key-fingerprint
mismatches, wrong immutable target identities and altered bundle bytes fail
closed. The independent pinned release public key and its expected
fingerprint are installed outside the downloaded artifacts; neither can be
selected from Server-supplied metadata. Successful read-only verification
does **not** persist/download an executable Agent updater, install software,
assert health, or authorize the next rollout wave. The verified candidate
must be re-bound at the authorized Agent-side Apply boundary, followed by
actual runtime/health and rollback qualification.

### 9.7 Public Automation API / Service Accounts

Automation clients authenticate as Service Accounts and receive only their configured
management permissions. The adapter exposes a versioned allowlist of Core capabilities,
uses the same Change Plan/expected-revision/risk classes, and never inherits browser or
MCP authorization. Service Account lifecycle is Admin-only and fully audited.

### 9.8 Signed Event Webhook / Access Hygiene

Webhook configuration is local Admin authority. Delivery contains only versioned,
secret-safe events with stable IDs and signatures; the Plugin may inspect health but never
receives signing secrets. Access Hygiene is OBSERVE-only derived output with evidence
quality and cannot trigger automatic lock/delete/policy mutation.

### 9.9 Lightweight JIT request / approval — P2 stretch

If shipped, requester and reviewer are distinct principals. One Admin Approve/Deny action
may create the same Temporary Access grant already defined by Core. Multi-stage approval,
self-approval, recurring entitlements, external workflow engines, and automatic renewal are
outside the stretch contract. Plugin approval is disabled by default.

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
drlink_access_hygiene
drlink_agent_update_rollout_start
```

Their required permission, operation class, Plugin exposure, input schema, and MCP
annotations are defined by `lib/drlink_management_catalog.py`. The catalog is Core data;
the Plugin relay must pass descriptors through rather than maintaining a copied list.

DRL3-5 activates `drlink_diagnose_connection` as a READY TEST operation. MCP and Web
therefore receive the same bounded side-effect-free correlation result from
`ManagementQueryService`; neither adapter may perform its own probes or diagnosis logic.
The admitted schema remains unchanged. Missing DNS/target/runtime/activity evidence is
reported as UNKNOWN/N/A rather than triggering browser-originated network work.

DRL3-6 activates the already-frozen `drlink_diagnostic_job_start` as a READY JOB
operation without changing the admitted MCP tool list or schema. The operation accepts
only `doctor`, `refresh`, `version-check`, and `support-bundle`, resolves at most 100
trusted immutable Managed Host IDs, and enqueues through the canonical Management Job Engine. Agent workers
claim only their own signed target row and return bounded per-target results. Doctor
disables network probes; refresh uses canonical Agent synchronization; version-check
compares local identity to the Server-pinned product/Relay Engine target carried in the
Job so isolated networks do not require one external version lookup per Host.

Job inspection remains `drlink_job_list` / `drlink_job_get` for MCP. Cancellation and
restart recovery are not new MCP tools: local CLI provides `system jobs`,
`system job <JOB-ID>`, `system job cancel <JOB-ID>`, and `system jobs recover`, while
the first-party Web adapter exposes Core-owned cancel UX to Admin/Operator with
`management-job-run`. Cancelling queued work never implies that already-running Agent
RPC was forcibly terminated.

DRL3-6 also keeps the rest of the safe fleet scope outside new MCP nouns:
`support-bundle` is an admitted value of the existing diagnostic Job operation and
creates sanitized artifacts locally on each Agent; inventory export is a Core-owned
Server read artifact shared by CLI/Web; and fleet description/tag/Managed Host Group
assignment is a Core/Web revision-bound Change Plan. These paths deliberately do not add
generic bulk mutation or arbitrary artifact-download MCP tools.

DRL3-3 adds these Core/Web-only guided configuration operations:

```text
drlink_guided_change_preview
drlink_guided_change_apply
drlink_remote_service_preview
drlink_remote_service_apply
```

They require `management-config`, delegate Managed Host metadata, Object/Group, and
Remote/Internet/AI Access Policy/Rule lifecycle validation and mutation semantics to the existing
Core CRUD/Change Plan path, and use `PLUGIN_NO`. They are therefore available to
the first-party Web adapter when authorized but are **not** added to the admitted
Management MCP/Plugin tool list above.

Managed Host lifecycle is also a first-party Web/Core-only DRL3-3 surface. Local Web Admin
plus `management-config` may preview/apply **trust revoke** or **reference-safe retirement**
through actor/Server/revision-bound Change Plans. Trust revoke requires typed `REVOKE`
and delegates to canonical `remove_client(..., revoke_only=True)`, preserving the Host
inventory record, published services, and active port reservations while preventing the
current management identity from authenticating again. Retirement requires typed `RETIRE`
and delegates to canonical `unset_managed_host`, including reference refusal and exact
owned service/port cleanup impact. Both operations record the actual Web actor/interface;
neither is added to Plugin/MCP.

**DRL3-0 Managed Host admission** is separate from trust revoke and retirement.
The first-party Web API routes /api/v1/managed-hosts/admission/preview and
/api/v1/managed-hosts/admission/apply require local Web Admin **and** the
dedicated management-host-approve permission; management-config alone is not
sufficient. Core issues a 300-second actor/Server/revision-bound Change Plan.
Approve/restore requires typed APPROVE; quarantine requires typed QUARANTINE.
Approval restores normal Remote/Internet/AI policy evaluation rather than
unconditional access. Quarantine denies new Host-bound authorization without
revoking management identity, changing connectivity, deleting references,
releasing services/ports or claiming to terminate established connections.
Core activates revision-bound policy generations and rolls back failed
activation; all applied admission transitions preserve audit attribution.
The Web adapter delegates to Core; no admission mutation is exported as a
Management MCP/Plugin tool or a public Automation API tool in 3.0.

The DRL3-3 Draft Workspace follows the same authority boundary even though Draft CRUD is
Web-only operational state rather than an MCP tool. Browser routes call the Web adapter,
which calls `ManagementCoreService`; the HTTP layer never calls the Draft service or
SQLite directly. ConfigurationBundle **Test** validates through the canonical v2.4
bundle parser/plan engine with zero authoritative mutation. **Diff & Preview** uses that
same engine and issues an opaque Core Change Plan bound to the actor, Server, exact
authoritative revision, Draft ID, and Draft bundle digest. Apply requires that exact
still-pending plan; cross-actor reuse, revision drift, or editing the Draft after Preview
fails closed and requires a fresh Preview. **Export Current** serializes the canonical
redacted Server ConfigurationBundle through the same export engine used by the CLI.
Draft export/copy remains non-authoritative, and Cancel never mutates authoritative
configuration.

DRL3-3 system/lifecycle Web operations also remain Core-owned and are not new Management
MCP tools. System status, certificate preflight, and backup validation are bounded
OBSERVE/TEST behavior. Protected backup creation requires local Web Admin plus
`management-config`; its archive remains server-side under
`/var/lib/drlink/backups/` and is never returned through Web. Sanitized support-bundle
creation requires Admin/Operator plus `management-job-run` and writes only under
`/var/lib/drlink/support-bundles/`. The browser cannot select an arbitrary output path,
archive contents are not exposed, and the authenticated Web actor/interface is propagated
to the canonical tool boundary. Certificate mutation is local Web Admin only and requires
`management-config`: intent configuration uses typed `APPLY`, AUTO_ACME/PRIVATE_CA
issuance uses typed `ISSUE`, USER_CERTIFICATE PEM import uses typed `IMPORT`, and renewal
uses typed `RENEW`. All delegate to canonical `drlink_mcp_tls`; PEM/private-key material
is never returned, imported material exists only in a private ephemeral staging directory,
and Web records the actual actor/interface.

Product and Relay Engine update checks are OBSERVE/TEST-style canonical `--check`
operations available under `management-diagnose`. Relay Engine apply is local Web Admin
only, requires `management-config` plus typed `UPDATE ENGINE`, and delegates to
canonical `frp-update` including rollback/RECOVERY_REQUIRED behavior. Core product
self-update apply remains intentionally unavailable through Web in DRL3-3. DRL3-7 adds
Admin-only typed `UPDATE PRODUCT` through the same Management Core boundary. The request
is queued to a fixed privileged one-shot; Web stops before Core mutation and restarts only
after the canonical updater succeeds and a SHA256-verified Web package proves the same
immutable source ref/HEAD and release channel. Build skew fails closed with recovery
required, and the Web package never becomes a Core dependency.

Restore is local Web Admin-only `RECOVERY_AUTHORITY`, requires
`management-recovery` plus explicit typed `RESTORE`, is restricted to the canonical
backup directory, revalidates the archive immediately before invoking canonical
`frp-restore --yes`, and relies on that engine's pre-restore snapshot/rollback/security-
impact recheck. The Web auth DB connection is reopened after restore, all restored browser
sessions are revoked, and the current session cookie is cleared so restored operational
session state cannot silently resume. Restore is not implied by backup validation or
backup creation and remains absent from Plugin/MCP.

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
MANAGED_HOST_ADMISSION_CROSS_SURFACE=PASS
STAGED_AGENT_UPDATE_AUTHORITY_BOUNDARY=PASS
AUTOMATION_API_CORE_SEMANTIC_PARITY=PASS
AUTOMATION_API_WEB_API_SEPARATION=PASS
SERVICE_ACCOUNT_PERMISSION_ISOLATION=PASS
SIGNED_WEBHOOK_SECRET_EXCLUSION_FROM_MCP=PASS
ACCESS_HYGIENE_READ_ONLY_MCP_PARITY=PASS
```

Exact Plugin acceptance remains separate from direct Core MCP acceptance. A passing direct
MCP test does not prove Plugin relay behavior, and a passing Plugin relay test does not
replace CLI/Web/Core qualification.
