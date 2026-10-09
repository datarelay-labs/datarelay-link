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

### 5.3 UXB-06F — Final whole-menu hands-on usability and functional convergence (owner request, 2026-10-09)

**Timing and intent:** After v3 feature implementation and the planned Web APIs are complete, perform a **fresh end-to-end review of every actual menu, submenu, contextual action and workflow**, not just UXE-01..12 first-connection screens. This is an **additional required pre-release UXB-06 acceptance slice**, before Browser PASS and the canonical two-user Full User E2E/release process. Early source/SSR/previews may catch defects but cannot close this final gate. The test operator is ChatGPT acting as a real first-time user **when an authorized browser capability and accounts are legitimately available**; otherwise record the precise tooling/credential gate and request the minimal owner/independent tester action. Do not route previously platform-denied browser login, browser installation or Client tests through alternate tools, runners or hosts.

**Actual populated lab is a prerequisite, not a presentation shortcut:**

1. Provision an authorized **isolated disposable v3 Server + Allocator + real Agent + reachable test target**, separate from v2.4/production. Populate state through documented product user actions: connected/approved and pending/offline Hosts; published and disabled Remote Services; Remote ALLOW and DENY rules; relevant Network/Service Objects and Groups; Internet and AI access policies and identities when implemented; revisions, Jobs, audit/diagnostic events and user roles. Preserve deliberate empty states as separate cases. Do **not** invent displayed UI data, write simulated production records or point a public preview at live production Core.
2. Verify the underlying Web routes, Core API and actual User E2E prerequisites before assessing layout. Distinguish a truly empty Core collection from an **unimplemented API, 401/403 role denial, 5xx/unreachable Core, stale result, pending async Job, and disconnected Agent**. An API that does not work is a functional defect or explicit blocker, never a usability PASS or an assumed empty dataset.
3. Use legitimate authorized **Admin, Operator and Read Only** test sessions. No passwords, TOTP keys, recovery codes, private keys, access tokens or active lab IPs in the public report. No unauthorized account reset or permission changes merely to make a test runnable.

**ChatGPT persona-led menu census and interaction sequence (100% applicable coverage):** Discover the menu inventory dynamically from the **actual candidate HEAD and browser**, including Foundation Administration subsections and hidden/contextual navigation. Traverse Home → Connections (Servers & Agents, published services, Agent enrollment/guided setup) → Access (Remote/Internet/AI rules, access test/diagnosis, resources/groups and advanced drafts) → Activity & Health (health, attention, Activity/Audit, Jobs, revisions, version drift, saved views and Doctor) → Administration (System Administration categories, Users/MFA, Integrations) plus Global Search, breadcrumb, drawers and action shortcuts. The names above are the present roadmap orientation, **not permission to assume every surface is implemented or rendered**; inventory each real menu and reconcile discrepancies.

For **each visible or intended menu/action**, manually enter as the appropriate role, identify the intended task without relying on code names, load actual Core-backed populated data, follow a complete read → create/update or preview → confirm/test → verify result → undo/return flow where applicable, and check expected permission denials. Repeat with explicit empty/error/loading/offline states, a refresh after mutation, and relevant desktop/375px/320px and keyboard/focus paths. Verify real Core effect and activity/audit/job evidence, not just HTTP 200, a saved form, a green badge or an SSR snapshot. For view-only roles, confirm both visible affordances and absence of unauthorized effects.

**Whole-product scenarios and simultaneous UI/UX review:** Execute the real onboarding → Agent trust/connection → publish SSH → narrow Remote policy → positive traffic → deliberately denied traffic → diagnose/evidence → change/revision/rollback chain; repeat distinct Internet and AI flows where supported, alongside Administration, Jobs, backup/recovery safety, role denial and Web optional/offline install. While following each scenario, evaluate **menu order, grouping, labeling, discoverability, cross-links, number of clicks, breadcrumb/back behavior, dialog focus, form defaults, status vocabulary, table readability, error/UNKNOWN/empty differentiation and responsive overflow**. Document confusing or misplaced controls as product findings, not merely cosmetic feedback.

**Fix-and-retest convergence:** Maintain one actual-HEAD ledger per menu/scenario containing `role | menu/route | Core API/data condition | user action | expected vs observed | real traffic/evidence | usability finding/severity | bug fix commit | repeated persona result`. Redact screenshots and traces. For every failure, make the minimum scoped implementation or information-architecture improvement, then **rerun the affected real-user steps and their adjacent cross-menu journey** plus relevant native tests, repeating until no release-blocking defect remains. Revisit overall menu ordering after populated-data journeys; a single initial visual approval is insufficient.

**Final pass criteria:** 100% of actual accessible menu entries and relevant Foundation subsections reconciled to functional behavior and role expectations; no dead links, misleading success/empty states, unexplained missing Core API, hidden required tasks, P0/P1 usability/accessibility defect or unqualified supported scenario. Record honest `NOT_IMPLEMENTED`, `BLOCKED`, `NOT_VERIFIED` or `NOT_SUPPORTED` instead of inventing a pass. Independent 5-person novice evidence, actual role/browser UXE-01..12 and **two genuine operators on one frozen HEAD** remain separate mandatory gates. Sequence: implementation/API completeness → populated isolated lab → entire-menu user walkthrough + scenarios → UI/UX repairs and reruns → Browser PASS → Full User E2E PASS1/PASS2 → HEAD freeze → CI/hash/provenance/public smoke → owner acceptance. No release or merge on static/scripted evidence alone.

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


## 12. UXB-06 evidence-state consistency and search race prequalification — 2026-10-09

**Scope:** Isolated v3 Web presentation only. No Core authorization, policy semantics, preview account credentials, protected Server/Agent state, system service or production/v2.4 changes.

- **UXE-09, Home recent activity/change history:** Separate `loading`, authoritative `ready` (including a genuinely empty `items: []`), and `unknown` (HTTP error, unavailable response, malformed `items`). A failed read no longer states "No retained recent activity" or "No retained configuration changes". Use the actual Audit or Change History page to retry; neither failed request grants permissions or masks a Core issue.
- **UXE-09, system health:** The Health workspace **and persistent top-bar status pill** share the same Core verdict requiring both observed `db_healthy` and `mismatch` booleans. Missing either field, any of the three runtime generation states, or management-job counters display `UNKNOWN` instead of healthy/0. The "Access planes" aggregate now counts only observed active runtime generations and explicitly says this is **not** proof of real application reachability. Shared Web Metric fallback for absent numeric data is UNKNOWN.
- **UXE-01/09, global resource search:** Editing the query or closing the dialog invalidates older asynchronous Core search responses and clears previous results; malformed Core `items` returns a visible error, never an authoritative empty set. Existing Core resource search and role-filtered local-page suggestions remain separate.

**Supporting regression:** `web/tests/uxb-first-use.test.mjs` covers settled-list vs failed/malformed-result distinctions, partial health state, true zero values and active-generation completeness. `tests/test-v30-web-saas-ux.py` checks the actual Main/Shell/GlobalSearch use of the guards. These are source/SSR/Node tests, not authenticated real-browser or novice UXE acceptance; UXB-06 and UXE-01..12 real-user PASS remain pending.

**Observed isolated pre-commit qualification evidence:** `python3 tests/test-v30-web-service.py -q` **29/29 PASS** (106.784s, fixture HTTP Web/Core service; a handled BrokenPipeError from a closed connection appeared in stderr, without test failures). Web UX contract **22/22 PASS**, Foundation management **12/12 PASS**, first-use journey **16/16 PASS**, P0 **9/9 PASS**, Administration **6/6 PASS**, deterministic Web bundle **6/6 PASS**, optional Web package lifecycle/reinstall **PASS**, production JS build **PASS** and Git whitespace check **PASS**. These checks ran on the updated **local working-tree contents** before the follow-up commit; they do not satisfy frozen-release exact-commit CI, actual browser/role acceptance or two-person full User E2E. The original Client fixture remains untested and excluded.

