#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
TREE="$WORK/tree"
mkdir -p "$TREE/etc/drlink/pki" "$TREE/var/lib/drlink/enrollments" "$TREE/var/lib/drlink/bootstrap"
python3 "$ROOT/lib/frp_pki.py" ensure --pki-dir "$TREE/etc/drlink/pki" --public-host example.test >/dev/null
python3 - "$TREE" <<'PY'
import json,sys
from pathlib import Path
r=Path(sys.argv[1])
(r/'etc/drlink/config.json').write_text(json.dumps({
 'enrollments_dir':'/var/lib/drlink/enrollments',
 'bootstrap_dir':'/var/lib/drlink/bootstrap',
 'tls_ca_cert':'/etc/drlink/pki/ca.crt',
 'allocator_public_url':'https://example.test/enroll',
 'client_installer_url':'https://example.test/bootstrap-client.sh',
 'bootstrap_hostname':'bootstrap.example.test',
})+'\n')
PY
export FRP_DEPLOY_TEST_ROOT="$TREE"
python3 "$ROOT/tools/frp-enroll-bulk" --count 3 --label-prefix node >"$WORK/count.csv" 2>"$WORK/count.err"
grep -q 'redirected output contains pending Bootstrap locators' "$WORK/count.err"
cat >"$WORK/input.csv" <<'CSV'
label,note
ssh-node,remote shell
inventory-only,no service
CSV
python3 "$ROOT/tools/frp-enroll-bulk" --csv "$WORK/input.csv" >"$WORK/input.out" 2>"$WORK/input.err"
python3 - "$WORK/count.csv" "$WORK/input.out" "$TREE/var/lib/drlink/bootstrap" <<'PY'
import csv,json,re,sys,hashlib
from pathlib import Path
rows=[]
for name in sys.argv[1:3]:
    with open(name,newline='') as f:
        batch=list(csv.DictReader(f))
        assert all(row.get('expires') for row in batch)
        assert all(row.get('enrollment_id') for row in batch)
        assert all(row.get('bootstrap_command') for row in batch)
        assert len({row['enrollment_id'] for row in batch}) == len(batch)
        assert len({row['label'] for row in batch})==len(batch)
        rows.extend(batch)
assert len(rows)==5
tickets=[]
for row in rows:
    m=re.fullmatch(r"curl -kfsS https://bootstrap\.example\.test/([A-Za-z0-9_-]{6})\|sudo bash", row['bootstrap_command'])
    if m:
        tickets.append(m.group(1))
        continue
    raise AssertionError('non-short Zero-Touch command generated')
assert len(set(tickets))==5
records=[json.loads(p.read_text()) for p in Path(sys.argv[3]).glob('*.json')]
assert len(records)==5
assert len({r['id'] for r in records})==5
assert len({r['enrollment_id'] for r in records})==5
# CSV identifiers must be the same public selectors returned by
# `show enrollments`, not paired internal Enrollment Code IDs (F026).
public_ids = {row['enrollment_id'] for row in rows}
persisted_ids = {rec['id'] for rec in records}
assert public_ids == persisted_ids, (public_ids, persisted_ids)
assert {rec['enrollment_id'] for rec in records}.isdisjoint(public_ids)
for ticket,row in zip(tickets,rows):
    digest=hashlib.sha256(ticket.encode()).hexdigest()
    index=json.loads((Path(sys.argv[3])/'entry-locators'/(digest+'.json')).read_text())
    assert index['ticket_id']==row['enrollment_id']
    record=next(r for r in records if r['id']==index['ticket_id'])
    assert record['entry_locator_hash']==digest
    assert record['entry_approval']['platform']=='linux'
    assert ticket not in json.dumps(record)
assert any(r.get('services')==[] for r in records)
assert all(r.get('services') == [] for r in records)
PY

# A stale former official public installer URL must never leak into newly issued
# bulk enrollment commands. Resolve it to the Server-local qualified artifact,
# matching the single-enrollment and Server Settings surfaces.
python3 - "$TREE/etc/drlink/config.json" <<'PY'
import json,sys
from pathlib import Path
path=Path(sys.argv[1])
cfg=json.loads(path.read_text())
cfg['client_installer_url']='https://raw.githubusercontent.com/datarelay-labs/datarelay-link/1111111111111111111111111111111111111111/dist/bootstrap-client.sh'
path.write_text(json.dumps(cfg)+'\n')
PY
python3 "$ROOT/tools/frp-enroll-bulk" --count 1 --label-prefix stale-source >"$WORK/stale-source.csv" 2>"$WORK/stale-source.err"
grep -Fq 'https://bootstrap.example.test/' "$WORK/stale-source.csv"
! grep -Fq 'raw.githubusercontent.com' "$WORK/stale-source.csv"
! grep -Fq '1111111111111111111111111111111111111111' "$WORK/stale-source.csv"
echo "PASS BULK_QUALIFIED_INSTALLER_SOURCE"

# F026: a published CSV row must address the same user-visible enrollment
# through inventory, detail and operator revoke (not just stored paired IDs).
PUBLIC_ID="$(python3 - "$WORK/count.csv" <<'PY'
import csv,sys
with open(sys.argv[1], newline='') as handle:
    print(next(csv.DictReader(handle))['enrollment_id'])
