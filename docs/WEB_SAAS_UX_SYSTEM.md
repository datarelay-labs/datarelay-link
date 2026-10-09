# Data Relay Link 3.0 — SaaS Workspace UX System

> **Status:** normative 3.0 Web UX contract
> **Roadmap:** DRL3-7A (visual shell) + DRL3-7B (workflow-first usability)
> **Usability roadmap:** `docs/WEB_USER_JOURNEY_UX_ROADMAP.md` (19-product vendor evidence; UXB-01..05 code implemented, UXB-06 actual-user E2E pending)
> **Visual reference authority:** Data Relay Control `main-v2` semantic foundation and App Shell
> **Product authority:** `PRODUCT_MASTER.md`, `WEB_MANAGEMENT.md`, `MANAGEMENT_SURFACE_CONTRACT.md`

## 1. Purpose

Data Relay Link Web Management must feel like a modern zero-trust SaaS workspace, not a
traditional NOC console. The Web surface is an optional management projection over the
same Core authority; visual modernization must not invent a second control plane, weaken
CLI/local recovery, or change security semantics.

The authenticated shell follows Data Relay Control's current visual foundation so the
DataRelay product family feels coherent. DRLink may simplify components for its smaller
scope, but it must not drift into a separate navy/NOC visual language.

## 2. Competitive UX conclusions

Current security/SASE/ZTNA products converge on a few durable patterns relevant to DRLink:

- task/workspace navigation rather than every capability at the root;
- resource list → detail page/drawer → contextual actions/tabs;
- a command-center home that prioritizes posture and required action over raw telemetry;
- policy work grouped by intent, with preview/test/explain close to the policy;
- search, saved views, troubleshooting, enrollment, and draft/change workflows surfaced
  contextually rather than as permanent top-level destinations;
- neutral application canvases with restrained semantic color and one primary action;
- compact sticky headers and collapsible side navigation;
- graph/relationship visualization only where it answers an operator question.

DRLink adopts these patterns selectively. It does **not** become a SOC analytics product,
a generic infrastructure dashboard, or an identity-governance suite.

### 2.1 Competitive reference matrix

| Product | Current pattern relevant to DRLink | Adopt | Explicitly do not copy |
|---|---|---|---|
| Cloudflare One | task-oriented navigation, consolidated Networks/Insights, resource-aware search | bounded workspace navigation, global search, contextual settings | mega-product navigation or Cloudflare product taxonomy |
| Palo Alto Strata Cloud Manager | Command Center as operational home with health/security/relationship drill-down | actionable home and source → control → destination relationship framing | SOC-scale telemetry density |
| NetBird | Control Center relationship graph and Draft Mode | bounded access relationship view and change-preview context | topology graph for decoration |
| Twingate | Policies grouped under one workspace with policy-type tabs | Remote/Internet/AI policy work in one access workspace | flattening distinct DRLink security semantics |
| Tailscale | compact admin console and visual policy editor | simple list/detail and visual policy context | raw ACL-file-first UX |
| Teleport | resource/session/access workflows nested under task areas | detail-centric resource workflow and contextual actions | full identity-governance scope |
| HashiCorp Boundary | resource hierarchy and session/target context | relationship-first detail surfaces | Boundary scope model as product authority |
| Netskope | role/action-oriented dashboard widgets with drill-down | small actionable attention/posture modules | large customizable NOC widget catalog |
| NordLayer | restrained modern SaaS shell, refined surfaces and responsive components | visual polish/accessibility patterns | external identity/device-posture platform scope |

Reference pages used for this 3.0 decision:

- Cloudflare One navigation update: https://developers.cloudflare.com/changelog/post/new-cloudflare-one-navigation-and-product-experience/
- Strata Cloud Manager Command Center: https://docs.paloaltonetworks.com/strata-cloud-manager/getting-started/command-center
- NetBird Control Center: https://docs.netbird.io/manage/control-center
- Twingate security policies: https://www.twingate.com/docs/security-policies
- Tailscale visual policy editor: https://tailscale.com/docs/features/visual-editor
- Teleport Web UI: https://goteleport.com/docs/connect-your-client/teleport-clients/web-ui/
- Boundary console: https://developer.hashicorp.com/boundary/tutorials/get-started-community/community-get-started-console
- Netskope dashboards: https://docs.netskope.com/en/netskope-dashboards
- NordLayer Control Panel 2.0: https://help.nordlayer.com/docs/control-panel-2

