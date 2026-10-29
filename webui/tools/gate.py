#!/usr/bin/env python3
"""The gate: everything that has to be green before a change reaches main.

    python webui/tools/gate.py             # run every check
    python webui/tools/gate.py --json
    python webui/tools/gate.py --skip unittest

The four checks are the ones rule R-03 names:

  patch_queue  every patch in the series applies, in series order
  stage        the staging tree rebuilds and verifies (the tree the builds run in)
  sync_check   upstream-owned files stay clean and the patches still apply
               onto the upstream commit recorded in webui/patches/UPSTREAM_BASE
  unittest     the fork's own tests

The rule checks (R-03, R-04, R-08..R-16) run as well, so the rules are not a
document nobody checks.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import staging  # noqa: E402
from webui.tools import rules  # noqa: E402

VENV_PYTHON = ROOT / '.webui-data' / 'venv' / 'Scripts' / 'python.exe'


def interpreter():
    """The interpreter that has the fork's dependencies (the venv), or this one."""
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    return sys.executable


def run_step(name, args, cwd=ROOT, timeout=3600):
    started = time.time()
    command = [interpreter(), *[str(arg) for arg in args]]
    try:
        process = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True,
                                 encoding='utf-8', errors='replace', timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'name': name, 'ok': False, 'seconds': time.time() - started,
                'detail': f'timed out after {timeout}s'}
    text = (process.stdout or '') + (process.stderr or '')
    tail = '\n'.join(text.strip().splitlines()[-40:])
    return {'name': name, 'ok': process.returncode == 0, 'seconds': round(time.time() - started, 1),
            'returncode': process.returncode, 'detail': tail}


def patch_queue_check():
    step = run_step('patch_queue', ['webui/tools/patch_queue.py', 'check'])
    if step['ok']:
        step['detail'] = 'every patch applies in series order'
    return step


def stage_checks():
    step = run_step('stage_ensure', ['webui/tools/stage.py', 'ensure', '--rebuild', '--json'])
    if not step['ok']:
        return step
    tree = None
    try:
        tree = json.loads(step['detail'].strip().splitlines()[-1])['tree']
    except (ValueError, KeyError, TypeError):
        pass
    if not tree:
        return {'name': 'stage', 'ok': False, 'seconds': step['seconds'],
                'detail': 'stage.py ensure did not report a tree'}
    verify = run_step('stage_verify', ['webui/tools/stage.py', 'verify', tree])
    return {'name': 'stage', 'ok': verify['ok'], 'seconds': round(step['seconds'] + verify['seconds'], 1),
            'detail': f'tree {tree}\n{verify["detail"]}'}


def recorded_upstream_base():
    """The upstream commit this tree is actually based on.

    `webui/patches/UPSTREAM_BASE` records it.  The gate checks against that
    commit, not against the live `upstream/main`: the live upstream moves
    every day, and until the daily rebase has landed, the fork's patches are
    written against the recorded base.  Once the rebase lands, the recorded
    base is the new upstream commit and the gate checks that one instead.
    """
    path = ROOT / 'webui' / 'patches' / 'UPSTREAM_BASE'
    if not path.is_file():
        return None
    for line in path.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ('base', 'upstream'):
            return parts[1]
    return None


def sync_check():
    base = recorded_upstream_base()
    if not base:
        return {'name': 'sync_check', 'ok': False, 'seconds': 0.0,
                'detail': 'webui/patches/UPSTREAM_BASE 里没有 base 行'}
    step = run_step('sync_check', ['webui/tools/sync_check.py', '--base', base, '--ref', base])
    step['detail'] = f'基线 {base}\n' + step['detail']
    return step


def unittest_step():
    return run_step('unittest', ['-m', 'unittest', 'discover', '-s', 'webui/tests', '-t', '.'])


def rule_checks():
    report = rules.run()
    failed = [entry for entry in report if entry['ok'] is False]
    pending = [entry for entry in report if entry['ok'] is None]
    detail = '\n'.join(f'{entry["id"]} {entry["title"]}: {entry["detail"]}' for entry in report)
    return {'name': 'rules', 'ok': not failed, 'seconds': 0.0,
            'detail': detail or 'no rule checks',
            'failed': [entry['id'] for entry in failed],
            'pending': [entry['id'] for entry in pending]}


STEPS = {
    'patch_queue': patch_queue_check,
    'stage': stage_checks,
    'sync_check': sync_check,
    'unittest': unittest_step,
    'rules': rule_checks,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip', action='append', default=[], choices=sorted(STEPS))
    parser.add_argument('--only', action='append', default=[], choices=sorted(STEPS))
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    names = [name for name in STEPS if name not in args.skip]
    if args.only:
        names = [name for name in names if name in args.only]

    results = []
    for name in names:
        print(f'==> {name}', flush=True)
        step = STEPS[name]()
        results.append(step)
        mark = 'PASS' if step['ok'] else 'FAIL'
        print(f'{mark}  {name}  ({step["seconds"]}s)', flush=True)
        if not step['ok']:
            print(step.get('detail', ''), flush=True)

    ok = all(step['ok'] for step in results)
    if args.json:
        print(json.dumps({'ok': ok, 'checks': results}, indent=2, ensure_ascii=False))
    else:
        print(f'\n{"GATE GREEN" if ok else "GATE RED"}  ({len(results)} checks)')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
