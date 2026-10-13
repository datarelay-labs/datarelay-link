# Link 3.0 — Private Product Foundation RC41 consumer gate

This is a product-owned **offline preflight**, not Foundation RC41 product installation,
browser acceptance, release permission, or a replacement for Foundation's canonical
private source/byte verifier.

## Immutable candidate (independently checked from Foundation PR #104)

- Original Foundation source: `46ddb60cad8eae7b1718588cd19421e61b5300e7`
- Later Foundation documentation HEAD: `68fe00e423458cdd77a6a9313073312bb2382caf`; **not** the package source
- Private ten-package npm family: `@datarelay-labs/*@0.1.0-rc.41`
- Combined private bundle SHA256: `628dd4d6fd8ccb1d39dd6cc33982a3411fedcca405aa193b3654505fcaaefb48`
- Python Wheel SHA256: `cad95d8ba2d707690ccdfc8ca097e9e746d8ace0f27d70c1c4c638bc663399b8`
- Foundation exact-source native tests 512/512 and source CI PASS; disposable Foundation
  consumer imports 18/18 and Python Wheel native tests 153/153 PASS
- Source of this identity: private Foundation
  `docs/PF10_PF12_RC41_PRIVATE_HANDOFF_2026-10-12.md`

The owner-supplied candidate is private and unpublished:
`SIGNED_DISTRIBUTION=false`,
`OWNER_LEGAL_DISTRIBUTION_APPROVED=false`,
`CONSUMER_PRODUCT_INSTALLED=false`. Neither private npm/Wheel bytes nor private
Foundation source may be committed, placed in an accessible Web static directory,
or exposed through public Link PRs, artifacts or CI logs.

## Link-side read-only gate

An authorized operator privately supplies the entire original RC41 bundle outside
the Git worktree, then executes:

```bash
python3 tools/verify-link-foundation-rc41.py \
  --bundle /approved/private/foundation-only-46ddb60cad8eae7b1718588cd19421e61b5300e7.tar.gz
python3 tests/test-link-foundation-rc41-verifier.py -q
```

The tool pins the original outer digest, byte count, all ten package archive
SHA256 values, the Python Wheel SHA256, required provenance members, archive
root, path and member types. It **does not extract**, execute, install, access
the network, change Git, or accept an unreviewed in-bundle digest as authority.
A successful preflight is necessary but **not sufficient** for product adoption.

## Private, isolated Web compatibility stage

If the operator has independently supplied the approved, complete original
RC41 archive on `dev-drlink`, a single Link-owned command can validate and
exercise the same Web with ten RC41 packages **without modifying the public
checkout or default `pf8.4` package pins**:

```bash
mkdir -p -m 700 "$HOME/.cache/drlink-foundation-rc41-staging"
python3 tools/stage-link-foundation-rc41.py \
  --bundle /approved/private/foundation-only-46ddb60cad8eae7b1718588cd19421e61b5300e7.tar.gz \
  --private-root "$HOME/.cache/drlink-foundation-rc41-staging"
```

The command first enforces the original independent SHA256 pins, stages only
verified npm archives, checks the immutable Foundation lock and changes only
the private scratch Web dependency projection. It performs `npm install`
strictly offline with lifecycle scripts disabled, verifies all ten installed
package names/versions, then runs the existing Link Web build, 3-role
Administration tests and Journey tests. Temporary private archives and the
scratch Web are removed after test completion or failure. An absent/unverified
RC41 bundle fails before staging. This is a source compatibility gate, not a
live Web installation, signed product qualification or a release decision.

### Authenticated private GitHub source: deterministic RC41 package replay

A distinct, owner-approved internal source path can also be used when the
original whole bundle is not available. It is **not** a retry of the previously
platform-denied dev-atlas-to-dev-drlink transfer. The developer must have
normal authorized **private GitHub repository read access**, retrieve the exact
immutable `46ddb60` Foundation commit into an owner-only directory outside
the Link Git tree, and rebuild 10 npm tarballs using Foundation's original
`tools/stage-release.mjs` with `0.1.0-rc.41`.

The builder must normalize Foundation Git-tracked source file modes to the
actual Git index modes (0644 for non-executables and 0755 for executable
entries) before staging. The originally observed `umask 077` mode 0600
produced nonmatching archives; staging under `umask 022` after restoring
tracked source modes reproduced **10/10 exact original RC41 tar SHA256s**.
These operations take place **only inside the authenticated private checkout**
whose ancestor directory is mode 0700, never in public Link Git.

