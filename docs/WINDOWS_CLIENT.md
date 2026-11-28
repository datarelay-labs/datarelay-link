# Windows Client Guide

Supported OS: **Windows 10 / 11 / Server 2019+** (amd64), Windows PowerShell **5.1** or PowerShell **7+**.

This client reuses the existing Data Relay Link allocator protocol (bootstrap redeem, enroll, CA pin, PBKDF2 token wrap, ECDSA management identity). It does **not** introduce a Windows-only enrollment API.

FRP pin: **0.71.0** Windows amd64 (`frp_0.71.0_windows_amd64.zip`).

## Install layout

```text
C:\ProgramData\drlink\
  bin\frpc.exe
  config\frpc.toml
  state\client-state.json, client-id, client-identity.*
  certs\allocator-ca.crt
  logs\frpc.log, frpc.pid
  tools\FrpClient.ps1, drlink.cmd, frp-client.cmd
  version
```

For non-Windows test hosts (pwsh on Linux CI), set `FRP_WINDOWS_ROOT` (default `/tmp/drlink-windows-test`).

## Zero-touch enrollment

On the Server, select Windows and the enrollment profile. Send only the generated one-line command; the fixed target for administrator PowerShell is:

```powershell
iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9mP2|Out-String)
```

Issuance grants one automatic first-claim registration; share the short command privately. No separate certificate registration, installer filename, hash, enrollment ID or DataRelay prerequisite. Public/private HTTPS use the same form. This target requires native Windows qualification. `-k` disables initial peer certificate authentication; the later stages must retain artifact integrity, actual authenticated connections and automatic first-claim enrollment. See [canonical contract](ZERO_TOUCH_REGRESSION_CONTROL.md).

### What zero-touch does

1. Fetches `/ca.crt` with a **one-shot** TLS exception, then pins DER SHA-256 (`FRP_ALLOCATOR_CA_SHA256`). Later calls use the pinned CA only — **no permanent global TLS bypass**.
2. Redeems the bootstrap ticket (`POST /bootstrap/redeem`).
3. Generates an ECDSA P-256 management identity (DPAPI-wrapped private key on Windows).
4. Enrolls (`POST /enroll`) with enrollment HMAC + public key.
5. Decrypts the FRP token (OpenSSL `Salted__` + PBKDF2-HMAC-SHA256 iter 200000 + AES-256-CBC).
6. Writes `frpc.toml` and downloads `frpc.exe` (HTTPS + SHA256 verify, zip-slip safe).
7. Starts `frpc` in the background.

### ENROLL ONCE / RUN MANY TIMES

Target retry behavior: the same entry command detects existing completed identity and config, reports success or resumes the existing service without redeeming a new credential. Port reservations and machine identity stay stable across restarts. This behavior requires implementation and native acceptance.

If enrollment finished but binary download/start did not (`install_status=enrolled_incomplete`), re-running the installer **resumes** with the same identity and reserved ports — it does not redeem a new ticket or mint a new management key.

### Zero-service (management-only)

When the redeemed ticket carries `services: []`, Windows keeps an empty service list. It does **not** invent an RDP mapping. Management identity remains enrolled; `frpc` is not started until a service exists.

### TLS

Pinned allocator CA verification and hostname/IP SAN checks both apply on the .NET HTTPS path. A trusted CA with the wrong hostname fails. Set `FRP_WINDOWS_FORCE_DOTNET_HTTP_HTTP=1` only in tests to exercise that path; production prefers `curl --cacert` when present.

### Updates, PID, secrets

