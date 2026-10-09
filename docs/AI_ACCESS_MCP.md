# Data Relay Link — AI Identity, AI Access, and MCP

> **Status:** v2.4 development operator/developer guide
> **Authority:** Public CLI semantics come from the CLI/AI Master; security and transport boundaries come from `SECURITY.md`.

## 1. Model

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
system credential rotate ai-identity <IDENTITY>
system credential revoke ai-identity <IDENTITY>
system credential configure ai-identity <IDENTITY> authentication <static-bearer|oauth>
system credential approve-oauth <PENDING-ID> [AI-IDENTITY]
system credential deny-oauth <PENDING-ID>
```

Credential rotate/revoke/configure are security-sensitive authentication changes; revoke can interrupt active clients. OAuth approve is an explicit authorization decision that can widen access, while deny rejects the pending authorization. These explicit commands are themselves operator approval and do not add a second confirmation prompt.

Public MCP is served only through the `single443` HTTPS frontend. `direct` deployment mode uses its public control port for the FRP listener and therefore must not advertise or activate `https://<host>/mcp`; `set mcp-tls` and certificate mutation commands fail closed until the Server is reconfigured to `single443`. The supported transition is to re-run the Data Relay Link Server installer from the same immutable release/source ref with `FRP_DEPLOYMENT_MODE=single443`, confirming the cutover by typing `SWITCH` on a TTY or setting `FRP_CONFIRM_MODE_SWITCH=yes` for a non-interactive run. A stale TLS intent or certificate from an earlier configuration does not make Direct mode MCP-capable.

For a single443 Server with an explicitly configured MCP TLS hostname and mode, that hostname is the canonical `https://<MCP-HOSTNAME>/mcp` origin for OAuth issuer, discovery, registration and token exchange. It takes priority over an older `DRLINK_MCP_PUBLIC_URL` environment override (which remains a fallback when no dedicated MCP TLS hostname is configured). After a hostname change, inspect `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource/mcp` through the externally reachable MCP HTTPS hostname; the issuer, registration endpoint, token endpoint and protected resource must all match the routed, certificate-valid FQDN. Internal loopback discovery checks do not substitute for the external client test.

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
set ai-access claude-prod mode whitelist source claude destination production-servers permission read-only enabled
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
a new listener on port 80. These checks qualify local certificate activation;
real MCP host interoperability remains a separate user gate.

Do not claim ChatGPT, Claude, Cursor, or another MCP host as supported solely from protocol conformance.

Release qualification must retain real interoperability evidence for every host explicitly claimed as supported.
