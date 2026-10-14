# UI-06 Two-Person Temporary Access — Security Contract

Status: **OWNER / SECURITY APPROVED FOR UXR-6.2–UXR-6.4 IMPLEMENTATION — 2026-10-14 KST**

Approval record: GitHub Issue #182 ACTIVE Work Packet / roadmap #184. The
approval authority is external to this file; this document remains the frozen
minimal UXR-6.1 contract and does not authorize scope beyond that exact record.

## 1. Existing authority and gap

Current Data Relay Link Temporary Access is a one-actor Core Change Plan:

1. an authenticated actor with management-temporary-access selects an existing
   WHITELIST rule;
2. Core previews temporary-access.set or temporary-access.clear;
3. the same actor types APPLY;
4. Core re-runs required policy safety tests and mutates only canonical rule
   expires_at; the policy evaluator owns expiry.

The current Web UI correctly states that this is not requester/reviewer
approval. UI-06 therefore cannot be a second browser form over those routes.

The retained contracts in MANAGEMENT_SURFACE_CONTRACT.md and
COMPETITIVE_EXPANSION_3_0.md allow only a lightweight one-step request record
over existing Temporary Access. No external workflow engine, new identity
plane, delegation, recurring entitlement, automatic renewal, or multi-stage
approval is permitted.

## 2. Actors and permissions

Requester:
- authenticated local Web Admin or Operator;
- must hold existing management-temporary-access;
- may create a request and inspect/revoke requests they own unless also an
  authorized reviewer;
- creating a request creates no access and no Change Plan.

Reviewer:
- authenticated local Web Admin;
- must hold a new dedicated Core permission:
  management-access-request-review;
- reviewer actor ID must differ from requester actor ID;
- one Admin may approve or deny one pending request;
- no delegation or approval chain;
- Plugin/MCP approval remains disabled.

Read Only cannot request, review, or revoke.

The reviewer permission is intentionally separate from direct Temporary Access
authority so current mutation permission cannot silently become reviewer
authority.

## 3. Eligible target

One request references exactly one existing eligible Temporary Access rule:
- plane is remote, internet, or ai;
- Core resource type is the matching access-rule family;
- current policy mode is WHITELIST;
- the rule exists at request creation and again at review;
- no browser-supplied arbitrary source/destination/service/permission payload
  is persisted as authority.

Core stores only a safe display snapshot. The canonical rule remains policy
authority.

## 4. Purpose, duration and expiry

Requester supplies:
- purpose: required bounded UTF-8 text, 1..500 characters; control and bidi
  characters rejected;
- duration_seconds: integer 300..86400, i.e. 5 minutes through 24 hours.

The request stores duration, not an untrusted browser-computed final expiry.
On approval Core computes approved expiry from trusted decision time.

Reviewer may shorten, never lengthen, the requested duration. Approved duration
must remain 300..86400 seconds. No automatic renewal or recurring schedule.

## 5. Durable Core request state

Add one Core-owned table named temporary_access_requests, never a browser
datastore. Required fields:

- id, opaque tar_ identifier, primary key
- server_id
- requester_actor_id and requester_role
- plane, resource_type, resource_ref
- bounded purpose
- requested_duration_seconds
- approved_duration_seconds, nullable
- requested_revision
- status
- created_at
- reviewed_at and reviewer_actor_id, nullable
- decision_reason, bounded
- approved_expires_at, nullable
- applied_revision, nullable
- revoked_at, revoked_by_actor_id and revoked_revision, nullable
- row_version, integer default 1

Allowed states only:
PENDING, APPROVED, REJECTED, EXPIRED, REVOKED.

No credential, session token, password, Change Plan token, private key, or
arbitrary nested metadata is stored. Index only requester/time and status/time
for bounded lists. No generic workflow queue.

## 6. Request transaction

Creating a request:
1. authenticates requester and permission;
2. resolves current exact rule and WHITELIST mode;
3. validates duration and purpose;
4. captures authoritative revision;
5. inserts PENDING;
6. emits one CONTROL audit event with safe request ID, target, duration and
   requester;
7. performs no policy mutation.

Client uses an immediate in-flight lock. Core rejects a second live PENDING
request for the same requester/plane/resource.

## 7. Review transaction

Approve or Deny is one Core single-writer transaction.

Before deciding Core re-reads and proves:
- request is PENDING;
- reviewer is authorized Admin;
- reviewer differs from requester;
- request server_id matches this Server;
- target is the same rule/resource and still WHITELIST;
- rule/revision is compatible with the request;
- requested and approved duration are bounded.

Deny atomically records REJECTED, reviewer/time/reason and row_version, with no
policy mutation.

