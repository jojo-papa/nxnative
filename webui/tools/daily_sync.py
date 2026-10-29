#!/usr/bin/env python3
"""Rebuild the daily branch from the upstream and promote it to main when it is green.

Rule R-01: the upstream's latest main is fetched, the fork's commits are
replayed onto it, the fork's patches are replayed onto the new baseline
(R-02), the gate runs, and only a green daily becomes main.  A red daily
leaves main exactly where it was.

    python webui/tools/daily_sync.py --plan      # what would happen; nothing is touched
    python webui/tools/daily_sync.py --run       # do it
    python webui/tools/daily_sync.py --run --no-promote

The work happens in a worktree under .webui-data/daily, so the working tree
of the fork is never disturbed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.tools import patch_rebase  # noqa: E402

WORKTREE = ROOT / '.webui-data' / 'daily'
BRANCH = 'daily'
MAIN = 'main'
UPSTREAM = 'upstream'


def git(*args, cwd=ROOT, check=False):
    process = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True,
                             text=True, encoding='utf-8', errors='replace')
    if check and process.returncode:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    return process


def git_out(*args, cwd=ROOT):
    process = git(*args, cwd=cwd)
    return process.stdout.strip() if process.returncode == 0 else ''


def upstream_base():
    """The upstream commit the fork is currently based on."""
    path = ROOT / 'webui' / 'patches' / 'UPSTREAM_BASE'
    if not path.is_file():
        return None
    for line in path.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == 'base':
            return parts[1]
    return None


def fork_commits(base):
    """The fork's own commits: everything after *base* that is not upstream's."""
    out = git_out('rev-list', '--count', f'{base}..{MAIN}')
    return int(out) if out.isdigit() else 0


def fetch_upstream():
    """Fetch the upstream.  HTTP/1.1, because HTTP/2 is blocked on this network."""
    command = ['git', '-c', 'http.version=HTTP/1.1', 'fetch', UPSTREAM, 'main']
    process = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
    if process.returncode:
        return {'ok': False, 'detail': (process.stderr or process.stdout).strip()}
    return {'ok': True, 'detail': git_out('rev-parse', f'{UPSTREAM}/main')}


def remove_worktree():
    git('worktree', 'remove', '--force', str(WORKTREE))
    git('worktree', 'prune')
    if WORKTREE.exists():
        shutil.rmtree(WORKTREE, ignore_errors=True)


def conflicted_files(worktree):
    out = git_out('diff', '--name-only', '--diff-filter=U', cwd=worktree)
    return [line for line in out.splitlines() if line]


def split_conflict(text):
    """The two sides of a conflicted file: (ours, theirs) or None."""
    ours = []
    theirs = []
    side = None
    for line in text.splitlines():
        if line.startswith('<<<<<<< '):
            side = ours
        elif line.startswith('======='):
            side = theirs
        elif line.startswith('>>>>>>> '):
            side = None
        elif side is not None:
            side.append(line)
    return ours, theirs


def attribute_rules(lines):
    """The path patterns of an attribute file (comments and blanks do not count)."""
    return [line.strip() for line in lines
            if line.strip() and not line.strip().startswith('#')]


def resolve_conflicts(worktree):
    """Resolve the conflicts the rebase hit, but only when it is obvious.

    The upstream and the fork both add a .gitattributes: the upstream adds
    its gallery merge rule, the fork adds the line ending rules.  Neither
    side mentions the other's paths, so the union is the right answer.  Any
    other conflict is reported and left to a person.
    """
    unresolved = []
    resolved = []
    for name in conflicted_files(worktree):
        path = Path(worktree) / name
        try:
            ours, theirs = split_conflict(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError):
            unresolved.append(name)
            continue
        if name != '.gitattributes':
            unresolved.append(name)
            continue
        our_rules = attribute_rules(ours)
        their_rules = attribute_rules(theirs)
        if any(rule in their_rules for rule in our_rules):
            unresolved.append(name)
            continue
        merged = []
        for line in ours:
            merged.append(line)
        if merged and merged[-1].strip():
            merged.append('')
        merged.extend(theirs)
        path.write_text('\n'.join(merged).rstrip('\n') + '\n', encoding='utf-8')
        git('add', '--', name, cwd=worktree)
        resolved.append(name)
    return resolved, unresolved


def build_worktree(base):
    """A worktree on a fresh daily branch, with the fork's commits replayed."""
    remove_worktree()
    created = git('worktree', 'add', '--detach', str(WORKTREE), MAIN)
    if created.returncode:
        return {'ok': False, 'detail': 'worktree add failed: ' + created.stderr.strip()}
    git('checkout', '-B', BRANCH, cwd=WORKTREE)
    environment = dict(os.environ, GIT_EDITOR='true')
    replayed = git('rebase', '--onto', f'{UPSTREAM}/main', base, BRANCH, cwd=WORKTREE)
    resolved_all = []
    while replayed.returncode:
        resolved, unresolved = resolve_conflicts(WORKTREE)
        resolved_all.extend(resolved)
        if unresolved or not resolved:
            detail = (replayed.stderr or replayed.stdout).strip()
            git('rebase', '--abort', cwd=WORKTREE)
            message = 'rebase onto the new upstream failed:\n' + detail
            if unresolved:
                message += '\n要人看的冲突：' + ', '.join(unresolved)
            return {'ok': False, 'detail': message, 'resolved': resolved_all,
                    'unresolved': unresolved}
        process = subprocess.run(['git', '-C', str(WORKTREE), 'rebase', '--continue'],
                                  capture_output=True, text=True, encoding='utf-8',
                                  errors='replace', env=environment)
        replayed = process
    return {'ok': True, 'detail': git_out('rev-parse', BRANCH, cwd=WORKTREE),
            'resolved': resolved_all}


