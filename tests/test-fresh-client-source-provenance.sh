#!/usr/bin/env bash
# A generated-only candidate must retain its identity without rewriting its
# embedded content-parent manifest. Exercise the real verifier and version writer.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
. "$ROOT/lib/frp-common.sh"
. "$ROOT/lib/frp-client-common.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export FRP_CLIENT_TEST_ROOT="$WORK/root"
export ALLOCATOR_URL=https://owned.test
export FRP_INSTALLER_URL="$ALLOCATOR_URL/artifacts/agent/bootstrap-client.sh"
export FRP_BUNDLE_FILE="$WORK/bootstrap-client.sh"
candidate=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
content=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
printf 'immutable bundle with embedded content parent %s\n' "$content" >"$FRP_BUNDLE_FILE"
digest="$(sha256sum "$FRP_BUNDLE_FILE" | cut -d' ' -f1)"
mkdir -p "$WORK/source"
printf 'PROJECT_VERSION=2.4.0\n' >"$WORK/source/VERSION"
printf '{"source_head":"%s","git_ref":"%s","channel":"development"}\n' "$content" "$content" >"$WORK/source/release-manifest.json"
# Reproduce the old fallback: it records the embedded content parent, not the
# qualified outer candidate. Then run the new fresh verifier from clean inputs.
frp_infer_expected_source_from_release_manifest "$WORK/source"
[[ "$FRP_EXPECTED_SOURCE_HEAD" == "$content" ]]
unset FRP_EXPECTED_SOURCE_REF FRP_EXPECTED_SOURCE_HEAD
python3 - "$WORK" "$candidate" "$digest" <<'PY'
import json, sys
from pathlib import Path
root, candidate, digest = sys.argv[1:]
Path(root, 'manifest.json').write_text(json.dumps(dict(
    qualification_status='PASS', channel='development', immutable_source_ref=candidate,
    artifacts=[dict(relative_path='agent/bootstrap-client.sh', source_head=candidate, sha256=digest)])))
Path(root, 'SHA256SUMS').write_text(digest + '  agent/bootstrap-client.sh\n')
PY
frp_allocator_ca_path() { printf '%s/ca.crt\n' "$WORK"; }
# Transport fixture only; parsing, artifact verification and persistence stay real.
curl() {
  local url='' output=''
  while (($#)); do
    case "$1" in
      -o) output="$2"; shift 2;;
      https://*) url="$1"; shift;;
      *) shift;;
    esac
  done
  cp "$WORK/${url##*/}" "$output"
}
frp_client_verify_fresh_source_provenance
[[ "$FRP_EXPECTED_SOURCE_REF" == "$candidate" ]]
[[ "$FRP_EXPECTED_SOURCE_HEAD" == "$candidate" ]]
[[ "$FRP_BUNDLE_SHA256" == "$digest" ]]
mkdir -p "$WORK/version"
frp_write_version_file "$WORK/version/installed-version" client 2.4.0 0.71.0
grep -q "SOURCE_HEAD=$candidate" "$WORK/version/installed-version"
grep -q "$content" "$WORK/source/release-manifest.json"
export FRP_EXPECTED_RELEASE_CHANNEL=stable
if frp_client_verify_fresh_source_provenance; then
  echo 'FAIL: requested channel mismatch accepted' >&2; exit 1
fi
export FRP_EXPECTED_RELEASE_CHANNEL=development
printf 'tamper\n' >>"$FRP_BUNDLE_FILE"
if frp_client_verify_fresh_source_provenance; then
  echo 'FAIL: changed outer bundle accepted' >&2; exit 1
fi
grep -q "SOURCE_HEAD=$candidate" "$WORK/version/installed-version"
printf 'PASS fresh candidate identity and tampered bundle refusal\n'
