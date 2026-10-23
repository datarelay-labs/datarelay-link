#!/usr/bin/env bash
# A staged upgrade must include modules added by its candidate, even when the
# invoking installed helper has an older payload catalog.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/candidate/lib" "$WORK/staged"
# Candidate metadata adds a future runtime file absent from this helper's list.
cp "$ROOT/lib/drlink_agent_payload.py" "$WORK/candidate/lib/"
printf '\nAGENT_LIB_FILES += ("future_candidate_only.py",)\n' >> "$WORK/candidate/lib/drlink_agent_payload.py"
printf 'candidate payload\n' > "$WORK/candidate/lib/future_candidate_only.py"
source "$ROOT/lib/frp-client-common.sh"
# Materialize candidate source inputs through the current public destination
# contract, then add the genuinely new candidate-only file above.
while IFS=: read -r rel mode src; do
  [[ "$src" == lib/drlink_agent_payload.py ]] && continue
  mkdir -p "$WORK/candidate/$(dirname "$src")"
  cp "$ROOT/$src" "$WORK/candidate/$src"
done < <(frp_client_upgrade_destinations)
frp_client_upgrade_stage "$WORK/candidate" "$WORK/staged"
test -f "$WORK/staged/usr/local/lib/drlink/future_candidate_only.py"
cmp "$WORK/candidate/lib/future_candidate_only.py" "$WORK/staged/usr/local/lib/drlink/future_candidate_only.py"
echo CANDIDATE_PAYLOAD_STAGE=PASS