## 3. DR Control visual parity contract

DRLink copies the visual system semantics, not Control application code.

Last implementation verification source (re-verified 2026-10-06):

```text
repository   datarelay-labs/datarelay-control
branch       main-v2
verified HEAD 41a561b769fb589f081e84ec5014de6f48881985
foundation   frontend/src/foundation-semantic-tokens.css
global CSS   frontend/src/index.css
shell        frontend/src/components/layout/sidebar.tsx
              frontend/src/components/layout/top-header.tsx
              frontend/src/components/shell/app-shell.tsx
components   frontend/src/lib/gdc-ui-tokens.ts
              frontend/src/components/ui/card.tsx
```

The values below are copied from that semantic foundation. If Control changes later, DRLink
updates only through an explicit UX-contract change; runtime coupling or importing Control
frontend code remains forbidden.

### 3.1 Typography

```text
UI font        Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
Base size      14 px
Small          13 px
XS             12 px
Large          16 px
Page title     20–24 px, semibold
Weights        400 / 500 / 600
```

### 3.2 Shape and spacing

```text
Control radius     8 px
Card radius        8 px
Pill radius        9999 px
Spacing scale      4 / 8 / 12 / 16 / 20 / 24 / 32 px
Sidebar expanded   260 px
Sidebar collapsed   57 px
Top header          58 px minimum
Content max        1440 px
```

### 3.3 Light semantic tokens

```text
page              oklch(98.75% 0 0)
panel/card/input  #ffffff
section/hover      oklch(97% 0 0)
border             oklch(92.2% 0 0)
strong/input       oklch(87% 0 0)
text primary       oklch(21% 0.006 285.885)
text secondary     oklch(37.1% 0 0)
text muted         oklch(55.6% 0 0)
brand mark         #00d084
brand relay        #007e4f
primary action     oklch(54.6% 0.245 262.881)
primary hover      oklch(48.8% 0.243 264.376)
success            #047857
warning            #92400e
critical           #b42318
focus              #1473e6
```

### 3.4 Dark semantic tokens

```text
page              oklch(10% 0 0)
panel/card         oklch(17% 0 0)
section            oklch(15% 0 0)
elevated           oklch(12% 0 0)
input              oklch(21% 0.006 285.885)
hover/divider      oklch(26.9% 0 0)
border             oklch(32% 0 0)
strong border      oklch(37.1% 0 0)
text primary       oklch(97% 0 0)
text muted         oklch(70.8% 0 0)
brand relay        #00d084
status success     #34d399
status warning     #f59e0b
status critical    #f87171
```

Dark mode must use neutral off-black/gray layers. Navy glow or decorative security-console
gradients are not part of the DataRelay visual system.

## 4. Information architecture

The persistent root shell is intentionally small:

```text
Overview
Infrastructure
Access Control
Operations
Observability
Administration
```

Workspace membership:

```text
Infrastructure
  Managed Hosts
  Remote Services
  Objects & Groups
  Connect Agent is contextual only (Overview / host workspace / command palette)

Access Control
  Access Operations
  Policies
  Draft Workspace is contextual only (Access workspace)

Operations
  Jobs
  Version Drift
  Revisions / Change History

Observability
  Audit
  Health
  Doctor / Troubleshoot is contextual only
  Search is the global command/search surface
  Saved Views is contextual through search/list workflows

Administration
  Users (Admin-only)
  Integrations (Admin-only)
  System
```

Role filtering remains server-authoritative. Hiding an item is never authorization.

### 4.1 Product Foundation PF-5B Administration projection

The Link **System** page embeds the pinned Foundation Administration Hub ahead of
Link's existing, Core-authoritative System panel. The common Foundation groups
are **Access & security**, **Platform & network**, **Lifecycle & recovery**,
and **Operations & audit**. The Link-owned sidebar, Web session/MFA rules,
Core routes, and System operations are not replaced by this presentation layer.

- **User Management** is a supported Web Admin function (user creation,
  role assignment at creation, and per-user MFA). It is visible and actionable
  only for `Admin` actors; `Operator` and `Read Only` actors have
  `access=none`, not a falsely reported unsupported product capability.
- **HTTPS** is a read-only common-task projection. The Link System panel
  reports the canonical **MCP TLS** certificate and exposes separate
  Admin-only certificate operations. It does **not** implement the
  Control-reference common task's Web HTTPS listener/redirect configuration.
