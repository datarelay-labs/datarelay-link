# Data Relay Link 3.0 — Competitive Scope Expansion Contract

> **Status:** Normative 3.0 scope-expansion contract
> **Work Packet:** #179
> **Applies to:** Data Relay Link 3.0 Core, CLI, Optional Web Management, Automation API, Management MCP
> **Purpose:** Close repeated user-expected operational gaps without changing Data Relay Link into PAM, RMM, SASE, or a large-fleet platform.

## 1. Decision

Data Relay Link 3.0 already covers the hard policy, audit, diagnosis, Web, and 100-host
management problems. The remaining high-value gaps are mainly day-2 operational features
that users of mature secure-connectivity products reasonably expect.

3.0 scope is expanded by the following priority:

| Priority | Capability | 3.0 disposition |
|---|---|---|
| P0 | Managed Host Approval / Quarantine | GA Must Ship |
| P0 | Bounded Staged Managed Agent Updates | GA Must Ship |
| P1 | Public Automation API + scoped Service Accounts | GA Must Ship |
| P1 | Signed Generic Webhook Notifications | GA Must Ship |
| P1 | Access Hygiene / Stale Access Review | GA Must Ship, recommendation-only |
| P2 | Lightweight one-step JIT Access Request / Approval | Stretch, non-blocking |

The existing exclusions remain: no SSO/IdP requirement, device-posture/MDM platform,
session recording, browser SSH/RDP terminal, credential vault, broad application discovery,
SIEM platform, HA/multi-region control plane, or hundreds/thousands-host orchestration.

## 2. Competitive basis

The scope expansion follows recurring current product patterns rather than copying any
competitor architecture.

- Tailscale: Device Approval with pre-approved auth keys, scoped OAuth clients, signed
  webhooks, device update visibility and auto-update.
- Teleport: managed Agent updates with ordered groups, canaries, halt-on-error, and
  maintenance-window concepts; time-bounded Access Requests.
- NetBird: public API, service users/tokens, approval workflows, Email/Webhook/Slack
  notifications.
- Twingate: Service Accounts/API, webhook notifications, usage-based access auto-lock,
  and JIT request/approval patterns.
- StrongDM / Boundary / OpenZiti and adjacent products reinforce scoped automation,
  lifecycle visibility, access review, and separation between management identity and
  target-system authority.

Official research references include:

- https://tailscale.com/docs/features/access-control/device-management/device-approval
- https://tailscale.com/docs/features/oauth-clients
- https://tailscale.com/docs/features/webhooks
- https://tailscale.com/docs/features/client/update
- https://goteleport.com/docs/upgrading/agent-managed-updates/
- https://goteleport.com/docs/connect-your-client/request-access/
- https://docs.netbird.io/manage/public-api
- https://docs.netbird.io/manage/settings/notifications
- https://www.twingate.com/docs/usage-based-auto-lock
- https://www.twingate.com/docs/notifications

Research is evidence for operator expectations only. Data Relay Link keeps its own
single-Server + SQLite, official-FRP/no-fork, CLI-recovery architecture.

## 3. Cross-cutting architecture rules

1. **Core remains authority.** Every new capability uses the Core Management Service,
   Change Plan, authorization, revision/audit, Job Engine, and existing Agent ownership.
2. **Web API remains private.** The bundled Web `/api/v1/` contract is not promoted.
   Public automation uses a separate versioned Automation API adapter.
3. **Service Accounts are local machine principals.** They do not require OIDC, SAML,
   LDAP, SCIM, or an external IdP.
4. **Webhook delivery is optional.** Failure to deliver a notification never changes an
   ALLOW/DENY decision, blocks Core startup, or makes relay enforcement unavailable.
5. **Managed updates are bounded jobs.** No generic arbitrary command fan-out and no
   unbounded fleet update/restart primitive.
6. **Access Hygiene is advisory.** 3.0 never silently removes a rule/grant because it
   appears unused or stale.
7. **JIT is additive only if it reuses Temporary Access.** No workflow engine, delegation,
   ticketing integration, recurring schedules, or new identity platform.
8. **All features remain bounded to the qualified 1–100 Managed Host target.**

## 4. P0 — Managed Host Approval / Quarantine

### 4.1 State model

Managed Host admission adds explicit Core-owned state:

```text
PENDING_APPROVAL
APPROVED
QUARANTINED
```

This state is separate from connectivity (`connected/stale/disconnected`) and separate
from management-trust revoke or reference-safe retirement.

