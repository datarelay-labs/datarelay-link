# Data Relay Link — v2.4.0 Release Validation

> **Purpose:** Validation plan for the final Control Plane / Object / Policy / MCP architecture
> **Rule:** Final stable evidence must come from the same exact source HEAD.

Current project version **2.4.0** / FRP **0.71.0**

Published tags are immutable.

### User E2E execution matrix

The canonical role-based real-user execution matrix is:

- docs/FULL_USER_E2E_SCENARIOS.md

An unqualified request for `User E2E`, `사용자 E2E`, `Full User E2E`, `전체 E2E`, `FULL_USER_E2E 수행해`, `GitHub에서 FULL_USER_E2E 문서 찾아서 수행해`, or equivalent wording means immediate execution of the `FULL_USER_E2E` profile in `datarelay-labs/datarelay-link/docs/FULL_USER_E2E_SCENARIOS.md`. Resolve the active-worktree canonical path first and avoid broad repository search. The profile is `PRODUCT_FUNCTIONAL_PERFORMANCE_OPERATIONAL`: all mandatory User, Operator, Administrator, functional failure/recovery, real-traffic, AI-assisted parity, platform/topology, concurrency, and performance scenarios. ChatGPT is the executor and final auditor for that profile.

Appendix A of the same file retains the v2.4 operator manual runbook. It does not replace FULL_USER_E2E and it is not a second canonical document.

A targeted subset is valid only when the requested scope is explicitly narrowed. Final release qualification still requires the exact-HEAD double Full Real E2E passes defined later in this document.

## 1. Gate philosophy

Validation must prove both allowed behavior and denied behavior.

Synthetic/unit tests are necessary but cannot replace Real E2E for final release qualification.

Failure classifications:

```text
PRODUCT_BUG
PLATFORM_COMPATIBILITY_BUG
TEST_HARNESS_BUG
ENVIRONMENT_BLOCKER
DOCUMENTATION_MISMATCH
RELEASE_METADATA_BUG
```

## 2. Automated validation order

Run in this order:

```text
static/syntax validation
schema/migration tests
Object/relationship tests
policy evaluator/compiler tests
impact/shadow tests
CLI targeted regressions
Internet Access security regressions
MCP auth/capability/path tests
backup/restore tests
version/release governance tests
full local automated suite
build/dist/source parity
```

After the exact candidate is installed, run `CLI_PRODUCT_SURFACE_RECONCILIATION` before counting any final Full User E2E pass. A later CLI/product change invalidates both the reconciliation and any downstream final E2E evidence.

Do not change product behavior merely to satisfy a stale test. First decide which contract is authoritative.

## 3. SQLite tests

Prove:

```text
fresh DB creation
migration ledger
foreign_keys enabled
WAL behavior
transaction rollback on failure
unsupported newer schema fail closed
corruption/integrity failure handling
concurrent writer busy handling
optimistic row-version conflict
```

## 4. Object tests

Prove:

```text
Host/Network/FQDN validation
multiple values
immutable ID rename behavior
reference preservation
reference-protected delete
Object Group membership
cycle rejection
context-invalid group assignment fails as a whole
Managed Host lifecycle remains under Managed Host commands
Managed Host references do not silently rebind to a different Agent identity
```

## 5. Endpoint address tests

Prove local inventory ingestion and membership calculation.

Reject/inactivate inappropriate loopback/link-local/multicast/special addresses from policy membership where required.

Test NAT/public observed source is not substituted for reported internal addresses.

For Internet Access Managed Host sources, prove the runtime distinction explicitly: direct peer address match follows normal BLACKLIST/WHITELIST semantics; a NAT/source mismatch that leaves Managed Host identity unprovable must fail closed under BLACKLIST when destination/service otherwise match, while Enforcement DISABLED still yields ALLOW ALL.

## 6. Remote Service tests

Prove Agent-owned connectivity through the public Agent Host CLI:

