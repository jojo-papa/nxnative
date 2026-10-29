"""The patch rebase engine: what it decides and why.

Rule R-02: when the new baseline already carries our change, drop our patch
and keep the baseline's version.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from webui import diffapply
from webui.tools import patch_rebase


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                          text=True, encoding='utf-8', errors='replace', check=True)


class RebaseEngineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.repo = Path(self.folder.name)
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.email', 'test@example.com')
        git(self.repo, 'config', 'user.name', 'test')
        self.write('f.txt', 'one\ntwo\nthree\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'base')
        self.old_base = git(self.repo, 'rev-parse', 'HEAD').stdout.strip()

    def tearDown(self):
        self.folder.cleanup()

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def commit(self, message):
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', message)
        return git(self.repo, 'rev-parse', 'HEAD').stdout.strip()

    def patch_file(self, name, before, after):
        """A patch file that turns *before* into *after*."""
        old = before.encode()
        new = after.encode()
        body = []
        for line in __import__('difflib').unified_diff(before.splitlines(), after.splitlines(),
                                                      lineterm='', n=3):
            body.append(line)
        text = (f'--- a/f.txt\n+++ b/f.txt\n' + '\n'.join(body) + '\n')
        path = self.repo / name
        path.write_text(text, encoding='utf-8')
        return path

    def judge(self, patch_path, new_base):
        return patch_rebase.judge_patch(patch_path, 'f.txt', self.old_base, new_base, repo=self.repo)

    def test_unchanged_file_is_kept(self):
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\nTWO\nthree\n')
        self.write('f.txt', 'one\ntwo\nthree\n')
        new_base = self.commit('upstream touched another file')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.KEEP)
        self.assertEqual(verdict['reason'], '上游没有动这个文件')

    def test_baseline_took_our_change_is_dropped(self):
        """Rule R-02: the baseline already has it, so our patch goes away."""
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\nTWO\nthree\n')
        self.write('f.txt', 'one\nTWO\nthree\n')
        new_base = self.commit('upstream took our change')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.DROP)

    def test_upstream_shift_is_followed(self):
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\ntwo\nthree\nfour\n')
        self.write('f.txt', 'zero\none\ntwo\nthree\n')
        new_base = self.commit('upstream added a line above')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.KEEP)
        regenerated = verdict['patch_bytes'].decode('utf-8')
        self.assertIn('+four', regenerated)

    def test_baseline_already_has_it_is_dropped(self):
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\nTWO\nthree\n')
        self.write('f.txt', 'one\nTWO\nthree\n')
        new_base = self.commit('upstream made the same change')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.DROP)

    def test_unrelated_change_needs_a_person(self):
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\nTWO\nthree\n')
        self.write('f.txt', 'one\nTWO-CHANGED\nthree\n')
        new_base = self.commit('upstream changed the same line differently')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.MANUAL)
        self.assertEqual(len(verdict['failed_hunks']), 1)
        self.assertEqual(verdict['failed_hunks'][0]['added'], ['TWO'])

    def test_partial_when_one_hunk_is_upstreamed(self):
        """Two hunks far apart: upstream took one, the other still stands."""
        before = ''.join(f'line{i}\n' for i in range(1, 21))
        after = before.replace('line2\n', 'LINE2\n').replace('line15\n', 'LINE15\n')
        patch = self.patch_file('p.patch', before, after)
        self.write('f.txt', before.replace('line2\n', 'LINE2\n'))
        new_base = self.commit('upstream took the first hunk')
        verdict = self.judge(patch, new_base)
        self.assertEqual(verdict['verdict'], patch_rebase.PARTIAL)
        self.assertEqual(verdict['dropped_hunks'], [0])
        self.assertIn('+LINE15', verdict['patch_bytes'].decode('utf-8'))

    def test_regenerated_patch_applies_to_the_new_base(self):
        patch = self.patch_file('p.patch', 'one\ntwo\nthree\n', 'one\ntwo\nthree\nfour\n')
        self.write('f.txt', 'zero\none\ntwo\nthree\n')
        new_base = self.commit('upstream added a line above')
        verdict = self.judge(patch, new_base)
        base = (self.repo / 'f.txt').read_text(encoding='utf-8').encode('utf-8')
        applied = diffapply.apply_bytes(base, verdict['patch_bytes'], 'f.txt')
        self.assertIn(b'four', applied)


class PatchFormatTests(unittest.TestCase):
    def test_make_patch_round_trip(self):
        old = b'one\ntwo\nthree\n'
        new = b'one\nTWO\nthree\nfour\n'
        patch = patch_rebase.make_patch('f.txt', old, new)
        self.assertIsNotNone(patch)
        self.assertTrue(patch.endswith(b'\n'))
        self.assertNotIn(b'\r\n', patch)
        applied = diffapply.apply_bytes(old, patch, 'f.txt')
        self.assertEqual(applied, new)

    def test_added_runs_and_upstream_detection(self):
        ops = [(' ', 'a'), ('+', 'b'), ('+', 'c'), (' ', 'd')]
        self.assertEqual(patch_rebase.added_runs(ops), [['b', 'c']])
        hunk = (1, ops)
        self.assertTrue(patch_rebase.hunk_is_upstreamed(hunk, ['x', 'b', 'c', 'd']))
        self.assertFalse(patch_rebase.hunk_is_upstreamed(hunk, ['x', 'b', 'd']))

    def test_apply_hunks_moves_with_the_baseline(self):
        lines = ['zero', 'one', 'two', 'three']
        hunks = [(2, [(' ', 'one'), ('+', 'ONE')])]
        result, applied, failed = patch_rebase.apply_hunks(lines, hunks)
        self.assertEqual(applied, [0])
        self.assertEqual(failed, [])
        self.assertEqual(result, ['zero', 'one', 'ONE', 'two', 'three'])


if __name__ == '__main__':
    unittest.main()
