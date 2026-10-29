#!/usr/bin/env python3
"""Link compiled iOS host objects and the real rewritten-game embed object.

Produces an unsigned Mach-O executable. Shader/resource assembly is separate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess


def sdk_version(path):
    try:
        return str(json.loads((path / 'SDKSettings.json').read_text(encoding='utf-8')).get('Version') or '26.5')
    except (OSError, ValueError):
        return '26.5'


def macho_layout(data):
    if struct.unpack_from('<II', data) != (0xfeedfacf, 0x100000c):
        raise ValueError('Expected 64-bit ARM64 Mach-O')
    ncmds, sizeofcmds = struct.unpack_from('<II', data, 16)
    offset, sections, segments, platforms, signed = 32, {}, {}, [], False
    for _ in range(ncmds):
        command, size = struct.unpack_from('<II', data, offset)
        if size < 8 or offset + size > 32 + sizeofcmds:
            raise ValueError('Invalid Mach-O load command bounds')
        if command == 0x19:
            name = data[offset + 8:offset + 24].split(b'\0')[0].decode()
            maximum, initial, count = struct.unpack_from('<III', data, offset + 56)
            segments[name] = {'maximum': maximum, 'initial': initial}
            for i in range(count):
                section = offset + 72 + 80 * i
                label = data[section:section + 16].split(b'\0')[0].decode()
                segment = data[section + 16:section + 32].split(b'\0')[0].decode()
                _, length, file_offset = struct.unpack_from('<QQI', data, section + 32)
                sections[(segment, label)] = (file_offset, length)
        elif command == 0x32:
            platforms.append(struct.unpack_from('<I', data, offset + 8)[0])
        elif command == 0x1d:
            signed = True
        offset += size
    return sections, segments, platforms, signed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--lld', required=True, type=Path)
    ap.add_argument('--sdk', required=True, type=Path)
    ap.add_argument('--build', required=True, type=Path)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[3]
    build, sdk = args.build.resolve(), args.sdk.resolve()
    inventory = json.loads((build / 'inventory.json').read_text(encoding='utf-8'))
    objects = []
    for entry in inventory:
        if entry['exit_code']:
            raise ValueError(f'Compile failure still recorded: {entry["source"]}')
        obj = Path(entry['object'])
        data = obj.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'Object changed after compilation: {obj}')
        if struct.unpack_from('<II', data) != (0xfeedfacf, 0x100000c):
            raise ValueError(f'Object is not ARM64 Mach-O: {obj}')
        objects.append(str(obj))
    embed = build / 'embed.o'
    embed_data = embed.read_bytes()
    embed_sections, _, _, _ = macho_layout(embed_data)
    frameworks = re.findall(r'-framework (\w+)', (root / 'dm/host/Makefile').read_text(encoding='utf-8'))
    frameworks = [f for f in frameworks if f != 'Cocoa']
    frameworks += ['UIKit', 'Foundation', 'GameController', 'CoreText', 'CoreGraphics', 'AVFAudio', 'CoreMotion', 'MetalFX']
    command = ['-arch', 'arm64', '-platform_version', 'ios', '26.0', sdk_version(sdk), '--error-limit=0',
               '-syslibroot', str(sdk), '-F', str(sdk / 'System/Library/Frameworks'),
               '-F', str(sdk / 'System/Library/SubFrameworks'), '-L', str(sdk / 'usr/lib'),
               '-e', '_main', '-dead_strip', '-no_adhoc_codesign',
               '-o', str(build / 'DmIOS')]
    for flag in shlex.split((build / 'embed_link_flags.txt').read_text(encoding='utf-8')):
        if not flag.startswith('-Wl,'):
            raise ValueError(f'Unexpected embed linker flag: {flag}')
        command.extend(flag[4:].split(','))
    command += objects + [str(embed), '-lSystem', '-lobjc']
    for framework in dict.fromkeys(frameworks):
        command += ['-framework', framework]
    response = build / 'link.rsp'
    response.write_text('\n'.join('"' + s.replace('\\', '/').replace('"', '\\"') + '"'
                                  for s in command) + '\n', encoding='utf-8')
    with (build / 'link.log').open('w', encoding='utf-8') as log:
        result = subprocess.run([str(args.lld.resolve()), '-flavor', 'darwin', '@' + str(response)],
                                stdout=log, stderr=subprocess.STDOUT)
    print((build / 'link.log').read_text(encoding='utf-8', errors='replace'))
    if result.returncode:
        raise SystemExit(result.returncode)
    executable = (build / 'DmIOS').read_bytes()
    if struct.unpack_from('<I', executable, 12)[0] != 2:
        raise ValueError('Link output is not MH_EXECUTE')
    sections, segments, platforms, signed = macho_layout(executable)
    if platforms != [2] or signed:
        raise ValueError('Expected an unsigned iOS executable')
    if [name for name, permissions in segments.items() if permissions['initial'] & 4] != ['__TEXT']:
        raise ValueError('Expected one executable segment, __TEXT')
    checked = []
    for name, (source_offset, source_size) in embed_sections.items():
        if source_size == 0:
            continue  # the assembler also emits an empty default __text section
        if name not in sections:
            raise ValueError(f'Linker removed embedded game section {name}')
        file_offset, size = sections[name]
        if size != source_size or executable[file_offset:file_offset + size] != embed_data[source_offset:source_offset + size]:
            raise ValueError(f'Embedded game section changed during link: {name}')
        checked.append(','.join(name))
    if not checked:
        raise ValueError('No nonempty embedded game sections were verified')
    report = {'objects': len(objects), 'embed_bytes': embed.stat().st_size,
              'executable_bytes': len(executable),
              'sha256': hashlib.sha256(executable).hexdigest(), 'signed': signed,
              'ios_platform': platforms[0], 'embedded_sections_verified': checked,
              'segment_permissions': segments}
    (build / 'link_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
