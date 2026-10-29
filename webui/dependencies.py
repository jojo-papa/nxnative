"""Allowlisted dependency installation through the existing logged task queue."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

from .bootstrap import DEFAULT_INDEX, PYTHON_INDEXES
from . import staging
from .jobs import emit
from .file_tools import filesystem_path, remove_stage
from .platform_tools import tool_path, find_dotnet, dotnet_environment, probe

PYTHON_PACKAGES = {'lz4': 'lz4', 'capstone': 'capstone', 'fontTools': 'fonttools', 'PIL': 'Pillow', 'nsz': 'nsz==5.0.0'}
BREW_PACKAGES = {'xcodegen', 'zstd', 'spirv-cross'}
DOTNET_METADATA = 'https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json'

def brew_path(config):
    return shutil.which('brew', path=tool_path(config))

def install_method(name, config, system=None, discovery=None):
    system = system or platform.system()
    if name in PYTHON_PACKAGES:
        return 'python'
    if name in ('dotnet', 'extractor') and system in ('Darwin', 'Windows') and platform.machine().lower() in ('arm64', 'aarch64', 'x86_64', 'amd64'):
        return 'local'
    if system == 'Windows':
        if name in ('clang', 'lld', 'spirv_cross') and platform.machine().lower() in ('amd64', 'x86_64', 'arm64', 'aarch64'):
            return 'portable'
        if name == 'sdk':
            from .apple_tools import sdk_install_method
            return sdk_install_method(config, discovery)
    if name == 'mac_metal' and system == 'Darwin' and probe(['/usr/bin/xcodebuild', '-version']).startswith('Xcode '):
        return 'xcode'
    if name in BREW_PACKAGES and system == 'Darwin':
        return 'homebrew' if brew_path(config) else 'direct'
    return 'manual'

def download(url, destination, folder, expected_hash, algorithm='sha512', label='.NET'):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('builds.dotnet.microsoft.com', 'download.visualstudio.microsoft.com', 'ci.dot.net', 'github.com', 'codeload.github.com'):
        raise ValueError('Unexpected dependency download origin')
    destination = filesystem_path(destination)
    if destination.is_file():
        digest = hashlib.new(algorithm)
        with destination.open('rb') as existing:
            while block := existing.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest().lower() == expected_hash.lower():
            print('Reusing verified download: ' + label, flush=True)
            emit(folder, 'stage', name='Reusing verified download: ' + label)
            return
        destination.unlink()
    temporary = destination.with_name(destination.name + '.partial')
    digest = hashlib.new(algorithm)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            total = int(response.headers.get('Content-Length', 0))
            done, last = 0, -1
            while block := response.read(1024 * 1024):
                output.write(block); digest.update(block); done += len(block)
                if done // (8 * 1024**2) != last:
                    last = done // (8 * 1024**2)
                    print(f'Downloaded {done // 1024**2} / {total // 1024**2} MiB', flush=True)
                    emit(folder, 'stage', name=f'Downloading {label}: {done // 1024**2} / {total // 1024**2} MiB')
        if digest.hexdigest().lower() != expected_hash.lower():
            raise ValueError(label + ' ' + algorithm + ' checksum mismatch')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def unpack(archive, destination, source_root=None):
    archive, destination = filesystem_path(archive), filesystem_path(destination)
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                path = (destination / item.filename).resolve()
                if not path.is_relative_to(destination.resolve()) or ':' in item.filename or '\\' in item.filename:
                    raise ValueError('Unsafe archive member')
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            members = None
            if source_root:
                # Only source files and licenses are needed for a CLI build.
                # Regression shader paths can exceed Windows' legacy path limit.
                members = [item for item in source if item.isfile() and
                           Path(item.name).parts[0] == source_root and
                           (len(Path(item.name).parts) == 2 or Path(item.name).parts[1] == 'LICENSES')]
            source.extractall(destination, members=members, filter='data')

def install_dotnet(folder, root, run):
    system = platform.system()
    arch = {'arm64': 'arm64', 'aarch64': 'arm64', 'x86_64': 'x64', 'amd64': 'x64'}[platform.machine().lower()]
    rid = ('win' if system == 'Windows' else 'osx') + '-' + arch
    suffix = '.zip' if system == 'Windows' else '.tar.gz'
    print('Reading official .NET 10 SDK release metadata', flush=True)
    with urllib.request.urlopen(DOTNET_METADATA, timeout=60) as response:
        metadata = json.load(response)
    sdk = next(sdk for release in metadata['releases'] for sdk in release.get('sdks', [release['sdk']]) if sdk['version'] == metadata['latest-sdk'])
    asset = next(f for f in sdk['files'] if f['rid'] == rid and f['url'].endswith(suffix))
    cache = root / 'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / ('dotnet-' + sdk['version'] + '-' + rid + suffix)
    download(asset['url'], archive, folder, asset['hash'])
    stage = root / ('.dotnet-' + folder.name[:16])
    stage.mkdir(parents=True, exist_ok=True)
    try:
        unpack(archive, stage)
        binary = stage / ('dotnet.exe' if system == 'Windows' else 'dotnet')
        run(folder, [binary, '--version'], dict(os.environ, DOTNET_ROOT=str(stage)))
        if (root / 'dotnet').exists():
            raise ValueError('The configured dotnet directory already exists but is incomplete. Choose a new tools directory or repair it manually.')
        stage.rename(root / 'dotnet')
    finally:
        remove_stage(stage, root)
    # Keep a verified archive on failure so retries do not download it again.
    archive.unlink(missing_ok=True)

MAC_DOWNLOADS = {
    'xcodegen': ('https://github.com/yonaskolb/XcodeGen/releases/download/2.46.0/xcodegen.zip',
                '4d9e34b62172d645eed6457cac13fc222569974098ef4ee9c3368bedf0196806', 'xcodegen', 'bin/xcodegen'),
    'zstd': ('https://github.com/facebook/zstd/releases/download/v1.5.7/zstd-1.5.7.tar.gz',
             'eb33e51f49a15e023950cd7825ca74a4a2b43db8354825ac24fc1b7ee09e6fa3', 'zstd-1.5.7', 'programs/zstd'),
    'spirv-cross': ('https://codeload.github.com/KhronosGroup/SPIRV-Cross/tar.gz/f11ba9f0b21ba8fc15153d50a2a1ae31ab1cf8f7',
                    '92b0458889ed77eac9892b3be5a41e3cf716849fd90f39632e159e555abf3d03',
                    'SPIRV-Cross-f11ba9f0b21ba8fc15153d50a2a1ae31ab1cf8f7', 'spirv-cross'),
}

def install_mac_tool(folder, root, name, run):
    if platform.system() != 'Darwin' or name not in MAC_DOWNLOADS:
        raise ValueError('This fallback installer is for macOS only')
    url, digest, source_name, binary_name = MAC_DOWNLOADS[name]
    # Source compilation uses Apple's selected toolchain, never a shell bootstrap.
    if name != 'xcodegen':
        compiler = probe(['/usr/bin/xcrun', '--find', 'clang++' if name == 'spirv-cross' else 'clang'])
        if not compiler or not Path('/usr/bin/make').is_file():
            raise RuntimeError('Install and configure Xcode before building ' + name)
    work = folder / ('mac-' + name); work.mkdir(exist_ok=True)
    archive = work / ('source.zip' if name == 'xcodegen' else 'source.tar.gz')
    emit(folder, 'stage', name='Downloading ' + name)
    download(url, archive, folder, digest, algorithm='sha256', label=name)
    unpack(archive, work)
    source = work / source_name
    if name != 'xcodegen':
        emit(folder, 'stage', name='Building ' + name + ' with Xcode')
        command = ['/usr/bin/make', '-C', str(source / 'programs' if name == 'zstd' else source), '-j2']
        command += ['zstd', 'CC=' + compiler] if name == 'zstd' else ['spirv-cross', 'CXX=' + compiler]
        run(folder, command)
    binary = source / binary_name
    if not binary.is_file(): raise RuntimeError('Missing installed binary: ' + name)
    if name == 'xcodegen':
        shutil.copytree(source / 'share', root / 'share', dirs_exist_ok=True)
    licenses = root / 'licenses' / name; licenses.mkdir(parents=True, exist_ok=True)
    for pattern in ('LICENSE*', 'COPYING*'):
        for license in source.glob(pattern):
            if license.is_file(): shutil.copy2(license, licenses / license.name)
    destination = root / 'bin' / name; destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + name + '-' + folder.name)
    try:
        shutil.copy2(binary, temporary); temporary.chmod(0o755)
        run(folder, [temporary, '--revision' if name == 'spirv-cross' else '--version'])
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    archive.unlink(missing_ok=True)

def extractor_current(root):
    marker = Path(root) / 'nx_extract' / 'build.json'
    if not marker.is_file():
        return False
    try:
        value = json.loads(marker.read_text(encoding='utf-8'))
        stage_root = Path(os.environ.get('NX_STAGE_ROOT') or (Path(root) / 'stage'))
        return value.get('stage_key') == staging.compute_key(staging.REPO, stage_root)
    except (OSError, ValueError):
        return False


def install(folder, task, config, run):
    from .capabilities import REPO, environment
    root = Path(config['tools']); root.mkdir(parents=True, exist_ok=True)
    names = task['dependencies']
    if not isinstance(names, list) or any(install_method(n, config) == 'manual' for n in names):
        raise ValueError('Unsupported automatic dependency')
    names = list(dict.fromkeys(names))
    if 'extractor' in names and 'dotnet' not in names:
        names.insert(0, 'dotnet')
    if 'dotnet' in names:
        names.remove('dotnet'); names.insert(0, 'dotnet')
    index = config.get('python_index', DEFAULT_INDEX)
    if index not in PYTHON_INDEXES:
        raise ValueError('Unsupported Python package source')
    failed = []
    for name in names:
        if name == 'extractor' and 'dotnet' in failed:
            print('【红】extractor: Skipped because .NET SDK installation failed. Retry the installation task after fixing .NET.', flush=True)
            failed.append(name)
            continue
        available = next(c for c in environment(config)['checks'] if c['name'] == name)['available']
        if available and (name != 'extractor' or extractor_current(root)):
            print('Already installed: ' + name, flush=True)
            continue
        emit(folder, 'stage', name='Installing ' + name)
        try:
            if name in PYTHON_PACKAGES:
                package_dir = root / 'python-packages'
                env = dict(os.environ, PIP_CONFIG_FILE=os.devnull, PIP_EXTRA_INDEX_URL='', PIP_CACHE_DIR=str(root / 'pip-cache'))
                run(folder, [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--index-url', index,
                             '--target', package_dir, '--upgrade', PYTHON_PACKAGES[name]], env)
                if str(package_dir) not in sys.path: sys.path.insert(0, str(package_dir))
                importlib.invalidate_caches()
            elif name == 'dotnet':
                install_dotnet(folder, root, run)
            elif name in ('clang', 'lld', 'spirv_cross') and platform.system() == 'Windows':
                from .windows_tools import install_llvm, install_spirv_cross
                if name == 'spirv_cross': install_spirv_cross(folder, root, run)
                else: install_llvm(folder, root, run)
            elif name == 'mac_metal':
                run(folder, ['/usr/bin/xcodebuild', '-downloadComponent', 'metalToolchain'])
            elif name == 'sdk':
                from .apple_tools import install_sdk
                install_sdk(folder, config)
            elif name == 'extractor':
                dotnet = find_dotnet(config)
                if not dotnet: raise RuntimeError('A working .NET 10 SDK is required')
                stage = staging.ensure(REPO, Path(os.environ.get('NX_STAGE_ROOT') or (root / 'stage')))
                run(folder, [dotnet, 'build', str(stage / 'dm/tools/nx_extract'), '-c', 'Release', '-o', root / 'nx_extract',
                             '-p:BaseIntermediateOutputPath=' + str(root / 'obj') + os.sep], dotnet_environment(config, os.environ))
                (root / 'nx_extract').mkdir(parents=True, exist_ok=True)
                (root / 'nx_extract' / 'build.json').write_text(json.dumps({'stage_key': stage.parent.name}), encoding='utf-8')
            else:
                brew = brew_path(config)
                if brew:
                    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE='1', HOMEBREW_NO_INSTALL_CLEANUP='1', HOMEBREW_CACHE=str(root / 'brew-cache'))
                    try:
                        run(folder, [brew, 'install', name], env)
                    except RuntimeError:
                        print('Homebrew failed; trying the official local installer.', flush=True)
                        install_mac_tool(folder, root, name, run)
                else:
                    install_mac_tool(folder, root, name, run)
            if not next(c for c in environment(config)['checks'] if c['name'] == name)['available']:
                raise RuntimeError('Dependency is still unavailable after installation: ' + name)
            print('Installed: ' + name, flush=True)
        except Exception as error:
            print('【红】' + name + ': ' + str(error), flush=True)
            failed.append(name)
    if failed:
        raise RuntimeError('Dependency installation failed: ' + ', '.join(failed) + '. See build.log; retry after fixing the reported cause.')
    emit(folder, 'stage', name='Dependency installation complete')
