#!/usr/bin/env bash
# Exact-HEAD derived artifact closure for ordinary development/PR validation.
# This verifier never refreshes tracked release metadata in the caller worktree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL $1" >&2
  exit 1
}

HEAD_COMMIT="$(git rev-parse HEAD)"
TMP="$(mktemp -d)"
WT="$TMP/repo"

cleanup() {
  git worktree remove --force "$WT" >/dev/null 2>&1 || true
  rm -rf "$TMP"
}
trap cleanup EXIT

git worktree add --detach "$WT" "$HEAD_COMMIT" >/dev/null
cd "$WT"

python3 scripts/build-bundles.py >/dev/null
if ! git diff --exit-code --   dist/bootstrap-server.sh   dist/bootstrap-client.sh   dist/bootstrap-client.ps1 >/dev/null; then
  fail "DERIVED_BUNDLE_STALE: regenerate bundles during implementation"
fi
echo "PASS DERIVED_BUNDLE_PARITY"

bash scripts/verify-sha256sums.sh >/dev/null ||
  fail "SHA256SUMS_STALE: run scripts/update-sha256sums.sh during implementation"
echo "PASS SHA256SUMS_PARITY"

python3 scripts/sync-release-manifest-provenance.py --check >/dev/null ||
  fail "RELEASE_MANIFEST_PROVENANCE_STALE"
echo "PASS RELEASE_MANIFEST_PROVENANCE"

bash tests/test-release-artifact-ordering.sh >/dev/null ||
  fail "RELEASE_ARTIFACT_ORDERING"
echo "PASS RELEASE_ARTIFACT_ORDERING"

echo "DRLINK_DERIVED_ARTIFACT_INTEGRITY=PASS"

