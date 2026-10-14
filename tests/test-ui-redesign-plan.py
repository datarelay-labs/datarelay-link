#!/usr/bin/env python3
"""Plan integrity regressions only. No private packages or product mutation."""
from pathlib import Path
import copy
import importlib.util
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ui_plan', ROOT / 'scripts/check-ui-redesign-plan.py')
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class UiRedesignPlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads((ROOT / 'docs/ui-redesign-plan.json').read_text())

    def test_actual_plan_complete_structure(self):
        result = mod.validate(self.plan)
        self.assertEqual((result['wbs'], result['cui'], result['gaps']), (66,40,37))
        self.assertEqual((result['vendors'], result['uxe_versions']), (22,24))

    def test_cui_omission_rejected(self):
        self.plan['competitor_references'].pop()
        with self.assertRaisesRegex(mod.PlanError, 'CUI'):
            mod.validate(self.plan)

    def test_gap_omission_rejected(self):
        del self.plan['gap_to_wbs']['G-05']
        with self.assertRaisesRegex(mod.PlanError, 'coverage omission'):
            mod.validate(self.plan)

    def test_pdf_promise_omission_rejected(self):
        del self.plan['objective_to_wbs']['V1-C']
        with self.assertRaisesRegex(mod.PlanError, 'promise coverage'):
            mod.validate(self.plan)

    def test_missing_pass_criteria_rejected(self):
        self.plan['tasks'][5]['pass_criteria'] = ''
        with self.assertRaisesRegex(mod.PlanError, 'pass_criteria'):
            mod.validate(self.plan)

    def test_unknown_mapping_rejected(self):
        self.plan['gap_to_wbs']['G-01'] = ['M2-unrelated-work']
        with self.assertRaisesRegex(mod.PlanError, 'outside WBS'):
            mod.validate(self.plan)

    def test_cycle_rejected(self):
        self.plan['tasks'][0]['depends_on'] = ['UXR-0.2']
        with self.assertRaisesRegex(mod.PlanError, 'Cyclic'):
            mod.validate(self.plan)

    def test_silent_scope_unlock_rejected(self):
        self.plan['exclusive'] = False
        with self.assertRaisesRegex(mod.PlanError, 'Exclusive'):
            mod.validate(self.plan)

    def test_source_only_cannot_be_accepted(self):
        task = self.plan['tasks'][5]
        task['status'] = 'ACCEPTED'
        task['evidence'] = {'review_ref':'synthetic-test-only', 'source_commit':'a'*40}
        with self.assertRaisesRegex(mod.PlanError, 'deployed_source_head'):
            mod.validate(self.plan)

    def test_required_ui06_cannot_be_rejected(self):
        self.plan['competitor_references'][3]['disposition'] = 'NOT_ADOPTED'
        with self.assertRaisesRegex(mod.PlanError, 'Required UI-06'):
            mod.validate(self.plan)

    def test_legacy_uxe_version_cannot_disappear(self):
        self.plan['uxe_to_wbs'] = self.plan['uxe_to_wbs'][12:]
        with self.assertRaisesRegex(mod.PlanError, 'UXE'):
            mod.validate(self.plan)

    def test_incomplete_product_closure_rejected(self):
        with self.assertRaisesRegex(mod.PlanError, 'UI acceptance incomplete'):
            mod.validate(self.plan, closure=True)

    def test_historical_19_vendor_scope_preserved(self):
        self.plan['vendor_to_wbs'][0]['source'] = 'SUPPLEMENTARY'
        with self.assertRaisesRegex(mod.PlanError, 'Original19'):
            mod.validate(self.plan)

    def test_fake_scope_change_rejected(self):
        self.plan['exclusive'] = False
        self.plan['scope_change_approval'] = 'assumed approval'
        with self.assertRaisesRegex(mod.PlanError, 'explicit owner'):
            mod.validate(self.plan)

    def test_text_scope_flags_rejected(self):
        self.plan['exclusive'] = 'false'
        with self.assertRaisesRegex(mod.PlanError, 'boolean'):
            mod.validate(self.plan)

    def test_test_registered_once(self):
        source = (ROOT / 'tests/run-all.sh').read_text()
        self.assertEqual(source.count('python3 tests/test-ui-redesign-plan.py -q'), 1)

if __name__ == '__main__':
    unittest.main()
