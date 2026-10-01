# Data Relay Link — v2.4.0 Release Checklist

> **Purpose:** Exact-HEAD stable qualification checklist
> **Rule:** A checked item requires retained evidence. Architecture documentation is not implementation evidence.

Authoritative classification of remaining gates is in `docs/RELEASE_VALIDATION.md`.
Do **not** tag a tree whose `PROJECT_VERSION` does not match the intended immutable tag.

FRP_VERSION=0.71.0

Published tags are immutable. Preparing the 2.4.0 immutable tag is a later qualification step. Published tags remain immutable and must never be moved, recreated, retargeted, or deleted.

## 1. Candidate identity

- [ ] `PROJECT_VERSION=2.4.0`.
- [ ] Candidate identity is an exact-SHA development build, or an optional `2.4.0-rc.N` / `preview` build. Preview/RC is not mandatory.
- [ ] `SOURCE_HEAD` is the exact 40-character SHA.
- [ ] Branch/worktree recorded.
- [ ] Worktree clean.
- [ ] Remote synchronized.
- [ ] Product and FRP versions recorded separately.
- [ ] Historical tags unchanged.
- [ ] `v2.4.0` does not already point elsewhere.

Evidence:

```text
RELEASE_VERSION=
RELEASE_CHANNEL=
SOURCE_HEAD=
BRANCH=
WORKTREE=
WORKTREE_CLEAN=
REMOTE_SYNCED=
UPSTREAM_ENGINE_VERSION=
CONTROL_DB_SCHEMA_VERSION=
```

## 2. Architecture scope

- [ ] `CONTROL_PLANE_ARCHITECTURE.md` matches implementation.
- [ ] SQLite is authoritative control-plane state.
- [ ] No dual authoritative JSON state remains.
- [ ] Network Object / Network Group model implemented.
- [ ] Service Object / Service Group model implemented.
- [ ] Permission Object / Permission Group model implemented.
- [ ] Managed Host / DRLink Agent model implemented.
- [ ] Managed Host address inventory implemented.
- [ ] Agent-owned Remote Service model implemented.
- [ ] Remote Access BLACKLIST / WHITELIST policy implemented.
- [ ] Internet Access BLACKLIST / WHITELIST policy implemented.
- [ ] AI Access/MCP included and implemented (`MCP_INCLUDED_IN_V2_4_0=YES`).
- [ ] Real ChatGPT Plus user authentication is a mandatory v2.4.0 release gate.
- [ ] ConfigurationBundle included in the v2.4.0 stable target.
- [ ] direct CLI, AI-generated CLI, and ConfigurationBundle share one Change Plan/mutation engine.
- [ ] ConfigurationBundle is an idempotent change set, not a second SSOT.
- [ ] Zero-Touch ticket issuance is server-bounded to max 10/request and max 10 active unused, unique single-use tickets.

## 3. SQLite control plane

- [ ] `/var/lib/drlink/drlink.db` is authoritative.
- [ ] Foreign keys enabled.
- [ ] WAL configured.
- [ ] Synchronous durability policy configured.
- [ ] Busy timeout configured.
- [ ] Trusted schema disabled where supported.
- [ ] `schema_migrations` is authoritative migration ledger.
- [ ] Unsupported newer schema fails closed.
- [ ] Integrity/foreign-key validation implemented.
- [ ] Corruption handling is fail closed.

Evidence:

```text
CONTROL_PLANE_DB=
SQLITE_SETTINGS=
SCHEMA_MIGRATION_FRAMEWORK=
DB_CORRUPTION_FAIL_CLOSED=
```

## 4. Object model

- [ ] Network Object CRUD for IP / CIDR / FQDN.
- [ ] Registered Managed Hosts appear as Network Objects of type Managed Host.
- [ ] Network Group CRUD and flat membership semantics.
- [ ] Service Object / Service Group CRUD.
- [ ] Permission Object / Permission Group CRUD.
- [ ] Immutable internal identity and rename/reference preservation where applicable.
- [ ] Managed Host lifecycle remains under Managed Host commands.
- [ ] Internet Access destination rejects Managed Host directly or through a Network Group.
- [ ] Context-invalid group assignment fails as a whole.
- [ ] Referenced Object/Group deletion blocked.

