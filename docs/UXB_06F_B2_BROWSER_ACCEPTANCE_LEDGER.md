# DRLink 3.0 — B2 Actual-Browser Acceptance Ledger

This ledger implements the **real-user** UXB-06F Browser / whole-menu gate from
[WEB_USER_JOURNEY_UX_ROADMAP.md](WEB_USER_JOURNEY_UX_ROADMAP.md), §5.3 and §54.
It is **not** a test result. Its source-derived route matrix is only a starting
inventory: the tester must independently discover and traverse the **actual**
browser at the **installed candidate HEAD**, without using a scripted/SSR run as
a substitute.

## 1. Entry facts observed on 2026-10-10 (preflight only)

| Requirement | Observed fact / evidence | Disposition |
| --- | --- | --- |
| Git source target | `datarelay-labs/datarelay-link`, `feat/v3-pf5b-foundation-administration`, `dfc905105536c842f85ff35c86d41b7e18520e8f` | Source candidate only |
| Actual candidate Web deployed and serving HTTPS | Read-only `ss -lnt '( sport = :18743 )'` on `dev-drlink`: **no listener** | **BLOCKED**; no browser session claimed |
| Installed v3 Server + Allocator + real Agent + test target bound to same candidate | No trustworthy installed-runtime/source matching evidence from B2 | **NOT_VERIFIED** |
| Isolated populated Core evidence and separate empty/error conditions | No actual populated v3 Core response observed from an authorized browser | **NOT_VERIFIED** |
| Genuine Admin, Operator, Read Only logged-in sessions | Previously denied browser-login execution; no authenticated role walkthrough | **PLATFORM_BLOCKED** |
| Browser installation/restart tooling | Earlier explicit platform refusals for Chromium/Playwright and preview restart | **PLATFORM_BLOCKED; do not reroute** |
| Client fixture | Nine existing dirty lines in `tests/test-frp-client.sh`, previously safety-denied | **UNTESTED / PRESERVE** |
| B1 automated evidence | Exact-source Web HTTP/Auth/UX/build checks recorded in Work Packet #182; native Web Journey/bundle remain previously blocked on this HEAD | **SUPPLEMENTAL ONLY** |
| Three-role Browser PASS, real Agent traffic and two-user E2E | No first-hand browser, traffic or two-person evidence | **NOT_VERIFIED** |

**No production/certificate/credential/role alteration is authorized by this
document.** The previous platform-denied operations must not be retried using
other processes, hosts, API tools, browser drivers or CI. An owner/authorized
operator must restore the isolated preview using a permitted process and
provide genuinely accessible B2 browser sessions; do not treat an open HTTPS
port alone as successful authentication or a working Agent.

## 2. Browser route census — source candidate, never a browser result

Derived from current `web/src/uxb-navigation.ts`,
`web/src/main.tsx`, and
`web/src/foundation-administration.ts`. **Each row below remains
NOT_VERIFIED for all three actual roles.** The "Expected" entries are
hypotheses from Web presentation code, **not** Core authorization tests.
The browser tester must inventory every actual visible or contextual action
and reconcile discrepancies rather than simply ticking these rows.

| Group | Route / visible task candidate | Admin | Operator | Read Only | Browser outcome |
| --- | --- | --- | --- | --- | --- |
| Home | `overview` / Home, setup or attention shortcuts | View + permitted actions | View + permitted actions | View only | NOT_VERIFIED |
| Connections | `hosts` / Servers & Agents | View + admin admission/lifecycle | View + permitted metadata | View only | NOT_VERIFIED |
| Connections | `services` / Published services | View + permitted edit | View + permitted edit | View only | NOT_VERIFIED |
| Connections contextual | `enrollments` / Add Agent | Visible | Not displayed | Not displayed | NOT_VERIFIED |
| Connections contextual | `setup` / Guided connection setup | Route visible; Core gates | Route visible; Core gates | Read-only effects required | NOT_VERIFIED |
| Access | `policies` / Remote, Internet, AI rules | View + permitted changes | View + permitted changes | View only | NOT_VERIFIED |
| Access | `access` / Test and explain access | Core-backed diagnosis | Core-backed diagnosis | Read-only diagnosis | NOT_VERIFIED |
| Access advanced | `objects` / Resources and groups | View + permitted editor | View + permitted editor | View only | NOT_VERIFIED |
| Access contextual | `drafts` / Advanced change draft | Visible | Visible | Not displayed | NOT_VERIFIED |
| Activity & Health | `health` / System Health | View | View | View | NOT_VERIFIED |
| Activity & Health | `hygiene` / Attention | Read-only findings | Read-only findings | Read-only findings | NOT_VERIFIED |
| Activity & Health | `audit` / Activity log and retention | Core audit; Admin retention controls | Core audit only | Core audit only | NOT_VERIFIED |
| Activity & Health | `jobs` / Management Jobs | Observe/start/cancel per Core | Observe/start/cancel per Core | View only | NOT_VERIFIED |
| Activity & Health | `revisions` / Change History | View | View | View | NOT_VERIFIED |
| Activity & Health advanced | `versions` / Agent version drift | View | View | View | NOT_VERIFIED |
| Activity & Health | `views` / Saved Views | Private display preference | Private display preference | Private display preference | NOT_VERIFIED |
| Activity & Health contextual | `doctor` / Troubleshoot | Read-only Core evidence | Read-only Core evidence | Read-only Core evidence | NOT_VERIFIED |
| Administration | `system` / Shared Administration + Link system | Canonical four groups + Core gates | Canonical four groups + Core gates | Canonical four groups, read-only | NOT_VERIFIED |
| Administration | `users` / Users & MFA | Visible + Core authorized actions | Not displayed | Not displayed | NOT_VERIFIED |
| Administration | `integrations` / API accounts & signed Webhooks | Visible + Core authorized actions | Not displayed | Not displayed | NOT_VERIFIED |
| Shell | Global Search, breadcrumb, menu grouping, contextual dialogs | Test | Test | Test | NOT_VERIFIED |