PY
)"
python3 "$ROOT/tools/frp-enrollments" >"$WORK/public-enrollments.txt"
grep -Fq "$PUBLIC_ID" "$WORK/public-enrollments.txt"
python3 "$ROOT/tools/frp-enrollments" "$PUBLIC_ID" >"$WORK/public-enrollment-detail.txt"
grep -Fq "ID      : $PUBLIC_ID" "$WORK/public-enrollment-detail.txt"
python3 "$ROOT/tools/frp-enrollment-revoke" "$PUBLIC_ID" >"$WORK/public-revoke.txt"
grep -Fq "Revoked enrollment $PUBLIC_ID" "$WORK/public-revoke.txt"
[[ "$(python3 "$ROOT/tools/frp-enrollments" "$PUBLIC_ID" --state-only)" == 'revoked' ]]
echo "PASS BULK_CSV_PUBLIC_SELECTOR_AND_REVOKE"

# Invalid input must point to the public wizard and never emit internal argparse flags.
if python3 "$ROOT/tools/frp-enroll-bulk" --count 11 >"$WORK/count-invalid.out" 2>"$WORK/count-invalid.err"; then
  echo "FAIL over-capacity batch was accepted" >&2
  exit 1
fi
grep -q 'Retry: sudo drlink set enrollment bulk' "$WORK/count-invalid.err"
! grep -q 'frp-enroll-bulk\|usage:' "$WORK/count-invalid.err"
echo "PASS BULK_PUBLIC_ERROR_GUIDANCE"

# Pre-validate all rows: a bad later row issues zero tickets.
BAD="$WORK/bad.csv"
cat >"$BAD" <<'CSV'
label,note
good-one,ok
BAD LABEL!!,no
CSV
BEFORE_TICKETS="$(find "$TREE/var/lib/drlink/bootstrap" -name '*.json' | wc -l)"
if python3 "$ROOT/tools/frp-enroll-bulk" --csv "$BAD" >"$WORK/bad.out" 2>"$WORK/bad.err"; then
  echo "FAIL bad row accepted" >&2
  exit 1
fi
AFTER_TICKETS="$(find "$TREE/var/lib/drlink/bootstrap" -name '*.json' | wc -l)"
[[ "$AFTER_TICKETS" -eq "$BEFORE_TICKETS" ]] || { echo "FAIL bad row issued tickets" >&2; exit 1; }
echo "PASS BULK_PREVALIDATE_ALL"
echo "PASS BULK_BAD_ROW_ZERO_ISSUED"

if python3 "$ROOT/tools/frp-enroll-bulk" --csv "$WORK/missing.csv" >"$WORK/missing.out" 2>"$WORK/missing.err"; then
  echo "FAIL missing CSV accepted" >&2
  exit 1
fi
! grep -q 'Traceback' "$WORK/missing.err" || { echo "FAIL missing CSV traceback" >&2; exit 1; }
grep -q 'cannot read CSV' "$WORK/missing.err"
[[ "$(find "$TREE/var/lib/drlink/bootstrap" -name '*.json' | wc -l)" -eq "$BEFORE_TICKETS" ]]
echo "PASS BULK_MISSING_CSV_READONLY_RECOVERY"

# Mid-batch failure rolls back only this batch.
EXISTING="$(ls "$TREE/var/lib/drlink/bootstrap"/*.json | wc -l)"
if FRP_ENROLL_BULK_HOOK_FAIL_AFTER=1 \
  python3 "$ROOT/tools/frp-enroll-bulk" --count 3 --label-prefix mid \
  >"$WORK/mid.out" 2>"$WORK/mid.err"; then
  echo "FAIL mid-batch succeeded" >&2
  exit 1
fi
AFTER_MID="$(ls "$TREE/var/lib/drlink/bootstrap"/*.json | wc -l)"
[[ "$AFTER_MID" -eq "$EXISTING" ]] || { echo "FAIL mid-batch left tickets" >&2; exit 1; }
python3 - "$TREE/var/lib/drlink/bootstrap" <<'PY' || { echo "FAIL orphan handle index" >&2; exit 1; }
import json
from pathlib import Path
root = Path(__import__('sys').argv[1])
assert not list((root/'handles').glob('*.json'))
live={json.loads(p.read_text())['entry_locator_hash'] for p in root.glob('*.json')}
# Rolled-back issued locators may remain reserved as tombstones; no live
# lookup may resolve a missing ticket.
for index in (root/'entry-locators').glob('*.json'):
    record=json.loads(index.read_text())
    target=root/(record['ticket_id']+'.json')
    if target.exists():
        assert index.stem in live
        assert json.loads(target.read_text())['entry_locator_hash']==index.stem
print('ok')
PY
echo "PASS BULK_MID_FAILURE_ROLLBACK"
echo "PASS BULK_EXISTING_RECORDS_PRESERVED"
echo "PASS BULK_ATOMICITY_TEST"

echo "ENROLL_BULK_TEST=PASS"
