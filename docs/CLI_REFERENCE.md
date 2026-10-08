# Data Relay Link — CLI Reference

> **Status:** v2.4 active
> **Primary CLI:** `drlink`
> **Authoritative behavior:** `docs/DATA_RELAY_LINK_CLI_AI_MASTER_v2.4_FINAL.md`

This document is a compact public command reference. The Master defines exact semantics when an example here is abbreviated.

## 1. Command model

Inside the REPL:

```text
drlink> show status
drlink> set network-object github
```

From a shell:

```bash
drlink show status
drlink set network-object github
```

Common roots:

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

Discovery:

```text
?
help
help managed-hosts
help network-objects
help commands
<verb> ?
Tab completion
```

## 2. Server show commands

```text
show status

show managed-hosts
show managed-host <HOST>
show managed-host <HOST> agent
show managed-host <HOST> addresses
show managed-host <HOST> remote-services

show managed-host-groups
show managed-host-group <GROUP>

show enrollments
show enrollment <ENROLLMENT>

show network-objects
show network-object <OBJECT>
show network-object <OBJECT> references
show network-groups
show network-group <GROUP>
show network-group <GROUP> references

show service-objects
show service-object <SERVICE>
show service-object <SERVICE> references
show service-groups
show service-group <GROUP>
show service-group <GROUP> references

show remote-access
show remote-access <RULE>

show internet-access
show internet-access <RULE>

show ai-identities
show ai-identity <IDENTITY>

show permission-objects
show permission-object <PERMISSION>
show permission-groups
show permission-group <GROUP>

show ai-access
show ai-access <RULE>

show ai-access-log
show ai-access-log identity <IDENTITY>
show ai-access-log destination <DESTINATION>
show ai-access-log permission <PERMISSION>
```

## 3. Server set commands

```text
set enrollment zero-touch
set enrollment manual
set enrollment bulk

set server public-hostname <FQDN>
set server bootstrap-hostname <FQDN>
set server installer-url <URL>
set server windows-installer-url <URL>

set managed-host-group <GROUP>
set managed-host <HOST> group <GROUP>

set network-object <OBJECT>
set network-group <GROUP>

set service-object <SERVICE>
set service-group <GROUP>

set remote-access <RULE>
set remote-access enabled
set remote-access disabled

set internet-access <RULE>
set internet-access enabled
set internet-access disabled

set ai-identity <IDENTITY>

set permission-object <PERMISSION>
set permission-group <GROUP>

set ai-access <RULE>
set ai-access enabled
set ai-access disabled

set mcp-tls hostname <FQDN>
set mcp-tls mode <auto-acme|user-certificate>
set mcp-tls contact-email <EMAIL>
set mcp-tls acme-environment <production|staging>
set mcp-tls acme-directory <URL>
```

Bare named `set` enters Guided Create/Edit. A complete one-shot form skips the Wizard. Server settings remain action-first under `set server ...` / `unset server ...`; the guided menu places the same settings under System → Server Settings.

Examples:

```text
set network-object github type fqdn value github.com
set network-object office-admin type ip value 203.0.113.10

set network-group approved-admins members office-admin,vpn-admin

set service-object ssh type tcp port 22
set service-object dns-udp type udp port 53
set service-object legacy-db type fixed-tcp port 1521

set service-group web-services members http,https

set permission-object read-only permissions host-info,process-read,file-read
set permission-group operators members read-only,operator

set ai-access allow-read mode whitelist source automation-ai destination ubuntu-prod permission read-only paths /var/lib/vendor/** enabled
```

## 4. Access Policy commands

First non-interactive Rule in an unconfigured policy must include `mode`.

Remote Access:

```text
set remote-access block-partner mode blacklist source partner-office destination ubuntu-prod service ssh enabled
```

Internet Access:

```text
set internet-access github-https mode whitelist source ubuntu-prod destination github service https enabled
```

AI Access:

```text
set ai-access claude-prod mode whitelist source claude destination production-servers permission read-only enabled
set ai-access allow-read mode whitelist source automation-ai destination ubuntu-prod permission read-only paths /var/lib/vendor/**,/opt/app/** enabled
```

File permissions (`file-read` / `file-write` / `file-upload` / `file-download`) use rule-bound `paths` scopes. Omit `paths` on edit to preserve existing scopes; use `paths -` or `paths none` to clear. Missing scopes remain fail-closed at runtime (no unrestricted filesystem default).

When Policy Mode already exists, `mode` may be omitted. A conflicting requested mode is rejected.

Policy enforcement:

```text
set remote-access enabled
set remote-access disabled
set internet-access enabled
set internet-access disabled
set ai-access enabled
set ai-access disabled
```

Rule disable excludes only that Rule from evaluation.

## 5. Policy semantics

Remote Access initial state:

```text
No Policy
No Rules
Effective = ALLOW
```

Remote Access BLACKLIST:

```text
match    → DENY
no match → ALLOW
```

WHITELIST (all three planes):

```text
match    → ALLOW
no match → DENY
```

Internet Access and AI Access support WHITELIST only. No Policy, No Rules,
no match, disabled enforcement, and unsupported/invalid mode all mean DENY.
Remote Access disabled enforcement means ALLOW ALL.

There is no public rule-order command and no per-rule `allow|deny` action field.

## 6. Server unset commands

```text
unset managed-host <HOST>
unset managed-host <HOST> group <GROUP>
unset managed-host-group <GROUP>
unset enrollment <ENROLLMENT>

unset server public-hostname
unset server bootstrap-hostname
unset server installer-url
unset server windows-installer-url

unset network-object <OBJECT>
unset network-group <GROUP>

unset service-object <SERVICE>
unset service-group <GROUP>

unset remote-access <RULE>
unset remote-access policy

unset internet-access <RULE>
unset internet-access policy

unset ai-identity <IDENTITY>

unset permission-object <PERMISSION>
unset permission-group <GROUP>

unset ai-access <RULE>
unset ai-access policy

unset mcp-tls
unset mcp-tls purge
```

`unset mcp-tls` clears TLS intent and removes the active public MCP route while retaining DRLink-owned certificate and ACME account material. Active MCP/OAuth connections may be interrupted; the explicit command approves this change without an additional confirmation prompt. Check `system certificate status` and `system diagnostics mcp` afterward. `unset mcp-tls purge` removes that retained material only after interactive y/N confirmation; non-interactive use fails closed.

Referenced Objects/Groups/Identities/Managed Hosts are protected from deletion until references are removed.

For Permission dependencies, inspect `show ai-access` and `show ai-access <RULE>`; inspect `show permission-groups` and `show permission-group <GROUP>` for Object membership. A blocked `unset permission-object <PERMISSION>` or `unset permission-group <GROUP>` lists the references before confirmation and applies no changes. Review each referencing Rule with `set ai-access <RULE>` to choose a replacement permission, or explicitly remove that Rule with `unset ai-access <RULE>`. Use `set permission-group <GROUP>` to review membership without the Object being retired. Disabling a Rule retains its reference. Review access impact and the required confirmations, then retry deletion only when all references have been removed. No Permission `references` subcommand is required.

`unset enrollment <ENROLLMENT>`, `unset network-object`, `unset network-group`, `unset service-object`, `unset service-group`, `unset permission-object`, `unset permission-group`, and `unset ai-identity` are destructive lifecycle operations and require explicit `y/N` confirmation after existence/reference validation. Default is No and cancellation applies no change. These are normal `y_n` flows rather than TTY-only flows, so controlled automation may provide `y`/`yes` on stdin; there is no public hidden environment-variable or `--yes` bypass for these commands. Policy Rule deletion uses effect-aware `conditional_y_n`: confirmation is required when the calculated change broadens or materially narrows access, while full `unset <plane>-access policy` reset always requires explicit confirmation.

