# Data Relay Link — Full User E2E Test Method and Evidence Policy

**Status:** Documentation change proposal; applies to new runs only after owner approves the applicable matrix and contract revision. Existing active RUN_IDs, worker assignments, historical ledgers and existing release gates are unchanged.
**Source of truth:** [FULL_USER_E2E_SCENARIOS.md](FULL_USER_E2E_SCENARIOS.md) (116 canonical scenario IDs); [E2E_EXECUTION_PROCEDURE.md](E2E_EXECUTION_PROCEDURE.md) (execution); [RELEASE_VALIDATION.md](RELEASE_VALIDATION.md) (release).
**Draft inventory:** [FULL_USER_E2E_APPLICATION_MATRIX_DRAFT.md](FULL_USER_E2E_APPLICATION_MATRIX_DRAFT.md).
**Date:** 2026-11-01. This document concerns test-method improvements, not product changes, feature de-scoping, or release approval.

## 1. Non-negotiable quality and coexistence rules

1. Preserve all 116 IDs, scenario assertions, genuine Direct/AI roles where required, negative security cases, supported platform and topology claims, real traffic, applicable 3,600-second soak and two complete same-HEAD Full Real E2E PASS runs. A Smoke, Delta or historical result does not replace any qualifying full run.
2. Do not remove platform-specific coverage or regressions for confirmed major defects. A proposed Core reference host is never a substitute for native Windows/macOS lifecycle, OS credential/trust, power management or uninstall behavior.
3. Incomplete, blocked, inconclusive, stale, unexecuted or environment-unavailable evidence is not PASS or automatically NOT_APPLICABLE. Unsupported scope requires documented product/release evidence and owner review, not a convenient missing test lab.
4. Never change an active Claude/Codex/ChatGPT worker's RUN_ID, test environment, frozen candidate, worktree or live ledger. Do not reclassify previous test results retroactively. Historical results stay immutable; any migration is a derived view with traceable provenance.
5. No product code change, production effect, release, merge, or new global test-start veto is authorized by this methodology. Owner-private host routes and secrets stay outside tracked documents. Readiness is per operation; independent permitted lanes continue if an unrelated prerequisite is missing.
6. The owner-approved **direction** is risk-based planning, not approval of individual scenario exclusions. The applicability matrix is a draft until the owner explicitly signs its reviewed, exact-revision contents.
7. If a test/release document conflicts with current product code, actual qualified release scope, or another contract, record a conflict for resolution; do not silently weaken one source. In particular, current Full User E2E labels AI/MCP mandatory for v2.4.0 while the Product Master describes an MCP-excluded v2.4.0 line. Determine the actual candidate/release contract and obtain owner disposition before asserting an exclusion or release PASS.

## 2. Three complementary tracks (A)

| Track | Purpose | Scheduling | May grant release PASS? |
|---|---|---|---|
| Smoke | Quick repeatable regression guard, including critical past-major regressions | At relevant product HEAD / artifact change; proposed initial size 30–40 and target under 2h are unvalidated planning estimates | **No** |
| Qualification | Complete required scenario×applicable-platform×role×assertion and topology evidence, frozen exact product and contract identities | For release candidate; two complete PASS runs at same exact HEAD | **Yes, only if every other release gate also passes** |
| Exploratory | Independent beginner personas, unexpected inputs, UX discoveries, adversarial behavior | At material feature change or an owner-approved time/risk budget; never replace required final coverage | **No** |

Exploratory has a bounded discovery session, not an obligation to keep re-running until zero new findings. Every credible major/high-impact finding must be triaged for reproducibility, severity, affected requirement/cell, regression test and release-blocking disposition. Unresolved release-blocking findings veto qualification, regardless of the Qualification track's individual PASS cells. All findings remain auditable and no evidence is erased after a later PASS.

Performance/load and Soak are **separate attributable jobs inside the qualification schedule**, not a fourth way to omit mandatory scenarios. Preserve the existing functional-under-load checks and release requirements. Never invent a performance SLO.

## 3. Requirement and platform applicability matrix (B)

Maintain exactly one row per canonical U/O/A/S/C/P/X ID in the draft inventory. For each ID attach:
- authoritative heading, scenario contract reference, requirement(s), positive and negative assertions, failure severity and known-major regression link(s);
- platform and role applicability (Server, Agent, supported OS version), topology dependencies, and whether an assertion is Core, Platform, Multi-host or Lifecycle; a scenario may require **multiple** cell kinds;
- required Direct and AI-assisted persona receipts where the live contract requires them, minimum number of independent hosts, test-fixture ownership and independently observed oracle;
- required evidence, predecessor/prerequisite IDs, exclusive global resources, candidate release scope, reviewer/owner disposition and reason if a cell is NOT_APPLICABLE.