## 5. Endpoint inventory

- [ ] Client reports eligible local addresses.
- [ ] Active/inactive state tracked.
- [ ] Interface metadata retained where supported.
- [ ] loopback/link-local/multicast/special addresses excluded appropriately.
- [ ] Network membership uses local inventory rather than NAT/public observed source.

## 6. Remote Services

- [ ] Remote Service mutation is Agent Host-local; Server inspection is read-only for configuration.
- [ ] Each Remote Service binds one destination and one Service Object.
- [ ] TCP and Fixed TCP Service Objects are supported; UDP Remote Service is rejected.
- [ ] Another-host destination uses the current Agent Host as Relay Host.
- [ ] Endpoint identity remains stable across restart, temporary disconnect, disable/enable, and same-pool-class edit.
- [ ] Unreachable but valid targets become DEGRADED rather than being silently deleted.
- [ ] Destination/Service Object edits run policy-impact analysis.

## 7. Remote Access policy

- [ ] Initial state is No Policy / No Rules / effective ALLOW.
- [ ] BLACKLIST: matching enabled Rule DENY; no match ALLOW.
- [ ] WHITELIST: matching enabled Rule ALLOW; no match DENY.
- [ ] Rules have no ordering and no per-rule ALLOW/DENY action.
- [ ] Policy Reset removes Mode and Rules and restores initial ALLOW.
- [ ] Enforcement DISABLED preserves Mode/Rules and makes policy effective ALLOW ALL.
- [ ] Effective access also requires an enabled/reachable Remote Service.
- [ ] Policy changes apply immediately to new connections.
- [ ] Established connections are not implicitly terminated by policy edit.

## 8. Internet Access policy/security

- [ ] Same BLACKLIST / WHITELIST / Enforcement semantics proven independently from Remote Access.
- [ ] Internet Access source may use Managed Host only with address-backed runtime identity; BLACKLIST source ambiguity fails closed under NAT/source mismatch; destination rejects Managed Host directly or through a Group containing one.
- [ ] FQDN destinations.
- [ ] Explicit public Host/CIDR destinations where supported.
- [ ] server-side DNS.
- [ ] DNS rebinding resistance.
- [ ] validated exact-IP connect.
- [ ] SSRF/private/local/metadata protection.
- [ ] IP-literal bypass protection.
- [ ] wildcard boundary safety where supported.
- [ ] CONNECT/SNI binding where applicable.
- [ ] ECH behavior fails safely where validation depends on SNI.
- [ ] malformed proxy/TCP input fails closed.
- [ ] resource/time limits.
- [ ] Fixed TCP uses same policy authority.

## 9. Policy-impact analysis

- [ ] Object value add/remove impact.
- [ ] Object Group membership impact.
- [ ] Rule content/enable impact.
- [ ] Policy Mode / Enforcement impact.
- [ ] Remote Service destination/Service Object impact.
- [ ] Managed Host address membership impact.
- [ ] AI permission/target/path impact.
- [ ] Access broadening identified.
- [ ] Access narrowing identified.
- [ ] New/removed shadowing identified.
- [ ] Effective-action changes identified.
- [ ] Interactive broadening defaults to No.

## 10. Optimistic concurrency / transactions

- [ ] Mutable entities have row-version protection or equivalent.
- [ ] Stale wizard commit rejected.
- [ ] No lost update.
- [ ] Security mutation transaction includes revision/audit records.
- [ ] Partial mutation not reported as success.

## 11. Revision and audit

- [ ] Every control-plane mutation has revision ID.
- [ ] Actor/action/entity/result captured.
- [ ] Before/after summary bounded.
- [ ] Policy impact recorded.
- [ ] Secret/raw payload leakage prevented.
- [ ] `system audit` works.
- [ ] `system revisions` works.
- [ ] revision diff works if claimed.
- [ ] rollback only claimed if qualified and creates a new revision.

