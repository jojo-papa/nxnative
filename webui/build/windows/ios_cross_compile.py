#!/usr/bin/env python3
"""Compile the existing iOS host sources with a Windows-hosted clang.

This is a compile-only bring-up tool, not an IPA packager. Source lists follow
dm/host/Makefile. Missing profile/shader inputs remain compiler errors.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


def source_list(repo):
    host = repo / 'dm/host'
    text = (host / 'Makefile').read_text(encoding='utf-8')

    def expand(variable):
        value = re.search(rf'^{variable}=(.*)$', text, re.M).group(1)

        def wildcard(match):
            paths = {p.resolve() for pattern in match[1].split()
                     for p in host.glob(pattern)}
            # Return relative POSIX paths so whitespace tokenization stays safe.
            import os
            return ' '.join(Path(os.path.relpath(p, host)).as_posix()
                            for p in sorted(paths))

        value = re.sub(r'\$\(sort \$\(wildcard (.*?)\)\)', wildcard, value)
        if '$' in value:
            raise ValueError(f'Unsupported Make expression in {variable}: {value}')
        return [(host / word).resolve() for word in value.split()]

    sources = [p for p in expand('SRC') + expand('GFX')
               if not p.stem.endswith('_mac')]
    sources += sorted((repo / 'dm/ios/Sources').glob('*.m'))
    sources.append(repo / 'webui/build/windows/launcher_stub.m')   # Windows has no Swift compiler; front_ios.m's dm_show_launcher
    sources += sorted((repo / 'dm/third_party/libvpx').rglob('*.c'))
    if len(sources) != len(set(sources)):
        raise ValueError('Duplicate sources in expanded iOS source list')
    if any(not p.is_file() for p in sources):
        raise ValueError('A source from the Makefile does not exist')
    return sources


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--clang', required=True, type=Path)
    ap.add_argument('--sdk', required=True, type=Path)
    ap.add_argument('--profile', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--cpu', default='apple-a16')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--only', help='Compile only repository-relative paths matching this regex')
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[3]
    out, profile, sdk, clang = (p.resolve() for p in
                                (args.out, args.profile, args.sdk, args.clang))
    sources = source_list(repo)
    if args.only:
        sources = [p for p in sources if re.search(args.only, p.relative_to(repo).as_posix())]
    if not sources:
        ap.error('No source files selected')
    if args.jobs < 1:
        ap.error('--jobs must be positive')
    (out / 'include').mkdir(parents=True, exist_ok=True)
    (out / 'objects').mkdir(exist_ok=True)
    (out / 'logs').mkdir(exist_ok=True)
    sys.path.insert(0, str(repo / 'dm/games'))
    import game
    g = game.Game(profile)
    (out / 'include/game_profile.h').write_text(game.header(g), encoding='utf-8')
    includes = [out / 'include', profile, repo / 'dm/host',
                repo / 'dm/gfx/nvn/include', repo / 'dm/third_party/vulkan-headers/include',
                repo / 'dm/third_party/libvpx', repo / 'dm/third_party/libvpx/config',
                repo / 'dm/third_party/stb_vorbis']
    includes += sorted({p.parent for p in source_list(repo)})
    common = [str(clang), '-target', 'arm64-apple-ios26.0', '-isysroot', str(sdk),
              '-F', str(sdk / 'System/Library/SubFrameworks'),
              '-DUSE_UIKIT_PUBLIC_HEADERS=1', '-fobjc-arc', f'-mcpu={args.cpu}',
              '-O1', '-g', '-Wno-deprecated-declarations', '-Wno-unused-function']
    common += [f'-I{p}' for p in dict.fromkeys(includes)]

    def compile_one(source):
        relative = source.relative_to(repo).as_posix()
        name = relative.replace('/', '__') + '.o'
        obj = out / 'objects' / name
        command = common + (['-Dmain=dm_main'] if relative == 'dm/host/main.c' else [])
        command += ['-c', str(source), '-o', str(obj)]
        log = out / 'logs' / (name + '.log')
        with log.open('w', encoding='utf-8') as output:
            process = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        result = {'source': relative, 'command': command, 'exit_code': process.returncode,
                  'object': str(obj), 'log': str(log)}
        if process.returncode == 0:
            result['sha256'] = hashlib.sha256(obj.read_bytes()).hexdigest()
        return result

    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(compile_one, p) for p in sources]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"[{len(results)}/{len(sources)}] {'OK' if result['exit_code'] == 0 else 'FAIL'} {result['source']}", flush=True)
    results.sort(key=lambda r: r['source'])
    inventory = out / ('inventory.json' if not args.only else 'inventory_selected.json')
    inventory.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    failed = [r for r in results if r['exit_code']]
    for item in failed:
        print(Path(item['log']).read_text(encoding='utf-8', errors='replace'), flush=True)
    print(f'Compiled {len(results) - len(failed)}/{len(results)} sources; inventory: {inventory}')
    return bool(failed)


if __name__ == '__main__':
    sys.exit(main())
