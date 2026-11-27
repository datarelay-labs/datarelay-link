# Data Relay Link — MCP Server Settings and AI Access

> **Status:** owner-approved target execution-account redesign (2026-11-27); implementation and installed-runtime qualification are pending.
> **Authority:** Public CLI semantics come from the CLI/AI Master; security and transport boundaries come from `SECURITY.md`.

## 1. Model

### MCP Server Settings and AI Access workflow

This is the candidate UX contract, not a claim of installed release qualification. This guide is the detailed normative workflow; CLI, menu, help, completion and tests must converge on this contract; any Web UI consuming these functions must follow the same design. Do not retain alternate public spellings, parallel wizards or duplicate menu entry points for retired UX. Preserve persisted identities, policy, certificates and audit history; no permission widening, implicit trust or silent reconfiguration during migration.

- **Managed Hosts**: register/enroll and manage actual hosts. Never add a host through an AI connection screen.
- **MCP Server Settings** (`set mcp-server`): one Configure endpoint, TLS and Server execution flow plus Diagnostics. Reuse valid TLS; prepare or review local executor ceiling and eligible existing accounts; no AI grant is created.
- **AI Identities** (`set ai-identity`): connect, verify, reconnect and manage credentials. Authentication alone is not authorization.
- **AI Access Rules**: select verified Source, Destination (existing host, trusted group/dynamic scope or explicitly selected `server:self`), Permission, allowed execution accounts and default, and direct-file paths. Account selection is part of the same reviewed rule, not an independent grant.
- **MCP Server Settings** uses shared System infrastructure, reuses ready TLS, and checks actual readiness. Offer the same AI Access wizard after connection; show and validate the local executor ceiling inline, using explicit local review when needed. Direct mode retains the single443 prerequisite. No silent deployment-mode switch; diagnostics without live evidence are NOT TESTED.
- **Advanced Permissions**: custom Permission Objects/Groups only when needed. Read-only grants host-info, process-read and scoped file-read, never shell. Full management supports selected existing OS accounts, including explicitly approved root, with direct-file paths defaulting to `/**` only on a new explicitly reviewed full-management rule. No automatic root grant.
- AI Access is WHITELIST-only. The wizard and one-shot Rule grammar require no mode field; first reviewed rule initializes WHITELIST atomically. No Policy, disabled enforcement, unverified/revoked identity, no matching rule or unsafe/unavailable target remains DENY.

First connection: MCP Server Settings (endpoint, TLS and local execution readiness) → AI Identity: connect ChatGPT/Claude/Other → complete verified OAuth/PKCE or supported credential workflow → open the named Access Rule with Source preselected → choose Destination, Permission and execution accounts/default (for management), review effective paths and OS authority → apply once and verify. Skipping the rule leaves DENY. The optional first-owner shortcut is only an explicitly reviewed rule, not a special trust mechanism. Existing hosts are the default; future trusted group members require explicit dynamic scope and their own compatible local execution approval. No automatic root authorization merely from future enrollment. Removing trust/group membership withdraws applicable grants. Subsequent AI connections reuse infrastructure, not other identities' grants.

The guided Rule destination picker lists enrolled Managed Hosts (including offline), Network Groups containing Managed Hosts, explicit Managed Host Groups, reviewed all-trusted scope and This Server. Routed LAN Network Objects (including `enrolled-target-*`) are not AI executors; preserve their Remote Service references. Local execution setup reviews eligible OS accounts and optional nonprivileged workspace but does not grant AI access. The rule chooses an authorized default and subset. If entered from the rule, present local approval and rule together without re-entering identical values; no automatic privilege expansion.