- `drlink system update engine` refreshes pinned `frpc.exe` with SHA256 verify; failure restores binary, metadata, config, and prior running/stopped state (`RECOVERY_REQUIRED=YES` if rollback itself fails).
- `drlink system update product` obtains the enrolled Server-qualified Windows bootstrap over pinned HTTPS, checks channel, immutable source and SHA256SUMS, and verifies the downloaded SHA256 before invoking upgrade mode. No new enrollment is performed. `FRP_WINDOWS_PROJECT_SRC` remains an explicit reviewed offline source option. Native Windows qualification is required before release.
- `drlink system version` prints both the installed candidate **Source HEAD** and the packaged **Content Source HEAD**. `Source HEAD: UNKNOWN` means verified candidate provenance is missing; do **not** edit `version` or provenance files to match the Server. To refresh management tools on an **already enrolled** Agent, run `drlink system update product` to obtain the verified Server artifact (or use an explicitly reviewed offline source package) as documented in `docs/UPGRADE.md`. **Do not rerun the Zero-Touch installer or re-enroll**; the installer intentionally rejects an existing enrollment. A successful local-source refresh does **not** itself prove Server-qualified source attestation. Recheck `system version` and keep exact-HEAD release qualification on HOLD while Source HEAD remains UNKNOWN or mismatched.
- Check modes are distinct: `system update product -Check` checks the project-update path and `system update engine -Check` checks the Server-provided Relay Engine without applying it. `system update check-engine` is Server-only.
- Stop kills only a PID whose recorded exe matches the managed `frpc.exe`.
- Secret ACL application is fail-closed on Windows.
- After upgrading a pre-v2.4 Windows Agent, run `drlink system synchronize` once. Existing enrolled services are promoted to canonical Remote Services with their existing public ports when the Server catalog provides an unambiguous matching Service Object. ConfigurationBundle export/apply fails closed until that convergence completes.
- A Remote Service becomes `HEALTHY` only after the owned current `frpc.exe` process logs a successful proxy start in its current Server connection and the Server acknowledges the same endpoint through the signed status API. Old log entries, a replaced process/configuration, failed integrity verification, or a mismatched endpoint cannot establish health. Stable lifecycle heartbeats report status without restarting active Remote Services.

## Windows native AI executor (candidate)

Windows install/update protects the installed product root, bin, tools, lib and identified code/provenance files against untrusted write/replace, reparse-point and multiply-linked-file substitution. It preserves existing enrollment and local profile; OS ancestor ACLs are not changed. The local status distinguishes unsafe installed code ACL from absent/invalid execution opt-in. A verified upgrade repairs the product-owned tree, not a potentially compromised operating system. Verify the installed Agent version and Server-observed readiness after updating.

The installed lifecycle worker does not automatically claim AI jobs merely because an AI Access Rule grants full management. The local operator must separately authorize the existing worker account and local file roots. No installation or upgrade creates or enables `state/ai-executor.json`; existing enrollment, policy and ports are unchanged. Local activation is a separate security-sensitive operation. The profile format is:

```json
{"enabled": true, "account_sid": "S-1-5-18", "allowed_roots": ["C:/ApprovedData"], "allow_command_exec": false}
```

The example SID is the existing SYSTEM lifecycle account, not a default grant. A local administrator must review the execution account, roots and optional command authority, and protect the profile and state using the existing product ACL contract. The profile, product code and its directories must have trusted administrative ownership and no untrusted effective write/replace rights. The worker fails closed on an absent, invalid, insecure or wrong-account profile. `system diagnostics` reports local opt-in separately from Server-observed executor readiness. Set `allow_command_exec` only after expressly approving the selected account's real OS authority; it is not a filesystem sandbox. File operations are bounded to 1 MiB and both policy and local roots. Existing-file writes use an exclusive verified handle to preserve ownership/ACL, restoring bounded prior bytes on ordinary write failure; an abrupt system failure is not an atomic-overwrite guarantee. Native command execution requires containment before delivery and is bounded to 30 seconds and capped output. Lifecycle synchronization and signed AI claims have independent retry clocks. A Remote Service sync failure does not disable a locally opted-in AI executor; the Server still authorizes each signed claim. Diagnostics show a bounded, timestamped local Worker receipt (no credentials or request bodies), including separate synchronization and AI failure classes. A missing or stale receipt is NOT TESTED, and even CLAIM_OK is not a substitute for Server-observed readiness. Candidate native OS tests and real installed-host E2E are required before qualification.

## RDP

Default Windows preset exposes TCP **3389** (`preset` treated as RDP in `drlink system info`):

```text
mstsc /v:PUBLIC_HOST:REMOTE_PORT
```

### Security caveats (honest)

- This tool does **not** enable Remote Desktop, open firewall rules, or set Windows credentials.
- Prefer **Network Level Authentication (NLA)** and strong local/domain accounts.
- Treat the public mapping like any internet-exposed RDP service; use VPN or allowlists when possible.
- The FRP token and bootstrap ticket are secrets — never paste them into tickets, chat, or logs.

## Multi-service

