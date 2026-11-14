#!/usr/bin/env bash
# F-004 regression: the guided manual enrollment wizard must reject an invalid
# Lifetime before the Review/Create step (like the bulk wizard), not only after
# the operator has confirmed and the backend refuses the value.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTL="$ROOT/tools/frpctl"

fn_src="$(awk '/^frpctl_guided_manual_enrollment\(\) \{/{p=1} p{print} p&&/^}/{exit}' "$CTL")"
[[ -n "$fn_src" ]] || { echo "FAIL could not extract frpctl_guided_manual_enrollment" >&2; exit 1; }

run_case() {
  # $1 = lifetime answer; remaining prompts answered with defaults.
  local life="$1"
  (
    set +e
    # frpctl_read runs in a command substitution, so answer by prompt text.
    frpctl_read() {
      case "$1" in
        Lifetime*) printf '%s' "$life" ;;
        *) printf '%s' "$2" ;;
      esac
    }
    frpctl_run() { echo "RUN $*"; }
    eval "$fn_src"
    frpctl_guided_manual_enrollment 2>&1
    echo "RC=$?"
  )
}

out="$(run_case zzz)"
if grep -q '^RUN ' <<<"$out"; then
  echo "FAIL invalid lifetime 'zzz' reached Create" >&2; echo "$out" >&2; exit 1
fi
grep -q 'Review' <<<"$out" && { echo "FAIL invalid lifetime shown at Review" >&2; echo "$out" >&2; exit 1; }
grep -qi 'lifetime' <<<"$out" || { echo "FAIL no lifetime error message" >&2; echo "$out" >&2; exit 1; }
grep -q '^RC=[1-9]' <<<"$out" || { echo "FAIL expected non-zero exit for invalid lifetime" >&2; echo "$out" >&2; exit 1; }
echo "PASS invalid lifetime rejected before Review"

for ok in 30m 1h 4h 1d 90s; do
  out="$(run_case "$ok")"
  grep -q "^RUN .*--ttl $ok" <<<"$out" || { echo "FAIL valid lifetime '$ok' not passed to create" >&2; echo "$out" >&2; exit 1; }
done
echo "PASS valid lifetimes still accepted"
