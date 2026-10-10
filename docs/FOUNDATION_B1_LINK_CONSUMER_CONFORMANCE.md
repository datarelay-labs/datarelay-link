# B2 — DataRelay Link consumes Foundation B1 Administration source

**Status: source-qualified development candidate; NOT product Browser/E2E acceptance.**

## Fixed source and package provenance

- Foundation B1 exact source: `datarelay-labs/datarelay-product-foundation@8726549f80f85b79d94e91a87324d2523e27ddbb` (Draft PR #88).
- Unpublished exact family version `0.1.0-pf8.4`: all **10** package tarballs were copied from the previously generated, immutable Grant source-qualification commit `datarelay-labs/datarelay-grant@5934b8a04d11b18cf25b9b078d2d076652fcbd54` in a read-only, disposable clone. No Foundation registry publication, source rebuild or Playwright installation on the Link host.
- Link `web/foundation.lock.json` is independently checked against the 10 archive SHA256 hashes **and** reconstructed release-staging content-tree SHA256 digests. All 10/10 matched before installation; all 10 packages and exact source revision remain pinned. Old `pf5b.1` packs are retained but not included in the newly built offline runtime bundle.
- New branch `feat/v3-pf5b-foundation-b1-conformance` was derived from `datarelay-link@b9156253973ba48b5cb11b76e9698c6952312300` with a separate Git worktree. The existing Link v3 worktree retains its original platform-denied `tests/test-frp-client.sh` uncommitted content and any independent ongoing changes.

## Current Link v3 parent reconciliation

After the original isolated B2 source commit, the existing Link v3 parent
advanced to `5637c2851f1768d01efba58ad940077b66a273da`. This candidate
takes that exact committed parent by a **non-destructive regular merge**,
retaining its Audit Export receipt validation and Agent rollout preview
evidence checks. The only merge conflict concerned generated
`web/dist/app.js`, which was resolved by building from the combined Web
source rather than by discarding either change. The original Link branch and
its protected uncommitted Client fixture remain unchanged.

Combined-source native regression: Administration **13/13**, P0 **11/11**,
Web Journey **70/70**, UX contract **49/49**, bundle **6/6**, and management
source **12/12** PASS, with a fresh production esbuild/Web CSS build PASS.
The separate Web auth **12/12** and isolated Web service **30/30** runs
were also successful on the B2 source prior to the parent merge; those
backend units were not modified by this source merge. All tests remain
supplemental, not direct-user Browser or Full User E2E evidence.

## Link-native integration and negative regression

- The original product-owned `createLinkFoundationAdministrationTasks` is validated against the pinned `@datarelay-labs/testkit.verifyAdministrationConsumer`, not a fake Foundation mock.
- The action inventory is read from the **actual Link Web `LinkFoundationAdministration` switch** and compared with all target actions. Canonical nine tasks/four groups and runtime action bindings must match for the three existing Link roles: Admin, Operator, Read Only.
- TDD reproduced a real presentation bug: empty or unknown role names previously inherited `View` links for certificate status, audit and health despite being unrecognized. Link now preserves product availability separately from actor access, but returns `access=none` and **no target** for unrecognized roles. Admin user-management permissions and the existing Operator/Read Only read-only behavior are unchanged.
- A deliberate missing `link.audit` dispatch case produces `ADMIN_TARGET_UNREGISTERED`; invented action registration cannot grant the non-admin user-management target.
- Existing static UX source assertions were **strengthened** to require guarded read-only access, not bypassed or removed. Offline bundle test was made version-independent and now requires **all 10** exact lock-bound tarballs, rather than one hard-coded `pf5b.1` filename.

## B2 product-native Backup & Import task parity (2026-10-10)

A native consumer discrepancy was reproduced: the shared canonical
`core.backup-import` task appeared as **Unavailable**, despite Link already
supporting authenticated read-only backup archive validation through
`POST /api/v1/system/backup/validate`. Link's Core allows Admin, Operator
and Read Only validation with `management-diagnose`; backup creation and
restore are independently restricted to Admin with distinct Core permissions
and restore confirmation. The product does **not** support the shared
configuration-import editor.

The Link consumer now projects this task as **read-only validation**, with
explicit notes that generic configuration Import is unavailable and Restore
remains independently Admin-authorized. A registered `link.backup` action
opens the existing Advanced Core section and focuses its actual Backup
validator, rather than inventing a new endpoint or backend permission.
Unknown/unauthenticated roles still have no actionable task target.

The pinned Foundation B1 `verifyAdministrationConsumer` checks this
fifth real Web action for Admin, Operator and Read Only and rejects an
unregistered callback. SSR asserts the fourth truthful View task under
the unchanged canonical four groups. Existing Web button role checks and
native Core validation/restore admission are unchanged; this is Web
presentation and navigation only, not a backup/restore proof.

## Evidence and remaining B2 release gates

- Offline clean Link Web npm installation (no browser/Playwright package install): **PASS**.
- Foundation Administration Node SSR/source conformance: **13/13 PASS**; Link Web P0 Node tests **11/11 PASS**; Web user-journey fixtures **68/68 PASS**.
- Source UX structural contract **47/47 PASS**; offline Web bundle/tamper/determinism **6/6 PASS**; native management source tests **12/12 PASS**; esbuild production Web app/Foundation CSS **PASS**; Git whitespace check **PASS**.
- `web/dist/app.js` and `web/dist/foundation.css` were rebuilt from the exact pinned local packages; no runtime service/host/Agent/allocator/API policy, SSH firewall, credentials, production or v2.4 files changed.
- **NOT RUN:** previously blocked Playwright install or browser/preview automation; protected `tests/test-frp-client.sh`; authentic three-persona real-user Browser reconciliation; two-user same-HEAD Full User E2E; full release qualification/hash/provenance, PR merge, owner acceptance or package registry publication.
- This is an independent B2 source-only integration slice. Actual common-surface parity and release still require the separately authorized Control, Link and Grant user scenarios; it does not replace them.