## 12. Runtime generation

- [ ] Runtime policy compiled from DB.
- [ ] Activation atomic.
- [ ] Remote policy generation records DB revision.
- [ ] Internet policy generation records DB revision.
- [ ] AI policy generation records DB revision.
- [ ] Generation mismatch surfaced.
- [ ] Unsafe mismatch fails closed.
- [ ] Status never calls a divergent plane simply Healthy.

## 13. Backup / restore / migration

- [ ] Live WAL DB backed up with SQLite Online Backup/equivalent.
- [ ] Required config/trust/secrets/provenance included.
- [ ] Naive `cp` not documented as live backup method.
- [ ] Restore validates archive and DB integrity.
- [ ] Restore validates foreign keys/schema.
- [ ] Restore preserves secure owner/mode.
- [ ] Runtime artifacts regenerated from DB.
- [ ] Runtime generation verified after restore.
- [ ] Upgrade migration has pre-upgrade backup.
- [ ] Failed migration does not leave ambiguous authority.

## 14. MCP / AI Access

- [ ] MCP Bridge runs on server.
- [ ] No per-endpoint MCP server required.
- [ ] Current official MCP spec/SDK re-verified before implementation freeze.
- [ ] Supported remote MCP transport qualified.
- [ ] Authentication binds a stable AI Identity.
- [ ] Anonymous privileged MCP access denied.
- [ ] Credential revoke/rotation works.
- [ ] Target = Network Object / Network Group.
- [ ] Permission = Permission Object / Permission Group.
- [ ] AI Access uses BLACKLIST / WHITELIST semantics; authentication remains mandatory.
- [ ] AI Rules have no ordering and no per-rule ALLOW/DENY action.
- [ ] `exec` enforcement.
- [ ] `read_file` enforcement.
- [ ] `write_file` enforcement.
- [ ] `upload_file` enforcement.
- [ ] `download_file` enforcement.
- [ ] path scopes resist traversal/symlink bypass appropriate to platform.
- [ ] exec timeout/resource handling.
- [ ] true read-only policy requires `exec=false` in tests/docs.
- [ ] each new tool call evaluates current policy.
- [ ] running operation not implicitly killed by policy edit.
- [ ] AI activity audit attributable to principal/target/rule/revision.
- [ ] real ChatGPT Plus owner/UI OAuth Authorization Code / consent completes through the public MCP endpoint.
- [ ] ChatGPT Plus tool discovery succeeds after authentication.
- [ ] one AI Access policy-allowed operation succeeds through ChatGPT Plus.
- [ ] one intentionally out-of-scope operation is denied through ChatGPT Plus.
- [ ] machine-side MCP/OAuth conformance evidence is retained separately and does not substitute for owner/UI acceptance.
- [ ] retained ChatGPT Plus owner/UI evidence is bound to the exact provenance HEAD, source HEAD, bootstrap-server artifact SHA256, and public HTTPS `/mcp` endpoint.
- [ ] owner/UI evidence capture time is at/after the exact provenance commit and not implausibly in the future.
- [ ] qualification rejects missing/stale/incomplete ChatGPT owner/UI evidence before destructive Real E2E begins.
- [ ] stable attestation revalidates the actual owner/UI evidence payload and derives acceptance/hash/HEAD instead of trusting free-form PASS/hash inputs.
- [ ] stable v2.4.0 attestation requires protected GitHub Environment `stable-release-owner-ui` approval; caller input cannot synthesize `trusted_owner_ui_review=PASS`.
- [ ] `stable-release-owner-ui` has at least one required reviewer and administrator bypass is disabled.
- [ ] denied, cancelled, skipped, or unconfigured protected owner/UI review fails closed before stable attestation proceeds.
- [ ] Claude interoperability tested if claimed supported.
- [ ] Cursor interoperability tested if claimed supported.

