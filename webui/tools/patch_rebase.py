#!/usr/bin/env python3
"""Replay the fork's patches onto a new upstream base.

Rule R-02: when the new baseline already carries our change, drop our patch
and keep the baseline's version; only what the baseline does not cover is
redone.  The verdict for every patch is one of:

  KEEP                  it applies to the new base
  DROP_BASELINE_HAS_IT  the new base already has the change; drop the patch
  PARTIAL               some hunks are upstreamed, the rest still apply
  NEEDS_MANUAL          something does not apply and the baseline does not
                        have it either — a person has to look at it

    python webui/tools/patch_rebase.py --base upstream/main
    python webui/tools/patch_rebase.py --base upstream/main --report report.json
    python webui/tools/patch_rebase.py --base upstream/main --regenerate DIR

`--regenerate` writes the new patches and the new series into DIR (not into
the repository) so the result can be reviewed before it is applied.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webui import staging  # noqa: E402

HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')

KEEP = 'KEEP'
DROP = 'DROP_BASELINE_HAS_IT'
PARTIAL = 'PARTIAL'
MANUAL = 'NEEDS_MANUAL'


# ---------- git ----------

def git(*args, binary=False, repo=None):
    process = subprocess.run(['git', '-C', str(repo or ROOT), *args], capture_output=True,
                             **({'text': False, 'encoding': None} if binary else
                                {'text': True, 'encoding': 'utf-8', 'errors': 'replace'}))
    return process.returncode, process.stdout, process.stderr


def git_text(*args, repo=None):
    code, out, _err = git(*args, repo=repo)
    return out if code == 0 else ''


def read_at(ref, path, repo=None):
    """The bytes of *path* at *ref*, or None when it is not there."""
    code, out, _err = git('show', f'{ref}:{path}', binary=True, repo=repo)
    return out if code == 0 else None


def blob_hash(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


# ---------- the patch format ----------

def parse_patch(patch):
    """(target, header lines, hunks) where a hunk is (old_start, ops)."""
    text = patch.decode('utf-8').replace('\r\n', '\n')
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    target = None
    header = []
    hunks = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith('--- '):
            target = line[4:].split('\t')[0].strip()
            if target.startswith('b/'):
                target = target[2:]
            header = lines[:index]
            index += 2
            continue
        if line.startswith('@@ '):
            match = HUNK.match(line)
            if not match:
                raise ValueError(f'malformed hunk header: {line!r}')
            ops = []
            index += 1
            while index < len(lines):
                body = lines[index]
                if body.startswith('@@ ') or body.startswith('diff --git '):
                    break
                if body == r'\ No newline at end of file':
                    index += 1
                    continue
                if not body:
                    raise ValueError('empty line inside a hunk')
                ops.append((body[0], body[1:]))
                index += 1
            hunks.append((int(match.group(1)), ops))
            continue
        index += 1
    if target is None:
        raise ValueError('patch has no file header')
    return target, header, hunks


def split_lines(data):
    """(lines, trailing newline)."""
    text = data.decode('utf-8').replace('\r\n', '\n')
    trailing = text.endswith('\n')
    lines = text.split('\n')
    if trailing:
        lines.pop()
    return lines, trailing


def added_runs(ops):
    """The contiguous runs of added lines in a hunk."""
    runs = []
    current = []
    for op, content in ops:
        if op == '+':
            current.append(content)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def contains(lines, sequence):
    """True when *sequence* appears contiguously in *lines*."""
    if not sequence:
        return True
    size = len(sequence)
    for start in range(0, len(lines) - size + 1):
        if lines[start:start + size] == sequence:
            return True
    return False


def apply_hunks(lines, hunks):
    """Apply the hunks, moving each one when the baseline shifted it.

    Returns (result lines, applied hunk indexes, failed hunk indexes).
    """
    result = []
    position = 0
    applied = []
    failed = []
    for index, (old_start, ops) in enumerate(hunks):
        block = [content for op, content in ops if op in ' -']
        found = None
        start = old_start - 1
        if start >= position and lines[start:start + len(block)] == block:
            found = start
        else:
            for candidate in range(position, len(lines) - len(block) + 1):
                if lines[candidate:candidate + len(block)] == block:
                    found = candidate
                    break
        if found is None:
            failed.append(index)
            continue
        result.extend(lines[position:found])
        position = found
        for op, content in ops:
            if op == ' ':
                result.append(content)
                position += 1
            elif op == '-':
                position += 1
            else:
                result.append(content)
        applied.append(index)
    result.extend(lines[position:])
    return result, applied, failed


def common_affixes(first, second):
    """(prefix length, suffix length) shared by two strings."""
    prefix = 0
    while prefix < len(first) and prefix < len(second) and first[prefix] == second[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < len(first) - prefix and suffix < len(second) - prefix
           and first[len(first) - 1 - suffix] == second[len(second) - 1 - suffix]):
        suffix += 1
    return prefix, suffix


def replacement_is_upstreamed(removed, added, base_lines):
    """One line replaced by another: the baseline may already carry the change.

    A long line that the upstream edited as well (it added another framework
    to the same clang line, say) does not match ours byte for byte, so the
    middle of the line is what matters: is it already in the baseline?
    """
    if len(removed) != 1 or len(added) != 1:
        return False
    prefix, suffix = common_affixes(removed[0], added[0])
    middle = added[0][prefix:len(added[0]) - suffix] if suffix else added[0][prefix:]
    head = removed[0][:prefix]
    if len(middle) < 3 or len(head) < 8:
        # Too little context to tell "the baseline has it" from "the baseline
        # happens to contain the same word".
        return False
    for line in base_lines:
        if middle in line and head in line:
            return True
    return False


def hunk_is_upstreamed(hunk, base_lines):
    """True when the new baseline already carries what this hunk adds.

    The added lines have to be there, in order and next to each other.  A hunk
    that only removes lines counts as upstreamed when the removed lines are
    gone from the new baseline.
    """
    ops = hunk[1]
    removed = [content for op, content in ops if op == '-']
    added = [content for op, content in ops if op == '+']
    if replacement_is_upstreamed(removed, added, base_lines):
        return True
    runs = added_runs(ops)
    if runs:
        return all(contains(base_lines, run) for run in runs)
    if not removed:
        return True
    return not any(contains(base_lines, [line]) for line in removed)


def make_patch(target, old, new):
    """A unified diff in the same shape as the patches the fork already has."""
    old_lines, old_trailing = split_lines(old)
    new_lines, new_trailing = split_lines(new)
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm='', n=3,
                                     fromfile=f'a/{target}', tofile=f'b/{target}'))
    if not diff:
        return None
    hunks = diff[2:]
    if old_trailing != new_trailing:
        hunks = hunks + [r'\ No newline at end of file']
    head = [f'diff --git a/{target} b/{target}',
            f'index {blob_hash(old)[:7]}..{blob_hash(new)[:7]} 100644',
            f'--- a/{target}', f'+++ b/{target}']
    return ('\n'.join(head + hunks) + '\n').encode('utf-8')


# ---------- the decision ----------

def recorded_base():
    path = ROOT / 'webui' / 'patches' / 'UPSTREAM_BASE'
    if not path.is_file():
        return None
    for line in path.read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == 'base':
            return parts[1]
    return None


def judge_patch(patch_path, target, old_base, new_base, repo=None):
    """The verdict for one patch."""
    patch = patch_path.read_bytes()
    parsed_target, _header, hunks = parse_patch(patch)
    old_file = read_at(old_base, target, repo=repo)
    new_file = read_at(new_base, target, repo=repo)
    verdict = {
        'patch': patch_path.name, 'target': target, 'verdict': None,
        'hunks': len(hunks), 'dropped_hunks': [], 'failed_hunks': [], 'reason': '',
        'patch_bytes': None,
    }
    if old_file is None:
        verdict['verdict'] = MANUAL
        verdict['reason'] = f'旧基线 {old_base[:12]} 里没有 {target}'
        return verdict
    if new_file is None:
        verdict['verdict'] = MANUAL
        verdict['reason'] = f'新基线 {new_base[:12]} 里没有 {target}（上游删了它或改了路径）'
        return verdict

    old_lines, _old_trailing = split_lines(old_file)
    new_lines, new_trailing = split_lines(new_file)
    if old_lines == new_lines:
        verdict['verdict'] = KEEP
        verdict['reason'] = '上游没有动这个文件'
        verdict['patch_bytes'] = patch
        return verdict

    result_lines, applied, failed = apply_hunks(new_lines, hunks)
    upstreamed = [index for index in failed if hunk_is_upstreamed(hunks[index], new_lines)]

    if not failed:
        verdict['verdict'] = KEEP
        verdict['reason'] = f'{len(hunks)} 个区块全部落在新基线上'
        new_text = '\n'.join(result_lines) + ('\n' if new_trailing else '')
        verdict['patch_bytes'] = make_patch(target, new_file, new_text.encode('utf-8'))
        return verdict

    if not applied and len(upstreamed) == len(failed):
        verdict['verdict'] = DROP
        verdict['reason'] = '新基线已经带了我们的改动'
        verdict['dropped_hunks'] = failed
        return verdict

    if applied and len(upstreamed) == len(failed):
        verdict['verdict'] = PARTIAL
        verdict['reason'] = (f'{len(upstreamed)} 个区块已被上游覆盖，其余 {len(applied)} 个仍然成立')
        verdict['dropped_hunks'] = upstreamed
        kept = [hunks[index] for index in applied]
        kept_lines, _applied_again, _still_failed = apply_hunks(new_lines, kept)
        new_text = '\n'.join(kept_lines) + ('\n' if new_trailing else '')
        verdict['patch_bytes'] = make_patch(target, new_file, new_text.encode('utf-8'))
        return verdict

    verdict['verdict'] = MANUAL
    verdict['reason'] = (f'{len(failed)} 个区块落不上新基线，其中 {len(upstreamed)} 个上游已经做了；'
                         f'第 {[index + 1 for index in failed]} 个区块要人看')
    verdict['dropped_hunks'] = upstreamed
    verdict['failed_hunks'] = [
        {'index': index + 1,
         'upstreamed': index in upstreamed,
         'added': [content for op, content in hunks[index][1] if op == '+'],
         'removed': [content for op, content in hunks[index][1] if op == '-'],
         'context': [content for op, content in hunks[index][1] if op == ' ']}
        for index in failed
    ]
    return verdict


def judge_all(old_base, new_base, repo=None):
    verdicts = []
    for patch_path, target in staging.patch_queue():
        verdicts.append(judge_patch(patch_path, target, old_base, new_base, repo=repo))
    return verdicts


def write_regenerated(verdicts, directory, base):
    """Write the new patches and the new series into *directory*."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    series = []
    for verdict in verdicts:
        if verdict['verdict'] == DROP:
            continue
        data = verdict.get('patch_bytes')
        if data is None:
            continue
        (directory / verdict['patch']).write_bytes(data)
        series.append(f"{verdict['patch']} {verdict['target']}")
    (directory / 'series').write_text('\n'.join(series) + '\n', encoding='utf-8')
    (directory / 'UPSTREAM_BASE').write_text(f'base {base}\n', encoding='utf-8')
    return series


