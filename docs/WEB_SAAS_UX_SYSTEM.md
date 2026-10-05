# Data Relay Link 3.0 — SaaS Workspace UX System

> **Status:** normative 3.0 Web UX contract
> **Roadmap:** DRL3-7A
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

## 3. DR Control visual parity contract

DRLink copies the visual system semantics, not Control application code.

Last implementation verification source (2026-10-05):

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
  Connect Agent (converges toward contextual CTA)

Access Control
  Access Operations
  Policies
  Draft Workspace (converges toward contextual mode)

Operations
  Jobs
  Version Drift
  Revisions / Change History

Observability
  Audit
  Doctor / Troubleshoot
  Health
  Search (converges toward global search)
  Saved Views (converges toward local list action)

Administration
  Users
  System
```

Role filtering remains server-authoritative. Hiding an item is never authorization.

## 5. Application shell

### 5.1 Sidebar

- white/light panel by default, neutral dark panel in dark mode;
- 260 px expanded, 57 px collapsed;
- DataRelay logo + Data/Relay wordmark + product label;
- group headings are quiet labels, not high-contrast buttons;
- active page uses a subtle neutral row highlight, not a bright NOC selection block;
- collapse/expand is persistent local preference only;
- account/environment summary belongs at the bottom rather than consuming page content.

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
- use white cards with 8 px radius and subtle border/shadow;
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
