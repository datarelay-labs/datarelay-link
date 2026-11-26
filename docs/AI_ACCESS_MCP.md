# Data Relay Link — AI Identity, AI Access, and MCP

> **Status:** AI Access UX redesign target; implementation and installed-runtime qualification pending
> **Authority:** Public CLI semantics come from the CLI/AI Master; security and transport boundaries come from `SECURITY.md`.

## 1. Model

### Beginner-first AI Access UX — target contract (2026-11-25)

This is the single intended UX for the next implementation candidate, not a claim that the installed release already implements it. This guide is the detailed normative workflow; CLI, menu, help, completion and tests must converge on this contract; any Web UI consuming these functions must follow the same design. Do not retain alternate public spellings, parallel wizards or duplicate menu entry points for retired UX. Preserve persisted identities, policy, certificates and audit history; no permission widening, implicit trust or silent reconfiguration during migration.

- **Managed Hosts**: register/enroll and manage actual hosts. Never add a host through an AI connection screen.
- **AI Identity**: connect, verify, inspect, reconnect and disconnect an AI client. Authentication alone is not authorization.
- **AI Access Rules**: select Source (verified AI Identity), Destination (Managed Host-backed Network Object / Network Group, or explicitly selected `server:self` under its separate native execution controls), and Permission (built-in profile or reusable custom Object/Group), with explicit path and execution constraints. The firewall-style policy is separate from inventory and authentication.
- **System → MCP Server Settings / Certificates**: owns infrastructure. The Connect AI wizard detects readiness and offers the same settings workflow inline when needed, then returns to onboarding. Ready TLS is reused without issuing or reconfiguring a certificate. Direct mode must report the supported single443 prerequisite; no silent deployment-mode switch.
- **Advanced Permissions**: custom Permission Objects/Groups only when needed; not prerequisites for routine onboarding. Read-only grants host-info, process-read and explicitly scoped file-read. Full management offers all seven capabilities only after explicit review of destination, path and OS execution constraints. No automatic root or unrestricted path grant by selecting a label.
- AI Access is WHITELIST-only. The wizard and one-shot Rule grammar require no mode field; first reviewed rule initializes WHITELIST atomically. No Policy, disabled enforcement, unverified/revoked identity, no matching rule or unsafe/unavailable target remains DENY.

First connection: AI Access → Connect AI → select ChatGPT/Claude/Other and name → check endpoint/TLS (fix only if needed) → show public URL and client connection instructions → verify pending OAuth request, explicit operator approval and actual PKCE exchange → optionally open the separate Access Rule wizard with the verified Source preselected. Review destination and permissions before applying; skipping policy setup leaves DENY. The first Owner shortcut is optional and explicitly reviewed: only a verified identity may receive a named audited rule for all trusted hosts, including future signed enrollments **only if the operator explicitly chooses that dynamic scope**, with explicit permissions and path bounds. Select managed-hosts:trusted only for this explicitly reviewed dynamic destination; it evaluates the current active trusted Managed Host inventory on every authorization call, not a mutable automatically populated group. Otherwise select existing host(s)/group. Never implicitly authorize a new AI because it is first. Subsequent hosts are enrolled under Managed Hosts; a matching dynamic policy needs no AI reconfiguration; other policies remain unchanged until edited. Show effective access and actual connectivity separately.

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


```text
Authentication
→ establish verified AI Identity

AI Access
→ decide which destination and permission that identity may use

MCP Bridge
→ integration/transport layer
```

MCP does not create a separate public identity model.

## 2. AI Identity

The normal entry point is `set ai-identity` (or AI Access → Connect AI), with the named form for an existing/new identity. In the guided flow the user selects and reviews pending requests directly; the one-shot actions below serve automation, not a second wizard.

Canonical public resource:

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

Server CLI entry:

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

Public MCP is served only through the `single443` HTTPS frontend. `direct` deployment mode uses its public control port for the FRP listener and therefore must not advertise or activate `https://<host>/mcp`; `set server mcp` and certificate mutation commands fail closed until the Server is reconfigured to `single443`. The supported transition is to re-run the Data Relay Link Server installer from the same immutable release/source ref with `FRP_DEPLOYMENT_MODE=single443`, confirming the cutover by typing `SWITCH` on a TTY or setting `FRP_CONFIRM_MODE_SWITCH=yes` for a non-interactive run. A stale TLS intent or certificate from an earlier configuration does not make Direct mode MCP-capable.

For a single443 Server with an explicitly configured MCP TLS hostname and mode, that hostname is the canonical `https://<MCP-HOSTNAME>/mcp` origin for OAuth issuer, discovery, registration and token exchange. The configured MCP hostname is the authoritative public origin; do not expose a competing public configuration path. After a hostname change, inspect `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/mcp` through the externally reachable MCP HTTPS hostname; the issuer, registration endpoint, token endpoint and protected resource must all match the routed, certificate-valid FQDN. Internal loopback discovery checks do not substitute for the external client test.

### First-time ChatGPT OAuth connection (DCR / CIMD)

On a fresh DRLink Server, there may be no existing AI Identity. The first
remote OAuth authorization must **not** require a pre-existing VERIFIED
identity (that would make initial onboarding impossible).

1. Add the public `https://<MCP-HOSTNAME>/mcp` endpoint in the supported
   ChatGPT MCP connection UI; this opens an OAuth request.
2. Copy the Pending request ID (oap_...) displayed on the browser consent page and paste it into the Pending request ID prompt in the guided AI Identity CLI. Review the client, redirect origin, requested resource and scope before approving. Alternatively, on the **DRLink Server** run:

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

`set ai-access` opens guided rule selection/creation. `set ai-access <RULE>` opens create/edit for that name. Show and review Source, Destination, Permission, file paths, effective OS execution constraints, enabled state and current/future host scope. The default destination scope is explicitly selected existing hosts; no implicit wildcard. Editing a named rule replaces its previous destination; create a different rule to add another destination. All trusted Managed Hosts (current and future; excludes Server) is the explicit dynamic destination. File path examples: `/**` (all files), `/home/**` (one directory), `/home/**,/opt/**` (multiple directories); `*` is not an absolute path scope. OS access restrictions still apply. `show ai-identity <IDENTITY>` lists configured rules and their destinations, permissions, paths and enabled state; runtime authorization is evaluated per call. `unset ai-access <RULE>` removes one rule, whereas `unset ai-access policy` resets all rules and fails closed after explicit confirmation. Use a verified identity and trusted host-backed selectors; native `server:self` is separately reviewed and never implied by all Managed Hosts.

Canonical fields:

```text
name
source      → AI Identity
destination → Network Object / Network Group
permission  → Permission Object / Permission Group
enabled
```

Example first rule:

```text
set ai-access claude-prod source claude destination production-servers permission read-only enabled
```

## 5. Policy semantics

AI Access is explicitly deny-by-default and **WHITELIST-only**.

```text
Authenticated AI Identity + matching enabled Rule → ALLOW
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

Useful entries expose timestamp, AI Identity, destination, permission, and result. Sensitive file contents, bearer tokens, and unrestricted command output are not audit payloads.

## 7. MCP security boundary

The intended server-side flow is:

```text
MCP host
→ authenticated HTTPS public MCP endpoint
→ server-side MCP Bridge
→ authenticated AI Identity
→ current AI Access authorization
→ authenticated DRLink Agent management path
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

Command execution is stronger than direct read/write permissions because a shell may modify system state. Grant `command-exec` only when the target OS identity and privilege boundary are appropriate.

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
