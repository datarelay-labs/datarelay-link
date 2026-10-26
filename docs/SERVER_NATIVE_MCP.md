# Data Relay Link v2.4 — Native Server MCP

> Workstream: [Issue #223](https://github.com/datarelay-labs/datarelay-link/issues/223)
>
> Candidate status: Native Server MCP Preview is live on dev-drlink at **loopback 127.0.0.1:16106**,
> pinned to immutable v2.4 candidate 73fce8e3. Direct Cloudflare HTTPS and actual ChatGPT OAuth are **not yet connected**.
> The dedicated mcp.link.xdr.ooo connector service is staged but disabled until owner-provided Cloudflare token and DNS hostname routing.

## Current owner scope: direct ChatGPT-to-access.xdr.ooo MCP

**Owner correction, 2026-10-26:** Direct control of the DRLink development
Server is the goal. ChatGPT must connect to the **Native MCP implementation
running on access.xdr.ooo** and eventually replace Desktop Commander for
development operations (file read/write/delete, tests, Git, deployments),
after acceptance on the actual ChatGPT tool surface.

An outbound peer enrolled as a Managed Host on `remote.xdr.ooo`, an
Enrollment Code, and installation of a DRLink Agent are **not prerequisites**.
The previously implemented Server-peer option is separate, not the accepted
solution to this objective. Likewise, merely reporting `get_server` metadata
is not a substitute for development command and file workflows.

Preferred direct integration:
```
ChatGPT custom MCP connection
  -> public, CA-trusted HTTPS MCP URL dedicated to access.xdr.ooo
  -> authenticated Native Server MCP Bridge on access.xdr.ooo
  -> per-AI-Identity AI Access WHITEList and worktree-specific path scopes
  -> unprivileged developer executor (no root shell)
  -> approved source, test and Git operations
```
The HTTPS entry point **may use a reverse proxy or existing trusted relay**
while retaining request handling, OAuth authorization and tool execution on
access.xdr.ooo. Do not confuse a TLS relay with central Managed-Host
enrollment. Existing FRP TCP/443 must not be replaced without a qualified
cutover and rollback.

**Hard requirements before removing Desktop Commander:** full MCP tool
coverage required for development, publicly trusted TLS and correct canonical
OAuth resource/issuer, explicit AI Access rules, user-accessible full-write
MCP entitlement, real allow/deny E2E through ChatGPT, and recoverable
rollout. Until then keep Desktop Commander connected.

## Direct ChatGPT access: mcp.link.xdr.ooo (owner-selected)

**Endpoint:** `https://mcp.link.xdr.ooo/mcp`. OAuth issuer:
`https://mcp.link.xdr.ooo`. Server executing these tools:
**access.xdr.ooo / dev-drlink**, loopback `127.0.0.1:16106`.

As checked on 2026-10-26, Cloudflare authoritative NS for `xdr.ooo`
are `nancy.ns.cloudflare.com` and `armando.ns.cloudflare.com`, but the
existing `mcp.link.xdr.ooo` **A record** still points at dev-drlink's
`221.139.249.111`. Its public TCP/443 is the existing Direct-mode FRP
listener with a self-signed leaf certificate, **not** an HTTPS MCP endpoint.
TCP/80 is not currently serving. Switching the DRLink Server from Direct
to single443 would disconnect Agent Hosts, so **do not do this merely to
activate ChatGPT**.

### Non-disruptive Cloudflare Tunnel

The existing binary `/usr/local/bin/cloudflared` (2026.8.3) and
outbound Cloudflare TCP/7844 are available on dev-drlink. This is a
Cloudflare network connector only: **not** an OpenAI Tunnel, a new DRLink
Agent, a central DRLink Server-peer enrollment or another user VM.
Cloudflare provides public HTTPS with a trusted certificate for
`mcp.link.xdr.ooo` while routing to the local Native MCP over HTTP on
`127.0.0.1:16106`. DRLink's own OAuth and AI Access still enforce auth.

The user-owned systemd service
`drlink-native-mcp-cloudflare.service` is pre-staged but **disabled**
until the Cloudflare account owner configures its tunnel token and
hostname. Existing root DRLink Server/MCP/FRP services are preserved.

**Cloudflare account owner's required action** (the ChatGPT session has
no Cloudflare dashboard credentials/authorized DNS-write connector):

1. In Cloudflare Dashboard → Networking → Tunnels, create a remotely
   managed tunnel named `drlink-access-native-mcp`.
