# Data Relay Link Roadmap

> **Status:** Living roadmap aligned to the v2.4.0 Control Plane / Policy / MCP architecture
> **Product Master:** `PRODUCT_MASTER.md`
> **Public model:** `DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`

## 1. Roadmap principle

Finish foundations that would be expensive to replace after stable release. Defer features that can be added later without changing those foundations.

Foundation to finish before v2.4.0 stable:

```text
SQLite authority
immutable Managed Host / Agent identity
Network Objects / Groups
Service Objects / Groups
Permission Objects / Groups
Managed Host address inventory
Agent-owned Remote Services
BLACKLIST / WHITELIST Remote Access policy
deny-by-default WHITELIST Internet Access policy
AI Identity + deny-by-default WHITELIST AI Access / MCP Bridge
revisions / audit
runtime generation
backup / migration
canonical CLI nouns
ConfigurationBundle + shared Change Plan
AI-generated canonical CLI / copy-paste bundle workflow
bounded Zero-Touch issuance (max 10/request and active unused)
short-only Zero-Touch launcher (ZT-P0-CONTRACT-20261026, owner revision 2026-11-24)
```

Can remain later work:

```text
Web UI
central SaaS management
external DB / HA
large-fleet orchestration
SIEM/reporting
broad vendor destination catalogs
```

### P0 — fixed short Zero-Touch entry (OPEN)

1. Replace customer-facing commands with the fixed eight-character root-path entry templates in `ZERO_TOUCH_REGRESSION_CONTROL.md`; same form for public/private HTTPS, no prerequisite or extra fields.
2. Implement locator lifecycle, platform selection, multi-stage downloads and idempotent retry. Keep configuration and all later-stage verification outside the customer command.
3. Establish automatic first-claim enrollment and preserve downstream authentication, artifact integrity and signed service destinations. The initial unauthenticated execution risk is recorded, not a passed security gate.
4. Regenerate artifacts, update structural tests, validate native Linux/macOS/Windows, exact-HEAD CI and real external enrollment/service E2E before qualification.

## 2. Phase DL-0 — proven relay foundation

**Status:** Existing foundation; preserve while redesigning control plane.

Includes:

```text
official fatedier/frp
Zero-Touch / Manual Enrollment
immutable Managed Host / Agent identity
multi-service relay
public-port reservation
Linux/macOS/Windows Agents
lifecycle/update/diagnostics/support bundle
```

Do not fork FRP.

## 3. Phase DL-1 — control-plane architecture closure

**Status:** Architecture approved; docs-first closure in progress.

Required:

```text
CONTROL_PLANE_ARCHITECTURE.md
Product Master alignment
CLI IA alignment
Security alignment
Version/release governance alignment
MCP inclusion decision aligned
```

No stable tag during this phase.

## 4. Phase DL-2 — SQLite control-plane implementation

**Status:** Next implementation phase.

Implement:

```text
/var/lib/drlink/drlink.db
schema_migrations
system_meta
config_revisions
revision_snapshots
audit_events
runtime_generations
```

Required properties:

```text
foreign keys
WAL
synchronous durability
busy timeout
trusted_schema off
transactional mutation
optimistic concurrency
integrity checks
unsupported-schema fail closed
```

## 5. Phase DL-3 — Object and endpoint model

Implement:

```text
objects
object_values
object_group_members
clients
managed_endpoints
endpoint_addresses
client_groups
client_group_members
client_tags
```

Acceptance:

```text
typed Network/Service/Permission Objects and flat Groups
no Source/Destination object duplication
context-valid static Network Objects
reject unsupported nested Groups
context validation
Managed Host lifecycle ownership
no silent identity rebinding
Managed Host local address inventory
reference-protected deletion
```

## 6. Phase DL-4 — Remote Service / Service Object model

Internal storage may retain compatibility table names such as `published_services` and `service_presets`, but they do not define the public model.

Acceptance:

```text
Agent Host owns Remote Service mutation
single destination + one Service Object
TCP and Fixed TCP Remote Service
UDP Remote Service rejected
Relay Host semantics for another-host destination
stable endpoint identity
policy-impact analysis on destination/Service Object changes
Service Object Wizard presets are creation conveniences, not public resources
```

