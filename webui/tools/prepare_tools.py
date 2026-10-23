#!/usr/bin/env python3
"""Prepare an offline tool folder on the build drive. Apple SDKs are not copied."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

OUTPUT_DIR = ''
SOURCE_TOOLS = ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=OUTPUT_DIR)
    parser.add_argument('--source-tools', default=SOURCE_TOOLS, help='Existing platform tool bundle to reuse')
    parser.add_argument('--python-runtime', type=Path, help='Optional redistributable Python runtime directory, with its license')
    parser.add_argument('--wheelhouse', type=Path, help='Install only from this offline wheel directory')
    parser.add_argument('--index-url', default='https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple', help='Python package mirror (ignored with --wheelhouse)')
    args = parser.parse_args()
    if not args.out: parser.error('Set OUTPUT_DIR or pass --out')
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from webui import staging
    out = Path(args.out).expanduser().resolve()
    if out == Path.home().resolve() or out == Path(out.anchor):
        parser.error('Use a dedicated subdirectory, not the filesystem or home root')
    out.mkdir(parents=True, exist_ok=True)
    if args.source_tools:
        source = Path(args.source_tools).resolve()
        if out == source or out.is_relative_to(source) or source.is_relative_to(out):
            parser.error('Source and destination tool folders must not overlap')
        # Explicit allowlist: no game files, keys, fonts, Apple SDKs or Metal tools.
        for name in ('dotnet', 'nx_extract', 'spirv-cross-build', 'ios-cross/toolchain/windows/iphone/bin', 'ios-cross/toolchain/windows/iphone/lib/clang'):
            original = source / name
            if original.exists(): shutil.copytree(original, out / name, dirs_exist_ok=True)
    if args.python_runtime:
        runtime = args.python_runtime.resolve()
        if not list(runtime.glob('LICENSE*')):
            parser.error('Python runtime must include its redistribution license')
        shutil.copytree(runtime, out / 'runtime', dirs_exist_ok=True)
    command = [sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', str(out / 'python-packages'),
               '-r', str(repo / 'webui/requirements.txt')]
    if args.wheelhouse: command += ['--no-index', '--find-links', str(args.wheelhouse)]
    else: command += ['--index-url', args.index_url]
    env = dict(os.environ, PIP_CACHE_DIR=str(out / 'pip-cache'), DOTNET_CLI_HOME=str(out / '.dotnet'),
               NUGET_PACKAGES=str(out / 'nuget'), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    subprocess.run(command, check=True, env=env)
    dotnet = out / 'dotnet' / ('dotnet.exe' if os.name == 'nt' else 'dotnet')
    executable = str(dotnet) if dotnet.is_file() else shutil.which('dotnet')
    if not executable: parser.error('A .NET 10 SDK is required to prepare nx_extract')
    stage = staging.ensure(repo, Path(os.environ.get('NX_STAGE_ROOT') or (repo / '.webui-data' / 'stage')))
    subprocess.run([executable, 'build', str(stage / 'dm/tools/nx_extract'), '-c', 'Release', '-o', str(out / 'nx_extract'),
                    '-p:BaseIntermediateOutputPath=' + str(out / 'obj') + os.sep], check=True, env=env)
    (out / 'nx_extract' / 'build.json').write_text(json.dumps({'stage_key': stage.parent.name}), encoding='utf-8')
    manifest = dict(system=platform.system(), architecture=platform.machine(), files=[], packages=[])
    for distribution in importlib.metadata.distributions(path=[str(out / 'python-packages')]):
        manifest['packages'].append(dict(name=distribution.metadata['Name'], version=distribution.version,
                                        license=distribution.metadata.get('License-Expression') or distribution.metadata.get('License', ''),
                                        source=distribution.metadata.get('Home-page', 'https://pypi.org/')))
    for file in sorted(out.rglob('*')):
        if not file.is_file() or any(part in ('.dotnet', 'nuget', 'obj', 'pip-cache', '__pycache__') for part in file.relative_to(out).parts): continue
        if file.name == 'manifest.json': continue
        with file.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest['files'].append(dict(path=file.relative_to(out).as_posix(), sha256=digest))
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Prepared tools:', out)
    print('Apple SDKs and Metal tools must be configured separately. Retain third-party licenses when distributing.')


if __name__ == '__main__': main()
