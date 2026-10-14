#!/usr/bin/env python3
"""Check the exclusive UI WBS/coverage/evidence structure, NOT product behavior.

No network, credentials, mutation or dependency installation. Actual artifacts
and user observations must still be audited; populated fields alone are not proof.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'docs/ui-redesign-plan.json'
COUNTS = [5, 10, 10, 11, 10, 7, 5, 8]
EXPECTED_TASKS = {f'UXR-{m}.{n}' for m, count in enumerate(COUNTS) for n in range(1, count + 1)}
EXPECTED_GOALS = ({f'UX-{n}' for n in range(1, 9)} | {f'UI-{n:02}' for n in range(1, 7)}
    | {f'UXB-{n:02}' for n in range(7)} | {'V1-A','V1-B','V1-C','V2-A','V2-B','V3-A','V3-B'}
    | {f'WU{n}' for n in range(1,5)} | {'UX-P1-A','UX-P1-B','UX-P1-C'})
STATES = {'SPEC_BOUND','IMPLEMENTED','DEV_DEPLOYED','BROWSER_VERIFIED','ACCEPTED','BLOCKED','APPROVAL_REQUIRED'}

class PlanError(ValueError):
    pass

def need(condition: bool, message: str) -> None:
    if not condition:
        raise PlanError(message)

def nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())

def validate(plan: dict, *, closure: bool = False) -> dict:
    need(isinstance(plan, dict) and plan.get('schema_version') == 1, 'Invalid plan schema')
    need(plan.get('repository') == 'datarelay-labs/datarelay-link', 'Wrong repository')
    need((plan.get('roadmap'), plan.get('packet'), plan.get('pr')) == (184, 182, 206), 'Wrong canonical issue/PR')
    need(plan.get('implementer') == 'CHATGPT_CHAT', 'Implementer drift')
    need(plan.get('priority') == 'P0_EXCLUSIVE_UI_REDESIGN', 'Priority drift')
    scope_change = plan.get('scope_change_approval')
    need(type(plan.get('scope_complete')) is bool and type(plan.get('exclusive')) is bool, 'Scope flags must be boolean')
    if scope_change is not None:
        need(isinstance(scope_change, dict) and nonempty(scope_change.get('evidence_ref')) and nonempty(scope_change.get('owner_instruction')), 'Scope change requires explicit owner evidence')
    if not plan.get('scope_complete') and not scope_change:
        need(plan.get('exclusive') is True, 'Exclusive UI scope cannot be silently released')
    ms = plan.get('milestones', [])
    need(len(ms) == 8 and {m.get('id') for m in ms} == {f'UXR-{n}' for n in range(8)}, 'Milestone omission')
    tasks = plan.get('tasks', [])
    need(len(tasks) == 66 and {t.get('id') for t in tasks} == EXPECTED_TASKS, 'WBS omission or duplicate')
    indexed = {t['id']: t for t in tasks}
    need(plan.get('next_task') in indexed, 'Next task is outside the exclusive UI WBS')
    for t in tasks:
        ident = t['id']
        need(t.get('milestone') == ident.rsplit('.', 1)[0], 'Task milestone mismatch: ' + ident)
        for field in ('title','deliverable_and_removal','verification','pass_criteria'):
            need(nonempty(t.get(field)), 'Missing task ' + field + ': ' + ident)
        need(isinstance(t.get('code_anchors'), list) and all(nonempty(a) for a in t['code_anchors']), 'Missing code anchors: ' + ident)
        need(t.get('status') in STATES, 'Invalid task status: ' + ident)
        need(t.get('owner') == 'CHATGPT_CHAT', 'Task owner drift: ' + ident)
        need(isinstance(t.get('depends_on'), list), 'Invalid dependencies: ' + ident)
        need(all(x in indexed and x != ident for x in t['depends_on']), 'Invalid dependency: ' + ident)
        if ident.startswith('UXR-6.'):
            need(t.get('approval_required') is True, 'UI-06 security dependency silently removed')
        if t.get('status') == 'ACCEPTED':
            ev = t.get('evidence', {})
            need(isinstance(ev, dict) and nonempty(ev.get('review_ref')), 'Accepted task lacks reviewed evidence: ' + ident)
            if ident.startswith('UXR-0.') or ident == 'UXR-6.1':
                need(nonempty(ev.get('saved_record')), 'Governance/design evidence missing: ' + ident)
            else:
                for field in ('source_commit','deployed_source_head','served_asset_sha','focused_tests','browser_evidence','interaction_result','deviation_disposition'):
                    need(nonempty(ev.get(field)), 'Accepted task lacks ' + field + ': ' + ident)
                need(re.fullmatch(r'[0-9a-f]{40}', ev['source_commit']) is not None, 'Invalid evidence commit: ' + ident)
                need(ev['source_commit'] == ev['deployed_source_head'], 'Deployed source differs from tested source: ' + ident)
                need(re.fullmatch(r'[0-9a-f]{64}', ev['served_asset_sha']) is not None, 'Invalid asset SHA: ' + ident)
            if t.get('approval_required'):
                need(nonempty(ev.get('approval_ref')), 'UI-06 approval evidence missing: ' + ident)
    visiting, done = set(), set()
    def walk(key):
        need(key not in visiting, 'Cyclic WBS dependency: ' + key)
        if key in done:
            return
        visiting.add(key)
        for dep in indexed[key]['depends_on']:
            walk(dep)
        visiting.remove(key)
        done.add(key)
    for key in indexed:
        walk(key)
    def mapped(values, label):
        need(isinstance(values, list) and bool(values), 'Unmapped requirement: ' + label)
        need(all(x in indexed for x in values), 'Mapping points outside WBS: ' + label)
    gaps = plan.get('gap_to_wbs', {})
    need(set(gaps) == {f'G-{n:02}' for n in range(1, 38)}, 'G-01..37 coverage omission')
    for key, values in gaps.items():
        mapped(values, key)
    goals = plan.get('objective_to_wbs', {})
    need(set(goals) == EXPECTED_GOALS, 'Prior/new promise coverage omission')
    for key, values in goals.items():
        mapped(values, key)
    refs = plan.get('competitor_references', [])
    need(len(refs) == 40 and {r.get('id') for r in refs} == {f'CUI-{n:03}' for n in range(1,41)}, 'CUI-001..040 coverage omission')
    for r in refs:
        mapped(r.get('wbs'), r['id'])
        need(nonempty(r.get('reason')), 'Missing adoption/rejection reason: ' + r['id'])
        need(r.get('disposition') in {'ADOPT_PRESERVE_AND_VERIFY','GATED_REQUIRED','NOT_ADOPTED'}, 'Invalid source disposition')
        need(all(g in gaps for g in r.get('gaps', [])), 'Unknown referenced gap')
        if r['id'] in {'CUI-004','CUI-005'}:
            need(r['disposition'] == 'GATED_REQUIRED' and any(x.startswith('UXR-6.') for x in r['wbs']), 'Required UI-06 dropped')
    vendors = plan.get('vendor_to_wbs', [])
    need(len(vendors) == 22 and len({v.get('name') for v in vendors}) == 22, 'Combined vendor coverage omission')
    need(sum(v.get('source') == 'LEGACY19' for v in vendors) == 19, 'Original19 matrix omitted')
    for v in vendors:
        mapped(v.get('wbs'), v['name'])
    scenarios = plan.get('uxe_to_wbs', [])
    expected = {f'{prefix}-UXE-{i:02}' for prefix in ('LEGACY19','CURRENT') for i in range(1,13)}
    need(len(scenarios) == 24 and {s.get('id') for s in scenarios} == expected, 'Versioned UXE semantic coverage omission')
    for s in scenarios:
        need(nonempty(s.get('meaning')), 'Missing scenario meaning')
        mapped(s.get('wbs'), s['id'])
    sources = plan.get('source_register', [])
    need(len(sources) >= 15, 'Source register incomplete')
    need(any(s.get('sha256') == '10dc9a02f969b4268d77bd2a439d055ba1fd0a2827b77ebdf77b5531eb4ff300' for s in sources), 'Approved proposal identity omitted')
    if closure or plan.get('scope_complete'):
        pending = [t['id'] for t in tasks if t['status'] != 'ACCEPTED']
        need(not pending, 'UI acceptance incomplete: ' + ','.join(pending[:8]))
        owner = plan.get('owner_acceptance')
        need(isinstance(owner, dict) and nonempty(owner.get('evidence_ref')) and nonempty(owner.get('source_head')), 'Final owner acceptance missing')
    return {'milestones':len(ms),'wbs':len(tasks),'cui':len(refs),'gaps':len(gaps),'vendors':len(vendors),'uxe_versions':len(scenarios),'accepted':sum(t['status']=='ACCEPTED' for t in tasks),'exclusive':plan['exclusive']}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--closure', action='store_true')
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.plan.read_text()), closure=args.closure)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('UI_REDESIGN_PLAN=FAIL: ' + str(exc), file=sys.stderr)
        return 1
    print('UI_REDESIGN_PLAN_STRUCTURE=PASS ' + json.dumps(result, sort_keys=True))
    print('PRODUCT_UI_ACCEPTANCE=NOT_INFERRED_FROM_PLAN_VALIDATION')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