**Current isolated static preview (no login automation):** HTTPS public-IP `/app.js` served byte-for-byte SHA256 `f261e9936aaa4d100cfb7673815469c0c28f04fd6678e53a5afd403dac994851` with pinned temporary certificate; `/healthz` reports `status=ok`. Existing preview server PIDs `723342` and `723343` remained running; temporary self-signed certificate expires 2026-10-23. Offline Web bundle SHA256 `6bcff2f7d1001e5603a4713a3fdd9284438a7b8140c76f61629a32cbd5a85842`.


## 13. UXB-06 in-flight Host/approval Preview isolation — 2026-10-09

**UXE-02/03/11 supplemental source correction:** Even a valid Core preview may be received after an operator changes the target Host or the surrounding first-use context. The Remote Service editor now gives preview/job refresh and apply HTTP operations a monotonically increasing in-component request generation. Changing the owning Host or editing the form invalidates earlier generations, previous typed confirmation and job/plan display; late preview responses cannot re-enable Apply for a different Host. If an in-flight old-Host job request completes after owner selection changes, the editor does not present it as evidence for the new owner and directs the operator to review actual Jobs.

The Agent admission screen likewise invalidates older preview generations on Host inventory refresh, step changes and explicit Host selection. Host/step/inventory navigation is disabled while a credential issuance/approval HTTP action is pending; the Admin-only, Core-authoritative approval endpoint and typed confirmation are unchanged. A late obsolete admission preview is ignored rather than exposing a stale change plan. No new browser persistence, privilege grant or client behavior was introduced.

**Verification boundary:** The newly added source contract in `tests/test-v30-web-saas-ux.py` failed before this correction and passed after it. Node P0/first-use SSR, deterministic static build, bundle/offline package lifecycle tests are supporting evidence. Only actual authorized Admin/Operator/Read Only browser interactions can qualify UXE-02/03/11, including changes while a network request is in flight. Earlier explicit platform denials remain in force and are not bypassed.

## 14. Competitor-to-implementation usability refinement — 2026-10-09

**Scope:** P0 UXB-01/02/03/05 usability follow-up on the isolated, offline-capable Link 3.0 Web candidate, not an assertion of real-user UXB-06 acceptance. Existing 19-product official-doc research above supplies the primary design basis; public vendor documentation is representative rather than exhaustive of tenant UIs or paid editions.

| Research lesson | Concrete, source-backed Link implementation | Guardrail |
| --- | --- | --- |
| **Cloudflare One / JumpCloud:** lead with a user task rather than infrastructure vocabulary | Home now uses clickable plain-language **Connect to a server / Allow approved outbound access / Grant an AI integration permission** cards; contextual navigation opens the correct Remote/Internet/AI guide using the existing `setup` route. The fresh Core/Home case suppresses NOC-style operational KPI clutter until actual Core observations show an installed environment. | An empty Core state requires explicit observed Host, service and policy-rule totals. UNKNOWN is not classified as a new install. |
| **Twingate / Firezone / ZeroTier:** explain the order of connecting a resource, authorizing it and verifying it | First Connection Setup shows three purpose cards with use-case examples, current stage 1–4 and an accessible term glossary. Remote Host enrollment remains separate from Remote Service publication and policy changes; Internet and AI do **not** inherit Remote's Agent/service prerequisites. | Switching steps cannot apply rules. The existing Core Preview → required tests → typed confirmation → Apply path and role checks are unchanged. |
| **Tailscale visual editor / NetBird policy relationships:** choose visible entities in a guided form, retain advanced precise entry | `web/src/uxb-core-choices.tsx` reads the **existing read-only** `/api/v1/objects-groups?limit=50` endpoint. Type-specific options come from canonical Core **Network Object/Group, Service Object/Group, Permission Object/Group and AI Identity** inventory. They appear in Setup, Remote Service publishing and Guided Policy; exact field text remains editable for expert users. | Snapshot failure is UNKNOWN, an authoritative empty list is empty, a cursor makes the option list explicitly partial. Names only, no credentials or implicit object provisioning. AI Identities still require authorized Core provisioning. The selector is disabled while its Core Preview/Apply request is busy, preserving the existing plan-generation guard. |
| **StrongDM / Teleport / Boundary:** separate what is configured, permitted and truly reachable | Inline stage evidence keeps Agent trust/admission, Remote Service queued status, Core policy decision and target/client reachability distinct. Contextual guidance points to Core evidence and never claims connection success from selecting an option. | No synthetic policies, shared remote sessions, hidden ALLOW or alternate frontend policy authority. |
| **NordLayer / Appgate:** responsive and accessible low-density workflow | Dedicated responsive mode cards and Core choice fields using existing DR Control/Foundation tokens, text labels, `aria-pressed`, native keyboard-select controls and visible focus ring. On narrow layouts cards and selectors stack. | Source/CSS checks are supplemental only; actual 320/375/desktop browser focus, screen-reader and five novice participants remain UXB-06 gates. |

**Source implementation:** `web/src/uxb-home.tsx`, `web/src/uxb-setup.tsx`, `web/src/uxb-core-choices.tsx`, `web/src/p0-access-policy.tsx`, `web/src/uxb-remote-service.tsx`, `web/src/main.tsx`, `web/dist/styles.css`. Offline packaging enumerates the new shared code and no runtime CDN/npm-network dependency was added.

**Supporting verification contract:** Native Node/SSR unit suites (`npm run test:journey`, `npm run test:p0`, `npm run test:administration`), Python Web UX source contract, deterministic offline bundle builder/test and isolated Web package install/remove/reinstall. These tests establish supported markup, API type mapping, role segregation, zero-vs-unknown, source contracts and offline continuity, **not** human comprehension or live application reachability. UXB-06 real logged-in Admin/Operator/Read Only 320/375/desktop keyboard and novice trials, live independent Agent lab, same-HEAD two-user Full User E2E, candidate release gates and owner visual acceptance remain **NOT VERIFIED**. Earlier platform-denied Playwright/Chromium installation, automated preview login and exact Client fixture tests were not rerouted.

**Observed isolated source qualification (before commit, not actual browser):** `npm run test:journey` **23/23 PASS** including new Core choice/navigator tests, `npm run test:p0` **9/9 PASS**, `npm run test:administration` **6/6 PASS**, `python3 tests/test-v30-web-saas-ux.py -q` **24/24 PASS**, Foundation management contract **12/12 PASS**, `python3 tests/test-v30-web-bundle.py -q` **6/6 PASS**, `bash tests/test-v30-web-package.sh` **WEB_PACKAGE_LIFECYCLE=PASS**, production `npm run build` PASS and `git diff --check` PASS. The existing 29-case Web HTTP suite **29/29 PASS** (108.494s) and Web Auth **12/12 PASS** were observed during the same frontend-only workstream before final frontend selector busy guards; no Core Web API or Web Auth implementation changed. The isolated public HTTPS `/app.js` and `/styles.css` served HTTP 200 and matched current worktree SHA256 (`c828d97f8e860a5b3238181c6f0c1ef67efae0b11f42ca5b4e43b0db84f31e58`, `e2a86c8451608b0443148beb5f7fd133037e29e4e027b8540ab05363c5b130f4`); `/healthz` reported `ok`. Reproducible offline bundle SHA256 `03821d937666562dd2f1d4cbacca89e5a4a117f031f84bb4cec84848d6cc5c39`. Original isolated preview processes remained running, unmodified. Real-browser/Agent E2E, owner acceptance, PR source convergence and release are **NOT VERIFIED**.


