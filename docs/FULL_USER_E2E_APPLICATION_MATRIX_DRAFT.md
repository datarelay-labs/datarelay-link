# Data Relay Link — Full User E2E 116-ID Application Matrix (DRAFT)

**Status:** Owner applicability signature PENDING. Generated from canonical scenario headings on the documentation branch, not from actual test outcomes.

**Authority:** [FULL_USER_E2E_SCENARIOS.md](FULL_USER_E2E_SCENARIOS.md). Review with [E2E_TEST_METHOD_POLICY.md](E2E_TEST_METHOD_POLICY.md). No row marked PASS, NOT_APPLICABLE or NOT_IN_SCOPE.

This table is an **inventory and review queue**, not a coverage reduction. The existing scenario contract and supported platforms/topologies apply unchanged until each assertion/platform cell is reviewed and the exact full matrix is signed by the owner. All past-major regressions and platform-native behavior must be preserved; one scenario may have multiple Core, Platform, Multi-host and Lifecycle cells. Add assertion-level child records rather than replacing these 116 IDs.

Before signing, fill the missing platform/role/topology/Direct+AI applicability, mandatory negative assertions, evidence oracle, resource locks, past-major links, release-scope dependency and actual source-line reference for **every** row. Keep source line references dynamic (e.g. grep -n) because contract revisions shift line numbers.

