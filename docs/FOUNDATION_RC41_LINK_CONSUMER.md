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
full Web Journey and P0 test suites against RC41. It stages Link-owned
`index.html`/`styles.css` and exact PUBLIC docs/Core read-only test fixtures
in its temporary private test layout, cleans up temporary files, and leaves
the retained authenticated private source/packages under the 0700 parent.

This staging helper also has **synthetic fixture** security tests in
`tests/test-link-foundation-rc41-staging.py`. On 2026-10-13 a **separate
real-package** private run verified ten matching tar SHA256 hashes and passed
the Link Web production build, Administration **20/20**, Journey **412/412**
and P0 **42/42**. On the same verified private RC41 Web build, the native
Link `create_server` with isolated disposable Core root and `127.0.0.1` port 0
served `index.html`, `app.js`, `styles.css` and `foundation.css` with HTTP 200
and exact local bytes: **4/4 loopback static-route checks PASS**. No real
login, credential, Agent, Browser, second user, live test host, publisher or
installed public product release was involved. The default public Link package
lock remains at pf8.4.

## Reproducible private RC41 Link Web installable bundle

To package the complete Link Web source with the **exact ten privately
reproduced RC41 npm archives**, use the Link-owned source-only builder.
It requires normal authenticated access to the immutable Foundation source
and matching 10 independent archive hashes; it does not use the previously
platform-denied cross-host transfer or publish any package. The private
packaging directory must be a mode-0700 root *outside* the public Link repo.

```bash
cd /home/aella/datarelay-link-worktrees/drl3-foundation-rc41-consumer-20261013
python3 tools/build-private-link-foundation-rc41-web.py \
  --private-source-checkout "$HOME/.cache/drlink-foundation-rc41/private-source" \
  --verified-package-dir "$HOME/.cache/drlink-foundation-rc41/packs-normalized" \
  --source-package-manifest "$HOME/.cache/drlink-foundation-rc41/stage-normalized/release-manifest.json" \
  --private-root "$HOME/.cache/drlink-foundation-rc41" \
  --output-dir "$HOME/.cache/drlink-foundation-rc41/installable-web-candidate"
```

The builder selects the **clean exact Link Git HEAD**, exports it to a
private temporary tree, applies only the independently SHA256-pinned RC41
Foundation archives/lock, installs offline with npm scripts disabled, runs
the production build and the existing Administration/Journey/P0 source suites,
then creates the native `data-relay-link-web.tar.gz` package twice and
compares SHA256. The package verifier checks all 10 nested npm archive
bytes and required static assets. Finally, `install-web.sh` is executed in
an **isolated disposable** fake Core root with a SQLite existence fixture
and `DRLINK_WEB_INSTALL_SKIP_SYSTEMD=1`. It validates installed asset
hashes and the explicit Link source and bundle hash marker. The stub is NOT
a real installed customer Core or authenticated product E2E.

Only after every gate succeeds does the builder put one private candidate
`data-relay-link-web-foundation-rc41-<linkhead>.private.tar.gz` and its
`private-build-receipt.json` into the mode-0700 output directory. The
bundle **contains private RC41 npm package bytes**; never commit, upload to
a public Link PR or CI artifact, distribute to customers, or treat as a
signed/published release. Source-level npm tests and private install tests
are not owner acceptance, signed distribution or full User E2E.

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

## RC41 private development preview (2026-10-13)

The owner-approved isolated RC41 Web is also served by the **actual Link Web
server** on `dev-drlink`, not by a synthetic Storybook rendering.

- Last directly observed endpoint: `http://127.0.0.1:19041` on dev-drlink
  (loopback only, **not** an external URL or an installed live product).
- Private Web assets:
  `$HOME/.cache/drlink-foundation-rc41/consumer-web-rc41/dist`.
- Link Core root:
  `$HOME/.cache/drlink-foundation-rc41/preview-root`, isolated from live
  Core; both source/packages and preview state remain under the owner-only
  mode-0700 private parent.
- Link HEAD at preview validation: `97832f378fbe78b32d0d5375c5466e623c9adc6a`.
  Foundation package family `0.1.0-rc.41`, original Foundation source
  `46ddb60cad8eae7b1718588cd19421e61b5300e7`.