2. Create its public application hostname `mcp.link.xdr.ooo` using
   **HTTP** service URL `http://127.0.0.1:16106`.
   Remove the pre-existing `mcp.link.xdr.ooo` **A record** in Cloudflare
   DNS first if Cloudflare reports a conflicting record. The Dashboard
   creates a tunnel CNAME to `<TUNNEL-UUID>.cfargotunnel.com`.
   The Cloudflare edge IP may appear in DNS afterward; the actual
   DRLink Native MCP still runs exclusively on **access.xdr.ooo**.
3. Copy the **connector token** from the Tunnel's Add a replica / Linux
   instructions. NEVER paste it in ChatGPT or Git; enter it only at the
   masked prompt on dev-drlink below. Do not add a Cloudflare Access
   login requirement that would preempt DRLink's OAuth flow.

On dev-drlink over direct SSH:

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026

# Read-only verification; no sudo needed.
python3 tools/operator-native-mcp-domain.py --check
python3 tools/operator-native-mcp-cloudflare.py --check

# Set canonical OAuth resource/issuer to the NEW public hostname.
# This edits ONLY the isolated Native MCP Preview systemd unit, and keeps
# the Server-local developer executor disabled. Root backup/rollback included.
sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --preflight
sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --apply
sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --verify

# Start the pre-staged, separate, unprivileged Cloudflare connector.
# This prompts privately for the Cloudflare connector token.
python3 tools/operator-native-mcp-cloudflare.py --activate

# Actual public TLS, OAuth metadata and anonymous 401 verification.
python3 tools/operator-native-mcp-cloudflare.py --verify
```

`NATIVE_MCP_DOMAIN_VERIFY=PASS` verifies the local service OAuth issuer.
`NATIVE_MCP_PUBLIC_TLS=PASS`,
`NATIVE_MCP_PUBLIC_OAUTH=PASS`,
`NATIVE_MCP_ANONYMOUS_DENY=PASS` prove the Cloudflare HTTPS route works
before adding it to ChatGPT. OAuth identity authorization/consent and
`tools/call` are separate live acceptance tests.

After those pass, in the user's ChatGPT custom MCP/app setup register
`https://mcp.link.xdr.ooo/mcp` with OAuth. The dev DRLink operator must
enable a verified AI Identity and a *separate, least-privilege* AI Access
WHITELIST for `server:self`. Neither anonymous access nor a previous
central Server Peer/Agent identity is sufficient. Developer file/test/Git
permissions additionally require explicit allowed worktree paths and the
non-root executor gates.

**Rollback only the new hostname and Tunnel:**

```bash
python3 tools/operator-native-mcp-cloudflare.py --stop
sudo /usr/bin/python3 tools/operator-native-mcp-domain.py --rollback
```

Remove/revoke the Tunnel from the Cloudflare account to invalidate its
connector token. Do not remove Desktop Commander until actual ChatGPT
read/write/test/Git/deploy E2E and deny-case tests succeed. Do not expose
FRP 443 directly to ChatGPT or bypass TLS certificate validation.

## Purpose and version

The unreleased v2.4.0 candidate includes MCP according to the repository's
`docs/VERSION_POLICY.md`. Extend MCP to the DRLink **Server itself**, without
installing a DRLink Agent on the Server. Existing Managed Host/Agent dispatch and
OAuth behavior remain unchanged. The feature is opt-in and independently gated.

## Targets

- `server:self` is a built-in Server-local target, not a Managed Host, Network
  Object, Agent Client ID, hostname, IP address or shortcut to an arbitrary Server.
- Server-self AI Access Rules bind `destination_ref_kind=server`,
  `destination_ref_id=local`, per-verified-AI-Identity and Permission Object.
  The policy is evaluated per call with the existing v2.4 WHITEList engine.
- Existing `list_hosts` must not advertise `server:self`. `get_server` is
  separate, and `get_system_info(endpoint="server:self")` uses the Server route.
- A `server:self` selector never impersonates an Agent or a Managed Host,
  and does not depend on a central DRLink Server or an Enrollment Code.

## Enforcement gates

- `DRLINK_MCP_SERVER_SELF_ENABLED=1`: enable Server-self metadata lookup only.
  Without an explicit enabled Server-self AI Access Rule granting `host-info`,
  even this metadata is denied.
- `DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=1`: second gate for Server-local
  file/Git operations. Both variables default to unset/disabled.
- `DRLINK_MCP_SERVER_EXEC_USER=<non-root-dedicated-OS-account>`: non-root
  execution identity. Root/UID0/GID0 are rejected; no new privileges are granted.
- `DRLINK_MCP_SERVER_ALLOWED_ROOTS=<absolute-worktree-paths-separated-by-colons>`:
  mandatory additional path boundary. Must name existing non-world-writable
  directories. AI Access path scopes and this boundary must **both** match.

Only an authorized operator should configure the above in the Server's optional
MCP service. No environment variables above are enabled by the installer or by
this candidate. Existing Server services, state, /etc/drlink, tokens/keys and
running MCP traffic are not changed.

