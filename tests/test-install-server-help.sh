#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for arg in --help -h; do
  out="$("$ROOT/install-server.sh" "$arg")"
  grep -q '^Usage:' <<<"$out"
  grep -q -- '--upgrade' <<<"$out"
  grep -q -- '--help' <<<"$out"
done

echo 'PASS: install-server help exits before installer actions'