Pass `-ServicesJson` with a JSON array of services (`id`, `local_ip`, `local_port`, `preset`, optional `name`). SSH login usernames are **not** accepted, stored, or sent by Data Relay Link; specify the account in your SSH client when connecting. Client-side `preset: "rdp"` is sent to the server as `custom` (server allow-list is `ssh|http|https|custom`) while local state keeps RDP-friendly display.

## single443 / WSS

When the allocator returns `frp_transport=wss`, the client writes:

- `serverPort = 443`
- `transport.protocol = "wss"`
- `transport.tls.trustedCaFile` = pinned allocator CA

FRP hard-codes the websocket path `/~!frp` (not configurable).

## LAN gateway

A Windows PC can forward LAN targets by setting `local_ip` to a reachable LAN address (same semantics as Linux). Ensure Windows routing/firewall allows frpc to reach that target. This project does not reconfigure host firewall or routing.

## Interactive CLI

Run `drlink` without arguments in an administrator PowerShell or Command Prompt to open the Agent Host command prompt. Use `?` or `help commands` for discovery, Tab for command and local Remote Service completion, `menu` for guided navigation, and `exit` to return to the original shell. For example, enter `show remote-services` inside the prompt. The shell and menu invoke the same canonical CLI handlers as one-shot `drlink show remote-services`; confirmations and server-owned resource restrictions are unchanged. Guided Remote Service creation/edit is available in the interactive prompt. The initial completion inventory is local and does not perform network requests. This interactive UX requires native Windows console acceptance on the exact candidate.

## Lifecycle

```text
tools\drlink.cmd show status
tools\drlink.cmd show agent
tools\drlink.cmd show remote-services
tools\drlink.cmd show remote-service <NAME>
tools\drlink.cmd set remote-service <NAME> destination <DEST|this-host> service <SERVICE> enabled|disabled
tools\drlink.cmd unset remote-service <NAME>
tools\drlink.cmd system info
tools\drlink.cmd system pause
tools\drlink.cmd system resume
tools\drlink.cmd system restart
tools\drlink.cmd system autostart enable|disable
tools\drlink.cmd system synchronize
tools\drlink.cmd system update product
tools\drlink.cmd system update engine
tools\drlink.cmd test configuration <FILE|->
tools\drlink.cmd system export configuration <FILE>
tools\drlink.cmd system diff configuration <FILE|->
tools\drlink.cmd system apply configuration <FILE|->
tools\drlink.cmd system diagnostics
tools\drlink.cmd system uninstall
```

| Command | Behavior |
| --- | --- |
| `system pause/resume/restart` | Manages the local Agent runtime while preserving identity and Remote Service intent |
| `show/set/unset remote-service(s)` | Canonical Agent Remote Service lifecycle; Service Objects are resolved from the synchronized Server catalog |
| `show/set/unset remote-access` and `internet-access` | Server-only policies; the Windows Agent rejects these operations without changing state and directs the operator to the DRLink Server |
| `test/system ... configuration` | Canonical Agent ConfigurationBundle validation, diff, export and atomic apply surface |
| `system info` | Prints connection details without secrets |
| `system update product/engine` | Separates Data Relay Link management updates from Relay Engine updates |
| `system uninstall` | **LOCAL SOFTWARE REMOVED, SERVER RESERVATIONS PRESERVED**; removes the product autostart task |
| `system autostart` | Show / enable / disable the product Scheduled Task (`DataRelayLinkClient`) |

## Reboot / autostart

Enrollment with enabled services registers a product-owned Scheduled Task
named **`DataRelayLinkClient`**. Older installs may still have
`FRPAutoDeployClient`; product-owned legacy tasks are migrated on the next
autostart register/uninstall. It runs `drlink system resume` as **SYSTEM** at
system boot (ONSTART), so `frpc` comes back without an interactive login.
Management-only (zero-service) clients do not register the task. Use
`drlink system autostart` to inspect, enable, or disable it. Enrollment state
under `ProgramData` persists across reboot.

## Unsupported / out of scope

- ARM64 Windows packages (amd64 only in this release)
- Automatic firewall changes
- Automatic RDP enablement or credential provisioning
- Forked Windows-only enrollment APIs

## Security summary

- No `irm | iex`
- No secrets in `client-state.json` or status/info output
- CA pin required for first enrollment
- Identity private key: DPAPI on Windows; plain restricted file only under Linux test root (`FRP_WINDOWS_ROOT`) with a warning