For the Foundation **System Administration** screen, enumerate the actual
four shared groups: **Access & security; Platform & network; Lifecycle &
recovery; Operations & audit.** Verify truthfulness for Link-specific capabilities:
MCP TLS certificate **status** only, Web HTTPS listener/redirect **not**
implemented by shared Link Administration; users are **supported** but
Admin-managed only; Audit/Health are view-only; unsupported Foundation
tasks are clearly unavailable. Verify both UI affordance **and Core denial**
for each unauthorized action.

## 3. Real per-route execution procedure (repeat, no scripted proxy)

1. Record **installed Web/Server/Agent source identity**, timestamp, browser
   build, actual actor role and a redacted screenshot reference. Stop and mark
   BLOCKED if installed source identity differs from the candidate.
2. Open each actual page from its normal navigation. Verify actual labels,
   paths, breadcrumbs, back links, submenus, contextual actions, role visibility
   and keyboard focus. Discover routes afresh; do not assume the source table
   is a browser truth.
3. Observe **real** populated Core data. Test a **genuinely empty** collection
   separately from `UNKNOWN`, 401, 403, 5xx, Core unreachable, pending Job,
   disconnected Agent and partial keyset pages.
4. Where legitimately authorized, complete read → create/update or Preview →
   review/test → explicitly confirm → observe Core effect → verify Audit/Jobs/
   revision evidence → undo/return. Do **not** perform destructive restore,
   retention purge, production mutation or credential rotation without the
   applicable explicit authority.
5. Repeat applicable paths at desktop, **375px**, **320px**, keyboard-only,
   refresh, and screen-reader/focus checkpoints; log truncated controls,
   misleading success, dead links, wrong destinations or incongruent status.
6. Repeat at Admin, Operator and Read Only using independent permitted
   sessions. Verify real RBAC/denied API effects, not only hidden buttons.
7. Record first-hand finding, exact candidate/installed HEAD, minimal repair
   commit and **actual browser retest** including the adjacent menu journey.
   Do not mark PASS from unit tests, mock data, screenshots or HTTP 200 alone.

## 4. Capture format — zero real executions recorded so far

For **each role × actual route × data condition × viewport** append a genuine
observation (retain evidence privately and share redacted identifiers only):

| HEAD (installed) | Role | Route / action | Core state | Viewport/input | User step | Expected / observed | Real Core or traffic evidence | Finding severity | Fix HEAD | Browser retest |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NOT_VERIFIED | NOT_RUN | NOT_RUN | NOT_VERIFIED | NOT_RUN | NOT_RUN | NOT_VERIFIED | NOT_VERIFIED | UNASSESSED | NONE | NOT_RUN |

Use `PASS`, `FAIL`, `NOT_VERIFIED`, `BLOCKED`, `NOT_SUPPORTED`, or
`NOT_IMPLEMENTED` accurately. A blocked/not-implemented step is **never PASS**.
Use the project's P0/P1/P2-USER-BLOCKING severity vocabulary. Never commit
plaintext login details, tokens, private screenshots, server private IPs,
full packet payloads or certificate/key material to GitHub.

## 5. Scenario gate — not yet executed

The same authorized human/browser tester must execute the actual sequence:
Agent enrollment/admission → publication of *one* SSH Remote Service →
narrow Remote ALLOW/DENY → real positive and negative traffic → Core diagnosis
and Audit evidence → change/revision/rollback. Repeat distinct Internet and
AI paths **only where the product officially supports them**. Cover Jobs,
retention safety (without unauthorized purge), credentials/MFA, backups,
optional-Web installation and absence of privilege escalation.

After whole-menu convergence, the **five genuine novice participants** and
**two separate real users on one frozen exact HEAD** remain independent
mandatory gates. Follow the canonical
`docs/FULL_USER_E2E_SCENARIOS.md` in full for those User E2E runs;
do not substitute this ledger, Node SSR, CI or harness output.

### Required B2 handoff before first browser action

- [ ] Authorized **isolated** candidate preview actually listening with HTTPS,
      not redirected to live v2.4/production
- [ ] Installed Server + Allocator + real Agent matched to the exact candidate HEAD
- [ ] Real populated Core state plus deliberate empty/error test cases
- [ ] Permitted authenticated Admin, Operator and Read Only sessions
- [ ] Legitimate browser/GUI capability; prior platform refusals resolved
      through the proper authority, **not** by a different execution route
- [ ] Start new actual-HEAD evidence ledger; initial count **0/N verified**

**Current release disposition: B2 NOT VERIFIED / Browser PASS NOT CLAIMED.**