A **Managed Host Group** is an inventory grouping of registered Managed Hosts. It is distinct from a **Network Group**, which is a reusable policy selector made from Network Objects. Adding or removing Managed Host Group membership does not retire the Managed Host, change Remote Services, reallocate public ports, or create/change a Network Group. The explicit `unset managed-host <HOST> group <GROUP>` command approves that metadata edit without an additional prompt. Bare `unset managed-host <HOST>` remains reference-safe irreversible retirement with explicit y/N confirmation. `unset managed-host-group <GROUP>` requires interactive y/N confirmation; public `--yes` is not supported.

## 7. Policy test commands

```text
test remote-access source <SOURCE> destination <DESTINATION> service <SERVICE>
test internet-access source <SOURCE> destination <DESTINATION> service <SERVICE>
test ai-access source <AI_IDENTITY> destination <DESTINATION> permission <PERMISSION> [path <PATH>]
```

Output includes Mode, Enforcement, selectors, matched Rules, and Effective Result. Where relevant, Remote Service runtime state is shown separately from policy authorization.

When a selector is a Network Group, Service Group, or Permission Group, the public test expands every leaf member (stable sorted order), evaluates each concrete combination with the same atomic/runtime evaluators used for single Objects, and reports member/combination detail. Top-level Effective Result is ALLOW only when every expanded member/combination is ALLOW; mixed outcomes aggregate to DENY. Single Object / Service / Permission Object / atomic permission behavior is unchanged.

For file permissions, omit `path` and `test ai-access` will not claim unconditional ALLOW (runtime requires an in-scope path). Provide `path <PATH>` to evaluate the same fail-closed path-scope contract used by MCP. Permission Groups that include file permissions apply that fail-closed rule per file member before aggregation.

## 8. Server system commands

```text
system status
system version
system diagnostics
system audit

system revisions
system revision <REVISION>
system diff <REVISION_A> <REVISION_B>
system rollback <REVISION>

system backup
system backup validate <FILE>
system restore <FILE>

test configuration <FILE|->
system export configuration <FILE>
system diff configuration <FILE|->
system apply configuration <FILE|->

system certificate issue
system certificate import <CERT> <KEY> [CHAIN]
system certificate renew
system certificate status
system certificate preflight

system credential rotate ai-identity <IDENTITY>
system credential revoke ai-identity <IDENTITY>
system credential configure ai-identity <IDENTITY> authentication <static-bearer|oauth>
system credential approve-oauth <PENDING-ID> [AI-IDENTITY]
system credential deny-oauth <PENDING-ID>

system update product
system update engine
system update check-engine
system support-bundle
system uninstall
```

Restore validates the archive before offering live replacement confirmation.
After replacement, backup-time host presence and proxy health require fresh
Agent verification; reconnect reconciliation reapplies the Agent runtime while
preserving its identity and allocated endpoints.

`system status` is the detailed Server read-only view. In addition to runtime/control-plane health, it shows the current public hostname, bootstrap hostname, Linux/macOS Agent installer source, and Windows Agent installer source, including their automatic/default fallback semantics. `show status` remains the role-aware summary.


`system certificate status` is the single public MCP TLS/certificate status surface. Configure TLS intent with `set mcp-tls ...`; there is no separate MCP TLS status read command.

## 9. Managed Host as Network Object

Registered Managed Hosts appear in `show network-objects` with type `Managed Host`.

Managed Host lifecycle is never performed through `set/unset network-object`.

Internet Access source may use a Managed Host. Because the egress proxy is agentless, that selector is proven only when the observed proxy peer IP matches an eligible active address for the Managed Host. Internet Access is WHITELIST-only, so an unprovable or NAT-translated Managed Host source does not match and is denied. Behind NAT, prefer an IP/CIDR selector for the proxy-visible source. Internet Access destination may not use a Managed Host, directly or through a Network Group.

Policy Rule and referenced Network/Service/Permission Object or Group edits
calculate security impact before mutation. A y/N confirmation is required for
calculated access widening or material narrowing. Safe creation and no-change
paths do not need an additional confirmation; cancellation preserves state.