## 7. Phase DL-5 — Remote Access policy

Implement the shared policy infrastructure and the Remote Access BLACKLIST / WHITELIST evaluator/compiler. Internet Access and AI Access reuse infrastructure but have stricter WHITELIST-only semantics.

Acceptance:

```text
Remote Access: No Policy / No Rules = effective ALLOW
Remote Access: BLACKLIST match DENY / no match ALLOW
Remote Access: WHITELIST match ALLOW / no match DENY
rule enable/disable
no rule ordering
no per-rule ALLOW/DENY action
Policy Reset semantics
Enforcement disable/enable
impact analysis
flow test/explain
Remote Service + reachability intersection
```

Only canonical Remote Access policy is public; no alternate legacy policy path.

## 8. Phase DL-6 — Internet Access policy

Replace legacy Internet Profile authoritative policy with Network/Service Objects plus a WHITELIST-only, deny-by-default Internet Access policy model.

Preserve/harden protocol boundary:

```text
HTTP forward proxy
HTTPS CONNECT
server-side DNS
SSRF/special-address protection
DNS rebinding resistance
CONNECT/SNI binding
controlled wildcard semantics
public Host/CIDR explicit policy
Fixed TCP through same authority
resource limits
safe audit
```

Acceptance includes curl/wget/git/apt Real E2E plus denied-traffic escape tests. Release-blocking invariants are: No Policy = DENY, disabled enforcement = DENY ALL, BLACKLIST rejected/fails closed, and only an enabled matching WHITELIST Rule may allow Internet traffic.

## 9. Phase DL-7 — revision/audit/runtime compiler

Implement one mutation pipeline:

```text
validate
→ impact
→ confirm
→ transaction
→ revision/audit
→ compile
→ atomic activate
→ verify generation
```

Acceptance:

```text
system audit
system revisions
runtime revision status
compiler failure surfaced
generation mismatch fail closed where required
```

Rollback may be added only if its semantics are fully transactional and qualified.

## 10. Phase DL-8 — backup / restore / migration

Implement SQLite Online Backup/equivalent consistent snapshot.

Acceptance:

```text
backup during WAL activity
config/trust/secret recovery
restore integrity + FK checks
schema compatibility
runtime regeneration
permissions/ownership
pre-upgrade backup
migration rollback/failure safety
```

Legacy JSON is migration input only, not dual authority.

## 11. Phase DL-9 — MCP Bridge / AI Access

**Status:** Included in v2.4.0 target.

**Current release blocker:** Real ChatGPT owner/UI OAuth Authorization Code/consent, tool discovery, one policy-allowed operation, and one expected policy denial must be retained as release evidence from a plan/surface that officially supports full MCP at evidence-capture time. Machine-side MCP/OAuth conformance is required but does not clear this user-authentication gate by itself.

Implement server-side MCP Bridge plus:

```text
AI Identity backing state
AI Access Rules
Network Object / Network Group targets
Permission Object / Permission Group references
path scopes / exec constraints
AI sessions / activity
```

Targets:

```text
Network Object
Network Group
```

Minimum capabilities:

```text
exec
read_file
write_file
upload_file
download_file
```

Additional discovery:

```text
list_hosts
get_host
get_system_info
list_processes
```

Security:

```text
current official MCP spec
modern supported remote transport
authenticated HTTPS
strong AI Identity binding
per-invocation authorization
least privilege
path scopes
exec timeout/process controls
audit
no per-host MCP server requirement
```

Real interoperability is required for each client explicitly claimed supported. AI Access is release-blocking deny-by-default: authentication alone never authorizes a tool, No Policy = DENY, disabled enforcement = DENY ALL, BLACKLIST is rejected/fails closed, and only an enabled matching WHITELIST Rule may authorize a capability.

### AI Access beginner UX convergence — owner direction 2026-11-25

