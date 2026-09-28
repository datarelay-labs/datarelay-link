#!/usr/bin/env bash
# One Full Real E2E release pass. The Engineering System contract invokes this
# twice (full_e2e_passes: 2): the first call is PASS1 and the second is PASS2.
# Both calls must observe the same Git HEAD. Terminal evidence is retained and
# cryptographically bound into qualification-evidence.json.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/require-release-target.sh
source "$ROOT/tests/lib/require-release-target.sh"
frp_require_release_target

HEAD="$(git -C "$ROOT" rev-parse HEAD)"
STATE_DIR="$ROOT/e2e-reports/release-qualification"
STATE="$STATE_DIR/state.env"
PASS1_OUT="$STATE_DIR/pass1"
PASS2_OUT="$STATE_DIR/pass2"
EVIDENCE="$STATE_DIR/qualification-evidence.json"
mkdir -p "$STATE_DIR"

validate_summary_file() {
  local pass_name="$1" summary="$2" expected_head="$3"
  python3 - "$summary" "$pass_name" "$expected_head" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

path, pass_name, head = Path(sys.argv[1]), sys.argv[2], sys.argv[3].lower()
if not path.is_file():
    raise SystemExit("ERROR: missing terminal qualification summary %s" % path)
raw = path.read_bytes()
doc = json.loads(raw)
if not isinstance(doc, dict):
    raise SystemExit("ERROR: qualification summary must be a JSON object")
if doc.get("schema_version") != 1:
    raise SystemExit("ERROR: qualification summary schema_version must be 1")
if doc.get("pass_name") != pass_name:
    raise SystemExit("ERROR: qualification summary pass_name mismatch")
if str(doc.get("git_head") or "").lower() != head:
    raise SystemExit("ERROR: qualification summary git_head mismatch")
if doc.get("final_status") != "PASS":
    raise SystemExit("ERROR: qualification summary final_status must be PASS")
gates = doc.get("gates")
if not isinstance(gates, dict):
    raise SystemExit("ERROR: qualification summary gates must be an object")
required = {
    "FROZEN_HEAD": head,
    pass_name + "_HEAD": head,
    "END_HEAD": head,
    "HEAD_UNCHANGED": "YES",
    pass_name: "PASS",
}
for key, want in required.items():
    got = str(gates.get(key) or "")
    if got.lower() != want.lower():
        raise SystemExit("ERROR: qualification summary %s=%s, expected %s" % (key, got or "<missing>", want))
ssh_exception = re.compile(r"^(UBUNTU|ROCKY|AWS_LINUX|WINDOWS|MACOS|UBUNTU24)_SSH$")
for key, value in gates.items():
    if str(value) in {"FAIL", "BLOCKED", "NOT_RUN"} and not ssh_exception.fullmatch(str(key)):
        raise SystemExit("ERROR: terminal blocking gate %s=%s" % (key, value))
paths = doc.get("evidence_paths")
if not isinstance(paths, dict) or paths.get("summary.txt") is not True or paths.get("matrix.log") is not True:
    raise SystemExit("ERROR: qualification summary must retain summary.txt and matrix.log")
print(hashlib.sha256(raw).hexdigest())
PY
}

if [[ ! -f "$STATE" ]]; then
  # Advance to PASS2 only after PASS1 has completed successfully and terminal
  # summary evidence has been validated on the exact unchanged HEAD.
  rm -rf "$PASS1_OUT" "$PASS2_OUT"
  rm -f "$EVIDENCE"
  if ! FRP_E2E_QUAL_OUT="$PASS1_OUT"       bash "$ROOT/tests/run-production-realistic-qualification.sh" PASS1; then
    rm -f "$STATE"
    exit 1
  fi
  now="$(git -C "$ROOT" rev-parse HEAD)"
  if [[ "$now" != "$HEAD" ]]; then
    echo "ERROR: PASS1 changed HEAD from $HEAD to $now" >&2
    rm -f "$STATE"
    exit 1
  fi
  pass1_sha="$(validate_summary_file PASS1 "$PASS1_OUT/summary.json" "$HEAD")" || {
    rm -f "$STATE"
    exit 1
  }
  state_tmp="${STATE}.tmp.$$"
  {
    printf 'QUALIFIED_HEAD=%s\n' "$HEAD"
    printf 'NEXT=PASS2\n'
    printf 'PASS1_SUMMARY_SHA256=%s\n' "$pass1_sha"
  } >"$state_tmp"
  mv "$state_tmp" "$STATE"
  echo "PASS1_HEAD=$HEAD"
  echo "PASS1_SUMMARY_SHA256=$pass1_sha"
  exit 0
