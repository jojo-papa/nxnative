"""Bounded discovery and local import of user-supplied Apple tools."""
import json
import posixpath
import stat
import zipfile

from .file_tools import filesystem_path, remove_stage
from .repo import REPO
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil

SDK_MINIMUM = (26, 5)
SKIP = {'.git', '.webui-data', 'node_modules', 'venv', 'runtime', '__pycache__'}


def sdk_version_key(version):
    return tuple(int(n) for n in re.findall(r'\d+', version))


def sdk_info(path):
    path = Path(path)
    if path.suffix.lower() != '.sdk' or not path.is_dir():
        return None
    try:
        metadata = path / 'SDKSettings.json'
        if metadata.is_file():
            data = json.loads(metadata.read_text(encoding='utf-8'))
        else:
            with (path / 'SDKSettings.plist').open('rb') as stream:
                data = plistlib.load(stream)
        if not isinstance(data, dict):
            return None
        canonical = str(data.get('CanonicalName', '')).lower()
        if not canonical.startswith('iphoneos'):
            return None
        version = str(data.get('Version', ''))
        if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
            return None
        numbers = tuple(int(n) for n in re.findall(r'\d+', version))
        if (numbers + (0, 0))[:2] < SDK_MINIMUM:
            return None
        required = ('usr/include', 'usr/lib/libSystem.tbd',
                    'System/Library/Frameworks/Foundation.framework/Headers/Foundation.h')
        if not all((path / name).exists() for name in required):
            return None
        return dict(path=str(path.resolve()), version=version)
    except (OSError, ValueError, TypeError, plistlib.InvalidFileException):
        return None


def downloads_directory():
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
                value, _ = winreg.QueryValueEx(key, '{374DE290-123F-4565-9164-39C4925E467B}')
            return Path(os.path.expandvars(value)).expanduser()
        except OSError:
            pass
    return Path.home() / 'Downloads'


def search_locations(config):
    root = Path(config['tools'])
    candidates = [root / 'ios-cross', downloads_directory(), root, REPO]
    if config.get('sdk_search'):
        candidates.insert(0, Path(config['sdk_search']).expanduser())
    result = []
    for candidate in candidates:
        try:
            candidate = candidate.resolve()
            # Never turn a configured drive/home root into a recursive search.
            if candidate == Path(candidate.anchor) or candidate == Path.home().resolve():
                continue
            if candidate not in result:
                result.append(candidate)
        except OSError:
            continue
    return result


def bounded_entries(root, depth=3, budget=1500):
    pending, count = [(Path(root), 0)], 0
    while pending and count < budget:
        directory, level = pending.pop(0)
        yield directory
        if directory.suffix.lower() == '.sdk':
            continue
        try:
            with os.scandir(directory) as stream:
                for entry in stream:
                    count += 1
                    if count > budget:
                        break
                    if entry.is_symlink() or entry.name in SKIP or entry.name.startswith('.'):
                        continue
                    path = Path(entry.path)
                    if entry.is_dir(follow_symlinks=False):
                        if level < depth:
                            pending.append((path, level + 1))
                    elif entry.is_file(follow_symlinks=False):
                        yield path
        except OSError:
            continue


def scan_apple_tools(config):
    locations = search_locations(config)
    sdks, archives, seen = [], [], set()
    for root in locations:
        for path in bounded_entries(root):
            if path in seen:
                continue
            seen.add(path)
            info = sdk_info(path)
            if info:
                sdks.append(info)
            elif 'iphoneos' in path.name.lower() and path.is_file() and path.name.lower().endswith(('.zip', '.tar', '.tar.gz', '.tar.xz', '.tgz')):
                archives.append(str(path.resolve()))
    sdks.sort(key=lambda item: (item['version'] == '26.5', sdk_version_key(item['version'])), reverse=True)
    metal = ''
    candidates = [Path(config['tools']) / 'metal/metal.exe']
    on_path = shutil.which('metal.exe')
    if on_path:
        candidates.append(Path(on_path))
    for variable in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)'):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / 'Metal Developer Tools/bin/metal.exe')
    for candidate in candidates:
        if candidate.is_file() and candidate.with_name('metallib.exe').is_file():
            metal = str(candidate.resolve())
            break
    releases = sorted(SDK_RELEASES.values(), key=lambda item: sdk_version_key(item['version']), reverse=True)
    return dict(sdks=sdks, archives=sorted(set(archives)), metal=metal,
                releases=[{key: item[key] for key in ('version', 'release', 'url', 'sha256')} for item in releases],
                default_version=DEFAULT_SDK_VERSION, searched=[str(path) for path in locations], minimum='26.5')