**Status:** Main integration completed in PR #318 (including #315); source CLI/menu/help/completion, shared MCP setup and separate AI Access Rule workflow implemented. Automated regression and exact installed-product qualification are distinct: remaining Web parity, installed upgrade/rollback and real user E2E must be verified against the exact candidate before release. No stable release qualification is claimed.

Maintain and qualify the canonical [AI Access workflow](AI_ACCESS_MCP.md) and [CLI information architecture](Data%20Relay%20Link%20CLI%20Information%20Architecture.md). Remove competing public command/menu paths, not security controls or persisted state. WBS: (1) reconcile catalog/parser/help/completion, (2) shared MCP setup/readiness wizard, (3) AI Identity onboarding and credential lifecycle, (4) separate AI Access Rule wizard and permission profiles, (5) CLI/Web parity, (6) persisted-state upgrade and failure/rollback, (7) focused regressions, surface reconciliation and real user E2E on exact candidate. Each item requires actual evidence, not document-only PASS.

## 12. Phase DL-10 — canonical CLI implementation

Implement guided root:

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

Direct roots:

```text
show
set
unset
test
system
menu
help
exit
```

Reject retired public resource names; do not retain compatibility aliases:

```text
service-profile
internet-profile
legacy ACL naming
ambiguous generic group
```

Protect impact confirmation, stale edit detection, contextual Tab completion, REPL/shell hints, and backend isolation.

## 13. Phase DL-11 — release governance

Verify consistent feature presence and independent release qualification across:

```text
release manifest schema
manifest generator
version identity validation
release governance scripts
version consistency checks
tests
release manifest content
```

Final candidate truth:

```text
features.mcp_included=true
```

only when the candidate bytes actually contain MCP Bridge and AI Access. Qualification is a separate release gate, not a feature-presence flag.

Keep exact-SHA pretag provenance, immutable tags, source/dist parity, checksums, and historical tag immutability.

## 14. Phase DL-12 — full automated closure

Required:

```text
static validation
DB/migration tests
Object tests
policy evaluator/compiler tests
shadow/impact tests
CLI/PTy tests
Internet security tests
MCP auth/capability/path tests
backup/restore tests
release governance tests
full local suite
CI
source/dist parity
secret/public metadata scan
```

No stale test is allowed to redefine the approved architecture.

## 14.1 Phase DL-12A — ConfigurationBundle and bounded Zero-Touch

**Status:** Required before v2.4.0 stable.

Implement one shared Change Plan path for direct CLI, AI-generated commands, and declarative ConfigurationBundle input.

Required closure:

```text
file + stdin ConfigurationBundle
validate / embedded policy tests / diff
idempotent present + explicit absent semantics
one atomic transaction
revision conflict protection
policy-impact confirmation
redacted export
secret exclusion
AI copy/paste real CLI E2E
CLIENT_ACTION_REQUIRED boundary
Zero-Touch enrollment plans separate from ticket issuance
max 10 tickets per issuance request
max 10 active unused tickets
unique single-use ticket
1h default / 24h max TTL
atomic consumption / double-use denial
```

This phase must reuse the canonical SQLite/domain policy engine; do not add a second YAML/AI state engine.

## 15. Phase DL-13 — multi-host Real E2E

Matrix:

```text
Ubuntu 24
Windows 10
Rocky Linux 8
Rocky Linux 9
Amazon Linux 2023
macOS Apple Silicon
```

Validate install, enrollment, services, policy, Internet Access, lifecycle, reboot, backup/restore, and supported AI/MCP operations.

## 16. Phase DL-14 — final exact-HEAD qualification

Freeze candidate HEAD, then:

```text
FULL_REAL_E2E_PASS_1=PASS
FULL_REAL_E2E_PASS_2=PASS
PASS1_HEAD==PASS2_HEAD
```

Both passes include all three access planes and release lifecycle applicable to stable claims.

Any code/dependency/generated-artifact change resets the counter.

## 17. Phase DL-15 — stable publication

Only after all gates:

```text
create immutable v2.4.0 tag
publish immutable artifacts/checksums/manifest
publish release notes
update stable channel
update public docs
verify clean stable install/bootstrap/update
```

## Cross-release engineering track RCL — repository/worktree/PR consolidation

