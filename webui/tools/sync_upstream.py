#!/usr/bin/env python3
"""Prepare an upstream sync branch, or report that upstream is already merged.

The GitHub Actions workflow uses this to build `auto/upstream-sync` and
`review/upstream-sync`. It never pushes main itself: the workflow fast-forwards
main only after the checks pass. A failed sync leaves its worktrees and logs in
place for inspection.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import staging
from webui.repo import REPO, UPSTREAM_URL, ensure_git_exclude


BRANCHES = {'auto': 'auto/upstream-sync', 'review': 'review/upstream-sync'}
HOOKS_BRANCH = 'hooks/upstream-sync'
FORK_OWNED = ('.github/workflows/upstream-sync.yml', 'webui/', 'FORK.md', '.gitattributes',
              'start-webui.sh', 'start-webui.command', 'start-webui.bat')
MANUAL_REVIEW = ('dm/ios/project.yml',)
SENSITIVE = set(staging.OVERLAY_TARGETS) | {target for _, target in staging.patch_queue()} | {
    'dm/games/profile_guess.py', 'scripts/build_ipa_from_nsp.py',
}
BOT_NAME = 'github-actions[bot]'
BOT_EMAIL = '41898282+github-actions[bot]@users.noreply.github.com'


class SyncError(Exception):
    def __init__(self, message, stage='error', code=2):
        super().__init__(message)
        self.stage = stage
        self.code = code


def _branch_name(mode):
    try:
        return BRANCHES[mode]
    except KeyError:
        raise SyncError(f'unknown mode: {mode}', stage='arguments', code=2) from None


def _is_owned(path):
    return any(path == item.rstrip('/') or path.startswith(item) for item in FORK_OWNED)


def _read_metadata(path):
    values = {}
    path = Path(path)
    if not path.is_file():
        return values
    for line in path.read_text(encoding='utf-8').splitlines():
        fields = line.split(None, 1)
        if len(fields) == 2 and not fields[0].startswith('#'):
            values[fields[0]] = fields[1].strip()
    return values


def _write_metadata(path, base, upstream, fork, hooks, merge_base):
    Path(path).write_text(
        f'base {base}\nupstream {upstream}\nfork {fork}\nhooks {hooks}\nmerge_base {merge_base}\n',
        encoding='utf-8', newline='\n')


def _write_series(path, upstream, fork):
    path = Path(path)
    lines = path.read_text(encoding='utf-8').splitlines()
    wanted = {'# Base:': f'# Base: {upstream}', '# Fork ref:': f'# Fork ref: {fork}'}
    out, seen = [], set()
    for line in lines:
        for prefix, replacement in wanted.items():
            if line.startswith(prefix):
                out.append(replacement)
                seen.add(prefix)
                break
        else:
            out.append(line)
    missing = [replacement for prefix, replacement in wanted.items() if prefix not in seen]
    if missing:
        position = 1 if out and out[0].startswith('#') else 0
        out[position:position] = missing
    path.write_text('\n'.join(out) + '\n', encoding='utf-8', newline='\n')


def _summary(result):
    checks = result.get('checks') or []
    lines = [
        f"# Upstream sync ({result.get('mode', '?')})", '',
        f"- Result: **{result.get('stage', '?')}**",
        f"- Base: `{result.get('base_sha') or '?'}`",
        f"- Upstream: `{result.get('upstream_sha') or '?'}`",
        f"- Merge base: `{result.get('merge_base') or '?'}`",
        f"- Branch: `{result.get('branch') or '?'}`",
        f"- Sync commit: `{result.get('sha') or 'none'}`",
        f"- Hooks commit: `{result.get('hooks_sha') or 'none'}`",
        f"- Changed paths: {result.get('changed_paths', 0)}",
    ]
    if result.get('warnings'):
        lines += ['', '## Warnings', *[f'- {item}' for item in result['warnings']]]
    if checks:
        lines += ['', '## Checks', *[f"- {'PASS' if item.get('ok') else 'FAIL'} `{item['name']}`" for item in checks]]
    if result.get('error'):
        lines += ['', '## Error', '', '```', str(result['error']), '```']
    if result.get('logs'):
        lines += ['', f"Logs: `{result['logs']}`"]
    return '\n'.join(lines) + '\n'


class Syncer:
    def __init__(self, mode, *, base_ref='main', upstream_ref='upstream/main', fetch=False,
                 dry_run=False, keep_worktrees=False, push=False, report_dir=None,
                 git_exe=None):
        self.mode = mode
        self.branch = _branch_name(mode)
        self.base_ref = base_ref
        self.upstream_ref = upstream_ref
        self.fetch = fetch
        self.dry_run = dry_run
        self.keep_worktrees = keep_worktrees
        self.push = push
        self.root = Path(REPO).resolve()
        self.git_exe = git_exe or os.environ.get('GIT_EXE') or shutil.which('git')
        self.report_dir = Path(report_dir or (self.root / '.webui-data/upstream-sync/report')).resolve()
        self.logs_dir = self.report_dir / 'logs'
        self.trees_dir = self.root / '.webui-data'
        self.sync_tree = self.trees_dir / 'auto-sync'
        self.hooks_tree = self.trees_dir / 'auto-hooks'
        self.stage_root = self.trees_dir / 'auto-stage'
        self.result = {
            'changed': False, 'ok': False, 'mode': mode, 'branch': self.branch,
            'base_sha': '', 'upstream_sha': '', 'merge_base': '', 'sha': '', 'hooks_sha': '',
            'changed_paths': 0, 'warnings': [], 'checks': [], 'stage': 'starting',
            'error': '', 'logs': str(self.logs_dir), 'report': str(self.report_dir),
            'started': time.time(), 'finished': None,
        }
        if not self.git_exe:
            raise SyncError('git is required; set GIT_EXE', stage='arguments', code=2)

    # ---- process helpers ----
    def git(self, *args, cwd=None, check=True):
        command = [self.git_exe, '-C', str(cwd or self.root), *[str(arg) for arg in args]]
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
        self._append_log('git.log', '$ ' + ' '.join(command) + '\n' + (process.stdout or '') + (process.stderr or ''))
        if check and process.returncode:
            raise SyncError((process.stderr or process.stdout or 'git failed').strip()[-2000:],
                            stage='git', code=2)
        return process

    def out(self, *args, cwd=None, check=True):
        return self.git(*args, cwd=cwd, check=check).stdout.strip()

    def _append_log(self, name, text):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with (self.logs_dir / name).open('a', encoding='utf-8') as stream:
            stream.write(text)
            if text and not text.endswith('\n'):
                stream.write('\n')

    def tool(self, label, args, cwd, timeout=900):
        command = [sys.executable, *[str(arg) for arg in args]]
        started = time.time()
        try:
            process = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                     encoding='utf-8', errors='replace', timeout=timeout)
        except subprocess.TimeoutExpired as error:
            text = (error.stdout or '') + (error.stderr or '') if isinstance(error.stdout, str) else ''
            self._append_log(label + '.log', text)
            raise SyncError(f'{label} timed out after {timeout}s', stage=label, code=2) from None
        text = (process.stdout or '') + (process.stderr or '')
        self._append_log(label + '.log', f'$ {" ".join(command)}\n[exit {process.returncode} {time.time() - started:.1f}s]\n{text}')
        if process.returncode:
            tail = '\n'.join(text.strip().splitlines()[-30:])
            raise SyncError(f'{label} failed ({process.returncode})' + (f':\n{tail}' if tail else ''),
                            stage=label, code=2)
        return text

    # ---- checks ----
    def require_clean(self):
        ensure_git_exclude()
        status = self.git('status', '--porcelain').stdout
        if status.strip():
            raise SyncError('the working tree is not clean:\n' + status.strip()[:4000],
                            stage='dirty-worktree', code=2)

    def ensure_remote(self):
        probe = self.git('remote', 'get-url', 'upstream', check=False)
        if probe.returncode:
            self.git('remote', 'add', 'upstream', UPSTREAM_URL)
        elif probe.stdout.strip() != UPSTREAM_URL:
            raise SyncError(f'unexpected upstream remote: {probe.stdout.strip()}', stage='upstream-remote', code=2)

    def fetch_refs(self):
        self.git('fetch', 'origin', '--prune')
        self.git('fetch', 'upstream', '--prune')

    def is_ancestor(self, older, newer):
        return self.git('merge-base', '--is-ancestor', older, newer, check=False).returncode == 0

    # ---- worktrees ----
    def _worktree_branch_owner(self, branch):
        text = self.git('worktree', 'list', '--porcelain').stdout
        for block in text.split('\n\n'):
            path = None
            for line in block.splitlines():
                if line.startswith('worktree '):
                    path = Path(line[9:]).resolve()
                elif line == f'branch refs/heads/{branch}':
                    return path
        return None

    def _remove_worktree(self, path):
        path = Path(path)
        if path.exists():
            self.git('worktree', 'remove', '--force', str(path), check=False)
        self.git('worktree', 'prune', check=False)

    def _remove_branch(self, branch):
        owner = self._worktree_branch_owner(branch)
        allowed = {self.sync_tree.resolve(), self.hooks_tree.resolve()}
        old_trees = (self.report_dir.parent / 'trees').resolve()
        if owner and owner not in allowed and not owner.is_relative_to(old_trees):
            raise SyncError(f'branch {branch} is checked out at {owner}; refusing to delete it',
                            stage='worktree', code=2)
        if owner:
            self._remove_worktree(owner)
        if self.git('rev-parse', '--verify', '--quiet', f'refs/heads/{branch}', check=False).returncode == 0:
            self.git('branch', '-D', branch, check=False)

    def prepare_worktrees(self):
        self.trees_dir.mkdir(parents=True, exist_ok=True)
        self._remove_worktree(self.sync_tree)
        self._remove_worktree(self.hooks_tree)
        self._remove_branch(self.branch)
        self._remove_branch(HOOKS_BRANCH)
        self.git('worktree', 'add', '-B', self.branch, str(self.sync_tree), self.base_sha)
        self.result['stage'] = 'merged'

    def merge(self):
        message = f'Merge upstream {self.upstream_sha[:12]} into {self.base_ref}'
        process = self.git('-c', f'user.name={BOT_NAME}', '-c', f'user.email={BOT_EMAIL}',
                           'merge', '--no-ff', self.upstream_ref, '-m', message,
                           cwd=self.sync_tree, check=False)
        if process.returncode:
            detail = (process.stderr or process.stdout or '').strip()[-2000:]
            self.git('merge', '--abort', cwd=self.sync_tree, check=False)
            raise SyncError('merge conflict' + (':\n' + detail if detail else ''),
                            stage='merge-conflict', code=2)
        parents = self.out('rev-list', '--parents', '-n', '1', 'HEAD', cwd=self.sync_tree).split()
        if len(parents) != 3 or set(parents[1:]) != {self.base_sha, self.upstream_sha}:
            raise SyncError('merge commit does not have the expected parents', stage='merge-graph', code=2)
        self.result['sha'] = parents[0]

    def port_hooks(self):
        self._remove_worktree(self.hooks_tree)
        self.git('worktree', 'add', '--detach', str(self.hooks_tree), self.upstream_ref)
        patches = [patch for patch, _target in staging.patch_queue()]
        try:
            self.git('apply', '--check', '--whitespace=nowarn', *patches, cwd=self.hooks_tree)
            self.git('apply', '--whitespace=nowarn', *patches, cwd=self.hooks_tree)
        except SyncError as error:
            raise SyncError('patch_apply failed: ' + str(error), stage='patch_apply', code=2) from error
        targets = [target for _, target in staging.patch_queue()]
        self.git('add', '--', *targets, cwd=self.hooks_tree)
        staged = self.git('diff', '--cached', '--quiet', cwd=self.hooks_tree, check=False)
        if staged.returncode == 0:
            raise SyncError('the hook patches produced no changes', stage='hooks', code=2)
        self.git('-c', f'user.name={BOT_NAME}', '-c', f'user.email={BOT_EMAIL}',
                 'commit', '-m', f'hooks: apply fork patches to {self.upstream_sha[:12]}',
                 cwd=self.hooks_tree)
        self.result['hooks_sha'] = self.out('rev-parse', 'HEAD', cwd=self.hooks_tree)
        if self.out('rev-parse', 'HEAD^', cwd=self.hooks_tree) != self.upstream_sha:
            raise SyncError('the hooks commit is not based on the new upstream', stage='hooks', code=2)
        self.git('update-ref', f'refs/heads/{HOOKS_BRANCH}', self.result['hooks_sha'])
        self.result['stage'] = 'hooks-ported'

    def regenerate(self):
        self.tool('patch_regenerate', [self.sync_tree / 'webui/tools/patch_queue.py', 'regenerate',
                                       '--base', self.upstream_ref, '--hooks', self.result['hooks_sha']],
                  cwd=self.sync_tree)
        patches_dir = self.sync_tree / 'webui/patches'
        for patch, _target in staging.patch_queue():
            data = (patches_dir / patch.name).read_bytes()
            if not data.strip() or b'@@' not in data:
                raise SyncError(f'{patch.name} regenerated empty (did upstream absorb the fork change?)',
                                stage='empty-patch', code=2)
        _write_metadata(patches_dir / 'UPSTREAM_BASE', self.upstream_sha, self.upstream_sha,
                        self.base_sha, self.result['hooks_sha'], self.merge_base)
        _write_series(patches_dir / 'series', self.upstream_sha, self.base_sha)
        self.git('add', '--', 'webui/patches', cwd=self.sync_tree)
        if self.git('diff', '--cached', '--quiet', cwd=self.sync_tree, check=False).returncode == 0:
            raise SyncError('patch regeneration produced no committed change', stage='patches', code=2)
        message = f'sync: regenerate hook patches for upstream {self.upstream_sha[:12]}'
        if self.result['warnings']:
            message += '\n\nWarnings:\n' + '\n'.join('- ' + item[:240] for item in self.result['warnings'][:20])
        merge_sha = self.result['sha']
        self.git('-c', f'user.name={BOT_NAME}', '-c', f'user.email={BOT_EMAIL}',
                 'commit', '-m', message, cwd=self.sync_tree)
        self.result['sha'] = self.out('rev-parse', 'HEAD', cwd=self.sync_tree)
        if self.out('rev-parse', 'HEAD^', cwd=self.sync_tree) != merge_sha:
            raise SyncError('the patch commit is not based on the merge commit', stage='patches', code=2)
        self.result['stage'] = 'patches-regenerated'

    def checks(self):
        checks = []

        def record(name, args, *, skip=False):
            if skip:
                checks.append({'name': name, 'ok': False})
                return None
            try:
                text = self.tool(name, args, cwd=self.sync_tree)
                checks.append({'name': name, 'ok': True})
                return text
            except SyncError as error:
                checks.append({'name': name, 'ok': False, 'error': str(error)[-2000:]})
                return None

        record('patch_queue', [self.sync_tree / 'webui/tools/patch_queue.py', 'check'])
        stage_text = record('stage_ensure', [self.sync_tree / 'webui/tools/stage.py', 'ensure',
                                             '--rebuild', '--stage-root', self.stage_root, '--json'])
        tree = None
        if stage_text:
            try:
                tree = json.loads(stage_text.strip())['tree']
            except (ValueError, KeyError, TypeError):
                tree = None
        record('stage_verify', [self.sync_tree / 'webui/tools/stage.py', 'verify', tree],
               skip=not tree)
        record('sync_check', [self.sync_tree / 'webui/tools/sync_check.py',
                              '--base', self.upstream_ref, '--ref', self.upstream_ref,
                              '--worktree', self.trees_dir / 'auto-sync-check'])
        record('tests', ['-m', 'unittest', 'discover', '-s', 'webui/tests', '-t', '.', '-v'])
        status = self.git('status', '--porcelain', '--untracked-files=no', cwd=self.sync_tree).stdout
        clean = not status.strip()
        self._append_log('workspace_clean.log', status or 'clean\n')
        checks.append({'name': 'workspace_clean', 'ok': clean})
        self.result['checks'] = checks
        if not all(item.get('ok') for item in checks):
            self.result['stage'] = 'checks-failed'
            return 1
        self.result['ok'] = True
        self.result['stage'] = 'synced'
        return 0

    def cleanup(self):
        if self.keep_worktrees:
            return
        self._remove_worktree(self.hooks_tree)
        self._remove_worktree(self.sync_tree)
        shutil.rmtree(self.stage_root, ignore_errors=True)

    def push_branches(self):
        for branch, sha in ((self.branch, self.result.get('sha')), (HOOKS_BRANCH, self.result.get('hooks_sha'))):
            if not sha:
                continue
            remote = self.git('ls-remote', '--heads', 'origin', f'refs/heads/{branch}', check=False).stdout.strip()
            if remote:
                expected = remote.split()[0]
                self.git('push', f'--force-with-lease=refs/heads/{branch}:{expected}',
                         'origin', f'{sha}:refs/heads/{branch}')
            else:
                self.git('push', 'origin', f'{sha}:refs/heads/{branch}')

    # ---- orchestration ----
    def run(self):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.require_clean()
            self.ensure_remote()
            if self.fetch:
                self.fetch_refs()
            self.base_sha = self.out('rev-parse', self.base_ref)
            self.upstream_sha = self.out('rev-parse', self.upstream_ref)
            self.result.update(base_sha=self.base_sha, upstream_sha=self.upstream_sha,
                               base=self.base_ref, upstream=self.upstream_ref)
            if self.is_ancestor(self.upstream_sha, self.base_sha):
                self.result.update(changed=False, ok=True, stage='up-to-date')
                return 0

            self.merge_base = self.out('merge-base', self.base_sha, self.upstream_sha)
            self.result.update(merge_base=self.merge_base, changed=True)
            if not self.is_ancestor(self.merge_base, self.upstream_sha):
                raise SyncError('upstream history was rewritten; refusing an automatic merge',
                                stage='upstream-rewritten', code=2)
            previous = _read_metadata(self.root / 'webui/patches/UPSTREAM_BASE').get('upstream')
            if previous and self.git('cat-file', '-e', previous + '^{commit}', check=False).returncode == 0:
                if not self.is_ancestor(previous, self.base_sha):
                    raise SyncError('the fork base does not contain the recorded upstream commit',
                                    stage='fork-history', code=2)
                if not self.is_ancestor(previous, self.upstream_sha):
                    raise SyncError('upstream rewrote a commit already synced by the fork',
                                    stage='upstream-rewritten', code=2)

            changed = self.out('diff', '--name-only', self.merge_base, self.upstream_sha).splitlines()
            changed = [line for line in changed if line]
            self.result['changed_paths'] = len(changed)
            forbidden = [path for path in changed if _is_owned(path)]
            if forbidden:
                raise SyncError('upstream changed fork-owned paths: ' + ', '.join(forbidden[:30]),
                                stage='fork-owned-change', code=2)
            manual = [path for path in changed if path in MANUAL_REVIEW]
            if manual:
                raise SyncError('upstream changed manually reviewed paths: ' + ', '.join(manual),
                                stage='manual-review', code=2)
            self.result['warnings'] = [f'upstream changed sensitive path {path}; review the fork integration'
                                       for path in changed if path in SENSITIVE]
            if self.dry_run:
                self.result.update(ok=True, stage='planned')
                return 0

            self.prepare_worktrees()
            self.merge()
            self.port_hooks()
            self.regenerate()
            code = self.checks()
            if self.push:
                self.push_branches()
            if code == 0:
                self.cleanup()
            return code
        except SyncError as error:
            self.result.update(ok=False, error=str(error), stage=error.stage)
            return error.code
        finally:
            self.result['finished'] = time.time()
            self.write_report()

    def write_report(self):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.report_dir / 'result.json.tmp'
        tmp.write_text(json.dumps(self.result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        os.replace(tmp, self.report_dir / 'result.json')
        (self.report_dir / 'summary.md').write_text(_summary(self.result), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=sorted(BRANCHES), required=True)
    parser.add_argument('--base-ref', default='main')
    parser.add_argument('--upstream-ref', default='upstream/main')
    parser.add_argument('--fetch', action='store_true', help='fetch origin and upstream first')
    parser.add_argument('--dry-run', action='store_true', help='report changes without worktrees')
    parser.add_argument('--keep-worktrees', action='store_true', help='keep worktrees after a successful sync')
    parser.add_argument('--push', action='store_true', help='push the sync and hooks branches to origin (never main)')
    parser.add_argument('--report-dir', type=Path)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    report_dir = Path(args.report_dir or (REPO / '.webui-data/upstream-sync/report')).resolve()
    try:
        with staging._lock(report_dir.parent / '.lock'):
            syncer = Syncer(args.mode, base_ref=args.base_ref, upstream_ref=args.upstream_ref,
                            fetch=args.fetch, dry_run=args.dry_run, keep_worktrees=args.keep_worktrees,
                            push=args.push, report_dir=report_dir)
            code = syncer.run()
    except SyncError as error:
        print('【红】' + str(error), file=sys.stderr)
        return error.code
    if args.json:
        print(json.dumps(syncer.result, indent=2, ensure_ascii=False))
    else:
        print(_summary(syncer.result), end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