## 10. Agent Host commands

Agent lifecycle commands act on the local Agent Host. The explicit command
authorizes pause, restart, synchronization and complete Remote Service edits;
these operations can interrupt connections and use no additional confirmation
prompt. The name-only Remote Service form still reviews its wizard draft before
apply. `system autostart disable` leaves the current runtime alone but prevents
automatic startup after the next boot; `system autostart enable` reverses that
setting. `system resume` restores automatic startup and starts the Agent.

```text
show status
show agent

show remote-services
show remote-service <NAME>

set remote-service <NAME>
unset remote-service <NAME>

system info
system pause
system resume
system restart
system autostart enable
system autostart disable
system update product
system update engine
system synchronize

test configuration <FILE|->
system export configuration <FILE>
system diff configuration <FILE|->
system apply configuration <FILE|->

system diagnostics
system support-bundle
system version
system uninstall
```

Agent one-shot example:

```text
set remote-service ssh-access destination this-host service ssh enabled

```

`SERVICE` selects a Server-defined TCP or Fixed TCP Service Object. The Server allocates and reserves the public endpoint; the Agent does not choose a public port.

Relay example executed on `branch-gateway`:

```text
set remote-service internal-db-postgres destination internal-db service postgres enabled
```

The current Agent Host is the Relay Host.

## 11. Remote Service contract

Remote Service uses exactly one Service Object.

Supported:

```text
TCP
Fixed TCP
```

Rejected:

```text
UDP
Service Group
CIDR/multi-target destination
duplicate Destination + Service on the same Agent
```

States:

```text
HEALTHY
DEGRADED
DISABLED
```

A valid but temporarily unreachable destination is saved as `DEGRADED`.

New valid Remote Service created while the Server is unavailable may show:

```text
Status   : DEGRADED
Endpoint : Pending allocation
```

After reconnect, DRLink synchronizes, allocates/activates, and transitions to `HEALTHY`.

## 12. Fixed TCP

Fixed TCP is a Service Object subtype.

```text
set service-object legacy-db type fixed-tcp port 1521
```

The external endpoint is allocated when an Agent creates a Remote Service using that Service Object. Standard TCP and Fixed TCP Remote Services use separate endpoint pools.

An existing Remote Service cannot change in place across standard TCP and Fixed TCP pool classes.

## 13. AI Identity

```text
set ai-identity <NAME>
show ai-identities
show ai-identity <NAME>
unset ai-identity <NAME>
```

Interactive AI binds through OAuth Authorization Code verification.

Automation / Custom AI binds through OAuth Client Credentials verification.

Authentication is distinct from AI Access authorization.

## 14. ConfigurationBundle

```text
test configuration <FILE|->
system diff configuration <FILE|->
system apply configuration <FILE|->
system export configuration <FILE>
```

stdin terminator:

```text
:end
```

Server Bundle and Agent Bundle are independently atomic within their current CLI context. Cross-context distributed atomicity is not provided.

## 15. Wrong-context errors

Server-only policy/Object mutation on an Agent Host must say the command belongs on the DRLink Server.

Agent-local Remote Service mutation on a Server must say it belongs on the owning Agent Host.

Do not reduce a known role error to an unexplained `Unknown command`.

## 16. Error contract

User-facing errors should state:

```text
what is wrong
what is required
whether a change was applied
what to do next
```

Raw traceback or backend database errors are not the public error contract.

## 17. Obsolete intermediate grammar

The following are not canonical v2.4 public resources/semantics:

```text
object / object-group as the only neutral public object hierarchy
managed-endpoint
published-service
service-preset
ai-principal
ordered-rule movement
per-rule ALLOW/DENY action
implicit default-DENY-only policy model
```

Use the Network/Service/Permission Object model, AI Identity, Remote Service, and plane-specific policy semantics defined by the Master: Remote Access supports BLACKLIST/WHITELIST; Internet Access and AI Access are WHITELIST-only and deny-by-default.
