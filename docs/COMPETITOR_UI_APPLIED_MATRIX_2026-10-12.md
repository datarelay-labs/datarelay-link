# DataRelay Link 3.0 — Competitor UI Adoption Closure (source-only)

**2026-10-12 KST · Canonical roadmap:** [Issue #184](https://github.com/datarelay-labs/datarelay-link/issues/184), [ACTIVE Work Packet #182](https://github.com/datarelay-labs/datarelay-link/issues/182), [existing Draft PR #206](https://github.com/datarelay-labs/datarelay-link/pull/206).

**Owner mandate:** finish *applicable, Core-authorized* competitor-derived UI implementation **before non-UI work**. User separately excludes real E2E from this implementation pass. This is an exact **source adoption/status index**, NOT release approval, product Browser PASS, copied vendor code, or an automatic Core security authorization. Earlier dated source analyses remain authoritative in [screen-by-screen P0-1/P0-2 evidence](COMPETITOR_UI_SCREEN_EVIDENCE_2026-10-11.md) and historical [13-vendor first-pass](WEB_UX_COMPETITIVE_AUDIT_2026-10.md). Do not turn vendor screenshots into claims of authenticated product interaction.

## Implementation decision key

- **APPLIED** = original DRLink Web source integrated with tests into existing open Draft PR #206, using only the product's already supported Core routes/data. There is **no actual browser/persona/E2E qualification** unless separately evidenced.
- **PRESERVED** = existing DRLink source already supports the appropriate operator workflow; replicating it would create duplicate UI and permission semantics.
- **REJECTED** = vendor-specific or edition-only functionality lacks corresponding DRLink data, scope, license or security authority; not an approved backlog item.
- **SECURITY GATE** = product owner requires the workflow but source **cannot truthfully implement it without a separately reviewed Core authorization/persistence contract**. It stays unfinished, not an empty checkbox.

## Canonical UX-1..UX-8 and UI-01..UI-06 owner matrix

| Owner objective | DRLink actual component/contract | Source decision / remaining gate |
| --- | --- | --- |
| UX-1 explain access from source→rule→destination | `p0-access-policy.tsx::AccessEvidenceExplorer`, `focusCoreModeledPaths`; UI-02 bounded publication-owning Host evidence; G01/G18/G37 | **APPLIED** read-only modeled/correlated/visible Core facts; does not assert live/effective connection |
| UX-2 task-first guide and safe changes | `p0-access-policy.tsx::GuidedPolicyJourney`; G06 rule-intent summary; exact Core Preview→Tests→bounded Impact→typed Apply | **APPLIED** to existing Core contract; no parallel authorization engine |
| UX-3 issue→install→approve→verify | `p0-enrollment.tsx::EnrollmentOnboarding`, first-use Home, separately modeled trust/admission/connected | **APPLIED** source, no automatic trust or preapproval |
| UX-4 posture/confidence/freshness/real drilldowns | `uxb-home.tsx::observedCoreOverviewEvidence/observedHomeAttention`; `main.tsx::CommandCenter` G37 explicit Core timestamp and route/action links | **APPLIED** fleet-derived counts with UNKNOWN and selected-plane/actor-safe read-only context, not guessed exact affected host |
| UX-5 contextual Audit investigation | `uxb-audit-context.ts`, G07/08 event details/time, G22 policy→Audit, G36 current applied query/page refresh | **APPLIED** explicit bounded Core Audit route; exact previously denied Policy detail-drawer callback remains unchanged |
| UX-6 Administration taxonomy/actor role | `foundation-administration.ts`, `SystemAdministrationWorkspace`, Foundation 4 groups | **PRESERVED/APPLIED** existing product/role guard; actual browser role verification excluded |
| UX-7 320/375/desktop focus and responsive design | native buttons, `web/dist/styles.css`, Table/Cards, focus and wrapping, G37 44px attention targets | **SOURCE APPLIED** where tested; **real viewport/keyboard Browser UNVERIFIED** (explicitly excluded here) |
| UX-8 search/status/empty/error/partial semantics | G09–17 Host/Service, G18–29 Policy, G30–35 Saved Views, bounded UNKNOWN Core evidence | **APPLIED** source only; unauthorized inventory/secret search rejected |
| UI-01 modeled permission path | Core graph/trace read-only `AccessEvidenceExplorer`, G01 | **APPLIED**; modeled ≠ live network access |
| UI-02 Remote Service→owning Host | `p0-access-policy.tsx` observed Core publication relationship / exact Host identity (ancestor source `192677cf`) | **APPLIED** existing source; unrelated prior **Policy detail drawer** platform-denied callback is NOT retargeted |
| UI-03 carry a verified context | setup/policy/draft navigation, exact audit investigation/return | **APPLIED** source |
| UI-04 Home/Host/Admin guided sections | `main.tsx`, `uxb-host-detail.tsx`, Foundation 4 group Hub, G37 | **APPLIED** source |
| UI-05 explicit Core change impact | bounded blast radius, required tests and typed one-shot confirmation | **APPLIED** existing canonical Core/Change Plan semantics |
| **UI-06 two-person time-bounded access request/review** | Existing `TemporaryAccessPanel` is **one actor's** Core preview/apply, explicitly says **NOT** request/reviewer approval. No durable request→different authorized reviewer→atomic decision→expiration/audit contract exists. | **SECURITY GATE — NOT IMPLEMENTED.** Requires explicit owner/security design acceptance, SQLite migration/roles/transaction/replay/concurrency/rollback and canonical Core contract. A fake reviewer form would create an unsafe privilege claim |

## Competitor screen → product code/decision ledger

References `CUI-001…040` are **40 ledger slots, not 40 distinct live authenticated product screens**. The early original ledger did not print literal CUI-027/CUI-028 identifiers; this status crosswalk assigns them **only as existing G24/G25 source associations**, never as new historical observations.

| Competitor reference(s) | UI idea | DRLink decision and exact delivered feature |
| --- | --- | --- |
| CUI-001 NetBird, CUI-003 Twingate | context-focused who→policy→resource | **APPLIED** G01 modeled-path focus, UI02 verified publication, G37 bounded Home context; no NetBird/Twingate mesh model transplanted |
| CUI-002 Tailscale | guided policy rule + preview/tests | **APPLIED** existing GuidedPolicyJourney and G06 explicit prepared intent |
| CUI-004 Teleport, CUI-005 StrongDM | enterprise requester/reviewer and expiry/history | **SECURITY GATE** UI06 genuine separate Core model absent; **no copy** or false completion. Only independently applicable read-only cards/review evidence adapted G20/21 |
| CUI-006 Cloudflare | actor/decision/time audit filtering | **PRESERVED** existing AuditExplorer filter/query; no fake per-request auth events |
| CUI-007 StrongDM | inspect single audit event details | **APPLIED** G07 source-whitelisted event details |
| CUI-008 Boundary | session broker/recording | **REJECTED** unowned session broker; existing Live Access observation does not prove Boundary session semantics |
| CUI-009 Palo Alto | quick time window shortcuts | **APPLIED** G08 UTC Audit presets |
| CUI-010 Zscaler | investigation time range | **PRESERVED/ADAPTED** G08 Core Audit time; vendor 14-day retention/analytics **REJECTED** |
| CUI-011 Palo Alto | NOC/traffic analytics | **REJECTED** no corresponding licensed Core telemetry or valid risk score |
| CUI-012 NetBird | Policy Enabled/Disabled/UNKNOWN | **APPLIED** G09 status filtering |
| CUI-013 Firezone | service search/type/configuration facets | **APPLIED** G13 |
| CUI-014 Firezone | Resource detail/drawer | **PRESERVED** existing ResourceWorkspace loaded-only detail |
| CUI-015 Firezone | personal Starting Page | **APPLIED** G14 role/actor-scoped start |
| CUI-016 NetBird | Host name ordering | **APPLIED** G15 |
| CUI-017 NetBird | peer mesh/IP-specific sorting | **REJECTED** different network model, no invented Core IP/group edge |
| CUI-018 NetBird | explicit peer last seen vs connected | **APPLIED** G16 Agent heartbeat / truthful unknown |
| CUI-019 NetBird | active Host filter chips | **APPLIED** G17 |
| CUI-020 Teleport | global resource search→exact detail | **APPLIED** G18 |
| CUI-021 Pomerium | SSH Service connection guidance | **APPLIED** G10; no unauthenticated SSH/browser launch |
| CUI-022 Teleport | resource table/card density | **APPLIED** G19 Host/Service cards |
| CUI-023 / CUI-024 Teleport | reviewer resource/duration cards | **APPLIED** G20 expiry triage/G21 Policy cards for READ-only facts; actual independent approval UI06 **SECURITY GATE** |
| CUI-025 Teleport | event→policy/Audit deep-link | **APPLIED** G22 read-only policy row/card→Audit |
| CUI-026 NetBird | Policy Name order | **APPLIED** G23 local policy sort |
| CUI-027* NetBird | Policy active filter chips/reset | **APPLIED** G24; indexed from G24 P0-1 evidence without inventing additional observation |
| CUI-028* NetBird | Policy source/destination facts | **APPLIED** G25 AI card destination/permission; indexed from G25 P0-1 |
| CUI-029 NetBird | AI policy Source→Provider columns | **APPLIED** G26 sanitized default Table AI mapping |
| CUI-030 NetBird | AI policy source/provider filter | **APPLIED** G27 search on already verified Core AI ref IDs |
| CUI-031 Grafana | reopen saved/starrred queries | **APPLIED** G28 operator-private Policy Saved View via existing Core API; no Enterprise library sharing |
| CUI-032 NetBird | safe Policy row name/description | **APPLIED** G29 fixed-whitelist Table display |
| CUI-033 Grafana | private saved query search | **APPLIED** G30 Saved View name-only list search |
| CUI-034 Grafana | query history changed-time sort | **APPLIED** G31 bounded loaded-only Saved View sort |
| CUI-035 Grafana | datasource/type filter | **APPLIED** G32 private Saved View type facet, retains unsupported entries |
| CUI-036 NetBird | per-table filter reset | **APPLIED** G33 local Saved Views list reset |
| CUI-037 NetBird | removable filter chips | **APPLIED** G34 Saved Views fixed-label chips, no raw query |
| CUI-038 NetBird | 25-row table paging | **APPLIED** G35 loaded-first-100/25-page truthful count |
| CUI-039 NetBird | Audit table refresh | **APPLIED** G36 exact previously-applied Core Audit query/current page refresh |
| CUI-040 NetBird/Twingate | navigable Core evidence/related workspace | **APPLIED** G37 CommandCenter attention/KPI and selected policy plane read-only routing + observed timestamp |

### Unresolved items (do not relabel as completed)

**Only one known owner-mandated missing competitor UI capability cannot be delivered with currently authorized Core:** **UI-06 distinct reviewer/expiry/Audit approval**. Its exact proposed canonical Core contract, RED→GREEN authorization scenarios and explicit separate owner approval gate are documented in `WEB_USER_JOURNEY_UX_ROADMAP.md` and Issue #184. Work on adjacent ordinary UI does not create that contract.

Previous specifically platform-denied detail-drawer correction/Browser/Client/packaging effects remain held; do not retarget through another tool. E2E explicitly deferred by user. Other roadmap **M2 Core/Agent integration** and **M3 backup/offline upgrade** are still independently tracked as integration or privileged qualification, **not all implemented merely because competitor UI source is mapped**. M5 release is not approved. The Draft PR is not merged, CI and distributed build acceptance remain separate.

### Verification approach and source provenance

- Every G01–G37 `P0-1` source/license/REA and `P0-2` original product implementation/test timeline is in the companion ledger, which takes precedence over this crosswalk if a date or source is ambiguous.
- G37 last source candidate: P0 38/38 PASS, Web Journey 345/345 PASS, Administration 20/20 PASS, Python UX 56/56 PASS, Bundle 6/6 PASS, production build + diff PASS; exact commit `290048551d95f0a7e20eed657c208ecce1127aa7`; **not Browser/full E2E**.
- This matrix reconciles **source implementation vs gated/rejected**; there is no truthful basis to assert “all competitor features fully implemented and accepted” until UI06 is separately authorized and implemented, and full user qualification is separately completed when requested.


## Original 13-product audit — complete first-pass disposition

This is a **source-specific comparison of 13 official public product documentation references** in `WEB_UX_COMPETITIVE_AUDIT_2026-10.md`, not an exhaustive survey of the industry and not a claim of authenticated competitor access.

| Vendor in original 13-product scope | Product-relevant application or clear rejection |
| --- | --- |
| Tailscale | Guided PolicyJourney, regression tests, G06 prepared change review — **APPLIED** original Link safe Core UI |
| NetBird | Read-only selected policy graph, Host/Policy sorting/status/filter chips, G37 Home evidence drilldowns — **APPLIED** safe subset, no VPN mesh assumptions |
| Twingate | Verified publication owning Host and bounded source→policy→resource explanation — **APPLIED** UI02 and G01/G37, no Twingate group authority |
| Teleport | Existing resource cards/Policy review/Audit G19/G21/G22 — **APPLIED**, Enterprise independent reviewer request **SECURITY GATE** |
| Cloudflare One | Existing Core Audit by actor/time/result, G07 event detail — **PRESERVED/APPLIED**, no Edge Authentication logging equivalence claim |
| StrongDM | Core Audit event detail G07 — **APPLIED**; Enterprise Access Request/independent approval **SECURITY GATE** UI06 |
| HashiCorp Boundary | Bounded Live Access/Host/Service source remains — **PRESERVED**; Boundary broker/session termination/recording **REJECTED** |
| BeyondTrust PRA | Field operator vs System Administration separation in existing Foundation 4-group hierarchy — **PRESERVED**, no appliance privileged session semantics |
| Zscaler ZPA | G08 bounded Audit UTC shortcuts — **APPLIED**; ZPA traffic analytics/14-day retention assumptions **REJECTED** |
| Palo Alto Prisma Access / Strata | CommandCenter Core-derived overview/UNKNOWN + G08 Audit UTC — **APPLIED** appropriate read-only subset; traffic/anomaly-score dashboard **REJECTED** |
| NordLayer | Mobile-safe keyboard-native controls, responsive 560px breakpoints, G37 focus-visible 44px target — **SOURCE APPLIED**, 320/375 Browser parity **UNVERIFIED** |
| Appgate SDP | Role-aware catalog/Administration visibility backed by Core checks — **PRESERVED**; no Appgate SDP Policy entitlement semantics copied |
| JumpCloud | Existing actor-dependent navigation/deny states and Core authorization remain — **PRESERVED**; conditional-access broker/IdP policy engine **REJECTED** |
