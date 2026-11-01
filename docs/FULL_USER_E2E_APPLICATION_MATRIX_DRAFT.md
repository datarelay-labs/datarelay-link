# Data Relay Link — Full User E2E 116-ID Application Matrix (DRAFT)

**Status: Owner applicability signature PENDING.** This draft records **every original canonical scenario** and direct traceability to the current Full User E2E contract. It does **not** change, narrow, waive or PASS any existing assertion.

Source: [FULL_USER_E2E_SCENARIOS.md](FULL_USER_E2E_SCENARIOS.md) at main commit `90d2eb359098d3aea9869bac024d96feea9c30ab` (line references are pinned to this version). Policy: [E2E_TEST_METHOD_POLICY.md](E2E_TEST_METHOD_POLICY.md).

**Historical major findings** are mapped from original immutable Claude Exploratory RUN_ID `cli100-fue2e-claude-20261101`, the `ledger/FINDINGS.tsv` snapshot (23 severity=major records); see [Issue #230](https://github.com/datarelay-labs/datarelay-link/issues/230). The 23 findings affect 26 unique scenario IDs, and **every major finding ID is represented**. They include environment-classified major reports and are **not all confirmed product defects**. An empty major-finding column does not demonstrate sufficient test coverage.

**How to interpret the new evidence columns:** `Explicit OS cues` and `Literal concern cues` are keyword references **appearing inside the source scenario's text**, not signed requirements, complete OS lists, or a risk ranking. `none explicit` does **not** mean Linux-only or N/A. The source may refer to other requirements by shared global contract or section. Treat exact platform / role / persona / assertion / negative traffic evidence / resource-lock / Wave A/B/C / supported release dependency as **REVIEW_REQUIRED** until qualified reviewers map them; historical major and OS-native regression cells cannot be reduced. If any contract or historical artifact changes, re-review source references before signing. This snapshot does not rewrite any existing exploratory test ledger.

**Next owner review:** For every ID attach its requirement assertions and one or more Core / Platform / Multi-host / Lifecycle cells as justified, actual supported OS versions/roles, independent traffic oracle, per-operation Preflight, wave/lock/resource ownership, historical major regression or explicit triage, and reviewer sign-off. No reduction is effective until the owner signs the **exact version** of the full approved matrix. 116 canonical IDs and 3,600-second Soak + double complete same-HEAD qualification remain in force.

| ID | Canonical heading | Family | Contract line | Explicit OS cues (not exhaustive) | Literal concern cues (not a test plan) | Historic major finding IDs | Platform × assertion mapping | Owner sign-off |
|---|---|---|---|---|---|---|---|---|
| U-001 | Published SSH service — MANDATORY | User | L1463 | none explicit | External | F-mac-cov-01, F-mac-cov-05, F-win-cov-02 | REVIEW_REQUIRED | PENDING |
| U-002 | HTTP, HTTPS, and Custom TCP services — MANDATORY | User | L1502 | none explicit | Security, External | F-mac-cov-01, F-mac-cov-02, F-mac-cov-05, F-win-cov-05, F-win-cov-12 | REVIEW_REQUIRED | PENDING |
| U-003 | Remote Access policy from the user perspective — MANDATORY | User | L1540 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| U-004 | Relay Host to another LAN destination — MANDATORY | User | L1581 | none explicit | External | F-mac-cov-01, F-mac-cov-05, F-u-traffic-08, F-win-cov-01, F-win-cov-07 | REVIEW_REQUIRED | PENDING |
| U-005 | Fixed TCP user path — MANDATORY | User | L1605 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| U-006 | Internet Access real applications — MANDATORY | User | L1624 | macOS, Ubuntu, Linux | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| U-007 | AI/MCP authorized and denied use — MANDATORY for v2.4.0 | User | L1703 | none explicit | Security, External | — | REVIEW_REQUIRED | PENDING |
| U-008 | User continuity across restart and policy change — MANDATORY | User | L1733 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| U-009 | Public hostname, public IP fallback, and Zero-Touch URL propagation — MANDATORY | User | L1748 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| U-010 | Guided CLI user journey parity — MANDATORY | User | L1761 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| U-011 | AI/MCP capability matrix and file transfer — MANDATORY for v2.4.0 | User | L1785 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| U-012 | Internet Access protocol/application coverage — MANDATORY | User | L1819 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| U-013 | Cross-surface terminology, clarity, and operator-guidance consistency — MANDATORY | User | L1836 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| O-001 | First-use discovery and role correctness — MANDATORY | Operator | L1906 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| O-002 | Zero-Touch enrollment — MANDATORY | Operator | L1920 | none explicit | none explicit | F-enr-mac-01, F-enr-mac2-05, F-enr-win-01 | REVIEW_REQUIRED | PENDING |
| O-003 | Manual and bulk enrollment — MANDATORY | Operator | L1945 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| O-004 | Remote Service lifecycle — MANDATORY | Operator | L1963 | none explicit | none explicit | F-u-traffic-08 | REVIEW_REQUIRED | PENDING |
| O-005 | Server outage, offline Agent edit, and synchronization — MANDATORY | Operator | L1987 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| O-006 | Agent lifecycle — MANDATORY | Operator | L2015 | none explicit | Lifecycle | F-enr-mac2-05 | REVIEW_REQUIRED | PENDING |
| O-007 | Agent ConfigurationBundle file/stdin — MANDATORY | Operator | L2030 | none explicit | none explicit | F-win-cov-07 | REVIEW_REQUIRED | PENDING |
| O-008 | Diagnostics and support bundle — MANDATORY | Operator | L2070 | none explicit | none explicit | F-enr-mac2-05 | REVIEW_REQUIRED | PENDING |
| O-009 | Product update and Relay Engine update separation — MANDATORY | Operator | L2080 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| O-010 | Reboot/autostart recovery — MANDATORY | Operator | L2099 | none explicit | Lifecycle, External | F-win-cov-02 | REVIEW_REQUIRED | PENDING |
| O-011 | Agent uninstall/reinstall behavior — MANDATORY on disposable host | Operator | L2114 | none explicit | Lifecycle | F-o-ops-05, F-o-ops-08 | REVIEW_REQUIRED | PENDING |
| O-012 | Wrong-context commands — MANDATORY | Operator | L2124 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| O-013 | AI-assisted one-resource CLI loop — MANDATORY | Operator | L2143 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| O-014 | AI-assisted multi-resource ConfigurationBundle loop — MANDATORY | Operator | L2168 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| O-015 | Wizard draft/cancel/invalid-input atomicity — MANDATORY | Operator | L2194 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| A-001 | Managed Host inventory and lifecycle — MANDATORY | Administrator | L2209 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| A-002 | Network Objects and Groups — MANDATORY | Administrator | L2228 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| A-003 | Service Objects and Groups — MANDATORY | Administrator | L2247 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| A-004 | Remote Access full policy lifecycle — MANDATORY | Administrator | L2268 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| A-005 | Internet Access full policy lifecycle — MANDATORY | Administrator | L2295 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| A-006 | AI Identity, permissions, AI Access, MCP TLS, OAuth approval, and logs — MANDATORY for v2.4.0 | Administrator | L2310 | none explicit | Security, External | — | REVIEW_REQUIRED | PENDING |
| A-007 | Reference protection — MANDATORY | Administrator | L2359 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| A-008 | Revisions, diff, audit, and rollback — MANDATORY | Administrator | L2370 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| A-009 | Backup and restore — MANDATORY on disposable environment | Administrator | L2382 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| A-010 | Server ConfigurationBundle atomicity and parity — MANDATORY | Administrator | L2410 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| A-011 | Server system operations — MANDATORY | Administrator | L2429 | none explicit | Lifecycle, Security, External | — | REVIEW_REQUIRED | PENDING |
| A-012 | Zero-Touch capacity and credential lifecycle — MANDATORY | Administrator | L2454 | none explicit | Multi-host, Security | — | REVIEW_REQUIRED | PENDING |
| A-013 | Endpoint pools and allocation lifecycle — MANDATORY | Administrator | L2474 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| A-014 | Concurrent/stale administrative change protection — MANDATORY | Administrator | L2489 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| A-015 | Fresh Server install / uninstall / reinstall — MANDATORY on disposable server | Administrator | L2500 | none explicit | Lifecycle | F-srv-b-02 | REVIEW_REQUIRED | PENDING |
| A-016 | AI workflow and CLI traceability audit — MANDATORY | Administrator | L2511 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| A-017 | Concurrent administrative writers — MANDATORY | Administrator | L2558 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| A-018 | Public hostname/bootstrap/installer configuration lifecycle — MANDATORY | Administrator | L2578 | Windows, Linux | Lifecycle | F-srv-admin2-15 | REVIEW_REQUIRED | PENDING |
| A-019 | Prior-stable upgrade to candidate — MANDATORY when an upgrade path is claimed | Administrator | L2609 | OS-wide | Lifecycle | F-srv-b-04, F-srv-b-05 | REVIEW_REQUIRED | PENDING |
| A-020 | Update failure and recovery — MANDATORY on disposable environment | Administrator | L2637 | none explicit | Lifecycle | F-srv-b-05 | REVIEW_REQUIRED | PENDING |
| S-001 | Allow and deny are both proven — MANDATORY | Failure/Recovery | L2660 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| S-002 | Invalid configuration is atomic — MANDATORY | Failure/Recovery | L2664 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-006 | Role/context correctness — MANDATORY | Failure/Recovery | L2668 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-007 | Server outage — MANDATORY | Failure/Recovery | L2672 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| S-008 | Agent or target outage — MANDATORY | Failure/Recovery | L2676 | none explicit | External | F-s-fail-01, F-s-fail-07, F-win-cov-01, F-win-cov-02 | REVIEW_REQUIRED | PENDING |
| S-009 | Runtime activation failure and rollback — MANDATORY | Failure/Recovery | L2691 | none explicit | none explicit | F-srv-b-12, F-srv-b-13 | REVIEW_REQUIRED | PENDING |
| S-010 | Backup/restore negative cases — MANDATORY | Failure/Recovery | L2695 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| S-011 | Stale synchronized Agent catalog — MANDATORY | Failure/Recovery | L2699 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-012 | Offline Remote Service deletion — MANDATORY | Failure/Recovery | L2703 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-013 | Endpoint-pool exhaustion and recovery — MANDATORY | Failure/Recovery | L2707 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-014 | Name, reserved-token, duplicate, and selector corner cases — MANDATORY | Failure/Recovery | L2720 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-015 | Network interruption during live traffic — MANDATORY | Failure/Recovery | L2724 | none explicit | Lifecycle | F-s-fail-01, F-win-cov-01, F-win-cov-12 | REVIEW_REQUIRED | PENDING |
| S-017 | DNS, TLS, and public-hostname failure/recovery — MANDATORY | Failure/Recovery | L2730 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| S-018 | ConfigurationBundle schema/patch corner cases — MANDATORY | Failure/Recovery | L2734 | none explicit | none explicit | F-win-cov-07 | REVIEW_REQUIRED | PENDING |
| S-020 | Boundary and capacity off-by-one cases — MANDATORY | Failure/Recovery | L2738 | none explicit | Multi-host | — | REVIEW_REQUIRED | PENDING |
| S-021 | Failure during mutation/activation — MANDATORY on disposable environment | Failure/Recovery | L2744 | none explicit | none explicit | F-srv-b-12, F-srv-b-13 | REVIEW_REQUIRED | PENDING |
| S-022 | Long-lived, half-close, abrupt-close, and idle connection cases — MANDATORY | Failure/Recovery | L2748 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| S-023 | Bootstrap catalog false-HEALTHY prevention — MANDATORY | Failure/Recovery | L2761 | none explicit | External | F-s-fail-01, F-s-fail-07, F-win-cov-05 | REVIEW_REQUIRED | PENDING |
| S-024 | Human/operator/admin misconfiguration and recovery matrix — MANDATORY | Failure/Recovery | L2765 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| S-025 | Repetition, idempotency, and sequence permutation — MANDATORY | Failure/Recovery | L2771 | none explicit | Lifecycle, Multi-host, Security, Performance | — | REVIEW_REQUIRED | PENDING |
| C-001 | All applicable test hosts online simultaneously — MANDATORY | Concurrency/Multi-host | L2781 | Windows, macOS, Amazon Linux, Rocky, Ubuntu, Linux | Multi-host | — | REVIEW_REQUIRED | PENDING |
| C-002 | Parallel enrollment across all hosts — MANDATORY | Concurrency/Multi-host | L2814 | none explicit | Lifecycle, Multi-host, Security | F-enr-mac-01, F-enr-mac2-05 | REVIEW_REQUIRED | PENDING |
| C-003 | Parallel Remote Service creation and endpoint allocation — MANDATORY | Concurrency/Multi-host | L2827 | none explicit | none explicit | F-mac-cov-02, F-mac-cov-05 | REVIEW_REQUIRED | PENDING |
| C-004 | Simultaneous real traffic on all hosts — MANDATORY | Concurrency/Multi-host | L2840 | none explicit | Multi-host, Performance | — | REVIEW_REQUIRED | PENDING |
| C-005 | Parallel Internet Access from multiple protected sources — MANDATORY | Concurrency/Multi-host | L2855 | none explicit | Multi-host, Security | — | REVIEW_REQUIRED | PENDING |
| C-006 | Parallel AI/MCP identities and calls — MANDATORY for v2.4.0 | Concurrency/Multi-host | L2861 | none explicit | Multi-host, Security, External | — | REVIEW_REQUIRED | PENDING |
| C-007 | Policy mutation while all-host traffic is active — MANDATORY | Concurrency/Multi-host | L2874 | none explicit | Multi-host | — | REVIEW_REQUIRED | PENDING |
| C-008 | Simultaneous Agent restart/reconnect storm — MANDATORY | Concurrency/Multi-host | L2884 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| C-009 | Server outage with all Agents active — MANDATORY | Concurrency/Multi-host | L2897 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| C-010 | Parallel ConfigurationBundle apply — MANDATORY | Concurrency/Multi-host | L2903 | none explicit | Multi-host | F-mac-cov-05 | REVIEW_REQUIRED | PENDING |
| C-011 | Concurrent destructive/race cases — MANDATORY | Concurrency/Multi-host | L2916 | none explicit | Lifecycle, Multi-host | — | REVIEW_REQUIRED | PENDING |
| C-012 | All-host simultaneous reboot recovery — MANDATORY on disposable/approved hosts | Concurrency/Multi-host | L2928 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| C-013 | Parallel Agent update/restart convergence — MANDATORY on disposable/approved hosts | Concurrency/Multi-host | L2941 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| C-014 | Parallel mixed lifecycle operations — MANDATORY | Concurrency/Multi-host | L2954 | none explicit | none explicit | F-mac-cov-02, F-mac-cov-05, F-win-cov-12 | REVIEW_REQUIRED | PENDING |
| C-015 | Parallel role-and-mistake storm — MANDATORY | Concurrency/Multi-host | L2968 | none explicit | Multi-host, Performance | — | REVIEW_REQUIRED | PENDING |
| P-001 | Direct-path baseline — MANDATORY | Performance/Soak | L3046 | none explicit | Performance | — | REVIEW_REQUIRED | PENDING |
| P-002 | Remote Access one-way throughput: User -> target — MANDATORY | Performance/Soak | L3054 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| P-003 | Remote Access one-way throughput: target -> User — MANDATORY | Performance/Soak | L3067 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| P-004 | Remote Access simultaneous full-duplex throughput — MANDATORY | Performance/Soak | L3073 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| P-005 | Connection establishment rate / CPS — MANDATORY | Performance/Soak | L3081 | none explicit | External, Performance | F-p-perf-01 | REVIEW_REQUIRED | PENDING |
| P-006 | Concurrent active connections — MANDATORY | Performance/Soak | L3098 | none explicit | Multi-host | — | REVIEW_REQUIRED | PENDING |
| P-007 | Connect/request latency — MANDATORY | Performance/Soak | L3113 | none explicit | Performance | — | REVIEW_REQUIRED | PENDING |
| P-008 | Mixed-service workload — MANDATORY | Performance/Soak | L3124 | none explicit | Multi-host | — | REVIEW_REQUIRED | PENDING |
| P-009 | Multi-host scale — MANDATORY | Performance/Soak | L3136 | none explicit | Multi-host | — | REVIEW_REQUIRED | PENDING |
| P-010 | Internet Access throughput and bidirectional application data — MANDATORY | Performance/Soak | L3162 | none explicit | Multi-host, Security, Performance | — | REVIEW_REQUIRED | PENDING |
| P-011 | AI/MCP performance — MANDATORY for v2.4.0 | Performance/Soak | L3174 | none explicit | Multi-host, Security, External, Performance | — | REVIEW_REQUIRED | PENDING |
| P-012 | Connection churn and reconnect storm — MANDATORY | Performance/Soak | L3191 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| P-013 | Soak / long-duration stability — MANDATORY | Performance/Soak | L3204 | none explicit | Lifecycle, Security, Performance | — | REVIEW_REQUIRED | PENDING |
| P-014 | Backup/restart/recovery under load — MANDATORY | Performance/Soak | L3221 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| P-015 | Aggregate all-host throughput and fairness — MANDATORY | Performance/Soak | L3232 | none explicit | Multi-host, Performance | — | REVIEW_REQUIRED | PENDING |
| P-016 | CPS while throughput and policy load are active — MANDATORY | Performance/Soak | L3249 | none explicit | Performance | — | REVIEW_REQUIRED | PENDING |
| P-017 | Recovery-time performance — MANDATORY | Performance/Soak | L3264 | none explicit | Lifecycle | — | REVIEW_REQUIRED | PENDING |
| P-018 | Operational commands under load — MANDATORY | Performance/Soak | L3288 | none explicit | Lifecycle, Security | — | REVIEW_REQUIRED | PENDING |
| P-019 | Extended endurance profiles — OPTIONAL unless explicitly selected | Performance/Soak | L3312 | none explicit | Performance | — | REVIEW_REQUIRED | PENDING |
| P-020 | Network impairment characterization — MANDATORY when test infrastructure supports controlled impairment | Performance/Soak | L3323 | none explicit | Performance | — | REVIEW_REQUIRED | PENDING |
| P-021 | Saturation and post-saturation recovery — MANDATORY | Performance/Soak | L3337 | none explicit | Multi-host | F-p-perf-01 | REVIEW_REQUIRED | PENDING |
| P-022 | Control-plane plus data-plane mixed pressure — MANDATORY | Performance/Soak | L3350 | none explicit | Lifecycle, Multi-host, Security | — | REVIEW_REQUIRED | PENDING |
| P-023 | Maximum available topology mixed-stress operation — MANDATORY | Performance/Soak | L3363 | none explicit | Lifecycle, Multi-host, Security, External, Performance | — | REVIEW_REQUIRED | PENDING |
| P-024 | Continuous function-under-load collision matrix — MANDATORY | Performance/Soak | L3426 | Windows, macOS, Amazon Linux, Rocky, Ubuntu, Linux, OS-wide | Lifecycle, Multi-host, Security, External, Performance | — | REVIEW_REQUIRED | PENDING |
| X-001 | Exact cross-repository identity — CONDITIONAL | External integration | L3793 | none explicit | none explicit | — | REVIEW_REQUIRED | PENDING |
| X-002 | Plugin package and MCP declaration — CONDITIONAL | External integration | L3807 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| X-003 | OAuth 2.1 / owner-consent flow — CONDITIONAL | External integration | L3813 | none explicit | Security, External | — | REVIEW_REQUIRED | PENDING |
| X-004 | MCP relay pass-through — CONDITIONAL | External integration | L3829 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| X-005 | DRLink policy result passthrough — CONDITIONAL | External integration | L3845 | none explicit | Security | — | REVIEW_REQUIRED | PENDING |
| X-007 | Core vs Plugin acceptance separation — CONDITIONAL | External integration | L3857 | none explicit | External | — | REVIEW_REQUIRED | PENDING |
| X-008 | OAuth concurrency and durable state — CONDITIONAL | External integration | L3869 | none explicit | Lifecycle, Multi-host, External | — | REVIEW_REQUIRED | PENDING |
| X-009 | Plugin OAuth state backup/restore — CONDITIONAL | External integration | L3881 | none explicit | Lifecycle, Security, External | — | REVIEW_REQUIRED | PENDING |
| X-010 | Real ChatGPT Plugin acceptance — CONDITIONAL when environment is available | External integration | L3887 | OS-wide | Lifecycle, Multi-host, Security, External, Performance | — | REVIEW_REQUIRED | PENDING |

**Provenance check:** 116 unique scenario IDs, all in original order; 23 / 23 historic major IDs mapped across 26 scenarios. No PASS or NOT_APPLICABLE inferred, no existing scenario requirement changed.
