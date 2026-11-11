# DRLink E2E feasibility and resource budget — 2026-11-11

**Purpose:** Review Claude's next independent 116-ID Full User E2E. This is a test-planning and evidence document, not a product release, a platform exclusion or a PASS. Canonical requirements remain in [FULL_USER_E2E_SCENARIOS.md](FULL_USER_E2E_SCENARIOS.md); methodology in [E2E_TEST_METHOD_POLICY.md](E2E_TEST_METHOD_POLICY.md).

## 1. Candidate and test topology observed

- The Codex test branch fix/cli100-codex-e2e-closure-20261110 was pushed at fdaddcb2cbce97c83c95e2bbe575cffce9f374d9. This is a **source commit**, not evidence of a published, immutable opt-in 2.4.0-rc.1 with a verified downloadable bundle hash. The Codex delegation was STOPPED_ITERATION_BUDGET (80th iteration); no two same-HEAD complete Full User E2E PASS runs were observed.
- The local main source is 02a1e498; origin/main is 90d2eb35. Neither may be silently substituted for the selected test candidate. Our test-budget branch and candidate HEAD are intentionally separate.
- Five assigned Linux SSH hosts passed product preinstall clean-room verification. No candidate was installed by cleanup.
- macOS Leeui-MacBookAir.local: supported Agent uninstall succeeded, preserved historical support bundle; the reverse-SSH listener on dev-drlink local 2222 later accepted TCP but hung before SSH banner. Mac AC and battery sleep settings showed 1 minute. Product clean-state and persistent SSH availability are separate facts.
- Windows DESKTOP-SLBCN3A: SSH on dev-drlink local 2223 works, but official Agent uninstall was rejected because durable Windows machine ID differs from enrolled client-state.json.machine_id. The enrolled client-id matches client-state; product and reverse-SSH remain. No forced identity rewrite.
- A-019 target SSH host key is untrusted, and A-019 VM had no network route. Neither prior-version installation nor cross-version restore qualification has been established.

## 2. Immediate change — maximum 30 public endpoint allocations

**Owner directive:** At most **30 concurrently live and 30 distinct RUN_ID-owned public endpoint ports** across normal + Fixed TCP pools, all participating physical hosts, and all parallel/retry lanes **combined**. Not 30 per scenario, not 30 per host. This cap does not change product capacity, TCP connection counts, CPS, or the separate 100 CLI-only scenario IDs.

- **A-013/S-013/S-020**: One shared, same-RUN_ID pool-capacity receipt; do not run full exhaustion separately for each scenario. Two isolated, product-supported 15-slot pools (normal + Fixed TCP) can each prove 14/15, a rejected 16th **request** (zero newly allocated endpoints), delete-one, and reuse; their ranges must have no more than 30 distinct ports **combined**. With a larger nonconfigurable real pool, test up to 30 and keep true maximum/max+1 assertions PARTIAL/BLOCKED, never PASS.
- **C-003/C-011/C-015/P-023/P-024**: Parallel creators must acquire one shared locked admission ledger before public endpoint creation. During performance, reuse existing allocated endpoints and raise connection pressure instead of creating more ports.
- **Control tool:** tools/e2e_port_budget.py runs per RUN_ID, pinned to the exact source HEAD, admits up to 30 active reservations, confirms real port observations, rejects duplicates and >30 distinct ports, and requires an owned cleanup receipt before release. The tool does not perform public product actions or certify traffic.

## 3. Other problematic test cases