## Tool matrix (v2.4 candidate)

| Tool | AI Access permission | Execution boundary |
|---|---|---|
| get_server | host-info | root Bridge: uname metadata only, flag-gated |
| get_system_info(endpoint=server:self) | host-info | root Bridge: uname metadata only |
| server_read_file | file-read + explicit paths | unprivileged worker, allowed roots, no symlinks |
| server_write_file | file-write + explicit paths | unprivileged worker; atomic regular-file replace |
| server_delete_file | file-write + explicit paths | unprivileged worker; regular file only |
| server_git | command-exec | unprivileged worker; narrowly allowlisted read-only argv |
| server_run | command-exec + explicit paths | separately opted-in developer Python/Bash test scripts, non-root, argv-only |
| exec(endpoint=server:self) | NEVER | denied (no arbitrary root shell) |
| Existing Managed Host tools | existing permissions | unchanged Agent RPC |

`server_git` intentionally supports only bounded read-only operations
(`status`, `rev-parse`, selected `diff` and `log` flag tuples), not shell
strings, Git hooks, credential exchange or push. The independently opted-in
executor is launched as a child with its own UID/GID, no supplementary groups,
a scrubbed environment, bounded I/O/time and a fixed implementation script.
The root MCP Bridge never invokes a caller-provided command as root.
`server_run` requires both general Server-local executor opt-in and
`DRLINK_MCP_SERVER_DEV_TEST_ENABLED=1` at the Server service. Only selected
`python3 tests/test-*.py`, `bash tests/test-*.sh` and bounded
`python3 -m pytest` forms are admitted without a shell. Git remains
**read-only**; commit/push, arbitrary shell commands and unrestricted package
install/deploy are not yet implemented. The future Desktop Commander
replacement must cover those separately with scoped developer permissions.

File tools reject path traversal, symlinks, nonregular files, protected file
names and secret formats; the worker anchors file operations through directory
file descriptors with O_NOFOLLOW. Operators must **not** include /etc, /var/lib,
PKI, credentials, SSH material or live production content among allowed roots.

## Security tests before acceptance

1. Anonymous/pending/disabled AI Identity and no matching Rule: DENY.
2. Disabled Server-self feature: DENY, even when host-info Rule exists.
3. Authorized read-only discovery: typed Server target and actual uname.
4. Server-self not returned as Agent Managed Host; no fake Client ID.
5. File write/read/delete in an isolated fixture, with literal bytes checked.
6. Traversal, symlink, special file, path outside scope, secret path: DENY.
7. Shell/sudo/Git mutation and unsupported argv: DENY.
8. Existing Managed Host bridge, AI Access and OAuth regression tests.
9. Dedicated OS executor UID/isolation acceptance on a disposable Server
   installation; no assumption that a hermetic unit test proves OS isolation.
10. Real ChatGPT OAuth → Server-self authorized operation and denied operation
    on the actual qualified build with externally valid TLS and audit evidence.
11. Direct ChatGPT HTTPS/OAuth MCP discovery, scoped workspace writes, bounded dev test execution, Git/test/deploy integration and complete ALLOW/DENY user E2E.
12. Exact HEAD full v2.4 product gates, twice where required, before stable.

## Existing Native MCP Preview — preserve installed services

The independent `drlink-mcp-native-preview.service` is already installed,
active, root-owned and listening exclusively on `127.0.0.1:16106`.
The latest *observed installed immutable snapshot* is
`73fce8e3922abbf3f3b6167ace5aa77e7a1642ba`. The primary DRLink
Server, ordinary MCP Bridge, Agent state and public FRP TCP/443 remain
unchanged.

Do **not** run the original `operator-native-mcp-preview.py --apply`
or legacy `operator-native-mcp-upgrade.py --apply` again on an already
installed Preview. Those scripts preserve historical installation/rollback
logic, not this domain change. Use the new, separately audited
`operator-native-mcp-domain.py` for changing the OAuth public hostname.
It takes an exact backup of the existing root-owned unit and explicitly
supports `--rollback`.

Before a real ChatGPT OAuth connection the Server still requires the
chosen, authenticated AI Identity and explicit `server:self` WHITELIST.
The OS-level developer executor gate remains OFF until separately
qualified. This is **connectivity and authentication preparation**, not
permission to run an unrestricted root shell or a completed replacement
of Desktop Commander.

## Deployment state

Feature flags are OFF. No Agent should be installed on a DRLink Server merely
to make it MCP-manageable. Existing server installed artifact versions need not
be overwritten during development. The implementation branch/PR is **not** a
release-qualified artifact; OAuth, public TLS and AI Access changes require
separately approved live configuration.
