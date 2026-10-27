# Data Relay Link v2.4 — Native Server MCP

> Workstream: [Issue #223](https://github.com/datarelay-labs/datarelay-link/issues/223).
> Target: dev-drlink / access.xdr.ooo.
> Public endpoint: **https://mcp.link.xdr.ooo/mcp**.
> Existing public TLS, OAuth, verified identity and Server-self host-info access are established.
> Source qualification and installed full-control acceptance are separate; live evidence is recorded in Issue #223.

## Scope

Native MCP controls the DRLink Server through the existing authenticated Bridge.
It does not require an Agent, central Server Peer, Enrollment Code, new ingress,
or another OAuth approval. This workstream changes the MCP implementation,
its necessary packaging and authorized development-server configuration only.

The full-control profile supports general argv and shell commands, file
creation/edit/read/delete, writable Git, process jobs, and service/package/
deployment commands under an explicitly selected OS account. The restricted
executor remains available when full-control is disabled.

**General command execution grants that account's real OS authority.**
An initial working-directory scope is not a filesystem sandbox. Root requires
a separate local operator opt-in. Authentication, current AI Access, job
ownership and audit remain enforced for every call.

## Authentication and authorization

- The existing OAuth or operator-issued bearer credential resolves a verified,
  enabled AI Identity. OAuth alone does not grant any operation.
- `server:self` is a built-in Server target, distinct from Managed Hosts.
  It is not included in `list_hosts` and never impersonates an Agent.
- Every operation re-evaluates canonical v2.4 AI Access and records ALLOW/DENY.
- Every process read/input/stop call additionally checks authenticated identity
  ownership and the current locally selected execution account/profile.
- A revoked identity, revoked command permission, removed path scope, disabled
  profile or changed account denies subsequent access to retained jobs.
- Child commands receive a minimal environment, not Bridge tokens or the
  Bridge's inherited environment. They may use the configured account's own
  files, groups, Git configuration and OS permissions.

## Operator settings

Configure settings in the existing MCP Bridge service only after source,
security, artifact and rollback checks pass.

| Setting | Meaning |
|---|---|
| `DRLINK_MCP_SERVER_SELF_ENABLED=1` | Enable independently authorized Server-self access |
| `DRLINK_MCP_SERVER_LOCAL_EXEC_ENABLED=1` | Enable local file/command execution |
| `DRLINK_MCP_SERVER_FULL_CONTROL_ENABLED=1` | Select the general command/job profile |
| `DRLINK_MCP_SERVER_EXEC_USER=<account>` | Required existing OS execution account; never chosen by tool arguments |
| `DRLINK_MCP_SERVER_ALLOWED_ROOTS=<absolute paths separated by colons>` | Required initial-cwd/file boundary, intersected with AI Access |
| `DRLINK_MCP_SERVER_DEFAULT_CWD=<absolute directory>` | Optional initial cwd for the existing `exec(endpoint=server:self)` alias |
| `DRLINK_MCP_SERVER_ADMIN_ENABLED=1` | Separate explicit local opt-in required when the selected account has UID 0 |

All execution gates default off. The Bridge service running as root does not
implicitly select root for commands. Existing `NoNewPrivileges=yes` remains
in force; selecting a non-root account does not promise privileged package or
system-service operations. An operator who needs those operations must choose
the intended account and independently enable UID 0 when appropriate.

Allowed roots validate paths and initial cwd; a general shell can subsequently
access anything its OS account permits. Do not describe this profile as a
restricted filesystem or process sandbox.

## Public tools

| Tool | Input | AI Access | Result |
|---|---|---|---|
| `get_server` | None | host-info | Server target and actual hostname |
| `get_system_info` | `endpoint=server:self` | host-info | Actual Server OS identity |
| `server_read_file` | `path` | file-read and path scope | Bounded file bytes |
| `server_write_file` | `path, content` | file-write and path scope | Create or update file |
| `server_delete_file` | `path` | file-write and path scope | Delete regular file |
| `server_run` | `cwd, argv` | command-exec and initial cwd | General argv command and job receipt |
| `server_exec` | `cwd, command` | command-exec and initial cwd | Shell command and job receipt |
| `server_git` | `cwd, argv` beginning with Git | command-exec and initial cwd | Git operations including add/commit/push |
| `server_job_poll` | `job_id`, optional cursors/wait | command-exec, stored cwd, same identity | State and incremental output |
| `server_job_input` | `job_id`, optional `data, eof` | command-exec, stored cwd, same identity | Accepted stdin byte count / EOF |
| `server_job_stop` | `job_id` | command-exec, stored cwd, same identity | Stop managed process group and collect state |

Existing file/process-list and `exec(endpoint=server:self)` aliases also use
the selected full-control profile. Managed Host behavior is unchanged.
When full-control is disabled, the original restricted executor continues
to enforce its read-only Git and selected-test rules; new shell/job tools deny.

Command, writable Git and stdin tools advertise mutating, destructive,
open-world behavior. Optional process settings have typed public schemas and
are validated before execution; they are not incorrectly marked required.

## Process and output contract

- `timeout_seconds`: 1–86,400; default 3,600.
- `wait_ms`: 0–5,000; default 1,000 on starts and 0 on polls.
- Starts return `job_id`, running/completed state, execution account, cwd,
  bounded stdout/stderr, exit status, timeout and duration.
- At most 32 live/retained entries exist. Completed entries expire after ten
  minutes or are reclaimed oldest-first to admit another command. Running
  jobs are never reclaimed to bypass the concurrency limit.
- Each output stream retains at most 1 MiB; each page contains up to 64 KiB.
  Byte cursors, `truncated_before` and `cursor_was_evicted` disclose loss.
  `data_b64` preserves exact bytes across UTF-8/page boundaries; `text` is
  a readable decoded view.
- Stdin accepts at most 64 KiB per request and returns `accepted_bytes`.
  Retry the unaccepted UTF-8 suffix; acceptance always ends on a character
  boundary. EOF is applied only after that request's entire input is accepted.
- Stop and timeout terminate the managed process group. Normal leader exit
  also cleans up remaining same-group descendants before completion.
  The leader is retained until cleanup to avoid signaling a reused process ID.
- Explicitly detached daemons are outside process-group lifecycle management;
  use the OS service manager for persistent services. Inherited output pipes
  are closed with bounded reader cleanup and `output_complete=false` if
  a detached process keeps them open.
- A Bridge restart ends its in-memory job registry and managed running jobs.
  Old job IDs are not portable across restarts.

## Packaging and deployment

Both `drlink_mcp_server_executor.py` and `drlink_mcp_full_control.py` belong
in the Server project manifest and generated Server bootstrap bundle.
The full-control runtime depends on the existing Agent file helper, without
changing Agent behavior. The shared `path_allowed` fix only corrects an
explicit `/**` tree; it grants no implicit path scope.

For this already-running public endpoint, use a reviewed **MCP-only rollout**:

1. Pass the runtime, public HTTP, affected authorization and packaging checks.
2. Preserve existing generated changes, produce a coherent source/artifact
   candidate, verify provenance, push it and verify required exact-head CI.
3. Back up the affected installed modules and MCP-only service configuration;
   record hashes and a rollback receipt. Preserve existing TLS, OAuth, DB,
   frontend, FRP and independent developer processes.
4. Install only the reviewed MCP modules and directly required shared helper.
   Configure the explicitly selected account/profile and the existing AI
   Identity's intended AI Access. Restart only `drlink-mcp-bridge.service`.
5. Check module hashes, active Bridge, unchanged TLS/OAuth metadata and real
   Native MCP ALLOW/DENY receipts. Retain rollback until acceptance completes.

`tools/operator-native-mcp-full-control.py` implements the narrow file transaction.
Its default `--check` is read-only. Apply requires root, an exact clean committed
`--head`, explicit `--exec-user` and `--allowed-root`; UID 0 requires `--allow-root`.
It installs committed Git blobs, writes only the dedicated `zz-native-full-control.conf`,
checks backup/install hashes, and automatically restores affected files after a
failed restart. Rollback refuses later file/permission changes. AI Access remains
unchanged and must be authorized separately; the helper cannot grant tool privileges.

The historical single443, certificate-issuance, Preview, domain and Server-peer
scripts are not this rollout path. Do not rerun them for full-control enablement.
A current tool/platform privilege denial must be reported and respected;
neither another executor nor operator-command substitution bypasses that denial.

## Validation and acceptance

Focused source checks:

```bash
python3 tests/test-mcp-server-full-control.py
python3 tests/test-mcp-server-full-control-public.py
python3 tests/test-mcp-full-control-rollout.py
bash tests/test-project-file-manifest.sh
python3 tests/test-mcp-server-self.py
python3 tests/test-mcp-server-local-executor.py
python3 tests/test-ai-access-mcp-e2e.py
python3 tests/test-mcp-remote-connector-interop.py
```

The runtime suite includes real temporary Git add/commit/push/clone, file CRUD,
general commands, prompt/stdin/EOF, output continuation, bounded registry,
same-group cleanup, account/root opt-in, identity and live-policy denial.
The public suite exercises authenticated HTTP `tools/list` and `tools/call`;
internal handlers alone cannot establish discoverability or public dispatch.

Source/loopback tests do not establish actual ChatGPT acceptance. After the
qualified candidate is deployed, use the genuine existing Native MCP connection
to demonstrate hostname/account, file CRUD, shell/argv, Git write/commit/push
in a disposable repository, process input/output/stop, and the authorized
service/deployment workflow with negative authorization checks.

Request tool refresh/reconnection only after implementation and deployment,
and only if new tool discovery needs it. Keep Desktop Commander until actual
parity is evidenced. Main merge, stable release and the unrelated whole-product
E2E roadmap are outside this MCP-only task.
