#!/usr/bin/env bash
# Generated prefix. For stdin, spool the complete remaining body with buffered
# I/O; never feed the large base64 here-documents to the streaming Bash parser.
if [[ -z "${BASH_SOURCE[0]:-}" ]]; then
  set -euo pipefail
  # Capture the original curl source ref while that process still exists.
  @SOURCE_REF_SNIPPET@
  _drlink_stream_dir="$(mktemp -d)"
  _drlink_stream_pid=""
  _drlink_stream_cleanup() {
    local rc=$?
    trap - EXIT
    if [[ -n "$_drlink_stream_pid" ]]; then
      kill "$_drlink_stream_pid" 2>/dev/null || true
      wait "$_drlink_stream_pid" 2>/dev/null || true
    fi
    rm -rf -- "$_drlink_stream_dir"
    exit "$rc"
  }
  trap _drlink_stream_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  echo "Downloading qualified Data Relay Link installer (@BODY_SIZE@ bytes)..."
  _drlink_stream_parent="$BASHPID"
  (
    while sleep 5; do
      kill -0 "$_drlink_stream_parent" 2>/dev/null || exit 0
      echo "  Download in progress: $(wc -c < "$_drlink_stream_dir/body.sh" 2>/dev/null || echo 0) / @BODY_SIZE@ bytes" >&2
    done
  ) </dev/null &
  _drlink_stream_pid=$!
  if ! cat > "$_drlink_stream_dir/body.sh"; then
    echo "ERROR: Installer download or staging failed. Installation has not started." >&2
    exit 1
  fi
  kill "$_drlink_stream_pid" 2>/dev/null || true
  wait "$_drlink_stream_pid" 2>/dev/null || true
  _drlink_stream_pid=""
  echo "Download complete. Verifying installer payload..."
  if ! printf '%s  %s\n' '@BODY_SHA256@' "$_drlink_stream_dir/body.sh" | sha256sum --check --status; then
    echo "ERROR: Incomplete or corrupt installer payload. Installation has not started. Retry the same command." >&2
    exit 1
  fi
  echo "Installer payload verified. Restoring installation files..."
  # Keep the prior stdin/TTY contract and forward every installer argument.
  bash "$_drlink_stream_dir/body.sh" "$@"
  exit $?
fi
