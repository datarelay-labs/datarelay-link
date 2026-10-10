# PF-11B — Link Product-Native Read-Only Connectivity Evidence

Status: **source-only Link Web consumer**, not a live host qualification or
a replacement for the existing native `frp_doctor` and Core health data.

Owner Work Packet [#200](https://github.com/datarelay-labs/datarelay-link/issues/200)
is stacked on the separate, clean Link B3 Web security source
[PR #197](https://github.com/datarelay-labs/datarelay-link/pull/197).
Product Foundation [PF-11B #77](https://github.com/datarelay-labs/datarelay-product-foundation/issues/77)
already owns the **single canonical** no-I/O diagnostic evaluator.
The separate Foundation System Doctor source edit was previously
platform-blocked: no change or workaround to that file is attempted.

## Product-owned evidence, not caller-supplied input

Link's optional Web module imports `diagnose_network`, `NetworkEvidence`
and `DiagnosticPolicy` from the same **SHA256-verified, exact-version**
`datarelay-onprem-security==0.10.0.dev0` wheel already shipped as part
of Link's opt-in PF-9 Web package. There is no second CIDR/DNS/NTP
severity engine.

- **DNS:** the only permitted target is the hostname already recorded in
  native Link MCP TLS intent, retrieved through read-only product
  `ControlPlane` and validated by `mcp_tls.canonicalize_hostname`.
  The user has no hostname, URL or IP input to the endpoint. The product
  executes a fixed Python resolver subprocess with a 3-second timeout,
  no shell, no stdout/stderr or address/hostname exposure. A real
  resolution failure reports FAIL; an absent product hostname or
  unavailable source reports UNKNOWN, never PASS.
- **NTP/time:** fixed absolute, read-only `/usr/bin/timedatectl` sync
  status and, if available, `/usr/bin/chronyc` or
  `/usr/sbin/chronyc` tracking, each limited to 2 seconds.
  Sync `no` is FAIL. Sync `yes` **without a measured offset** is
  UNKNOWN. A measured offset goes through the Foundation PF11B
  recommended 10-second WARN / 30-second FAIL thresholds relevant to
  opt-in TOTP logins. No NTP setting is modified.
- **TLS certificate:** the product's existing MCP TLS native active
  certificate reader supplies only the verified present certificate's
  expiration timestamp, not its private key, hostname, issuer or PEM.
  Missing/invalid/unavailable proof is UNKNOWN. Expiry alone is **not**
  public CA chain, hostname, revocation or client TLS assurance.
- **Proxy and enterprise CA:** if the product Web service environment
  explicitly declares an HTTPS proxy or CA bundle, **presence is not
  reachability/trust**: the common evaluator returns UNKNOWN until a
  separate native trust/connection probe exists. When these optional
  surfaces are not configured, the corresponding status is SKIPPED.
  This implementation does not read or reveal credential values,
  download CA files, resolve arbitrary proxies or change trust roots.

Native results use five stable, ordered shared codes for DNS, NTP,
Proxy, enterprise trusted CA and certificate expiry. The response
includes only severity/reason/remediation codes, timestamp and
truthful `read_only=true`/`authoritative_mutation=false` metadata.
A failed/stale/absent finding is **UNKNOWN or FAIL** rather than
manufactured PASS. External resolver and time probes are completely
disabled for test-only synthetic product roots.

## Web identity and user experience

Authenticated current **Admin-only** GET
`/api/v1/system/connectivity` invokes this read-only product
evidence. Anonymous users receive 401; Read Only or Operator users
receive 403 before a probe. A 30-second in-process, single-flight
snapshot prevents concurrent Admin requests from multiplying the fixed
DNS/time subprocesses; the response retains its actual collection
timestamp. Expiry or collection failure is not silently promoted to
PASS. No long-lived product configuration cache or external service is
introduced. The existing B3 management Web source
allowlist is enforced first, so diagnostics do not bypass ingress ACL.

The existing Administration → System page adds one small read-only
**Connectivity health** section using this API. It has no independent
root menu, settings form, credentials, external target input or
Apply/Save button. Any missing API/data error becomes UNKNOWN.
The existing `/api/v1/doctor` continues reporting distinct
DB/runtime-generation health and is not replaced or falsely upgraded
to a complete network doctor.

## Test and release boundary

- `tests/test-v30-web-connectivity.py`: actual product synthetic-root
  MCP TLS state source, DNS success/failure/timeouts, measured NTP
  source and drift thresholds, certificate absent/expiring/expired,
  configured but unverified Proxy/CA, no raw endpoint data and no
  synthetic-root host/network probes.
- `V30WebServiceTests.test_pf11b_admin_only_connectivity_is_redacted_and_no_fixture_host_probe`:
  real temporary HTTP 401/200/403 session isolation, product state
  redaction and no developer-host network/time command.
- `tests/test-v30-web-connectivity-ui.py`: source and built Web
  bundle static contract (not browser acceptance).
- Existing pinned Foundation wheel, Web auth, staged MFA, ACL,
  install/uninstall/reinstall, full Web bundle and native workflows
  remain applicable.

**Remaining gates:** real authorized deployed DNS/NTP/Proxy/CA
configuration/trust measurements, independent CA/TLS connection tests,
operator and two-user Browser/Full User E2E on same candidate HEAD,
source/hash provenance, CI/review, owner acceptance and release.
No host OS/proxy/NTP/CA/SSH/firewall/secret or installed service is
changed. No customer or production network probe was performed.