- `PENDING_APPROVAL`: enrolled management identity may authenticate enough to report
  bounded identity/health, but the Host cannot authorize Remote/Internet/AI access,
  publish newly usable Remote Services, or claim mutating management Jobs.
- `APPROVED`: normal policy and management behavior applies.
- `QUARANTINED`: existing inventory, identity, policy references, Remote Services, and
  port reservations are preserved, but all new Remote/Internet/AI authorization involving
  that Host fails closed and mutating Agent Jobs are blocked.
- Quarantine does not silently terminate an already-established connection unless that
  plane has separately qualified active-termination support.
- A Zero-Touch enrollment may be explicitly issued as pre-approved by an authorized local
  Admin. Pre-approval is recorded and audited; it is never implied by enrollment alone.

### 4.2 UX acceptance

- Pending Hosts are visible at the top of Managed Hosts and in Attention Center.
- Pending/quarantined state is visually distinct from offline/disconnected state.
- Approve, Quarantine, and Restore-to-Approved show an impact preview.
- Quarantine explains that normal policy is preserved and only the admission override is
  changing.
- Web never calls quarantine "delete", "revoke", or "retire".
- Guided enrollment offers an explicit Admin-only **Pre-approve this enrollment** option,
  default OFF.

### 4.3 CLI acceptance

3.0 additive grammar must provide discoverable equivalents for:

```text
show managed-host <HOST> admission
set managed-host <HOST> admission approved
set managed-host <HOST> admission quarantined
set enrollment zero-touch ... pre-approved
```

Exact flag spelling may be frozen during DRL3-0 grammar work, but the semantic operations
above are required. Approval/quarantine is revision/audit bound and requires explicit
impact confirmation. Existing revoke/retire commands remain separate.

### 4.4 Web acceptance

- Managed Host list filters: Pending Approval / Approved / Quarantined.
- Detail view shows actor, timestamp, reason where supplied, and recent admission audit.
- Admin can Approve, Quarantine, or Restore with Change Plan preview.
- Operator/Read Only cannot grant admission authority unless explicitly mapped by the
  frozen RBAC contract.
- Pre-approved enrollment issuance is Admin-only and display-once credential semantics
  remain unchanged.

### 4.5 Automation API / MCP acceptance

- Automation API may read admission state with `management-read`.
- Admission mutation requires dedicated `management-host-approve`; it is never implied
  by general configuration write access.
- Management MCP/Plugin may observe admission state through normal inventory tools.
- 3.0 Plugin/MCP does **not** expose approval/quarantine mutation by default.

### 4.6 Required evidence

```text
HOST_PENDING_CANNOT_AUTHORIZE=PASS
HOST_PREAPPROVED_ENROLLMENT_AUDITED=PASS
HOST_APPROVAL_ENABLES_NORMAL_POLICY=PASS
HOST_QUARANTINE_DENIES_NEW_ACCESS=PASS
HOST_QUARANTINE_PRESERVES_POLICY_REFERENCES=PASS
HOST_ADMISSION_NOT_CONNECTIVITY_STATE=PASS
HOST_ADMISSION_NOT_TRUST_REVOKE_RETIRE=PASS
```

## 5. P0 — Bounded Staged Managed Agent Updates

### 5.1 Scope

3.0 adds a manual, bounded rollout controller over the existing rollback-capable Agent
update path.

Minimum rollout input:

```text
immutable qualified target build
bounded Host selector / Managed Host Group
canary count
batch size / concurrency
halt-on-failure = true by default
```

3.0 does not add recurring schedules, arbitrary OS patch management, arbitrary software
deployment, or a generic RMM command runner.

A rollout is a Management Job with per-target states and durable progress. Each target
uses the canonical verified Agent updater and keeps identity/state preservation and
rollback semantics.

- **Default failure threshold = 0%**: halt upon the first failed target. A
  nonzero threshold is an explicit operator-selected tolerance; Canary failure
  always halts regardless of the selected percentage.
- Canary and ordinary Host groups are divided into fixed-size deterministic
  batches. A new batch may start only after **every Host** in the preceding
  batch has a terminal outcome and the failure policy has been evaluated.
  Completed Hosts do not create sliding-window capacity for the next batch.
- Preview displays the exact planned batch membership and remains read-only.
  Signature, running-Agent Health, real Rollback and release qualification
  must be independently verified before enabling any live Apply.

### 5.2 UX acceptance

