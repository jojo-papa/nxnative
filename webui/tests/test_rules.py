"""The rules document and the rule registry must agree.

Rule R-13: a rule change cannot land without the document changing with it.
"""
import unittest
from pathlib import Path

from webui.tools import rules

REPO = Path(__file__).resolve().parents[2]


class RuleRegistryTests(unittest.TestCase):
    def test_every_rule_has_its_parts(self):
        ids = [rule['id'] for rule in rules.RULES]
        self.assertEqual(len(ids), len(set(ids)), 'rule ids must be unique')
        for rule in rules.RULES:
            for field in ('id', 'section', 'status', 'title', 'rule', 'check', 'fix'):
                self.assertTrue(rule.get(field), f'{rule["id"]}: {field} is empty')
            self.assertIn(rule['status'], (rules.ACTIVE, rules.PLANNED), rule['id'])
            self.assertIn(rule['section'], [name for name, _title in rules.SECTIONS], rule['id'])

    def test_active_rules_have_a_check(self):
        for rule in rules.RULES:
            if rule['status'] == rules.ACTIVE:
                self.assertIn(rule['id'], rules.CHECKS,
                              f'{rule["id"]} is active but has no check function')

    def test_document_matches_the_registry(self):
        result = rules.check_r13_doc_matches_registry()
        self.assertTrue(result[0][0], result[0][1])

    def test_document_lists_every_rule(self):
        text = (REPO / 'RULES.md').read_text(encoding='utf-8')
        for rule in rules.RULES:
            self.assertIn(f'**{rule["id"]}**', text, f'RULES.md is missing {rule["id"]}')
            self.assertIn(rule['check'], text, f'RULES.md is missing the check of {rule["id"]}')

    def test_feature_table_is_well_formed(self):
        features = rules.load_features()
        self.assertTrue(features, 'webui/features.tsv is empty')
        for fid, feature in features.items():
            self.assertIn(feature['scope'], ('runtime', 'build'), fid)
            self.assertTrue(feature['label'], f'{fid}: no label')
            self.assertTrue(feature['note'], f'{fid}: no note')
            if feature['scope'] == 'runtime':
                self.assertTrue(feature['env'], f'{fid}: a runtime feature needs an env variable')
                self.assertNotEqual(feature['env'], '-', fid)
            else:
                self.assertEqual(feature['env'], '-', f'{fid}: a build feature has no env variable')

    def test_patch_table_is_well_formed(self):
        meta = rules.load_patch_meta()
        self.assertTrue(meta, 'webui/patches/features.tsv is empty')
        for name, row in meta.items():
            self.assertIn(row['kind'], ('base', 'custom'), name)
            self.assertTrue(row['reason'], f'{name}: no reason')
            for need in row['needs']:
                self.assertIn(need, meta, f'{name}: needs {need}, which has no row')

    def test_features_referenced_by_patches_exist(self):
        features = rules.load_features()
        for name, row in rules.load_patch_meta().items():
            if row['feature'] in ('', '-'):
                continue
            self.assertIn(row['feature'], features, f'{name}: unknown feature {row["feature"]}')

    def test_rule_checks_pass(self):
        for rule in rules.RULES:
            function = rules.CHECKS.get(rule['id'])
            if function is None:
                continue
            results = function()
            self.assertTrue(all(ok for ok, _ in results),
                            f'{rule["id"]}: ' + '; '.join(detail for ok, detail in results if not ok))


if __name__ == '__main__':
    unittest.main()
