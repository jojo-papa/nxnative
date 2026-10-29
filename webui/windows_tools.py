"""Verified portable Windows compiler and SPIRV-Cross installers."""
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import time

from .apple_tools import remove_stage
from .jobs import emit

LLVM_VERSION = '20261020'
LLVM_ASSETS = {
    'x86_64': 'fd5462b7f5d93b2ff981fcd3f9c7e427e47f3203c64ea91c27bcc444eebd74cd',
    'aarch64': '8f24fedd0b75c674c6c83dec2d76a7ac31a690120212843a17e465ef49854f69',
}
TOOLCHAIN = Path('ios-cross/toolchain/windows/iphone')


def check_apple_compiler(folder, compiler, run):
    source = folder / 'compiler-probe.c'
    obj, library = folder / 'compiler-probe.o', folder / 'compiler-probe.dylib'
    source.write_text('#include <stdint.h>\nuint64_t probe(void) { return 1; }\n', encoding='utf-8')
    run(folder, [compiler / 'bin/clang.exe', '-target', 'arm64-apple-ios26.0', '-ffreestanding',
                 '-mcpu=apple-a16', '-c', source, '-o', obj])
    if obj.read_bytes()[:8] != struct.pack('<II', 0xfeedfacf, 0x100000c):
        raise RuntimeError('Compiler did not generate an ARM64 Mach-O object')
    run(folder, [compiler / 'bin/lld.exe', '-flavor', 'darwin', '-arch', 'arm64', '-platform_version',
                 'ios', '26.0', '26.5', '-dylib', '-no_adhoc_codesign', '-o', library, obj])
    if library.read_bytes()[:8] != struct.pack('<II', 0xfeedfacf, 0x100000c):
        raise RuntimeError('Darwin linker did not generate an ARM64 Mach-O library')


def replace_with_retry(source, destination, attempts=40, delay=0.25):
    """Move a freshly built executable into place, retrying Windows sharing violations.

    Defender and other scanners briefly hold a just-executed executable open, so
    os.replace can fail with WinError 32 even though the build process exited.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, destination)
            return
        except PermissionError as error:
            if attempt + 1 == attempts:
                raise RuntimeError(
                    'Could not move the built SPIRV-Cross executable into place because '
                    'another program is using it. Close other nxnative builds or scanners '
                    'watching the tools folder, then retry the installation.') from error
            time.sleep(delay)


def install_llvm(folder, root, run, for_spirv=False):
    from .dependencies import download, unpack
    if platform.system() != 'Windows':
        raise ValueError('This portable toolchain is for Windows')
    host = {'amd64': 'x86_64', 'x86_64': 'x86_64', 'arm64': 'aarch64', 'aarch64': 'aarch64'}[platform.machine().lower()]
    destination = root / TOOLCHAIN
    # Keep a manually prepared Apple compiler when only a native C++ builder is needed.
    if for_spirv and destination.exists() and not (destination / 'nxnative-toolchain.json').is_file():
        destination = root / 'windows-build/llvm-mingw'
    marker = destination / 'nxnative-toolchain.json'
    if marker.is_file():
        try:
            metadata = json.loads(marker.read_text(encoding='utf-8'))
            if metadata == dict(version=LLVM_VERSION, host=host) and all((destination / 'bin' / name).is_file() for name in ('clang.exe', 'clang++.exe', 'lld.exe')):
                check_apple_compiler(folder, destination, run)
                print('Reusing portable LLVM compiler: ' + str(destination), flush=True)
                return destination
        except (OSError, ValueError):
            pass
    archive = folder / 'llvm-mingw.zip'
    name = 'llvm-mingw-' + LLVM_VERSION + '-ucrt-' + host
    url = 'https://github.com/mstorsjo/llvm-mingw/releases/download/' + LLVM_VERSION + '/' + name + '.zip'
    emit(folder, 'stage', name='Downloading portable LLVM (clang and lld)')
    download(url, archive, folder, LLVM_ASSETS[host], algorithm='sha256', label='LLVM')
    stage = root / ('.llvm-install-' + folder.name)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        unpack(archive, stage)
        prepared = stage / name
        binary = prepared / 'bin'
        # Use the real compiler, without a wrapper that defaults to Windows targets.
        engines = [path for path in binary.glob('clang-*.exe') if path.stem[6:].isdigit()]
        if len(engines) != 1:
            raise RuntimeError('Unexpected portable compiler layout')
        shutil.copy2(engines[0], binary / 'clang.exe')
        shutil.copy2(binary / 'ld.lld.exe', binary / 'lld.exe')
        emit(folder, 'stage', name='Verifying Apple ARM64 compiler and Darwin linker')
        check_apple_compiler(folder, prepared, run)
        (prepared / 'nxnative-toolchain.json').write_text(json.dumps(dict(version=LLVM_VERSION, host=host)) + '\n', encoding='utf-8')
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.rename(destination.with_name(destination.name + '.previous-' + folder.name))
        prepared.rename(destination)
    finally:
        remove_stage(stage, root)
    archive.unlink(missing_ok=True)
    return destination


def install_spirv_cross(folder, root, run):
    from .dependencies import download, unpack, MAC_DOWNLOADS
    compiler = install_llvm(folder, root, run, for_spirv=True)
    url, digest, source_name, _ = MAC_DOWNLOADS['spirv-cross']
    archive = folder / 'spirv-cross.tar.gz'
    stage = root / ('.spirv-install-' + folder.name)
    stage.mkdir(parents=True, exist_ok=False)
    try:
        emit(folder, 'stage', name='Downloading pinned SPIRV-Cross sources')
        download(url, archive, folder, digest, algorithm='sha256', label='SPIRV-Cross')
        unpack(archive, stage, source_root=source_name)
        source = stage / source_name
        revision = source_name.removeprefix('SPIRV-Cross-')
        (source / 'gitversion.h').write_text('#define SPIRV_CROSS_GIT_REVISION "' + revision + '"\n', encoding='utf-8')
        output = stage / 'spirv-cross.exe'
        emit(folder, 'stage', name='Building SPIRV-Cross with portable LLVM')
        run(folder, [compiler / 'bin/clang++.exe', '-std=c++11', '-O2', '-DNDEBUG',
                     '-DSPIRV_CROSS_SPV_HEADER_NAMESPACE_OVERRIDE=spv_private', '-DHAVE_SPIRV_CROSS_GIT_VERSION',
                     '-static', source / 'main.cpp', *sorted(source.glob('spirv_*.cpp')), '-o', output])
        # Static C++ linkage avoids requiring the toolchain DLLs on PATH.
        run(folder, [output, '--revision'], dict(os.environ, PATH=os.environ.get('SystemRoot', 'C:/Windows') + '/System32'))
        if not output.is_file():
            raise RuntimeError('SPIRV-Cross build produced no executable')
        destination = root / 'spirv-cross-build'
        destination.mkdir(parents=True, exist_ok=True)
        replace_with_retry(output, destination / 'spirv-cross.exe')
        licenses = root / 'licenses/spirv-cross'
        licenses.mkdir(parents=True, exist_ok=True)
        for license in source.glob('LICENSE*'):
            if license.is_file():
                shutil.copy2(license, licenses / license.name)
        (destination / 'source.json').write_text(json.dumps(dict(url=url, sha256=digest, revision=revision)) + '\n', encoding='utf-8')
    finally:
        remove_stage(stage, root)
    archive.unlink(missing_ok=True)