Evidence:

```text
MCP_BRIDGE=
MCP_AUTH=
MCP_HOST_ROUTING=
MCP_CAPABILITY_ENFORCEMENT=
MCP_FILE_SCOPE=
MCP_AUDIT=
MCP_REAL_E2E=
CHATGPT_PLUS_USER_AUTH=
CHATGPT_PLUS_TOOL_DISCOVERY=
CHATGPT_PLUS_ALLOW_DENY=
```

## 14.1 ConfigurationBundle / AI-assisted configuration

- [ ] `apiVersion: drlink.datarelay.run/v1alpha1` / `kind: ConfigurationBundle` schema validated.
- [ ] file input validated.
- [ ] standard-input copy/paste validated.
- [ ] no top-level `apply` root introduced; stable direct roots unchanged.
- [ ] `test configuration` is non-mutating.
- [ ] diff is generated against authoritative current state.
- [ ] identical reapply returns `NO CHANGE`.
- [ ] omission preserves resources; deletion requires explicit absent state.
- [ ] multi-resource apply is one authoritative transaction.
- [ ] reference/security validation occurs before commit.
- [ ] revision conflict aborts without partial mutation.
- [ ] broadening/destructive confirmation uses existing impact engine and defaults No.
- [ ] export is redacted and excludes tickets/secrets/private keys.
- [ ] direct CLI and equivalent bundle have semantic parity.
- [ ] AI-generated simple changes use canonical public CLI only.
- [ ] AI-generated complex changes use a copy/paste ConfigurationBundle and public `drlink` only.
- [ ] unsupported existing-client local target changes report `CLIENT_ACTION_REQUIRED`.
- [ ] bundle enrollment plans issue 0 secrets during apply.
- [ ] Zero-Touch issuance request max = 10.
- [ ] active unused Zero-Touch tickets max = 10.
- [ ] each ticket is unique/single-use and consumed atomically.
- [ ] default TTL = 1 hour; max TTL = 24 hours.
- [ ] raw ticket/install URL displayed once; server retains verifier/hash, not raw ticket.
- [ ] expired/revoked tickets release capacity without disconnecting enrolled clients.
- [ ] YAML/CLI/API cannot override server ticket ceilings.

## 15. Legacy model removal

- [ ] `registry.json` no longer authoritative.
- [ ] `egress-control.json` no longer authoritative.
- [ ] no public `service-profile` canonical resource.
- [ ] no public `internet-profile` canonical resource.
- [ ] no legacy ACL model presented as canonical.
- [ ] old v2.4 MCP exclusion removed from version/release code.
- [ ] release manifest schema no longer forces `mcp_included=false` for 2.4.x.
- [ ] release manifest generator/checkers/tests aligned to target.
- [ ] generated candidate manifest says `mcp_included=true` only when feature is actually included.

## 16. CLI UX and product-surface reconciliation