## 15. First-use Core name discovery beyond the first page — 2026-10-09

**Operator pain resolved:** The UXB-07 initial resource picker shows at most 50 Core entries per resource type. Previously, another valid object/group or AI Identity could only be entered if a first-time user already knew its exact name. Filtering within the Objects & Groups page also searched only the loaded first page, potentially misreporting no matches.

**Implemented in the existing offline Web code:**

- Each Setup, Guided Policy and Remote Service Core choice can now search **existing exact Core names** using the **existing read-only** `GET /api/v1/inventory?resource_type=<canonical-kind>&q=<encoded-substring>&limit=50` (note the canonical HTTP parameter is `q`, not `query`). The operator types at least two characters and explicitly presses **Find matching names**. The UI queries only the relevant safe resource types for that access direction: Remote/Internet source/destination = Network Object/Group; selector = Service Object/Group; AI source = AI Identity; selector = Permission Object/Group. No new Core endpoint, object creation, credential read/write or policy mutation was added.
- Each requested resource kind must return a valid `items` array before the search is considered complete. Errors/malformed responses produce **Core name search unavailable**; successful empty matches, partial results (`next_cursor`) and the original bounded first page are visibly distinct. Users can refine the search or return to the first-page selection, and can still enter an expert exact name through the existing advanced field.
- Async search uses a per-component request generation. Edits, plane/resource-kind changes, catalog refresh or component unmount invalidate older results so delayed responses cannot re-select an obsolete identity/object. Search selection calls the existing form setter and invalidates old Change Plans through the existing editor guards. Search/selection are nonmutating; Core Preview → required tests → typed Apply remain authoritative.
- **Contextual navigation:** Setup's AI Identity action now lands in the existing Objects & Groups **AI Identity tab**; Internet source links to **Network**, AI permission configuration to **Permission**. Only ephemeral route context is carried; no URL or local-storage secrets.
- **Snapshot honesty:** Objects & Groups now labels its count **visible Core resources**, warns when a family has additional pages, and explicitly distinguishes partial/incomplete snapshots from a genuine empty result. A quick action returns to guided setup for an actual Core name search, rather than falsely declaring an absent resource.

**Code and tests:** `web/src/uxb-core-choices.tsx`, `web/src/uxb-setup.tsx`, `web/src/p0-access-policy.tsx`, `web/src/uxb-remote-service.tsx`, `web/src/main.tsx`, `web/dist/styles.css`, `web/tests/uxb-core-choices.test.mjs`, `tests/test-v30-web-saas-ux.py`, `tests/test-v30-web-service.py`, `tests/test-v30-web-package.sh`. Read-only **isolated HTTP** regression seeds a real temporary Core network and service object, checks unauthorized GET is 401, verifies Core snapshot and filtered GET, confirms a genuine no-match returns `items:[]`, and asserts the Core revision remains unchanged. This fixture does not log in to or mutate the public development preview.

**Observed supporting test results before exact-HEAD commit:** Web HTTP suite **30/30 PASS** (including the new source-backed Core search test; the earlier 29-test baseline becomes 30); Node/SSR first-use journey **26/26 PASS**, UX source **24/24 PASS**, P0 **9/9 PASS**, Administration **6/6 PASS**, Foundation management **12/12 PASS**, deterministic Web bundle **6/6 PASS**, Web production JS build **PASS**. **No real browser / 320px/375px keyboard interaction, first-time novice study, live Agent or two-person same-HEAD E2E PASS** was obtained by these tests. The previously platform-denied browser installer, automated preview-account login and exact Client fixture were not rerouted.


## 16. UXE-02/03 — explicit Host retarget and novice next action — 2026-10-09

**Defect fixed:** A first-time Admin could select Agent A, prepare service and access form values, return to the Agent selector, choose Agent B and then see previous Agent A's Remote Service draft owner/name/selector or corresponding flow values retained in the next stage. The backend Core still validates a fresh Preview, but the UI made it too easy to send a reviewed operation to an unintended Host.

- The first-connection Setup now uses a single explicit `chooseRemoteHost` action for both step 1 and step 2. A genuinely different Host selection calls pure `retargetRemoteHost`, clearing the previous Remote Service name, Service Object, source, destination and rule selector and setting the new service draft owner. The embedded Remote Service editor is keyed by the selected Host, so its old local preview, confirmation, queued job view and pending input cannot be carried to a different owning Agent. This does not change the independently offered advanced exact-owner editor or Core permissions.
- While a Remote Service Core Preview, Apply or job refresh is in flight, its editor reports a busy state to the first-use parent. That state disables Host selection, access-direction cards, stage navigation and inventory refresh inside this wizard so an in-flight old-Host mutation cannot disappear from view because the operator changed the parent context. Controls are re-enabled after the result or error is handled; switching pages or closing the browser is not proof that a queued Core job was cancelled. Independent Core Jobs/audit remain the source for what actually happened.
- Host refresh compares **the current selected Host reference** against authoritative Core inventory, rather than a stale React closure captured at initial render. If a previously selected Agent disappears, the UI invalidates that Host's dependent choices rather than silently switching to the first available Agent. When Remote Host inventory becomes unavailable, this context is fail-closed and readiness is explicitly UNKNOWN; no connection success is fabricated.
- Each Remote, Internet and AI stage displays a short context-sensitive **What to do next** message based only on the observed Host admission/trust/connection state and the explicitly selected resource names. It distinguishes missing selection, awaiting Admin approval, missing trust, disconnected Agent, incomplete objects, unverified Agent service job and the final `NOT VERIFIED` connection check. **Next stage remains navigable for exploration**; advancing the wizard does not assert that the earlier step succeeded or apply a Core change.
- Canonical Core Preview, saved required policy tests, typed Apply confirmation, server authorization and all Remote/Internet/AI selector semantics remain authoritative. No production/v2.4, Client fixture, certificate, account or privilege change is involved.

**Source/test evidence:** `web/src/uxb-setup.tsx`, `web/dist/styles.css`, `web/tests/uxb-connection.test.mjs`, `tests/test-v30-web-saas-ux.py`. Two Node/SSR tests for explicit Host retarget and per-plane next-step guidance were **RED (missing helpers)** before implementation, then Web journey **28/28 PASS**, Web P0 SSR **9/9 PASS**, Web UX source **24/24 PASS** after fixes. These are not actual rendered browser/user E2E nor proof of target network reachability; owner and independent first-time human-browser acceptance remain UXB-06 release gates.

**Latest permitted source qualification on this candidate:** first-use journey Node/SSR **28/28 PASS**, P0 **9/9 PASS**, Foundation Administration UI **6/6 PASS**, Web UX source contracts **25/25 PASS** (including explicit Remote Service busy-context controls), Foundation management **12/12 PASS**, isolated native Web HTTP **30/30 PASS** (116.442s, transient BrokenPipeError recorded from closed probe connection while assertions all passed), deterministic offline bundle **6/6 PASS**, `WEB_PACKAGE_LIFECYCLE=PASS` and production JS build PASS. These tests were executed on the modified working-tree content before the follow-up commit, and do **not** replace actual-user/role browser qualification at a frozen HEAD. The isolated HTTPS preview static JS SHA256 after build was `9b00712e0b79eaefa3196e40895a68cf8103cada3b47293540814fbcd7d0a0e2`, CSS `368f2b05911c1a297db2ad8e08cb210deecd7d3257a749cd65076993c357ec51`, offline Web bundle `7aa25f7d20d0be62e93ca1ecc40b486d861b60bda033fc28878490a4fee2a42b`; the original isolated preview processes were not restarted, credential/auth changes were not performed, and the original denied Client fixture remained untouched.


