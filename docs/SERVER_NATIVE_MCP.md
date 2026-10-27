# Data Relay Link v2.4 — Native Server MCP

> Workstream: [Issue #223](https://github.com/datarelay-labs/datarelay-link/issues/223)
>
> Current public endpoint: **https://mcp.link.xdr.ooo/mcp**, hosted on dev-drlink/access.xdr.ooo.
> The owner completed on-host Let's Encrypt, OAuth approval and `server:self` host-info authorization.
> Native `get_server` and `get_system_info` succeeded through ChatGPT. Do not repeat TLS setup or enrollment.
> **Full-control implementation is WIP, not deployed or acceptance-qualified.** The live developer executor remains OFF.

## Full-control WIP — owner requirement, 2026-10-27

The owner requires general shell/argv commands, writable Git (including
add/commit/push), package and service management, and deployment operations
using an explicitly selected operating-system account. Root administration
requires a separate operator-controlled opt-in; per-call OAuth/AI Access
and attribution remain mandatory. A command working-directory scope is
**not** a filesystem sandbox once general command execution is authorized.

Source `lib/drlink_mcp_full_control.py` and Native Bridge dispatch are now
present. The runtime includes operator-selected account launching, general
commands, bounded process-output pages, owner-bound stdin/termination, and
existing Agent file/process helpers. Installation/upgrade source manifests
include the module. Existing restrictive mode is retained as the default,
not presented as the completed owner-requested full-control feature.

**Do not enable full-control on this WIP build.** Remaining acceptance blockers:

- The MCP tool descriptors still advertise the old read-only/test-only
  contract. A tool edit to add truthful side-effect annotations and shell/job
  schemas was platform-blocked. New job methods are not discoverable yet.
- The output reader still uses buffered `read(8192)`; prompt-sized output
  before process exit is not qualified. Its attempted fix was blocked.
- Writing the new isolated full-control test suite was blocked; the suite
  is absent and was not executed. Existing Server-self/local-executor
  regression results do not establish full-control acceptance.
- A real full-control account/job/Git/file acceptance suite, final packaging
  provenance, an authorized rollout and actual ChatGPT workflow tests are
  required before deployment or Desktop Commander removal.

The earlier restricted-executor sections below describe the currently
installed mode. They do not override the owner's full-administration goal.
Current implementation and exact tool-denial evidence are tracked in
Issue #223, including comment 6441365580.

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
The native DRLink HTTPS frontend, certificate issuance/renewal, MCP Bridge
and OAuth authorization must run on **access.xdr.ooo itself**. Cloudflare is
not a transport component, and no second machine or central Managed Host
enrollment is involved. FRP TCP/443 may change mode only after a qualified
maintenance cutover and rollback plan.

**Hard requirements before removing Desktop Commander:** full MCP tool
coverage required for development, publicly trusted TLS and correct canonical
OAuth resource/issuer, explicit AI Access rules, user-accessible full-write
MCP entitlement, real allow/deny E2E through ChatGPT, and recoverable
rollout. Until then keep Desktop Commander connected.

## Direct HTTPS MCP on this host, with Let's Encrypt (owner-selected)

**Canonical endpoint:** `https://mcp.link.xdr.ooo/mcp`.
**Actual Server:** dev-drlink / access.xdr.ooo (public DNS verified to match this host's IPv4 interface).
**Public Native MCP backend after supported single443 reinstall:** the installed
DRLink Bridge at `127.0.0.1:6103`. The older isolated v2.4 Native Preview at
`127.0.0.1:16106` remains separate and does not serve public traffic.
OAuth issuer must be `https://mcp.link.xdr.ooo`.

**Explicit operator decision (2026-10-26):** Use a real Let's Encrypt
certificate issued and renewed **on this development Server** and the
native DRLink MCP/HTTPS stack. No Cloudflare Tunnel, OpenAI Tunnel,
additional Server Peer, Agent, or second host. DNS is already correct.
No private-CA or insecure TLS bypass is an acceptance result.

### Confirmed live constraints

- DNS A for `mcp.link.xdr.ooo` resolves to the same public IPv4 currently assigned to this development Server. Verify the match dynamically before changing services.
- Existing FRP Direct listener owns TCP/443; its self-signed certificate
  is not a ChatGPT-trusted web certificate.
- TCP/80 has no listener and a remote TCP/80 attempt returned connection
  refused. The public firewall must permit port 80 while the ACME HTTP-01
  challenge listener is active; refusal without a listener is not enough
  to distinguish firewall policy from a closed service.
- Ubuntu 24.04 packaged `python3-acme` is present (version 2.9.0).
  DRLink has a native `AUTO_ACME` issuer and controlled TLS renewal flow,
  based on ACME HTTP-01.
- The product intentionally denies public MCP TLS configuration when
  deployed in `direct` mode. The **supported product architecture**
  serves public HTTPS MCP in `single443` mode, with an nginx SNI frontend
  separating FRP from MCP. A Direct→single443 mode cutover is **not
  zero-downtime** for existing Agents and requires a maintenance window and
  explicit `SWITCH` confirmation. Merely installing a certificate is
  NOT sufficient to make TCP/443 route to the MCP HTTP service.

### Read-only readiness check

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026
python3 tools/native-mcp-letsencrypt-preflight.py
```

No Cloudflare, DNS, Agent, or FRP changes are made by this probe.

### Development Server activation (explicitly approved on 2026-10-27)

The owner confirmed there are no existing Agent deployments to preserve on
this development Server and authorized reinstall or mode conversion. Use
the **current exact, clean and pushed v2.4 development candidate source**:
the installed earlier v2.4 development build (release manifest source
`4a5d526a…`) lacks the newer `drlink_mcp_server_executor.py` and
therefore would not implement the requested Native Server MCP operations.

A guarded operator script implements the entire supported product sequence.
It retains root-only DRLink configuration/SQLite/PKI backup and validates
restore readability before modifying a service. The distro nginx service is
stopped and disabled only after verifying that both `sites-enabled` and
`conf.d` are empty; the installer then owns its separate
`drlink-frontend.service` and rebinds FRP through supported single443 mode.

```bash
cd /home/aella/datarelay-link-worktrees/feat-v240-server-native-mcp-20261026
bash tools/operator-native-mcp-single443.sh --check
# In direct owner SSH, the supported privileged deployment:
sudo bash tools/operator-native-mcp-single443.sh --apply
```

The operator must type `SWITCH` at the SSH TTY. The script performs the
same supported native installer action with
`FRP_DEPLOYMENT_MODE=single443`, verifies DRLink services, configures
the built-in AUTO_ACME client, issues and activates the certificate, and
verifies trusted public HTTPS + MCP anonymous 401 + OAuth issuer/resource.
It does **not** disable certificate verification or configure an unrelated
Cloudflare ingress. The Server-self metadata tool is independently enabled,
while the developer executor remains disabled until explicit AI Access and
OS isolation gates are accepted.

If the mode switch succeeds but Let's Encrypt fails because inbound TCP/80
cannot reach the temporary HTTP-01 challenge route, open TCP/80 for the
issuance/renewal flow, then run:

```bash
sudo bash tools/operator-native-mcp-single443.sh --issue
```

Read-only public validation at any time:

```bash
bash tools/operator-native-mcp-single443.sh --verify
```

Native DRLink CLI operations performed by `--issue` are:

```text
set mcp-tls hostname mcp.link.xdr.ooo
set mcp-tls mode auto-acme
system certificate preflight
system certificate issue
system certificate status
```

4. Verify a real publicly trusted TLS chain on
   `https://mcp.link.xdr.ooo/mcp`, OAuth protected-resource metadata,
   authorization-server issuer, real anonymous HTTP 401, correct
   authentication, and an explicit `server:self` AI Access rule.
   The actual ChatGPT user must then connect the custom MCP endpoint and
   demonstrate allowed and denied tool calls.
5. The independently installed Native MCP Preview is a development
   candidate and is NOT a replacement for the installed public DRLink
   Bridge until the source and public listener are reconciled. Do not
   remove Desktop Commander until the real user file/test/Git/deploy
   E2E proves parity. Keep the rollback to the previous FRP deployment
   and certificate/config backups before switching.

**Execution evidence:** the direct root installer call is not yet made
from this ChatGPT session because the connected Remote Desktop Commander
tool returned `Command not allowed` for direct `sudo -n id -u`. Owner
authorization does not bypass that tool-level denial; root changes must
run from the owner's authenticated SSH terminal. As of this note, no
mode switch or real public Let's Encrypt certificate has been verified.

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