def regenerate_from_tree(tree, base, directory, verdicts=None):
    """Write the patches that turn *base* into *tree*.

    After a person has fixed the files by hand in a worktree, this makes the
    patch files say what the tree actually does.  A target that the tree did
    not change keeps its patch: the worktree holds the unpatched upstream
    files, so "no change in the tree" means "nobody touched this one", not
    "the patch is empty".  A patch the judge called DROP_BASELINE_HAS_IT is
    dropped, and a target the tree changed is written out again.
    """
    tree = Path(tree)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    verdicts = verdicts or {}
    series = []
    changed = []
    dropped = []
    kept = []
    for patch_path, target in staging.patch_queue():
        after_path = tree / target
        verdict = verdicts.get(patch_path.name, {})
        if verdict.get('verdict') == DROP:
            dropped.append(patch_path.name)
            continue
        if not after_path.is_file():
            dropped.append(patch_path.name)
            continue
        before = read_at(base, target)
        if before is None:
            raise ValueError(f'{base}:{target} 不在新基线里')
        after = after_path.read_bytes()
        # The worktree's files are checked out with CRLF on Windows and the
        # blobs are LF, so compare the texts, not the bytes.
        after_lines, after_trailing = split_lines(after)
        before_lines, before_trailing = split_lines(before)
        if after_lines == before_lines and after_trailing == before_trailing:
            # Nobody touched this file in the tree: keep the patch as it is.
            if patch_path.is_file() and patch_path.stat().st_size:
                series.append(f'{patch_path.name} {target}')
                kept.append(patch_path.name)
                continue
            dropped.append(patch_path.name)
            continue
        data = make_patch(target, before, after)
        if data is None:
            dropped.append(patch_path.name)
            continue
        (directory / patch_path.name).write_bytes(data)
        series.append(f'{patch_path.name} {target}')
        changed.append(patch_path.name)
    (directory / 'series').write_text('\n'.join(series) + '\n', encoding='utf-8')
    resolved = git_text('rev-parse', base).strip() or base
    write_upstream_base(directory / 'UPSTREAM_BASE', resolved)
    return {'series': series, 'changed': changed, 'dropped': dropped, 'kept': kept}