Normal commands:
```text
set mcp-server
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
`set mcp-server` opens MCP Server Settings; `set ai-identity` opens the single connection/authentication wizard; `set ai-access` opens named Rule creation/editing. Named Identity opens onboarding or management; named Rule opens create/edit. Reusing a Rule name replaces selected Source/Destination rather than adding a second Rule. File permissions require absolute path scopes such as `/**`, `/home/**` or `/home/**,/opt/**`; command execution is not a filesystem sandbox. `show ai-identity <NAME>` lists its configured rules; `unset ai-access <RULE>` deletes only that rule, while `unset ai-access policy` resets all rules after confirmation. Cancellation preserves policy. AI Identity management contains pending requests, approve/deny, reconnect, authentication method, rotation and revocation; security-sensitive effects require the existing explicit review/authorization, never a duplicate or bypass. Explicit TLS intent uses `set mcp-server <SETTING> <VALUE>`; MCP Server owns `unset mcp-server` (remove route, retain certificate/account material), `unset mcp-server purge` (interactive destructive confirmation), certificate lifecycle and `system diagnostics mcp`. The approved one-shot grammar is documented in CLI Reference. Preserve real user OAuth, positive and negative authorization, safe certificate activation/rollback, upgrade state continuity and exact-head E2E release gates.


```text
Authentication
→ establish verified AI Identity

AI Access
→ decide which destination and permission that identity may use

MCP Bridge
→ integration/transport layer
```

MCP does not create a separate public identity model. Managed Host tools accept the exact name or full Client ID returned by `list_hosts`; prefixes and ambiguous identifiers fail closed. Both identifiers use the same existing AI Access rules. Server-self is separately controlled and must be explicitly enabled. Agent connectivity does not imply AI executor readiness. Windows Agent lifecycle support alone does not establish AI executor readiness. The Windows native executor reuses authenticated claim/complete transport with mandatory response HMAC. It remains disabled unless the local operator explicitly opts in using a protected execution-account profile. The signed claim records the Windows path dialect; native file paths use drive-qualified paths (for example `C:/Data/**`), and `/**` is the explicit all-file policy scope. The local allowed roots intersect with the Server Rule scope. UNC/device paths, traversal, streams, reparse points and multiply linked files are rejected. Native Windows and enrolled-host qualification remain separate from implementation. Installed Windows upgrades harden the product code-tree ACL without widening OS ancestors or changing identity/state; see [WINDOWS_CLIENT.md](WINDOWS_CLIENT.md).

## 2. Connect and authenticate an AI Identity

Use `set mcp-server` for MCP Server Settings (Configure endpoint, TLS and Server execution; Diagnostics). Use `set ai-identity [NAME]` to connect or manage an AI Identity and review pending requests. Authorization is separately managed by `set ai-access`.

```text
AI Identity
```

Examples:

```text
chatgpt
claude
cursor-dev
custom-ai
```

A display name alone is not trusted identity.

Existing action-first Server CLI resource command:

```text
set ai-identity <NAME>
```

Interactive AI uses OAuth Authorization Code verification where supported.

Automation/custom AI may use OAuth Client Credentials where supported.

The exact public MCP/OAuth endpoint design and host interoperability must remain consistent with `SECURITY.md` and exact-HEAD qualification evidence.

Operator credential / OAuth lifecycle:

```text
set ai-identity <IDENTITY> rotate
set ai-identity <IDENTITY> revoke
set ai-identity <IDENTITY> authentication <static-bearer|oauth>
set ai-identity <IDENTITY> oauth-redirect <URI>
set ai-identity <IDENTITY> approve <PENDING-ID>
set ai-identity <IDENTITY> deny <PENDING-ID>
```

Credential rotate/revoke/configure are security-sensitive authentication changes; revoke can interrupt active clients. OAuth approve is an explicit authorization decision that can widen access, while deny rejects the pending authorization. These explicit commands are themselves operator approval and do not add a second confirmation prompt.

Public MCP is served only through the `single443` HTTPS frontend. `direct` deployment mode uses its public control port for the FRP listener and therefore must not advertise or activate `https://<host>/mcp`; `set mcp-server` and certificate mutation commands fail closed until the Server is reconfigured to `single443`. The supported transition is to re-run the Data Relay Link Server installer from the same immutable release/source ref with `FRP_DEPLOYMENT_MODE=single443`, confirming the cutover by typing `SWITCH` on a TTY or setting `FRP_CONFIRM_MODE_SWITCH=yes` for a non-interactive run. A stale TLS intent or certificate from an earlier configuration does not make Direct mode MCP-capable.

For a single443 Server with an explicitly configured MCP TLS hostname and mode, that hostname is the canonical `https://<MCP-HOSTNAME>/mcp` origin for OAuth issuer, discovery, registration and token exchange. The configured MCP hostname is the authoritative public origin; do not expose a competing public configuration path. After a hostname change, inspect `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/mcp` through the externally reachable MCP HTTPS hostname; the issuer, registration endpoint, token endpoint and protected resource must all match the routed, certificate-valid FQDN. Internal loopback discovery checks do not substitute for the external client test.

### First-time ChatGPT OAuth connection (DCR / CIMD)

On a fresh DRLink Server, there may be no existing AI Identity. The first
remote OAuth authorization must **not** require a pre-existing VERIFIED
identity (that would make initial onboarding impossible).

1. Add the public `https://<MCP-HOSTNAME>/mcp` endpoint in the supported
   ChatGPT MCP connection UI; this opens an OAuth request.
2. Copy the Pending request ID (oap_...) displayed on the browser consent page and paste it into the Pending request ID prompt in `set ai-identity`. Review the client, redirect origin, requested resource and scope before approving. Alternatively, on the **DRLink Server** run:

   ```text
   set ai-identity chatgpt approve <PENDING-ID>
   ```

   For a previously absent AI Identity, this explicit action creates only
   an **enabled PENDING** identity and binds the requested client to it. It
   does not grant VERIFIED trust or bypass consent. Existing disabled,
   revoked or otherwise unverified identities remain ineligible.
3. After CLI approval, select the OAuth browser page's **Retry** link. The one-time code
   is delivered only to the originally registered redirect. Only a valid
   authorization-code exchange with matching client, redirect URI, resource
   and PKCE verifier transitions the new identity to VERIFIED. A wrong
   verifier, expired/replayed code or revoked identity cannot do so.
   If the operator approves a newer request for this same still-PENDING
   first identity, the superseded authorization code is invalidated and
   cannot later acquire trusted access.
4. The verified identity remains DENY until the operator reviews and applies a separate Access Rule. The wizard may preselect the verified source and offer an explicit Owner profile as described above; no policy is created if the operator skips this step.

This flow permits first-time OAuth onboarding without using a private
registration database edit, fabricated credentials or an automatic
operator-approval bypass.

### v2.4.0 release status

MCP Bridge is included in the v2.4.0 target. The current stable-release blocker is the real ChatGPT owner/UI authentication path on a plan/surface that officially supports full MCP at evidence-capture time, not MCP protocol implementation itself.

The release gate requires retained owner/UI evidence that a real user on a currently supported ChatGPT full-MCP plan/surface can:

1. connect to the public Data Relay Link MCP endpoint;
2. complete OAuth Authorization Code and consent successfully;
3. discover the expected MCP tools;
4. execute one operation that current AI Access policy allows; and
5. receive a policy denial for one intentionally out-of-scope operation.

Machine-side OAuth discovery, token exchange, MCP initialize, tools/list, and direct allow/deny tests remain required evidence, but they do not replace this real-user acceptance gate.

## 3. Permission Objects

The normal Rule wizard offers built-in Read-only, Full management, and Custom choices. Built-in choices resolve to deterministic reusable permission objects, with path scope shown and reviewed separately on the Rule. No separate Permission Object creation is required for built-ins. Custom Objects/Groups remain advanced and use the same policy engine. Do not silently change existing named objects or grants.

Permission Objects contain reusable DRLink operation permissions such as:

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

Example:

```text
set permission-object read-only permissions host-info,process-read,file-read
```

A true read-only role does not grant command execution.

## 4. AI Access Rule

`set ai-access` / `set ai-access <RULE>` opens the canonical reviewed rule wizard. Select Source, Destination, Permission, execution accounts/default and direct-file paths as specified below. A named rule replaces its prior destination; separate rules add destinations. Existing trusted Managed Host/group selectors, immutable group IDs, explicit dynamic trusted membership and separate `server:self` remain unchanged. `show ai-access`, `show ai-identity <NAME>` and `test ai-access` must show configured versus effective permissions and account readiness; deletion/reset remain fail-closed.

Canonical fields:

```text
name
source      → AI Identity
destination → Managed Host / Network Object / Network Group / Managed Host Group / managed-hosts:trusted / server:self
permission  → Permission Object / Permission Group
execution   → allowed OS accounts and default (account-bearing operations)
paths       → absolute direct-file scopes
enabled
```

Example first rule:

```text
set ai-access claude-prod source claude destination production-servers permission read-only paths /var/log/** enabled
```

### 4.1 Canonical execution-account contract

**User outcome:** a user says "fix the project, test and deploy it"; the AI discovers its available execution context and chooses the approved account. The user never has to provide an account or path for routine requests. No automatic root retry, sudo password manager, command classifier, new gateway or sandbox is in scope.

For Full management (and Custom with account-bearing operations), show the default existing OS account, additional existing accounts (multi-select), and explicit Administrator/root choice. Root may be the only or default account; no forced `drlink-mcp` account. Default is one allowed account, chosen explicitly; root must never be selected implicitly. A read-only rule offers no arbitrary execution account switch: diagnostic tools and scoped reads use a locally approved nonprivileged reader, and shell/write/delete/transfer permissions not granted by the rule are denied. Read-only plus management are not independent modes that can be combined to elevate a grant; Permission describes capabilities and accounts describe execution identity.

```text
Source           : ChatGPT
Destination      : dev-drlink
Permission       : Full management
Default account  : aella
Additional users : ubuntu
Administrator    : root (explicitly approved)
Direct file paths: /**
Review           : aella, ubuntu, root; default aella
```

Select accounts from the target's eligible existing OS users, not arbitrary names supplied by an AI. For a group/dynamic target, use exact account names, check each member's local execution eligibility independently, and report incompatible/offline members as unavailable; never substitute an account. New members must explicitly permit the relevant accounts locally, including root. The local administrator's target-specific ceiling and the authenticated AI's rule must both authorize the chosen account. On the local Server, the existing privileged CLI may configure that ceiling and the rule in one reviewed workflow; on a Managed Host use its existing trusted Agent/local operator authority. Never let an AI Access rule silently increase the target-local ceiling. If the ceiling is missing or incompatible, show the exact required operator action, leave the requested grant ineffective and retain the previous working configuration. Review root selection as full OS administrative authority, including ability to change DRLink itself. An existing OS account may already have privilege escalation rights; the product does not claim to confine arbitrary shell execution to its nominal UID or path scope.

For each operation, resolve target and current identity, then choose the explicitly requested `run_as` or a unique effective default. Apply one complete enabled matching rule that authorizes the capability, account and applicable path together; do not union independent rules into a new grant. If matching eligible rules disagree on the implicit default, return an ambiguity error with the authorized choices; explicit `run_as` can select an otherwise fully authorized rule. Never silently choose root or substitute another account. Job operations inherit the original target, immutable identity, UID/account, rule context and cwd; do not accept an account switch. Recheck current entitlement for every call, deny revoked job access and terminate tracked running jobs on revocation or loss of their grant; detached OS processes are not guaranteed retractable.

**Paths:** direct file operations enforce rule scopes plus target-local path ceilings and OS permissions; all files is `/**` in policy and `/` as an OS root. Full management defaults to full direct-file paths only with explicit review; narrower custom paths remain possible. Initial cwd is not a shell sandbox. Omitted cwd selects the target-approved per-account default (normally its accessible HOME); if no safe approved default exists return a diagnostic, never guess or fall back to root. Explicit invalid/out-of-scope cwd fails. A filesystem-wide grant may resolve legitimate existing directory aliases to their canonical cwd; scoped file operations retain traversal/symlink protections. For a general shell, the actual account's OS authority applies regardless of direct-file paths.

**Discovery and normal use:** `get_server` / `get_host` (and eligible target listings) expose only the requesting identity's effective capabilities, permitted accounts, UID/home, default account/cwd, applicable direct-file scope, availability and explicit administrator access. Unsupported targets/capabilities report unsupported, not false READY. MCP command, Git and account-bearing file/process calls take optional `run_as`; command cwd is optional. Default is used when omitted; AI tool descriptions direct development/Git to the project-owning approved account and system changes to explicitly approved root only when appropriate to user intent. Never auto-escalate on permission failure. No need to reconnect OAuth after an ordinary policy edit.

**Operator verification:** `test ai-access` evaluates configured policy; it does not by itself prove OS-level execution readiness. Show the chosen identity/target/account, effective paths, local executor readiness and actual command/file checks appropriate to the permission. Separate local executor self-test from real authenticated remote MCP checks; never claim remote PASS from local tests. Provide machine-readable denial codes identifying authentication, policy, account, cwd, file scope, OS permission or unavailable target, with only authorized recovery information. Audit the resolved account/UID, identity, target, rule/revision, tool and result without tokens or sensitive file contents.

**Native tracked jobs:** the candidate revalidates the complete grant against a single read snapshot before launch and on access. While jobs are active the native executor also checks current grants on a bounded 0.5-second interval (plus DB/OS scheduling latency); it terminates the managed process group and permanently denies the revoked job receipt. No client poll is required. Regranting access permits new jobs, not reuse of revoked job IDs. Detached OS processes are not guaranteed retractable.

**Linux Managed Host:** on the Agent Host run `sudo drlink set agent-execution` and review the selected existing accounts, roots and optional reader. `show agent-execution` shows local eligibility, not remote readiness. On the Server, the Rule wizard offers the names advertised by eligible targets; group eligibility remains per target. The operator-owned local execution profile supplies the allowed OS accounts, pinned UIDs, roots, default cwd and optional nonprivileged reader. Signed Agent claims advertise only that metadata; authenticated management response integrity is mandatory for account-bound jobs. Server dispatch and the final queued-job claim resolve the current complete grant, and the Agent rechecks its actual profile and paths before running the selected account. The dedicated account-bound wire capability cannot be interpreted as a legacy command by an older Agent. A previously account-aware host that loses its profile or downgrades is unavailable for account-bearing operations, not silently restored to service-user execution. Legacy hosts that have never advertised such a profile retain the old compatible behavior; explicit account selection is not available on those hosts. The Agent revalidates the signed attempt and local profile before launch, every 0.5 seconds while running (plus management response latency, bounded request timeout), and before returning output. It terminates its tracked process group on denial or loss of the management response; detached processes are not guaranteed retractable. Activation requires explicit review and existing unbound management Rules must be explicitly rebound; no legacy account authority is inferred when the original Agent execution identity cannot be proven. Windows/macOS account switching and actual installed upgrade/qualification remain separate.

**Persistence and upgrade:** maintain one canonical rule representation across CLI, Web (where present), policy evaluation and ConfigurationBundle. Execution binding is an allowed account list plus one default; omitted edit preserves binding, invalid/default-not-allowed or ambiguous configuration fails closed. Existing legacy single-account execution and Agent behavior must migrate only to the previously effective locally approved account and paths, never grant additional accounts/root by migration; if identity/OS authority cannot be verified, preserve state and mark unavailable pending explicit review. Preserve OAuth, certificates, identities, audit and existing policy/revisions. Do not claim implementation until new schemas, CLI, runtime, packaging, upgrade/rollback and real E2E pass.

## 5. Policy semantics

AI Access is explicitly deny-by-default and **WHITELIST-only**.

```text
Authenticated AI Identity + complete matching enabled Rule + local execution eligibility → ALLOW
No Policy / No Rules                              → DENY
No matching Rule                                  → DENY
Enforcement DISABLED                              → DENY ALL
Unsupported/invalid mode                          → DENY
```

Rules are not ordered and do not carry per-rule ALLOW/DENY actions. Authentication is necessary but never sufficient authorization. Disabling AI Access enforcement preserves configuration but shuts privileged AI/MCP operations fail-closed.

## 6. Test and audit

Test authorization without mutation:

```text
test ai-access source <AI_IDENTITY> destination <DESTINATION> permission <PERMISSION>
```

Audit views:

```text
show ai-access-log
show ai-access-log identity <IDENTITY>
show ai-access-log destination <DESTINATION>
show ai-access-log permission <PERMISSION>
```

Useful entries expose timestamp, AI Identity, destination, permission, selected execution account/UID, rule/revision and result. Sensitive file contents, bearer tokens, and unrestricted command output are not audit payloads.

## 7. MCP security boundary

The intended server-side flow is:

```text
MCP host
→ authenticated HTTPS public MCP endpoint
→ server-side MCP Bridge
→ authenticated AI Identity
→ current AI Access authorization
→ local Server executor or authenticated DRLink Agent management path
→ target OS permission boundary
```

Remote Services or exposed SSH are not prerequisites for an authorized MCP operation.

Every new privileged tool invocation is authorized against current policy.

## 8. File and command permissions

Direct file operations must enforce configured path scope after safe canonical path resolution.

Public v2.4 configuration binds those scopes on the AI Access rule:

```text
set ai-access allow-read ... permission read-only paths '/var/lib/vendor/**' enabled
```

ConfigurationBundle rules use the same `paths` list. Omit `paths` on edit to preserve existing scopes; export includes configured scopes so same-state reapply is NO CHANGE.

`test ai-access` accepts optional `path <PATH>` so public policy test agrees with MCP runtime authorization for in-scope and out-of-scope file operations. Without a path, file permissions do not report unconditional ALLOW.

When `permission` is a Permission Group, public `test ai-access` expands to atomic permissions, evaluates each member with the same path-aware rules, and aggregates ALLOW only when every atomic member allows. Mixed Permission Groups therefore cannot report a false scalar ALLOW.

Command execution is stronger than direct read/write permissions because a shell may modify system state. The account selection, optional cwd, target-local ceiling and effective rule semantics in §4.1 are mandatory. Direct-file paths and initial cwd are not a shell sandbox.

Unknown or ungranted operations are denied.

## 9. Secrets

Do not expose or place in ConfigurationBundle/AI copy-paste output:

```text
OAuth access/refresh tokens
Static Bearer tokens
private keys
enrollment tickets
credentials
```

Support bundles and logs must redact protected values.

## 10. Interoperability qualification

Certificate activation must regenerate the project-owned single-443 frontend
from the Server configuration and active certificate metadata before reload.
Activation validates nginx configuration and the actual loopback TLS peer with
the configured MCP SNI hostname. Certificate and frontend configuration are
restored together on failure. Clearing MCP TLS intent removes its SNI route;
purging secrets happens only after that route has been removed and reloaded.
The distinct control hostname retains its private-CA certificate and WSS route.
HTTP-01 is enabled only for AUTO_ACME; an imported certificate does not require
a new listener on port 80. On **first** AUTO_ACME issuance there is not yet
an active public MCP certificate: the issuer must first stage a challenge-only
HTTP/80 nginx route for the configured hostname, while preserving the existing
FRP/WSS HTTPS/443 configuration. The challenge listener is prepared only within
the authorized issuance lifecycle, and the exact previous frontend bytes and
listener state are restored if ACME issuance fails. Therefore HTTP/80 being
closed before the first issuance request is **not by itself** proof that the OCI
Security List is closed; cloud ingress policy, actual challenge listener and
external ACME reachability need separate evidence. No private CA, -k/skip-verify
or successful unit fixture substitutes for a real publicly trusted certificate.
These checks qualify local certificate activation; real MCP host interoperability
remains a separate user gate.

Do not claim ChatGPT, Claude, Cursor, or another MCP host as supported solely from protocol conformance.

Release qualification must retain real interoperability evidence for every host explicitly claimed as supported.

### Upgrade data retention

Pre-v2.4 capability/action records are not an effective authorization source and are retained for recovery and audit. The current CLI shows their count separately; it never lists them as active rules, completes their names or edits/deletes them through the current rule command. Recreate an explicitly reviewed current rule only when needed. Existing canonical rules and saved credentials remain unchanged. No old allow/deny order is automatically translated into a broader WHITELIST grant.
