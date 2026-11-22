#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FRP_TEST_UNAME_S=Darwin FRP_TEST_UNAME_M=arm64
export FRP_CLIENT_SOURCED=1
. "$ROOT/install-client.sh"

export FRP_ALLOCATOR_URL='https://example.test/enroll'
export FRP_ALLOCATOR_CA_SHA256="$(printf 'a%.0s' {1..64})"
export FRP_BOOTSTRAP_TICKET="bt1.$(printf 'b%.0s' {1..16}).$(printf 'c%.0s' {1..64})"
export FRP_ZERO_TOUCH=1
frp_zero_touch_require_inputs
[[ "$FRP_ALLOCATOR_URL" == https://example.test/enroll ]]
frp_detect_arch
[[ "$FRP_ARCH" == arm64 ]]
echo "MACOS_ZERO_TOUCH_COMMAND_TEST=PASS"