- [ ] `CLI_FEATURE_SCENARIO_RECONCILIATION=PASS` using `CLI_FEATURE_SCENARIO_RECONCILIATION.md`; this is a runtime non-destructive Feature ↔ CLI/AI ↔ Operator Workflow audit separate from Full User E2E. Every applicable feature/FCS requires 100% Direct-user and AI-assisted persona coverage; scripts/harnesses are supplemental evidence only. The audit uses read-only runtime evidence plus catalog/parser/docs/isolated tests and never changes assigned product state.
- [ ] `CLI_PRODUCT_SURFACE_RECONCILIATION=PASS` is satisfied by the same exact-candidate reconciliation evidence.
- [ ] every Product Master capability has a justified public CLI/menu/installer lifecycle mapping.
- [ ] every installed runtime command maps to a current product capability and canonical documentation.
- [ ] every required lifecycle variant is discoverable from public help/?/completion/menu without memorized hidden syntax.
- [ ] root help, `?`, Tab, menu, `help commands`, command-specific help, and errors expose the same supported surface; no supported command requires memorization.
- [ ] every behavior-changing setting/subcommand has an explicit disposition; family-level parsing alone does not count as coverage.
- [ ] no duplicate public mutation path exists for the same operation without an explicit product reason.
- [ ] unreleased/greenfield v2.4 exposes no compatibility-only root-bypass alias or executable obsolete hidden grammar.
- [ ] installer completion text, enrollment instructions, diagnostics, update recommendations, and recovery text point only to current canonical commands or exact documented installer actions.
- [ ] active documentation examples use canonical public grammar or an explicitly justified installer-only lifecycle.
- [ ] no supported workflow ends with a non-actionable recovery instruction or legacy alias.
- [ ] destructive subvariants have effect-appropriate `risk`/confirmation metadata and isolated regression coverage for interactive/default-No/non-TTY fail-closed behavior; the reconciliation itself does not execute them on assigned runtime state.
- [ ] destructive/non-TTY cancellation contract is automation-safe and never returns success for an unapplied mutation.
- [ ] privilege/readability ERROR paths return non-zero and are not misreported as wrong-role errors.
- [ ] empty-list output explicitly distinguishes zero items from failure rather than silent RC=0 success.
- [ ] status/version/provenance surfaces are mutually consistent and do not expose retired state models as current.
- [ ] final reconciliation records `RUNTIME_MUTATION_ATTEMPT_COUNT=0`; cleanup proves zero audit-owned temporary process/file residue and does not remove pre-existing product resources.
- [ ] Server root = Managed Hosts / Network Objects / Service Objects / Remote Access / Internet Access / AI Access / System / Help / Exit.
- [ ] Agent Host root = Remote Services / Agent / Configuration / System / Help / Exit.
- [ ] Direct roots = show/set/unset/test/system/menu/help/exit.
- [ ] Managed Host / Network Object terminology consistent.
- [ ] Remote Service terminology consistent.
- [ ] Service Object Wizard presets are clear and are not exposed as standalone public resources.
- [ ] BLACKLIST / WHITELIST Mode and Enforcement state are visible.
- [ ] `test` explains effective policy outcome without ordered-rule semantics.
- [ ] Tab context filters invalid Object types.
- [ ] broadening confirmation visible.
- [ ] stale edit failure visible.
- [ ] backend/internal FRP helpers not leaked.
- [ ] REPL vs shell hints correct.

## 17. Version/reference integrity

- [ ] one product version SSOT.
- [ ] development/preview/stable identity correct.
- [ ] `show version` includes exact HEAD and separate FRP version.
- [ ] control DB schema/version visible.
- [ ] pre-tag bootstrap/install refs exact SHA/immutable RC.
- [ ] no future nonexistent stable-tag URL.
- [ ] no mutable fallback for qualified install.
- [ ] release manifest matches actual candidate bytes/features.

## 18. Local and CI validation

- [ ] targeted regressions pass.
- [ ] static/syntax validation pass.
- [ ] DB/migration tests pass.
- [ ] policy compiler/evaluator tests pass.
- [ ] CLI/PTY regression pass.
- [ ] lifecycle regression pass.
- [ ] security regression pass.
- [ ] MCP unit/integration pass.
- [ ] full local suite pass.
- [ ] GitHub CI pass.
- [ ] source/dist parity pass.
- [ ] secret scan pass.
- [ ] public metadata scan pass.

## 19. Real environment validation