## 17. UXE-02 — Preserve display-once Agent invitation during Core request (2026-10-09)

**Problem:** Issuing a zero-touch/manual Agent enrollment ticket is a Core POST that may return display-once material. While the in-flight request was pending, the nested Agent onboarding screen disabled its own navigation but the parent first-connection wizard still let the operator choose another access type or change stage. The child would unmount, making an issued credential inaccessible in that browser session and making the result of pending admission review hard to locate.

**Frontend-only resolution:** `web/src/p0-enrollment.tsx` reports its Core issuance/approval `busy` state to its parent via an optional `onBusyChange` callback, cleaned up when the child unmounts. Setup combines this with Remote Service Preview/Apply/job busy state as `wizardBusy`, temporarily disabling changes to the current Agent, access plane, stages, and inventory refresh. An accessible inline status message explains that the user must review the current Core operation result before leaving. Existing child-level guards and Core authorization, expiration, revocation, role checks, typed confirmation and one-time secret behavior remain authoritative; this does not persist or recreate enrollment secrets.

**Regression evidence:** A new source contract test first failed with missing callback guards, then Python UX contract **26/26 PASS**, offline journey Node **28/28 PASS**, P0 **9/9 PASS**, Foundation Administration UI **6/6 PASS**, and production JS build **PASS**. This is offline source/SSR qualification, *not* actual-browser focus/navigation testing, successful enrollment or a guarantee that a user won't intentionally leave the page after completion. Previously denied public-preview automated login, Chromium installer and Client fixture were not rerouted.

**Additional isolated evidence before follow-up commit:** Web offline deterministic bundle **6/6 PASS**; optional Web installation/uninstallation/reinstallation **WEB_PACKAGE_LIFECYCLE=PASS**, preserving Core and CLI behavior without Web; Foundation management **12/12 PASS**; SHA256 parity of current compiled `/app.js` (`3edcd34e11eead77823c4725d5cf1c875ca89a18c8ac4f62a009ff19d64501c0`) and `/styles.css` (`dedbb85153c2dc07b37dfe5bed7b8731a418ad87acf749b92e2f1792c992e397`) with the existing pinned-certificate isolated HTTPS preview; offline Web archive SHA256 `d2b0e12ecaf9c7d771545e3384a39c7bb5bd38cb0df65f5444e1dbc7a0732f4e`. Preview server PID 723342/723343 preserved. No production, released Client, credential or TLS configuration was changed.


## 18. UXB-06 beginner-first display-once Agent install instructions (2026-10-09)

**Observed usability gap:** After an Admin issues an Agent invitation, the canonical install command and optional manual enrollment code appeared as raw multi-line text with no explicit copy affordance. First-time operators had to select sensitive text manually, increasing copy/paste errors and confusion about the next installation step.

**Isolated Web-only update:** In `web/src/p0-enrollment.tsx`, step 2 now offers explicit native **Copy install command** and (only when Core returned one) **Copy enrollment code** buttons. Copy runs **only upon a user click** using `navigator.clipboard.writeText`; the product does not automatically place anything in the clipboard, URL, analytics, localStorage or sessionStorage. The status message includes only the item label (never the secret) and warns that clipboard contents may be visible to other applications. If the secure Clipboard API is unavailable or rejects the request, the UI truthfully instructs the user to select the already displayed text manually. Display-once expiry, token issuance, Admin role gate, installation guidance, admission defaults and Core trust/security decisions remain unchanged; the UI neither regenerates nor persists secrets.

**Supporting source tests:** An added Web UX contract test initially **RED** and then `python3 tests/test-v30-web-saas-ux.py -q` **27/27 PASS**, Node P0 component suite **9/9 PASS** and compiled offline production Web JS build PASS. No actual authenticated browser clipboard acceptance or real Agent enrollment occurred; those remain UXB-06 and Full User E2E gates.

**Further supporting evidence for this isolated Web-only slice:** journey SSR **28/28 PASS**, Administration SSR **6/6 PASS**, Foundation management **12/12 PASS**, deterministic Web bundle **6/6 PASS**, and optional Web offline package installation/uninstallation/reinstallation **WEB_PACKAGE_LIFECYCLE=PASS**. Current compiled JS SHA256 `31de0d478651a167aa33e5557a7e9003f8c818a855b788a4a54f7f2e71ce1f66`, CSS `dedbb85153c2dc07b37dfe5bed7b8731a418ad87acf749b92e2f1792c992e397` matched the unchanged isolated HTTPS preview with pinned temporary certificate; offline Web archive SHA256 `b1455c10cb7b5e3b47392bf3b712eadf53ca5d5d2cd9e3f1d3fe96ca59660a47`. No real user/browser clipboard interaction was claimed.


## 19. UXB-03/UXE-02/03 — Prevent split-owner Remote Service preview in first-connection guide (2026-10-09)

**Concrete usability/correctness defect (reproduced with RED offline render tests):** Setup’s Step 2 presented a selected Managed Host (Agent A) as the Remote Service owner, but the nested Remote Service editor separately accepted an editable “Owning Agent / Managed Host” value. A returning session could also retain `serviceDraft.owner` from Agent B, and the Remote Service editor prioritized `initialSelection.owner` over `ownerHint`. The first-time user could believe they were previewing a service for the selected Host while sending a Preview for another manually entered/stale Host. Likewise the editor appeared when the selected Agent was **not yet observed** in the Core inventory, allowing a typed owner despite the guide asking the user to choose a real Agent.

**Frontend-only correction:**
- `RemoteServiceEditor` adds explicit opt-in `lockOwner` for the **guided** Setup, not the advanced Published Services editor. A pure `remoteServiceOwner(owner,ownerHint,lockOwner)` determines the single effective owner for **displayed field, readiness, parent selection callback and Core Preview payload**. When guided, it is the selected Host ID from `ownerHint`; the input is read-only, accompanied by a “change owner in the guide” explanation. The advanced standalone editor leaves manual owner input behavior unchanged.
- Setup Step 2 mounts this editor only if `selected` is a truly observed Managed Host from the canonical inventory. Otherwise it shows a visible **Selected Agent must be observed before publishing** message, never enables a Preview based solely on a typed/stale Host, and provides a **Go to Agent selection** return action. A selected Host additionally displays its observed friendly name, ID, and admission/trust/connection state, while connection success remains `NOT VERIFIED`.
- The previous typed Core Preview/confirmation, queued Agent job, RBAC, service type, policy enforcement, Host approval and the actual Core ownership rules are unchanged. This is a **presentation binding**, not a new authorization engine.

**Reproducible regression evidence:** Two new `web/tests/uxb-connection.test.mjs` offline Node/SSR tests failed before implementation, then the first-use Node/SSR suite **30/30 PASS**. Python Web UX source contract **27/27 PASS**, native Web production JS bundle build **PASS**, Foundation management **12/12 PASS**, deterministic offline Web bundle verification **6/6 PASS**. The isolated native HTTP regression `V30WebServiceTests.test_remote_service_preview_apply_queues_agent_job_without_false_success` was separately **1/1 PASS**, covering the existing actual Core Preview/Apply/job lifecycle without altering backend behavior. These are supporting source and isolated fixture checks; real logged-in Admin/Operator/Read Only browser and actual Agent network E2E remain **NOT VERIFIED**. Previously platform-denied browser installer, automated preview login and Client fixture are neither executed nor rerouted.


## 20. UXB-03/UXE-09 — Latest Core inventory refresh wins; stale Host/plane ignored (2026-10-09)