- Update Center shows current/target version, provenance, update availability, and drift.
- Preview lists exact targets and canaries before Apply.
- Canary success is required before the remaining batch proceeds.
- Any canary/update verification failure halts further rollout by default.
- Operator can pause, resume, or cancel queued future targets.
- Already-running target work is never falsely reported as forcibly cancelled.
- Failed target shows rollback result and recovery guidance. Until an
  independently qualified live Agent update/rollback reports trusted evidence,
  the Job Detail read model must explicitly show **NOT_VERIFIED** for signed
  update, post-update Agent Health and rollback, even if Job target rows say
  SUCCEEDED. Halted or failed targets require clear operator reconciliation
  guidance. This read-only view must not grant public rollout Apply authority.
- No "Update All" action exists without bounded target preview and concurrency limits.

### 5.3 CLI acceptance

Required discoverable semantics:

```text
system update agents check
system update agents preview <selector> [canary N] [batch-size N]
system update agents apply <PLAN-ID>
system job <JOB-ID>
system job cancel <JOB-ID>
```

The final grammar may reuse existing Job nouns, but preview/apply binding to the immutable
target build and target set is mandatory.

### 5.4 Web acceptance

- Administration / Updates provides Update Center and rollout wizard.
- Admin selects bounded target set, canary count, and batch size.
- Web shows per-target Job progress and halt reason.
- Resume requires explicit acknowledgement after a failed canary/batch.
- Rollback status is shown per Host where canonical updater rollback was required.
- Web never upgrades Server/Core as a side effect of an Agent rollout.

### 5.5 Automation API / MCP acceptance

- Automation API may preview/start/status/cancel a rollout only with
  `management-update`.
- API requires idempotency protection for rollout creation/start.
- Plugin/MCP can observe rollout Job status through existing Job tools.
- Plugin/MCP does not start, resume, or rollback Agent rollouts in 3.0.

### 5.6 Required evidence

```text
AGENT_UPDATE_IMMUTABLE_TARGET=PASS
AGENT_UPDATE_CANARY_GATE=PASS
AGENT_UPDATE_HALT_ON_FAILURE=PASS
AGENT_UPDATE_BOUNDED_CONCURRENCY=PASS
AGENT_UPDATE_STATE_IDENTITY_PRESERVED=PASS
AGENT_UPDATE_ROLLBACK_TRUTHFUL=PASS
AGENT_UPDATE_NO_GENERIC_RMM=PASS
```

## 6. P1 — Public Automation API + scoped Service Accounts

### 6.1 Architecture

Public automation is a separate adapter:

```text
automation client
  → /api/automation/v1/
  → Automation API adapter
  → Core Management Service
```

It does not expose or stabilize the bundled Web `/api/v1/` contract and does not route
through the Plugin relay.

Service Accounts are non-interactive Core principals with:
- immutable identity;
- explicit management-permission set;
- optional resource/selector restrictions where the Core permission model supports them;
- one or more revocable tokens;
- optional token expiry;
- last-used metadata and audit attribution.

Tokens are generated with cryptographic entropy, display-once, stored only as a verifier/
hash, and cannot be recovered from Web/CLI/API after issuance.

### 6.2 API acceptance

The public Automation API must provide:
- explicit versioning;
- bounded list/query pagination;
- stable machine-readable errors;
- current-revision preconditions for authoritative mutation;
- Change Plan preview/apply for security-relevant changes;
- idempotency keys for create/apply/job-start operations where replay could duplicate work;
- request/audit correlation IDs;
- bounded rate/resource limits;
- secret-safe responses and logs;
- the same Core authorization and fail-closed semantics as CLI/Web/MCP.

The API is not required to provide every local recovery/security operation. Restore,
operator/MFA recovery, protected secret export, and equivalent `RECOVERY_AUTHORITY`
remain local CLI/Web authority.

### 6.3 CLI acceptance

Required local lifecycle semantics:

```text
show service-accounts
show service-account <ACCOUNT>
set service-account <ACCOUNT> permissions <...>
system credential issue service-account <ACCOUNT> [ttl]
system credential rotate service-account <ACCOUNT>
unset service-account <ACCOUNT>
```

The final grammar may be normalized during the CLI design gate, but must preserve:
display-once secret issuance, explicit permission assignment, rotate/revoke, expiry/status,
last-use/audit visibility, and no secret recovery.

### 6.4 Web acceptance

Administration / Service Accounts provides:
- list/detail with permissions, token count, expiry, last used, last actor/event;
- create account;
- issue/rotate/revoke token with display-once secret;
- copy-once warning and no later reveal;
- explicit permission preview;
- no interactive browser login as a Service Account.

### 6.5 MCP acceptance