| ID | Canonical heading / requirement | Family | Platform × assertion mapping | Prior-major linkage | Owner disposition |
|---|---|---|---|---|---|
| U-001 | Published SSH service — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-002 | HTTP, HTTPS, and Custom TCP services — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-003 | Remote Access policy from the user perspective — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-004 | Relay Host to another LAN destination — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-005 | Fixed TCP user path — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-006 | Internet Access real applications — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-007 | AI/MCP authorized and denied use — MANDATORY for v2.4.0 | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-008 | User continuity across restart and policy change — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-009 | Public hostname, public IP fallback, and Zero-Touch URL propagation — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-010 | Guided CLI user journey parity — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-011 | AI/MCP capability matrix and file transfer — MANDATORY for v2.4.0 | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-012 | Internet Access protocol/application coverage — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| U-013 | Cross-surface terminology, clarity, and operator-guidance consistency — MANDATORY | User | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-001 | First-use discovery and role correctness — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-002 | Zero-Touch enrollment — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-003 | Manual and bulk enrollment — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-004 | Remote Service lifecycle — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-005 | Server outage, offline Agent edit, and synchronization — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-006 | Agent lifecycle — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-007 | Agent ConfigurationBundle file/stdin — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-008 | Diagnostics and support bundle — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-009 | Product update and Relay Engine update separation — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-010 | Reboot/autostart recovery — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-011 | Agent uninstall/reinstall behavior — MANDATORY on disposable host | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-012 | Wrong-context commands — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-013 | AI-assisted one-resource CLI loop — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-014 | AI-assisted multi-resource ConfigurationBundle loop — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| O-015 | Wizard draft/cancel/invalid-input atomicity — MANDATORY | Operator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-001 | Managed Host inventory and lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-002 | Network Objects and Groups — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-003 | Service Objects and Groups — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-004 | Remote Access full policy lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-005 | Internet Access full policy lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-006 | AI Identity, permissions, AI Access, MCP TLS, OAuth approval, and logs — MANDATORY for v2.4.0 | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-007 | Reference protection — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-008 | Revisions, diff, audit, and rollback — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-009 | Backup and restore — MANDATORY on disposable environment | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-010 | Server ConfigurationBundle atomicity and parity — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-011 | Server system operations — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-012 | Zero-Touch capacity and credential lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-013 | Endpoint pools and allocation lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-014 | Concurrent/stale administrative change protection — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-015 | Fresh Server install / uninstall / reinstall — MANDATORY on disposable server | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-016 | AI workflow and CLI traceability audit — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-017 | Concurrent administrative writers — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-018 | Public hostname/bootstrap/installer configuration lifecycle — MANDATORY | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-019 | Prior-stable upgrade to candidate — MANDATORY when an upgrade path is claimed | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| A-020 | Update failure and recovery — MANDATORY on disposable environment | Administrator | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-001 | Allow and deny are both proven — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-002 | Invalid configuration is atomic — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-006 | Role/context correctness — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-007 | Server outage — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-008 | Agent or target outage — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-009 | Runtime activation failure and rollback — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-010 | Backup/restore negative cases — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-011 | Stale synchronized Agent catalog — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-012 | Offline Remote Service deletion — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-013 | Endpoint-pool exhaustion and recovery — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-014 | Name, reserved-token, duplicate, and selector corner cases — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-015 | Network interruption during live traffic — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-017 | DNS, TLS, and public-hostname failure/recovery — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-018 | ConfigurationBundle schema/patch corner cases — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-020 | Boundary and capacity off-by-one cases — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-021 | Failure during mutation/activation — MANDATORY on disposable environment | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-022 | Long-lived, half-close, abrupt-close, and idle connection cases — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-023 | Bootstrap catalog false-HEALTHY prevention — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-024 | Human/operator/admin misconfiguration and recovery matrix — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| S-025 | Repetition, idempotency, and sequence permutation — MANDATORY | Failure/Recovery | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-001 | All applicable test hosts online simultaneously — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-002 | Parallel enrollment across all hosts — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-003 | Parallel Remote Service creation and endpoint allocation — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-004 | Simultaneous real traffic on all hosts — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-005 | Parallel Internet Access from multiple protected sources — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-006 | Parallel AI/MCP identities and calls — MANDATORY for v2.4.0 | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-007 | Policy mutation while all-host traffic is active — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-008 | Simultaneous Agent restart/reconnect storm — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-009 | Server outage with all Agents active — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-010 | Parallel ConfigurationBundle apply — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-011 | Concurrent destructive/race cases — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-012 | All-host simultaneous reboot recovery — MANDATORY on disposable/approved hosts | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-013 | Parallel Agent update/restart convergence — MANDATORY on disposable/approved hosts | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-014 | Parallel mixed lifecycle operations — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| C-015 | Parallel role-and-mistake storm — MANDATORY | Concurrency/Multi-host | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-001 | Direct-path baseline — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-002 | Remote Access one-way throughput: User -> target — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-003 | Remote Access one-way throughput: target -> User — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-004 | Remote Access simultaneous full-duplex throughput — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-005 | Connection establishment rate / CPS — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-006 | Concurrent active connections — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-007 | Connect/request latency — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-008 | Mixed-service workload — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-009 | Multi-host scale — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-010 | Internet Access throughput and bidirectional application data — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-011 | AI/MCP performance — MANDATORY for v2.4.0 | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-012 | Connection churn and reconnect storm — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-013 | Soak / long-duration stability — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-014 | Backup/restart/recovery under load — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-015 | Aggregate all-host throughput and fairness — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-016 | CPS while throughput and policy load are active — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-017 | Recovery-time performance — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-018 | Operational commands under load — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-019 | Extended endurance profiles — OPTIONAL unless explicitly selected | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-020 | Network impairment characterization — MANDATORY when test infrastructure supports controlled impairment | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-021 | Saturation and post-saturation recovery — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-022 | Control-plane plus data-plane mixed pressure — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-023 | Maximum available topology mixed-stress operation — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| P-024 | Continuous function-under-load collision matrix — MANDATORY | Performance/Soak | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-001 | Exact cross-repository identity — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-002 | Plugin package and MCP declaration — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-003 | OAuth 2.1 / owner-consent flow — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-004 | MCP relay pass-through — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-005 | DRLink policy result passthrough — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-007 | Core vs Plugin acceptance separation — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-008 | OAuth concurrency and durable state — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-009 | Plugin OAuth state backup/restore — CONDITIONAL | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |
| X-010 | Real ChatGPT Plugin acceptance — CONDITIONAL when environment is available | External integration | REVIEW_REQUIRED (retain current contract) | REVIEW_REQUIRED | PENDING |

**Generated count:** 116 unique scenario IDs. Families: U=13, O=15, A=20, S=20, C=15, P=24, X=9.

**Known risk examples to map before sign-off:** false-HEALTHY after target outage; CLI rc=0 on activation failure; failed runtime generation/rollback guidance; prior-stable backup validation vs restore rejection; Windows Schannel enrollment; Windows uninstall confirmation/duplicate identity; Server public DNS hostname propagation; stale removed-Agent catalog; macOS sleep/wake Agent stale. These are illustrative, not a complete 14-major enumeration. Verify each against the finding ledger before assigning its regression cell.

**Current-run snapshot warning:** The review prompt reported 18 PASS, 62 PARTIAL, 2 FAIL, 9 BLOCKED_ENVIRONMENT and 25 NOT_RUN (116 total) in an earlier active run. Those are historical reported figures, not claims about today, and are intentionally not imported as matrix outcomes.