The resulting private, source-locked paths on the approved `dev-drlink`:

```text
$HOME/.cache/drlink-foundation-rc41/private-source
$HOME/.cache/drlink-foundation-rc41/stage-normalized/release-manifest.json
$HOME/.cache/drlink-foundation-rc41/packs-normalized
```

Run the same Link-owned fail-closed compatibility gate without weakening the
original whole-bundle verifier:

```bash
python3 tools/stage-link-foundation-rc41.py \
  --verified-package-dir "$HOME/.cache/drlink-foundation-rc41/packs-normalized" \
  --private-source-checkout "$HOME/.cache/drlink-foundation-rc41/private-source" \
  --source-package-manifest "$HOME/.cache/drlink-foundation-rc41/stage-normalized/release-manifest.json" \
  --private-root "$HOME/.cache/drlink-foundation-rc41"
```

Before touching npm, this mode verifies exact private `git rev-parse HEAD`,
clean Git source checkout, immutable versioned package manifest, independently
pinned **all ten** individual tar SHA256 hashes, and ownership-only private
scratch. It then installs npm strictly offline with scripts disabled, builds
the **actual Link Web source**, and runs Admin/Operator/Read Only Administration,
full Web Journey and P0 test suites against RC41. It stages the original Link
CSS and the exact PUBLIC docs/Core read-only test fixture in its temporary
private test layout, cleans up temporary files, and leaves the separately
retained authenticated private source/packages under the 0700 parent.

This staging helper also has **synthetic fixture** security tests in
`tests/test-link-foundation-rc41-staging.py`. On 2026-10-13 a **separate
real-package** private run verified ten matching tar SHA256 hashes and passed
the Link Web production build, Administration **20/20**, Journey **412/412**
and P0 **42/42**; it did **not** install a live Server/Agent, qualify Browser
E2E, publish RC41 or alter the public Link dependency lock.

## Consumer migration boundary

The default PUBLIC Link Web remains on the tracked `pf8.4` package family
until an authorized, reproducible **private package supply for all product
builders/CI** is available. Although authenticated private RC41 staging and
source tests now PASS on dev-drlink, do not change default `web/package.json`,
`package-lock.json`, `foundation.lock.json` or delete the rollback packages.
Never commit an RC41 file dependency whose private archive is absent from the
publicly reproducible checkout or publish private Foundation sources/assets.

Once a permitted private delivery is available, Link's owning Chat can run
product-specific isolated install and verify:

1. Exact ten-package offline install, source/version/hash and external
   archive receipt; keep generated bytes outside public Git and Web static
   directories.
2. Current Link `AdministrationHub` / `createStandardAdministrationTasks`
   role and action conformance for Admin, Operator and Read Only, with native
   Core authorization still authoritative.
3. New Foundation PF10–PF12 UI only where Link Core actually exposes the
   required reviewed typed projection. Unsupported controls stay
   unavailable/read-only; never synthesize approval, audit forwarding,
   retention deletion, secret rotation or recovery success.
4. Web production bundle, Link native source/CI and rollback against the
   **same** installed/private candidate; true Browser, signed Agent,
   two-person User E2E and release remain independent owner gates.

## Current Link checkpoint (2026-10-13)

- Link Draft PR #206 source candidate before this scoped update:
  `f8adc3f94026528f7aec17a7837b804d62132180` (exact latest PR HEAD
  must always be re-read). Public default Web packages remain `pf8.4`.
- Foundation private original RC41 source `46ddb60cad8eae7b1718588cd19421e61b5300e7`
  was checked out directly through the authenticated private GitHub remote on
  dev-drlink and built inside a 0700 root; rebuilt npm archives **10/10 SHA256
  exactly match** the independent Foundation owner receipt.
- The original dev-atlas cross-host transport was safety denied; partial bytes
  were discarded, **not reused, retransmitted or used as an authorization**.
- The Link RC41 private isolated Web dependency installation and source build
  passed, with native Admin 20/20, Journey 412/412 and P0 42/42. The private
  compatibility runner independently reproduced the same results and cleaned
  its temporary Web staging. All results are source/isolated-product checks,
  **not installed Server/Agent/Browser or genuine User E2E**.
- No original Foundation package, Wheel, secret, private code or npm tarball
  is part of the public Link Git change. Separate private package distribution,
  secure publication, user/release gates and live candidate promotion remain
  explicitly unqualified.
