# PF-9 — DRLink Web Two-Step Password Then OTP Login

**Scope:** source-only Link 3.0 optional Web authentication candidate. No
running Web/Core process, user account, SSH/firewall or production deployment
changed. Work Packet [#188](https://github.com/datarelay-labs/datarelay-link/issues/188).
Dependency: shared Foundation TOTP wheel via Link Draft PR #186.

## Actual new Web login

The Web login view now submits **only username and password** to
`POST /api/v1/auth/login/start`. The Core-owned authentication service
verifies the product's password hash and current operator status:

- **MFA off (default):** creates a full authenticated Web session after
  successful password verification; no unnecessary OTP step.
- **MFA required but not enrolled:** preserves the existing temporary
  enrollment key and QR onboarding. Enrollment confirmation must succeed
  before a full session is issued.
- **MFA required and already enrolled:** issues a cryptographically random
  short-lived **pre-auth challenge** (3-minute TTL, max 1,024 globally
  and 5 per account in memory). New challenges are rejected at capacity,
  never allowed to evict another valid unexpired password proof.
  There is no session ID, cookie, CSRF token, role or TOTP secret.
  The frontend clears the password input and displays a **separate**
  authenticator-code or one-time recovery-code screen.
- `POST /api/v1/auth/login/complete` consumes that challenge **once**,
  binds it to the same direct socket peer and user agent and verifies
  current Core operator enablement, MFA requirement, role and row version
  before accepting the supplied current TOTP or unused recovery code.
  Only successful factor verification starts an authenticated session
  and causes an HttpOnly session cookie to be set.
- `POST /api/v1/auth/login/cancel` invalidates a pending challenge and
  returns the user to the password screen. Invalid, stale, replayed,
  wrong-source and expired challenges produce generic errors.
- The existing `/api/v1/auth/login` combined credential+MFA route
  remains for compatibility with old operators/tests, but the user-facing
  Web client no longer uses it. It still requires successful TOTP for
  MFA-enabled operators; there is no password-only bypass.

## Security properties

- Challenge tokens are **stored only as SHA256 digests** in the Web
  service's bounded ephemeral memory, never in Core SQLite or
  localStorage. Nothing stores the password or OTP in the challenge,
  support bundle or current role projection.
- A password-successful but **MFA-incomplete** attempt does not reset
  prior OTP failure counters. Repeated invalid codes across newly
  requested challenges still trigger the normal login rate limit.
- The pending-challenge pool is bounded globally **and by account**.
  If full, the server denies additional challenge creation without
  deleting an unexpired proof that another sign-in may still need.
  Expired challenges are pruned before enforcing either limit.
- The final Core transaction re-reads the effective role, enabled state,
  policy revision and MFA enrollment, and atomically consumes recovery
  codes or advances the `mfa_last_counter` **only when larger**.
  This rejects replay between two pending challenges and a concurrent
  downgrade/reset of an operator.
- A password-first challenge **is not an authenticated principal**:
  protected HTTP/API routes still require a full server-backed cookie
  plus CSRF verification. Web-only challenges do not weaken DRLink
  Core/FRP separate policy enforcement.
- DataRelay Foundation wheel `0.10.0.dev0` supplies the common RFC6238
  primitive with exact SHA256 and pinned source, as qualified by PR #186.
  No independent second TOTP implementation is added in this workstream.

## Validation and remaining security gates

New `tests/test-v30-web-password-otp.py` exercises source/UA binding,
password-only default-off, no pre-auth session, successful OTP, replay,
recovery, expiration, cancel, operator disable/change, login throttle and
invalid password. `tests/test-v30-web-service.py` exercises **real
loopback HTTP endpoints** and explicitly confirms **no Set-Cookie until
the second factor**. Product existing Web auth and MFA policy tests remain
mandatory. Web UI build, optional package/bundle, browser and user E2E are
separate evidence.

To release: actual direct-user browser sign-in (first password, second
OTP), member/admin roles, wrong OTP/rate-limit and recovery, login and
pre-auth expiration, trusted network source, full two-user E2E on exact
candidate HEAD, then machine CI/qualifications/owner acceptance.

The requested **management SSH and Web UI/API IP allowlists are not
implemented by this login flow**. They require distinct, product-authoritative
host/ingress adapters, privilege-safe previews and timed out-of-band rollback.
Do not claim completion of on-prem security solely from this login PR.