```text
Agent Host + destination + Service Object -> Remote Service
TCP Remote Service works
Fixed TCP Remote Service works
UDP Remote Service is rejected with no mutation/allocation
another-host destination uses the current Agent Host as Relay Host
endpoint identity remains stable across restart and same-pool-class edits
valid unreachable target becomes DEGRADED rather than disappearing
```

Edit destination/Service Object and verify impact analysis.

## 7. Policy evaluator tests

For Remote Access and Internet Access separately:

```text
No Policy / No Rules -> effective ALLOW
BLACKLIST + matching enabled Rule -> DENY
BLACKLIST + no match -> ALLOW
WHITELIST + matching enabled Rule -> ALLOW
WHITELIST + no match -> DENY
disabled Rule does not match
Enforcement DISABLED -> effective ALLOW ALL while Mode/Rules are preserved
Policy Reset -> No Policy / No Rules / effective ALLOW
Rules have no ordering and no per-rule ALLOW/DENY action
```

## 8. Policy mode / enforcement mutation tests

Prove:

```text
BLACKLIST <-> WHITELIST mode change uses the documented reset semantics
Policy Reset removes Mode and Rules
Enforcement disable/enable preserves configured Mode/Rules
disabled Rule remains stored but ineffective
same desired state is idempotent
```

## 9. Policy-impact tests

For every referenced-entity class, create before/after expected effective behavior.

Required cases:

```text
Network Object value changes effective membership
Network Group member changes effective membership
Rule enable/disable changes effective access
Policy Mode / Enforcement change alters effective access
Remote Service destination/Service Object change alters effective connectivity/policy impact
Managed Host address membership changes destination membership
AI permission addition broadens
AI path scope expansion broadens
```

## 10. Runtime generation tests

Prove:

```text
DB revision -> compiled artifact revision
atomic activation
generation metadata persistence
compiler failure surfaced
generation mismatch surfaced
unsafe stale/missing generation fail closed
restart retains/verifies active generation
```

## 11. Backup/restore tests

Use the supported consistent snapshot mechanism.

Prove:

```text
backup under WAL activity
restore to clean install
schema/integrity validation
permissions/ownership
secrets/trust recovery
runtime regeneration from DB
revision/generation consistency
policy behavior identical after restore
```

Negative:

```text
truncated archive
corrupt DB
unsupported schema
missing required trust material
```

## 12. Internet Access security tests

Required deny regressions:

```text
unapproved source
Managed Host BLACKLIST source identity ambiguous behind NAT/source mismatch -> DENY fail-closed
unapproved FQDN
wrong port
loopback
RFC1918/private target where unsafe
link-local
metadata
IPv6 local/private where unsafe
IP-literal bypass
wildcard boundary bypass
DNS rebinding-style behavior
malformed CONNECT
CONNECT/SNI mismatch
unsafe ECH-dependent validation path
corrupt/missing current policy generation
```

Required allowed cases:

```text
approved HTTP
approved HTTPS CONNECT
approved public Host/CIDR where supported
approved Fixed TCP
```

## 13. Real application Internet Access

At minimum:

```text
curl
wget
git
apt
```

For `apt`, prove both:

```text
required destinations present → operation succeeds
required destination removed → operation fails through policy
```

Do not use broad wildcards merely to make the application test pass.

## 14. Remote Access Real E2E

Prove as applicable:

```text
SSH Remote Service
HTTP/HTTPS Remote Service
Custom TCP
Relay Host to another LAN destination
No Policy effective ALLOW
BLACKLIST deny match
WHITELIST allow match and non-match deny
Enforcement disable/enable behavior
established session not implicitly killed by policy edit
new connection uses new policy immediately
```

## 15. MCP protocol/interoperability validation

Immediately before implementation freeze, re-check the current official MCP specification and supported SDK behavior.

Do not treat legacy SSE-only behavior as the target if current clients support modern Streamable HTTP/current revision.

For each client claimed supported, record exact product/version and transport/auth method.

Target matrix:

```text
MCP_SPEC_VERSION=2026-07-28
OFFICIAL_SPEC_SOURCE=https://modelcontextprotocol.io/specification/2026-07-28/
REFERENCE_SDK=Python mcp 2.2.0 Streamable HTTP
ChatGPT Plus=REQUIRED_REAL_USER_ACCEPTANCE (interactive OAuth Authorization Code / consent through owner UI)
ChatGPT Plus current status=BLOCKED_PENDING_OWNER_UI_AUTH
Machine-side OAuth/MCP qualification=REQUIRED_BUT_NOT_SUFFICIENT for the ChatGPT Plus user-auth gate
Claude=not claimed unless separately qualified with real host/account evidence
Cursor=not claimed unless separately qualified with real remote MCP host evidence
Official SDK E2E=PASS (HTTPS /mcp through product frontend in tests)
```

Real ChatGPT Plus owner/UI acceptance is retained as JSON evidence. By default the
qualification harness reads `e2e-reports/chatgpt-owner-acceptance.json`; an
external evidence path may be supplied with `FRP_E2E_CHATGPT_OWNER_EVIDENCE`.
The evidence is valid only when it binds all of the following to the candidate
being qualified:

```text
schema_version=1
status=PASS
client_surface=ChatGPT Plus owner/UI
core_provenance_head=<exact qualification HEAD>
core_source_head=<release-manifest source_head>
bootstrap_server_sha256=<release-manifest bootstrap-server.sh artifact SHA256>
mcp_endpoint=https://<public-dns-name>/mcp
oauth_authorization_code_consent=PASS
tool_discovery=PASS
policy_allowed_operation=PASS
policy_denied_operation=PASS
captured_at=<offset-aware ISO-8601 timestamp>
evidence_refs=<one or more retained owner/UI evidence references>
```

Missing, stale, machine-only, loopback/raw-IP, or incomplete evidence blocks
qualification before the destructive multi-host matrix begins. For this gate,
`stale` includes evidence whose `captured_at` predates the exact provenance
commit; timestamps more than 10 minutes in the future are also rejected.
The qualification report records `MCP_REAL_E2E`, `CHATGPT_PLUS_USER_AUTH`,
`CHATGPT_PLUS_TOOL_DISCOVERY`, and `CHATGPT_PLUS_ALLOW_DENY` separately in
addition to the aggregate owner/UI gate. Stable attestation receives the same
owner/UI evidence JSON as a base64 workflow input, revalidates it against the
checked-out release HEAD, and derives PASS/hash/HEAD values from that payload;
free-form owner acceptance/hash inputs are not authoritative.

The JSON payload is still external/self-reported evidence and therefore cannot
be terminal release authority on its own. Stable v2.4.0 attestation must also
pass the protected GitHub Environment `stable-release-owner-ui`, configured
with a required reviewer and administrator bypass disabled. The workflow may
consume `trusted_owner_ui_review=PASS` only from that environment-gated job
output; there is no caller-supplied workflow input for this value. A denied,
cancelled, or missing protected review blocks stable attestation.

A claim is not made merely because a generic MCP test client works.

## 16. MCP authentication tests

Prove:

```text
valid AI Identity succeeds only within policy
invalid credential denied
revoked credential denied
expired credential denied where applicable
disabled AI Identity denied
AI Identity attribution stable
authenticated transport required
real ChatGPT Plus owner/UI OAuth authentication and consent succeeds
ChatGPT tool discovery succeeds after authentication
one authorized ChatGPT operation succeeds
one intentionally out-of-scope ChatGPT operation is denied
machine-side protocol success alone does not satisfy the owner/UI gate
```

## 17. MCP authorization tests

First prove AI Access policy semantics:

```text
AI authentication remains mandatory
No Policy / No Rules -> effective ALLOW after authentication
BLACKLIST matching enabled Rule -> DENY
BLACKLIST no match -> ALLOW
WHITELIST matching enabled Rule -> ALLOW
WHITELIST no match -> DENY
Enforcement DISABLED preserves Mode/Rules and yields policy ALLOW ALL
Rules have no ordering and no per-rule ALLOW/DENY action
```