- **Audit** and **System Health** are read-only tasks routed to Link's
  observability pages. Password Management, Display timezone, Network,
  Retention, and portable **Backup & Import** are shown as unavailable
  rather than given non-existent common-task routes. Link's protected
  disaster-recovery backup/restore actions remain a separate System-panel
  workflow and must not be described as portable workspace import/export.

Task `availability` describes an actually implemented product capability.
Task `access` describes the current actor's permission. Visual filtering
does not authorize API calls; Web/Core enforce mutations independently.
Actual browser/mobile accessibility and role acceptance remain separate E2E gates.

The offline, non-browser Administration qualification runs after the pinned
Web dependencies are locally available:

```sh
cd web
npm run test:administration
```

This compiles Link's real `src/foundation-administration.ts` projection in
a disposable directory and server-renders the pinned Foundation
`AdministrationHub` for `Admin`, `Operator`, and `Read Only`. It checks
four-group composition, effective task availability, privileged button
visibility, and honest HTTPS/MCP TLS status. It does **not** interact with the
deployed site or qualify keyboard, responsive, mobile, or browser E2E behavior.
The offline Web release archive must contain the projection source as well
as the precompiled UI and exact pinned Foundation packages.

## 5. Application shell

### 5.1 Sidebar

- white/light panel by default, neutral dark panel in dark mode;
- 260 px expanded, 57 px collapsed;
- DataRelay logo + Data/Relay wordmark + product label;
- group headings are quiet labels, not high-contrast buttons;
- active page uses a subtle neutral row highlight, not a bright NOC selection block;
- collapse/expand is persistent local preference only;
- account/environment summary belongs at the bottom rather than consuming page content;
- Sign out lives with the account panel in the sidebar, matching Control rather than becoming a top-header primary action.

### 5.2 Top header

The sticky 58 px header contains:

- breadcrumb/context when useful;
- page title;
- small health/attention pill plus bounded summary;
- global search/command entry;
- refresh, theme, and account/session actions.

### 5.3 Main canvas

- page background is near-white neutral, not blue-gray;
- content is centered/bounded to 1440 px where practical;
- use white cards with 8 px radius, subtle neutral border, and Control-equivalent `shadow-sm`;
- use Control-equivalent optimized text rendering, selection color, and thin neutral scrollbars;
- semantic color is reserved for action/status, not decorative chrome.

## 6. Command Center Overview

Overview answers, in order:

1. Is the product healthy?
2. Does anything require attention?
3. Who/what can currently reach what?
4. What changed recently?
5. What is the next common action?

Minimum layout:

```text
Header: Overview + health + Connect Agent
Posture strip: Managed Hosts / Connected / Remote Services / Active Jobs
Needs Attention
Access overview / relationship summary
Recent activity and recent configuration changes
```

Raw tables are drill-down content, not the home experience.

## 7. Resource workspaces

Managed Host, Remote Service, policy, identity, enrollment, and job rows should converge on
click-through detail views/drawers with contextual tabs/actions. Do not force operators to
jump between unrelated root pages to answer a single resource question.

## 8. Access workspace

Remote Access, Internet Access, and AI Access keep distinct semantics but share a visual
workspace. The long-term access map shows:

```text
Source → Policy / decision → Destination / Service / Permission
```

The operator can pivot to matched policy, policy test/explain, Temporary Access, draft
preview, and recent access decisions from the same context.

## 9. UX safety

- destructive actions remain explicit and typed-confirmed where required;
- Web does not hide UNKNOWN or synthetic-vs-real evidence boundaries;
- status color never substitutes for text;
- MFA, recovery, update, restore, uninstall, and emergency cutoff retain their Core safety
  contracts;
- visual simplification may reduce navigation noise but never reduce authorization checks.

## 10. DRL3-7A implementation order

Current implementation checkpoint (2026-10-05): implementation-order items 1–6 are now
in the Web package. This includes semantic token parity, Control-compatible App Shell,
collapsible navigation, sticky header, light/dark theme, actionable Command Center, global
search/command palette, contextual removal of Search/Saved Views/Connect Agent/Draft/Doctor
from permanent navigation, Managed Host/Remote Service/Object/Policy list-detail workspaces,
and the relationship-oriented Access workspace. Responsive shell rules, skip navigation,
keyboard command search, Escape-close dialogs, and deterministic UX contract regression are
also implemented. Remaining release work is real-browser owner/user UX validation, any
resulting targeted fixes, and exact-candidate qualification after the UI is frozen.