Service Accounts are **not** AI Identities and do not inherit Management MCP access.
Management MCP remains authenticated/authorized through the MCP identity model.
MCP may read non-secret Service Account health/count only if explicitly admitted later;
3.0 does not need Service Account administration tools.

### 6.6 Required evidence

```text
AUTOMATION_API_SEPARATE_FROM_WEB_API=PASS
AUTOMATION_API_CORE_SEMANTIC_PARITY=PASS
SERVICE_ACCOUNT_NON_INTERACTIVE=PASS
SERVICE_ACCOUNT_TOKEN_DISPLAY_ONCE=PASS
SERVICE_ACCOUNT_TOKEN_HASHED_AT_REST=PASS
SERVICE_ACCOUNT_SCOPE_ENFORCEMENT=PASS
SERVICE_ACCOUNT_ROTATE_REVOKE=PASS
AUTOMATION_API_CHANGE_PLAN_PARITY=PASS
AUTOMATION_API_IDEMPOTENCY=PASS
AUTOMATION_API_AUDIT_ATTRIBUTION=PASS
```

## 7. P1 — Signed Generic Webhook Notifications

### 7.1 Scope

3.0 provides one generic outbound HTTPS webhook sink rather than separate Slack/Teams/
Email implementations.

Candidate event families include:
- Managed Host pending approval / quarantined / stale;
- Remote Service degraded;
- repeated meaningful policy deny;
- Temporary Access near expiry/expired;
- Emergency Cutoff activation/recovery;
- certificate/backup/update readiness;
- failed Management Job or staged update halt;
- audit spool/high-water degradation;
- Access Hygiene findings.

Webhook delivery uses a versioned JSON event envelope and stable event ID. Each delivery is
signed with a per-endpoint secret using an authenticated construction such as HMAC-SHA256
over timestamp + event ID + payload.

### 7.2 Delivery rules

- HTTPS only by default.
- Secret is display-once and rotatable.
- Bounded local queue/spool.
- Exponential backoff with hard retry/time/queue limits.
- Duplicate delivery is possible and consumers dedupe by event ID.
- Delivery failure creates local Attention but does not block enforcement, Core mutation,
  startup, backup, or CLI recovery.
- Payload reuses secret-redaction rules and contains no credentials/application payload.
- Test delivery is explicit and separately audited.

### 7.3 CLI acceptance

Required semantics:

```text
show webhooks
show webhook <NAME>
set webhook <NAME> endpoint <HTTPS-URL> events <...>
system credential rotate webhook <NAME>
test webhook <NAME>
unset webhook <NAME>
```

### 7.4 Web acceptance

Administration / Notifications provides:
- endpoint list/status;
- event-family selection;
- enable/disable;
- secret rotation;
- test delivery;
- last success/failure and next retry;
- bounded backlog indicator.

Email/Slack/Teams remain later adapters that may consume the same event boundary.

### 7.5 Automation API / MCP acceptance

- Automation API may read/configure/test webhooks only with
  `management-webhook`.
- Plugin/MCP may read Attention state that reflects webhook delivery degradation.
- Plugin/MCP does not receive webhook secrets or configure webhook endpoints in 3.0.

### 7.6 Required evidence

```text
WEBHOOK_SIGNED_DELIVERY=PASS
WEBHOOK_VERSIONED_EVENT=PASS
WEBHOOK_SECRET_DISPLAY_ONCE=PASS
WEBHOOK_RETRY_BOUNDED=PASS
WEBHOOK_DUPLICATE_EVENT_ID_STABLE=PASS
WEBHOOK_FAILURE_NOT_ENFORCEMENT_DEPENDENCY=PASS
WEBHOOK_SECRET_REDACTION=PASS
WEBHOOK_TEST_AUDITED=PASS
```

## 8. P1 — Access Hygiene / Stale Access Review

### 8.1 Scope

Access Hygiene turns existing Audit + Effective Access Graph data into bounded, read-only
recommendations.

3.0 may classify:
- access grant/rule with no observed successful use during the configured review window;
- object/group/policy reference with no remaining reachable relationship;
- long-offline Managed Host still referenced by policy;
- expired Temporary Access residue that is no longer enforcement-relevant;
- stale Service Account token;
- credential/certificate nearing expiry where action is required.

It must distinguish:

```text
STALE_OR_UNUSED
ORPHANED
ACTION_REQUIRED
UNKNOWN_EVIDENCE
```

No finding automatically changes policy, revokes access, disables a Host, or deletes an
object.

### 8.2 Evidence-quality rules

