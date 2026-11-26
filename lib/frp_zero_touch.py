#!/usr/bin/env python3
"""Current Zero-Touch short-command helpers with direct bootstrap environment.

Legacy opaque package issuance and decoding are intentionally unsupported.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import secrets
import shlex
from urllib.parse import urlparse

BOOTSTRAP_TICKET_RE = re.compile(
    r'^bt1\.[0-9a-f]{16}\.[0-9a-f]{64}$',
    re.IGNORECASE,
)
# 128-bit CSPRNG capability, unpadded base64url. Must match allocator parsing.
COMPACT_CREDENTIAL_RE = re.compile(r'^[A-Za-z0-9_-]{22}$')
DNS_HOSTNAME_RE = re.compile(
    r'^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*$'
)
# Redact opaque tickets in /i/<ticket> request paths and URLs.
SHORT_URL_PATH_RE = re.compile(r'(/i/)([^/?\s#]+)', re.IGNORECASE)
BT1_TOKEN_RE = re.compile(r'bt1\.[0-9a-f]{16}\.[0-9a-f]{32,}', re.IGNORECASE)
BOOTSTRAP_ENV_RE = re.compile(r'(FRP_BOOTSTRAP_(?:TICKET|LOCATOR)\s*=\s*)\S+', re.IGNORECASE)


# Entry locators are routing indices, never accepted by the existing
# high-entropy enrollment credential parser.  Do not connect these helpers
# to the old /i/ handler, which returns a redeemable credential.
BOOTSTRAP_LOCATOR_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
BOOTSTRAP_LOCATOR_RE = re.compile(r'[A-Za-z0-9_-]{8}')
# /enroll is an existing allocator endpoint (POST).
BOOTSTRAP_RESERVED_LOCATORS = frozenset({'enroll', 'zt0000', 'zt000000', 'healthz', 'ca.crt'})

# Product-local Apple Silicon interpreter, not an unpinned Homebrew/CLT
# prerequisite. Pin the upstream release artifact rather than its mutable latest.
MACOS_RUNTIME_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20261123/'
                     'cpython-3.11.18%2B20261123-aarch64-apple-darwin-install_only.tar.gz')
MACOS_RUNTIME_SHA256 = 'e1b27b6f634cf9c01722ebae87be0b08c98a21e5b123edbdf3a0e7bf4b57e0ee'



def is_bootstrap_locator(value):
    return (isinstance(value, str)
            and BOOTSTRAP_LOCATOR_RE.fullmatch(value) is not None
            and value.lower() not in BOOTSTRAP_RESERVED_LOCATORS)


def new_bootstrap_locator():
    """Generate a candidate only; caller must claim it atomically in storage."""
    while True:
        value = ''.join(secrets.choice(BOOTSTRAP_LOCATOR_ALPHABET) for _ in range(8))
        if is_bootstrap_locator(value):
            return value


def entry_authority(value):
    """Validate a canonical HTTPS authority, never a URL or shell expression."""
    if not isinstance(value, str):
        raise ValueError('invalid bootstrap authority')
    match = re.fullmatch(r'(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(?::([1-9][0-9]{0,4}))?', value)
    if not match:
        raise ValueError('invalid bootstrap authority')
    host, port = match.groups()
    if port is not None and int(port) > 65535:
        raise ValueError('invalid bootstrap port')
    if host.startswith('['):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError as exc:
            raise ValueError('invalid bootstrap IPv6 address') from exc
    elif re.fullmatch(r'[0-9.]+', host):
        try:
            ipaddress.IPv4Address(host)
        except ValueError as exc:
            raise ValueError('invalid bootstrap IPv4 address') from exc
    elif not DNS_HOSTNAME_RE.fullmatch(host):
        raise ValueError('invalid bootstrap hostname')
    return value


def render_entry_command(authority, locator, platform):
    """Render the owner-approved entry fields only; no enrollment credential.

    This is a pure renderer, not installed-product or security qualification.
    In particular the initial fetch deliberately does not authenticate TLS.
    """
    authority = entry_authority(authority)
    if not is_bootstrap_locator(locator):
        raise ValueError('invalid bootstrap locator')
    url = 'https://%s/%s' % (authority, locator)
    if platform in ('linux', 'macos'):
        return 'curl -kfsS %s|sudo bash' % url
    if platform == 'windows':
        return 'iex(curl.exe -kfsS %s|Out-String)' % url
    raise ValueError('unsupported bootstrap platform')


def entry_claim_message(action, payload):
    """Domain-separated signed claim; never includes a credential."""
    if action not in ('request', 'redeem'):
        raise ValueError('invalid entry action')
    fields = {name: payload[name] for name in (
        'locator', 'machine_id', 'hostname', 'public_key', 'nonce', 'timestamp')}
    fields.update(domain='drlink-entry-v1', action=action)
    return json.dumps(fields, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def entry_enroll_message(enrollment_id, timestamp, body):
    """Prove possession of the approved key for the exact enrollment body."""
    if isinstance(body, str):
        body = body.encode('utf-8')
    return ('drlink-entry-enroll-v1\n%s\n%s\n%s' % (
        enrollment_id, timestamp, hashlib.sha256(body).hexdigest())).encode('ascii')


def accepted_bootstrap_credential(ticket):
    text = str(ticket or '').strip()
    return bool(
        BOOTSTRAP_TICKET_RE.fullmatch(text) or COMPACT_CREDENTIAL_RE.fullmatch(text)
    )


def bootstrap_record_id(ticket):
    """Internal ticket-file id for a public credential.

    Legacy bt1 uses the explicit id. Compact credentials use the first 16 hex
    chars of SHA-256 over the exact ASCII credential (same derivation as the
    allocator). Returns '' when the credential is not an accepted form.
    """
    text = str(ticket or '').strip()
    if BOOTSTRAP_TICKET_RE.fullmatch(text):
        return text.split('.')[1].lower()
    if COMPACT_CREDENTIAL_RE.fullmatch(text):
        return hashlib.sha256(text.encode('ascii')).hexdigest()[:16]
    return ''


def shell_quote(value):
    quoted = shlex.quote(str(value))
    if quoted and quoted[0] not in ("'", '"'):
        quoted = "'" + quoted + "'"
    return quoted


def bootstrap_hostname(cfg):
    """Optional Zero-Touch HTTPS entry authority (not public_hostname)."""
    if not isinstance(cfg, dict):
        return ''
    return str(cfg.get('bootstrap_hostname') or '').strip().lower()













def https_origin(url):
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("URL must be HTTPS")
    return "https://%s" % parsed.netloc


def same_https_origin(left, right):
    """True when two HTTPS URLs share a host and port (443 is the default)."""
    try:
        a = urlparse(str(left or "").strip())
        b = urlparse(str(right or "").strip())
    except Exception:
        return False
    if a.scheme != "https" or b.scheme != "https":
        return False

    def key(parsed):
        return ((parsed.hostname or "").lower(), parsed.port or 443)

    return key(a) == key(b)


def ca_crt_url(allocator_url):
    return https_origin(allocator_url) + "/ca.crt"


def _require_ca_fingerprint(ca_sha256):
    fp = str(ca_sha256 or "").strip().lower()
    if len(fp) != 64 or any(ch not in "0123456789abcdef" for ch in fp):
        raise ValueError("invalid CA fingerprint")
    return fp


def _private_ca_pin_shell(allocator_url, ca_sha256):
    """Shell that leaves a fingerprint-checked CA at ``$d/ca.crt``.

    The only unverified fetch is ``/ca.crt``. Callers must use ``--cacert``
    for every later download.
    """
    fp = _require_ca_fingerprint(ca_sha256)
    ca_url = ca_crt_url(allocator_url)
    return (
        "set -euo pipefail; "
        "d=$(mktemp -d /tmp/drlink-zt.XXXXXX); "
        'trap "rm -rf $d" EXIT; '
        "curl --fail --silent --show-error --max-time 30 --proto =https --insecure "
        "-o $d/ca.crt %s; "
        "openssl x509 -in $d/ca.crt -outform DER -out $d/ca.der >/dev/null; "
        'fp=$(openssl dgst -sha256 $d/ca.der | awk "{print \\$NF}" | tr A-F a-f); '
        'test "$fp" = %s || { echo "ERROR: CA fingerprint mismatch (pinned %s, '
        'got $fp). Nothing was installed." >&2; exit 1; }; '
    ) % (shell_quote(ca_url), shell_quote(fp), fp)


def _entry_posix_runtime_setup():
    """Provision missing Linux prerequisites via existing OS repository trust.

    This is part of the downloaded entry, never a customer command field.
    Do not change repository configuration, trust anchors or system Python
    links. Darwin can install the independently pinned portable runtime in
    the product-owned directory, without installing CLT or Homebrew.
    """
    return r"""entry_os="$(uname -s)"