def regenerate_patches(base):
    """Replay the patches onto the new baseline inside the worktree."""
    verdicts = patch_rebase.judge_all(base, f'{UPSTREAM}/main', repo=WORKTREE)
    counts = {}
    for verdict in verdicts:
        counts[verdict['verdict']] = counts.get(verdict['verdict'], 0) + 1
    if counts.get(patch_rebase.MANUAL, 0):
        return {'ok': False, 'verdicts': verdicts, 'counts': counts,
                'detail': f'{counts[patch_rebase.MANUAL]} 条补丁需要人看（NEEDS_MANUAL）'}
    patch_rebase.write_regenerated(verdicts, WORKTREE / 'webui' / 'patches', f'{UPSTREAM}/main')
    return {'ok': True, 'verdicts': verdicts, 'counts': counts, 'detail': ''}


def run_gate():
    """The gate, in the worktree."""
    process = subprocess.run([sys.executable, str(WORKTREE / 'webui' / 'tools' / 'gate.py')],
                             cwd=str(WORKTREE), capture_output=True, text=True,
                             encoding='utf-8', errors='replace')
    tail = '\n'.join(((process.stdout or '') + (process.stderr or '')).strip().splitlines()[-30:])
    return {'ok': process.returncode == 0, 'detail': tail}


def promote(daily_sha):
    """Point main at the green daily branch."""
    current = git_out('rev-parse', MAIN)
    updated = git('update-ref', 'refs/heads/' + MAIN, daily_sha, current)
    if updated.returncode:
        return {'ok': False, 'detail': updated.stderr.strip()}
    return {'ok': True, 'detail': f'main {current[:12]} -> {daily_sha[:12]}'}


