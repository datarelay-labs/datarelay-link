# Data Relay Link v2.4 — Native Server MCP

> Workstream: [Issue #223](https://github.com/datarelay-labs/datarelay-link/issues/223)
>
> Candidate status: partial implementation on an isolated feature branch. **Not live-deployed or release-qualified.**
> This document is a security/runbook specification, not evidence of a production deployment.

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
- `remote.xdr.ooo` → `access.xdr.ooo` is a **separate Server-peer transport**
  feature (SMCP-08). A `server:self` selector never tunnels itself to another
  hostname. It requires mutually authenticated Server identity/delegation and
  policy enforcement on the destination before it can be activated.

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
| exec(endpoint=server:self) | NEVER | denied (no arbitrary root shell) |
| Existing Managed Host tools | existing permissions | unchanged Agent RPC |

`server_git` intentionally supports only bounded read-only operations
(`status`, `rev-parse`, selected `diff` and `log` flag tuples), not shell
strings, Git hooks, credential exchange or push. The independently opted-in
executor is launched as a child with its own UID/GID, no supplementary groups,
a scrubbed environment, bounded I/O/time and a fixed implementation script.
The root MCP Bridge never invokes a caller-provided command as root.

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
11. Server-peer mutual-auth identity/revocation/delegation/E2E for SMCP-08.
12. Exact HEAD full v2.4 product gates, twice where required, before stable.

## Preferred: existing central DRLink MCP manages an enrolled Server

**Owner decision (2026-10-26):** Use the existing MCP/OAuth endpoint
`https://remote.xdr.ooo/mcp` as the single ChatGPT entry. The local
DRLink Server at `access.xdr.ooo` connects outward as a **Server Peer**,
reusing DRLink's signed Agent management transport and central AI jobs without
installing any DRLink Agent or OpenAI Tunnel.

```
ChatGPT
  -> remote.xdr.ooo/mcp (existing verified OAuth + AI Access)
  -> central Managed Host "dev-drlink Server" (distinct Server-peer identity)
  -> signed POST /v1/ai-jobs/claim and /complete over HTTPS
  -> dev-drlink Server Peer worker (separate state, not Agent)
  -> explicit local allowlist / unprivileged executor
```

Central management API compatibility has been probed: unauthenticated
`/enroll/preflight`, `/enroll` and `/v1/ai-jobs/claim` all return
**HTTP 403 with validated TLS**. This confirms protected route presence,
**not successful enrollment or authorized ChatGPT calls**.

**Central operator step (must occur on the central DRLink Server, not
dev-drlink):** run the v2.4 public CLI `set enrollment manual`, creating
an independent management-only Enrollment Code (zero published services) for
the Server. Display-once credentials are never to be copied into ChatGPT or
committed to Git. Unlike Agent installation, the Server Peer enrolls through
`lib/drlink_server_peer_enroll.py` into its private
`/var/lib/drlink-server-peer` tree. Its state, ECDSA P-256 key and signed
management identity are separate from both `/etc/frp` and `/etc/drlink`.

An authorized operator stores the display-once manual `id.secret` in a
root-owned mode 0600 file on dev-drlink and then performs:

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026
HEAD_SHA="$(git rev-parse HEAD)"
# The Code file MUST already exist and be chmod 0600, owned by root.
sudo /usr/bin/python3 lib/drlink_server_peer_enroll.py \
  --root /var/lib/drlink-server-peer \
  --central https://remote.xdr.ooo \
  --label "dev-drlink Server" \
  --code-file /root/drlink-server-peer-enrollment-code
# Securely erase the consumed Code file after successful enrollment.
sudo /usr/bin/python3 lib/drlink_server_peer.py \
  --root /var/lib/drlink-server-peer --probe-central
# Install a separate, opt-in Server Peer systemd service; existing DRLink
# Server/Agent/MCP units are preserved.
python3 tools/operator-server-peer.py --preflight --expected-head "$HEAD_SHA"
sudo /usr/bin/python3 tools/operator-server-peer.py \
  --apply --expected-head "$HEAD_SHA"
sudo /usr/bin/python3 tools/operator-server-peer.py --verify
```

The dedicated peer service defaults to **Server info only**. Arbitrary
`exec`, process listing, upload, write/delete and even file reading are
DENY unless explicitly developed/qualified and opted in. The server peer
is not a trusted shell just because it was enrolled. Central AI Access must
independently permit the requesting AI Identity to access **only this newly
enrolled Managed Host** and the `host-info` Permission Object. The central
operator tests this before use:

```text
set permission-object server-info-only permissions host-info
set ai-access drlink-server-read mode whitelist source <VERIFIED-AI-IDENTITY> destination <ENROLLED-SERVER-PEER-NAME> permission server-info-only enabled
test ai-access source <VERIFIED-AI-IDENTITY> destination <ENROLLED-SERVER-PEER-NAME> permission host-info
```

Those CLI commands mutate the **central** Server's authoritative AI Access
state and must be applied only to the exact verified identity and target; do
not widen an unrelated Rule. A central operator must create the Enrollment
Code and explicitly authorize the AI Identity. The ChatGPT MCP connection
should then discover the Server Peer in `list_hosts` and return system info
for the precise enrolled target; a different target/permission must DENY.

No public TLS certificate is required on `access.xdr.ooo` for this
outbound Peer architecture: the central `remote.xdr.ooo` TLS and OAuth
issuer remain authoritative. Existing FRP port 443 must not be repurposed.

## Development Server operator rollout (independent direct preview)

Use the opt-in operator-only `tools/operator-native-mcp-preview.py` for an
isolated DRLink Server Native MCP preview on `dev-drlink`/`access.xdr.ooo`.
It installs **only a separate loopback service** on TCP `127.0.0.1:16106`,
preserving existing DRLink Server, Agent, public 443 and MCP services. The
installer makes a consistent root-only SQLite backup before activation and
includes verification and rollback. Exact Git SHA is mandatory.

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026
HEAD_SHA="$(git rev-parse HEAD)"
python3 tools/operator-native-mcp-preview.py --preflight --expected-head "$HEAD_SHA"
sudo /usr/bin/python3 tools/operator-native-mcp-preview.py --apply --expected-head "$HEAD_SHA"
python3 tools/operator-native-mcp-preview.py --verify
```

If the first install created the root-owned snapshot and DB backup but
stopped immediately with `Connection refused` on port 16106, **do not
rerun `--apply`**. In that case, the `Type=simple` service may not have
bound its listener before the first probe. Update only the operator script
and use `--resume` with the **original installed snapshot commit**:

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026
git pull --ff-only origin feat/v240-server-native-mcp-20261026
sudo /usr/bin/python3 tools/operator-native-mcp-preview.py --resume \
  --expected-head 446f372c979e1cfbec7a3ffade3b32912dda0499
python3 tools/operator-native-mcp-preview.py --verify
```

`--resume` checks the exact root-owned service definition and immutable
snapshot against Git before starting the existing unit. It does not
modify the primary Server, recreate the backup, or install another Agent.
The listener readiness check retries only connection/transport errors,
with a finite timeout; OAuth or MCP validation failures are not treated as
startup latency.

If it still fails, inspect the Preview journal and **do not retry full
installation**. Roll back only the Preview unit if necessary:

```bash
journalctl -u drlink-mcp-native-preview.service -n 80 --no-pager
sudo /usr/bin/python3 tools/operator-native-mcp-preview.py --rollback
```

Preview defaults: `server:self` discovery capability ON but **AI Access
authorization still requires an explicit verified AI Identity and Rule**.
The Server-local developer file/Git executor remains OFF. **Direct MCP mode**
(using `access.xdr.ooo/mcp` itself as a separate ChatGPT connector) is not
ready without a trusted public TLS certificate and external OAuth routing.
The preferred **central Server Peer mode above** avoids that requirement
entirely by reusing `remote.xdr.ooo/mcp`. Never skip TLS verification or
overwrite the existing public 443 listener.

## Deployment state

Feature flags are OFF. No Agent should be installed on a DRLink Server merely
to make it MCP-manageable. Existing server installed artifact versions need not
be overwritten during development. The implementation branch/PR is **not** a
release-qualified artifact; OAuth, public TLS and AI Access changes require
separately approved live configuration.