entry_linux_python_package() {
  case "$1:$2" in
    rhel:8|centos:8|rocky:8|almalinux:8|ol:8) printf '%s' python39 ;;
    *) printf '%s' python3 ;;
  esac
}
entry_install_linux_packages() {
  [[ "$entry_os" == Linux ]] || return 1
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq &&
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "$@"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "$@"
  else
    echo "ERROR: no supported OS package manager for Bootstrap dependencies" >&2
    return 1
  fi
}
entry_find_python() {
  local candidate bin
  if [[ "$entry_os" == Darwin ]]; then
    # A transient PATH interpreter cannot support a future launchd service.
    for bin in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
      [[ -x "$bin" ]] || continue
      if [[ "$bin" == /usr/bin/python3 ]] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
      if "$bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' >/dev/null 2>&1; then
        ENTRY_PYTHON="$bin"
        return 0
      fi
    done
    return 1
  fi
  for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8 python3.7; do
    bin="$(type -P "$candidate" 2>/dev/null || true)"
    [[ -n "$bin" ]] || continue
    if "$bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)' >/dev/null 2>&1; then
      ENTRY_PYTHON="$bin"
      return 0
    fi
  done
  return 1
}
entry_ensure_openssl() {
  command -v openssl >/dev/null 2>&1 && return 0
  if [[ "$entry_os" == Linux ]]; then
    entry_install_linux_packages openssl || return 1
    hash -r
  fi
  command -v openssl >/dev/null 2>&1 || {
    echo "ERROR: Bootstrap cannot provision OpenSSL on this host" >&2
    return 1
  }
}
entry_owned_path() {
  local path="$1" meta owner mode
  [[ -e "$path" && ! -L "$path" ]] || return 1
  meta="$(stat -f '%u %Lp' "$path")" || return 1
  read -r owner mode <<< "$meta"
  [[ "$owner" == "$(id -u)" && "$mode" =~ ^[0-7]{3,4}$ ]] || return 1
  (( (8#$mode & 022) == 0 ))
}
entry_owned_directory() {
  [[ -d "$1" ]] && entry_owned_path "$1"
}
entry_make_owned_directory() {
  if [[ ! -e "$1" && ! -L "$1" ]]; then
    mkdir -m 0755 "$1" || return 1
  fi
  entry_owned_directory "$1"
}
entry_macos_python_path() {
  local base="$1" runtime="$1/runtime/python" bin marker
  bin="$runtime/bin/python3"
  marker="$runtime/.drlink-runtime-sha256"
  entry_owned_directory "$base" &&
    entry_owned_directory "$base/runtime" &&
    entry_owned_directory "$runtime" &&
    entry_owned_directory "$runtime/bin" || return 1
  [[ -f "$marker" && -x "$bin" && -L "$bin" ]] || return 1
  [[ "$(readlink "$bin")" == python3.11 ]] || return 1
  entry_owned_path "$runtime/bin/python3.11" && entry_owned_path "$marker" || return 1
  [[ "$(cat "$marker")" == @MACOS_SHA@ ]] || return 1
  "$bin" -I -c 'import sys,ssl,sqlite3,hashlib; sys.exit(0 if sys.version_info[:3] == (3,11,18) else 1)' >/dev/null 2>&1 || return 1
  printf '%s' "$bin"
}
entry_macos_install_python() (
  local base="$1" scratch="$2" runtime="$1/runtime/python" stage="" archive got
  [[ "$entry_os" == Darwin && "$(uname -m)" == arm64 ]] || {
    echo "ERROR: the managed runtime requires Apple Silicon macOS" >&2; return 1
  }
  entry_macos_python_path "$base" >/dev/null && return 0
  entry_owned_directory "$(dirname "$base")" &&
    entry_make_owned_directory "$base" &&
    entry_make_owned_directory "$base/runtime" || {
    echo "ERROR: unsafe managed Python directory" >&2; return 1
  }
  if [[ -e "$runtime" || -L "$runtime" ]]; then
    entry_macos_python_path "$base" >/dev/null && return 0
    echo "ERROR: existing managed Python runtime is invalid; refusing replacement" >&2
    return 1
  fi
  stage="$(mktemp -d "$base/runtime/.python-install.XXXXXX")" || return 1
  trap 'rm -rf "$stage"' EXIT
  archive="$scratch/drlink-macos-python.tar.gz"
  echo "Preparing Data Relay Link managed Python runtime ..." >&2
  curl -fsSL --proto '=https' --proto-redir '=https' --tlsv1.2 --max-time 300 @MACOS_URL@ -o "$archive" || return 1
  got="$(shasum -a 256 "$archive" | awk '{print tolower($1)}')" || return 1
  [[ "$got" == @MACOS_SHA@ ]] || {
    echo "ERROR: managed Python archive SHA256 mismatch" >&2; return 1
  }
  # Exact upstream archive was inspected; never extract before digest match.
  tar -xzf "$archive" --no-same-owner -C "$stage" || return 1
  [[ -d "$stage/python" && ! -L "$stage/python" && -x "$stage/python/bin/python3" ]] || return 1
  chmod -R go-w "$stage/python" || return 1
  "$stage/python/bin/python3" -I -c 'import sys,ssl,sqlite3,hashlib; sys.exit(0 if sys.version_info[:3] == (3,11,18) else 1)' || return 1
  printf '%s\n' @MACOS_SHA@ >"$stage/python/.drlink-runtime-sha256" || return 1
  # rename never merges into an existing directory. A concurrent successful
  # install can be reused, but no partial or unknown runtime is executed.
  if ! "$stage/python/bin/python3" -I -c 'import os,sys; os.rename(sys.argv[1],sys.argv[2])' "$stage/python" "$runtime"; then
    entry_macos_python_path "$base" >/dev/null || return 1
  fi
  entry_macos_python_path "$base" >/dev/null || return 1
)
entry_ensure_python() {
  local package ID="" VERSION_ID="" macbase='/Library/Application Support/drlink'
  if [[ "$entry_os" == Darwin ]]; then
    if ENTRY_PYTHON="$(entry_macos_python_path "$macbase")"; then
      export PATH="${ENTRY_PYTHON%/*}:$PATH"
      return 0
    fi
    if entry_find_python; then
      export PATH="${ENTRY_PYTHON%/*}:$PATH"
      return 0
    fi
    entry_macos_install_python "$macbase" "$WORKDIR" || return 1
    ENTRY_PYTHON="$(entry_macos_python_path "$macbase")" || return 1
    export PATH="${ENTRY_PYTHON%/*}:$PATH"
    return 0
  fi
  entry_find_python && return 0
  if [[ "$entry_os" == Linux ]]; then
    if [[ -r /etc/os-release ]]; then . /etc/os-release; fi
    package="$(entry_linux_python_package "$ID" "${VERSION_ID%%.*}")"
    entry_install_linux_packages "$package" || return 1
    hash -r
    entry_find_python && return 0
  fi
  echo "ERROR: compatible Python runtime is not available to the Bootstrap" >&2
  return 1
}""".replace('@MACOS_SHA@', shell_quote(MACOS_RUNTIME_SHA256)).replace(
        '@MACOS_URL@', shell_quote(MACOS_RUNTIME_URL))


def _qualified_linux_shell(installer_url, allocator_url, ca_file, bundle_file, workdir, *, entry=False):
    """Verify the pinned Server's outer candidate before any installer executes."""
    origin = https_origin(allocator_url)
    if str(installer_url) != origin + '/artifacts/agent/bootstrap-client.sh':
        return ''
    validator = '''import hashlib,json,re,sys
from pathlib import Path
def require(condition,message):
 if not condition: raise SystemExit("ERROR: " + message)
manifest,sums,bundle=sys.argv[1:]
m=json.loads(Path(manifest).read_text())
require(m.get("qualification_status")=="PASS", "qualified manifest is not PASS")
c=str(m.get("channel", "")).lower()
c="development" if c=="dev" else c
require(c in ("development","preview","stable"), "invalid channel")
r=str(m.get("immutable_source_ref") or m.get("git_ref") or m.get("source_head") or "")
require(re.fullmatch(r"[0-9a-fA-F]{40}|v[0-9]+\\.[0-9]+\\.[0-9]+(?:-rc\\.[0-9]+)?",r), "invalid immutable ref")
a=[x for x in m.get("artifacts",[]) if isinstance(x,dict) and x.get("relative_path")=="agent/bootstrap-client.sh"]
require(len(a)==1, "missing or duplicate Agent artifact")
h=str(a[0].get("sha256", "")).lower()
require(re.fullmatch("[0-9a-f]{64}",h), "invalid digest")
head=str(m.get("source_head") or a[0].get("source_head") or r)
require(re.fullmatch("[0-9a-fA-F]{40}",head), "invalid candidate head")
require(str(a[0].get("source_head") or head).lower()==head.lower(), "artifact head mismatch")
if re.fullmatch("[0-9a-fA-F]{40}",r):
 require(head.lower()==r.lower(), "candidate source mismatch")
entries=[line.split() for line in Path(sums).read_text().splitlines()]
matches=[x[0].lower() for x in entries if len(x)==2 and x[1]=="agent/bootstrap-client.sh"]
require(matches==[h], "manifest and SHA256SUMS disagree")
require(hashlib.sha256(Path(bundle).read_bytes()).hexdigest()==h, "installer SHA256 mismatch")
print(c+"\\t"+r+"\\t"+h+"\\t"+head)
'''
    ca_setup = ('ca_args=(--cacert "%s"); ' % ca_file) if ca_file else ('ca_args=(); if [[ -n "${FRP_ALLOCATOR_CA_FILE:-}" ]]; then ca_args=(--cacert "$FRP_ALLOCATOR_CA_FILE"); fi; ')
    return ca_setup + (
        'curl -fsSL --proto =https "${ca_args[@]}" %s -o "%s/manifest.json"; '
        'curl -fsSL --proto =https "${ca_args[@]}" %s -o "%s/qualified-sums"; '
        'metadata=$(%s -c %s "%s/manifest.json" "%s/qualified-sums" "%s"); '
        'IFS=$(printf "\\t") read -r channel source_ref digest source_head <<< "$metadata"; '
        'if [[ -n "${FRP_EXPECTED_SOURCE_REF:-}" && "$FRP_EXPECTED_SOURCE_REF" != "$source_ref" ]]; then '
        'echo "ERROR: qualified bootstrap source does not match requested source" >&2; exit 1; fi; '
        'if [[ -n "${FRP_EXPECTED_SOURCE_HEAD:-}" && "$FRP_EXPECTED_SOURCE_HEAD" != "$source_head" ]]; then '
        'echo "ERROR: qualified bootstrap HEAD does not match requested HEAD" >&2; exit 1; fi; '
        'requested_channel=${FRP_EXPECTED_RELEASE_CHANNEL:-${FRP_RELEASE_CHANNEL:-}}; '
        'if [[ "$requested_channel" == dev ]]; then requested_channel=development; fi; '
        'if [[ -n "$requested_channel" && "$requested_channel" != "$channel" ]]; then '
        'echo "ERROR: qualified bootstrap channel does not match requested channel" >&2; exit 1; fi; '
        'export FRP_EXPECTED_SOURCE_REF="$source_ref" FRP_BUNDLE_SHA256="$digest" '
        'FRP_EXPECTED_SOURCE_HEAD="$source_head" '
        'FRP_RELEASE_CHANNEL="$channel" FRP_EXPECTED_RELEASE_CHANNEL="$channel"; '
    ) % (shell_quote(origin + '/artifacts/manifest.json'), workdir,
         shell_quote(origin + '/artifacts/SHA256SUMS'), workdir,
         '"$ENTRY_PYTHON"' if entry else 'python3',
         shell_quote("exec(" + repr(validator) + ")"), workdir, workdir, bundle_file)


def pinned_ca_manual_linux_command(installer_url, allocator_url, ca_sha256, env_parts):
    """Manual or legacy enrollment command that pins the CA before the installer.

    The enrollment code stays interactive. ``env_parts`` are already
    shell-quoted ``KEY=value`` assignments passed to the installer.
    """
    installer = str(installer_url or "").strip()
    parts = [str(part) for part in (env_parts or []) if str(part).strip()]
    if not installer.lower().startswith("https://"):
        raise ValueError("installer URL must be HTTPS")
    if not parts:
        raise ValueError("manual install environment is required")
    inner = _private_ca_pin_shell(allocator_url, ca_sha256) + (
        "curl -fsSL --proto =https --cacert $d/ca.crt %s -o \"$d/installer.sh\"; "
        "export %s; %senv %s FRP_ALLOCATOR_CA_FILE=\"$d/ca.crt\" FRP_INSTALLER_URL=%s "
        "FRP_BUNDLE_FILE=\"$d/installer.sh\" bash \"$d/installer.sh\""
        % (shell_quote(installer), " ".join(parts), _qualified_linux_shell(installer, allocator_url, '$d/ca.crt', '$d/installer.sh', '$d'), " ".join(parts), shell_quote(installer))
    )
    if inner.count("--insecure") != 1:
        raise ValueError("manual command must fetch only the CA insecurely")
    return "sudo bash -c %s" % shell_quote(inner)


def _qualified_windows_shell(installer_url, allocator_url, digest_var, expected_var):
    origin = https_origin(allocator_url)
    if str(installer_url) != origin + '/artifacts/agent/bootstrap-client.ps1':
        return ''
    return (
        '$qualified=$wc.DownloadString(%s)|ConvertFrom-Json;'
        '$candidateRef=[string]$qualified.immutable_source_ref;'
        'if(-not $candidateRef){$candidateRef=[string]$qualified.git_ref};'
        'if(-not $candidateRef){$candidateRef=[string]$qualified.source_head};'
        '$agent=@($qualified.artifacts|Where-Object {$_.relative_path -ceq "agent/bootstrap-client.ps1"});'
        'if($qualified.qualification_status -cne "PASS" -or '
        '$qualified.channel -cnotin @("development","preview","stable") -or '
        '$qualified.source_head -cnotmatch "^[0-9a-f]{40}$" -or '
        r'$candidateRef -cnotmatch "^([0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+(-rc\.[0-9]+)?)$" -or '
        '($candidateRef -cmatch "^[0-9a-f]{40}$" -and $candidateRef -cne $qualified.source_head) -or '
        '$agent.Count -ne 1 -or $agent[0].source_head -cne $qualified.source_head -or '
        '$agent[0].sha256 -cnotmatch "^[0-9a-f]{64}$" -or '
        '$agent[0].sha256 -cne %s -or $agent[0].sha256 -cne %s)'
        '{throw "qualified Windows bootstrap provenance mismatch"};'
        'if($env:FRP_EXPECTED_SOURCE_HEAD -and $env:FRP_EXPECTED_SOURCE_HEAD -cne $qualified.source_head)'
        '{throw "qualified Windows bootstrap HEAD does not match request"};'
        'if($env:FRP_EXPECTED_SOURCE_REF -and $env:FRP_EXPECTED_SOURCE_REF -cne $candidateRef)'
        '{throw "qualified Windows bootstrap source does not match request"};'
        '$requestedChannel=$env:FRP_EXPECTED_RELEASE_CHANNEL;'
        'if(-not $requestedChannel){$requestedChannel=$env:FRP_RELEASE_CHANNEL};'
        'if($requestedChannel -eq "dev"){$requestedChannel="development"};'
        'if($requestedChannel -and $requestedChannel -cne $qualified.channel)'
        '{throw "qualified Windows bootstrap channel does not match request"};'
        '$env:FRP_EXPECTED_SOURCE_REF=$candidateRef;'
        '$env:FRP_EXPECTED_SOURCE_HEAD=[string]$qualified.source_head;'
        '$env:FRP_RELEASE_CHANNEL=[string]$qualified.channel;'
        '$env:FRP_BUNDLE_SHA256=[string]$agent[0].sha256;'
    ) % (powershell_quote(origin + '/artifacts/manifest.json'), digest_var, expected_var)


def powershell_quote(value):
    """Return a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"




def sha256sums_url_for_installer(installer_url):
    installer = str(installer_url or '').strip()
    if not installer.lower().startswith('https://'):
        raise ValueError('installer URL must be HTTPS')
    marker = '/artifacts/'
    if marker in installer:
        return installer.split(marker, 1)[0] + '/artifacts/SHA256SUMS'
    for suffix in ('/dist/bootstrap-client.ps1', '/dist/bootstrap-client.sh'):
        if installer.endswith(suffix):
            return installer[: -len(suffix)] + '/SHA256SUMS'
    # Non-release layouts (tests / custom mirrors): SHA256SUMS beside the installer.
    if '/' not in installer[8:]:
        raise ValueError('installer URL path is incomplete')
    parent = installer.rsplit('/', 1)[0]
    return parent + '/SHA256SUMS'


def linux_installer_sum_names(installer_url):
    """Return candidate SHA256SUMS pathnames for the Linux installer artifact."""
    installer = str(installer_url or '').strip()
    if installer.endswith('/artifacts/agent/bootstrap-client.sh'):
        return ('agent/bootstrap-client.sh',)
    if installer.endswith('/dist/bootstrap-client.sh'):
        return ('dist/bootstrap-client.sh',)
    name = installer.rsplit('/', 1)[-1]
    if not name:
        raise ValueError('Linux installer URL must include a filename')
    if name == 'bootstrap-client.sh':
        return ('dist/bootstrap-client.sh', 'bootstrap-client.sh', 'agent/bootstrap-client.sh')
    return (name,)


def _pinned_or_stock_curl_line(url_var, dest_var, pin_private_ca):
    """Curl one HTTPS URL, pinning the allocator CA when the origin matches.

    ``FRP_ALLOCATOR_CA_FILE`` is set by the fresh-client command. A distinct
    public installer origin keeps stock OS trust. Neither path uses
    ``--insecure``.
    """
    stock = 'curl -fsSL --proto "=https" --tlsv1.2 "$%s" -o "$%s"' % (url_var, dest_var)
    if not pin_private_ca:
        return stock
    return (
        'if [[ -n "${FRP_ALLOCATOR_CA_FILE:-}" && -f "$FRP_ALLOCATOR_CA_FILE" ]]; then '
        'curl -fsSL --proto "=https" --tlsv1.2 --cacert "$FRP_ALLOCATOR_CA_FILE" '
        '"$%s" -o "$%s"; else %s; fi'
    ) % (url_var, dest_var, stock)


def render_short_url_bootstrap_script(allocator_url, ca_sha256, ticket, installer_url,
                                     qualified_provenance=None, *, entry_locator=None, ca_pem=None):
    """Return the short-URL bootstrap using direct, validated installer env.

    Downloads installer + SHA256SUMS, verifies the exact expected hash, then
    executes. Same-origin HTTPS checksum integrity — not signed authentication.
    """
    allocator = str(allocator_url or '').strip()
    ca = str(ca_sha256 or '').strip().lower()
    if not allocator.startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', ca):
        raise ValueError('allocator URL and pinned CA fingerprint are required')
    entry = entry_locator is not None
    if entry:
        if ticket or not is_bootstrap_locator(entry_locator) or not ca_pem:
            raise ValueError('secret-free entry locator and public CA required')
    elif not BOOTSTRAP_TICKET_RE.fullmatch(str(ticket or '')):
        raise ValueError('internal bootstrap ticket required for stage-1')
    installer = str(installer_url or '').strip()
    if not installer.lower().startswith('https://'):
        raise ValueError('installer URL must be HTTPS')
    sums_url = sha256sums_url_for_installer(installer)
    expected_names = linux_installer_sum_names(installer)
    names_csv = ','.join(expected_names)
    provenance_lines = []
    if qualified_provenance is not None:
        p = qualified_provenance
        head = str(p.get('source_head') or '')
        ref = str(p.get('immutable_source_ref') or p.get('git_ref') or head)
        digest = str(p.get('sha256') or '')
        channel = str(p.get('channel') or '')
        if (not re.fullmatch(r'[0-9a-f]{40}', head)
                or not re.fullmatch(r'[0-9a-f]{40}|v[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?', ref)
                or (re.fullmatch(r'[0-9a-f]{40}', ref) and ref != head)
                or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or channel not in ('development', 'preview', 'stable')):
            raise ValueError('invalid qualified bootstrap provenance')
        provenance_lines = [
            '# Bind public-hostname aliases to the serving Server candidate.',
            'if [[ "$GOT" != %s ]]; then echo "ERROR: qualified installer digest mismatch" >&2; exit 1; fi' % shell_quote(digest),
            'if [[ -n "${FRP_EXPECTED_SOURCE_HEAD:-}" && "$FRP_EXPECTED_SOURCE_HEAD" != %s ]]; then echo "ERROR: qualified bootstrap HEAD does not match request" >&2; exit 1; fi' % shell_quote(head),
            'if [[ -n "${FRP_EXPECTED_SOURCE_REF:-}" && "$FRP_EXPECTED_SOURCE_REF" != %s ]]; then echo "ERROR: qualified bootstrap source does not match request" >&2; exit 1; fi' % shell_quote(ref),
            'if [[ -n "${FRP_BUNDLE_SHA256:-}" && "$FRP_BUNDLE_SHA256" != %s ]]; then echo "ERROR: qualified bootstrap digest does not match request" >&2; exit 1; fi' % shell_quote(digest),
            'requested_channel=${FRP_EXPECTED_RELEASE_CHANNEL:-${FRP_RELEASE_CHANNEL:-}}; if [[ "$requested_channel" == dev ]]; then requested_channel=development; fi',
            'if [[ -n "$requested_channel" && "$requested_channel" != %s ]]; then echo "ERROR: qualified bootstrap channel does not match request" >&2; exit 1; fi' % shell_quote(channel),
            'export FRP_EXPECTED_SOURCE_HEAD=%s FRP_EXPECTED_SOURCE_REF=%s FRP_BUNDLE_SHA256=%s FRP_RELEASE_CHANNEL=%s FRP_EXPECTED_RELEASE_CHANNEL=%s'
            % tuple(shell_quote(v) for v in (head, ref, digest, channel, channel)),
        ]
    lines = [
        '#!/bin/bash',
        '# Data Relay Link — Zero-Touch short URL bootstrap',
        '# Generic entry script. Enrollment profile remains server-side.',
        '# Integrity: download SHA256SUMS + installer, verify, then execute.',
        '# Not a cryptographic signature — same-origin HTTPS checksum only.',
        'set -euo pipefail',
        'if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then',
        '  echo "ERROR: re-run the Server-issued Zero-Touch command as root" >&2',
        '  exit 1',
        'fi',
        'INSTALLER_URL=%s' % shell_quote(installer),
        'SUMS_URL=%s' % shell_quote(sums_url),
        'EXPECTED_NAMES=%s' % shell_quote(names_csv),
        'FRP_ALLOCATOR_URL=%s' % shell_quote(allocator),
        'FRP_ALLOCATOR_CA_SHA256=%s' % shell_quote(ca),
        ('FRP_BOOTSTRAP_LOCATOR=%s' % shell_quote(entry_locator) if entry else
         'FRP_BOOTSTRAP_TICKET=%s' % shell_quote(ticket)),
        ('unset FRP_BOOTSTRAP_TICKET; export FRP_ALLOCATOR_URL FRP_ALLOCATOR_CA_SHA256 FRP_BOOTSTRAP_LOCATOR'
         if entry else 'export FRP_ALLOCATOR_URL FRP_ALLOCATOR_CA_SHA256 FRP_BOOTSTRAP_TICKET'),
        'export FRP_ZERO_TOUCH=1',
        'WORKDIR="$(mktemp -d /tmp/drlink-bootstrap.XXXXXX)"',
        'cleanup() { rm -rf "$WORKDIR"; }',
        'trap cleanup EXIT',
        'umask 077',
        *([
            _entry_posix_runtime_setup(),
            'entry_ensure_openssl',
            'FRP_ALLOCATOR_CA_FILE="$WORKDIR/allocator-ca.crt"',
            'printf %s %s > "$FRP_ALLOCATOR_CA_FILE"' % ('%s', shell_quote(ca_pem)),
            'openssl x509 -in "$FRP_ALLOCATOR_CA_FILE" -outform DER -out "$WORKDIR/ca.der"',
            '''CA_GOT="$(openssl dgst -sha256 "$WORKDIR/ca.der" | awk '{print tolower($NF)}')"''',
            '[[ "$CA_GOT" == "$FRP_ALLOCATOR_CA_SHA256" ]] || { echo "ERROR: CA fingerprint mismatch" >&2; exit 1; }',
            'export FRP_ALLOCATOR_CA_FILE',
        ] if entry else []),
        'SUMS_FILE="$WORKDIR/SHA256SUMS"',
        'INSTALLER_FILE="$WORKDIR/bootstrap-client.sh"',
        _pinned_or_stock_curl_line('SUMS_URL', 'SUMS_FILE', same_https_origin(sums_url, allocator_url)),
        _pinned_or_stock_curl_line('INSTALLER_URL', 'INSTALLER_FILE', same_https_origin(installer, allocator_url)),
        'WANT="$(awk -v names="$EXPECTED_NAMES" \'BEGIN{split(names,a,","); for(i in a) ok[a[i]]=1; c=0} ($2 in ok){print tolower($1); c++} END{if(c!=1) exit 1}\' "$SUMS_FILE")"',
        # GNU sha256sum is not installed on a stock macOS host. Preserve
        # byte-identical digest verification using native shasum -a 256.
        'if command -v sha256sum >/dev/null 2>&1; then',
        '  GOT="$(sha256sum "$INSTALLER_FILE" | awk \'{print tolower($1)}\')"',
        'elif command -v shasum >/dev/null 2>&1; then',
        '  GOT="$(shasum -a 256 "$INSTALLER_FILE" | awk \'{print tolower($1)}\')"',
        'else',
        '  echo "ERROR: SHA256 verifier unavailable (install sha256sum or shasum)" >&2',
        '  exit 1',
        'fi',
        'if [[ "$GOT" != "$WANT" ]]; then',
        '  echo "ERROR: installer SHA256 mismatch (integrity check failed)" >&2',
        '  exit 1',
        'fi',
        *provenance_lines,
        *(['entry_ensure_python'] if entry else []),
        'chmod 0700 "$INSTALLER_FILE"',
        '# Same-origin artifacts use FRP_ALLOCATOR_CA_FILE when the fresh-client',
        '# command supplied it. A distinct public installer origin uses stock OS trust.',
        '# The installer then pins this CA by fingerprint before enrollment.',
        _qualified_linux_shell(installer, allocator_url, '', '$INSTALLER_FILE', '$WORKDIR', entry=entry),
        'FRP_INSTALLER_URL="$INSTALLER_URL" FRP_BUNDLE_FILE="$INSTALLER_FILE" bash "$INSTALLER_FILE"',
        '',
    ]
    if entry:
        # Bash reads the complete compound command before executing it.
        # An incomplete HTTP response cannot run an otherwise valid prefix.
        return '#!/bin/bash\n{\n' + '\n'.join(lines[1:]) + '\n}\n'
    return '\n'.join(lines)


def _entry_windows_download_client(private_ca_origin):
    """Request-local .NET validator usable on both WinPS 5.1 and PowerShell 7.

    ServicePointManager scriptblock callbacks do not reliably apply to real
    HTTPS on .NET Core. A compiled callback needs no PowerShell runspace and
    preserves CA pinning, hostname validation and normal public trust.
    """
    source = r"""using System;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;

namespace DataRelayLinkBootstrap {
 public sealed class EntryDownloadV1 {
  private readonly X509Certificate2 ca;
  private readonly Uri pinnedOrigin;
  public EntryDownloadV1(X509Certificate2 certificate, string origin) {
   ca = certificate;
   pinnedOrigin = certificate == null ? null : new Uri(origin);
  }
  private bool Validate(object sender, X509Certificate certificate,
                        X509Chain peerChain, SslPolicyErrors errors) {
   if (certificate == null) return false;
   if (ca == null) return errors == SslPolicyErrors.None;
   if ((errors & ~SslPolicyErrors.RemoteCertificateChainErrors) != 0)
    return false;
   using (var leaf = new X509Certificate2(certificate.GetRawCertData()))
   using (var chain = new X509Chain()) {
    chain.ChainPolicy.ExtraStore.Add(ca);
    if (peerChain != null)
     foreach (X509ChainElement element in peerChain.ChainElements)
      chain.ChainPolicy.ExtraStore.Add(element.Certificate);
    chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
    chain.ChainPolicy.VerificationFlags = X509VerificationFlags.AllowUnknownCertificateAuthority;
    chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
    bool built = chain.Build(leaf);
    if (chain.ChainElements.Count == 0) return false;
    foreach (X509ChainStatus status in chain.ChainStatus)
     if ((status.Status & ~X509ChainStatusFlags.UntrustedRoot) != 0)
      return false;
    return (built || chain.ChainStatus.Length > 0) &&
     Convert.ToBase64String(chain.ChainElements[chain.ChainElements.Count-1].Certificate.RawData)
       == Convert.ToBase64String(ca.RawData);
   }
  }
  private void RequireOrigin(Uri uri) {
   if (uri.Scheme != Uri.UriSchemeHttps || !String.IsNullOrEmpty(uri.UserInfo))
    throw new InvalidOperationException("HTTPS artifact URL required");
   if (pinnedOrigin != null &&
       !String.Equals(uri.GetLeftPart(UriPartial.Authority),
         pinnedOrigin.GetLeftPart(UriPartial.Authority), StringComparison.OrdinalIgnoreCase))
    throw new InvalidOperationException("pinned artifact origin changed");
  }
  private HttpWebResponse Open(string url) {
   var uri = new Uri(url);
   for (int hop = 0; hop <= 5; hop++) {
    RequireOrigin(uri);
    var request = (HttpWebRequest)WebRequest.Create(uri);
    request.AllowAutoRedirect = false;
    request.KeepAlive = false;
    request.Timeout = 30000;
    request.ReadWriteTimeout = 30000;
    request.ServerCertificateValidationCallback = Validate;
    var response = (HttpWebResponse)request.GetResponse();
    int status = (int)response.StatusCode;
    if (status == 200) return response;
    string location = response.Headers["Location"];
    response.Dispose();
    if ((status != 301 && status != 302 && status != 303 && status != 307 && status != 308)
        || String.IsNullOrEmpty(location))
     throw new InvalidOperationException("artifact download failed: HTTP " + status);
    uri = new Uri(uri, location);
   }
   throw new InvalidOperationException("artifact redirect limit exceeded");
  }
  public void DownloadFile(string url, string path) {
   using (var response = Open(url))
   using (var input = response.GetResponseStream())
   using (var output = File.Create(path))
    input.CopyTo(output);
  }
  public string DownloadString(string url) {
   using (var response = Open(url))
   using (var reader = new StreamReader(response.GetResponseStream()))
    return reader.ReadToEnd();
  }
 }
}"""
    setup = (
        "  if (-not ('DataRelayLinkBootstrap.EntryDownloadV1' -as [type])) {\n"
        "    Add-Type -TypeDefinition @'\n" + source +
        "\n'@ -IgnoreWarnings -WarningAction SilentlyContinue\n"
        "  }\n"
    )
    if private_ca_origin:
        setup += "  $wc = New-Object DataRelayLinkBootstrap.EntryDownloadV1($caCert, ([Uri]$artifactOrigin).GetLeftPart([UriPartial]::Authority))"
    else:
        setup += "  $wc = New-Object DataRelayLinkBootstrap.EntryDownloadV1($null, '')"
    return setup


def windows_current_path_refresh():
    # The child installer writes machine PATH, but cannot change its caller's
    # process environment. Run this only after a successful child exit, in
    # the caller that evaluated the bootstrap. Preserve PATH order and local
    # overrides; never replace it with Machine+User PATH.
    return r'''  try {
    $drlinkRoots = @()
    if ($env:FRP_WINDOWS_ROOT) { $drlinkRoots = @($env:FRP_WINDOWS_ROOT) }
    elseif ($env:ProgramData) {
      $drlinkRoots = @((Join-Path $env:ProgramData 'drlink'), (Join-Path $env:ProgramData 'frp-auto-deploy'))
    }
    $drlinkDirs = @()
    foreach ($drlinkRoot in $drlinkRoots) {
      $drlinkTools = Join-Path $drlinkRoot 'tools'
      $drlinkShim = Join-Path $drlinkTools 'drlink.cmd'
      if ((Test-Path -LiteralPath $drlinkShim -PathType Leaf) -and
          ((Get-Content -LiteralPath $drlinkShim -Raw) -match 'DRLINK-PRODUCT-SHIM') -and
          (Test-Path -LiteralPath (Join-Path $drlinkRoot 'state/path-shim.json') -PathType Leaf)) {
        $drlinkDirs += $drlinkTools
      }
    }
    if ($drlinkDirs.Count -eq 1) {
      $drlinkTools = $drlinkDirs[0]
      $drlinkPresent = @($env:Path -split ';' | Where-Object {
        [Environment]::ExpandEnvironmentVariables($_.Trim().TrimEnd('\', '/')) -ieq $drlinkTools.TrimEnd('\', '/')
      }).Count -gt 0
      if (-not $drlinkPresent) {
        $env:Path = (@($env:Path, $drlinkTools) | Where-Object { $_ }) -join ';'
        Write-Host ('Current PowerShell PATH includes {0}.' -f $drlinkTools)
      }
    } elseif ($drlinkDirs.Count -gt 1) {
      Write-Warning 'Multiple installed CLI paths found; use the intended drlink.cmd explicitly.'
    }
  } catch {
    Write-Warning ('Could not refresh current PowerShell PATH: ' + $_.Exception.Message)
  }'''


def render_short_url_windows_bootstrap_script(
    allocator_url, ca_sha256, ticket, installer_url, *, entry_locator=None, ca_pem=None
):
    """Return a PowerShell bootstrap that verifies the installer before -File."""
    allocator = str(allocator_url or '').strip()
    ca = str(ca_sha256 or '').strip().lower()
    ticket = str(ticket or '').strip()
    installer = str(installer_url or '').strip()
    if not allocator.lower().startswith('https://'):
        raise ValueError('allocator URL must be HTTPS')
    if len(ca) != 64 or any(ch not in '0123456789abcdef' for ch in ca):
        raise ValueError('invalid CA fingerprint')
    entry = entry_locator is not None
    if entry:
        if ticket or not is_bootstrap_locator(entry_locator) or not ca_pem:
            raise ValueError('secret-free entry locator and public CA required')
    elif not accepted_bootstrap_credential(ticket):
        raise ValueError('invalid bootstrap ticket')
    if not installer.lower().startswith('https://'):
        raise ValueError('installer URL must be HTTPS')
    sums_url = sha256sums_url_for_installer(installer)
    private_ca_origin = (
        same_https_origin(sums_url, allocator)
        and same_https_origin(installer, allocator)
    )
    lines = [
        '#Requires -Version 5.1',
        "# Data Relay Link - Windows Zero-Touch short URL bootstrap",
        "$ErrorActionPreference = 'Stop'",
        "$ProgressPreference = 'SilentlyContinue'",
        *([
            "$savedBootstrapEnv = @{}",
            "foreach ($name in @('FRP_ALLOCATOR_URL','FRP_ALLOCATOR_CA_SHA256','FRP_ALLOCATOR_CA_FILE','FRP_BOOTSTRAP_TICKET','FRP_BOOTSTRAP_LOCATOR','FRP_ZERO_TOUCH','FRP_PLATFORM','FRP_EXPECTED_SOURCE_HEAD','FRP_EXPECTED_SOURCE_REF','FRP_RELEASE_CHANNEL','FRP_BUNDLE_SHA256','PSModulePath')) { $savedBootstrapEnv[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }",
            "$savedSecurityProtocol = [Net.ServicePointManager]::SecurityProtocol",
        ] if entry else []),
        "$dir = Join-Path $env:TEMP ('frp-bs-' + [guid]::NewGuid().ToString('N'))",
        'New-Item -ItemType Directory -Force -Path $dir | Out-Null',
        'try {',
        "  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12",
        "  $sums = Join-Path $dir 'SHA256SUMS'",
        "  $installer = Join-Path $dir 'bootstrap-client.ps1'",
    ]
    if entry or private_ca_origin:
        lines.extend(["  $ca = Join-Path $dir 'ca.crt'"])
        if entry:
            lines.append('  [IO.File]::WriteAllText($ca,%s)' % powershell_quote(ca_pem))
        else:
            lines.extend([
                "  $curl = Get-Command curl.exe -ErrorAction Stop",
                '  & $curl.Source --fail --silent --show-error --max-time 30 --proto =https --insecure -o $ca %s'
                % powershell_quote(ca_crt_url(allocator)),
                '  if ($LASTEXITCODE -ne 0) { throw "ca.crt download failed" }',
            ])
        lines.extend([
            '  $caCert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ca)',
            '  $fp = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($caCert.RawData)) -replace \'-\',\'\'',
            '  if ($fp.ToLowerInvariant() -ne %s) { throw "CA fingerprint mismatch" }'
            % powershell_quote(ca),
        ])
        if entry:
            lines.append('  $env:FRP_ALLOCATOR_CA_FILE = $ca')
    if private_ca_origin and not entry:
        installer_host = (urlparse(installer).hostname or '').lower()
        lines.extend([
            '  $script:drlinkCaCert = $caCert',
            '  $script:drlinkCaThumb = $caCert.Thumbprint',
            '  $script:drlinkPinHost = %s' % powershell_quote(installer_host),
            '  $oldCertCallback = [Net.ServicePointManager]::ServerCertificateValidationCallback',
            '  [Net.ServicePointManager]::ServerCertificateValidationCallback = {',
            '    param($snd,$cert,$chain,$pol)',
            '    if (-not $snd -or -not $snd.RequestUri -or $snd.RequestUri.Host.ToLowerInvariant() -ne $script:drlinkPinHost) { return $false }',
            # The only permissible OS trust error is the expected untrusted
            # private CA. A matching CA signature NEVER overrides hostname
            # mismatch or a missing peer certificate.
            '    if (([int]$pol -band 3) -ne 0 -or $null -eq $cert -or $null -eq $chain) { return $false }',
            '    $leaf = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $cert',
            '    $chain.ChainPolicy.ExtraStore.Add($script:drlinkCaCert) | Out-Null',
            '    $chain.ChainPolicy.VerificationFlags = [System.Security.Cryptography.X509Certificates.X509VerificationFlags]::AllowUnknownCertificateAuthority',
            '    $chain.ChainPolicy.RevocationMode = [System.Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck',
            '    if (-not $chain.Build($leaf)) { return $false }',
            '    $rootEl = $chain.ChainElements[$chain.ChainElements.Count-1].Certificate',
            '    return ($rootEl.Thumbprint -eq $script:drlinkCaThumb)',
            '  }',
        ])
    if entry:
        lines.append("  $artifactOrigin = %s" % powershell_quote(installer))
        lines.append(_entry_windows_download_client(private_ca_origin))
    else:
        lines.append('  $wc = New-Object Net.WebClient')
    lines.extend([
        '  $wc.DownloadFile(%s, $sums)' % powershell_quote(sums_url),
        '  $wc.DownloadFile(%s, $installer)' % powershell_quote(installer),
        '  $want = $null',
        '  Get-Content -LiteralPath $sums | ForEach-Object {',
        "    if ($_ -match '^([0-9a-fA-F]{64})\\s+(?:dist/bootstrap-client\\.ps1|agent/bootstrap-client\\.ps1|bootstrap-client\\.ps1)\\s*$') {",
        '      if ($want) { throw "duplicate bootstrap-client.ps1 hash" }',
        '      $want = $Matches[1].ToLowerInvariant()',
        '    }',
        '  }',
        '  if (-not $want) { throw "bootstrap-client.ps1 hash missing from SHA256SUMS" }',
        '  $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()',
        '  if ($got -ne $want) { throw "bootstrap-client.ps1 SHA256 mismatch" }',
        _qualified_windows_shell(installer, allocator, '$got', '$want'),
        '  $env:FRP_ALLOCATOR_URL = %s' % powershell_quote(allocator),
        '  $env:FRP_ALLOCATOR_CA_SHA256 = %s' % powershell_quote(ca),
        ('  $env:FRP_BOOTSTRAP_LOCATOR = %s' % powershell_quote(entry_locator) if entry else
         '  $env:FRP_BOOTSTRAP_TICKET = %s' % powershell_quote(ticket)),
        *(['  Remove-Item Env:FRP_BOOTSTRAP_TICKET -ErrorAction SilentlyContinue'] if entry else []),
        "  $env:FRP_ZERO_TOUCH = '1'",
        "  $env:FRP_PLATFORM = 'windows'",
        *(["  [Environment]::SetEnvironmentVariable('PSModulePath', $null, 'Process')"] if entry else []),
        '  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installer -ZeroTouch',
        '  $rc = $LASTEXITCODE',
        '  Remove-Item Env:FRP_BOOTSTRAP_TICKET -ErrorAction SilentlyContinue',
        '  if ($rc -ne 0) { exit $rc }',
        windows_current_path_refresh(),
        '} finally {',
    ])
    if private_ca_origin and not entry:
        lines.append(
            '  [Net.ServicePointManager]::ServerCertificateValidationCallback = $oldCertCallback'
        )
    lines.extend([
        *([
            "  foreach ($name in $savedBootstrapEnv.Keys) { [Environment]::SetEnvironmentVariable($name, $savedBootstrapEnv[$name], 'Process') }",
            "  [Net.ServicePointManager]::SecurityProtocol = $savedSecurityProtocol",
            "  if ($caCert) { $caCert.Dispose() }",
        ] if entry else []),
        '  Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue',
        '}',
        '',
    ])
    if entry:
        return '& {\n' + '\n'.join(lines[1:]) + '\n}\n'
    return '\n'.join(lines)

def redact_text(text):
    """Redact internal bootstrap tickets and /i/<handle> path segments."""
    if not text:
        return ''
    out = str(text)
    out = SHORT_URL_PATH_RE.sub(r'\1<redacted>', out)
    out = re.sub(r'(?P<lead>(?:https://[^/\s]+|GET |HEAD ))/(?P<locator>[A-Za-z0-9_-]{6,8})(?=[?\s\"\'#$|)]|$)',
                 lambda m: m.group('lead') + '/<redacted>' if len(m.group('locator')) in (6, 8) and m.group('locator').lower() not in BOOTSTRAP_RESERVED_LOCATORS else m.group(0),
                 out)
    out = BOOTSTRAP_ENV_RE.sub(r'\1<redacted>', out)
    out = BT1_TOKEN_RE.sub('bt1.<redacted>', out)
    return out
