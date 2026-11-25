# Data Relay Link — Product Master

> **Document role:** Canonical product charter and product-level specification
> **Status:** Normative living document
> **Target release:** v2.4.0 development; stable qualification pending
> **Primary CLI:** `drlink`
> **CLI/AI SSOT:** `docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`
> **Version governance:** `docs/VERSION_POLICY.md`

Current project version: **2.4.0**

Development builds must display an identity equivalent to `2.4.0-dev+g<shortsha>`
(with exact Source HEAD shown separately), not plain `2.4.0`.
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

Remote Access      — BLACKLIST / WHITELIST
Internet Access    — WHITELIST only, deny-by-default
AI Access          — WHITELIST only, deny-by-default

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

```text
1–5 hosts       extremely simple
10–30 hosts     comfortable CLI operation
30–50 hosts     reusable Objects/Groups are sufficient
100–1000 hosts  not the current product target
```

Do not turn Data Relay Link into a large fleet-management or network-overlay platform merely to match competitor feature lists.

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

Internet Access is WHITELIST-only. If the observed proxy source cannot be proven to be the selected Managed Host, that source selector does not match and access is denied. NAT can therefore make a selective Managed Host source unusable; use an IP/CIDR Network Object representing the proxy-visible source when deterministic NAT-aware policy is required. Persisted unsupported BLACKLIST policy state is denied regardless of rule matches.

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

### v2.4 Custom TCP half-close limitation

Custom TCP remains supported for ordinary bidirectional TCP application traffic and normal connection lifecycle behavior. v2.4 does **not** claim the TCP half-close pattern where a client performs a write-half-close, the target waits for EOF, and the target sends its response only after observing that EOF.

The pinned official Relay Engine, FRP 0.71.0, does not preserve that EOF-driven response through a plain TCP proxy, and Data Relay Link does not fork or patch upstream FRP for this release.

```text
CUSTOM_TCP_HALF_CLOSE=UNSUPPORTED_FRP_0_71_0
```

Protocols that require response-after-EOF half-close semantics are outside the v2.4 Custom TCP support contract. This limitation does not waive real bidirectional Custom TCP traffic, normal close, abrupt disconnect/recovery, endpoint stability, or other applicable release tests.

When destination is another host, the current Agent Host is the Relay Host.

A policy Rule never creates connectivity.

### Zero-Touch default and regression-prevention gate