- [ ] fresh server install.
- [ ] fresh client install.
- [ ] Zero-Touch.
- [ ] reboot/autostart.
- [ ] update/migration.
- [ ] backup/restore.
- [ ] uninstall zero-residue where purge requested.
- [ ] reinstall.
- [ ] Remote Access SSH/HTTP/HTTPS/TCP as claimed.
- [ ] Custom TCP half-close preserves the reverse response after client `shutdown(SHUT_WR)`; pinned FRP compatibility reports `tcp_half_close=PASS`.
- [ ] ROUTED LAN target.
- [ ] Internet Access curl/wget/git/apt.
- [ ] denied Internet traffic cannot escape.
- [ ] multi-host matrix.
- [ ] MCP real operation on private/closed target.
- [ ] real ChatGPT Plus owner/UI connects to the public MCP endpoint.
- [ ] ChatGPT Plus OAuth Authorization Code / consent completes successfully.
- [ ] ChatGPT Plus tool discovery succeeds.
- [ ] one policy-allowed operation succeeds through ChatGPT Plus.
- [ ] one intentionally out-of-scope operation is denied through ChatGPT Plus.
- [ ] machine-side MCP/OAuth evidence and owner/UI evidence are both retained; neither is substituted for the other.

Platform evidence:

```text
Ubuntu 24=
Rocky Linux 8=
Rocky Linux 9=
Amazon Linux 2023=
macOS Apple Silicon=
Windows 10=
```


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

## 20. Mandatory pre-release exhaustive gates and Double Full Real E2E

- [ ] `CLI_FEATURE_SCENARIO_RECONCILIATION=PASS` on the same exact candidate before PASS1 starts.
- [ ] `FULL_USER_E2E PASS1=PASS` and `FULL_USER_E2E PASS2=PASS` are both retained on that same exact HEAD.
- [ ] `PRODUCT_QUALITY_CLOSURE=PASS`: the reconciliation and FULL_USER_E2E have no known in-scope product defect and no unresolved actionable product/usability improvement. This closes product-quality work only; it does not mean `RELEASE_READY=YES`.
- [ ] `python3 scripts/check-pre-release-exhaustive-gates.py --gate all` passes before automated release qualification starts.
- [ ] `.engineering/release.yaml` has `preflight_required: true` and uses the same exhaustive-gate validator.
- [ ] `CLI_PRODUCT_SURFACE_RECONCILIATION=PASS` on that same reconciliation evidence.
- [ ] reconciliation evidence records zero feature/CLI gaps, runtime-only CLI, duplicate/legacy/hidden paths, discovery/dead-end gaps, installer-guidance mismatches, destructive-confirmation/metadata drift, ERROR-with-RC0 cases, state/doc/example/role mismatches, workflow blockers, audit-owned cleanup residue, and `RUNTIME_MUTATION_ATTEMPT_COUNT=0`.
- [ ] no CLI/product/documentation surface change occurred after the reconciliation; otherwise rerun it before PASS1/PASS2 count.
- [ ] `FULL_REAL_E2E_PASS_1=PASS`
- [ ] `FULL_REAL_E2E_PASS_2=PASS`
- [ ] `PASS1_HEAD==PASS2_HEAD`
- [ ] `PASS1_HEAD==FINAL_QUALIFIED_HEAD`
- [ ] PASS1 terminal `summary.json` records `final_status=PASS`, exact unchanged HEAD, required evidence paths, and no mandatory FAIL/BLOCKED/NOT_RUN gate.
- [ ] PASS2 terminal `summary.json` records the same guarantees independently on the same exact HEAD.
- [ ] PASS1/PASS2 summary SHA256 values are retained in `qualification-evidence.json`.
- [ ] `scripts/check-release-qualification-evidence.py` revalidates the combined package on the exact tag/provenance HEAD.
- [ ] stable release-attest derives PASS1/PASS2/final HEAD and qualification evidence SHA256 from the validated package; there are no caller-supplied free-form PASS HEAD inputs.
- [ ] protected GitHub Environment `stable-release-qualification` has at least one required reviewer and administrator bypass is disabled.
- [ ] protected qualification approval records `PASS` and the exact prevalidated qualification evidence SHA256 from the same workflow run.
- [ ] stable binding rejects missing protected qualification approval or any reviewed/package SHA256 mismatch.
- [ ] no product/dependency change between passes.
- [ ] no tracked commit is created after PASS2; the immutable tag is that same provenance HEAD.

Any change resets the pass counter.

## 21. Artifacts