Then for each required capability:

```text
exec
read_file
write_file
upload_file
download_file
```

prove ALLOW and DENY paths.

Also test target selection through:

```text
Network Object
Network Group
```

Unknown capability/tool => DENY.

## 18. MCP path-scope tests

Required cases:

```text
allowed file path
outside allowed path
../ traversal
absolute/relative normalization edge
symlink escape as applicable
upload destination outside scope
download outside scope
platform-specific path semantics
```

A path that cannot be proven within scope is denied.

## 19. MCP exec tests

Prove:

```text
allowed exec
denied exec
exec timeout
bounded output
process cleanup
OS account/sudo boundary
read-only role with exec=false
policy change affects next invocation
running command not implicitly killed by policy edit
```

## 20. MCP file transfer Real E2E

On a real private/closed endpoint:

```text
read known file
write allowed file
upload file
verify checksum/content
download file
verify checksum/content
attempt out-of-scope path -> DENY
```

Use disposable test data, not production secrets.

## 21. AI audit validation

Verify records contain:

```text
principal
target
tool
matched rule
result
duration
revision
safe metadata
```

Verify they do not contain raw credentials, full sensitive file contents, or unrestricted command output.


### Continuous execution and finding accumulation

A single finding, mismatch, scenario failure, or test failure MUST NOT stop the suite. Record the finding and its evidence, then continue every remaining check that is safe and independent. Exhaust all executable checks before the suite reports its aggregate result.

Stop or skip only the specific downstream check when continuing it would be unsafe, would corrupt shared state/evidence, requires an unavailable mandatory dependency or explicit owner action, or is technically impossible because its prerequisite failed. Mark that check `BLOCKED` or `NOT_RUN` with the exact reason and continue all other independent checks. Do not remediate product/source findings inline during a frozen audit pass; finish the pass first, then remediate findings as one phase and rerun the required pass.


### Qualification execution order

Use this order for v2.4 release closure:

1. CLI Feature/Scenario reconciliation PASS1; accumulate findings and finish the pass.
2. Batch remediation if required; freeze a new candidate.
3. CLI Feature/Scenario reconciliation PASS2 must PASS.
4. Full User E2E PASS1; accumulate findings and finish the pass.
5. Batch remediation if required; any source/product/doc change invalidates affected evidence.
6. Full User E2E PASS2 must PASS on the unchanged final candidate.
7. Execute A-019 and remaining release-specific qualification.
8. Run final exact-head CI and automated regression, artifact, provenance, governance, and attestation gates.
9. Perform final release audit, then merge/tag/publish only if every required gate is green.

CI may run earlier as advisory feedback, but it is not a blocking wait point for independent semantic/user qualification. Only the final exact-head CI on the unchanged release candidate counts as terminal CI evidence. If final CI forces a source/product/doc change, invalidate and rerun every affected qualification pass before release.

### Product-quality closure vs release qualification

The two exhaustive product-quality contracts answer whether the product still needs product fixes/improvements; they do not replace release qualification.

```text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FULL_USER_E2E=PASS
=> PRODUCT_QUALITY_CLOSURE=PASS
=> NO_KNOWN_IN_SCOPE_PRODUCT_DEFECTS=YES
=> NO_FURTHER_PRODUCT_CHANGE_REQUIRED_BY_CURRENT_QUALITY_GATES=YES
```

`PRODUCT_QUALITY_CLOSURE=PASS` does **not** set `RELEASE_READY=YES`. Continue the existing release procedure in this document: exact-HEAD repeat/evidence rules where required, release-specific qualification, final CI/automated regressions, artifacts, SHA/SBOM/provenance, governance/attestation, protected approvals, final audit, tag, publication, and stable-channel update.

## 21.1 CLI product-surface reconciliation — independent release gate

