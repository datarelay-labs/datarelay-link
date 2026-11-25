#!/usr/bin/env bash
# Generated distribution entry is small. The entire function must arrive
# before its invocation, so a truncated initial response cannot install.
drlink_online_install() (
  set -euo pipefail
  umask 077
  fail() { printf 'ERROR: %s\nNo installation was started. Retry the same command.\n' "$*" >&2; exit 1; }
  ref="${1:-}"
  [[ "$ref" =~ ^([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?)$ ]] ||
    fail 'Pass the exact immutable Git SHA or release tag as the first argument.'
  shift
  [[ -z "${FRP_EXPECTED_SOURCE_REF:-}" || "$FRP_EXPECTED_SOURCE_REF" == "$ref" ]] ||
    fail 'Requested source ref conflicts with the existing expected source ref.'
  [[ "$(uname -s)" == Linux ]] || fail 'Data Relay Link Server requires Linux.'
  case "$(uname -m)" in
    x86_64|amd64) native=linux_amd64.tar.gz ;;
    aarch64|arm64) native=linux_arm64.tar.gz ;;
    *) fail 'Unsupported Linux CPU architecture.' ;;
  esac
  for cmd in curl tar base64 sha256sum mktemp cat; do
    command -v "$cmd" >/dev/null || fail "Required command not found: $cmd"
  done
  [[ "${EUID}" == 0 || -n "${FRP_SERVER_TEST_ROOT:-}" ]] || fail 'Run the online installer with sudo.'
  work="$(mktemp -d)" || fail 'Cannot create private staging directory.'
  trap 'rm -rf -- "$work"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  base="https://raw.githubusercontent.com/datarelay-labs/datarelay-link/$ref"
  fetch() {
    local rel="$1" digest="$2" size="$3" dest="$4"
    printf '\nDownloading %s (%s bytes)...\n' "${rel##*/}" "$size" >&2
    if ! curl --disable --fail --location --show-error --progress-bar \
      --proto '=https' --proto-redir '=https' --connect-timeout 10 \
      --max-time 300 --retry 2 --retry-max-time 600 \
      --speed-limit 1024 --speed-time 30 --max-filesize "$size" \
      --output "$dest" "$base/$rel"; then
      fail "Download failed or timed out: $rel"
    fi
    printf 'Verifying %s...\n' "${rel##*/}" >&2
    printf '%s  %s\n' "$digest" "$dest" | sha256sum --check --status ||
      fail "SHA256 mismatch: $rel"
  }
  rows=(
@BINARY_ROWS@
  )
  echo "Data Relay Link Server online installation: $(uname -m), $ref"
  fetch 'dist/bootstrap-server-core.tar' '@CORE_SHA256@' '@CORE_SIZE@' "$work/core.tar"
  mkdir "$work/core"
  tar -xf "$work/core.tar" -C "$work/core" || fail 'Core extraction failed.'
  # Native FRP first. The other three archives are required by the existing
  # Server-local Agent distribution contract, not by the Server CPU.
  for phase in native agent; do
    for row in "${rows[@]}"; do
      IFS='|' read -r rel digest size <<< "$row"
      if [[ "$phase" == native ]]; then
        [[ "$rel" == *"$native" ]] || continue
      else
        [[ "$rel" != *"$native" ]] || continue
      fi
      fetch "$rel" "$digest" "$size" "$work/${rel##*/}"
    done
  done
  echo 'Reconstructing and verifying the qualified offline installer...'
  bundle="$work/bootstrap-server.sh"
  {
    index=0
    for row in "${rows[@]}"; do
      IFS='|' read -r rel digest size <<< "$row"
      cat "$work/core/part-$index"
      base64 --wrap=76 "$work/${rel##*/}"
      index=$((index + 1))
    done
    cat "$work/core/part-$index"
  } >"$bundle" || fail 'Installer reconstruction failed.'
  printf '%s  %s\n' '@BUNDLE_SHA256@' "$bundle" | sha256sum --check --status ||
    fail 'Reconstructed installer differs from the qualified offline bundle.'
  echo 'Installer verified. Starting installation...'
  export FRP_EXPECTED_SOURCE_REF="$ref"
  export FRP_BUNDLE_SHA256='@BUNDLE_SHA256@'
  bash "$bundle" "$@"
)
drlink_online_install "$@"
