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

# Development bundles embed immutable provenance from the last committed
# source snapshot. Rebuilding them at HEAD changes only self-referential
# provenance when HEAD itself is the artifact-refresh commit. Verify payload
# parity with provenance normalized to the committed manifest instead.
COMMITTED_MANIFEST="$(mktemp)"
cp release-manifest.json "$COMMITTED_MANIFEST"
python3 scripts/build-bundles.py >/dev/null
python3 - "$COMMITTED_MANIFEST" release-manifest.json <<'PY2'
import json, sys
from pathlib import Path
committed = json.loads(Path(sys.argv[1]).read_text())
current = json.loads(Path(sys.argv[2]).read_text())
for key in ("git_ref", "source_head", "immutable_source_ref"):
    if key in committed:
        current[key] = committed[key]
Path(sys.argv[2]).write_text(json.dumps(current, indent=2, sort_keys=False) + "\n")
PY2
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