**Status:** ACTIVE / IN PROGRESS (2026-10-28). **Work Packet:** [#230](https://github.com/datarelay-labs/datarelay-link/issues/230). This is cross-release repository hygiene, **not** an extra v2.4 runtime feature, stable-release PASS, or a new UI WBS. #165 CLI-only/full-user validation, #223 Native MCP, #135 v3, and #182/#184's existing 66 UI WBS retain their independent acceptance requirements. The owner's explicit repository cleanup priority does not revoke active actors or reset their source-bound evidence.

**Initial verified baseline:** 81 registered Git worktrees -> 77 after four clean detached ancestral candidate removals, protected by exact-SHA archive refs and a verified private receipt at `/home/aella/drlink-validation/issue165-main-consolidation-20261028/cleanup-results.json`. The separate RCL implementation worktree adds one temporary registered checkout. Initially 19 open PRs; main is clean at `e8ce7f33e2ea06958172293602d7c9a9bfe669e8`. These are baseline facts, not an assertion that all remaining checkouts are disposable.

| WBS | Work | Acceptance / stop rules | State |
| --- | --- | --- | --- |
| RCL-0 | Current HEAD/worktree/process/PR inventory with cross-reference to existing workspace index and immutable past receipts | Non-secret reproducible JSON, protected owner/dirty/frozen/ignored cases explicitly retained; no assumed clean candidate | COMPLETE: inventory and protected references recorded |
| RCL-1 | Safe reduction of inactive historical worktrees | Each target has fresh exact SHA, no process reference/dirty/ignored/evidence dependency, main ancestor and restorable archive ref; no `--force`, branch deletion, reset or automatic pruning | PARTIAL: five historical/own checkouts removed with archive receipts, others protected |
| RCL-2 | Uncommitted WIP and generated-artifact disposition | Per-worktree change counts, PR owner, diff/status evidence, protected backups; no loss or stealth copy into main | PARTIAL: ten dirty tracked-patch candidates, one exact already on main, nine not exact |
| RCL-3 | Open PR dependency graph and duplicate change classification | All 19 initial PRs classified KEEP / INTEGRATE_LATER / ALREADY_APPLIED / REVIEW_REQUIRED on verified base/head/diff; preserve v3 stacked dependencies; no mass merge/close | PARTIAL: all 19 original PR base/head SHA deltas reconciled; merge decisions pending |
| RCL-4 | Core structure / large-module cleanup after source-bound release-quality convergence | Complexity and responsibility seams measured, narrow compatible adapters, focused RED->GREEN, public/DB/API behavior parity | DEFERRED until #165 appropriate quality boundary |
| RCL-5 | Recurrence prevention | Read-only `tools/drlink-worktree-audit.py` with hermetic negative tests, optional explicitly reviewed cleanup procedure and private restore receipts; no scheduled deletion or product runtime impact | READ-ONLY AUDIT IMPLEMENTED: optional tracked-patch proof added and tested |

**2026-10-28 RCL-2/3 source-bound evidence:** The read-only audit supports explicit `--triage-path <registered-worktree>` checks of dirty tracked changes against a clean, exact base HEAD. It uses `git diff --binary HEAD` and `git apply --reverse --check` without applying, resetting, deleting, stashing or printing patch contents. Even a successful exact-patch result never authorizes deletion of ignored/untracked content or owner/frozen evidence. Ten source-WIP checkouts were inspected: one prior Zero-Touch/LAN seed patch is exactly present on main@ac00ce28; the other nine are not exact. All ten were preserved. GitHub REST exact base/head SHA comparisons confirm the 19 original PR relationships: #178 HEAD is already in main, but #209/#181 are based on its branch; #199 has 5 unique commits and 17 changed files, despite inconsistent summary metadata. Private evidence is retained in /home/aella/drlink-validation/issue230-repository-consolidation-20261028/. Do not merge/close stacked PRs or alter active CLI E2E/MCP/UI sources on this evidence alone.

**Execution sequence:** RCL-0 inventory -> RCL-1 individually validated cleanup -> RCL-2 preserve/diff and classify -> RCL-3 dependency-aware PR reconciliation -> RCL-5 safety tooling -> RCL-4 measured refactors only after the release-quality gate permits. Independent safe stages may overlap; a blocked candidate must not stop inventory or other unrelated safe checks. Existing `/home/aella/datarelay-link-WORKSPACE.md` and 2026-10-27 cleanup receipts remain the continuity baseline; this roadmap and [#230](https://github.com/datarelay-labs/datarelay-link/issues/230) are not competing issue queues.

**Hard limits:** do not disturb live Codex, Native MCP, Web/3.0 or protected frozen runs; never infer deletion eligibility solely from clean status, branch merge or elapsed time. Any ambiguous/active/dirty or ignored file is held for explicit evidence-backed disposition. Production, credential/permission, release and genuinely destructive effects retain their separate authority gates. The RCL audit tool is read-only and its classifications never authorize deletion.

---

## Cross-release performance track LPERF — MCP multi-host and Internet Access CPU spikes

**Status:** PR [#304](https://github.com/datarelay-labs/datarelay-link/pull/304) implementation in progress; integration and exact-candidate qualification outstanding. **Priority:** P0. **Implementation tracker:** [#302](https://github.com/datarelay-labs/datarelay-link/issues/302). No production deployment or release authority is implied. This bounded track covers existing AI Access/MCP and Internet Access planes.

**Operator symptom:** CPU spikes and degraded responsiveness when several Managed Hosts are connected through MCP while the Link Server also handles outbound Internet Access. Actual deployed source HEAD, Bridge worker count, bottleneck, and production capacity have **not** been confirmed. Earlier [AUD-21 MCP dispatch findings](MCP_BRIDGE_DISPATCH_DESIGN.md) are historical evidence only; PR #304 and exact-candidate benchmarks govern current implementation status, not proof of current deployment.

| WBS | Scope | Required result |
| --- | --- | --- |
| LPERF-0 | Read-only source/installed HEAD, topology, Worker count (including `DRLINK_MCP_WORKERS`), CPU cores/RAM and process profiles | Timestamped, source/host-bound baseline; preserve active worktrees |
| LPERF-1 | MCP 1/10/30 concurrent calls across 1/10/30 Managed Hosts, representative 100-Agent fleet | CPU user/system, RSS/PSS, context switches, queue/run/total p50/p95/p99, errors, worker fairness; compare historical 30-call p95 <= 500 ms target on valid topology |
| LPERF-2 | Internet Access HTTP forward/HTTPS CONNECT and applicable Fixed TCP: 10/50/100 connections, churn and throughput | Connection p95, traffic throughput, CPU/socket/DNS/policy bottlenecks, failed/denied traffic receipts |
| LPERF-3 | Simultaneous multi-host MCP + Internet Access workloads on one Server | Isolate cross-plane contention and distinguish CPU hotspots from scheduling, SQLite and network I/O |
| LPERF-4 | Confirm activation of already merged D1–D7 changes before making small measured fixes to bounded concurrency, scheduling, connection reuse and redundant work | Reproducible same-hardware A/B gain; no unbounded resource load, policy/audit change or duplicate command execution |
| LPERF-5 | Owner-selected bounded Rust runtime migration: R1 Internet Access/TCP relay, R2 MCP I/O/dispatch/streaming/backpressure, R3 Linux/macOS executor lifecycle helpers | Keep Python as the only CLI, identity, authorization, policy, DB/job/nonce/audit authority; Go FRP and PowerShell Windows Agent unchanged; locked dependencies, reproducible packaging, fail-closed rollback |
| LPERF-6 | Integrate R1–R3, normative functional/security tests, regression, independent audit/fix/retest, eligible real E2E, load/soak/resource bounds, packaging/rollback and EN/KO docs | Exact-HEAD CI and real surface evidence; preserve SSRF/DNS-rebinding/CONNECT-SNI, revocation, audit, bounds and existing service limits; performance comparisons are not migration gates |

**Current Rust migration checkpoint (2026-11-27):** The owner selected Rust for the previously bounded native runtime scope and superseded conditional adoption and language-benchmark gates. Completed loopback PoC measurements are historical evidence only. R1 has an experimental Rust `cdylib` relay behind the existing Python-authorized socket boundary, plus a Python callback for periodic canonical policy revalidation and an explicit Python rollback mode. Independent review found and drove fixes for unread payload at `POLLHUP` and CPU spinning on inactive hung-up descriptors; focused half-close/backpressure regressions and Rust-selected egress suites pass. R2 has a pinned Rust `cdylib` for atomic bounded MCP dispatch admission, a bounded output window for the existing 1 MiB retention/64 KiB cursor-page contract, and a response writer capped at 64 KiB per callback. Python still owns MCP identity/policy, durable jobs, DB, audit, cursor validation, dispatch, result waits, HTTP/TLS framing, and socket ownership; the Python connection writer supplies backpressure. Rust-selected admission, cursor, and partial-write regressions pass. Inbound/connection I/O and native result-wait integration remain unfinished. R3 integrates bounded Rust stdout/stderr draining for Python-spawned Linux/macOS Agent and Server executors, while Python retains account selection, process creation, input, timeout selection, group termination and reaping. Linux Rust-selected regressions passed: MCP bridge workers 17/17, Server full-control 24/24, Server local executor 8/8, AI Agent/MCP harness 19/19 (external UI E2E NOT_RUN). The Apple Silicon build succeeded but process-capture testing failed during process-group cleanup; a macOS `kqueue` exit observer is under focused revalidation. Python adapters are in bundle inputs, but native shared libraries remain absent from installer bundles; supported-platform qualification, actual gateway E2E, independent review of the remediated candidate and exact-head CI remain pending. Do not describe native shared libraries as packaged or fully qualified.

Reuse `tests/test-mcp-bridge-scale-target.py`, `tests/run-egress-benchmark.py` and current Engineering System acceptance contracts. Do not change production settings, OAuth/AI Access, sensitive secrets, or installed services without applicable separate authorization. Link-chat implementation should proceed from [#302](https://github.com/datarelay-labs/datarelay-link/issues/302) LPERF-0 through LPERF-6 after verifying source and active actor state.

---

## 18. Post-v2.4 demand-driven work

Potential later additions only with real demand:

```text
Web UI
central multi-server/fleet coordination
enterprise identity providers beyond required MCP auth
HA deployment
reporting/SIEM exports
more protocols
more Fixed TCP presets
policy rollback UX enhancements
signed policy/export packages
```

These additions should reuse, not replace, the v2.4 identity/Object/policy/database foundation.

## 19. Stable non-goals

Data Relay Link is not being expanded into:

```text
VPN/full network overlay
SASE/SWG/CASB/DLP
TLS inspection platform
RMM/fleet orchestrator
automatic firewall/DNS manager
large database cluster
```

## 20. Roadmap success condition

The v2.4.0 foundation is done when no further foreseeable core change requires replacing:

```text
control-plane authority
identity model
Object model
plane-specific policy semantics (Remote BLACKLIST/WHITELIST; Internet/AI WHITELIST-only)
Remote Service destination/Service Object semantics
AI Identity / permission authorization model
backup/migration model
canonical CLI nouns
```

Feature growth after that point should be additive.

## Deferred privilege separation hardening

Current v2.4 correctness and qualification take precedence over dedicated service accounts; v2.3.1 was not manufactured. Decision:

```text
ROOT_PRIVILEGE_HARDENING=DEFERRED_WITH_REASON
```

Reason:

Narrowing systemd User=/CapabilityBoundingSet= for drlink-access,
drlink-client (frpc), drlink-server (frps), and the allocator requires
platform-specific installer compatibility validation (Amazon Linux 2 and
older systemd) plus dual-role file ownership audits. Shipping that during
v2.4.0 qualification risks installer/runtime instability for the 1–50 client
target without changing the product contract.

Post-v2.4 follow-up:

- dedicated drlink-access user with narrow write paths
- unprivileged frpc account when supported targets allow
- frps with CAP_NET_BIND_SERVICE only if privileged bind is required
- allocator read-only config/PKI with narrow registry/enrollment write
