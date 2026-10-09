# Data Relay Link 3.0 — Workflow-First Web UX Roadmap (DRL3-7B)

> **Status:** UXB-01..05 CODE IMPLEMENTED IN ISOLATED PF-5B WEB PREVIEW (2026-10-09); UXB-06 ACTUAL-USER BROWSER E2E / RELEASE PENDING
> **Position:** follows DRL3-7A SaaS/Web shell and PF-5B Administration; precedes final DRL3-8 Web qualification if approved as the target-release UX gate.
> **Product authority:** `docs/PRODUCT_MASTER.md`, `docs/WEB_MANAGEMENT.md`, `docs/MANAGEMENT_SURFACE_CONTRACT.md`
> **Shared UI authority:** `docs/WEB_SAAS_UX_SYSTEM.md` and pinned Product Foundation; Data Relay Control is the family visual/semantic reference.
> **Evidence:** 19 vendors' publicly available official documentation; actual DRLink 3.0 source/worktree; owner review feedback. This is NOT a usability study across 19 real authenticated SaaS tenants.

## 1. Explicit decision: current UI is not the target UI

Current isolated Web preview (`feat/v3-pf5b-foundation-administration`, last inspected `06f3b1fd`) has a working modern shell, Control-compatible visual tokens, PF-5B four-group Administration, navigation, Core-backed P0 access explanation, guided policy editing, a four-step Agent enrollment UI and a status dashboard. **That is the first functional UI baseline, not final user-friendly acceptance.**

The owner has confirmed that the visual quality is substantially better but the menu purposes are still unclear. The bottleneck is **information architecture, vocabulary and task completion**, not an absent colorful dashboard or a missing graph. A user should not have to learn product internal names or travel across five pages to perform their first useful job.

**Design north star:** “A first-time on-premises administrator can connect one server, permit precisely one useful connection, prove that it works, and troubleshoot a denial — without opening documentation, guessing a technical noun, or weakening any security requirement.”

The current product's three independent security planes must remain precise:

- **Remote Access:** approved external requester → approved internal Remote Service.
- **Internet Access:** managed/protected source → approved external destination.
- **AI Access:** authenticated AI Identity → explicit approved target permission.

They may share page components but **never be merged into a generic VPN/ACL policy model**. `Managed Host`, `Remote Service`, `Network Object/Group`, `Service Object/Group`, `Permission Object/Group`, `AI Identity`, `WHITELIST/BLACKLIST` and `ConfigurationBundle` remain authoritative product concepts, exposed in help/advanced details, APIs and CLI. Friendly navigation labels are aliases, not a rename of security semantics.

## 2. Research method and what the evidence can actually support

- **Coverage:** 19 relevant ZTNA, remote access, PAM, private-application access, self-hosted networking and policy-management products across open-source/on-prem and commercial/cloud categories.
- **Evidence:** the vendor's own published setup walkthrough, admin-navigation, resource detail, policy-editor, approval, diagnostics or UX-change documentation. The exact URLs are below. Research captured patterns rather than copying an inaccessible licensed UI.
- **Current Link baseline:** inspected `web/src/main.tsx`, `web/src/p0-access-policy.tsx`, `web/src/p0-enrollment.tsx`, `web/src/foundation-administration.ts`, `docs/WEB_SAAS_UX_SYSTEM.md`, `docs/WEB_P0_UX_IMPLEMENTATION.md`, `docs/PRODUCT_MASTER.md` and current roadmap.
- **Limitations:** this is a comprehensive **representative category survey**, not a proof every commercial product, edition or screen was examined. Tier-dependent and cloud-only product features must not be presented as existing Link capabilities. No logged-in DRLink 320px/375px/desktop User E2E or first-time independent participant study was performed; those are **mandatory future gates**, not completed findings. Previously platform-denied browser installation/login test cannot be reattempted via another tool/path.

### 2.1 19-product competitive evidence matrix