For release qualification, the release workflow may first prepare the installed exact candidate environment for correlation, then invokes `CLI_FEATURE_SCENARIO_RECONCILIATION.md`. The reconciliation itself remains runtime non-destructive: it may use read-only discovery/status/help/test-explain evidence, but it does not create/edit/delete/apply/rollback/restore/update/restart/reboot product state, provision hosts, or search for replacements. `CLI_EXHAUSTIVE_AUDIT.md` may invoke the same product-surface audit, but it is not a substitute for the dedicated reconciliation contract.

This gate is intentionally separate from Full User E2E. Full User E2E answers whether representative real journeys work. Product-surface reconciliation answers whether the complete supported product model has one coherent, discoverable, non-duplicated CLI surface.

Required evidence:

```text
CLI_PRODUCT_SURFACE_RECONCILIATION=PASS
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FEATURE_INVENTORY_TOTAL=<n>
FEATURE_NO_CLI_GAPS=0
FEATURE_WITHOUT_DISCOVERABLE_CLI_COUNT=0
CLI_WITHOUT_PRODUCT_FEATURE_COUNT=0
RUNTIME_ONLY_CLI_COUNT=0
DUPLICATE_PUBLIC_PATH_COUNT=0
PUBLIC_ALIAS_PATH_COUNT=0
LEGACY_COMPATIBILITY_PATH_COUNT=0
ROOT_BYPASS_ALIAS_COUNT=0
HIDDEN_EXECUTABLE_PATH_COUNT=0
DISCOVERY_GAP_COUNT=0
INSTALLER_GUIDANCE_MISMATCH_COUNT=0
DESTRUCTIVE_CONFIRMATION_GAP_COUNT=0
ERROR_WITH_ZERO_RC_COUNT=0
SCENARIO_BLOCKED_COUNT=0
SCENARIO_DEAD_END_COUNT=0
CONFIRMATION_METADATA_DRIFT_COUNT=0
STATE_SEMANTICS_DRIFT_COUNT=0
DOC_EXAMPLE_NONCANONICAL_COUNT=0
ROLE_SURFACE_DRIFT_COUNT=0
STATUS_DOC_RUNTIME_MISMATCH_COUNT=0
CLEANUP_RESIDUE_COUNT=0
RUNTIME_MUTATION_ATTEMPT_COUNT=0
```

For the unreleased/greenfield v2.4 CLI, compatibility-only aliases, root-bypass aliases, duplicate mutation routes, and executable obsolete hidden grammar are not accepted as release justification. If a future released version requires compatibility, each exception must be explicit, documented, bounded, and separately tested.

The reconciliation must treat installer completion output, generated enrollment instructions, contextual help, completion, diagnostics/update recommendations, error recovery, and active documentation command examples as part of the public surface. A feature is not considered reachable when its command exists but its required lifecycle variant is undiscoverable, when the advertised next action is obsolete/hidden, or when a recovery message does not name an actionable supported path.

After black-box discovery is retained, perform post-hoc executable catalog/parser enumeration to prove that hidden/alias paths do not escape the public model. This source inspection is reconciliation evidence for operator-workflow coherence; it does not authorize execution of hidden or mutation-bearing runtime paths.

Every behavior-changing setting/subcommand and destructive subvariant must receive its own disposition. Reconcile intended effect against catalog/parser/source risk/confirmation metadata and deterministic isolated-test coverage; do not execute destructive confirmation probes on assigned runtime state. Privilege/readability errors for read-only probes must return non-zero and must not be misreported as role errors. Status/version/provenance surfaces must not contradict the current control-plane model.

The reconciliation must record `RUNTIME_MUTATION_ATTEMPT_COUNT=0`. Its cleanup evidence covers only audit-owned temporary processes/files because the audit must not create product resources. Environment provisioning, product-resource cleanup, and host lifecycle cleanup remain responsibilities of the enclosing release/FULL_USER_E2E workflow.

Any CLI/product/documentation surface change after this PASS invalidates the gate and requires a fresh reconciliation before Full User E2E PASS1/PASS2 can count as final stable evidence.

