# Windows Client design

Base: current architecture at `origin/feature/macos-client-current-main` (`afc446c`)
Branch: `feature/windows-client-current-main`
FRP pin: **0.71.0** (Windows amd64 zip SHA256 pinned in `lib/frp-common.sh`)

## Reusable server protocol

Windows does **not** fork enrollment. It reuses:

| Area | Contract |
| --- | --- |
| Bootstrap | `POST /bootstrap/redeem` accepts internal `bt1.<id>.<secret>` only. The six-character root-path locator selects entry code only; independent authorization must precede credential issuance |
| Enroll | `POST /enroll` — enrollment HMAC or mgmt ECDSA |
| CA | `GET /ca.crt` — DER SHA-256 pin via `FRP_ALLOCATOR_CA_SHA256` |
| Token | OpenSSL `Salted__` + PBKDF2-HMAC-SHA256 (200000) + AES-256-CBC |
| Mgmt identity | ECDSA P-256 / SHA-256, canonical JSON schema 1 |
| Services | TCP presets; ports allocated by existing registry |
| single443 | `frp_transport=wss`, path `/~!frp` (FRP hard-coded) |

## Linux-specific vs Windows

| Concern | Linux | Windows |
| --- | --- | --- |
| Installer | `bootstrap-client.sh` | `bootstrap-client.ps1` |
| Paths | `/etc/frp`, `/etc/drlink` | `C:\ProgramData\drlink\` |
| Process | systemd | background process + optional autostart later |
| machine_id | `/etc/machine-id` or random `client-id` | random id persisted under ProgramData |
| Crypto CLI | OpenSSL | .NET `System.Security.Cryptography` |
| HTTPS client | curl `--cacert` | curl.exe when present; else request-local .NET pin |

## Filesystem

```
C:\ProgramData\drlink\
  bin\frpc.exe
  config\frpc.toml
  state\client-state.json
  state\client-id
  state\client-identity.key.dpapi
  state\client-identity.pub
  state\client-identity.mac
  certs\allocator-ca.crt
  logs\frpc.log
  logs\frpc.pid
  tools\FrpClient.ps1
  version
```

Sensitive files: ACL for `SYSTEM` + `Administrators` only.

## Zero-touch UX

`set enrollment zero-touch` → platform menu → Linux or Windows (RDP-first).

Fixed Windows entry target: `iex(curl.exe -kfsS https://remote.xdr.ooo/A3xK9m|Out-String)` (60 characters at the reference authority). Administrator PowerShell with native curl.exe, no client-side DataRelay prerequisite. Public/private HTTPS use the same form. All subsequent artifact downloads, verification, independent enrollment and retry belong to Bootstrap. See [canonical contract](ZERO_TOUCH_REGRESSION_CONTROL.md); native acceptance pending.

## Lifecycle semantics

**ENROLL ONCE / RUN MANY TIMES**

- First run: redeem + enroll + write state/config + start drlink-client
- Later: repeating the same entry command resumes existing identity/config/ports without new enrollment; implementation and native verification pending

Autostart (Service / Task Scheduler) is **optional**, not MVP-blocking.

## Security invariants

- No global TLS bypass; fixed entry target has an initial request-local `-k` exception, which does not authenticate the peer. This is a recorded security qualification issue.
- `/ca.crt` may use one-shot unauthenticated TLS; fingerprint must match
- All later calls use pinned CA
- No ticket/token/private key in logs
- Zip-slip safe FRP extract
- Quoting-safe PowerShell command generation

## Test strategy

- Cross-language ECDSA + token vectors (Python ↔ PowerShell)
- Local FRP TCP forwarding E2E on `windows-latest`
- Mock allocator HTTPS where feasible
- Linux `./tests/run-all.sh` must remain PASS
