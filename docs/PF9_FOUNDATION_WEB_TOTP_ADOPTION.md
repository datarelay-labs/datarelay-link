# PF-9 Link Web — Shared Foundation TOTP Wheel Adoption

**Status:** DRLink 3.0 optional Web **source candidate**, not deployed to
running hosts and not released. Work Packet
[#185](https://github.com/datarelay-labs/datarelay-link/issues/185).
Stacked on Link PF-5B [PR #183](https://github.com/datarelay-labs/datarelay-link/pull/183).
This does not touch Link 2.4 host/FRP or the existing active, dirty
PF-5B development worktree.

## One shared security implementation

The Web-only installation ships **exactly one** reviewed Foundation
`datarelay-onprem-security==0.10.0.dev0` Python wheel, version pinned
to Foundation source `59b8199d6182e0bed2b25307736edb4dad32a246`.
The wheel is the same 36,276-byte artifact as Control's PF-9 integration,
SHA256:

`6c7c4c8b425fb181e0c10c61aa7ec4ea47c24121379db2c5230251a3bdbc40db`

`lib/drlink_foundation_security.py` checks the **actual wheel byte hash,
regular-file type and expected size before import**. It then imports its
cryptographic functions directly from the zip wheel; a preloaded replacement
from a different Python site-packages path is rejected. No `pip`, internet,
mutable repo ref, second TOTP algorithm or external running service is
required. Missing/mismatched wheel fails closed for the optional Web
service; it does not disable the independent DRLink Core service.

The explicit `lib/web-project-files.manifest` copies the wheel and helper
into `/usr/local/lib/drlink` alongside
`drlink_web_auth.py`; `install-web.sh` already respects that manifest.
`uninstall-web.sh` removes exactly these optional Web files and leaves
Core SQLite, protected MFA secrets/recovery state and host networking
untouched.

## What is actually connected

The **real existing** `drlink_web_auth.py` functions now delegate:
- `generate_totp_secret` → Foundation's 160-bit secret generator;
- `totp_code` → Foundation's standard RFC 6238 6-digit/30-second code
  while preserving Link's original `(code, counter)` return type;
- `verify_totp` → Foundation's bounded +/-1 30-second tolerance and
  replay-counter comparison, while preserving native input whitespace
  trimming and rejection of invalid codes.

The Link Web Core still owns the **encrypted** TOTP seed, SQLite
`mfa_required` default OFF, enrollment/recovery code lifecycle, rate
limits, sessions, token revocation, actor roles, and audit. No
configuration, password, key or policy is changed in a running system.

## Still missing before the owner's full PF-9 acceptance

- Link 3.0 Web currently accepts password and OTP in a **combined login
  submission** (plus an enrollment flow). The requested password-then-OTP
  two-stage screen/short-lived pre-auth challenge must be implemented and
  directly tested separately. A shared TOTP library does not create it.
- Host **SSH** IP allowlist is not the existing DRLink 2.4 FRP remote-service
  access ACL. Management SSH and Web UI/API source ACL require independent
  privileged host enforcement, current-user lockout preview, out-of-band
  recovery and verified timed rollback before they can be advertised.
- Shared Administration capability gates must accurately show unavailable
  features, rather than a clickable fake configuration panel.
- Native Web MFA + recovery/multirole tests, optional Web install/uninstall
  and bundle integrity, user Chromium and two-persona Full User E2E must
  PASS on final exact candidate HEAD, followed by source CI/provenance and
  distinct owner acceptance.

**No host service installation/restart, actual user modification, SSH,
firewall, production, registry publication or release is authorized by this
source PR.** Earlier Foundation TS Administration platform safety blocks
remain binding and were not rerouted.