### 21.2 Mandatory pre-release exhaustive evidence hard gate

Stable release qualification requires both independent exhaustive test families on the same exact HEAD:

```text
CLI_FEATURE_SCENARIO_RECONCILIATION=PASS
FULL_USER_E2E_PASS1=PASS
FULL_USER_E2E_PASS2=PASS
```

The release preflight and direct release-pass entry validate retained machine-readable evidence with:

```bash
python3 scripts/check-pre-release-exhaustive-gates.py --gate all
```

Default evidence paths are:

```text
e2e-reports/release-qualification/cli-feature-scenario.json
e2e-reports/release-qualification/full-user-e2e-pass1.json
e2e-reports/release-qualification/full-user-e2e-pass2.json
```

Missing, stale, different-HEAD, partial, blocked, non-cleanup, or counter-nonzero evidence fails closed. These gates are mandatory in addition to the automated production-realistic PASS1/PASS2 qualification; no one test substitutes for another.

## 22. CLI/PTy validation

Protect:

```text
root domains
role filtering
root ?
help topics
help commands parity
Tab non-execution
context-valid Object suggestions
Managed Host / Network Object terms
Service Object Wizard preset terminology
BLACKLIST / WHITELIST Mode display
Enforcement state display
effective policy outcome
impact confirmation
stale-edit rejection
AI Identity secret safety
REPL vs shell hints
backend command isolation
```

## 22.1 ConfigurationBundle / AI-assisted configuration validation

Qualification must exercise the actual public CLI and the same installed control-plane engine used by ordinary operators.

Required automated + Real E2E cases:

```text
CONFIGURATION_BUNDLE_SCHEMA=PASS
CONFIGURATION_FILE_INPUT=PASS
CONFIGURATION_STDIN_INPUT=PASS
CONFIGURATION_VALIDATE_NO_MUTATION=PASS
CONFIGURATION_EMBEDDED_POLICY_TESTS=PASS
CONFIGURATION_DIFF=PASS
CONFIGURATION_IDEMPOTENT_REAPPLY_NO_CHANGE=PASS
CONFIGURATION_EXPLICIT_DELETE_ONLY=PASS
CONFIGURATION_REFERENCE_PROTECTION=PASS
CONFIGURATION_ATOMIC_ROLLBACK=PASS
CONFIGURATION_REVISION_CONFLICT=PASS
CONFIGURATION_SECURITY_IMPACT_CONFIRMATION=PASS
CONFIGURATION_REDACTED_EXPORT=PASS
CONFIGURATION_SECRET_EXCLUSION=PASS
DIRECT_CLI_AND_BUNDLE_SEMANTIC_PARITY=PASS
AI_COPY_PASTE_REAL_E2E=PASS
CLIENT_ACTION_REQUIRED_BOUNDARY=PASS
```

Semantic parity must compare equivalent changes made through direct CLI and ConfigurationBundle and prove they produce the same authoritative state/effective policy, impact decision, revision/audit semantics, and runtime behavior.

AI copy/paste Real E2E starts from a generated stdin block, applies it through the installed public `drlink` CLI, and verifies real traffic. Direct SQLite, JSON mutation, private helper commands, or hidden compatibility grammar cannot count as PASS.

Zero-Touch qualification:

```text
ZERO_TOUCH_MAX_10_PER_REQUEST=PASS
ZERO_TOUCH_MAX_10_ACTIVE_UNUSED=PASS
ZERO_TOUCH_CAPACITY_REMAINDER=PASS
ZERO_TOUCH_UNIQUE_PER_DEVICE=PASS
ZERO_TOUCH_SINGLE_USE=PASS
ZERO_TOUCH_CONCURRENT_DOUBLE_USE_DENY=PASS
ZERO_TOUCH_DEFAULT_TTL_1H=PASS
ZERO_TOUCH_MAX_TTL_24H=PASS
ZERO_TOUCH_EXPIRED_REVOKED_CAPACITY_RELEASE=PASS
ZERO_TOUCH_SECRET_DISPLAY_ONCE=PASS
ZERO_TOUCH_SERVER_STORES_NO_RAW_TICKET=PASS
ZERO_TOUCH_YAML_CANNOT_EMBED_SECRET=PASS
ZERO_TOUCH_LIMIT_CANNOT_BE_OVERRIDDEN=PASS
ZERO_TOUCH_EXPIRY_DOES_NOT_DISCONNECT_ENROLLED_CLIENT=PASS
```

