#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/build-bundles.py
python3 scripts/build-web-bundle.py
