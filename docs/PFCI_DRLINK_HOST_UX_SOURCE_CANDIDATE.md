# PF-CI → DRLink 3.0 Host UX source candidate

**Date:** 2026-10-10 KST
**Owner path:** [Link UX roadmap #184](https://github.com/datarelay-labs/datarelay-link/issues/184) and existing [Work Packet #182](https://github.com/datarelay-labs/datarelay-link/issues/182).
**Competitive evidence:** [Product Foundation pilot PR #101](https://github.com/datarelay-labs/datarelay-product-foundation/pull/101) based on MeshCentral documentation and DRLink exact source evidence.
**Implementation baseline:** Optional DRLink v3 Web `feat/v3-pf5b-foundation-administration` commit `870d310d29265d69957e87c5423988bfaf828f87`. This is a **separate, isolated stacked source candidate**; it does not mutate the active Web/Client or Core v3 worktree and it is not a combined frozen product/release candidate.

## UX-P1 A: Host Saved View admission restoration

Existing DRLink Saved Views saved a private text/resource filter but did not capture the independent Host admission selector. The updated presentation layer persists an optional enum (`PENDING_APPROVAL`, `APPROVED`, `QUARANTINED`) within the existing operator-private `saved-views` payload and restores it only on the Managed Hosts list. An explicit selection without text is valid; blank all-state filters remain invalid. Legacy text-only Saved Views continue to open as before. Invalid, unknown and cross-resource admission values fail closed.

This setting is **only a display preference**: it does not grant, revoke, approve or quarantine Hosts, change Core evaluation, obtain more hidden inventory pages, alter role authorization or store credentials. Users continue to receive explicit partial-inventory caveats. The existing authenticated session and CSRF-protected Saved View API remain unchanged.

## UX-P1 C: Task-grouped and allowlisted Host details

The former Host detail drawer rendered arbitrary scalar keys from the selected Core object. The new Host-only presentation uses an explicit positive list of fields under Identity, Trust & Admission, and Connectivity & Version. Missing admission/trust/connection facts are explicitly **UNKNOWN**; false connectivity (including SQLite `0`) is Disconnected, explicit true/SQLite `1` is Connected, and absent/invalid values remain UNKNOWN. Input text is length-bounded and control/bidi characters are removed before React HTML escaping.

Raw source metadata, nested objects, unknown properties, tokens, private keys, cookie/session material and credential fields are not printed. The existing Recent activity and Why can/cannot connect navigation actions are preserved. The Remote Service detail remains unchanged by this slice.

## UX-P1 B: B1 bounded Typed Host Search — implemented as loaded-page filter, NOT fleet-wide Core search

MeshCentral vendor docs show typed user/ip/group/tag/os filtering, but the exact DRLink Core `managed-host` projection exposes only id/name/hostname/status/trust_status/admission_state/connected/agent_platform/agent_version and related bounded timestamps. The Core server-side `query` predicate is **display-name-only**, with a bounded opaque cursor. It does not project or search the advertised MeshCentral `tag/group/ip` attributes.

The B1 implementation adds a pure, positive-list **Web-only** typed filter `web/src/uxb-host-search.ts` for the actually loaded and authorized Core Host pages: `name:`, `id:`, `host:/hostname:`, `status:`, `trust:`, `admission:`, `os:/platform:`, `version:`, `connected:`. Unprefixed searches also check only known Core-projected fields, **never arbitrary source metadata**. Multiple tokens are AND. Malformed/unsupported `tag:`, `group:`, `ip:` and other facets result in **Search not applied**, not a fabricated empty fleet; per-host missing facts are UNKNOWN with explicit warning. Current page and pagination caveats remain visible, saved typed text is only a private display preference and cannot expand Core authorization. No new API, RMM discovery or Core schema change.

The helper's focused RED (missing implementation) → GREEN tests cover supported/unsupported facets, unknown values, arbitrary secret keys and loaded-only scope. Existing admission/Host detail changes from prior PR #206 are preserved, not rewritten. This remains source evidence, **not three-role browser E2E or real-agent proof**.

## Validation and release boundary

- Red before implementation: two saved-admission cases failed (null admission-only view and invalid admission erroneously accepted).
- **Initial A/C source checkpoint (`e808bf54`):** private filter Node 9/9, Web Journey 83/83, Web UX 55/55, Web build, Web bundle 6/6 and whitespace all PASS; these are historical source results, not new typed-search evidence.
- **Current B1 typed filtering (working candidate, 2026-10-10):** new helper initially failed because missing; exact-state regression then failed because `status:active` also matched `inactive`. Both fixed with positive-list Core fields, exact state matches, UNKNOWN/unsupported/partial page caveats. Pure helper 6/6, all Web Journey **89/89**, Web UX source **56/56**, P0 SSR **11/11**, Foundation Administration **6/6**, Core Query **24/24**, esbuild, Secret Scan, Public Metadata and Git whitespace PASS. No native full-suite or real browser/E2E qualification inferred.
- **Native Linux CI classification:** exact parent #183 at `870d310d` (run `37956615105`) and exact initial child #206 at `e808bf54` (run `38022147889`) both fail with `allocator rejected enrollment: enrollment could not be committed to Core` after dual-role restore tests. #206 originally changed Web/tests/docs/assets only; **inherited**, not a PF-CI Host search regression. The protected Client fixture and preview/login/Chromium denials remain binding. Never claim lint PASS or reroute denied tests.
- These checks **are not** authenticated Admin/Operator/Read Only browser testing or Full User E2E. Original platform denials on Playwright/preview login, Chromium install and protected Client tests remain untouched. No production/v2.4/allocator/Agent changes.
- Generated `web/dist/app.js` and static CSS are committed with the source, as an isolated optional Web candidate. No release archive, SHA freeze, source verification artifact, service restart, merge or GA approval is inferred.
- Next true user gate: the current UXB-06F browser ledger in the owning Link workstream, on a coherent exact Web/Core HEAD and legitimately authorized sandbox; preserve existing active-dirty test file.

**Scope decision:** These two small UX improvements do not change DRLink 3.0 release priorities or add MeshCentral RMM browser terminal, file transfer, session recording or device rights.
