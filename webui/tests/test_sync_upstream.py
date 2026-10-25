import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from webui.tools import sync_upstream

BASE = '1' * 40
UPSTREAM = '2' * 40
MERGE_BASE = '3' * 40


class MetadataTests(unittest.TestCase):
    def test_metadata_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'UPSTREAM_BASE'
            sync_upstream._write_metadata(path, UPSTREAM, UPSTREAM, BASE, '4' * 40, MERGE_BASE)
            self.assertEqual(sync_upstream._read_metadata(path), {
                'base': UPSTREAM, 'upstream': UPSTREAM, 'fork': BASE,
                'hooks': '4' * 40, 'merge_base': MERGE_BASE,
            })

    def test_series_comments_are_replaced_and_inserted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'series'
            path.write_text('# series\n# Base: old\n# Fork ref: old\n0001.patch target\n', encoding='utf-8')
            sync_upstream._write_series(path, UPSTREAM, BASE)
            text = path.read_text(encoding='utf-8')
            self.assertIn(f'# Base: {UPSTREAM}', text)
            self.assertIn(f'# Fork ref: {BASE}', text)
            self.assertEqual(text.count('# Base:'), 1)
            path.write_text('# series\n0001.patch target\n', encoding='utf-8')
            sync_upstream._write_series(path, UPSTREAM, BASE)
            self.assertEqual(path.read_text(encoding='utf-8').splitlines()[:3],
                             ['# series', f'# Base: {UPSTREAM}', f'# Fork ref: {BASE}'])

    def test_fork_owned_and_sensitive_paths(self):
        self.assertTrue(sync_upstream._is_owned('webui/server.py'))
        self.assertTrue(sync_upstream._is_owned('.github/workflows/upstream-sync.yml'))
        self.assertTrue(sync_upstream._is_owned('FORK.md'))
        self.assertFalse(sync_upstream._is_owned('dm/ios/project.yml'))
        self.assertIn('dm/ios/Sources/main.m', sync_upstream.SENSITIVE)
        self.assertIn('dm/games/profile_guess.py', sync_upstream.SENSITIVE)

    def test_summary_contains_stage_and_checks(self):
        text = sync_upstream._summary({
            'mode': 'review', 'stage': 'checks-failed', 'changed_paths': 2,
            'base_sha': BASE, 'upstream_sha': UPSTREAM, 'merge_base': MERGE_BASE,
            'branch': 'review/upstream-sync', 'sha': '4' * 40, 'hooks_sha': '5' * 40,
            'warnings': ['sensitive path'], 'checks': [{'name': 'tests', 'ok': False}],
            'error': 'boom', 'logs': '/tmp/logs',
        })
        self.assertIn('checks-failed', text)
        self.assertIn('FAIL `tests`', text)
        self.assertIn('sensitive path', text)


