# DRLink 3.0 Web UI/UX Competitive Audit — 2026-10-09

> **Historical first pass (13 products):** Expanded on 2026-10-09 in
> `docs/WEB_USER_JOURNEY_UX_ROADMAP.md` with **19 official-vendor
> references** and a separate novice-navigation/first-use UI roadmap.
> The first three P0 technical UI components have since been committed
> to the isolated Web development preview; do not confuse that with
> completion of DRL3-7B beginner usability or User E2E.

Status: **RESEARCH / PROPOSED**. This is not a release decision, a new feature claim, or authorization to change Core policy/security. It supplements `docs/WEB_SAAS_UX_SYSTEM.md` and the DR Control visual/semantic-token reference.

## Basis, coverage, limitations

- Owner goal: decide whether the **current** Data Relay Link Web Management UX can improve before undertaking a broad redesign; **implement the favicon now**.
- Current DRLink observation: source and compiled static assets in isolated PF-5B worktree `feat/v3-pf5b-foundation-administration`; specifically `web/src/main.tsx`, `web/src/foundation-administration.ts`, `web/dist/styles.css`, `docs/WEB_SAAS_UX_SYSTEM.md` and existing Web tests. The isolated preview is reachable at `127.0.0.1:18743`, but **no actual Chromium/320px/375px logged-in acceptance was performed**: prior Playwright installation was explicitly platform-denied, and later preview login automation was separately safety-blocked.
- Competitive basis: **13 relevant enterprise ZTNA, remote access, PAM and device access products**, reviewed using **vendor public documentation** and published interface descriptions (references below), as of 2026-10-09. This is a cross-category representative audit, **not** an assertion that every commercial product or authenticated screen was inspected. Features may depend on tier, edition, cloud/on-prem, or role.
- Scope of decisions: information architecture, discoverability, progressive disclosure, traceable state, policy change interaction, safety and accessibility. Do **not** transplant product-specific network-policy semantics into Link's Remote / Internet / AI planes.

## Existing DRLink strengths — preserve, do not rebuild

| Existing source-backed capability | Evidence | Recommendation |
| --- | --- | --- |
| Five bounded sidebar groups and contextual utilities | `web/src/main.tsx` `navGroups`, `Shell` | Keep; resist new top-level menus for minor features |
| Control-reference brand tokens, collapsed sidebar, light/dark modes | `web/dist/styles.css`, `Shell`, `docs/WEB_SAAS_UX_SYSTEM.md` | Keep shared Foundation/Control tokens and brand identity |
| Command Center with connected-host counts, Needs Attention, policy coverage, audit and changes | `CommandCenter` | Improve confidence/last-observed metadata and drill-down, not decorative KPIs |
| Search/command palette, saved views, audit and context drawers | `CommandPalette`, `ResourceWorkspace`, `AccessHygienePanel` | Deep-link to selected entity/context; preserve keyboard support |
| Explicit Managed Host admission separate from connectivity/trust | `ResourceWorkspace`, `ManagedHostAdmissionPanel` | Preserve distinctions; connect admission → evidence/action |
| Core-backed draft, policy test, preview/confirmation, emergency cutoff | `PolicySafetyPanel`, `AccessOperations`, `DraftWorkspace` | Do not invent a second mutation engine; add task-first UI atop existing contracts |
| Product Foundation four-group Administration hub with actor-aware tasks | `createLinkFoundationAdministrationTasks` and pinned Foundation | Preserve canonical taxonomy; product availability differs from actor permission |
| Isolated offline Web bundle with pinned Foundation packages | `scripts/build-web-bundle.py` and its tests | All icons/help assets local; no runtime CDN |

## Competitor evidence and applicable lessons

