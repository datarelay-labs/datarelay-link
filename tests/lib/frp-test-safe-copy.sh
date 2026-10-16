#!/usr/bin/env bash
# Safe repository tree copy helpers for tests.
# Prevents recursive self-copy / full-filesystem copy when ROOT is empty or "/".

frp_test_require_repo_root() {
  local root="${1:-}"
  if [[ -z "$root" || "$root" == "/" ]]; then
    echo "FAIL: unsafe or empty repo root: '${root}'" >&2
    return 1
  fi
  if [[ ! -f "$root/release-manifest.json" ]]; then
    echo "FAIL: not a Data Relay Link repo root (missing release-manifest.json): $root" >&2
    return 1
  fi
  return 0
}

# Copy repo tree into dest. Rejects unsafe roots and destination-inside-source.
frp_test_copy_repo_tree() {
  local root="${1:?root required}"
  local dest="${2:?dest required}"
  frp_test_require_repo_root "$root" || return 1

  local root_abs dest_abs
  root_abs="$(cd "$root" && pwd)" || return 1
  mkdir -p "$dest" || return 1
  dest_abs="$(cd "$dest" && pwd)" || return 1

  case "$dest_abs" in
    "$root_abs"|"$root_abs"/*)
      echo "FAIL: destination is inside source (recursive self-copy risk): $dest_abs ⊆ $root_abs" >&2
      return 1
      ;;
  esac
  case "$root_abs" in
    "$dest_abs"/*)
      echo "FAIL: source is inside destination: $root_abs ⊆ $dest_abs" >&2
      return 1
      ;;
  esac

  # Bound the copy before reading: repository metadata, generated dist and
  # local audit evidence (which may contain protected runtime files) are not
  # source inputs to an isolated update fixture.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude '.git' --exclude 'dist' --exclude '/e2e-reports' "$root_abs"/ "$dest_abs"/ || return 1
  else
    (
      set -o pipefail
      tar -C "$root_abs" --exclude='./.git' --exclude='./dist' --exclude='./e2e-reports' -cf - . |
        tar -C "$dest_abs" -xf -
    ) || return 1
  fi
  return 0
}
