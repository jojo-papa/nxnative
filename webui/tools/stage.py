#!/usr/bin/env python3
"""Manage the build staging tree (create, verify, inspect, run a command)."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import staging


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)

    ensure = sub.add_parser('ensure', help='create or reuse the stage')
    ensure.add_argument('--stage-root', type=Path)
    ensure.add_argument('--rebuild', action='store_true')
    ensure.add_argument('--json', action='store_true')

    verify = sub.add_parser('verify', help='verify a stage')
    verify.add_argument('stage', type=Path, nargs='?')

    sub.add_parser('key', help='print the current stage key')

    run = sub.add_parser('run', help='run a command in the stage tree')
    run.add_argument('--stage-root', type=Path)
    run.add_argument('command', nargs=argparse.REMAINDER)

    args = parser.parse_args(argv)
    if args.command == 'ensure':
        tree = staging.ensure(staging.REPO, args.stage_root, force=args.rebuild)
        value = {'tree': str(tree), 'key': tree.parent.name}
        print(json.dumps(value) if args.json else str(tree))
        return 0
    if args.command == 'verify':
        stage = args.stage or (staging.ensure(staging.REPO) / '..')
        record = staging.verify(stage)
        print(json.dumps(record, indent=2))
        return 0
    if args.command == 'key':
        print(staging.compute_key(staging.REPO))
        return 0
    if args.command == 'run':
        command = args.command
        if command and command[0] == '--':
            command = command[1:]
        if not command:
            parser.error('run requires a command after --')
        tree = staging.ensure(staging.REPO, args.stage_root)
        env = dict(os.environ, NX_STAGE_TREE=str(tree), NX_STAGE_KEY=tree.parent.name)
        env['PYTHONPATH'] = os.pathsep.join([str(tree), env.get('PYTHONPATH', '')])
        return subprocess.run(command, cwd=tree, env=env).returncode
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