| Priority | Canonical IDs | Actual obstacle or risk | Correct approach |
| --- | --- | --- | --- |
| P0 | **All 116; O-002/A-015** | No published exact RC artifact/hash; clean Linux hosts currently have no product | Freeze qualified immutable preview source, bundle hash, test-contract identity; install only on assigned disposable hosts and read back real installed Source HEAD. |
| P0 | **O-011/O-009, C-001/C-012/C-013** | Windows local uninstall blocked by persistent machine ID mismatch | Reconcile authoritative binding through supported and owner-approved recovery; never delete durable anchor or hide failure. Windows-dependent E2E stays BLOCKED. |
| P0 | **O-009/O-010, C-001/C-012, P-013** | Mac sleep and intermittent SSH banner timeout after successful uninstall | Establish stable awake/AC-powered management SSH without altering host trust; product Agent loss must be distinguished from controller path failure. |
| P0 | **A-019/A-020/A-009/S-010** | Prior-stable fixture and isolated upgrade/restore environment not ready; A-019 VM lacks route | Use trusted old-version package and disposable recovery topology. No restore over shared Server. |
| P0 | **U-007/U-011/A-006/C-006/P-011/X-001..X-010** | v2.4 AI/MCP mandatory language versus Product Master exclusion conflict noted by method policy; external owner OAuth/plugin/TLS may be absent | Resolve *claimed* candidate scope and owner-sign exact applicability matrix. Claimed functionality remains BLOCKED without real consent/traffic; no blanket N/A or PASS. |
| P0 | **U-009/A-018/S-017** | Public hostname/DNS, trust chain and Zero-Touch URL require controlled public resources | Verify real end-to-end hostname and certificate path; use isolated authorized DNS/CA fixture, never edit shared authoritative services for tests. |
| P1 | **A-013/S-013/S-020/C-003** | Real-pool max exhaustion may allocate hundreds of endpoints and repeat the same setup | Global 30-slot cap with reuse and explicit maximum-boundary evidence gap when real pool >30. |
| P1 | **A-015/A-009/A-020/S-021** | Server uninstall, restore, update-failure and activation injection are destructive | Only disposable isolated Server, backup/rollback state receipts and clean rollback. Unsupported fault injection stays BLOCKED for that assertion. |
| P1 | **C-012/C-009/S-015/S-007** | Simultaneous reboot/outage/network cuts can remove the only management SSH path | Verified independent OOB access, exclusive global lock and approved disposable hosts; protect reverse SSH, never reboot shared systems. |
| P1 | **P-005/P-006/P-012/P-021/P-023/P-024** | CPS, connection ramp, churn and mixed saturation can consume all CPU/FD/ports and run indefinitely | Predeclare finite ramp/timeout, stop at measured limiter, attribute bottleneck to DRLink vs target/generator, preserve cleanup and real integrity/policy checks. No invented numeric SLO. |
| P1 | **P-013/P-015/P-016/P-018** | Actual 3,600-second soak and 60-second warmup/300-second measurements expensive and redundant when dependent data path already failed | Retain mandatory timing for qualification; if the same-run product prerequisite failed, preserve FAIL_PRECONDITION and do not rerun equivalent load. |
| P1 | **P-020** | Controlled impairment unsupported on some assigned OS/controllers (historical netem unavailable on Rocky9) | Use an actually approved impairment-capable disposable host, else record conditional environment block and evidence. |
| P1 | **O-003/A-012/C-002/S-023** | Bulk enrollment and ticket-capacity checks may burn single-use credentials and accumulate stale identities | RUN_ID-owned enrollments/tickets, finite test-specific capacity after separate review, normal cleanup, no mutation of shared managed hosts. |
| P1 | **O-013/O-014/U-010/U-013** | AI adviser first response / novice discoverability cannot be proven by scripts preloaded with correct commands | Independent real Direct and AI-assisted user personas, exact first response, public CLI side effects and external traffic receipts. |
| P2 | **P-019** | Optional 8h/24h endurance may be mistaken for required P-013 soak | Existing contract is OPTIONAL unless explicitly selected; P-013 3,600-second soak remains mandatory. |
| P2 | **S-022/U-005** | Custom TCP response-after-EOF half-close unsupported by pinned FRP 0.71.0 | Keep the explicit unsupported subcase disposition, but execute other supported close/idle/abrupt behaviors and Fixed TCP tests. |

## 4. Completion conditions and limits

1. Freeze a qualified opt-in RC with source hash, bundle hash and exact TEST_CONTRACT_HEAD before Claude and owner use separate RUN_IDs on the **same published RC**. Do not assume a Git commit is a released artifact.
2. Per-lane preflight: assigned host identity, management path, installed Source HEAD, isolation/ownership, capacity and credentials, external dependencies, locked test-resource budgets and cleanup.
3. Run every safe, independent criterion; prerequisite failures block only dependent cells. Keep 116 original IDs, real direct/AI actors, native platform coverage, negative tests and actual application traffic.
4. Full qualification still requires supported applicable 116-ID evidence, an actual 3,600-second soak and two complete passes on the exact same candidate. Any material code change triggers a new RC and fresh qualification. No release approval implied.
