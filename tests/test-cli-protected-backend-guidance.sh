#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$EUID" -eq 0 ]]; then
  echo 'SKIP: protected-backend guidance requires an unprivileged caller'
  exit 0
fi
work="$(mktemp -d)"
backend_dir="$work/root/usr/local/lib/drlink"
trap 'chmod -R u+rwX "$work"; rm -rf "$work"' EXIT
mkdir -p "$work/bin" "$backend_dir"
cp "$ROOT/tools/drlink" "$work/bin/drlink"
printf '#!/usr/bin/env bash\necho BACKEND_RAN\n' >"$backend_dir/frpctl"
for fault in directory file; do
  chmod 700 "$backend_dir"
  chmod 600 "$backend_dir/frpctl"
  if [[ "$fault" == directory ]]; then chmod 000 "$backend_dir"; else chmod 000 "$backend_dir/frpctl"; fi
  if FRP_CTL_TEST_ROOT="$work/root" bash "$work/bin/drlink" help commands >"$work/$fault.out" 2>&1; then
    echo "FAIL: protected backend executed ($fault)" >&2; exit 1
  fi
  grep -q 'sudo drlink' "$work/$fault.out"
  if grep -qE 'backend is missing|BACKEND_RAN' "$work/$fault.out"; then
    echo "FAIL: wrong protected-backend diagnosis ($fault)" >&2; exit 1
  fi
done
chmod 700 "$backend_dir"
chmod 600 "$backend_dir/frpctl"
FRP_CTL_TEST_ROOT="$work/root" bash "$work/bin/drlink" help commands >"$work/readable.out" 2>&1
grep -q 'BACKEND_RAN' "$work/readable.out"
rm "$backend_dir/frpctl"
if FRP_CTL_TEST_ROOT="$work/root" bash "$work/bin/drlink" help commands >"$work/missing.out" 2>&1; then
  echo 'FAIL: missing selected-root backend fell through to another installation' >&2; exit 1
fi
grep -q 'backend is missing' "$work/missing.out"
echo 'PASS protected-backend administrator guidance'
