#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ALL="$ROOT/tests/run-all.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

good="$TMP/first valid.sh"
bad="$TMP/later invalid.sh"
printf '#!/usr/bin/env bash\necho ok\n' > "$good"
printf '#!/usr/bin/env bash\nif then\n' > "$bad"

# bash only parses the first script argument, so batching filenames is unsafe.
bash -n "$good" "$bad" >/dev/null 2>&1

if printf '%s\0' "$good" "$bad" | xargs -0 -r -n 1 bash -n -- >/dev/null 2>&1; then
  echo 'FAIL: per-file shell syntax enumeration did not detect a later invalid script' >&2
  exit 1
fi

grep -Fq "git ls-files -z '*.sh' | xargs -0 -r -n 1 bash -n --" "$RUN_ALL"
grep -Fq "git ls-files -z -o --exclude-standard '*.sh' | xargs -0 -r -n 1 bash -n --" "$RUN_ALL"
if grep -Fq "git ls-files '*.sh' | xargs -r bash -n" "$RUN_ALL"; then
  echo 'FAIL: unsafe batched tracked-shell syntax check remains' >&2
  exit 1
fi

echo 'SHELL_SYNTAX_ENUMERATION=PASS'
