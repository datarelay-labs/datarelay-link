#!/usr/bin/env bash
# Fast deterministic PR gate. Full run-all.sh remains stable-candidate/release qualification.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1

echo "=== shell syntax ==="
git ls-files '*.sh' | xargs -r bash -n

echo "=== Python compile ==="
git ls-files '*.py' -z | xargs -0 -r python3 -m py_compile

echo "=== version and release governance ==="
./scripts/check-version-consistency.sh
./tests/test-version-governance.sh

echo "=== public CLI / contract regressions ==="
./tests/test-cli-catalog-parity.sh
python3 tests/test-public-cli-grammar-parity.py
python3 tests/test-cli-feature-scenario-remediation.py
python3 tests/test-no-legacy-current-surface.py
python3 tests/test-canonical-runtime-policy.py
python3 tests/test-v24-final-closure.py
python3 tests/test-v24-doc-consistency.py
python3 tests/test-v24-cli-ai-master-closure.py
python3 tests/test-v24-cli-workflow-semantic-parity.py

echo "=== derived artifact closure ==="
bash tests/test-change-closure-artifacts.sh

echo "=== repository safety ==="
./scripts/secret-scan.sh
./scripts/check-public-metadata.sh
git diff --check HEAD

echo "FAST_PR=PASS"