def effective_config(config, discovery=None):
    result = dict(config)
    if platform.system() != 'Windows':
        return result
    discovery = discovery if discovery is not None else scan_apple_tools(config)
    version = config.get('sdk_version') or ''
    if version:
        selected = sdk_info(Path(config['tools']) / 'ios-cross' / f'iPhoneOS{version}.sdk')
        if selected:
            result['sdk'] = selected['path']
        else:
            result.pop('sdk', None)
    else:
        selected = sdk_info(config.get('sdk') or Path(config['tools']) / 'ios-cross/iPhoneOS26.5.sdk')
        if selected:
            result['sdk'] = selected['path']
        elif discovery['sdks']:
            result['sdk'] = discovery['sdks'][0]['path']
    configured_metal = Path(config.get('metal') or Path(config['tools']) / 'metal/metal.exe')
    if configured_metal.is_file():
        result['metal'] = str(configured_metal.resolve())
    elif discovery['metal']:
        result['metal'] = discovery['metal']
    return result


def sdk_archive(config, discovery=None):
    explicit = config.get('sdk_archive')
    if explicit:
        path = Path(explicit)
        return path if path.is_file() and path.name.lower().endswith(('.zip', '.tar', '.tar.gz', '.tar.xz', '.tgz')) else None
    found = discovery if discovery is not None else scan_apple_tools(config)
    # Multiple archives require the user's choice rather than guessing a version.
    return Path(found['archives'][0]) if len(found['archives']) == 1 else None




SDK_RELEASES = {
    '26.5': {
        'repository': 'https://github.com/xybp888/iOS-SDKs',
        'release': 'iOS26.5-SDKs',
        'version': '26.5',
        'url': 'https://github.com/xybp888/iOS-SDKs/releases/download/iOS26.5-SDKs/iPhoneOS26.5.sdk.zip',
        'sha256': 'bed0f155d84e98ad8273b3bd57a0816ae5e772e1aa8539e6d79476221ce33173',
    },
    '27.0': {
        'repository': 'https://github.com/xybp888/iOS-SDKs',
        'release': 'iOS27.0-SDKs',
        'version': '27.0',
        'url': 'https://github.com/xybp888/iOS-SDKs/releases/download/iOS27.0-SDKs/iPhoneOS27.0.sdk.zip',
        'sha256': '97d107a51562b2236c064a0dea98777faddcf65a1259d4f7abccd46695ef3c15',
    },
}
DEFAULT_SDK_VERSION = '26.5'
SDK_REPOSITORY = SDK_RELEASES[DEFAULT_SDK_VERSION]
SDK_SOURCES = ('xybp888', 'local')


def sdk_release(version=None):
    version = version or DEFAULT_SDK_VERSION
    try:
        return SDK_RELEASES[version]
    except KeyError:
        raise ValueError('Unsupported iPhoneOS SDK version') from None


def sdk_install_method(config, discovery=None):
    selected = config.get('sdk_source', 'xybp888')
    if selected not in SDK_SOURCES:
        return 'manual'
    if config.get('sdk_archive') and sdk_archive(config, discovery):
        return 'import'
    if selected == 'xybp888':
        return 'repository'
    return 'import' if sdk_archive(config, discovery) else 'manual'