- "Unused" is claimed only when retained audit coverage spans the entire review window.
- Missing/lagged/pruned audit becomes `UNKNOWN_EVIDENCE`, never "unused".
- Aggregated visibility is not promoted to exact per-identity usage.
- Review thresholds are bounded operator settings and are audited.

### 8.3 CLI acceptance

Required semantics:

```text
show access-hygiene
show access-hygiene <FINDING>
test access-hygiene
```

Any proposed remediation links to the normal existing Change Plan operation rather than
creating an auto-cleanup command.

### 8.4 Web acceptance

Operations / Access Hygiene provides:
- severity/type/age/resource filters;
- evidence window and evidence-quality label;
- direct links to policy/object/Host/Service Account detail;
- "Preview remediation" only through the canonical Change Plan of the affected resource;
- dismiss/snooze as operational preference only, never authoritative access state.

High-confidence findings also appear in Attention Center.

### 8.5 Automation API / MCP acceptance

- Automation API exposes bounded read-only hygiene results under `management-read`.
- Management MCP adds one read-only tool: `drlink_access_hygiene`.
- MCP can explain findings but cannot auto-apply a remediation.
- Any mutation follows the existing resource-specific controlled operation.

### 8.6 Required evidence

```text
ACCESS_HYGIENE_READ_ONLY=PASS
ACCESS_HYGIENE_AUDIT_WINDOW_PROVEN=PASS
ACCESS_HYGIENE_UNKNOWN_WHEN_EVIDENCE_INCOMPLETE=PASS
ACCESS_HYGIENE_NO_AUTO_REVOKE=PASS
ACCESS_HYGIENE_CORE_WEB_API_MCP_PARITY=PASS
```

## 9. P2 Stretch — Lightweight one-step JIT Access Request / Approval

This is explicitly **not a 3.0 GA blocker**.

It may ship only if it can be implemented as a thin request record over the existing
Temporary Access grant and current authenticated principals.

Maximum 3.0 stretch scope:
- requester selects an existing eligible Temporary Access target/template;
- supplies reason + bounded duration;
- one authorized reviewer approves or denies;
- approval materializes the normal Temporary Access grant;
- expiry/enforcement/audit remain exactly the existing Temporary Access implementation;
- request/decision status visible in Web/CLI and optionally by signed webhook.

Not allowed:
- multi-stage approval chains;
- delegation/escalation engine;
- recurring/auto-renew access;
- Jira/ServiceNow dependency;
- new enterprise identity/governance subsystem;
- approval that bypasses policy evaluation or Change Plan semantics.

If implementing this slice requires a new identity plane, workflow engine, or FRP changes,
defer it to later 3.x.

## 10. Phase placement

```text
DRL3-0
  freeze admission state, Automation API/service-account auth, webhook envelope/signing,
  access-hygiene evidence rules, staged-update risk/rollback contract

DRL3-1
  Core schema/query/auth primitives for Host admission, Service Accounts,
  Automation API adapter, webhook queue/event boundary, hygiene read model

DRL3-2
  read-only Web visibility for admission, update drift, Service Accounts,
  notification delivery health, hygiene findings

DRL3-3
  Host approval/quarantine mutations, pre-approved enrollment,
  Service Account/token administration, webhook endpoint administration,
  public Automation API v1 contract

DRL3-4
  admission/quarantine and hygiene findings participate in preview/graph/explain;
  existing Temporary Access remains JIT substrate

DRL3-5
  Access Hygiene + Attention integration; webhook event production/delivery health

DRL3-6
  bounded staged Agent update rollout using Job Engine; canary/halt-on-failure

DRL3-7
  hardening, rate/resource limits, queue recovery, token/webhook secret lifecycle,
  mixed-load qualification

DRL3-8
  exact-candidate cross-surface and 100-host acceptance
```

## 11. 3.0 final priority boundary

### Must ship

```text
Managed Host Approval / Quarantine
Bounded Staged Managed Agent Updates
Public Automation API + scoped Service Accounts
Signed Generic Webhook Notifications
Access Hygiene / Stale Access Review
```

### Stretch, not release-blocking

```text
Lightweight one-step JIT Access Request / Approval
```

### Remains later/out

```text
SSO/OIDC/SAML/LDAP/SCIM
multi-stage JIT governance
device posture / MDM
session recording / browser terminal
credential vault
generic RMM / arbitrary software deployment
SIEM platform / payload inspection
HA / multi-region
large-fleet orchestration
```

This expansion is intentionally operational rather than architectural: it adds the missing
day-2 controls users expect while preserving the Data Relay Link product identity.
