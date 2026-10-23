"""Strict unified-diff application with CRLF/LF normalization.

The build stage must not depend on a working ``git`` (the Windows Scoop shim can
fail).  This module applies the fork's small, exact patch queue to source text
and rejects fuzz, path escapes and target mismatches.
"""
from __future__ import annotations

from pathlib import Path
import re

__all__ = ['DiffError', 'apply_bytes', 'apply_file']

_HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


class DiffError(ValueError):
    """A patch is malformed or does not match its target."""


def _normalize(text: str) -> str:
    if text.startswith('\ufeff'):
        text = text[1:]
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _strip_path(value: str) -> str:
    value = value.split('\t', 1)[0].strip()
    if value == '/dev/null':
        raise DiffError('delete patches are not supported')
    if value.startswith(('a/', 'b/')):
        value = value[2:]
    if value.startswith('/') or '..' in Path(value).parts:
        raise DiffError(f'unsafe patch path: {value}')
    return value


def _parse(patch: bytes, expected_target: str | None):
    text = _normalize(patch.decode('utf-8'))
    lines = text.split('\n')
    if lines and lines[-1] == '':
        lines.pop()
    target = None
    hunks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('--- '):
            if i + 1 >= len(lines) or not lines[i + 1].startswith('+++ '):
                raise DiffError('malformed file header')
            if target is not None:
                raise DiffError('a patch must target one file')
            target = _strip_path(lines[i + 1][4:])
            i += 2
            continue
        if line.startswith('@@ '):
            match = _HUNK.match(line)
            if not match:
                raise DiffError(f'malformed hunk header: {line}')
            old_start = int(match.group(1))
            old_count = int(match.group(2) or '1')
            new_count = int(match.group(4) or '1')
            ops = []
            i += 1
            while i < len(lines):
                body = lines[i]
                if body.startswith('@@ ') or body.startswith('diff --git '):
                    break
                if body == r'\ No newline at end of file':
                    if not ops:
                        raise DiffError('newline marker without a line')
                    op, content, _ = ops[-1]
                    ops[-1] = (op, content, False)
                    i += 1
                    continue
                if not body:
                    raise DiffError('empty line inside a hunk')
                op = body[0]
                if op not in ' +-':
                    raise DiffError(f'unexpected hunk line: {body[:60]!r}')
                ops.append((op, body[1:], True))
                i += 1
            if old_count != sum(1 for op, _, _ in ops if op in ' -'):
                raise DiffError('hunk old-line count mismatch')
            if new_count != sum(1 for op, _, _ in ops if op in ' +'):
                raise DiffError('hunk new-line count mismatch')
            hunks.append((old_start, ops))
            continue
        i += 1
    if target is None:
        raise DiffError('patch has no file header')
    if expected_target is not None and target != expected_target:
        raise DiffError(f'patch target {target!r} != expected {expected_target!r}')
    if not hunks:
        raise DiffError('patch has no hunks')
    return target, hunks


def apply_bytes(target: bytes, patch: bytes, expected_target: str | None = None) -> bytes:
    """Apply *patch* to *target* and return LF-normalized bytes."""
    target_text = _normalize(target.decode('utf-8'))
    trailing = target_text.endswith('\n')
    lines = target_text.split('\n')
    if trailing:
        lines.pop()
    _, hunks = _parse(patch, expected_target)
    result = []
    pos = 0
    for old_start, ops in hunks:
        start = old_start - 1
        if start < pos or start > len(lines):
            raise DiffError(f'hunk starts outside the file at {old_start}')
        result.extend(lines[pos:start])
        pos = start
        for op, content, _has_newline in ops:
            if op in ' -':
                if pos >= len(lines) or lines[pos] != content:
                    actual = lines[pos] if pos < len(lines) else '<EOF>'
                    raise DiffError(f'context mismatch at line {pos + 1}: expected {content!r}, got {actual!r}')
                if op == ' ':
                    result.append(content)
                pos += 1
            else:
                result.append(content)
    result.extend(lines[pos:])
    for _op, _content, has_newline in hunks[-1][1]:
        if not has_newline:
            trailing = False
    return ('\n'.join(result) + ('\n' if trailing else '')).encode('utf-8')


def apply_file(path: Path, patch: bytes, expected_target: str) -> bytes:
    """Apply *patch* to *path* in memory; return the new bytes (does not write)."""
    return apply_bytes(path.read_bytes(), patch, expected_target)
