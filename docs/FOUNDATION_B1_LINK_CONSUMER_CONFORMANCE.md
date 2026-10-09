# B2 — DataRelay Link consumes Foundation B1 Administration source

**Status: source-qualified development candidate; NOT product Browser/E2E acceptance.**

## Fixed source and package provenance

- Foundation B1 exact source: `datarelay-labs/datarelay-product-foundation@8726549f80f85b79d94e91a87324d2523e27ddbb` (Draft PR #88).
- Unpublished exact family version `0.1.0-pf8.4`: all **10** package tarballs were copied from the previously generated, immutable Grant source-qualification commit `datarelay-labs/datarelay-grant@5934b8a04d11b18cf25b9b078d2d076652fcbd54` in a read-only, disposable clone. No Foundation registry publication, source rebuild or Playwright installation on the Link host.
- Link `web/foundation.lock.json` is independently checked against the 10 archive SHA256 hashes **and** reconstructed release-staging content-tree SHA256 digests. All 10/10 matched before installation; all 10 packages and exact source revision remain pinned. Old `pf5b.1` packs are retained but not included in the newly built offline runtime bundle.
- New branch `feat/v3-pf5b-foundation-b1-conformance` was derived from `datarelay-link@b9156253973ba48b5cb11b76e9698c6952312300` with a separate Git worktree. The existing Link v3 worktree retains its original platform-denied `tests/test-frp-client.sh` uncommitted content and any independent ongoing changes.

## Link-native integration and negative regression

- The original product-owned `createLinkFoundationAdministrationTasks` is validated against the pinned `@datarelay-labs/testkit.verifyAdministrationConsumer`, not a fake Foundation mock.
- The action inventory is read from the **actual Link Web `LinkFoundationAdministration` switch** and compared with all target actions. Canonical nine tasks/four groups and runtime action bindings must match for the three existing Link roles: Admin, Operator, Read Only.
- TDD reproduced a real presentation bug: empty or unknown role names previously inherited `View` links for certificate status, audit and health despite being unrecognized. Link now preserves product availability separately from actor access, but returns `access=none` and **no target** for unrecognized roles. Admin user-management permissions and the existing Operator/Read Only read-only behavior are unchanged.
- A deliberate missing `link.audit` dispatch case produces `ADMIN_TARGET_UNREGISTERED`; invented action registration cannot grant the non-admin user-management target.
- Existing static UX source assertions were **strengthened** to require guarded read-only access, not bypassed or removed. Offline bundle test was made version-independent and now requires **all 10** exact lock-bound tarballs, rather than one hard-coded `pf5b.1` filename.

## Evidence and remaining B2 release gates

- Offline clean Link Web npm installation (no browser/Playwright package install): **PASS**.
- Foundation Administration Node SSR/source conformance: **13/13 PASS**; Link Web P0 Node tests **11/11 PASS**; Web user-journey fixtures **68/68 PASS**.
- Source UX structural contract **47/47 PASS**; offline Web bundle/tamper/determinism **6/6 PASS**; native management source tests **12/12 PASS**; esbuild production Web app/Foundation CSS **PASS**; Git whitespace check **PASS**.
- `web/dist/app.js` and `web/dist/foundation.css` were rebuilt from the exact pinned local packages; no runtime service/host/Agent/allocator/API policy, SSH firewall, credentials, production or v2.4 files changed.
- **NOT RUN:** previously blocked Playwright install or browser/preview automation; protected `tests/test-frp-client.sh`; authentic three-persona real-user Browser reconciliation; two-user same-HEAD Full User E2E; full release qualification/hash/provenance, PR merge, owner acceptance or package registry publication.
- This is an independent B2 source-only integration slice. Actual common-surface parity and release still require the separately authorized Control, Link and Grant user scenarios; it does not replace them.
