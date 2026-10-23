#!/usr/bin/env python3
"""Check original NSO rewrite sites against emitted tables and branch targets.

This verifies static coverage and file layout, not native execution semantics.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct

import capstone
import lz4.block


def original_text(path):
    data = path.read_bytes()
    fileoff, memory, size = struct.unpack_from('<III', data, 0x10)
    stored = struct.unpack_from('<I', data, 0x60)[0]
    raw = data[fileoff:fileoff + stored]
    if struct.unpack_from('<I', data, 12)[0] & 1:
        raw = lz4.block.decompress(raw, uncompressed_size=size)
    if memory != 0 or len(raw) != size:
        raise ValueError('Expected text at image offset zero')
    return raw, data[0x40:0x50].hex()


def verify(nso, patched, name):
    original, build = original_text(nso)
    image = (patched / f'{name}.patched.bin').read_bytes()
    headers = dict(line[2:].split() for line in
                   (patched / f'{name}.fixups.tsv').read_text().splitlines())
    if headers['BUILD_ID'] != build:
        raise ValueError(f'{name}: wrong build ID')
    patch_offset = int(headers['PATCH_OFF'], 0)
    patch_file = int(headers.get('FILE_IMAGE_LEN', headers['PATCH_OFF']), 0)
    patch_length = len(image) - patch_file
    points, windows, spin_edges = {}, [], []
    for line in (patched / f'{name}.sites.tsv').read_text().splitlines():
        columns = line.split('\t')
        address = int(columns[0], 0)
        if columns[1] == 'W':
            windows.append((address, int(columns[2], 0)))
        elif columns[1] == 'S':
            # The head stays original; only the back-edges branch into the copied region.
            spin_edges.extend(int(item, 0) for column in columns[2:] for item in column.split())
        elif columns[1] not in ('J', 'T'):
            points[address] = columns[1]
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    expected = {}
    for address in range(0, len(original), 4):
        word = struct.unpack_from('<I', original, address)[0]
        kind = None
        if word & 0xffe0001f == 0xd4000001:
            kind = 'svc'
        else:
            for mask, value, label in (
                (0xffffffe0, 0xd53bd040, 'tpidr_r'),
                (0xffffffe0, 0xd51bd040, 'tpidr_w'),
                (0xffffffe0, 0xd53bd060, 'tpidrro_r'),
                (0xffffffe0, 0xd53be020, 'cntpct'),
                (0xffffffe0, 0xd53be040, 'cntvct'),
                (0xffffffe0, 0xd53b0020, 'ctr'),
            ):
                if word & mask == value:
                    kind = label
                    break
        # x18/w18 must occur in one of the four AArch64 register fields.
        if kind is None and any((word >> shift) & 31 == 18 for shift in (0, 5, 10, 16)):
            instruction = next(md.disasm_lite(original[address:address + 4], address), None)
            if instruction and re.search(r'\b[xw]18\b', instruction[3]):
                kind = 'x18'
        if kind:
            expected[address] = kind
    uncovered = [hex(a) for a, kind in expected.items()
                 if points.get(a) != kind and not any(lo <= a < hi for lo, hi in windows)]
    if uncovered:
        raise ValueError(f'{name}: uncovered sites: {uncovered[:20]}')
    for address in sorted(set(points) | {lo for lo, _ in windows} | set(spin_edges)):
        word = struct.unpack_from('<I', image, address)[0]
        if points.get(address) == 'ctr':
            register = struct.unpack_from('<I', original, address)[0] & 31
            if word != 0xd2a00080 | register:
                raise ValueError(f'{name}: wrong CTR constant at {address:#x}')
            continue
        if word >> 26 != 0b000101:
            raise ValueError(f'{name}: no branch at rewrite site {address:#x}')
        immediate = word & 0x3ffffff
        if immediate & 0x2000000:
            immediate -= 0x4000000
        target = address + 4 * immediate
        if not patch_offset <= target < patch_offset + patch_length:
            raise ValueError(f'{name}: branch leaves patch area at {address:#x}')
    return {'module': name, 'build_id': build, 'expected_sites': dict(Counter(expected.values())),
            'table_points': len(points), 'exclusive_windows': len(windows),
            'uncovered_sites': 0, 'branch_targets_within_patch': True,
            'patched_bytes': len(image)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exefs', type=Path)
    ap.add_argument('patched', type=Path)
    ap.add_argument('modules', nargs='+')
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    results = [verify(args.exefs / name, args.patched, name) for name in args.modules]
    args.report.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
