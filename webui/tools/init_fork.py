#!/usr/bin/env python3
"""One-time fork setup: add the upstream remote and local git excludes."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui.repo import REPO, UPSTREAM_URL, ensure_git_exclude


def git_executable():
    value = os.environ.get('GIT_EXE') or shutil.which('git')
    if not value:
        raise SystemExit('git is required; set GIT_EXE to a working git executable')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='fetch the upstream remote after configuring it')
    parser.add_argument('--no-remote', action='store_true', help='only update local excludes')
    args = parser.parse_args(argv)
    ensure_git_exclude()
    if args.no_remote:
        print('local git excludes updated')
        return 0
    git = git_executable()
    probe = subprocess.run([git, '-C', str(REPO), 'remote', 'get-url', 'upstream'],
                           capture_output=True, text=True)
    if probe.returncode:
        subprocess.run([git, '-C', str(REPO), 'remote', 'add', 'upstream', UPSTREAM_URL], check=True)
        print('added upstream:', UPSTREAM_URL)
    else:
        print('upstream:', probe.stdout.strip())
    if args.fetch:
        subprocess.run([git, '-C', str(REPO), 'fetch', 'upstream', '--prune'], check=True)
        print('fetched upstream')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