**Found during the guided-owner correction:** First Connection Setup can request several Core inventories asynchronously on mount, manual Refresh, and child enrollment callbacks. Without a request-generation guard, an older response could finish after a newer refresh and overwrite later Host, Remote Service, enrollment or Object/Group observations, including invalidating a recently selected Host against a stale list. A response captured on the initial Remote plane could also act on the wrong active plane after the operator switched to Internet/AI Access. Clicking an already-active plane card redundantly reset the form.

**Fix scoped to `web/src/uxb-setup.tsx`:** `refreshGeneration` monotonically identifies the newest Core refresh; only its settled result may update inventory, status or loading state. Effect cleanup invalidates outstanding responses on unmount. A separate `planeRef` holds the current selected access plane, including across pending requests, and explicit plane switching clears the now irrelevant Remote Host selection/associated service draft instead of retaining it as a hidden choice. Clicking the same access plane preserves the user's non-secret form choices. As before, missing Core inventory is **UNKNOWN**, not an observed empty set, and no backend policy or authorization is changed.

**Supporting qualification:** A new Python UI/source contract was RED before the guard and later Web UX contracts **28/28 PASS**, Node/SSR first-use journey **30/30 PASS** and offline production JS build PASS. These are source/SSR observations, *not* a simulated real logged-in browser, nor a qualified two-user Agent/Server Full User E2E. Prior platform-denied browser login/installer and exact Client fixture remain outside permitted scope.

**Supporting local qualification at this source candidate (before commit):** first-use Node/SSR `npm run test:journey` **30/30 PASS** (two new Host-bound tests first RED then GREEN); Node P0 **9/9**, Foundation Administration UI **6/6**, Python UX source **28/28** (latest-wins snapshot test first RED then GREEN), Foundation management **12/12**, Web bundle **6/6**, optional install/uninstall/reinstall `WEB_PACKAGE_LIFECYCLE=PASS`, production JS build and Git whitespace validation PASS. The focused actual isolated Web HTTP `V30WebServiceTests.test_remote_service_preview_apply_queues_agent_job_without_false_success` was **1/1 PASS**; the Core/agent API implementation itself is unchanged. These are not authenticated public-preview browser acceptance or a live Agent E2E result. HTTPS public-preview JS `7b17e493fc26c51a4094d821324f746dde824cfdd6dfd346bc7e722e7be09007` and CSS `874789fbf58524f64155f3650903d98286d410e97e4d749178dea5adf792a961` matched the compiled local bytes using the previously pinned temporary certificate, existing Python preview processes 723342/723343 remained running, and the optional offline bundle SHA256 was `22924e3df6dcfd88358138ddeb73fb84e70c645f37efd14efd7298845e4cb795`. The original unqualified Client fixture `tests/test-frp-client.sh` was neither tested nor staged; earlier explicit platform denials for the browser installer or public-preview login automation remain respected.


## 21. UXE-03 — Reconcile returned-to wizard drafts with the explicitly selected Agent (2026-10-09)

**Additional user-resume correctness:** The Shell can retain non-secret first-use form choices during an authenticated React session. A saved Remote draft produced before the guided Host ownership lock may legitimately contain `selectedHost=Agent A` but `service.owner=Agent B`; forcing the Preview owner to A without resetting the saved Remote Service name and Source/Destination/Service Object choices could misleadingly suggest these were prepared for A.

**Implemented:** The pure, side-effect-free `reconcileHostBoundDraft` normalizes only mismatched Remote Access drafts before state initialization in `FirstConnectionSetup`. A conflicting stored owner triggers `retargetRemoteHost` to clear the old service name, service object, source, destination and rule selector while preserving the explicitly selected Agent and the requested setup stage. Consistent Remote drafts and **all Internet/AI drafts remain unchanged**. This stores no password, enrollment token, cookie, OTP, signed API permission or Core mutation. The authoritative Remote Service Preview body remains locked to the observed Host and Core revalidates all policy/job permissions.

**Regression:** An offline Node test for old Agent A/B draft mismatch was RED before the normalizer and now `npm run test:journey` **31/31 PASS**, Python Web UX source contracts **28/28 PASS** and Web JS production build PASS; the test also verifies a rendered resumed Step 3 does not preload Host B's obsolete source/destination/service selectors and AI drafts are preserved. Actual authenticated browser resume and independent human comprehension remain mandatory UXB-06 gates and were not substituted by SSR.

**Exact local candidate source verification (before this follow-up commit):** first-use Node/SSR **31/31 PASS**, P0 **9/9 PASS**, Foundation Administration UI **6/6 PASS**, Web UX contracts **28/28 PASS**, Foundation management from the preceding unchanged shared-source commit **12/12 PASS**, offline Web bundle verification **6/6 PASS**, native isolated Remote Service Preview/Apply/job Core HTTP test **1/1 PASS**, `npm run build` and optional Web install/remove/reinstall **WEB_PACKAGE_LIFECYCLE=PASS**. Original separately blocked Client fixture not run. Current compiled `app.js` SHA256 `066efa5b3acd0a2d4bbe1a0a3b3da8f3d89081b3e322f43be10ae6fb90481691` and `styles.css` `874789fbf58524f64155f3650903d98286d410e97e4d749178dea5adf792a961` are byte-identical to existing pinned-cert isolated HTTPS dev preview; offline Web bundle SHA256 `70230a6031c102b8ae09173e57b6352d0a230ba7f61c83e6e73a0af3e9e60713`. These tests demonstrate source/SSR/isolated fixture consistency **not** authenticated real-browser E2E, first-time participant usability, real Agent network reachability or final release acceptance.


## 22. UXE-03/09/11 — Keep Core policy work in view and preserve AI task context (2026-10-09)

**Observed source-level operator defects:**
1. The Setup wizard already temporarily disabled Stage/Agent/Plane navigation while Agent enrollment and Remote Service Preview/Apply were in flight, but the embedded **Guided Policy** editor did not notify its parent. Users could leave Stage 3 while Core `guided/preview`, independent `policy-tests/run` or `guided/apply` requests were pending and lose the immediate response or queue/access outcome context.
2. The **Objects & Groups** first-page-only inventory warning offered **Find another Core name**. From an AI Identity or Permission tab, the button always opened default Remote setup, even though those resource families exclusively belong to the AI Access workflow. Choosing Remote by default causes first-time users to search Service Objects instead of Permission Objects.

**Implemented on the isolated DRL3-7B Web candidate:**
- Guided Policy exposes an optional `onBusyChange` output that reflects its Core Preview / independent required-test / Apply request state to the parent Setup. A pure `isWizardBusy(serviceBusy,enrollmentBusy,policyBusy)` now covers all three source-owned request families, preventing inadvertent intra-wizard Stage, Agent, access-plane or inventory refresh changes before the result is displayed. The policy editor also disables its own links to Access explanation and Objects & Groups during those requests; it never converts pending Core work into a completed connection. Standalone policy usage keeps the callback optional; authorization, immutable Change Plans, typed confirmation and Core-required regression tests remain unchanged.
- A narrow `setupContextForObjectFamily(family)` helper in `web/src/uxb-navigation.ts` returns an AI setup context **only for the `ai` and `permission` families**. Network and Service resources are shared by Remote and Internet, so their setup context remains unassigned rather than guessing which security plane the user intended. The existing Objects Workspace first-page warning passes this ephemeral route context through the normal `onNavigate` function; the original canonical `setup` route is preserved. No URL/browser storage, credential, identity or Core policy changes.

**Permitted regression evidence:** Node/SSR source-backed tests and CSS static build are supplemental only. The new policy-busy and task-context tests each reproduced a RED failure before implementation, then Node `npm run test:journey` **33/33 PASS** and Python Web UX source contracts **30/30 PASS**; local production Web compilation PASS, P0 UI **9/9**, Foundation Administration UI **6/6**, and isolated native Web HTTP **30/30 PASS** (119.669s, same unchanged backend). Browser navigation while Core requests are in flight, responsive 320/375px and real Agent/Operator/Read Only UXE tests still require qualified real-user browser evidence. Prior explicit platform refusals for browser installation, automated preview login and `tests/test-frp-client.sh` were not rerouted or bypassed.