Also prove that applying a bundle containing 30 enrollment plans issues 0 tickets and that explicit batch issuance never exceeds remaining active-unused capacity.

## 23. Version/governance transition validation

Before RC, tests that encode legacy MCP exclusion must be intentionally replaced.

Final governance proves:

```text
features.mcp_included=true whenever v2.4.0 candidate bytes include MCP Bridge/AI Access
manifest schema permits/requires actual feature truth
no MCP_V2_4_EXCLUSION legacy guard
MCP inclusion evidence present
ChatGPT Plus owner/UI user-auth acceptance evidence retained before stable
exact source HEAD/ref immutable
no future-tag URL before tag exists
```

Set manifest feature truth from the candidate bytes: once MCP Bridge/AI Access are present, `features.mcp_included=true` even while ChatGPT Plus owner/UI authentication remains blocked. Do not use `mcp_included=false` to represent an unqualified or blocked release.

## 24. Fresh install / uninstall / reinstall

Prove:

```text
fresh server DB created
fresh client enrollment
no legacy JSON authority required
uninstall preserve-state behavior if supported
purge removes product-owned DB/runtime/secrets according to contract
reinstall creates/uses correct state
```

## 25. Upgrade/migration

Because v2.4.0 is pre-stable, backward compatibility with development JSON formats is not a public requirement.

Nevertheless, lab/test transition migration may be implemented for engineering convenience. It must not create dual authoritative state.

Final supported upgrade claims are based on actual prior stable releases and explicit migration code/evidence.

## 26. Multi-host matrix

Final applicable matrix:

```text
Ubuntu 24
Windows 10
Rocky Linux 8
Rocky Linux 9
Amazon Linux 2023
macOS Apple Silicon
```

Record qualification level honestly:

```text
code-only
container
system service
real VM/physical
field validated
stable supported
```

## 27. Full Real E2E pass 1

Record:

```text
FULL_REAL_E2E_PASS_1=PASS|FAIL
PASS1_HEAD=<40-char SHA>
PASS1_SUMMARY_SHA256=<64-char SHA256>
```

It includes Remote Access + Internet Access + AI/MCP + lifecycle + backup/restore + supported platform matrix applicable to the release claim. The terminal `summary.json` must be written only after the PASS1 gate is recorded and must show `final_status=PASS`, `FROZEN_HEAD==PASS1_HEAD==END_HEAD`, `HEAD_UNCHANGED=YES`, retained `summary.txt` and `matrix.log`, and no release-blocking `FAIL`, `BLOCKED`, or `NOT_RUN` gate.

## 28. Full Real E2E pass 2

Repeat independently on the exact same HEAD:

```text
FULL_REAL_E2E_PASS_2=PASS|FAIL
PASS2_HEAD=<40-char SHA>
PASS2_SUMMARY_SHA256=<64-char SHA256>
PASS1_HEAD==PASS2_HEAD
```

After PASS2, `run-release-qualification-pass.sh` creates
`e2e-reports/release-qualification/qualification-evidence.json` containing
both validated terminal summaries and their SHA256 digests. The package must
itself revalidate with `scripts/check-release-qualification-evidence.py` on
the unchanged exact HEAD. Stable attestation derives the PASS1/PASS2/final
HEADs and qualification evidence SHA256 from this package; caller-supplied HEAD
strings are not terminal qualification evidence.

Any product/dependency/generated artifact change resets the count.

## 29. Evidence integrity