| Product / category | Vendor-verified UI or first-use mechanism | Action for DRLink | Official source |
| --- | --- | --- | --- |
| **Tailscale** / mesh ZTNA | Device-centric Machines → Add device; visual rule form for source, destination, port; policy-test tab | Give users named tasks and a basic rule builder with pre-save regression testing | [Device setup](https://tailscale.com/docs/features/access-control/device-management/how-to/set-up), [Visual editor](https://tailscale.com/docs/reference/visual-editor) |
| **NetBird** / self-hosted ZTNA | Control Center maps user/peer/group/policy to resource; Live/Draft review and deploy, including incomplete-change warnings | Effective-access diagram tied to actual Core facts; keep review/test before mutation; do not copy browser-only draft persistence as authority | [Control Center](https://docs.netbird.io/manage/control-center), [Draft mode](https://netbird.io/knowledge-hub/control-center-draft-mode) |
| **Twingate** / resource ZTNA | Setup order Remote Network → Resource → Connector → Client; Resource/User detail access graph; role-aware Admin UI | Setup checklist, resource-focused “who can access it?”, explicit roles | [Quick Start](https://www.twingate.com/docs/quick-start), [Resources](https://www.twingate.com/docs/resources), [Admins](https://www.twingate.com/docs/admins) |
| **Firezone** / self-hosted-resource ZTNA | Quickstart: Site → Gateway → Resource → Policy → Client; default-deny explicitly explained | “First useful connection” journey, dependency-aware steps, teach deny-by-default up front | [Quickstart](https://www.firezone.dev/kb/quickstart) |
| **Cloudflare One** / SSE | Replaced product-name navigation with task-oriented labels, guided menu migration on login, old/new term search and contextual settings; streamlined policy builders | Rename labels to real tasks; search aliases; one “What changed?” tour; no backend contract changes | [Navigation update](https://developers.cloudflare.com/changelog/post/new-cloudflare-one-navigation-and-product-experience/), [Changelog](https://developers.cloudflare.com/cloudflare-one/changelog/) |
| **Teleport** / infra access | Resource-first Web UI, active sessions and access-request/review interfaces, distinguished per client tool | Task-centered resource details and reviewer context; do not falsely advertise recording/requests where unavailable | [Web UI](https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/) |
| **StrongDM** / PAM | Admin UI separates Access, Resources, Audit and Principals; Access Requests page has Catalog/Requests tabs and purpose/duration (Enterprise) | Access-first catalog, inline purpose/expiry, clear Operator vs Administrator tasks, explicit edition caveat | [Admin guide](https://docs.strongdm.com/admin), [Requests](https://docs.strongdm.com/users/access-requests) |
| **HashiCorp Boundary** / self-managed access | Target/host catalog organization; 8-step beginner tutorial covers Admin console, first target and connections | First-use guided tour with concrete target and next action, but do not copy Boundary internal scope model | [Community quickstart](https://developer.hashicorp.com/boundary/tutorials/get-started-community) |
| **BeyondTrust PRA** / privileged remote access | Explicitly separates /appliance (host config), /login (administration), and access console (operator work); ordered setup | Separate first-use operation, account/security settings and advanced appliance recovery | [Getting started](https://docs.beyondtrust.com/pra/rs/docs/privileged-remote-access-getting-started) |
| **Microsoft Entra Private Access** / enterprise ZTNA | Quick Access guided connector→app/forwarding→client workflow, then per-app segmentation | Offer first access in minimum safe steps, then explain a more granular per-service policy | [Quick Access](https://learn.microsoft.com/en-us/entra/global-secure-access/quickstart-quick-access), [Per-app](https://learn.microsoft.com/en-us/entra/global-secure-access/quickstart-per-app-access) |
| **ZeroTier** / managed mesh | New Central quickstart focuses on creating a network, joining and approving two devices, verifying connectivity | “Set up and test” as one continuous user goal; distinct authorization vs connected state | [Quickstart](https://docs.zerotier.com/quickstart/), [New Central](https://docs.zerotier.com/new-central/) |
| **Netmaker** / self-hosted network | Annotated admin UI, sensible network form defaults, consolidated Gateway/Remote Access setup | Minimize irrelevant fields for defaults and make effective route/host selection explicit | [UI guide](https://docs.netmaker.io/docs/references/user-interface), [Gateway guide](https://docs.netmaker.io/docs/features/gateways) |
| **NordLayer** / SASE admin | Documented nav simplification, form redesign, responsive/WCAG improvements, descriptive renaming and tabs | Plain-language labels, accessible dialogs and mobile-friendly administration forms | [Control Panel changelog](https://help.nordlayer.com/docs/control-panel-2) |
| **JumpCloud** / identity/admin | Simplified renamed Admin Portal navigation and New Admin Checklist; policies grouped into Info/Assignments/Conditions/Action | Contextual checklist, human-readable field groups and migration/search for old labels | [Navigation](https://jumpcloud.com/support/updated-admin-portal-navigation), [Policy editor](https://jumpcloud.com/support/configure-a-conditional-access-policy) |
| **Palo Alto Strata Cloud Manager** / SASE | Simplified consistent left-side navigation and unified workflow for network data, onboarding and insights | Consistent group titles, task-to-evidence drill-down; avoid copying SOC-scale telemetry | [First Look](https://origin-docs.paloaltonetworks.com/strata-cloud-manager/getting-started/overview/first-look) |
| **Zscaler ZPA** / private app | Application dashboards have bounded time filters and drill-down into app usage | Show observation time and source, drill into a failing application, not an unexplained zero | [Applications dashboard](https://help.zscaler.com/zpa/viewing-applications-dashboard) |
| **Appgate SDP** / on-prem SDP | Policies UI distinguishes access entitlements, admin privileges, client controls, DNS and deny conditions | Preserve distinct DRLink policy planes and make protected effect explicit | [Using policies](https://support.appgate.com/docs/using-policies-v6-5) |
| **OpenZiti ZAC** / self-hosted SDP | Browser-based Ziti Admin Console to configure and explore controller networks | Self-contained admin interface and discoverable infrastructure concepts; no assumption of feature equivalence | [Ziti Admin Console](https://openziti.io/docs/learn/quickstarts/zac/) |
| **Netskope Private Access** / private app | Private-app setup/troubleshooting docs and a context-specific Troubleshooter listing checks and solutions; vendor warns single-port health checks can mislead | One-click “Why can't I connect?” from a resource with fidelity/partial-evidence warnings | [Private Access FAQs](https://docs.netskope.com/en/private-access-faqs), [App definition](https://docs.netskope.com/en/create-a-private-app-definition) |

### 2.2 Cross-vendor findings and limits of transfer

**Most applicable recurring designs:** (A) real task names rather than module names; (B) a fixed first-connect sequence with visible prerequisites; (C) each resource lists its owner, access and next action in context; (D) policies offer a visual form with diff/test/confirmation; (E) connectivity failure has a specific trace/fix path; (F) authorization, connection, trust, freshness and backend evidence are displayed separately. These patterns are based on the above cited vendor documentation and are **our design synthesis**, not cross-vendor user-study measurements.

**Do not copy:** vendor-specific mesh network models, always-allow quickstarts, live topological assumptions, deep session recording, non-DRLink approvals, cloud IdP/device posture obligations, dashboard-wide SOC metrics, unsafe “green” indicators, client-side authority, or pricing-tier-only features DRLink cannot implement.

## 3. Why today's DRLink menu is still hard for a first-time user

The existing Web source declares a flat `Overview` plus **five abstract section headings**: `Infrastructure`, `Access Control`, `Operations`, `Observability`, `Administration`. Its underlying pages include `Managed Hosts`, `Remote Services`, `Objects & Groups`, `Access Operations`, `Policies`, `Jobs`, `Access Hygiene`, `Version Drift`, `Revisions`, `Audit`, `Health`, `Users`, `Integrations`, and `System`. Even with the implemented P0 components, beginners have to infer where to begin and why a remote connection requires both a Host, a Remote Service and a policy.

| Evidence in current Link source | Novice user's likely question (**design inference**, not observed stopwatch data) | Required improvement |
| --- | --- | --- |
| `Infrastructure`, `Operations`, `Observability` at the same sidebar level | “Where should I start to connect a server?” | Task-first entry, fewer top-level conceptual categories and a persistent New Setup action |
| `Managed Hosts` vs `Remote Services` vs `Objects & Groups` | “Why do I have to add three things just to use SSH?” | Show their relationship, dependency order, purpose and one next action without renaming Core models |
| `Access Operations` vs `Policies` vs `Policy Simulator` | “Where do I allow something vs test if it is allowed?” | “Set access rules” versus “Test / explain a connection” with obvious actions |
| Three policy planes and `WHITELIST`/`BLACKLIST` | “What is Internet Access vs Remote Access vs AI Access?” | Use a use-case selector explaining direction and effects, not a single ambiguous “allow access” button |
| `Access Hygiene`, `Version Drift`, `Revisions` | “Does this need attention now?” | Plain-language issue cards with severity/evidence, “what happened?” and remediation route |
| Long `Administration → System` with shared Foundation and product-owned operations | “Is this safe to change? Is this the Web certificate or MCP certificate?” | Group routine, advanced and recovery tasks; show authority, availability, impact and confirmation inline |
| Role-dependent pages via `Shell.visible` | “Why is a function missing for me?” | Explicit role/capability explanation near unavailable tasks, without disclosing secrets or unauthorized controls |
| Existing Command Center and P0 journeys added to separate pages | “What is my next step after the last screen?” | Flow resumes from the user's selected Host/policy; no restart or manual copy/paste of context |

**Direct source evidence is the menu/component/route text, not a claim that quantitative confusion rates have been measured.** The owner's own browser-feedback that the menus are confusing is the current qualitative signal.

## 4. Target product UI: tasks first, technical detail when needed

### 4.1 Default sidebar proposal (five first-level destinations, including Home)

This is the **target UX architecture**, not the menu currently implemented. The DR Control shared shell styling, Foundation Administration four shared groups, current Web route IDs, Core APIs, RBAC and CLI public grammar remain canonical. A new visual label is not a new resource type.

```text
Home                                — What should I do now?
Connections                         — Connect and publish internal services
  Servers & Agents                  — (Managed Hosts; source role explained)
  Published services                — (Remote Services; existing configured endpoints)
Access                              — Who may connect, and why?
  Access rules                      — (Policies; tabs: Remote / Internet / AI)
  Test & explain access             — (Access Operations, Decision Trace)
  Resources & groups  [Advanced]    — (existing Network/Service/Permission object families)
Activity & Health                   — Is something broken or pending?
  Attention & troubleshooting       — (Health, Doctor, Access Hygiene)
  Activity log                      — (Audit)
  Jobs & change history             — (Jobs, Revisions, Version Drift via tabs)
Administration                      — Manage product and operators
  Shared System Administration      — (exact Foundation four canonical groups)
  Users & MFA                       — (Users, Admin only)
  Integrations                      — (Integrations, Admin only)
  Advanced product settings         — (existing System Core operations, role-gated)
```

On **Home**, task shortcuts are more important than these categories:

- **Add a server / Agent** (first-time/empty state); **Review waiting Agents** (admission pending).
- **Publish SSH/RDP/other service**; **Allow a source to reach a service**; **Test a connection**.
- **Why is access denied?**; **Review current alerts/jobs**; **Inspect recent changes**.
- **Internet Access setup** and **AI Access setup** are **separate** actions once applicable, never mislabeled as SSH remote access.

A user's default view remains small and calm; task shortcuts can be conditionally shown by server-observed Core capability and actor authority. Do not add a second persistent sidebar for every wizard.

### 4.2 User-facing labels / exact canonical mappings

| Proposed visible label | Existing page/workspace | Explain in one sentence / safe behavior |
| --- | --- | --- |
| Home | `overview` | “Your system status and what to do next” |
| Add a server / Agent | contextual `enrollments` | “Install a DRLink Agent on a server that needs managed connectivity” |
| Servers & Agents | `hosts` | “Servers enrolled with an Agent; connection, admission and trust are different” |
| Published services | `services` | “Specific services made available through approved managed Hosts” |
| Access rules | `policies` | “Define who may access what under Remote, Internet or AI policy” |
| Test & explain access | `access` | “Ask Core why a specific source can or cannot access a destination” |
| Resources & groups (Advanced) | `objects` | Preserve separate Network, Service and Permission Object/Group families |
| Attention / troubleshoot | `hygiene`, `doctor`, `health` | “What needs review; what was observed and when?” |
| Activity log | `audit` | “Who did what, when, to which resource and with what result” |
| Jobs & changes | `jobs`, `revisions`, `versions` | “In-progress operations, history and out-of-date Agents” |
| System settings | `system` | Shared Administration Hub + Link Core-controlled system functions |
| Users & MFA / Integrations | `users`, `integrations` | Admin-only; Web sessions/MFA never conflated with AI Identities |
| Draft / advanced editor | contextual `drafts` | Advanced ConfigurationBundle, Core preview and apply; not a separate alternate policy engine |
| Global search | existing command palette | Search both **new labels and old labels**; support exact resource and CLI public nouns |

**Navigation contract:** Existing IDs and deep-link destinations remain stable until an explicit migration and real-browser acceptance. Never rename the v2.4 CLI/API grammar to match a new UI label. Foundation canonical Admin task/group names must remain unchanged unless the shared product-standard repository updates them across Link/Control/Grant.

### 4.3 First-time login should answer five questions, in this order

```text
Welcome to Data Relay Link
Secure Connectivity for Isolated Networks

[1] Is my management Core ready?             (Core-backed readiness / UNKNOWN if not observed)
[2] Which server should I add?                 (Add Agent; choose OS, install, approve)
[3] Which service should be available?         (Publish a specific Remote Service)
[4] Who should be allowed to use it?           (Create policy, preview, test, confirm)
[5] How do I prove access and troubleshoot?    (Core Decision Trace + health/observations)
```

- Render “**Not started / Ready / Needs approval / Needs verification / Unknown**” from **real authoritative state**, not a self-reported local checklist. A grey unknown is not a success.
- Each step: one sentence of purpose, one obvious primary action, prerequisites, expected result, a *Back* route and clear recovery when failed.
- If the user chooses **Internet Access** or **AI Access**, adapt the same conceptual journey to its **own** source/destination/permission model; no implicit Remote Service prerequisite for unrelated planes.
- Do not expose encryption keys, account passwords, TOTP seeds, one-time enrollment codes or tokens in cached state, browser preferences, command/search history or URLs. UI-only preferences may persist locally; progress facts must come from Core.
- On a populated deployment, replace onboarding clutter with **Needs Attention**, important recent changes and **Continue task** contextual actions rather than forcing setup every login.
- Run the user with a documented **example SSH access** in an isolated lab, never fake a success or provision live production assets merely to fill the demo.

### 4.4 In-place help and progressive disclosure

Every prominent user task needs a short **“Why this?”** explanation and practical inline examples:

- **Managed Host / Agent:** “A server where Data Relay Link Agent is installed” (does *not* by itself publish all its ports).
- **Remote Service:** “The particular service/port you intentionally expose from an approved managed Host.”
- **Network Object / Group:** “An address or address collection referenced by a rule”; not a synonym for a Managed Host.
- **Service Object / Group:** “Protocol/port(s) referenced in access rules”; not automatically a published Remote Service.
- **Permission Object / Group:** “Named permissions for AI Access”, not network ports.
- **Admission vs Trust vs Connected vs Allowed vs Reachable:** five distinct stages; a green Connected host does **not** imply a policy ALLOW or target reachable.
- **Rule changes:** show plain-language effect, matched identities and affected services first; raw JSON, internal IDs, API details and advanced path sets only in an expandable advanced section. Core still decides.

Tooltips alone are not an accessibility or first-run solution. Use explanatory subtitles, focused examples, empty-state actions, disabled reasons, searchable glossary and context-linked Help accessible by keyboard and small screens. Users who want the current full/advanced editor can still reach it without a separate IDE.

## 5. Prioritized execution plan — DRL3-7B

`P0` below means **workflow usability priority**, not a security-release PASS claim. Existing delivered P0 technical components (access explorer, rule-change steps, Agent enrollment) are inputs, not completed outcomes for novice usability.

| ID | Priority | Exact deliverable / minimum slice | Prerequisite | Status |
| --- | --- | --- | --- | --- |
| **UXB-00** | P0 | 19-product vendor-source audit, mapping of confusing current labels, target IA/role/task journeys, test contract | Current Web source and product SSOT | **DOC COMPLETE in this roadmap**; user navigation validation PENDING |
| **UXB-01** | P0 | Rename **navigation presentation only** to “Home / Connections / Access / Activity & Health / Administration”; map existing routes, preserve old names as search aliases; role-aware accessible menu subtitles / breadcrumbs | Canonical DR Control and Foundation shared semantics; no API/CLI rename | **CODE IMPLEMENTED / BROWSER NOT VERIFIED** |
| **UXB-02** | P0 | Home onboarding/next-action cards for new vs deployed installations: Agent → admission → Remote Service → Access Rule → Verify; verify each Core-observed completion state/unknown; deep-link with context preserved | UXB-01 route map; existing P0 APIs | **CODE IMPLEMENTED / BROWSER NOT VERIFIED** |
| **UXB-03** | P0 | End-to-end **publish-and-allow** flow in one workspace, displaying dependency chain, basic form by access plane, Core preview/test and typed Apply; advanced ConfigurationBundle optional | UXB-01/02, P0 guided policy components and existing Core | **CODE IMPLEMENTED / ACTUAL CONNECTION NOT E2E VERIFIED** |
| **UXB-04** | P1 | Host/Remote Service/Policy detail “Who can connect?”, “Why denied?”, “Check connection” actions; preserve selection across Core traces, audit and troubleshooting, distinguish evidence freshness and partial observation | UXB-03 and Core read-only diagnosis/trace contracts | **CODE IMPLEMENTED / REAL-USAGE FIDELITY NOT VERIFIED** |
| **UXB-05** | P1 | Simplified daily admin page: explicit routine/advanced/destructive sections under the canonical Foundation four groups, contextual role messages, local Help/tooltips, consistent errors, statuses, empty-state guidance | UXB-01; Product Foundation and Control parity | **CODE IMPLEMENTED / BROWSER USABILITY NOT VERIFIED** |
| **UXB-06** | P0 release gate after UXB-01..05 | Actual-user usability study and manual/real-browser E2E on desktop/375px/320px, Admin/Operator/Read Only, security regression, offline build/package, owner review, exact-HEAD freeze and CI | All preceding UXB milestones; policy-permitted browser testing | **NOT VERIFIED / NOT COMPLETE** |

UXB-01/02/03 are the **next recommended implementation tranche**. Do not add dozens of new settings or unrelated features to satisfy this roadmap. First prove the core first-use journey.

### 5.1 Per-phase acceptance

**UXB-01 — Navigation and naming**

- The first-time user can find **Add Agent**, **Publish Service**, **Create Access Rule** and **Test Connection** from Home without first knowing “Infrastructure”, “Access Operations”, “Access Hygiene” or “ConfigurationBundle”.
- Five high-level destinations at most (including Home); not a second, duplicated navbar. Expert resources remain reachable through Advanced and global search, which recognizes both old and new labels.
- Breadcrumb always states where the action is performed and offers a predictable return to the original Host, rule, or diagnostic flow.
- Role-specific Admin-only actions hidden/non-interactive for non-admins, while read-only resource data is shown where authorized; server auth still denies illicit API requests.
- Keyboard navigation, focus-visible and screen-reader descriptions work. Shared Foundation Administration tasks/groups still match Control/Grant/Link semantic contracts.

**UXB-02 — Start and continue**

- On fresh isolated Core, Home shows a **specific first action** and a step sequence; on an already configured Core, Home shows relevant outstanding work rather than forcing welcome setup.
- Success is derived from **actual Core observations**; disconnected, pending admission, untrusted, unobserved and policy denied remain separate and are never fabricated as passed.
- Generated Agent enrollment secrets are one-time and never placed in URLs, client persistent storage or analytics; pre-approval remains disabled unless Admin consciously requests it.
- A user can resume after returning from Agent setup/Host detail without reentering every known non-sensitive field. No duplicate authoritative Core state.

**UXB-03 — Complete one useful connection**

- A first-time admin can follow **Managed Host → Agent registration/approval → Remote Service → WHITELIST rule → Explain/verify** in one identifiable contextual journey; completion claims require Core/reachability evidence, not merely a saved rule.
- For **Internet Access** and **AI Access**, the UI shows separate permitted source, destination, service vs permission and required prerequisites, and does not accidentally create a Remote Access policy.
- The policy form gives simple human-readable fields with optional Advanced details. Required policy tests, Core impact, unknown/truncated areas and typed confirmation remain mandatory wherever the Core contract demands them.
- No second network-policy engine, no new implicit ALLOW, no unattended admin approval and no mutation during preview or view-only interactions.

**UXB-04 — Troubleshoot and explain**

- Clicking “Why can't this connect?” from the actual Host, Remote Service or rule prepopulates **only supported verified context**, preserves plane and returns a Core-backed `ALLOW`/`DENY`/`UNKNOWN` reason with matched rule and evidence quality.
- Show where failure resides: not installed, not enrolled, pending approval, not trusted, disconnected, policy denied, service unpublished, target probe unavailable, Core stale/error.
- Correlated Activity log links preserve resource identity and chosen filters; diagnostic claims never exceed official telemetry (FRP per-connection lifecycle visibility may be unavailable).
- No speculative “green” network topology or synthetic “100% secure” score.

**UXB-05 — Routine versus dangerous settings**

- Common Foundation Administration remains visible with all four groups. Critical security/recovery actions are separated, plainly explained and clearly gated.
- Certificate UI explicitly distinguishes **MCP TLS** from **Web HTTPS listener/redirect** (which Link does not currently expose as shared settings). Backup validation differs from destructive restore; preview differs from apply.
- Routine operator tasks never ask for raw JSON when simple fields exist; experienced users can reach exact source and Core evidence under Advanced.
- Missing capabilities explicitly show “Not supported / Insufficient role / Not configured / Unknown” as different concepts.

### 5.2 UXB-06 — Real-user E2E and human usability gates

**Contract-first testing:** The assigned tester/ChatGPT must read `AGENTS.md`, `.engineering/project.yaml`, `.engineering/tests.yaml`, `docs/FULL_USER_E2E_SCENARIOS.md` and the applicable scenario document **in full** before execution. The documented real-user steps must be followed faithfully; scripted helpers and Node SSR tests are **supplementary**, not replacements for a browser persona acting as a first-time user. The canonical CLI/FULL_USER_E2E exact-HEAD release requirements remain separate.

| Test ID | First-time persona task (isolated lab; source/HEAD bound) | Required observation |
| --- | --- | --- |
| UXE-01 | New Admin logs in and locates “Add Agent” without instructions | Can discover action and distinguish on-prem install roles |
| UXE-02 | New Admin registers Linux Agent, reviews admission, approves with explicit confirmation | Shows installation/waiting/trust/connection as separate states |
| UXE-03 | Same Admin publishes only SSH service, creates narrow Remote WHITELIST and tests it | One understandable path; Core outcome confirmed and runtime evidence reported honestly |
| UXE-04 | An intentionally denied source tries to connect | A single “Why denied?” workflow shows truthful reason, policy and next action; no false ALLOW |
| UXE-05 | Admin sets Internet Access (protected source to approved external destination) | Correct distinct plane and selector semantics |
| UXE-06 | Admin defines AI Identity permission and tests AI Access | Permission Object/Group semantics, not Remote/Internet port confusion |
| UXE-07 | Operator reviews Jobs, pending changes and Activity evidence | Finds evidence without navigating obscure internals or elevating permissions |
| UXE-08 | Read Only attempts admin-only action; Admin tests local MFA/recovery path | View affordances and Core denial match; no secret disclosure |
| UXE-09 | Fresh/no-data or Core temporarily unavailable | Honest empty vs error vs UNKNOWN; visible recovery guidance |
| UXE-10 | Repeat UXE-01..09 on desktop, **375px and 320px**, keyboard and accessible focus | No critical action clipped or inaccessible; dialogs, tables, error/help and onboarding work |
| UXE-11 | Change plan proposed then modified, tests fail, preview expires and wrong confirmation entered | No stale-plan Apply, hidden bypass, silent save, unauthorized effect or erroneous success |
| UXE-12 | Offline install/reinstall, original Web/Core/CLI regression | No CDN/new infrastructure dependency; Web remains optional and not authoritative |

**Proposed measurable usability targets (not yet measured or PASS):**

- With **at least five independent first-time participants** who receive only a one-sentence product goal, **at least four of five** should locate “Add Agent” in **60 seconds** and find “Test connection” without an internal glossary. Use a moderated observation log, not only the author's own opinion.
- In a preprovisioned test lab, **at least four of five** should finish the Remote SSH first-use task without being blocked by an undocumented menu jump. Record time-to-first-verified-connection, wrong turns and assistance needed; decide an evidence-based time threshold after baseline measurement rather than inventing one.
- **Zero** role leaks, unverified success states, silent access grants, secret persistence, unsafe Apply bypasses, or mandatory task dead ends. All security/user-blocking bugs are release blockers even if automated static tests pass.
- Genuine **two-user, identical frozen HEAD** full User E2E PASS and the project's Browser/User E2E → freeze → CI/provenance/hash/public smoke → owner acceptance gates remain required. DO NOT replace them with SSR/static, reroute a platform-denied browser installation or infer browser PASS from the publicly accessible preview.
- This study protocol is a **recommended future acceptance target**; no recruited participants, stopwatch timing or owner-browser signoff has yet been observed.

## 6. Scope and implementation constraints

1. Use existing React/TypeScript, pinned Foundation packages, DR Control semantic colors/spacing and DataRelay branding. Do not create a Link-only design system or a runtime CDN dependency.
2. Apply small, separate PR/commit slices after role and route mapping. No monolithic rewrite of `main.tsx` until the new first-use path is demonstrably safer and clearer.
3. Presentation labels must not alter v2.4 CLI/AI master, `MANAGEMENT_SURFACE_CONTRACT`, canonical stored resource types or any role/source-destination rule semantics.
4. Read-only actions remain side-effect-free; create/change actions use existing authorized Core preview/regression/confirmation/commit. Raw audit/credentials remain Core-governed.
5. Do not introduce SSO, Messenger setup, external AI service, automatic trust, AI-generated access rules, packet inspection or agent session recording merely for UI completeness.
6. Preserve the owner-visible existing PF-5B preview as **a candidate**, not a release. Do not modify existing v2.4 runtime or live production config when working on the UI roadmap.
7. Historical blockers still stand: platform previously refused the Client fixture test, Playwright install and preview-login automation. These are **NOT VERIFIED**, and any denied action must not be rerouted through a different command, host or CI.
8. Owner authorized implementing the roadmap on 2026-10-09. UXB-01..05 source and offline regression work has been performed; the owner still must visually review the new menu and Home, and real permitted browser/user E2E must drive targeted usability iterations.

## 7. Status summary and next runnable action

- **Implemented technical starting point:** 3.0 Web shell, PF-5B shared Administration, Core-backed P0 access trace/graph, guided policy, four-step Agent UI, favicon and public-IP HTTPS development preview. These have static/SSR/build/package/HTTP evidence from prior work; actual user browser E2E and release still incomplete.
- **Roadmap code implemented:** **UXB-00** remains the research artifact; **UXB-01..05** are implemented in the isolated optional-Web UI (simplified navigation and old-name search, Home setup, a 4-stage connection journey, contextual diagnosis and audit, progressive Foundation/Core Administration). Offline Node SSR, static contracts, compiled assets and bundle tests support the implementation; **real-user first-use acceptance is not yet verified**.
- **Non-goals:** No duplicate feature implementation, new policy engine, new root navigation overload, synthetic status data, unrequested stable publication, or bypass of previously denied tests.
- **Acceptance condition for calling this the “target UI”:** owner can perform the end-to-end first-use/diagnose flows without asking what each menu means, independently observed user tests meet proposed success criteria, and every real-browser/security/release gate passes at the frozen candidate HEAD.

**Owner conclusion:** the earlier DRL3-7A/P0 Web was an intermediate UI. UXB-01..05 now have code implementations, but the target UI is **not signed off as final** until actual users complete first-use tasks and the full product/release gates pass.


## 8. UXB-01..05 implementation checkpoint — 2026-10-09

Owner explicitly requested implementing the roadmap in the isolated PF-5B DRLink 3.0 Web worktree. This section separates **implemented code and offline tests** from **unobserved browser/user/release outcomes**.

| Slice | Implemented product source | Observable behavior / bound |
| --- | --- | --- |
| UXB-01 | `web/src/uxb-navigation.ts`, `web/src/main.tsx` | Four grouped destinations plus Home; stable existing route IDs; Admin/Read Only visibility; plain English descriptions and breadcrumbs; Ctrl/Cmd+K finds old and new menu terms without a backend migration |
| UXB-02 | `web/src/uxb-home.tsx`, `web/src/main.tsx` | Five-step first-use checklist derived from Core overview and actual Managed Host inventory; successful configuration remains separate from verified reachability; missing Core data remains UNKNOWN |
| UXB-03 | `web/src/uxb-setup.tsx`, `web/src/uxb-remote-service.tsx`, updated `web/src/p0-access-policy.tsx` | Context-preserving four-step connection workspace, separate Remote/Internet/AI semantics, reuse of canonical Agent enrollment, remote-service preview/queued Agent job, Core guided policy preview/required tests/typed Apply, and read-only Core access trace |
| UXB-04 | `web/src/main.tsx` | Resource/Policy detail → contextual “Why can/cannot connect?” Core trace; preserving selected origin, valid policy plane, and specific rule flow where known; no synthetic mapping from Managed Host to Network Object; Audit filter carries source resource ID via ephemeral React state |
| UXB-05 | `web/src/main.tsx`, `web/dist/styles.css` | Routine vs Admin-only vs advanced Core tasks; original Foundation 4-group System Administration preserved; sensitive certificate/update/backup/restore operation panel disclosed on demand; missing health/attention numbers shown as UNKNOWN, not Healthy/zero |

**Implementation/regression command set (offline, nonbrowser):**
```sh
cd web
npm run test:journey
npm run test:p0
npm run test:administration
npm run build
cd ..
python3 tests/test-v30-web-saas-ux.py -q
python3 tests/test-v30-web-bundle.py -q
bash tests/test-v30-web-package.sh
```

These checks validate route mappings, roles, SSR-visible stage controls, effective result UNKNOWN, Core policy-apply gates, unapproved API/secret-storage avoidance, package integrity and offline build. The real Web package is served from the isolated worktree `web/dist` at the existing loopback/public-IP HTTPS preview. No Core/CLI/back-end policy authority is changed by UXB-01..05.

**UXB-06 remains PENDING:** Actual browser logged-in Admin/Operator/Read Only navigation, popup/keyboard, 320/375/mobile UI, interactions through each step including a real queued job, actual Core policy decision and deliberately denied flow, owner visual acceptance, independent first-user study, two-user exact-HEAD Full User E2E and release/CI/security gates **are NOT passed or claimed**. An earlier OpenAI platform safety denial of the Playwright installer and preview login automation cannot be circumvented with alternate commands/tools. Previously platform-denied Client fixture remains separately unqualified/uncommitted. The public-IP HTTPS preview uses a short-lived self-signed certificate, not a stable production deployment.


## 9. UXB-06 independent Web prequalification — 2026-10-09

This is **source/SSR/static/offline-package supporting evidence only**. It does
**not** mark UXB-06, UXE-01..12, actual User E2E, or DRL3-8 PASS.

Targeted issues found by a source-level walkthrough of the implemented
first-time-user journey and corrected in the isolated Web projection:

- **Read-only guide access:** Read Only users were blocked at Home's
  `Open guided setup` button even though the workflow offers read-only
  views and keeps Agent issuance, policy mutations and Core approval
  privilege-gated. The guide is now accessible to all three personas;
  backend authorization and admin-only actions are unchanged.
- **Resume after context switch:** leaving the setup wizard previously
  discarded stage, selected Host, source/destination, Service Object and
  related non-secret Remote Service form inputs. `Shell` now keeps an
  ephemeral `SetupDraft` **only in current authenticated React memory**;
  returning to Setup resumes non-secret choices. Session/logout ends this
  memory. No enrollment ticket, one-time code, password, secret, OTP,
  `change_plan_id`, preview safety result or confirmation is stored;
  those still require a new Core preview/test/typed confirmation.
- **Advanced menu overload:** `Resources & groups` and `Agent version
  drift` are now in a keyboard-focusable **Advanced tools** disclosure
  in their corresponding sidebar groups, still reachable by search.
  Existing CLI, API route IDs and RBAC are untouched.

Observed supplementary results on the local UXB-06 candidate:
`npm run test:journey` **12/12 PASS**, `npm run test:p0` **8/8 PASS**,
`npm run test:administration` **6/6 PASS**,
`python3 tests/test-v30-web-saas-ux.py` **15/15 PASS**,
`python3 tests/test-v30-management-foundation.py` **12/12 PASS**,
`python3 tests/test-v30-web-bundle.py` **6/6 PASS**,
`bash tests/test-v30-web-package.sh` **WEB_PACKAGE_LIFECYCLE=PASS**,
and `npm run build` PASS. Exact compiled UI/CSS and favicon bytes
were served HTTP 200 on the existing short-lived public-IP HTTPS preview.

**Pending mandatory UXB-06**: real first-time Admin/Operator/Read Only
human browser sessions; 320px, 375px and desktop click/keyboard/focus
verification; actual Host registration, admission, service/job completion,
Remote/Internet/AI policy enforcement and denied-source troubleshooting;
five first-time participants' task outcomes; two-user identical-head Full
User E2E; source freeze, CI/artifact/hash/provenance and owner acceptance.
Prior explicit platform safety refusals for Playwright installation,
preview-login automation and the Client test remain in force and must
not be rerouted. Partial static evidence cannot close these gates.


## 10. UXB-06 UI/API stabilization and permitted manual verification handoff — 2026-10-09

**Gate:** UXB-06/UXE-01..12 remain **NOT VERIFIED** by actual users. This entry is a reproducible *prequalification* record and does not supersede the canonical E2E contract or grant release acceptance.

### Corrected Web/Core integration and misleading-state cases

- **Remote Service → Management Job detail:** Core Apply queues with `job_id`, while subsequent canonical `GET /jobs/{id}` identifies the job using `id`. The editor now retains the original queue ID across refreshes and rejects mismatched job details, without calling QUEUED a published service or connection. Offline regression covers QUEUED → RUNNING → SUCCEEDED plus ID mismatch.
- **Configuration Draft → Change Plan:** changing editor contents, exporting a different bundle, starting another validation/diff, or receiving an obsolete async response invalidates or ignores the old preview. Apply now submits the already-previewed exact draft ID and plan, without another implicit update immediately before Apply; Core hash/revision/role/confirmation remain authoritative.
- **Other Change Plans:** Host metadata, object/group, policy settings, Host lifecycle, temporary access, saved policy regression tests and emergency cutoff changes invalidate the prior reviewed plan on input changes. The Access Diagnosis panel hides the previously observed decision when its flow inputs change, pending another actual Core query.

### Reproducible supporting checks on the isolated worktree

| Evidence | Observed result | What it does **not** prove |
| --- | --- | --- |
| `python3 tests/test-v30-web-service.py -q` | **29/29 PASS** (temporary test root, Web/Core HTTP handlers) | Real lab/browser authentication or remote connection success |
| `python3 tests/test-v30-web-auth.py -q` | **12/12 PASS** | Cross-role manual UI clicks |
| `python3 tests/test-v30-web-mfa-policy.py -q` | **5/5 PASS** | Manual authenticator/recovery usability |
| `python3 tests/test-v30-web-saas-ux.py -q` | **20/20 PASS** (includes newly added stale-plan invariants) | Browser click/focus/layout behavior |
| `npm run test:journey` | **13/13 PASS** (includes queue/detail identity regression) | Actual Agent job completion |
| `npm run test:p0`; `npm run test:administration` | **8/8; 6/6 PASS** | Human onboarding and subjective clarity |
| `python3 tests/test-v30-web-bundle.py -q` | **6/6 PASS**, deterministic bundle checks | Signed stable release |
| `bash tests/test-v30-web-package.sh` | **WEB_PACKAGE_LIFECYCLE=PASS**, optional Web install/uninstall/reinstall preserves Core policy | Full production upgrade |
| `npm run build`; `python3 scripts/build-web-bundle.py` | **PASS**, isolated package updated | Real-browser acceptance |
| HTTPS preview GET using local pinned preview certificate | **HTTP 200**, current `web/dist` served by existing isolated processes | Authenticated UX or production-grade certificate |

### Allowed UXE manual verification sequence

1. In the existing isolated preview, use explicitly authorized Admin, Operator, and Read Only sessions; check UXE-01..08 and the real Agent → service → job → rule → decision stages. Never record credentials, enrollment links, OTP, or session cookies in evidence.
2. For UXE-09/11, verify separate empty/error/UNKNOWN states; deliberately edit **each** reviewed Change Plan field and confirm the old Apply control disappears. Test wrong confirmation, failed required tests, expired plan, queued-to-detail refresh and deliberately denied Core policy decision. Never interpret a policy ALLOW or QUEUED job as target reachability.
3. For UXE-10, verify desktop, 375px and 320px, keyboard Tab/Enter/Escape, modal focus, screen-reader labels, tables, Help and logout. Record tester/role, exact candidate HEAD, scenario ID, actual action/evidence and PASS/FAIL in the approved test location.
4. UXE-12 remains gated by independently confirmed Web/Core/CLI and offline lifecycle results at the qualified exact HEAD, plus the documented two-user Full User E2E sequence and owner acceptance.

**Explicit boundary:** The platform-denied automated browser install/login and denied Client fixture remain **NOT RUN / NOT BYPASSED**. Only the isolated preview static GET is included here. Preserve the unrelated local `tests/test-frp-client.sh` modification without staging. Do not claim UXB-06 PASS until permitted real-user browser evidence and exact-HEAD qualifications exist.


## 11. UXB-06 first-time enrollment/empty-state follow-up — 2026-10-09

The existing UI was silently selecting the **first Managed Host** after loading or refreshing the inventory whenever the previously selected Host was absent. In onboarding/approval and Remote Service ownership workflows that could direct a subsequent explicit operator action to the wrong Host. Both the Setup guide and Agent admission wizard now retain the previous Host only if it still exists; otherwise the controlled selector returns to an explicit **Select an observed Managed Host** placeholder and mutation/approval buttons remain gated until the operator makes a choice. A failed or malformed Core inventory response is now **UNKNOWN**, not an observed empty set, and invalidates an old admission preview.

The Setup guide now initializes Enrollment history as **UNKNOWN** until Core returns an authoritative `items` array. A failed enrollment-inventory request is no longer disguised as `No enrollment history reported`, which is only shown after a *successful observed empty* result. These are UXE-01/02/09 source and SSR-level improvements only; real first-time enrollment and cross-role browser workflows remain **NOT VERIFIED**. Offline regressions cover the null-vs-empty rendering and the no-auto-selection source contract. The human manual checklist in §10 remains authoritative for later evidence and blocking decisions.