**Observed pre-commit source candidate qualification:** `npm run test:journey` **33/33 PASS**, P0 **9/9**, Foundation Administration SSR **6/6**, Python UX source **30/30**, Foundation management **12/12**, deterministic Web bundle **6/6**, Web build PASS and optional Web install/uninstall/reinstall `WEB_PACKAGE_LIFECYCLE=PASS`. Isolated native Web HTTP suite **30/30 PASS** (119.669s) during this same frontend-only change set, with no Core Web API or policy backend code modified. Existing isolated, owner-authorized HTTPS development preview (address deliberately omitted from public repository documentation) served compiled `app.js` SHA256 `8637351cd391b1b7a17295a6933259bcc106c976fafbfa1bfaae7574b3ad050c` and `styles.css` SHA256 `874789fbf58524f64155f3650903d98286d410e97e4d749178dea5adf792a961` byte-identical to the worktree; `/healthz` reported `ok`; previously-running preview PIDs were preserved. Offline Web archive SHA256 `dbd485ae3193ff043df1dcb12df8c2b28e0d0e69531b6ea5522c0d8fcca10c9e`. This evidence is not logged-in real-browser persona acceptance, independent novice measurement, a live Agent connection or a 2-user frozen-HEAD Full User E2E PASS.


## 23. UXE-04/09/11 — Core evidence stays bound to the queried flow and cutoff plan (2026-10-09)

**Confirmed UI risk:** The Effective Access and Advanced Access Workspace screens relied on updating or clearing React result state in effects or on new submissions. A previously loaded **ALLOW / DENY** or diagnostic result could temporarily appear beside edited Source, Destination, Service/Permission or a different AI request path. Delayed Core diagnosis and Live Access responses were not all generation-guarded. On the emergency cutoff panel, a prior plane's active cutoff count could be displayed under another plane, and a delayed **Preview** response could reappear after changing its plane/scope/action. Core still revalidates mutations; the Web representation must not suggest that old evidence belongs to a new request.

**Source correction and explicit guardrails:**
- `web/src/p0-access-policy.tsx` adds pure `coreFlowKey` and `visibleCoreEvidence`: an input-normalized, plane-specific key includes Source, Destination, Service/Permission, and additionally the request path for AI Access. **A trace result is displayed only when its captured request key matches the currently displayed flow**, even during the render before effect cleanup. The modeled graph is similarly keyed to the Core access plane, and old asynchronous responses are discarded on input/plane changes or unmount. An old ALLOW never proves the newly selected flow has been approved; policy ALLOW remains distinct from actual Agent/target reachability.
- The separate Advanced Access Workspace uses the same evidence predicate for independent Core **diagnosis** and **live visibility**, matching diagnosis to the exact current flow and live observations to the exact current plane/resource filter. Editing any input invalidates previous outstanding generations; async old results cannot overwrite the newer query, and the UI explicitly displays **Diagnosis: UNKNOWN** and **Live access: UNKNOWN** when there is no matching response.
- Active **emergency cutoff** inventory is keyed by Core plane, with newest-request-wins and malformed inventory treated as unavailable; missing counters are `UNKNOWN` rather than invented zero. The emergency cutoff Change Plan review is now keyed to the selected plane, scope kind/reference, operation (apply/clear), and reason. Changing these fields invalidates previous previews and typed confirmation, and the UI shows/queues an Apply only when the verified response belongs to the current request key. Delayed old Preview results are discarded; the plane and cutoff editing controls are disabled while an in-flight Preview or Apply is being handled locally. Actual Core confirmation, RBAC and change plan expiry semantics are unchanged; this is not an independent frontend cutoff authority.
- The work does **not** introduce browser-probing, DNS calls, credential export, a second policy database, new backend API or broader SASE features. It reuses existing Core APIs and Product Foundation/Control visual tokens. Actual user access, Agent join, denied/allowed network traffic and the three-role desktop/375/320 keyboard UXB-06 gate remain separate.

**Test method:** New Node/SSR pure-key regressions cover positive matches, changes to source/service/plane, AI path sensitivity, and cutoff plane/scope/action/reason mismatches. Python UI source contracts separately assert that the real screens use per-request keys, discard obsolete generations, disable in-flight local cutoff changes and keep all read-only observations visibly UNKNOWN without matching Core evidence. Both tests were deliberately run RED before implementation and subsequently passed. These are supporting source-level checks; they are **not** an authenticated browser, a real Agent network E2E or release acceptance.

**Actual isolated dev-source qualification before commit:** P0 Node/SSR **11/11 PASS** (two new exact-flow/cutoff Change Plan key tests first RED and then GREEN), first-use journey **33/33 PASS**, Foundation Administration UI **6/6 PASS**, Python UX source contracts **31/31 PASS**, Foundation management **12/12 PASS**, native isolated Web HTTP **30/30 PASS** (124.669s; a BrokenPipe diagnostic from deliberately closing an invalid request was printed, but all assertions passed), production `npm run build` PASS, deterministic offline Web bundle **6/6 PASS**, optional install/uninstall/reinstall `WEB_PACKAGE_LIFECYCLE=PASS`, and source whitespace `git diff --check` PASS. Existing isolated pinned-certificate HTTPS preview serves compiled `app.js` SHA256 `d1674797420c5d52201dffec11b72e29e5c4cffb6df7156670fdedbfd9774155`, `styles.css` `874789fbf58524f64155f3650903d98286d410e97e4d749178dea5adf792a961` and Foundation CSS matching the worktree exactly; `/healthz` status `ok`, same pre-existing preview PIDs 723342/723343. Optional offline Web archive SHA256 `6d44538eaa50ed1f607e7bc3119edad85bf5aa1fcd59e674d472bf5fec1de01b`. No actual logged-in Admin/Operator/Read Only browser or network reachability was tested, and no Core or credential state was changed in the running preview. All Native Web HTTP actions occurred in the suite's separate temporary test root. The pre-existing 9-line `tests/test-frp-client.sh` candidate and the previously platform-denied browser installer/login tests were not executed or routed through any alternate host or tool.

## 24. UXE-09 — Home first-connection welcome and incomplete Core overview remain truthful (2026-10-09)

**Observed Web UX defect on the isolated v3 branch:** The task-first Home card displayed "Your first protected connection starts here" after a successful Host inventory read whenever the total Managed Host count was zero. A server can have no current Hosts but retain published Remote Services or Remote/Internet/AI rules; the displayed novice greeting would then misclassify existing access configuration as a new empty install. Independently, any truthy, even incomplete `overview` object was announced as "Core overview received" in the first readiness card. Neither presentation proved actual successful connectivity.

**Bounded implementation:** `web/src/uxb-home.tsx` now bases its fresh-install greeting on the same complete `isFreshInstallation` Core-count predicate used by the parent Home workspace, after an observed successful Host inventory response. A common `hasObservedCoreOverview` predicate requires numeric Host/Service totals and complete observed totals for each reported policy family. Missing or malformed Core evidence is **UNKNOWN**, never labeled as received or a fresh installation. Core authorization, Access policy, Agent ownership, server API, browser secrets and release authority are unchanged.