A single example Linux Agent may demonstrate a shared Core protocol assertion; it cannot replace Windows Schannel, native Windows uninstall/reinstall, macOS launchd/sleep/wake/reconnect, Linux systemd, platform bootstrap, or OS-specific persistence assertions. Preserve actual physical/VM/system-service qualification level; a container PASS is not equivalent.

**Matrix safety:** Before owner signature, every not-yet-mapped applicability remains REVIEW_REQUIRED, *not* NOT_IN_SCOPE, NOT_RUN(owner skip), or PASS. No reduction is effective merely because a draft suggests fewer cells. Compare the matrix against all 116 current ID headings, historical major findings and the candidate's supported platform/topology claims. A discrepancy keeps the current stricter contract in force.

## 4. Independent test oracles and harness correctness (C)

For repeatable workflows, use a deterministic harness to collect evidence of setup → action → actual target effect → deny/allow verification → teardown. An exit code, CLI success string, online registry row, synthetic fixture, simulated API response or a script claiming PASS is not sufficient to prove a real User E2E result. Prefer external client/receiver traffic, independently observed target bytes/commands, saved public CLI output, protected audit receipt, and post-operation identity/state checks. For security-negative paths, establish that the forbidden destination or protected service was **not reached**; an error response alone is insufficient if a bypass can succeed.

Harness controls:
- unit-test the oracle against both known-good and deliberately bad evidence (including false-HEALTHY, rc=0 on failed activation, stale catalog and silent rollback error);
- run mutation/fault-injection checks against disposable assets only, with the right exclusive lock;
- record harness version/hash, stdout/stderr/exit code, timestamps and raw evidence references; distinguish test-harness bug from product bug;
- quarantine flaky assertions: retain every attempt; never turn intermittent FAIL into PASS through repeated retries without triage and root-cause evidence;
- do not make a harness the Direct User or AI-assisted actor where persona execution is contractually required; retain original first AI advice and genuine public UX discovery.

Choose the initial automation candidates by security impact, independently verifiable observable results, prior major linkage and repetition cost, not usage frequency alone. Suggested order: candidate identity; Zero-Touch enrollment; actual SSH traffic; identity/port continuity; activation rc/failure; server catalog cleanup; allowed Remote Access; denied Remote Access; allowed/denied egress; update/restore rollback. This is a design order, not a claim that these tests have already run.

## 5. Per-operation Preflight (D)

Per participating host and lane verify owner-approved scope, installed artifact/hash and exact Source HEAD, test-contract HEAD, native OS role and service state, OOB/management path separately from product channel, sufficient capacity, stable DNS/TLS for the **particular** dependent scenario, test identity/credential presence without revealing secrets, expected cleanup ownership, power/sleep management, and exclusive lock availability. Record PASS, FAIL or BLOCKED with precise reasons for that lane. A missing Windows reverse SSH path or macOS test-host sleep prevention must not be mistaken for proof of a product Agent failure; also do not let lab-management fixes mask a product defect.

Missing public DNS/trusted cert or external AI/MCP dependency blocks the dependent required assertion until its necessity is resolved. Owner sign-off for a nonclaimed feature is required before changing applicability. List each external dependency with owner, release, evidence, due point and *blocks-release?* decision. No arbitrary NOT_IN_SCOPE from an unavailable lab. Never provision, alter firewall/DNS, modify credentials, or remove host state merely because Preflight detected a problem; those remain separately authorized actions.

Preflight is diagnostic and per-lane readiness: it is **not** reintroduction of LAB_GO or a global execution barrier. Other independent, authorized functional tests continue.

## 6. Cell evidence, state and aggregate ledger (E)

Keep the existing exactly-116-row canonical 'ledger/scenario-results.tsv' as the authoritative **scenario-level projection** for compatibility. Add an append-only 'ledger/cell-events.tsv' within each *new* RUN_ID as the provenance of every platform/role/assertion attempt; do not overwrite current active-run evidence and do not rewrite history to fit a summary.

