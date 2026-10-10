# PF-12A — Link Native Non-Secret Configuration History

Status: **isolated read-only source / synthetic operator tests**. This is
a Product Foundation B5 consumer integration for existing Work Packet
[datarelay-link#202](https://github.com/datarelay-labs/datarelay-link/issues/202),
stacked on the clean optional-Web PF-9 parent PR #197.

The shared PF-12A contract lives in
[datarelay-product-foundation#79](https://github.com/datarelay-labs/datarelay-product-foundation/issues/79).
Link reuses `ConfigRevision`, `ConfigField`,
`diff_configurations`, `RollbackEvidence`, and
`preview_config_rollback` from its pre-existing SHA256-pinned exact
Foundation wheel `datarelay-onprem-security==0.10.0.dev0`.
No second shared revision engine or generic rollback authority was made.

## Genuine product-owned read path

Link Core already stores immutable `config_revisions` and
`revision_snapshots` on authoritative SQLite, with optional historical
canonical `configuration_bundle`. The new optional Web module uses
`ControlPlane(..., read_only=True)` to inspect two specifically numbered
historical snapshots; no configuration export API or customer data download
is issued. The snapshot format and `sourceRevision` are checked, YAML is
parsed using `SafeLoader` with duplicate-key and alias denial, source
text is limited to 128 KiB, and each allowlisted category is limited
to 1,024 entries. Legacy, malformed, unavailable or unsupported data
fails closed with a generic error; raw parser exceptions never reach
the Web client.

Critically, the Web boundary **does not report raw ConfigurationBundle
YAML, object names, source/destination IPs, hostnames, keys, user/actor
names, token paths, or rule contents**. Only known non-secret numeric
counts enter the pinned Foundation diff evaluator: object/group counts,
service and permission group counts, and per-policy rule/active rule
counts. Unknown sections are rejected. Counts and deterministic
fingerprints are based on this intentionally limited projection only.

**A count-only diff is NOT a full semantic configuration diff.** Two
snapshots with different IP addresses or rule targets but the same
number of entries may have zero count changes. Such a result expressly
does **not** establish semantic equality, safe rollback, valid current
policy enforcement, backup freshness or eligible deployment. The UI
labels this as count-only.

## Advisory rollback stays blocked

An advisory `preview_config_rollback` is computed using the upstream
shared Foundation contract, with real product latest revision for
staleness detection. Backup integrity, privileged operator authority,
recent MFA, out-of-band recovery, reversible-path proof and audit-ready
evidence are **not asserted**. The result always has
`may_submit_to_product_authority=false`, and shows specific safety
blockers. There is no Apply, Save, Restore or Rollback mutation route.

Link native authenticated, current **Admin + management-diagnose**
users may call:

`GET /api/v1/system/configuration/history?from_revision=1&to_revision=2`

Only exact two revision identifiers are accepted; duplicates and
extra query fields are rejected. Anonymous access is 401; current
Read Only/Operator sessions get 403 before the product history reader
runs. The existing Web source ingress guard applies even earlier.

Administration → System shows a small read-only category-count
comparison card without additional navigation roots. Comparison
requires two ascending positive revision numbers, and changing input
clears old evidence. It lists count changes and safety blockers but
does not render raw records or enable administrator mutations.

## Acceptance and still-open release gates

Native temporary-root tests use real synthetic SQLite revision rows
containing deliberately sensitive fake actors, IPs, tokens and rule
names. An additional regression invokes the genuine Link Core
`v24.set_network_object` product write twice against a disposable root
to prove that **the real exporter-generated revision snapshots** are
compatible with this read-only adapter, and its network-object count
changes without revealing native IP bytes.
RED pre-implementation test and GREEN data/role/HTTP/UI
regressions check deterministic count results, missing/duplicate/
malformed YAML, invalid revisions, case-specific nonleakage,
read-only DB snapshots and blocked rollback. Existing Web auth,
MFA, ingress, optional package install/remove/reinstall, and
off-line Web bundle build remain compulsory.

This feature is bounded preflight and **not actual historical
recovery readiness**. Final B5 requires trustworthy full semantic
diff, real encrypted archived state and credential handling,
appropriately authenticated and approved rollback, isolated restore
drill, verified per-product/browser/two-user Full User E2E on same
HEAD, exact frozen package/hash/provenance qualification and owner
release authorization. No customer or production database, SSH,
OS settings, credentials, browser session, package registry,
service lifecycle or previously safety-denied path was changed.