def write_upstream_base(path, resolved):
    """Record the new base, keeping the other lines of the file."""
    lines = []
    if path.is_file():
        lines = path.read_text(encoding='utf-8').splitlines()
    out = []
    seen_base = False
    for line in lines:
        parts = line.split()
        if parts and parts[0] == 'base':
            out.append(f'base {resolved}')
            seen_base = True
            continue
        if parts and parts[0] == 'upstream':
            out.append(f'upstream {resolved}')
            continue
        out.append(line)
    if not seen_base:
        out.insert(0, f'base {resolved}')
    path.write_text('\n'.join(out) + '\n', encoding='utf-8')


def json_safe(verdicts):
    """The verdicts without the patch bytes, which are not JSON."""
    out = []
    for verdict in verdicts:
        item = {key: value for key, value in verdict.items() if key != 'patch_bytes'}
        item['patch_size'] = len(verdict['patch_bytes']) if verdict.get('patch_bytes') else 0
        out.append(item)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='upstream/main', help='the new upstream base')
    parser.add_argument('--old-base', default=None, help='the base the patches were made against')
    parser.add_argument('--report', type=Path, help='write the JSON report here')
    parser.add_argument('--regenerate', type=Path, help='write the new patches and series here')
    parser.add_argument('--from-tree', type=Path,
                        help='take the patched files from this tree and write the patches from them')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    old_base = args.old_base or recorded_base()
    if not old_base:
        print('webui/patches/UPSTREAM_BASE 里没有 base 行', file=sys.stderr)
        return 2
    code, _out, err = git('rev-parse', '--verify', f'{args.base}^{{commit}}')
    if code:
        print(f'找不到基线 {args.base}: {err.strip()}', file=sys.stderr)
        return 2

    if args.from_tree:
        directory = args.regenerate or ROOT / 'webui' / 'patches'
        verdicts = {v['patch']: v for v in judge_all(old_base, args.base)}
        result = regenerate_from_tree(args.from_tree, args.base, directory, verdicts)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f'从 {args.from_tree} 重新生成了 {len(result["changed"])} 条补丁，'
                  f'保留了 {len(result["kept"])} 条')
            for name in result['dropped']:
                print(f'  丢弃: {name}')
        return 0

    verdicts = judge_all(old_base, args.base)
    counts = {}
    for verdict in verdicts:
        counts[verdict['verdict']] = counts.get(verdict['verdict'], 0) + 1
    report = {'old_base': old_base, 'new_base': git_text('rev-parse', args.base).strip(),
              'counts': counts, 'verdicts': json_safe(verdicts)}

    if args.regenerate:
        series = write_regenerated(verdicts, args.regenerate, report['new_base'])
        report['series'] = series
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f'旧基线 {old_base[:12]}  新基线 {report["new_base"][:12]}')
        for verdict in verdicts:
            print(f'{verdict["verdict"]:<19} {verdict["patch"]}  {verdict["target"]}')
            print(f'                     {verdict["reason"]}')
        print('\n' + '  '.join(f'{name}={count}' for name, count in sorted(counts.items())))
    return 0 if counts.get(MANUAL, 0) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