class SyncFlowTests(unittest.TestCase):
    def syncer(self, folder):
        return sync_upstream.Syncer('review', report_dir=Path(folder) / 'report', git_exe='git')

    def test_no_change_is_a_successful_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            value = self.syncer(folder)
            with patch.object(value, 'require_clean'), patch.object(value, 'ensure_remote'), \
                 patch.object(value, 'write_report'), \
                 patch.object(value, 'out', side_effect=[BASE, UPSTREAM]) as out, \
                 patch.object(value, 'is_ancestor', return_value=True):
                self.assertEqual(value.run(), 0)
            self.assertFalse(value.result['changed'])
            self.assertTrue(value.result['ok'])
            self.assertEqual(value.result['stage'], 'up-to-date')
            self.assertEqual(out.call_count, 2)

    def test_dirty_worktree_stops_before_any_branch(self):
        with tempfile.TemporaryDirectory() as folder:
            value = self.syncer(folder)
            with patch.object(value, 'require_clean', side_effect=sync_upstream.SyncError(
                    'dirty', stage='dirty-worktree', code=2)), patch.object(value, 'write_report'):
                self.assertEqual(value.run(), 2)
            self.assertEqual(value.result['stage'], 'dirty-worktree')
            self.assertFalse(value.result['changed'])

    def test_rewritten_upstream_stops_before_worktrees(self):
        with tempfile.TemporaryDirectory() as folder:
            value = self.syncer(folder)
            with patch.object(value, 'require_clean'), patch.object(value, 'ensure_remote'), \
                 patch.object(value, 'write_report'), \
                 patch.object(value, 'out', side_effect=[BASE, UPSTREAM, MERGE_BASE]), \
                 patch.object(value, 'is_ancestor', side_effect=[False, False]), \
                 patch.object(value, 'prepare_worktrees') as prepare:
                self.assertEqual(value.run(), 2)
            prepare.assert_not_called()
            self.assertEqual(value.result['stage'], 'upstream-rewritten')
            self.assertTrue(value.result['changed'])

    def test_merge_conflict_keeps_no_sync_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            value = self.syncer(folder)
            with patch.object(value, 'require_clean'), patch.object(value, 'ensure_remote'), \
                 patch.object(value, 'write_report'), \
                 patch.object(value, 'out', side_effect=[BASE, UPSTREAM, MERGE_BASE, '']), \
                 patch.object(value, 'is_ancestor', side_effect=[False, True]), \
                 patch.object(sync_upstream, '_read_metadata', return_value={}), \
                 patch.object(value, 'prepare_worktrees'), \
                 patch.object(value, 'merge', side_effect=sync_upstream.SyncError(
                     'merge conflict', stage='merge-conflict', code=2)):
                self.assertEqual(value.run(), 2)
            self.assertEqual(value.result['stage'], 'merge-conflict')
            self.assertFalse(value.result['ok'])
            self.assertEqual(value.result['sha'], '')

    def test_report_is_written_on_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            value = self.syncer(folder)
            with patch.object(value, 'require_clean'), patch.object(value, 'ensure_remote'), \
                 patch.object(value, 'out', side_effect=[BASE, UPSTREAM]), \
                 patch.object(value, 'is_ancestor', return_value=True):
                self.assertEqual(value.run(), 0)
            result = json.loads((Path(folder) / 'report/result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['stage'], 'up-to-date')
            self.assertEqual(result['base_sha'], BASE)
            self.assertTrue((Path(folder) / 'report/summary.md').is_file())


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(__file__).resolve().parents[2] / '.github/workflows/upstream-sync.yml'
        self.text = self.path.read_text(encoding='utf-8')

    def test_triggers_branches_and_permissions(self):
        self.assertIn("cron: '17 3 * * *'", self.text)
        self.assertIn('workflow_dispatch:', self.text)
        self.assertIn('options: [review, auto]', self.text)
        self.assertIn('auto/upstream-sync', self.text)
        self.assertIn('review/upstream-sync', self.text)
        self.assertIn('hooks/upstream-sync', self.text)
        self.assertIn('contents: write', self.text)
        self.assertIn('pull-requests: write', self.text)
        self.assertIn('issues: write', self.text)
        self.assertIn('group: upstream-sync', self.text)
        self.assertIn('cancel-in-progress: false', self.text)

    def test_no_token_is_persisted_for_the_tests(self):
        self.assertIn('persist-credentials: false', self.text)
        self.assertIn('include-hidden-files: true', self.text)
        self.assertIn('DRY_RUN', self.text)
        self.assertIn('--mode "$MODE"', self.text)
        self.assertIn('webui/requirements-sync-ci.txt', self.text)
        self.assertIn('secrets.SYNC_TOKEN', self.text)
        self.assertIn('WORKFLOW_CHANGES', self.text)

    def test_actions_are_pinned_to_commits(self):
        uses = re.findall(r'uses:\s+([^\s#]+)', self.text)
        self.assertTrue(uses)
        for value in uses:
            self.assertRegex(value, r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$')

    def test_main_is_never_force_pushed(self):
        self.assertNotIn('pull_request_target', self.text)
        for line in self.text.splitlines():
            if 'git push' in line and 'refs/heads/main' in line:
                self.assertNotIn('--force', line)
        self.assertIn('git merge-base --is-ancestor', self.text)
        self.assertIn('git diff --name-only "$BASE_SHA..$SYNC_SHA" -- .github/workflows/upstream-sync.yml .gitattributes', self.text)
        self.assertIn("grep -v '^webui/patches/'", self.text)

    def test_failure_and_review_notifications_exist(self):
        self.assertIn('gh issue create', self.text)
        self.assertIn('gh pr create', self.text)
        self.assertIn('gh pr edit', self.text)
        self.assertIn('--draft', self.text)


if __name__ == '__main__':
    unittest.main()
