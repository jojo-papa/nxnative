#!/usr/bin/env python3
"""Inspect, check or apply the fork's upstream hook patch queue."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import diffapply, staging


def check(tree: Path):
    results = []
    for patch, target in staging.patch_queue():
        source = tree / target
        if not source.is_file():
            raise ValueError(f'missing target: {target}')
        data = diffapply.apply_file(source, patch.read_bytes(), target)
        results.append({'patch': patch.name, 'target': target, 'bytes': len(data)})
    return results


def apply(tree: Path):
    for patch, target in staging.patch_queue():
        source = tree / target
        data = diffapply.apply_file(source, patch.read_bytes(), target)
        temporary = source.with_name(source.name + '.patch-tmp')
        temporary.write_bytes(data)
        os.replace(temporary, source)


def regenerate(base: str, hooks: str):
    git = os.environ.get('GIT_EXE') or shutil.which('git')
    if not git:
        raise SystemExit('git is required; set GIT_EXE')
    for patch, target in staging.patch_queue():
        data = subprocess.check_output([git, '-C', str(ROOT), 'diff', '--no-ext-diff', '--unified=3',
                                        base, hooks, '--', target])
        patch.write_bytes(data)
        print(f'{patch.name}: regenerated from {base}..{hooks} ({len(data)} bytes)')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check_cmd = sub.add_parser('check', help='apply every patch in memory to a base tree')
    check_cmd.add_argument('tree', type=Path, nargs='?', default=ROOT)
    check_cmd.add_argument('--json', action='store_true')
    apply_cmd = sub.add_parser('apply', help='apply the queue to a copy of the base tree')
    apply_cmd.add_argument('tree', type=Path)
    sub.add_parser('list', help='list the series')
    regen = sub.add_parser('regenerate', help='regenerate patches from a git range')
    regen.add_argument('--base', required=True)
    regen.add_argument('--hooks', required=True)
    args = parser.parse_args(argv)
    if args.command == 'list':
        for patch, target in staging.patch_queue():
            print(f'{patch.name}\t{target}')
        return 0
    if args.command == 'check':
        results = check(args.tree.resolve())
        print(json.dumps(results, indent=2) if args.json else
              '\n'.join(f'{r["patch"]}: OK ({r["bytes"]} bytes)' for r in results))
        return 0
    if args.command == 'apply':
        apply(args.tree.resolve())
        return 0
    if args.command == 'regenerate':
        regenerate(args.base, args.hooks)
        return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