Owner browser review fixes completed in the current implementation cycle:

- Jobs fleet-metadata form converted from a dense one-line control strip into sectioned
  target / metadata / group-membership form grids with bounded responsive spacing;
- Audit Explorer filters and retention controls aligned to deterministic grids and action
  rows instead of mixed-width toolbar wrapping;
- Health replaced raw-JSON-first presentation with structured Core / DB / policy-plane /
  job-capacity views; raw payload is now an explicit advanced disclosure only;
- MFA enrollment is QR-first and keeps the setup secret ephemeral: the QR is rendered
  locally from the temporary `otpauth://` challenge with no external QR service, the raw
  fallback key is hidden by default with explicit reveal/copy, recovery codes appear only
  after successful verification, and Cancel setup immediately revokes the pending challenge
  so the next login receives a different key.

Current evidence state:

```text
DR_CONTROL_VISUAL_TOKEN_PARITY=PASS
SAAS_SHELL_PARITY=PASS
BOUNDED_ROOT_NAVIGATION=PASS
COLLAPSIBLE_SIDEBAR=PASS
LIGHT_DARK_THEME=PASS
COMMAND_CENTER_OVERVIEW=PASS
CONTEXTUAL_WORKSPACE_NAV=PASS
WEB_PACKAGE_VISUAL_PARITY=PASS
BROWSER_REAL_USER_UX=PENDING_REAL_BROWSER_REVIEW
```

1. foundation semantic tokens + authenticated shell parity;
2. collapsible grouped sidebar + sticky top header + theme/local preference;
3. Command Center Overview modernization;
4. global search and contextual removal of utility root destinations;
5. resource list/detail modernization;
6. Access relationship workspace;
7. browser accessibility/responsive/real-user qualification;
8. freeze candidate and restart DRL3-8 exact-HEAD evidence.

## 11. Acceptance

```text
DR_CONTROL_VISUAL_TOKEN_PARITY=PASS
SAAS_SHELL_PARITY=PASS
BOUNDED_ROOT_NAVIGATION=PASS
COLLAPSIBLE_SIDEBAR=PASS
LIGHT_DARK_THEME=PASS
COMMAND_CENTER_OVERVIEW=PASS
CONTEXTUAL_WORKSPACE_NAV=PASS
WEB_PACKAGE_VISUAL_PARITY=PASS
BROWSER_REAL_USER_UX=PASS
```

## 12. DRL3-7B — First-time, non-developer usability target (PENDING)

This specification's DRL3-7A shell, visual token and layout criteria are **necessary
but not sufficient** for the target Data Relay Link Web interface. The 2026-10-09
owner review found that while the implemented UI is better visually, the menus
are not yet self-explanatory. The existing P0 access, policy and Agent screens
are **technical foundations**, not a completed beginner user journey.

The accepted roadmap destination for the next UX design/implementation slice
is [the workflow-first Web UX roadmap](WEB_USER_JOURNEY_UX_ROADMAP.md),
recorded as **DRL3-7B in `DATA_RELAY_ROADMAP.md` section 17B**.
It contains:

- 19-product official-doc evidence and its explicit limitations;
- target Home / Connections / Access / Activity & Health / Administration
  labels with current route, actor and canonical product-term mappings;
- step-by-step first Host → Remote Service → narrow policy → access verification,
  plus independent Internet and AI Access journeys;
- inline explanation/advanced disclosure, context-preserving navigation,
  truthful evidence and no-guess next actions;
- UXB-01..06 implementation slices and actual first-time-user/real-browser
  E2E acceptance before claiming a final product UI.

**DRL3-7B status (2026-10-09): UXB-01..05 CODE IMPLEMENTED IN ISOLATED WEB PREVIEW / USER E2E NOT VERIFIED.** The current
`DRL3-7A` visual acceptance and source-level Web P0 test evidence must not
be interpreted as DRL3-7B first-time usability PASS. All proposed navigation
renames are **presentation aliases only** until owner review and a scoped
implementation preserve stable Core/CLI contracts, Product Foundation's
four-group Administration, RBAC/MFA/session protections and Link's
Remote/Internet/AI access semantics.

Previously safety-denied browser/preview login tests remain prohibited from
rerouting. Only a genuinely permitted real User E2E and final owner
acceptance may qualify the target UI at a frozen candidate HEAD.