fi

# shellcheck disable=SC1090
source "$STATE"
if [[ "${QUALIFIED_HEAD:-}" != "$HEAD" ]]; then
  echo "ERROR: PASS2 HEAD $HEAD != PASS1_HEAD ${QUALIFIED_HEAD:-}" >&2
  exit 1
fi
if [[ "${NEXT:-}" != "PASS2" ]]; then
  echo "ERROR: qualification for $HEAD is already recorded; do not add a commit and reuse it" >&2
  exit 1
fi

# PASS2 may proceed only if retained PASS1 terminal evidence is still intact.
pass1_sha="$(validate_summary_file PASS1 "$PASS1_OUT/summary.json" "$HEAD")" || exit 1
if [[ "$pass1_sha" != "${PASS1_SUMMARY_SHA256:-}" ]]; then
  echo "ERROR: retained PASS1 summary digest changed" >&2
  exit 1
fi

rm -rf "$PASS2_OUT"
if ! FRP_E2E_QUAL_OUT="$PASS2_OUT"     bash "$ROOT/tests/run-production-realistic-qualification.sh" PASS2; then
  exit 1
fi
now="$(git -C "$ROOT" rev-parse HEAD)"
if [[ "$now" != "$HEAD" ]]; then
  echo "ERROR: PASS2 changed HEAD from $HEAD to $now" >&2
  exit 1
fi
pass2_sha="$(validate_summary_file PASS2 "$PASS2_OUT/summary.json" "$HEAD")" || exit 1

evidence_tmp="${EVIDENCE}.tmp.$$"
python3 - "$PASS1_OUT/summary.json" "$PASS2_OUT/summary.json" "$HEAD"   "$pass1_sha" "$pass2_sha" "$evidence_tmp" <<'PY'
import json
import sys
from pathlib import Path

pass1_path, pass2_path = Path(sys.argv[1]), Path(sys.argv[2])
head, pass1_sha, pass2_sha, out = sys.argv[3], sys.argv[4], sys.argv[5], Path(sys.argv[6])
doc = {
    "schema_version": 1,
    "status": "PASS",
    "pass1_head": head,
    "pass2_head": head,
    "final_qualified_head": head,
    "pass1_summary_sha256": pass1_sha,
    "pass2_summary_sha256": pass2_sha,
    "pass1_summary": json.loads(pass1_path.read_text(encoding="utf-8")),
    "pass2_summary": json.loads(pass2_path.read_text(encoding="utf-8")),
}
out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
mv "$evidence_tmp" "$EVIDENCE"

"$ROOT/scripts/check-release-qualification-evidence.py"   --root "$ROOT" --evidence "$EVIDENCE" >/tmp/drlink-qualification-evidence-check.$$
cat /tmp/drlink-qualification-evidence-check.$$
evidence_sha="$(sha256sum "$EVIDENCE" | awk '{print $1}')"
rm -f /tmp/drlink-qualification-evidence-check.$$

{
  printf 'QUALIFIED_HEAD=%s\n' "$HEAD"
  printf 'NEXT=DONE\n'
  printf 'PASS1_SUMMARY_SHA256=%s\n' "$pass1_sha"
  printf 'PASS2_SUMMARY_SHA256=%s\n' "$pass2_sha"
  printf 'QUALIFICATION_EVIDENCE_SHA256=%s\n' "$evidence_sha"
} >"$STATE"

echo "PASS1_HEAD=$HEAD"
echo "PASS2_HEAD=$HEAD"
echo "FINAL_QUALIFIED_HEAD=$HEAD"
echo "QUALIFICATION_EVIDENCE=$EVIDENCE"
echo "QUALIFICATION_EVIDENCE_SHA256=$evidence_sha"