- HTTP GET `/index.html`, `/app.js`, `/styles.css`,
  `/foundation.css` returned HTTP 200 and byte-identical local SHA256
  **4/4 PASS**. Anonymous request to `/api/v1/system/status` was **401**;
  no session or privileged user identity was provisioned or exercised.
- This is a currently observed development **process**, not a durable
  systemd service, external TLS endpoint, authenticated Browser PASS, or
  installed Server/Agent product release.

To launch the same local-only private preview using the previously
verified RC41 assets, after confirming the port is unused:

```bash
cd /home/aella/datarelay-link-worktrees/drl3-foundation-rc41-consumer-20261013
install -d -m 700 "$HOME/.cache/drlink-foundation-rc41/preview-root"
PYTHONPATH="$PWD/lib" DRLINK_WEB_QUIET=1 DRLINK_SKIP_ACTIVATION=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  python3 server/drlink-web.py --listen 127.0.0.1 --port 19041 \
    --root "$HOME/.cache/drlink-foundation-rc41/preview-root" \
    --static-root "$HOME/.cache/drlink-foundation-rc41/consumer-web-rc41/dist"
```

Do not forward this preview publicly, use a live Core root, invent login
credentials, or assert User E2E from unauthenticated static file checks.
The public Link `pf8.4` fallback, draft PR and release approval remain
unchanged.

## Private RC41 installed development candidate activation

The private RC41 Web installer and localhost smoke checks are already
qualified. The **product-owned** selector keeps the selected *development*
candidate under the existing 0700 private namespace while rechecking all
source/package/install evidence. It does **not** modify the public Link
`web/package.json`, invoke a live Core operation, install a systemd unit,
publish packages or qualify a customer release.

```bash
cd /home/aella/datarelay-link-worktrees/drl3-foundation-rc41-consumer-20261013
root="$HOME/.cache/drlink-foundation-rc41"
# Read-only check first:
python3 tools/activate-private-link-foundation-rc41.py \
  --private-root "$root" \
  --candidate "$root/dev-installed-f18fd471" \
  --receipt "$root/installable-link-rc41-f18fd471/private-build-receipt.json"

# Only on explicitly approved private DEVELOPMENT promotion:
python3 tools/activate-private-link-foundation-rc41.py \
  --private-root "$root" \
  --candidate "$root/dev-installed-f18fd471" \
  --receipt "$root/installable-link-rc41-f18fd471/private-build-receipt.json" \
  --activate --expected-active-name dev-installed-f18fd471
```

The selector verifies the original immutable Foundation SHA `46ddb60`,
the source-locked private receipt, whole Web archive SHA256, all ten
private npm TAR SHA256 values, all five installed runtime asset digests,
and the installed `build.json` link/bundle identity. It rejects symlink
escape, world-readable private roots, missing archives, tampering, unknown
versions and forged publisher/E2E claims. Activation of a **different**
private candidate requires the explicitly observed previous active name;
the value is rechecked before an atomic symlink replacement. This does not
claim protection against uncoordinated concurrent external pointer changes.
Nothing alters the public product or starts external services.

On 2026-10-13 the exact private installed RC41
`dev-installed-f18fd471` was reverified and selected idempotently:
`PRIVATE_RC41_DEV_ACTIVATION=PASS`, all 10 private npm archives verified,
5 installed static assets verified, active pointer unchanged and
development loopback `127.0.0.1:19042` still bound. The new
`tests/test-link-foundation-rc41-activation.py` uses synthetic files
only and is included in `tests/run-all.sh`.

### Public default promotion is separate

The **public** Link `pf8.4` family and existing CI must stay reproducible
until a *legitimate* publisher path has made the requested immutable
Foundation version available to every builder. Real checks found no Link
repository-level Actions secrets, GitHub Packages API `403` for missing
`read:packages`, and an unauthenticated npm registry `E401`. The
Foundation publisher requires a default-branch SHA match; its observed
default SHA is not original RC41 `46ddb60`. Existing source/migration
approval does **not** replace credentials, legal distribution approval,
publisher provenance, two-real-user tests or the final merge/release gate.

Do not downgrade those checks or commit private RC41 package bytes to the
public Link repository to simulate completion. Qualified development
installation is **done**, public default and official release remain
**NOT QUALIFIED** until the technical/authority gates really pass.