def plan():
    base = upstream_base()
    if not base:
        return {'ok': False, 'detail': 'webui/patches/UPSTREAM_BASE 里没有 base 行'}
    new_base = git_out('rev-parse', f'{UPSTREAM}/main')
    if not new_base:
        return {'ok': False, 'detail': '没有 upstream/main，先 fetch'}
    verdicts = patch_rebase.judge_all(base, new_base, repo=ROOT)
    counts = {}
    for verdict in verdicts:
        counts[verdict['verdict']] = counts.get(verdict['verdict'], 0) + 1
    return {'ok': True, 'base': base, 'new_base': new_base, 'counts': counts,
            'fork_commits': fork_commits(base),
            'manual': [v['patch'] for v in verdicts if v['verdict'] == patch_rebase.MANUAL],
            'dropped': [v['patch'] for v in verdicts if v['verdict'] == patch_rebase.DROP]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', action='store_true', help='only report, change nothing')
    parser.add_argument('--run', action='store_true', help='do the whole thing')
    parser.add_argument('--fetch', action='store_true', help='fetch the upstream first')
    parser.add_argument('--no-promote', action='store_true', help='leave main alone')
    parser.add_argument('--report', type=Path, help='write the JSON report here')
    args = parser.parse_args(argv)

    started = time.time()
    steps = []

    if args.fetch:
        fetched = fetch_upstream()
        steps.append({'name': 'fetch', **fetched})
        if not fetched['ok']:
            print(f'fetch 失败：{fetched["detail"]}', file=sys.stderr)
            return 2

    if args.plan or not args.run:
        result = plan()
        if not result['ok']:
            print(result['detail'], file=sys.stderr)
            return 2
        print(f'旧基线   {result["base"][:12]}')
        print(f'新基线   {result["new_base"][:12]}')
        print(f'我们的提交 {result["fork_commits"]} 条')
        print('判定     ' + '  '.join(f'{name}={count}' for name, count in sorted(result['counts'].items())))
        if result['dropped']:
            print('可以丢弃（上游已经做了）: ' + ', '.join(result['dropped']))
        if result['manual']:
            print('需要人看               : ' + ', '.join(result['manual']))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                                   encoding='utf-8')
        return 0 if not result['manual'] else 1

    if not args.run:
        parser.error('give --plan or --run')

    base = upstream_base()
    if not base:
        print('webui/patches/UPSTREAM_BASE 里没有 base 行', file=sys.stderr)
        return 2

    worktree = build_worktree(base)
    steps.append({'name': 'rebase', **worktree})
    print(('PASS' if worktree['ok'] else 'FAIL') + '  rebase  ' + worktree['detail'][:200], flush=True)
    if not worktree['ok']:
        return 1

    patches = regenerate_patches(base)
    steps.append({'name': 'patches', **{k: v for k, v in patches.items() if k != 'verdicts'}})
    print(('PASS' if patches['ok'] else 'FAIL') + '  patches  ' + patches['detail'], flush=True)
    if not patches['ok']:
        for verdict in patches.get('verdicts', []):
            if verdict['verdict'] == patch_rebase.MANUAL:
                print(f'  {verdict["patch"]}  {verdict["target"]}: {verdict["reason"]}', file=sys.stderr)
        return 1

    gate = run_gate()
    steps.append({'name': 'gate', **gate})
    print(('PASS' if gate['ok'] else 'FAIL') + '  gate', flush=True)
    if not gate['ok']:
        print(gate['detail'], file=sys.stderr)
        return 1

    daily_sha = git_out('rev-parse', BRANCH, cwd=WORKTREE)
    if args.no_promote:
        steps.append({'name': 'promote', 'ok': True, 'detail': 'skipped (--no-promote)'})
        print(f'SKIP  promote  daily {daily_sha[:12]} 不提升（--no-promote）', flush=True)
    else:
        promoted = promote(daily_sha)
        steps.append({'name': 'promote', **promoted})
        print(('PASS' if promoted['ok'] else 'FAIL') + '  promote  ' + promoted['detail'], flush=True)
        if not promoted['ok']:
            return 1

    report = {'ok': True, 'seconds': round(time.time() - started, 1), 'steps': steps,
              'base': base, 'new_base': git_out('rev-parse', f'{UPSTREAM}/main')}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'\nDAILY 绿了，用时 {report["seconds"]}s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