Proposed cell schema (schema version required):

    RUN_ID  TEST_CONTRACT_HEAD  PRODUCT_SOURCE_HEAD  ARTIFACT_SHA256
    SCENARIO_ID  ASSERTION_ID  CELL_KIND  PLATFORM  OS_VERSION  HOST_ROLE  HOST_ID
    TOPOLOGY  PERSONA_ROLE  ATTEMPT_ID  START_UTC  END_UTC
    EXECUTION_STATE  OUTCOME  REASON_CODE  PREREQUISITE_ID
    RESOURCE_LOCK_KEY  HARNESS_HASH  EVIDENCE_URI  EVIDENCE_SHA256
    FINDING_ID  OWNER_SCOPE_REF  REVIEWER_DISPOSITION

'EXECUTION_STATE' = NOT_RUN | RUNNING | COMPLETED | BLOCKED | INVALIDATED.
'OUTCOME' = PASS | FAIL | INCONCLUSIVE | NONE.
'REASON_CODE' includes PRODUCT_DEFECT, PLATFORM_DEFECT, HARNESS_DEFECT, ENVIRONMENT, TOOLING, MANAGEMENT_PATH, CONCURRENT_STATE, PREREQUISITE_FAILURE, OWNER_SKIP, RELEASE_SCOPE_NOT_APPLICABLE, and EVIDENCE_STALE. Do not represent PARTIAL or NOT_IN_SCOPE as an independent cell PASS status.

Deterministic scenario projection:
1. Resolve the **approved** applicability set for this exact release, contract version, host roles and topology. Keep one canonical scenario row per ID.
2. Require each mandatory assertion, applicable platform/topology, genuine persona and required repeat to have supported current-run evidence on the same qualified candidate; PASS requires all of them PASS and no unresolved release-blocking finding.
3. Any observed required FAIL makes the scenario FAIL; even a newer PASS after an unexplained earlier FAIL demands documented triage/disposition. Missing or unfinished cells make the scenario PARTIAL/NOT_RUN. Blocked cells preserve their exact blocking category and prevent full aggregate PASS.
4. Precondition failures are not a harmless environment skip: preserve the causal failed scenario and dependent cells. Invalidated-by-concurrency evidence is never PASS and must be reacquired under isolated conditions.
5. A truly inapplicable cell requires specific product/release support evidence, an owner-approved matrix revision and an audit trail; 'owner skip' remains NOT_RUN and cannot qualify.
6. Worker authors append events for **their own** cells; one deterministic single-writer reducer exclusively materializes scenario totals and final JSON from the immutable events. No two workers update the same scenario total row. Preserve atomic checkpoints, unique event IDs and referential integrity.
7. A scenario report total is recomputed, not hand-counted. A mismatch between events, 116-row projection, summary and release JSON is REPORT_CONSISTENCY_FAIL. Keep separate counts for execution coverage, assertion PASS, blocked prerequisites and product defects. Never infer product quality from raw scenario PASS percentage alone.

Existing run/ledger formats are not migrated mid-flight. Treat this schema as a design until an approved implementation and migration check pass.

## 7. Safe scheduling, exclusive resources and lifecycle (F)

- Wave A: independent read-only or *actually isolated* namespaced tests. Namespaced object names alone do not isolate allocator, port pools, global policy, trust stores, enrollment capacity, log service, restart or shared Server state.
- Wave B: serialized/shared-global mutations (policy mode, CA, restore, restart, update, allocator exhaustion, global revocation, state migration, rollback) under an explicit exclusive resource lock.
- Wave C: destructive/failure-injection tests on disposable, independently owned Server/Client state with teardown and post-test integrity checks. Keep separate management routes intact.
- Deliberate concurrency/race tests are a controlled group holding a scope-specific lock, not an excuse for unrelated workers to modify global state simultaneously.

Record lock owner, acquired/released UTC, resource key, baseline state snapshot/hash, mutation manifest and final state comparison. Failed cleanup/lock release is a blocker for subsequent dependent lanes, not an invitation to reset other workers' environment. The ownership rule extends to process PID/TTY, TCP port, DNS name, endpoint allocation, private CA/PKI, system service, backup artifact and client enrollment. Preserve immutable release and historical test evidence.

## 8. Performance and Soak treatment (G)

Use independent performance jobs with 60-second warmup and 300-second steady measurements when required by the current contract; ensure throughput, CPS, p50/p95/p99, errors, CPU/RSS/FD, data-integrity checks and baseline/recovery data are collected. Keep a short reconnection/continuous-traffic check in functional coverage to expose quick leaks and stale sessions. Separate longer resource-growth, gradual degradation and reconnection accumulation evidence into the mandatory 3,600-second soak when qualification requires it.

