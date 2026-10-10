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

## UX-P1 B: Typed Host search — explicitly deferred

MeshCentral documents user/ip/group/tag/os tokens but the DRLink Web currently filters only **observed/loaded Core pages**. The exact DRLink v3 `lib/drlink_management_service.py` `managed-host` inventory SQL projection provides id/name/hostname/admission/trust/platform/version/heartbeat but **does not project tag/group/IP attributes**; its server-side `query` predicate matches the canonical Host name expression only, not those MeshCentral facets. A typed/global Host search could therefore hide valid Hosts or imply completeness without authoritative field coverage and cursor/role proofs. No new query engine, network discovery, Core search API or false fleet-wide filter is introduced here. Reconcile product-owned Core projection, pagination and the real 1–100 Host UX before scheduling implementation.

## Validation and release boundary

- Red before implementation: two saved-admission cases failed (null admission-only view and invalid admission erroneously accepted).
- New source after fixes: private filter contract Node 9/9 PASS, Web Journey 83/83 PASS, Web UX source contract 55/55 PASS, Web build PASS, deterministic Web bundle 6/6 PASS and `git diff --check` PASS.
- These checks **are not** authenticated Admin/Operator/Read Only browser testing or Full User E2E. Original platform denials on Playwright/preview login, Chromium install and protected Client tests remain untouched. No production/v2.4/allocator/Agent changes.
- Generated `web/dist/app.js` and static CSS are committed with the source, as an isolated optional Web candidate. No release archive, SHA freeze, source verification artifact, service restart, merge or GA approval is inferred.
- Next true user gate: the current UXB-06F browser ledger in the owning Link workstream, on a coherent exact Web/Core HEAD and legitimately authorized sandbox; preserve existing active-dirty test file.

**Scope decision:** These two small UX improvements do not change DRLink 3.0 release priorities or add MeshCentral RMM browser terminal, file transfer, session recording or device rights.