Retain enough evidence to verify:

```text
exact HEAD
build/artifact identity
commands/test suite version
platform
result
failure classification
release manifest/checksum
PASS1 terminal summary + SHA256
PASS2 terminal summary + SHA256
combined qualification evidence package + SHA256
```

Do not claim PASS from memory, a different HEAD, or manually repeated
PASS1/PASS2 HEAD strings. A stable release-attest run must revalidate the
retained qualification package and fail closed when either embedded summary,
digest, exact-HEAD binding, terminal status, or mandatory gate is invalid.

The validated package is still implementer-produced evidence and therefore is
not terminal release authority by itself. Stable attestation additionally
requires protected GitHub Environment `stable-release-qualification`
approval, with a required reviewer and administrator bypass disabled. The
protected approval must carry the exact prevalidated qualification evidence
SHA256, and the stable binding must fail when that reviewed SHA256 differs from
the package SHA256.

## 30. Final result format

```text
PHASE=V2_4_0_FINAL_RELEASE_QUALIFICATION
FINAL_STATUS=PASS|PARTIAL|FAIL
SOURCE_HEAD=
CONTROL_PLANE_DB=
NETWORK_OBJECT_MODEL=
NETWORK_GROUP_MODEL=
MANAGED_HOST_MODEL=
MANAGED_HOST_ADDRESS_INVENTORY=
REMOTE_SERVICE_MODEL=
REMOTE_ACCESS_POLICY_MODE=
INTERNET_ACCESS_POLICY_MODE=
AI_ACCESS_POLICY_MODE=
BLACKLIST_WHITELIST=
POLICY_ENFORCEMENT=
POLICY_RESET_SEMANTICS=
POLICY_IMPACT_ANALYSIS=
REFERENCE_PROTECTION=
CONCURRENT_EDIT_PROTECTION=
MCP_BRIDGE=
MCP_AUTH=
MCP_HOST_ROUTING=
MCP_CAPABILITY_ENFORCEMENT=
MCP_FILE_SCOPE=
MCP_AUDIT=
MCP_REAL_E2E=
MCP_INCLUDED_IN_V2_4_0=YES
CHATGPT_PLUS_USER_AUTH_STATUS=PASS|BLOCKED
CONFIGURATION_BUNDLE=
CONFIGURATION_DIRECT_CLI_PARITY=
CONFIGURATION_AI_COPY_PASTE_REAL_E2E=
ZERO_TOUCH_BOUNDED_BATCH=
CLI_PRODUCT_SURFACE_RECONCILIATION=PASS|FAIL
CLI_PRODUCT_SURFACE_EVIDENCE=
PRODUCT_QUALITY_CLOSURE=PASS|FAIL
SQLITE_MIGRATION_FRAMEWORK=
REVISION_AUDIT=
RUNTIME_GENERATION_CONSISTENCY=
BACKUP_RESTORE=
DB_CORRUPTION_FAIL_CLOSED=
MULTI_HOST_REAL_E2E=
FULL_REAL_E2E_PASS_1=
FULL_REAL_E2E_PASS_2=
PASS1_HEAD=
PASS2_HEAD=
UNRESOLVED_P0=
UNRESOLVED_P1=
UNRESOLVED_P2=
BLOCKERS=
```

PASS requires zero unresolved release-blocking findings and exact-HEAD evidence for every mandatory gate.

Recorded prior evidence and remaining platform limitations:

```text
REAL_ENTERPRISE_RESTRICTED_NETWORK_E2E=PASS
REAL_SSH_SERVICE_E2E=PASS
REAL_END_TO_END_REBOOT_RECOVERY=PASS
FIREWALL_DNAT_PRIVATE_FRP_SERVER=NOT_TESTED
REAL_ARM_SYSTEMD=NOT_TESTED
REAL_OPENSSL_1_0_2_TLS_ENROLLMENT=NOT_TESTED
ROCKY_9_SELINUX_ENFORCING=NOT_TESTED
```
