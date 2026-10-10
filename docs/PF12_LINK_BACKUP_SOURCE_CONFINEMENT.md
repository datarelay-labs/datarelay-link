# PF-12B Link — Product-Native Backup Source Confinement

Status: **isolated source and temporary-root acceptance candidate**.
Work Packet [#198](https://github.com/datarelay-labs/datarelay-link/issues/198)
stacked on shared Web security [PR #197](https://github.com/datarelay-labs/datarelay-link/pull/197).
This is not a backup scheduler, recovery drill, installation, or product release.

## Why a product-specific adapter matters

Product Foundation PF-12B #81 defines immutable backup/restore evidence
and read-only restore preflight. Its BackupEvidence/preview_restore cannot
inspect actual Link archives or establish which host directory owns them.
Link ManagementSystemService already delegates validation to the product
Core-owned frp-restore --validate tool and owns the archive location
/var/lib/drlink/backups/.

Previously _backup_target relied on Path.resolve(). If the backup root
itself was a symlink to a foreign directory, that foreign directory became
the new logical root. A symlink to an archive elsewhere inside the
directory could be accepted as a different requested path.

## Product source guard

Before invoking the read-only canonical validator, Link checks the literal
canonical request path rather than only its resolved destination.

- Requires the exact archive prefix and nonempty relative archive path;
  rejects parent/dot segments, doubled or trailing separators, backslashes,
  embedded NUL/CR/LF and long relative paths.
- Rejects symlinks at the injected root and each var/lib/drlink/backups
  component, as well as nested alias, dangling and final-file symlinks.
  A symlinked backup root cannot establish an alternate authority root.
- For an existing archive, requires a regular file with exactly one
  hard link. Directory/FIFO/hardlinked aliases are rejected before
  invoking the validator. A missing *canonical* backup remains eligible
  for the validator to return valid=false without creating a file.
- Preserves the canonical, user-visible backup path and the previous
  read-only frp-restore --validate behavior for ordinary files.
  No actual backup, restore, decryption or archive mutation is performed.

The guard is preflight, **not an atomic no-follow file-descriptor proof**.
A concurrently writable backup directory can change between inspection
and invocation. Final production qualification must prove controlled
filesystem ownership and a secure native file handoff before privileged
restore. This source-only change is NOT an authorization to restore.

## Operator-facing backup terminology

The Web System page previously displayed Backup Ready: YES when only the
backup and validation executables existed. That did not establish a
completed protected archive, verified encryption-at-rest, checksum
provenance or an isolated restore drill.

The page now labels this fact Backup tools: Available/Unavailable, and
explicitly states that archive validation is not proof of disaster
recovery readiness. Existing Administrator restoration confirmation,
auth, CSRF and canonical CLI delegation are unchanged.

Full PF-12B restore readiness remains UNKNOWN/BLOCKED until real product
native evidence proves artifact byte integrity, publisher/ownership,
isolated restore-drill success, current pre-restore backup, actor/MFA,
schema compatibility, offline recovery, audit and rollback through the
shared Foundation contract. No evidence is invented in this adapter.

## Test acceptance and remaining gates

- New temporary-root tests: tests/test-v30-web-backup-path-confinement.py
  and tests/test-v30-web-backup-readiness-ui.py.
- Product native regression: existing test-v30-management-system.py,
  actual authenticated Web HTTP symlink rejection at
  V30WebServiceTests.test_backup_validation_rejects_symlinked_archive_over_authenticated_http,
  Web authentication/CSRF, bundle/UX, and optional Web package lifecycle.
  HTTP test confirms the denied symlink never invokes frp-restore validation
  or changes the original temporary-root archive.
- Exact-HEAD GitHub CI, authentic Browser + two-user Full User E2E,
  final encrypted archive and isolated native restore drill, and
  owner approval remain separate mandatory release gates.

No production, customer, active host backup/restore, credential, SSH,
firewall, service restart, permission change or protected Client/Core
test bypass occurred in this source branch.

## B5 native real-byte integrity observation (2026-10-10 follow-on)

Link now implements a narrowly bounded **read-only** product-owned archive
inspection. A current Admin may explicitly request
`POST /api/v1/system/backup/integrity` with a canonical
`{"path":"/var/lib/drlink/backups/<archive>.tar.gz"}` and optional
`expected_sha256` (exactly 64 lowercase hexadecimal characters).
The existing full Web session and anti-CSRF requirements apply; non-admin
Web roles receive HTTP 403 without reaching the filesystem. There is no
public/anonymously accessible archive inspection endpoint.

The native Link filesystem adapter opens the caller-selected archive
through a chain of directory file descriptors with `O_NOFOLLOW`, final
`O_NONBLOCK`, and checks that the file is regular and has exactly one
hard link. It streams a maximum of **128 MiB** in 128 KiB chunks from
one opened archive descriptor, computes SHA256 over those actual bytes,
and verifies stable file identity, size and modification/change metadata
before returning a result. It rejects missing, oversized, aliased and
concurrently modified sources, including a symlink swap after the
earlier path preflight. No file content is returned.

The response includes `artifact_bytes`, `sha256_observed`, optional
`matches_caller_supplied_sha256`, `read_only=true`, and
`authoritative_mutation=false`. It **always** reports:
`expected_digest_authenticated=false`, `encryption_verified=false`,
`isolated_restore_drill_verified=false`, and `restore_ready=false`.
A caller-supplied matching checksum is a byte comparison, not a verified
publisher signature, trusted backup provenance, encryption evidence,
canonical `frp-restore --validate` success or release authorization.

The existing Administration → System → Backup page shows a separate
Admin-only **Observe archive SHA256** button. It does not alter the
authoritative Validate Backup result or enable the destructive Restore
button. An archive-path edit clears both prior validation and integrity
results. The UI identifies the 128 MiB Web limit and warns that the
result is neither publisher authentication, encryption evidence, nor
an isolated restore drill.

**Remaining limitations:** This Web read is resource-bounded but a true
end-to-end operational backup may be larger; qualified bulk/offline
integrity inspection is a separate product-owner operation. An open FD
protects byte observation from a final-component symlink race, but it
does not prove the separately invoked native restore CLI will consume
the same immutable inode. Final FD-based handoff and filesystem owner
enforcement, trusted backup creation, encryption key custody, verified
restore-in-disposable-lab, backup freshness/schedule, offline console
recovery, fail-safe rollback, direct user/browser E2E and release gates
must still be completed. All tests use synthetic files under a
temporary test root; no real installed archive or service was read.

Focused native tests:
`tests/test-v30-web-backup-byte-integrity.py`,
`V30WebServiceTests.test_backup_integrity_api_requires_admin_csrf_and_real_bytes`,
and `tests/test-v30-web-backup-byte-integrity-ui.py`.
The existing PF-12 path confinement, Web auth, lifecycle and source/bundle
regressions remain applicable.
