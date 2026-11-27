# Data Relay Link — Native Server MCP execution contract

> **Status:** approved target redesign, not installed-runtime qualification.
> Canonical user workflow and authorization semantics: [AI_ACCESS_MCP.md §4.1](AI_ACCESS_MCP.md#41-canonical-execution-account-contract).

Native MCP controls `server:self` without an Agent on the Server; Managed Hosts use the authenticated Agent path. Both expose the same account-selection semantics and capability discovery. Existing Server and Managed Host tools remain compatible. No new gateway, sandbox, or OAuth model is required.

General command execution grants the chosen OS account's actual authority. Native execution defaults off unless locally enabled. An explicit local root approval and a matching AI Access rule for root are both mandatory. A privileged Bridge does not implicitly grant root. Child execution preserves the selected account's UID/GID, groups, HOME, Git and file ownership context without inheriting Bridge credentials. Existing OS escalation privileges are real authority, not a DRLink sandbox.

Every invocation rechecks current AI Access, target-local account eligibility and applicable paths. Job ownership binds identity, target, selected account/UID and cwd; subsequent input/poll/stop never changes account. Deny unauthorized/revoked access and terminate tracked jobs on loss of grant. Detached processes remain outside managed lifecycle.

## Connection renewal

Public tool security schemes and both HTTP/tool authentication challenges request
`drlink.ai offline_access`. The token endpoint grants a refresh token only when
the client requested and was authorized for `offline_access`; an explicitly
primary-only grant stays primary-only. AI Access and OS execution permissions
are independent and unchanged.

Access tokens last one hour. Refresh tokens last 30 days and rotate on each
successful renewal, restarting that 30-day window. A connection with an
unexpired refresh token can renew without a new operator consent.
Revoked/expired refresh tokens require a new authorization flow.

A pre-existing ChatGPT connection reporting `oauth_refresh_token_missing`
cannot be repaired by restarting the server: the host has no refresh token.
After deploying this fix and refreshing cached tool metadata if needed,
reconnect that existing app once and complete the normal OAuth/operator
approval. Do not recreate the app, copy credentials, disable expiry, or
silently broaden a registered client's scope. Verify the new connection
renews after access-token expiry before calling host interoperability fixed.

## Operator settings and public tools

The canonical `set mcp-server` menu combines public endpoint, TLS and local execution setup; Diagnostics is the second item. Reuse an active valid certificate, preserve the existing approved ceiling and explicitly review new account eligibility. Optional dedicated `drlink-mcp` preparation is not a remote grant. Preserve Linux ACL preparation, ownership, no privileged-group fallback, rollback on failed activation and truthful Unknown diagnostics. The rule binds identity-specific accounts/default, not a second global execution-user setting.

The public rule wizard is the account configuration entry point. Review the local execution ceiling and permitted accounts together with the AI rule; no second mandatory manual environment-variable or path configuration for normal setup. The local executor enforces allowed accounts and paths independently of the central rule. Use root for explicit full administration, a real project owner for development, or a locally approved read-only reader. The existing `drlink-mcp` user remains optional, not mandatory. Existing singleton settings are migration inputs only; do not reintroduce a global execution account as the target design.

| Tool family | Target contract |
|---|---|
| `get_server`, `get_host`, `list_hosts` | Discover identity-filtered effective execution context and capabilities; Server-self remains distinct from Managed Host inventory |
| `server_run`, `server_exec`, `server_git`, Managed Host `exec` | Optional `run_as` and optional cwd; default account/cwd from authorized context |
| Existing file read/write/delete/upload/download aliases | Optional `run_as`; identical rule/local path checks and OS ownership |
| `list_processes` | Read-only capability or approved account context, according to effective rule |
| `server_job_poll/input/stop` and Managed Host job equivalents | Bound original job account and identity, no account override |

Keep existing tool names/argument compatibility, extend Managed Host parity without replacing the transport. Expose only supported capabilities. New optional parameters are genuinely optional in public JSON schemas. Existing clients omitting them use their explicitly authorized default. Tool descriptions explain account selection; do not classify command strings to choose root. All errors identify the failing boundary, with authorized context only. Command, writable Git, stdin and mutation tools retain accurate destructive/open-world annotations. The canonical path/default, overlapping-rule, root, migration and diagnostic semantics are in AI_ACCESS_MCP.md.

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

Implement in the existing Bridge, native executor, Agent execution path, shared authorization and public CLI/configuration code. Package the actual changed modules and Agent payload through the existing manifest and immutable build process. Migrate legacy singleton Server settings (including the old execution user, allowed roots, default cwd and administrator opt-in) and existing Agent behavior without widening effective grants. A legacy rollout helper may remain for compatible historical artifacts only; it is not the target user configuration procedure.

Use exact-HEAD, reviewed development qualification before rollout. Preserve TLS/OAuth, DB, audit, FRP, unrelated services and existing operator permissions. Back up changed configuration and runtime, verify artifact hashes, apply atomically or restore the previous effective state on failure; report incomplete rollback. No production deployment or permission change is authorized by this document. A current tool/platform denial is binding. Reconnection is required only for actual credential or host tool-discovery changes, not ordinary policy edits.

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

Extend the existing tests with multi-account/default selection, no implicit root, root opt-in per identity and target, conflicting rules, missing account/cwd, scoped paths, file ownership, migration without expansion, Agent parity and real natural-language workflow tests.

Request tool refresh/reconnection only after implementation and deployment,
and only if new tool discovery needs it. Keep Desktop Commander until actual
parity is evidenced. Main merge, stable release and the unrelated whole-product
E2E roadmap are outside this MCP-only task.