| Product | Publicly documented UI/workflow | Relevant lesson for DRLink | Apply? |
| --- | --- | --- | --- |
| **Tailscale** | Visual policy editor alongside policy JSON; rule tabs, tests, groups, tags and device approvals | Task-first access rule form + explicit tests and preview, with advanced editor optional | P0 |
| **NetBird** | Control Center explains peer/group/network/policy relationships; separate Live and Draft with Review & Deploy | Explainable, selectable *effective* path; live/draft difference and diff before apply | P0 |
| **Twingate** | Resource detail shows group access/Access Graph; Resource Policies combine authentication, device and location constraints | Resource-centric “Who can access this and why?” with source + policy trace | P0 |
| **Teleport** | Web UI lists authorized resources, sessions and access requests; request/reviewer UX (some features Enterprise-only) | Distinguish actor privilege, pending action and audit; do not claim session recording in Link | P1 |
| **Cloudflare One** | Reusable Access policies with session duration/reasons/MFA; searchable auth events by app, actor, decision, time | Show policy outcome and decisive evidence with navigable actor/resource audit filters | P1 |
| **StrongDM** | Admin UI grants/access workflows, approvals, actor/resource audit-log filters | Make permission reason, expiry and request review discoverable in relevant contexts | P1 |
| **HashiCorp Boundary** | Target catalog/alias navigation and session list/detail with permission + lifecycle states | Host/service “Next action” and session-related context, without mixing current/live and historical states | P1 |
| **BeyondTrust PRA** | Explicit separation of administrative configuration, operator access console and appliance settings | Keep operator workflow separate from machine administration; avoid an indiscriminate admin mega-page | P1 |
| **Zscaler ZPA** | Application and user dashboards support time range, connector-related drill-down and navigation into diagnostics | Drill down from exception/card → affected service/host → evidence; avoid heavyweight analytics unless available | P1 |
| **Palo Alto Prisma Access / Strata Cloud Manager** | Interactive activity dashboards/Command Center, log-viewer drill-down (license-dependent) | Make posture panels actionable and bounded, with diagnostic context and data freshness | P1 |
| **NordLayer** | Control Panel redesign documents responsive/WCAG goals and more consistent accent/actions | Refine 320/375px layout, table overflow, accessible focus and task hierarchy | P2 |
| **Appgate SDP** | Policy UI and entitlement assignments; admin Dashboard visibility varies with explicit privileges | Reflect actor-dependent task visibility consistently; never let UI visibility substitute for API checks | P2 |
| **JumpCloud** | Conditional policies for Admin Portal with actor/group/device context | Put effective actor restrictions next to protected admin actions; avoid duplicate policy engines | P2 |

### Primary sources (vendor documentation)

1. Tailscale: https://tailscale.com/docs/features/visual-editor ; https://tailscale.com/docs/features/access-control/device-management/device-approval
2. NetBird: https://docs.netbird.io/manage/control-center ; https://netbird.io/knowledge-hub/control-center-draft-mode
3. Twingate: https://www.twingate.com/docs/resources ; https://www.twingate.com/docs/resource-policies
4. Teleport: https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/ ; https://goteleport.com/docs/admin-guides/access-controls/access-requests/role-requests/
5. Cloudflare One: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/policy-management/ ; https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/access-authentication-logs/
6. StrongDM: https://docs.strongdm.com/admin/access ; https://docs.strongdm.com/admin/audit/logs/view-adminui
7. HashiCorp Boundary: https://developer.hashicorp.com/boundary/docs/desktop ; https://developer.hashicorp.com/boundary/docs/targets/sessions/view-sessions
8. BeyondTrust: https://docs.beyondtrust.com/pra/rs/docs/privileged-remote-access-getting-started
9. Zscaler ZPA: https://help.zscaler.com/zpa/viewing-applications-dashboard ; https://help.zscaler.com/zpa/about-usage-insights
10. Palo Alto: https://docs.paloaltonetworks.com/prisma-access/administration/monitor/activity-dashboards-and-reports
11. NordLayer: https://help.nordlayer.com/docs/control-panel-2
12. Appgate: https://support.appgate.com/docs/using-policies-v6-5 ; https://support.appgate.com/support/creating-an-sdp-admin-or-api-user-and-determining-the-correct-privileges-1
13. JumpCloud: https://jumpcloud.com/support/configuring-conditional-access-policies-for-admin-portal

## Actionable DRLink UX improvements (proposal only)

### P0 — Highest product impact: explain / change / connect

**UX-1. Explain effective access from a selected entity.**
Current `AccessOperations` has a simple Source → Decision → Destination relationship strip and several separate read-only/policy-test views; `PolicySafetyPanel` exposes model paths in tables. Introduce *interactive selection* of source, destination, plane and service/permission; show **ALLOW/DENY/UNKNOWN**, governing rules, evidence fidelity and observation age; route directly to the matching policy and audit evidence. UNKNOWN must not appear as ALLOW. Reuse existing Core read/query/trace operations, not new authorization logic. If the Core cannot prove an edge, label it unavailable/unknown.

**UX-2. Task-first guided policy editor.**
Current policies, drafts, previews and saved regression tests exist but operators can encounter raw JSON blobs and multiple context switches. Present a simple guided form (who/source, target/destination, service vs permission, expiry, purpose), then **Preview diff → Validate saved tests → Review affected resources → Typed confirmation/Apply**. Advanced bundle/source view stays available. Submit through the current canonical Draft/Change Plan/Core API, respecting the exact existing supported operations and irreversible-change controls.