**ZT-P0-CONTRACT-20261026 — fixed eight-character entry target (owner revision 2026-11-25).** The customer starts with one OS-native command, one HTTPS authority (FQDN or IP), and one eight-character root-path file locator. Public and private HTTPS use the same target form. No preinstalled DataRelay software, inline configuration, separate enrollment ID, fingerprint, artifact hash, or installer body in the customer command. All subsequent configuration, downloads, verification, installation, recovery and enrollment belong to the multi-stage Bootstrap; their size and count are unrestricted. Issuing the command authorizes one automatic registration by the first valid signed Agent claim. Treat the short locator as a sensitive, expiring bearer capability; it is not the downstream enrollment code. See `docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for exact target templates, the automatic first-claim policy, the explicit initial-transport risk and actual acceptance status. This is a design target, not installed-product qualification.

Linux/macOS and Windows must share the fixed entry behavior; the later-stage installer integrity requirement remains. Signed Zero-Touch LAN destinations
must not be projected as Agent `this-host`; Server/Agent destination and
public endpoint must remain authoritative and stable. Unit/CI PASS alone
cannot qualify the installed product: see
`docs/ZERO_TOUCH_REGRESSION_CONTROL.md` for causes, negative tests, and
the real external operator/Agent E2E gates.


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

The three planes intentionally do **not** share the same default-access semantics.

Remote Access preserves the publish-first compatibility model:

```text
Mode        BLACKLIST | WHITELIST
No Policy   ALLOW
Disabled    ALLOW ALL
```

Internet Access and AI Access are privileged/restricted planes and are fail-closed:

```text
Mode        WHITELIST only
No Policy   DENY
No Rules    DENY
No Match    DENY
Disabled    DENY ALL
Unknown/invalid mode DENY
```

For Internet Access and AI Access, authentication or network reachability alone never grants authorization; only an enabled matching WHITELIST Rule can ALLOW. Policy Reset removes Mode and Rules and therefore returns those planes to DENY.

There is no rule ordering and no per-rule ALLOW/DENY action. Remote Access retains its existing BLACKLIST/WHITELIST behavior for v2.4 compatibility.

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

### Beginner-first AI Access UX — target contract (2026-11-25)

This is the single intended UX for the next implementation candidate, not a claim that the installed release already implements it. The [AI Access guide](AI_ACCESS_MCP.md) is the detailed normative workflow; CLI, menu, Web UI, help, completion and tests must converge on this contract. Do not retain alternate public spellings, parallel wizards or duplicate menu entry points for retired UX. Preserve persisted identities, policy, certificates and audit history; no permission widening, implicit trust or silent reconfiguration during migration.

- **Managed Hosts**: register/enroll and manage actual hosts. Never add a host through an AI connection screen.
- **AI Identity**: connect, verify, inspect, reconnect and disconnect an AI client. Authentication alone is not authorization.
- **AI Access Rules**: select Source (verified AI Identity), Destination (Managed Host-backed Network Object / Network Group), and Permission (built-in profile or reusable custom Object/Group), with explicit path and execution constraints. The firewall-style policy is separate from inventory and authentication.
- **System → MCP Server Settings / Certificates**: owns infrastructure. The Connect AI wizard detects readiness and offers the same settings workflow inline when needed, then returns to onboarding. Ready TLS is reused without issuing or reconfiguring a certificate. Direct mode must report the supported single443 prerequisite; no silent deployment-mode switch.
- **Advanced Permissions**: custom Permission Objects/Groups only when needed; not prerequisites for routine onboarding. Read-only grants host-info, process-read and explicitly scoped file-read. Full management offers all seven capabilities only after explicit review of destination, path and OS execution constraints. No automatic root or unrestricted path grant by selecting a label.
- AI Access is WHITELIST-only. The wizard and one-shot Rule grammar require no mode field; first reviewed rule initializes WHITELIST atomically. No Policy, disabled enforcement, unverified/revoked identity, no matching rule or unsafe/unavailable target remains DENY.

First connection: AI Access → Connect AI → select ChatGPT/Claude/Other and name → check endpoint/TLS (fix only if needed) → show public URL and client connection instructions → verify pending OAuth request, explicit operator approval and actual PKCE exchange → optionally open the separate Access Rule wizard with the verified Source preselected. Review destination and permissions before applying; skipping policy setup leaves DENY. The first Owner shortcut is optional and explicitly reviewed: only a verified identity may receive a named audited rule for all trusted hosts, including future signed enrollments **only if the operator explicitly chooses that dynamic scope**, with explicit permissions and path bounds. Otherwise select existing host(s)/group. Never implicitly authorize a new AI because it is first. Subsequent hosts are enrolled under Managed Hosts; a matching dynamic policy needs no AI reconfiguration; other policies remain unchanged until edited. Show effective access and actual connectivity separately.

Normal commands:
```text
set ai-identity
set ai-identity <NAME>
show ai-identities
show ai-identity <NAME>
unset ai-identity <NAME>
set ai-access
set ai-access <RULE>
show ai-access
unset ai-access <RULE>
test ai-access source <AI_IDENTITY> destination <DESTINATION> permission <PERMISSION> [path <PATH>]
show ai-access-log
```
Name-free set opens the relevant guided create/select flow. Named Identity opens onboarding or management; named Rule opens create/edit. AI Identity management contains pending requests, approve/deny, reconnect, authentication method, rotation and revocation; security-sensitive effects require the existing explicit review/authorization, never a duplicate or bypass. System owns `set server mcp` (guided setup), `unset server mcp` (remove route, retain certificate/account material), `unset server mcp purge` (interactive destructive confirmation), certificate lifecycle and `system diagnostics mcp`. The approved one-shot grammar is documented in CLI Reference. Preserve real user OAuth, positive and negative authorization, safe certificate activation/rollback, upgrade state continuity and exact-head E2E release gates.


## 16. Human, AI, and ConfigurationBundle convergence

Three configuration input styles share the same semantics:

```text
Human Guided Wizard
AI complete one-shot CLI
ConfigurationBundle
```

All converge on one Change Plan.

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

These transport/security controls are independent of policy matching, and Internet Access itself is WHITELIST-only and deny-by-default.

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

For v2.4 release closure, these two exhaustive contracts form the primary **product-quality convergence loop**. There is no fixed pass count and no candidate-freeze shortcut:

1. execute the complete CLI Feature/Scenario reconciliation and finish every safe/independent check before remediation;
2. batch-fix every actionable in-scope product, CLI, documentation, usability, or test-contract defect found by that run;
3. rerun the complete CLI Feature/Scenario reconciliation and repeat until it produces no new or unresolved in-scope defect;
4. execute the complete `FULL_USER_E2E` contract and finish every safe/independent scenario before remediation;
5. batch-fix every actionable in-scope defect found by that run;
6. rerun every exhaustive contract affected by those fixes, including the CLI reconciliation when product/CLI/docs changed, and continue the loop whenever a new defect appears.

A finding may be closed only by a verified fix, a deterministic proof that the finding is not a product defect, or an explicit out-of-scope disposition supported by the canonical product contract. Reclassifying a real defect to a lower severity does not satisfy convergence. P0/P1/P2 defects are always blocking; a P3 classified as a real product defect is also fixed before convergence rather than carried into release as known debt.

The convergence loop exits only when the latest complete runs of **both** exhaustive contracts establish all of the following:

```text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FULL_USER_E2E=PASS
NEW_IN_SCOPE_PRODUCT_DEFECTS=0
UNRESOLVED_IN_SCOPE_PRODUCT_DEFECTS=0
UNRESOLVED_ACTIONABLE_USABILITY_FINDINGS=0
PRODUCT_QUALITY_CLOSURE=PASS
NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES
NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES
```

Only after this convergence may the repository freeze the final candidate and spend release effort on exact-HEAD repetition, CI, SBOM, artifacts, provenance, governance, attestation, approval, tagging, and publication. Those release gates remain mandatory, but they do not take priority over finding and fixing product defects while the quality loop is still open.

Critical v2.4 CLI/AI acceptance includes:

- Guided Wizard implementation and Cancel atomicity;
- plane-specific policy behavior: Remote Access BLACKLIST/WHITELIST, Internet Access and AI Access WHITELIST-only deny-by-default;
- Managed Host selector validation;
- Agent-local Remote Service ownership;
- Relay DEGRADED/reconnect behavior;
- Fixed TCP separate pool;
- UDP rejection;
- AI Identity verification;
- Server/Agent Bundle parity;
- runtime rollback and truthful rollback-failure path;
- role-aware help/error discovery.

## 26. Non-goals

Data Relay Link is not:

```text
VPN
full network overlay
SASE/SWG
DLP platform
large fleet orchestrator
Web-UI-first control plane
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
TROUBLESHOOTING.md
```

These guides make existing normative behavior easier to find. They do not override the Product Master, CLI/AI Master, Version Policy, Security specification, or exact release qualification evidence.

## 27. Documentation ownership

```text
DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md
  authoritative CLI/AI public behavior