**Reproducible supplemental evidence:** Two new Node first-use regression cases were RED before source fixes and GREEN after them. Focused tests: `npm run test:journey` **35/35 PASS**, `npm run test:p0` **11/11 PASS**, `npm run test:administration` **6/6 PASS**, Python Web UX source **31/31 PASS**, deterministic Web bundle **6/6 PASS**, Web JS production build and offline package install/remove/reinstall **WEB_PACKAGE_LIFECYCLE=PASS**, whitespace **PASS**. Regenerated `web/dist/app.js` SHA256 `1a2e1bf96cb9cb7caed8f1198fe26be12f83db333d9a34ad41da8c3b01258bb3`; offline `dist/data-relay-link-web.tar.gz` SHA256 `267a7bad1ecef8e864f4c089f7ab3298dccb50d434fe92399fbe1f2cc644f826`.

**Gate separation:** A predecessor exact-HEAD CI lint failure was observed in the existing `tests/test-frp-client.sh` Core enrollment fixture path. The platform-denied nine-line local Client test candidate was not executed, edited, staged, committed or used to bypass CI; no alternative test/CI route was introduced. Authenticated Admin/Operator/Read Only browser on desktop/375/320, independent novice observation, real Agent and permitted/denied traffic, two-user frozen-HEAD Full User E2E and owner release remain **NOT VERIFIED**. Node SSR, offline bundling, read-only HTTP and normal GitHub CI are not substitutes for these gates.

## 25. UXE-10 — Global search keyboard focus stays in the dialog (2026-10-09)

**Observed source-level UX gap:** Global Search was marked `role="dialog"` / `aria-modal="true"`, opened with the Search button or Ctrl/Command+K, auto-focused the query input, and closed with Escape; it did not constrain Tab/Shift+Tab to the dialog or restore the triggering control's focus. On a keyboard-only session, focus could leave a visually modal search workspace or be lost when the dialog was removed. These findings are from source inspection, not a logged-in browser reproduction.

**Bounded v3 Web remediation:** `web/src/main.tsx` retains the previously focused trigger in a transient React ref *before* React mounts and autofocuses search. While open, Tab and Shift+Tab wrap between the first and last currently visible, enabled focusable elements inside the dialog; Escape closes it. Mouse-opened search captures the clicked trigger explicitly for browsers where clicking a button does not move keyboard focus. Closing or unmounting returns focus only if the original trigger remains connected, and clears the ephemeral reference. Repeated keyboard shortcuts while open cannot overwrite the return target. No storage of search queries or credentials, new dependencies, route names, Core policy, role entitlement or backend changes. The existing disabled-client test remains excluded from this separate UI change.

**Actual supporting checks:** Python Web source integration/UX contract **32/32 PASS** (new focused static regression protecting modal wiring and focus-return handling); Web production compilation **PASS**; deterministic offline Web bundle **6/6 PASS**; optional Web package install/uninstall/reinstall **WEB_PACKAGE_LIFECYCLE=PASS** and whitespace **PASS**. Newly compiled Web app JS SHA256 `0fa19691429e8e925ca39cfcfd8ed5c303f25e9920960d30239c23cebda74dda`; offline Web archive SHA256 `6585d7564197d5103397cb764ecfc761adeac88b2cfbda881b2f1e9b2a3dfcfe`. A static-source assertion and bundling are **not** human browser, assistive technology, or cross-user E2E qualification. The previously platform-denied focused Node/Home test and browser login/Chromium work were not rerouted.

**Remaining mandatory acceptance:** manually verify desktop, 375px and 320px for Admin/Operator/Read Only using the documented UXE-10 task. Confirm Search button/shortcut initial focus, forward and reverse Tab containment, Escape/overlay/navigation close focus return, result navigation, screen-reader announcements and no clipped action; any further defect requires a new authorized source/test cycle. Real isolated Agent/Allocator, permitted/denied connection and two-user identical frozen-HEAD Full User E2E also remain NOT VERIFIED. GitHub lint remains blocked at the inherited, platform-denied `tests/test-frp-client.sh` enrollment fixture; no CI bypass, merge or release authority is implied.

## 26. Release preflight — synthetic certificate-import fixture and secret scanner (2026-10-09)

**Independent observed release preflight failure:** The unchanged native `bash scripts/secret-scan.sh` returned `SECRET_SCAN=FAIL private key material is tracked` on exact v3 candidate `57f981eb`. A read-only path-only search isolated one tracked match to `tests/test-v30-management-system.py` inside a mocked certificate-import test. Its `key_pem` argument was a deliberately fake PEM-like string containing the literal text `KEY`, not an actual credential. The test intercepts the import operation and asserts the temporary key file was created with mode `0600`, captures its content and checks staging cleanup. This was a repository text-scanner false positive and is **independent of** the previous lint `tests/test-frp-client.sh` Core enrollment blocker.

**Minimal source correction:** Split the synthetic placeholder's `BEGIN`/`END` key header string into adjacent Python string literals. Python constructs the **exact same original PEM-like test value at runtime**, while no contiguous private-key marker remains in the committed text. The production certificate-import implementation, validated trust semantics, scanner rule, scanner scope, exceptions/allowlists, credential handling, policies and package payload were **not changed**. Do not interpret this fixture cleanup as permission to commit real PEM private keys or weaken the secret scanner.

**Actual independent validation before commit:** Parsed the Python AST and compared the runtime synthetic key argument byte-for-byte with the original test string (`SYNTHETIC_KEY_RUNTIME_EQUALITY=PASS`), ran `python3 tests/test-v30-management-system.py -q` **19/19 PASS**, ran the unchanged native `bash scripts/secret-scan.sh` **SECRET_SCAN=PASS**, and `git diff --check` PASS. This does not resolve or bypass the separate platform-denied Client fixture failure, and is not a release qualification, browser acceptance or owner signoff.

## 27. UXE-10 — Search result navigation, focus handoff and assistive status (2026-10-09)

**Observed source issue on the current v3 Web candidate:** UXE-10 previously added a keyboard focus trap and opener restoration to the Global Search modal, but this treated choosing a search result as ordinary dismissal. After navigation the user was returned to the Search button instead of the new page's main content. The dialog also lacked a live announcement for Core search progress/errors; a Core resource result could target a route not authorized for the active Web role and close with no visible destination.

**Bounded Web-only correction:** `GlobalSearch` now records an in-memory `navigatingRef` only after checking the canonical `visibleRoute(id,operator.role)` mapping. A permitted result invokes existing `onNavigate`, closes the modal, and moves focus to the existing focusable `#drlink-main-content`; Escape/outside-click dismissal still restores the original opening control. A denied route instead keeps Search open and displays a `role=alert` message; existing server-side authorization remains authoritative. The query UI announces in-flight Core search through `role=status`/`aria-live=polite`, treats Core resource matches as an accessible group with `aria-busy`, and announces errors via `role=alert`. No policy state, token, credential, browser persistent storage, Core API, route ID, role permission, JS dependency, or production/v2.4 service was changed.

**Actual supporting evidence:** The independent source-level Python UX contract was updated to cover both focus handoff paths, role-gated navigation, live status and errors. An original static assertion expecting the previous single-line focus restoration failed in the first focused run and was corrected to match and enforce the new branch; `python3 tests/test-v30-web-saas-ux.py -q` then passed **33/33**, Web JS production build PASS, deterministic offline Web bundle **6/6 PASS**, optional Web install/uninstall/reinstall `WEB_PACKAGE_LIFECYCLE=PASS`, and whitespace PASS. Built JS SHA256 `826ca81e2f385c7e29ad5264d1af6e375d4048d9f187f00d6e6b7317c0850752`; offline Web archive SHA256 `c68dabc4ce8fc0136d7433d8443ebcab8536bf433e707be23cf03e025279920d`. These are **not** actual logged-in three-role/320px/375px/desktop browser or screen-reader observations.

