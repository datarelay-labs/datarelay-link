# DRLink 3.0 — P0 Access / Policy / Onboarding UI

Date: 2026-10-09
Status: **Implemented in isolated PF-5B development Web preview; browser/user acceptance and release pending.**
Source: `docs/WEB_UX_COMPETITIVE_AUDIT_2026-10.md` (13-product vendor-document audit).
Visual tokens and shared Administration vocabulary: existing DR Control parity and pinned Product Foundation; no independent design system.

## Screens and navigation

1. **Access Control → Access Operations**: *Who can reach what — and why?* (`AccessEvidenceExplorer`).
   - Choose Remote, Internet or AI Access. Enter source, destination and service/permission, or select a bounded Core-modeled path from `GET /api/v1/policy/graph?plane=<plane>`.
   - Press **Explain selected access**: call `POST /api/v1/policy/trace` using the existing authenticated Web API, CSRF token and same-origin cookie. Show the **exact Core final.result** (ALLOW, DENY or UNKNOWN), normalized source/destination, reason, matching rules, policy mode and enforcement; highlight mixed group results.
   - The graph is a bounded **policy/inventory** projection, *not* network topology. Missing paths, failed requests and unrecognized decisions **must remain UNKNOWN**. Policy ALLOW **does not prove** reachability. Link to existing policy and audit pages; no new mutation endpoint.
2. **Access Control → Policies**: *Define → Preview → Test → Apply* (`GuidedPolicyJourney`).
   - Guide form for plane, rule name, whitelist/blacklist, source/destination, service/permission, optional expiry and optional AI paths. Existing `POST /api/v1/guided/preview` generates Core Change Plan, revision-bound impact and blast-radius data. A free-text **review purpose is UI-local only** and explicitly **not** persisted to Core.
   - **Required policy test verification** invokes existing `POST /api/v1/policy-tests/run` with `required_only:true`. Apply remains disabled without an exact change_plan_id, non-empty change, test `ok:true`, `required_failed:0` and a non-failing preview-embedded policy regression result.
   - An impact model marked `limits.truncated` blocks Apply. Any `blast_radius.unknowns` requires explicit acknowledgment, which **does not imply the decision is ALLOW**. Changing any form input invalidates the previous plan, results and typed confirmation; inputs are disabled during requests.
   - **Only** the canonical `POST /api/v1/guided/apply` is used for commit with the exact Core `confirmation_class` (normally APPLY). The server revalidates revision/plan/permissions/CSRF and remains the final authority; the UI cannot override a server rejection. Original Configuration Draft/advanced tools remain available.
3. **Overview → Connect Agent**: *Issue → Install → Approve → Verify* (`EnrollmentOnboarding`).
   - Preserve existing manual/zero-touch issuance via `/api/v1/enrollments/manual` and `/api/v1/enrollments/zero-touch` and one-time credential/command display. The default `pre_approved` is **false**; only an Admin can explicitly enable it.
   - Load canonical Host inventory using `GET /api/v1/inventory?resource_type=managed-host&limit=100`; user chooses a Host. Admission, trust, observed connection and last heartbeat are independent, **not** a single green “healthy” state.
   - Step 3 uses existing `POST /api/v1/managed-hosts/admission/preview` then exact typed confirmation to `POST /api/v1/managed-hosts/admission/apply`. It does not silently approve or quarantine.
   - Step 4 shows current admission/trust/connection but labels policy access **NOT VERIFIED** until the operator follows **Verify effective access** to a separate Core trace. Connected, trusted, approved **never** implies a successful target session.

## Packaging, styling and tests

- New product-owned modules: `web/src/p0-access-policy.tsx`, `web/src/p0-enrollment.tsx`. They reuse existing Web `api()` (session/CSRF), React, pinned Foundation-compatible tokens and compiled local static files. No CDN or third-party network runtime dependency.
- `scripts/build-web-bundle.py` lists both source modules in its required archive members, preserving rebuildability; `tests/test-v30-web-bundle.py` asserts both.
- `web/dist/styles.css` implements responsive cards, four-step progress, bounded Core paths, decision labels (ALLOW/DENY/UNKNOWN), keyboard focus and narrow widths at 850px/560px using canonical tokens.
- Offline focused run: `cd web && npm run test:p0`. Node SSR tests render actual exported UI, validate role-based issuance visibility, strict apply guard, fail-closed unknown classification, 4 onboarding stages and distinct Host dimensions. Existing Web UX static and package/bundle suites supplement the evidence.

## Unverified gates and deployment constraints

- The authorized preview is loopback-only on **dev-drlink** `127.0.0.1:18743`; SSH forwarding from the *user's Mac* makes it visible at `http://localhost:18743/`. It serves `web/dist` from the isolated PF-5B worktree and uses an independent non-production Core DB.
- No claim of actual Chromium/320px/375px User E2E, login persona acceptance, full regression, release artifact freeze, CI PASS or final PR merge. Prior Playwright installer and preview login automation requests were explicitly platform safety denied; **do not retry via other tools/hosts/CI**. The separate denied Client test fixture also remains unqualified.
- Keep running v2.4 services, production Core, installed data, GitHub remote and release gates unchanged while isolated-source QA proceeds. The new P0 UI is a **development-preview candidate**, not a released product or security-enforcement change.

## Manual operator acceptance when browser execution becomes permitted

1. Admin/Operator/Read Only each see appropriate P0 navigation; only Admin may issue enrollment or approve Host; Read Only cannot apply policy changes.
2. Choose an actual Core-modelled ALLOW or DENY path. Explain and verify reason/matched rule, and that network reachability is labeled separately. Invalid/empty Core result displays UNKNOWN.
3. Define a valid guided change and verify **Preview → saved required tests → complete blast-radius review → typed confirmation**. Change any field and verify old plan/confirmation disappears. Reject missing tests, truncated graph, and wrong confirmation.
4. Issue a non-preapproved enrollment, confirm first Host is Pending Approval, inspect trust vs connection, preview/approve with typed confirmation and return to separate effective access query. Ensure secrets are never stored in localStorage.
5. Test at desktop, 375px and 320px with keyboard tab/Escape, focus, no horizontal page overflow, no offscreen Apply button and no invisible critical status.