**UX-3. Enrollment and admission stepper.**
Link's zero-touch enrollment, Managed Host admission, trust and connectivity are separate legitimate concepts. Present a four-step contextual journey: **Issue invitation/enrollment → Install/Join → Admin approval and trust review → Verify agent connectivity and policy reachability**. Distinguish *waiting for approval*, *connected but not trusted*, *connected and approved*, *no observation*. Never silently pre-approve or auto-trust.

### P1 — Improve information quality and admin discoverability

**UX-4. Posture/attention details with freshness and traceability.**
Keep the Command Center's compact KPI layout. Every health/attention number should show the observed scope, latest timestamp and a route to affected hosts/jobs/policies. A query failure must be visibly **UNKNOWN/Unavailable**, not transformed into a reassuring zero. Separate configuration, observed connection, admission, and compiled runtime generation.

**UX-5. Contextual investigation shortcuts.**
From host/policy/service detail panels, open the Audit page with target, actor, result and time filters preserved. Add cause-oriented saved filters and a route back to the originating resource. Keep secrets redacted and role restrictions authoritative.

**UX-6. Administration hierarchy.**
The shared Foundation Hub exposes all canonical four groups, but the product-specific `SystemPanel` contains many advanced recovery/update/certificate operations. Keep the common task catalog up front, group Core-owned advanced/system operations behind labeled sections, and show *read-only*, *unsupported*, *Admin-only* and *requires confirmation* as distinct concepts. DR Control remains the visual and shared Administration terminology authority; do not introduce a separate Link design language.

### P2 — Accessibility and scalability

**UX-7. Real browser and small-viewport verification.**
Test admin/operator/read-only flows at **320px, 375px and desktop** with actual Chromium, including login/TOTP, sidebar, shared Administration cards, keyboard/focus, tables, drawers and role-denied routes. Browser gate is currently **NOT VERIFIED** due to an explicitly denied installer request. Do not reroute or claim E2E PASS from source/SSR tests.

**UX-8. Reusable density, search and status semantics.**
Keep light/dark tokens and the existing Ctrl/Cmd+K search. Standardize empty/error/loading/stale states, contextual actions and evidence labels across all five sidebar groups. Avoid showing sensitive key/cert material in tooltips/search/saved views. Fit low-density small deployments and large fleets without adding a generic NOC-style dashboard.

## What we should explicitly **not** copy

- Chart-heavy NOC/network traffic analytics, speculative “security score” or unproven 100% uptime/health.
- Functional claims for features Link does not actually implement: deep SSH session recording, entitlement broker, device posture enforcement, Web HTTPS listener/redirect management, full Visual Policy Edit/Deploy before integration exists.
- A second frontend design system, a new policy-engine authority, unconditional approval flows, runtime CDN/icons or duplicated administration menus.
- Feature parity based only on vendor marketing screenshots or a gated/paid edition without qualification.

## Recommended sequencing and acceptance

1. **Now, implemented:** a same-origin DataRelay monogram favicon shipped as `web/dist/favicon.svg`; `web/dist/index.html` points to it; the offline Web packaging manifest and bundle regression cover it. Existing isolated preview reads static files from this worktree; full release/PR CI is separate.
2. **Next design slice (UX-1 + UX-3 first):** create a prototype based on current Core read models and the pinned Foundation/Control components; verify truth/error/fidelity states with a source-scoped test; then run real User E2E when platform-permitted.
3. **Following bounded slice (UX-2):** specify mapping from guided fields to existing draft/preview/test/apply contracts and fail-closed behavior; do not start a parallel mutation mechanism.
4. **Finish (UX-4 to UX-8):** information quality, admin sections, mobile/accessibility and cross-persona verification.

Acceptance must include: (a) operator can explain one real permission path without opening raw JSON; (b) no action applies without current preview, required tests and explicit confirmation; (c) pending admission, connection and trust are distinct on-screen; (d) read-only actors cannot open admin actions; (e) all 4 Foundation groups use canonical product semantics; (f) no new network/CDN dependency; (g) genuine desktop/320/375 browser user E2E and source/CI gates before release.

**Conclusion:** improvement potential is substantial, primarily in **workflow discoverability and trustworthy evidence**, not a wholesale visual redesign. Preserve the existing DR Control-compatible design foundation and invest first in **who can access what, why, and what changes if I edit it**.