- [ ] artifacts built from `FINAL_QUALIFIED_HEAD`.
- [ ] artifact SHA256 recorded.
- [ ] manifest exact source HEAD/ref/FRP version/features correct.
- [ ] `features.mcp_included=true` whenever the v2.4.0 candidate bytes contain MCP Bridge/AI Access; this flag records feature presence, not qualification status.
- [ ] no secret/private lab metadata.
- [ ] final stable artifacts immutable.

## 22. Documentation

- [ ] README matches qualified behavior.
- [ ] `DOCUMENTATION_INDEX.md` correctly classifies canonical, operator, qualification, historical, and internal documents.
- [ ] Product Master matches qualified behavior.
- [ ] Control Plane Architecture matches implementation and contains no current-behavior first-match/per-rule-ALLOW-DENY drift.
- [ ] CLI/AI Master, CLI IA, and CLI Reference match tested grammar and semantics.
- [ ] `CONFIGURATION_BUNDLE.md` matches the qualified canonical parser/schema and Server/Agent context boundaries.
- [ ] Installation and upgrade guides use immutable-source/release references appropriate to the release channel.
- [ ] Remote Access guide matches Remote Service ownership, endpoint lifecycle, and BLACKLIST/WHITELIST behavior.
- [ ] Internet Access guide matches tested security behavior.
- [ ] AI Access/MCP guide matches qualified authentication, permission, and interoperability behavior.
- [ ] Troubleshooting guide matches tested failure/recovery behavior.
- [ ] Security doc current.
- [ ] Version policy current.
- [ ] Changelog only lists qualified scope.
- [ ] ConfigurationBundle/AI copy-paste examples use canonical public CLI only.
- [ ] known limits current.

## 23. Publication

Only after all gates:

- [ ] create immutable `v2.4.0` tag on final qualified HEAD.
- [ ] verify remote tag resolves to same HEAD.
- [ ] publish GitHub Release/artifacts/checksums/manifest.
- [ ] publish final release notes.
- [ ] atomically update stable channel.
- [ ] update public docs metadata.
- [ ] verify clean public install/bootstrap.

## 24. Final record

```text
RELEASE_VERSION=2.4.0
FINAL_QUALIFIED_HEAD=
FINAL_STATUS=PASS|PARTIAL|FAIL
RELEASE_READY=YES|NO
TAG_CREATED=YES|NO
RELEASE_PUBLISHED=YES|NO
STABLE_CHANNEL_UPDATED=YES|NO

CONTROL_PLANE_DB=
NETWORK_OBJECT_MODEL=
MANAGED_HOST_MODEL=
REMOTE_SERVICE_MODEL=
REMOTE_ACCESS_POLICY=
INTERNET_ACCESS_POLICY=
AI_ACCESS_POLICY=
POLICY_IMPACT_ANALYSIS=
REVISION_AUDIT=
RUNTIME_GENERATION_CONSISTENCY=
BACKUP_RESTORE=
MCP_REAL_E2E=
MCP_INCLUDED_IN_V2_4_0=YES
CHATGPT_PLUS_USER_AUTH_ACCEPTANCE=REQUIRED
CHATGPT_PLUS_USER_AUTH_STATUS=PASS|BLOCKED
CONFIGURATION_BUNDLE=
CONFIGURATION_DIRECT_CLI_PARITY=
CONFIGURATION_AI_COPY_PASTE_REAL_E2E=
ZERO_TOUCH_BOUNDED_BATCH=
CLI_PRODUCT_SURFACE_RECONCILIATION=PASS|FAIL
CLI_PRODUCT_SURFACE_EVIDENCE=
PRODUCT_QUALITY_CLOSURE=PASS|FAIL
FULL_REAL_E2E_PASS_1=
FULL_REAL_E2E_PASS_2=

UNRESOLVED_P0=
UNRESOLVED_P1=
UNRESOLVED_P2=
BLOCKERS=
```

`FINAL_STATUS=PASS` is invalid if any mandatory applicable gate lacks retained evidence.
