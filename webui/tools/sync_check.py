#!/usr/bin/env python3
"""Check that upstream-owned paths are clean and the hook patches still apply."""
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
from webui.repo import REPO, UPSTREAM_URL, ensure_git_exclude

UPSTREAM_PATHS = ('dm', 'scripts', 'docs', '.github', 'README.md', 'AGENTS.md', 'LICENSE', '.gitignore')
ALLOWED_EDITS = {'dm/ios/project.yml', '.github/workflows/upstream-sync.yml'}
OLD_PATHS = (
    'dm.webui',
    'dm/webui',
    'dm/macos',
    'dm/tools/ios_cross_',
    'dm/gfx/tools/windows_shader_build',
    'scripts/start_webui',
    'scripts/webui_bootstrap',
    'scripts/prepare_webui_tools',
    'scripts/build_ipa_windows',
)


def git():
    value = os.environ.get('GIT_EXE') or shutil.which('git')
    if not value:
        raise RuntimeError('git is required; set GIT_EXE')
    return value


def git_out(*args):
    return subprocess.run([git(), '-C', str(REPO), *args], capture_output=True, text=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='upstream/main',
                        help='upstream base used for the working-tree cleanliness check')
    parser.add_argument('--ref', default='upstream/main', help='upstream ref for patch applicability')
    parser.add_argument('--worktree', type=Path, help='temporary worktree path (default: .webui-data/sync-check)')
    parser.add_argument('--offline', action='store_true', help='do not inspect the upstream ref')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    findings = []
    ensure_git_exclude()

    remote = git_out('remote', 'get-url', 'upstream')
    if remote.returncode:
        findings.append({'kind': 'upstream-remote', 'detail': 'missing; run webui/tools/init_fork.py'})
    elif remote.stdout.strip() != UPSTREAM_URL:
        findings.append({'kind': 'upstream-remote', 'detail': remote.stdout.strip()})

    diff = git_out('diff', '--name-status', args.base, '--', *UPSTREAM_PATHS)
    if diff.returncode:
        findings.append({'kind': 'git', 'detail': diff.stderr.strip()})
    else:
        for line in diff.stdout.splitlines():
            fields = line.split('\t', 1)
            if len(fields) == 2 and fields[1] not in ALLOWED_EDITS:
                findings.append({'kind': 'upstream-edit', 'detail': line})

    untracked = git_out('status', '--porcelain', '--untracked-files=all', '--', 'dm', 'scripts', 'docs')
    if untracked.returncode == 0:
        for line in untracked.stdout.splitlines():
            if line.startswith('??'):
                findings.append({'kind': 'fork-file-in-upstream', 'detail': line})

    for rel in OLD_PATHS:
        for path in (REPO / 'webui').rglob('*'):
            if not path.is_file() or path.suffix not in ('.py', '.js', '.html', '.md', '.ps1', '.bat', '.sh', '.command'):
                continue
            if path.name in ('sync.md', 'sync_check.py'):
                continue
            try:
                text = path.read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
            if rel in text:
                findings.append({'kind': 'old-reference', 'detail': f'{path.relative_to(REPO)}: {rel}'})

    try:
        for patch, target in staging.patch_queue():
            data = diffapply.apply_file(REPO / target, patch.read_bytes(), target)
            if not data:
                findings.append({'kind': 'patch', 'detail': f'{patch.name}: empty result'})
    except Exception as error:
        findings.append({'kind': 'patch', 'detail': str(error)})

    if not args.offline:
        worktree = (args.worktree or (REPO / '.webui-data' / 'sync-check')).expanduser().resolve()
        if worktree == REPO.resolve():
            findings.append({'kind': 'worktree', 'detail': 'refusing to use the repository root as a temporary worktree'})
        else:
            git_out('worktree', 'remove', '--force', str(worktree))
            git_out('worktree', 'prune')
            if worktree.exists():
                shutil.rmtree(worktree, ignore_errors=True)
        created = git_out('worktree', 'add', '--detach', str(worktree), args.ref) if worktree != REPO.resolve() else None
        if created is not None and created.returncode:
            findings.append({'kind': 'upstream-ref', 'detail': created.stderr.strip()})
        elif created is not None:
            try:
                for patch, target in staging.patch_queue():
                    result = subprocess.run([git(), '-C', str(worktree), 'apply', '--check', '--whitespace=nowarn',
                                             str(patch)], capture_output=True, text=True)
                    if result.returncode:
                        findings.append({'kind': 'patch-upstream', 'detail': f'{patch.name}: {result.stderr.strip()}'})
            finally:
                git_out('worktree', 'remove', '--force', str(worktree))
                git_out('worktree', 'prune')

    report = {'ok': not findings, 'findings': findings}
    print(json.dumps(report, indent=2) if args.json else
          ('clean' if not findings else '\n'.join(f'{f["kind"]}: {f["detail"]}' for f in findings)))
    return 0 if not findings else 1


if __name__ == '__main__':
    raise SystemExit(main())
