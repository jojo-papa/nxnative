"""Bounded PFS0/HFS0 parsing and streaming, lossless XCI/NSZ conversion."""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int


def read_exact(stream, count):
    value = stream.read(count)
    if len(value) != count:
        raise ValueError('Truncated container')
    return value


def entries(path, offset=0, length=None, magic=b'PFS0'):
    path = Path(path)
    end = offset + length if length is not None else path.stat().st_size
    if offset < 0 or end > path.stat().st_size or end - offset < 16:
        raise ValueError('Invalid container bounds')
    with path.open('rb') as stream:
        stream.seek(offset)
        found, count, strings, _ = struct.unpack('<4sIII', read_exact(stream, 16))
        if found != magic or count > 100000 or strings > 16 * 1024 * 1024:
            raise ValueError('Unsupported or invalid container header')
        stride = 64 if magic == b'HFS0' else 24
        data_start = offset + 16 + count * stride + strings
        if data_start > end:
            raise ValueError('Container index exceeds file')
        table = read_exact(stream, count * stride)
        names = read_exact(stream, strings)
        result, seen, spans = [], set(), []
        for i in range(count):
            start, size, name_offset = struct.unpack_from('<QQI', table, i * stride)
            stop = names.find(b'\0', name_offset)
            if name_offset >= len(names) or stop < 0:
                raise ValueError('Invalid entry name offset')
            name = names[name_offset:stop].decode('utf-8')
            if not name or name in ('.', '..') or any(c in name for c in '/\\:\0') or name.lower() in seen:
                raise ValueError('Unsafe or duplicate container entry')
            seen.add(name.lower())
            if start + size > end - data_start:
                raise ValueError('Entry exceeds container bounds')
            absolute = data_start + start
            if magic == b'HFS0':
                hashed_size = struct.unpack_from('<I', table, i * stride + 20)[0]
                hashed_offset = struct.unpack_from('<Q', table, i * stride + 24)[0]
                if hashed_offset + hashed_size > size:
                    raise ValueError('Invalid HFS0 hash range')
                if hashed_size:
                    stream.seek(absolute + hashed_offset)
                    digest = hashlib.sha256()
                    remaining = hashed_size
                    while remaining:
                        block = read_exact(stream, min(1024 * 1024, remaining))
                        digest.update(block); remaining -= len(block)
                    if digest.digest() != table[i * stride + 32:i * stride + 64]:
                        raise ValueError('HFS0 integrity check failed')
            result.append(Entry(name, absolute, size))
            if size:
                spans.append((absolute, absolute + size))
        spans.sort()
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError('Overlapping container entries')
        return result


def xci_entries(path):
    with Path(path).open('rb') as stream:
        stream.seek(0x100)
        if read_exact(stream, 4) != b'HEAD':
            raise ValueError('Expected a standard uncompressed XCI')
        stream.seek(0x130)
        root = struct.unpack('<Q', read_exact(stream, 8))[0]
    partitions = entries(path, root, magic=b'HFS0')
    secure = next((e for e in partitions if e.name == 'secure'), None)
    if secure is None:
        raise ValueError('XCI has no secure partition')
    return entries(path, secure.offset, secure.size, b'HFS0')


def repack(source, selected, destination, progress=lambda *args: None, hashes=None):
    """Write PFS0 without changing NCA contents, rights, headers or signatures."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Output already exists')
    temporary = destination.with_name(destination.name + '.partial')
    names, table, offset = bytearray(), bytearray(), 0
    for item in selected:
        table.extend(struct.pack('<QQII', offset, item.size, len(names), 0))
        names.extend(item.name.encode() + b'\0'); offset += item.size
    names.extend(b'\0' * (-(16 + len(table) + len(names)) % 16))
    total, done = offset, 0
    try:
        with Path(source).open('rb') as src, temporary.open('xb') as dst:
            dst.write(struct.pack('<4sIII', b'PFS0', len(selected), len(names), 0))
            dst.write(table); dst.write(names)
            for item in selected:
                src.seek(item.offset)
                remaining, digest = item.size, hashlib.sha256()
                while remaining:
                    block = read_exact(src, min(4 * 1024 * 1024, remaining))
                    dst.write(block); digest.update(block)
                    remaining -= len(block); done += len(block)
                    progress(done, total)
                if hashes and item.name in hashes and digest.hexdigest() != hashes[item.name]:
                    raise ValueError('NCA content hash mismatch: ' + item.name)
        entries(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def decompress_nsz(source, destination, keys, run, folder):
    """Decompress an NSZ into NSPs with the MIT-licensed nsz package."""
    if importlib.util.find_spec('nsz') is None:
        raise ValueError('NSZ conversion needs the nsz Python package. Restart the WebUI so it can install it, then retry.')
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    run(folder, [sys.executable, '-c', 'import nsz; nsz.main()', '-D', str(source),
                 '-o', str(destination), '--keys', str(keys), '--overwrite', '--minimal-output'])
    outputs = sorted(destination.rglob('*.nsp'))
    if not outputs:
        raise ValueError('NSZ decompression produced no NSP')
    return outputs


def catalog(extractor, keys, package):
    result = subprocess.run([str(extractor), str(keys), '--catalog', str(package)],
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise ValueError('Package metadata could not be read. Check keys and container integrity.')
    value = json.loads(result.stdout)
    if not value:
        raise ValueError('No application metadata found')
    return value


def convert(source, destination, extractor, keys, progress=lambda *args: None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    staging = destination / 'secure.nsp'
    allowed = [e for e in xci_entries(source) if e.name.lower().endswith(('.nca', '.tik', '.cert'))]
    try:
        repack(source, allowed, staging, progress)
        titles = catalog(extractor, keys, staging)
        index = {e.name: e for e in entries(staging)}
        outputs = []
        for title in titles:
            required = [title['meta']] + [c['name'] for c in title['contents'] if c['type'] != 6]
            if any(name not in index for name in required):
                raise ValueError('XCI is missing content referenced by its metadata')
            selected = [index[name] for name in dict.fromkeys(required)]
            selected += [e for e in index.values() if e.name.endswith(('.tik', '.cert'))]
            out = destination / f"{title['title_id']}_v{title['version']}.nsp"
            hashes = {c['name']: c['sha256'] for c in title['contents'] if c['type'] != 6}
            repack(staging, selected, out, progress, hashes)
            catalog(extractor, keys, out)
            outputs.append(out)
        return outputs
    finally:
        staging.unlink(missing_ok=True)