**Owner/browser acceptance step (not yet completed):** In an authorized Web browser login on the isolated HTTPS development preview, activate Search by click and Ctrl/Command+K, verify the first query receives focus, Tab/Shift+Tab never leaves the open dialog, Escape and outside-click close return to the original trigger, selecting a permitted page moves focus to that page's main content, and any unavailable role-bound destination remains denied with an understandable alert. Repeat with Admin, Operator and Read Only at desktop, 375px and 320px with keyboard/assistive technology. Do not enter login secrets into issues, screenshots, trace logs or public repository docs. Complete UXE-01..12 and the independent novice/live-Agent/two-user frozen-HEAD acceptance separately.

## 28. UXB-06F — Menu Core API truth and partial inventory prequalification (2026-10-09)

**Observed source defect:** Several Web route read paths treated an HTTP 200 response with missing or invalid `items` as `[]`, which falsely displayed a genuinely unimplemented, unavailable or malformed Core API as an empty resource collection. In the same way, filtering a first inventory/policy page without indicating `next_cursor` may misleadingly claim a resource is missing while more Core pages exist. Jobs had similar potential to report no records after invalid inventory. This was source-level evidence, not a completed authenticated-browser reproduction.

**Bounded v3 Web correction:** `web/src/uxb-menu-evidence.ts` provides explicit read-only response-shape checks for Hosts, Services, Rules, Enrollments, Access Hygiene, Jobs, Revisions and Saved Views; Doctor/version/overview require their observed canonical structure. `View` consumes the validator, avoids stale in-flight responses after menu change, and distinguishes successful empty Core results from `UNKNOWN · Core data unavailable` with an explicit `Retry Core read` action. Refreshes of Enrollment, Hygiene and Saved Views keep the same validation. Jobs show loading/unknown state separately instead of rendering an empty table while Core data is missing. Policy/Host/Service first-page filter views warn when an actual Core cursor indicates more rows, without inventing a loaded total or automatically changing rules. Objects & Groups already distinguishes its existing incomplete/partial resource families. No server API contract, user permission, authentication, account data, release authority or Core policy engine was changed; server-side authorization remains authoritative.

**Supplemental deterministic tests:** New `web/tests/uxb-menu-evidence.test.mjs` exercises actual valid empty/populated and malformed Core payloads, cursor semantics and tolerant Objects partial responses; it is wired into `npm run test:journey`. Python source contract also asserts that menu reads/refreshes are validated, inactive route responses cannot overwrite later page state, and partial inventory messaging is present. Such tests and a normal Web build are *not* Browser PASS or actual API availability in an authenticated isolated lab. The owner-requested final complete populated-data menu+API+real-Agent user exercise remains mandatory per §5.3.

## 29. UXB-06F — Administration API truth and one-time secret safety prequalification (2026-10-09)

**Observed additional source issue:** Users & MFA and Integrations initially rendered empty account and destination tables while their backing Web API inventory was loading or malformed, making unimplemented or disconnected APIs appear to have no records. The same first-page/paginated ambiguity existed in some resource menus. This is a source-level finding, not a completed Admin/Operator/Read Only browser test.

**UI-only correction:** The common Core payload validator now includes Admin-only `users`, `service-accounts` and `webhooks`, rejects malformed collection entries and invalid pagination cursor types, and preserves valid empty collections as truly observed emptiness. `UsersPanel` displays Loading or UNKNOWN with an explicit Retry until its authorized `/operators` inventory is valid; it does not offer account/MFA mutation controls on an unobserved user list. `IntegrationsPanel` requires both service-account and webhook inventories before treating either as ready or allowing new management controls; it shows Loading/UNKNOWN/Retry for failed API requests, **while preserving the already returned display-once token or signing secret in the current transient React session** when a *post-create refresh* fails. The server's existing RBAC and credential requirements are unchanged. Jobs' read epoch prevents a late response from hiding a newer status or overwriting an unmounted Jobs page. No real accounts/tokens/permissions, backend, v2.4/production Core, release gate or test allowance was changed.

**Supplemental tests:** The Web journey contract now runs the menu evidence unit cases on valid empty and nonempty pages and malformed/missing entries across all applicable menus, along with malformed cursor scenarios. A focused static Web contract asserts Admin loading/error state, API guard wiring and display-once secret reachability. Actual authenticated three-role Web behavior, screen reader checks, populated-data Agent and traffic flows, independent novices and frozen-HEAD two-user E2E remain **NOT VERIFIED** until a legitimate authorized environment and user/browser access are available.

## 30. UXB-06F — Jobs historical pagination and cross-menu label consistency (2026-10-09)

**Observed source defect and API comparison:** The bounded Management Jobs page fetched only the first 50 jobs and displayed a partial-list warning when Core reported `next_cursor`, but did not let operators reach the remaining pages. The Web Server already supports the documented, bounded `GET /api/v1/jobs?limit=50&cursor=<opaque>` backed by the Core keyset cursor; this is a Web usability gap rather than a Core/CLI/API implementation request. Separately, the Objects & Groups page carried a `Connections` eyebrow despite being located under the `Access` menu's Advanced subsection.

**Bounded v3 optional-Web correction:** Jobs now expose **Older Jobs** and **Newer Jobs** using the exact opaque Core cursor and local in-memory page history. The page count is derived from the actual navigation history (not a guessed Core total); loading/failed responses remain `UNKNOWN`, a new job returns to the first page to find the new result, and an out-of-order async Core page cannot replace the selected result. Read-only roles can browse jobs without acquiring any Job mutation permission. The Objects & Groups eyebrow now names its actual `Access · Advanced` location. No SQL, Core query, server API, user role, Agent or production/v2.4 change.

**Supplemental prequalification:** Python Web source contract asserts cursor forwarding, preceding-page navigation, role-preserving navigation and the correct location label. Web production build, all journey/P0/Foundation administration Node tests and Web bundle/install lifecycle remain distinct from an actual logged-in user clicking through real Core history. During real UXB-06F, verify at least two valid Core pages with real Jobs, click Older/Newer/Refresh after mutations as each role, and check that filters, labels and browser focus remain usable at desktop, 375px and 320px; do not report this as Browser PASS from source-only tests.

## 31. UXB-06F — Audit Explorer fail-closed evidence and filter-result consistency (2026-10-09)

**Observed Web source defect:** Activity & Health → Audit previously rendered `No results` before the authenticated Core API had returned anything, and also when an HTTP-success response had no valid `items` collection. After editing or clearing filters, the prior result list could remain on screen under a new filter, misleading users about what Core actually returned. Async replies from an old search could overwrite a newer request.

**Bounded v3 Web correction:** The `AuditExplorer` now validates each Core audit collection with the same read-only `requireObservedMenuPayload` helper before treating a response as observed. It keeps explicit `loading`, `ready`, `unknown` and `idle` presentation states; no table or `Next page` is displayed until an observed valid Core response exists. Search/latest-page refresh increments an in-memory generation to ignore superseded responses; `Clear filters` invalidates pending requests, clears the prior results and explicitly invites a new `Search audit` rather than implying Core contains no records. Server-side audit retention, RBAC, export, backend logging semantics and actual event records are untouched; this does not create or simulate audit data.

**Supplemental verification:** The focused Python Web UX source contract asserts the Core response-shape guard, loading/UNKNOWN distinctions, latest-wins generation and filter-clear invalidation; separate Node Core menu payload contract validates genuinely empty vs missing/malformed audit lists. Build, bundle and native audit test evidence are supplementary only. Final UXB-06F requires the ChatGPT/user real browser persona to inspect nonempty Audit/Jobs pages using actual test events, deliberately wrong/expired filters and API failure, verify pagination/back navigation and click paths in desktop/375px/320px and Operator/Read Only roles; this gate remains NOT VERIFIED without a populated isolated lab and authorized browser.
