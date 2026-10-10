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
