# PF-12C — Link Offline Release Byte Preflight (source candidate)

This source-only native Link utility consumes the exact SHA256-pinned
`datarelay-onprem-security==0.10.0.dev0` PF-12C contract from Product
Foundation #83. It is **read-only**, does **not** invoke the existing online
`frp-project-update` / `frp-update` commands, and is not an installer.

## Inputs and contract

The operator supplies (1) an absolute local archive path, (2) an absolute
local JSON manifest and (3) the manifest's SHA256 from a **separate** channel.
The file checksum is an integrity hint, **not** publisher authentication.

Schema v1 accepts only `schema_version=1`, `product_ref`,
`release_ref`, `version`, `kind`, `artifact_sha256`,
`artifact_bytes`, and `publisher_key_ref`. These manifest claims are
untrusted; user-supplied `signature_verified` or permission fields are
rejected. Duplicate JSON fields are rejected.

```bash
python3 tools/drlink-offline-upgrade-preflight \
  --artifact /path/to/local/offline-release.tar.gz \
  --manifest /path/to/local/manifest.json \
  --manifest-sha256 '<independently-recorded-lowercase-64-hex-sha256>'
```

A synthetic test root may be selected with `--root /path/to/test-root`.
The installed version and immutable `SOURCE_HEAD` are read from the
product's `etc/drlink/version`. Unknown version/HEAD fails closed.

The manifest is limited to 64 KiB; the artifact is streamed in 1 MiB chunks
and capped at 2 GiB. Component-by-component no-follow file descriptors,
single hardlink, regular-file checks and before/after inode/size/timestamps
guard against symlinks, path races and content changes. No archive extraction,
remote fetch, credential, service, database or host configuration occurs.

Output is JSON with actual archive/manifest byte integrity, version and
enumerated shared Foundation `preview_offline_upgrade` blockers. A
checksum match does **not** set signed provenance, publisher trust,
schema compatibility, recovery readiness, MFA, audit or approval to true.
Return code 2 means **BLOCKED** with an integrity report; 3 means invalid
source/manifest/identity. There is **no success/ready-to-install exit**.

## Required follow-on product/owner gates

A separately authorized native installer must verify the manifest's
cryptographic signature against an independently trusted publisher key,
verify actual installed revision/schema and compatible migration, ensure
tested recovery backup/restore and rollback media, recent privileged MFA,
offline console access and audit, then perform same-HEAD user qualification.
This utility never authorizes or performs an upgrade or rollback.

This branch is an unmerged source candidate, not a distributed package.
Existing online product and engine update UI, protected Client tests, and
active worktrees are unchanged.

## Tests

`python3 tests/test-v30-offline-upgrade-preflight.py -q` covers an actual
temporary-root version file and artifact bytes, tampering, symlink/hardlink
paths, >2 GiB sparse file, invalid manifest/duplicate fields, wrong product
kind, and CLI fail-closed output. Unit/component PASS is not Browser or
Full User E2E acceptance.
