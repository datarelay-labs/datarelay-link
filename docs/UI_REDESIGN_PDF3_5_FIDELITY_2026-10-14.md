# Data Relay Link UI Redesign — PDF Pages 3–5 Fidelity Matrix

Status: SOURCE / FIXTURE COMPARISON COMPLETE; AUTHENTICATED BROWSER FIDELITY OPEN

The owner-provided five-page DRLink_UI_Reanalysis_Decision_20261014.pdf was
recovered from the authorized project Library on 2026-10-14. The roadmap
no-omission register already records SHA256
10dc9a02f969b4268d77bd2a439d055ba1fd0a2827b77ebdf77b5531eb4ff300.
The PDF itself is not copied into the repository.

This matrix compares pages 3–5 with current product source and retained
browser-fixture evidence. Fixture evidence is not real authenticated-user
acceptance.

## Page 3 — V1 Servers

| PDF requirement | Current implementation / evidence | Result boundary |
| --- | --- | --- |
| True zero-host state has one Servers task, first-server guidance and one primary Add server action; list/edit controls are hidden | workflow-servers.tsx; mounted UXR-1.1/1.2 browser cases | SOURCE + FIXTURE PASS |
| Loading, read failure/retry, filter-zero and incomplete reads remain distinct; API failure cannot become first-use | UXR-1.1 HTTP 401/403/500/503, timeout, partial/truncated/stale cases | SOURCE + FIXTURE PASS |
| Registered-host list defaults to six columns: Server, Agent connection, Approval, Services, Last observed, Action | UXR-1.3 six-column browser assertion | SOURCE + FIXTURE PASS |
| Selected server opens Overview / Services / Activity / Settings and carries the selected target without manual Host-ID entry | UXR-1.5/1.7 mounted browser cases | SOURCE + FIXTURE PASS |
| Metadata, Change Plan, admission and lifecycle actions move behind selected target/review; technical prose is disclosed | UXR-1.6/1.7 and UXR-5.2 | SOURCE + FIXTURE PASS |
| Return preserves display context; stale/wrong-target plans cannot Apply | UXR-1.4/1.8 plus exact admission/lifecycle validators | SOURCE + FIXTURE PASS |
| Same-condition visual coverage includes 0/1/10/50, desktop/mobile and light/dark | retained 32-case Server matrices; zero overflow, undersized primary controls, runtime errors or writes | FIXTURE VISUAL PASS; authenticated comparison OPEN |

Exact-head mounted Servers run after PDF recovery: 35/35 PASS.

## Page 4 — V2 and V3 workflows

| PDF requirement | Current implementation / evidence | Result boundary |
| --- | --- | --- |
| Add server: platform selection → install/detect → server review; copy/install/detect/approval are distinct states | UXR-2.1–2.4 enrollment and setup continuity | SOURCE + FIXTURE PASS |
| Detection delay/failure/expiry remains in the current step; no false install/connection success | bounded polling/timeout and exact admission receipt guards | SOURCE + FIXTURE PASS |
| Published services expose identity/type/owner/endpoint plus policy and transport evidence without equating Enabled with reachable | UXR-2.6/2.7 and ServiceEvidenceStatus | SOURCE + FIXTURE PASS |
| SSH command copy, safe HTTP(S) URL copy/open and TCP endpoint copy; no invented endpoint/browser shell | UXR-2.7 protocol action regressions | SOURCE + FIXTURE PASS |
| Publish service carries selected server, focuses internal target/service, and confirms public endpoint only from Core evidence | UXR-2.5/2.8/2.9 | SOURCE + FIXTURE PASS |
| Access rules preserve Remote/Internet/AI semantics; task-first fields, advanced disclosure and Review diff/impact/tests/confirmation | UXR-3.1–3.5 | SOURCE + FIXTURE PASS |
| Test & explain keeps policy authorization separate from transport/live-use evidence; Allowed + Not tested is valid | UXR-3.6/3.7/3.11 | SOURCE + FIXTURE PASS |
| Web login actor is never substituted for network source; Internet is not forced through Agent setup | UXR-3.1/3.7 | SOURCE + FIXTURE PASS |
| Home prioritizes next action, attention, usable configured services and recent changes instead of decorative metrics | UXR-4.1–4.3 | SOURCE + FIXTURE PASS |
| Activity is who/what/when/result first with one bounded selected detail and return context | UXR-4.4/4.5 | SOURCE + FIXTURE PASS |

After PDF recovery, exact-head V1/V2/V3 focused regression evidence includes
Servers browser 35/35, Setup continuity browser PASS, related source suites
78/78 and the registered Journey 439/439 from the same UI source family.

## Page 5 — common visual and acceptance rules

| PDF requirement | Current implementation / evidence | Result boundary |
| --- | --- | --- |
| Foundation visual language; title about 24px; body 14–16px; primary interaction target 44px | UXR-5.1 computed/browser gates | SOURCE + FIXTURE PASS |
| State is not color-only; normal explanation is concise; nonessential implementation evidence is disclosed while critical warnings remain visible | UXR-5.2/5.5 | SOURCE + FIXTURE PASS |
| Foundation owns common login/users/MFA/System UI; Link owns server/service/policy workflows | UXR-4.9 + Foundation Administration 20/20 | SOURCE PASS |
| Data states cover 0/1/10/50, pending, partial/error/stale where applicable | Servers/responsive fixture suites | FIXTURE PASS |
| Roles are Admin / Operator / Read Only and API authority must remain unchanged | source/role tests pass; private preview lacks independent Operator/Read Only sessions | REAL BROWSER BLOCKED |
| 1440×900, 1280×800, 375×812 and 320×568; light/dark; keyboard/detail/error/return | UXR-5 responsive/accessibility browser gate 2/2 PASS | FIXTURE PASS; authenticated comparison OPEN |
| Measure next-action discovery time, clicks and wrong-menu entries; predeclare 10-second target | UI_REDESIGN_NOVICE_USABILITY_PROTOCOL_2026-10-14.md | 0/5 REAL PARTICIPANTS; BLOCKED |
| V1 → V2 → V3 screen-unit redesign; source tests and actual UI acceptance remain separate | executable 66-WBS plan | PRESERVED |

## Deviations and disposition

1. The previously unavailable PDF source is now recovered and reviewed
   page-by-page. Missing PDF evidence is no longer a UXR-7.3 blocker.
2. No source-level deviation was found in the mapped V1/V2/V3 requirements.
3. UXR-7.3 still requires same-condition authenticated deployed-browser
   interaction evidence. Source/fixture parity is not Browser PASS.
4. UXR-7.6 still requires five independent real novice humans.
5. The PDF explicitly excludes a fake unimplemented JIT approval UI. UI-06
   remains behind the UXR-6.1 security contract and is not satisfied by current
   one-actor Temporary Access.