A proposal to run Soak only once per release candidate is **not approved**. Preserve the existing Double Full Real E2E / Soak obligation unless a future separately approved contract revision explicitly changes it. An owner-directed skip for one exploratory/current run is NOT_RUN(owner skip), never a completed qualification gate. A missing numeric SLO yields MEASURED_NOT_QUALIFIED, not invented numerical PASS.

## 9. Delta selection and exact-HEAD final acceptance (H)

During development, map each defect and changed file to requirements, assertions, OS-specific paths, shared libraries, security boundaries, state migrations and prior regressions. Run affected cells plus mandatory Smoke; extend regression when dependency mapping is incomplete. A targeted PASS clears only the identified defect, not unrelated cells or the final release counter. Changes to common parser/config/state/PKI/installer paths trigger broad-impact review.

Once the final candidate is frozen, execute the applicable complete Full User E2E **twice** on the same exact source/build identity, with no unresolved release blocker and valid performance/Soak/negative traffic evidence. A qualifying product or dependency/artifact change between passes resets the counter. Neither historical receipts, per-platform partial passes, Delta, Smoke, exploratory findings, nor a stale HEAD substitutes for these gates.

## 10. Operational safety and Zero-Touch UX (I)

Delete test artifacts only from explicit manifest paths owned by the current RUN_ID and only within the authorized disposable test boundary; never wildcard-clean or delete another worker's evidence. Existing active tests remain untouched.

Zero-Touch length limits are suitable PR-time unit tests but do **not** prove execution. Retain actual Linux/macOS and Windows launcher copy/paste, real install, trustworthy download/verification (including Windows hash-before-execute), certificate validation/revocation behavior, registration, reconnect, identity preservation and operator-visible error recovery. Record command length as a measured diagnostic; do not change present product acceptance limits without separate product approval.

## 11. Planning and owner decisions (seven recorded directions)

| # | Direction | Status |
|---|---|---|
| 1 | Risk-based Qualification planning, retain all platform-native and previous-major regressions | Method direction; individual applicability NOT signed |
| 2 | Integration by release; mandatory DNS/TLS path remains a gate when claimed, AI/MCP version scope requires reconciliation | Conditional; specific release claims pending verification |
| 3 | Maintain existing 3,600-second Soak and double Full Real E2E requirement | Retained; no contract relaxation |
| 4 | Time/risk-bounded Exploratory; unresolved release-blocking findings veto release | Method direction |
| 5 | Execution state/outcome/reason separation; immutable historic evidence | Method direction; schema implementation not yet approved |
| 6 | Owner reviews and signs completed scenario applicability matrix before any reduction | PENDING |
| 7 | Test-method documentation separate from product bugfix issue/PR; draft review before merge | This change stays documentation-only draft |

This table is a policy planning record, not a forged owner-signature or confirmation that requirements disappeared. Owner approval of this document does not sign individual cells in the matrix.

## 12. Implementation order and review acceptance

1. Freeze current test-method baseline, all 116 IDs, contract references, supported platforms, known major defect IDs and immutable active-run evidence. Identify conflicts, including MCP-in-v2.4 applicability, for explicit release-scope resolution.
2. Build and independently review the scenario×requirements×platform×assertion matrix and identify missing/duplicated/unsafe cells. Hold every proposed reduction pending owner signature. No blanket N/A.
3. Define and version cell-state schema, precedence and deterministic reducer + controlled legacy projection; prove lossless accounting with synthetic fixtures for PASS, FAIL, blocked, incomplete, stale, simultaneous events and flaky attempts.
4. Define per-operation Preflight, test-resource locks, Wave A/B/C admission and cleanup evidence; validate it on isolated fixtures before any user test run.
5. Build independent-oracle harness and risk-selected Smoke candidates, including every past major regression; retain genuine beginner Direct/AI exploratory paths.
6. Run one **non-release** Qualification rehearsal on a new RUN_ID to evaluate completeness, conflicts and duration; record actual cost/quality metrics rather than 2h/30–40 marketing estimates.
7. After owner-approved coverage and contract/implementation, execute release-required complete qualification passes and Soak without reusing old receipts.

For the **documentation-only draft**, acceptance means: 116 unique unchanged IDs, traceable contract headings, no removals/downgraded tests, no source changes, no silent release-gate relaxation, no active-run mutation, no unauthorized production action, and a separate draft PR for review.

Track: mandatory requirement coverage; platform-specific mandatory coverage; unverified high-risk cells; genuine external traffic/negative evidence rate; unresolved major regressions; environment/tool blockers; harness false-PASS/false-FAIL; flaky attempts; per-lane elapsed time and duplicated runs. Do not fabricate targets or outcomes.