def unpack_sdk(archive, destination):
    from .dependencies import unpack
    if archive.suffix.lower() != '.zip':
        unpack(archive, destination)
        return
    root = filesystem_path(destination)
    with zipfile.ZipFile(archive) as source:
        files, links = [], {}
        for item in source.infolist():
            name = item.filename.rstrip('/')
            parts = name.split('/')
            if not name or parts[0] == '__MACOSX':
                continue
            if name.startswith('/') or any(part in ('', '.', '..') for part in parts) or ':' in name or '\\' in name:
                raise ValueError('Unsafe SDK archive member')
            path = root.joinpath(*parts)
            if not path.resolve().is_relative_to(root):
                raise ValueError('Unsafe SDK archive member')
            if stat.S_ISLNK(item.external_attr >> 16):
                if item.file_size > 4096:
                    raise ValueError('Invalid SDK archive link')
                target = source.read(item).decode('utf-8')
                if not target or target.startswith('/') or ':' in target or '\\' in target or '\0' in target:
                    raise ValueError('Unsafe SDK archive link')
                normalized = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                sdk_roots = [i for i, part in enumerate(parts) if part.lower().endswith('.sdk')]
                sdk_root = '/'.join(parts[:sdk_roots[0]+1]) + '/' if sdk_roots else ''
                if not sdk_root or not normalized.startswith(sdk_root):
                    raise ValueError('SDK archive link leaves its SDK')
                links[name] = normalized
            else:
                files.append((item, path))
        for item, path in files:
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with source.open(item) as incoming, path.open('wb') as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
        # Resolve links only within the extracted SDK. Copies work without
        # Windows Developer Mode, administrator access or symlink privileges.
        pending = dict(links)
        while pending:
            progress = False
            for name, target in list(pending.items()):
                original, output = root.joinpath(*target.split('/')), root.joinpath(*name.split('/'))
                if not original.exists():
                    continue
                if original.is_dir() and any(other.startswith(target + '/') for other in pending):
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                if original.is_dir():
                    shutil.copytree(original, output, dirs_exist_ok=True)
                else:
                    shutil.copy2(original, output)
                del pending[name]
                progress = True
            if not progress:
                raise ValueError('SDK archive contains unresolved or cyclic links')
        if links:
            print('Materialized SDK archive links: ' + str(len(links)), flush=True)


def install_sdk(folder, config):
    from .dependencies import download
    from .jobs import emit
    release = sdk_release(config.get('sdk_version'))
    method = sdk_install_method(config)
    downloaded = method == 'repository'
    if downloaded:
        archive = folder / ('iPhoneOS' + release['version'] + '.sdk.zip')
        emit(folder, 'stage', name='Downloading iPhoneOS ' + release['version'] + ' SDK from xybp888/iOS-SDKs')
        print('Third-party SDK source: ' + release['url'], flush=True)
        download(release['url'], archive, folder, release['sha256'], algorithm='sha256', label='iPhoneOS SDK')
    else:
        archive = sdk_archive(config)
    if not archive:
        raise ValueError('Download an iPhoneOS SDK archive first, or choose one of the discovered archives.')
    root = Path(config['tools']).resolve()
    stage = root / ('.sdk-install-' + folder.name)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        emit(folder, 'stage', name='Extracting and adapting iPhoneOS SDK for Windows')
        print('SDK archive: ' + str(archive), flush=True)
        unpack_sdk(archive, stage)
        candidates = [info for path in bounded_entries(stage, depth=5, budget=5000) if (info := sdk_info(path))]
        if len(candidates) != 1:
            raise ValueError('Archive must contain exactly one complete iPhoneOS SDK version 26.5 or newer; simulator and macOS SDKs are not accepted.')
        if downloaded and candidates[0]['version'] != release['version']:
            raise ValueError('Downloaded SDK version does not match the selected release')
        source = Path(candidates[0]['path'])
        if downloaded:
            (source / 'nxnative-sdk-source.json').write_text(json.dumps(release, indent=2) + '\n', encoding='utf-8')
        destination = root / 'ios-cross' / ('iPhoneOS' + candidates[0]['version'] + '.sdk')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ValueError('SDK destination already exists. Repair or choose the existing SDK in Settings.')
        source.rename(destination)
        print('SDK configured automatically: ' + str(destination), flush=True)
        if downloaded:
            archive.unlink(missing_ok=True)
    finally:
        remove_stage(stage, root)
