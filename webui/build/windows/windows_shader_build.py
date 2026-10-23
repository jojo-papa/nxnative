#!/usr/bin/env python3
"""Materialize and run an isolated Windows port of the pinned shader chain.

The generated sources and real tool fingerprints define a separate chain ID.
The repository's Mac chain and its lock are never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def replace(source, old, new):
    if old not in source:
        raise ValueError('Upstream shader source changed: ' + old[:100])
    return source.replace(old, new)



def cache_directory(output, directory=None):
    """Keep Python-only shader cache IO usable beyond Windows MAX_PATH."""
    path = str(Path(directory or Path(output) / 'mac/cas').resolve())
    if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
        path = '\\\\?\\UNC\\' + path[2:] if path.startswith('\\\\') else '\\\\?\\' + path
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('profile', 'packages', 'out', 'metal', 'spirv_cross', 'dotnet'):
        ap.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    ap.add_argument('--cache-dir', type=Path, help='Shared content-addressed shader cache')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--prepare-only', action='store_true')
    ap.add_argument('keys', nargs='*')
    a = ap.parse_args()
    repo = Path(__file__).resolve().parents[3]
    root = a.out.resolve()
    tools = root / 'chain/gfx/tools'
    tools.mkdir(parents=True, exist_ok=True)
    original = repo / 'dm/gfx/tools'
    for p in original.glob('dmsh_*.py'):
        shutil.copyfile(p, tools / p.name)
    for folder in ('dmsh_xlate',):
        shutil.copytree(original / folder, tools / folder, dirs_exist_ok=True)
    # Git's Windows checkout uses CRLF; the pinned translator embeds LF sources.
    for name in ('Program.cs', 'dmsh_xlate.csproj'):
        p = tools / 'dmsh_xlate' / name
        p.write_bytes(p.read_bytes().replace(b'\r\n', b'\n'))
    for folder, filename in (('games', 'game.py'), ('ios/tools', 'ios_metal.py')):
        dest = root / 'chain' / folder
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / 'dm' / folder / filename, dest / filename)
    metal = str(a.metal.resolve())
    metallib = str(a.metal.resolve().with_name('metallib.exe'))
    dotnet = str(a.dotnet.resolve())
    dll = str(original / 'dmsh_xlate_bin/dmsh_xlate.dll')
    sc = str(a.spirv_cross.resolve())
    cache = root / 'module_cache'
    cache.mkdir(exist_ok=True)
    def command(target, relaxed=False):
        return [metal, '-c', '-target', target, '-fpreserve-invariance',
                '-fmodules-cache-path=' + str(cache)] + (['-fmetal-math-mode=relaxed'] if relaxed else [])
    mac = command('air64-apple-macos14.0')
    ios = command('air64-apple-ios18.0', True)
    build = (tools / 'dmsh_build.py').read_text(encoding='utf-8')
    build = replace(build, "MAC_METAL = ['xcrun', '-sdk', 'macosx', 'metal', '-c', '-fpreserve-invariance']", 'MAC_METAL = ' + repr(mac))
    build = replace(build, "'; xcrun -sdk macosx metallib'", repr('; ' + metallib))
    build = replace(build, "['xcrun', '-sdk', 'macosx', 'metallib', air, '-o', lib]", repr([metallib]) + " + [air, '-o', lib]")
    build = replace(build, '[XLATE, jp, w]', repr([dotnet, dll]) + ' + [jp, w]')
    build = replace(build, "['spirv-cross',", '[' + repr(sc) + ',')
    (tools / 'dmsh_build.py').write_text(build, encoding='utf-8')
    ip = root / 'chain/ios/tools/ios_metal.py'
    src = ip.read_text(encoding='utf-8')
    start = src.index('METAL = ')
    end = src.index('RECORD = ', start)
    src = src[:start] + 'METAL = ' + repr(ios) + '\nMETALLIB = ' + repr([metallib]) + '\n' + src[end:]
    ip.write_text(src, encoding='utf-8')
    cp = tools / 'dmsh_mtlcache.py'
    src = cp.read_text(encoding='utf-8')
    line = next(x for x in src.splitlines() if x.startswith('_clonefile ='))
    src = replace(src, line, '_clonefile = None')
    start, end = src.index('def compiler_id('), src.index('\n\nclass Cache:')
    identity = json.dumps({str(Path(x).name): hashlib.sha256(Path(x).read_bytes()).hexdigest()
                           for x in (metal, metallib, sc)}, sort_keys=True)
    src = src[:start] + 'def compiler_id(sdk):\n    return sdk + ' + repr(identity) + '\n' + src[end:]
    cp.write_text(src, encoding='utf-8')
    cp = tools / 'dmsh_chain.py'
    src = cp.read_text(encoding='utf-8')
    src = replace(src, "['which', 'spirv-cross']", "['where.exe', " + repr(sc) + ']')
    src = replace(src, "[os.path.join(XLATE_DIR, 'dmsh_xlate'), '--source-sha']", repr([dotnet, dll, '--source-sha']))
    src = replace(src, "['xcrun', '-sdk', sdk, 'metal', '--version']", repr([metal, '--version']))
    src = replace(src, '    return t\n', '    t["windows_tools"] = ' + repr(identity) + '\n    return t\n')
    src = replace(src, "'tools/dmsh_chain.lock']", "'tools/dmsh_chain.lock', 'tools/windows_shader_build.py', 'tools/dmsh_mtlcache.py']")
    cp.write_text(src, encoding='utf-8')
    # Windows indexers can briefly hold a newly written cache file without
    # delete sharing. Retry the same atomic operation; never discard a failure.
    retry = '''
import time
def windows_replace(source, destination):
    for attempt in range(40):
        try:
            os.replace(source, destination)
            return
        except PermissionError as error:
            if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 39:
                raise
            time.sleep(0.1)

'''
    for name in ('dmsh_build.py', 'dmsh_mtlcache.py'):
        p = tools / name
        src = p.read_text(encoding='utf-8').replace('os.replace(', 'windows_replace(')
        # Place the helper before top-level build/cache initialization.
        anchor = 'DM_ROOT = ' if name == 'dmsh_build.py' else 'FORMAT = '
        position = src.index(anchor)
        p.write_text(src[:position] + retry + src[position:], encoding='utf-8')
    shutil.copyfile(__file__, tools / 'windows_shader_build.py')
    env = dict(os.environ, DM_GAME=str(a.profile.resolve()), XLATE=str(original / 'dmsh_xlate_bin/dmsh_xlate'),
               PYTHONUTF8='1', J=str(a.jobs), IOSOUT=str(root / 'ios'), WORK=str(root / 'work'))
    # CAS holds only Python-managed files; external compilers use WORK and IOSOUT.
    # Prefix the cache root so atomic copies and JSON writes can exceed MAX_PATH.
    env['DMSH_CAS'] = cache_directory(root, a.cache_dir or env.get('DMSH_CAS'))
    print('Shader cache: ' + env['DMSH_CAS'], flush=True)
    (root / 'work').mkdir(exist_ok=True)
    # Verify the original translator before generating a distinct Windows lock.
    lock = dict(x.split('\t', 1) for x in (original / 'dmsh_chain.lock').read_text(encoding='utf-8').splitlines() if '\t' in x and not x.startswith('#'))
    for name in ('dmsh_xlate.dll', 'Ryujinx.Graphics.Shader.dll', 'Ryujinx.Common.dll'):
        if hashlib.sha256((original / 'dmsh_xlate_bin' / name).read_bytes()).hexdigest()[:16] != lock[name]:
            raise ValueError('Pinned translator differs: ' + name)
    subprocess.run([sys.executable, str(cp), '--update-lock'], env=env, check=True)
    subprocess.run([sys.executable, str(cp), '--check-tools'], env=env, check=True)
    subprocess.run([sys.executable, str(cp), '--header'], env=env, check=True)
    (root / 'windows_tools.json').write_text(identity + '\n', encoding='utf-8')
    if not a.prepare_only:
        subprocess.run([sys.executable, str(tools / 'dmsh_build.py'), str(a.packages.resolve()), str(root / 'mac'), *a.keys], env=env, check=True)


if __name__ == '__main__':
    main()