Data Relay Link CLI Information Architecture.md
  derived menus/discovery/UX

CLI_REFERENCE.md
  derived direct command reference

CONFIGURATION_BUNDLE.md
  derived Bundle contract

CONTROL_PLANE_ARCHITECTURE.md
  internal architecture/schema history; public semantics must remain consistent with the Master

VERSION_POLICY.md / RELEASE_CHECKLIST.md / RELEASE_VALIDATION.md
  version and qualification governance
```

No other document may redefine the public CLI/AI model independently.

## 28. Decision log

### 2026-09 — Final v2.4 CLI/AI model freeze

**Decision:** Adopt the Managed Host + Network/Service/Permission Object + AI Identity + Agent-local Remote Service model; Remote Access retains BLACKLIST/WHITELIST while Internet Access and AI Access are WHITELIST-only and deny-by-default.

**Supersedes:** the intermediate Managed Endpoint / Published Service / Service Preset / ordered first-match ALLOW-DENY / AI Principal public model.

### 2026-09 — Fixed TCP

**Decision:** Fixed TCP is a Service Object subtype. External endpoint allocation occurs when a Remote Service uses it, from a separate Fixed TCP endpoint pool.

### 2026-09 — Context-local Bundle atomicity

**Decision:** ConfigurationBundle atomicity is scoped to the current Server or Agent CLI context, not distributed across contexts.

### 2026-10 — Managed Host Internet source identity under NAT

**Decision:** Keep Managed Host as an Internet Access source selector, but define it as address-backed because Controlled Egress remains agentless. Runtime identity exists only when the observed proxy peer IP matches an eligible active address reported for that Managed Host.

**Security consequence:** Internet Access is WHITELIST-only. When Managed Host source identity cannot be proven, the selector does not match and Data Relay Link denies fail-closed. Persisted unsupported BLACKLIST state is denied regardless of rule matches. NAT-aware deployments that need deterministic source policy should use the proxy-visible IP/CIDR.

**Reason:** Do not invent per-host cryptographic identity for an agentless proxy, and do not let source-identity ambiguity silently broaden access.

## 29. Master rule

Before adding a feature, ask:

> Does this make Data Relay Link better at safely and simply connecting only the services or destinations that are actually needed?

Then preserve:

> **Simple to deploy. Simple to understand. Safe to operate. Lightweight by design.**