Approve:
1. Core computes exact approved expiry.
2. Core builds/revalidates the same Temporary Access safety preview.
3. Required policy regression tests pass and impact is untruncated.
4. Core applies canonical expiry mutation with exact expected revision.
5. Only after confirmed mutation does the request become APPROVED with applied
   revision and expiry.
6. Audit links request, requester, reviewer, target, duration, expiry and
   resulting revision.

Failure cannot display APPROVED. HTTP 200 alone is not success evidence.

## 8. Early revoke and natural expiry

Natural expiry remains owned by the existing Core policy evaluator. No browser
timer changes authorization.

UI-06 also requires early revoke. temporary-access.clear is NOT revoke because
clearing a WHITELIST expiry broadens access.

The approved implementation must add one narrow Core revoke path for an
APPROVED request:
1. verify current request/rule still correspond;
2. authorize the original requester or an Admin reviewer;
3. use canonical policy mutation to move rule expiry to trusted Core current
   time, or the smallest canonical already-expired timestamp supported by the
   frozen temporal contract;
4. re-run policy safety and exact revision checks;
5. record REVOKED, actor/time/revision and audit linkage atomically.

No delete, permanent-expiry clear, Host quarantine, session termination or
unrelated rule mutation is implied.

If canonical policy mutation cannot safely express early revoke without direct
special-case SQL, UXR-6.2 stops for a new security decision. Direct Web SQL is
forbidden.

## 9. First-party API

Web/Core only:
- POST /api/v1/temporary-access-requests
- GET /api/v1/temporary-access-requests with bounded status/limit/cursor
- GET /api/v1/temporary-access-requests/<id>
- POST /api/v1/temporary-access-requests/<id>/review
- POST /api/v1/temporary-access-requests/<id>/revoke

All POSTs retain current HttpOnly-session and CSRF requirements. Lists and
details are fixed-field projections before JSX. No request/review mutation is
added to Plugin/MCP by default.

## 10. Concurrency and replay

- Review/revoke are non-idempotent with immediate client in-flight locks.
- Core transitions use status plus row_version compare-and-update under a
  single-writer transaction.
- Concurrent or repeated approve/deny yields at most one decision.
- Self-review fails.
- Stale rule/revision, malformed receipt, or lost reply never auto-retries.
- Browser reports UNKNOWN and requires authoritative request/policy/Audit
  reread.
- If mutation committed but HTTP reply was lost, retry is forbidden until Core
  state is reconciled.

## 11. Audit

Minimum event families:
- temporary_access.request.created
- temporary_access.request.approved
- temporary_access.request.rejected
- temporary_access.request.revoked

Natural expiry remains evidenced by canonical policy expiry; read model may
derive EXPIRED only from trusted Core time.

Safe fields: request ID, requester/reviewer IDs, plane/resource, bounded purpose
or purpose hash under existing audit redaction, requested/approved duration,
approved expiry and revision. No secrets or browser session identifiers.

## 12. Migration and rollback

Schema/RBAC migration begins only after explicit approval.

Rules:
- additive table/index and reviewer permission only;
- v3 upgrade is transactional; fresh DB gets identical schema;
- repeat migration is idempotent;
- failed migration rolls back;
- downgrade must not pretend request state never existed;
- code rollback requires retained request/audit evidence and no PENDING or
  unexpired APPROVED request that depends on the feature;
- existing management_change_plans, policy rules and current Temporary Access
  semantics are not rewritten by migration.

Private dev tests must cover fresh DB, v3 upgrade, repeat migration, failed
migration rollback and read-only open behavior.

## 13. Mandatory negatives

Test all of:
- requester equals reviewer;
- Operator/Read Only review;
- requester lacks request permission;
- reviewer lacks dedicated review permission;
- wrong request or cross-server ID;
- duplicate create;
- concurrent approve vs deny;
- replay/repeated decision;
- target deleted/renamed/mode changed;
- stale revision;
- reviewer lengthens requested duration;
- past/invalid/unbounded duration;
- failed policy regression or truncated impact;
- lost reply after mutation;
- natural expiry;
- early revoke by requester;
- unauthorized revoke;
- revoke after expiry/revoke;
- restart with PENDING/APPROVED rows;
- audit projection/redaction;
- exact two-user Web proof on one deployed candidate.

## 14. Approval boundary

Approving UXR-6.1 approves this exact scope only:
- one-step, two-person JIT over existing eligible Temporary Access rules;
- new Admin-only management-access-request-review permission;
- one durable Core request table;
- duration 5 minutes through 24 hours;
- reviewer may shorten but not lengthen;
- self-approval denied;
- early revoke via canonical expiry semantics, never clear expiry;
- Web/Core only; Plugin approval disabled;
- no workflow/IAM/delegation/recurrence system.

Any need outside this boundary stops for a new owner/security decision.
