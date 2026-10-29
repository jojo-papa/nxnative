"""Profile and installed-tool capability checks without loading game files."""
import importlib
import importlib.util
from pathlib import Path
import platform
import shutil
import sys

from .repo import REPO
sys.path.insert(0, str(REPO / 'dm/games'))
import game


DEPENDENCY_HELP = {'extractor': ('https://github.com/xbunax/nxnative/blob/main/webui/docs/webui.md', 'Build nx_extract from this repository with webui/tools/prepare_tools.py; it is not a separate vendor download.'), 'dotnet': ('https://dotnet.microsoft.com/en-us/download/dotnet/10.0', 'Get the .NET 10 SDK for your host and place it in the tools/dotnet folder.'), 'clang': ('https://github.com/llvm/llvm-project/releases', 'Get host-compatible LLVM with ARM64 and Mach-O support. Keep bin and lib/clang together under tools/ios-cross/toolchain/windows/iphone.'), 'lld': ('https://github.com/llvm/llvm-project/releases', 'Get lld from the LLVM toolchain. The Windows build uses its Darwin linker mode.'), 'sdk': ('https://developer.apple.com/xcode/resources/', 'Obtain the iPhoneOS SDK from your Xcode installation, then set its directory below. This project does not distribute Apple SDKs.'), 'metal': ('https://developer.apple.com/metal/tools/', 'Get Apple Metal Developer Tools for Windows, then set the metal.exe path below.'), 'spirv_cross': ('https://github.com/KhronosGroup/SPIRV-Cross', 'Build SPIRV-Cross with its documented CMake instructions and place spirv-cross.exe in tools/spirv-cross-build.'), 'spirv-cross': ('https://github.com/KhronosGroup/SPIRV-Cross', 'Install SPIRV-Cross and add it to PATH. Follow the repository shader-tool lock requirements.'), 'xcodegen': ('https://github.com/yonaskolb/XcodeGen', 'Install XcodeGen following its official instructions and add xcodegen to PATH.'), 'zstd': ('https://github.com/facebook/zstd', 'Install Zstandard and add zstd to PATH.'), 'xcodebuild': ('https://developer.apple.com/xcode/resources/', 'Install Xcode and its command-line tools on the Mac; check the selected developer directory.'), 'xcrun': ('https://developer.apple.com/xcode/resources/', 'Install Xcode and its command-line tools on the Mac; check the selected developer directory.'), 'make': ('https://developer.apple.com/xcode/resources/', 'Install Xcode and its command-line tools on the Mac; check the selected developer directory.'), 'codesign': ('https://developer.apple.com/xcode/resources/', 'Install Xcode and its command-line tools on the Mac; check the selected developer directory.'), 'ditto': ('https://developer.apple.com/xcode/resources/', 'Install Xcode and its command-line tools on the Mac; check the selected developer directory.'), 'lz4': ('https://pypi.org/project/lz4/', 'Install lz4 into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.'), 'capstone': ('https://pypi.org/project/capstone/', 'Install capstone into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.'), 'fontTools': ('https://pypi.org/project/fonttools/', 'Install fonttools into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.'), 'PIL': ('https://pypi.org/project/Pillow/', 'Install Pillow into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.')}


DEPENDENCY_HELP.update({name: ('https://developer.apple.com/xcode/resources/', 'Provided by the selected Xcode installation. Finish Xcode setup and select its command-line tools.') for name in ('macos_sdk', 'iphoneos_sdk', 'mac_metal')})
DEPENDENCY_HELP['dotnet'] = ('https://dotnet.microsoft.com/en-us/download/dotnet/10.0', '.NET 10 SDK is a build-time dependency for the C# extractor and shader tools on both Mac and Windows. Existing compatible SDKs are reused; built apps do not require .NET.')

DEPENDENCY_HELP.update({'clang': ('https://github.com/mstorsjo/llvm-mingw/releases/tag/20261020', 'Downloads verified portable LLVM together with lld into the project. Checks real ARM64 Apple compilation before installation. No Visual Studio or administrator access is needed.'), 'lld': ('https://github.com/mstorsjo/llvm-mingw/releases/tag/20261020', 'Installed together with clang. Verifies Darwin linking before installation; an existing complete toolchain is reused.'), 'spirv_cross': ('https://github.com/KhronosGroup/SPIRV-Cross', 'Downloads verified SPIRV-Cross sources and builds with portable LLVM. Installs the C++ compiler automatically if needed; no Visual Studio or CMake is required.'), 'sdk': ('https://developer.apple.com/download/all/?q=Xcode', 'Finds complete iPhoneOS SDKs version 26.5 or newer in Downloads, the project and the configured search folder. Simulator and macOS SDKs are rejected. A discovered SDK archive can be extracted and configured locally. Obtain the SDK from your own Xcode installation.'), 'metal': ('https://developer.apple.com/download/all/?q=metal%20developer%20tools%20for%20windows', 'Sign in on the Apple website to download and install Metal Developer Tools for Windows. Recheck detects standard installations automatically. For a custom installation, select metal.exe below. Apple login stays in your browser.')})

DEPENDENCY_HELP['mac_metal'] = ('https://developer.apple.com/documentation/Xcode/downloading-and-installing-additional-xcode-components', 'With Xcode installed and selected, downloads and installs its Metal Toolchain through the official xcodebuild command. Finish Xcode first-launch setup before installing.')

DEPENDENCY_HELP['sdk'] = ('https://github.com/xybp888/iOS-SDKs/releases', 'Choose an iPhoneOS SDK version (26.5 or newer); missing SDKs download from xybp888/iOS-SDKs (third-party) with SHA-256 verification. Windows links are materialized automatically. Existing valid SDKs are reused; local archives remain supported.')
DEPENDENCY_HELP['nsz'] = ('https://github.com/nicoboss/nsz', 'The MIT-licensed nsz package decompresses .nsz uploads to NSP. Install it here or let the WebUI install it at startup.')

def profiles(system=None):
    system = system or platform.system()
    result = []
    for g in game.all_games():
        graphics = g.get('graphics', 'detect')
        reason = ''
        if system == 'Windows':
            if graphics == 'vulkan':
                reason = 'Windows does not support Vulkan builds.'
            elif any(g.get(k, 'off') == 'on' for k in ('shader_glslc_capture', 'shader_vk_capture')):
                reason = 'This game needs runtime shader capture on a Mac.'
            elif g.words('shader_versions') != [g.get('package')]:
                reason = 'Windows requires one shader version matching the package.'
        elif system != 'Darwin':
            reason = 'Application builds require Windows or Apple Silicon macOS.'
        if not reason and graphics == 'detect': reason = 'Renderer and runtime-capture requirements are checked after extraction.'
        supported = not reason or graphics == 'detect' and reason.startswith('Renderer')
        result.append(dict(id=g.id, name=g.get('name'), version=g.get('package'), builds=g.builds(),
                           graphics=graphics, ios=supported, mac=system == 'Darwin', reason=reason))
    return result


def environment(config):
    from .dependencies import install_method, tool_path
    from .platform_tools import find_dotnet, probe
    importlib.invalidate_caches()
    system = platform.system()
    from .apple_tools import scan_apple_tools, effective_config
    discovery = scan_apple_tools(config) if system == 'Windows' else None
    resolved = effective_config(config, discovery)
    root = Path(config['tools'])
    exe = '.exe' if system == 'Windows' else ''
    expected = {'extractor': root / 'nx_extract' / ('nx_extract' + exe),
                'dotnet': root / 'dotnet' / ('dotnet' + exe)}
    if system == 'Windows':
        version = config.get('sdk_version')
        sdk_default = root / 'ios-cross' / ('iPhoneOS' + version + '.sdk' if version else 'iPhoneOS26.5.sdk')
        expected.update(clang=root / 'ios-cross/toolchain/windows/iphone/bin/clang.exe',
                        lld=root / 'ios-cross/toolchain/windows/iphone/bin/lld.exe',
                        sdk=Path(resolved.get('sdk') or sdk_default),
                        metal=Path(resolved.get('metal') or root / 'metal/metal.exe'),
                        spirv_cross=root / 'spirv-cross-build/spirv-cross.exe')
    checks = [dict(name=k, path=str(v), available=v.is_dir() if k == 'sdk' else v.is_file()) for k, v in expected.items()]
    if system == 'Windows':
        from .apple_tools import sdk_info
        for check in checks:
            if check['name'] == 'sdk': check['available'] = sdk_info(check['path']) is not None
    dotnet = find_dotnet(config)
    for check in checks:
        if check['name'] == 'dotnet':
            check.update(path=dotnet or check['path'], available=bool(dotnet))
    if system == 'Darwin':
        for name in ('xcodebuild', 'xcrun', 'xcodegen', 'make', 'zstd', 'spirv-cross', 'codesign', 'ditto'):
            found = shutil.which(name, path=tool_path(config))
            checks.append(dict(name=name, path=found or '', available=bool(found)))
        for name, command in [('macos_sdk', ['--sdk', 'macosx', '--show-sdk-path']), ('iphoneos_sdk', ['--sdk', 'iphoneos', '--show-sdk-path']), ('mac_metal', ['--find', 'metal'])]:
            found = probe(['/usr/bin/xcrun', *command])
            available = bool(found and Path(found).exists())
            if name == 'mac_metal' and available:
                available = bool(probe(['/usr/bin/xcrun', 'metal', '--version']))
            checks.append(dict(name=name, path=found, available=available))
    packages = str(root / 'python-packages')
    if packages not in sys.path: sys.path.append(packages)
    for name in ('lz4', 'capstone', 'fontTools', 'PIL', 'nsz'):
        checks.append(dict(name=name, path='Python package', available=importlib.util.find_spec(name) is not None))
    for check in checks:
        check['label'] = {'dotnet': '.NET 10 SDK', 'macos_sdk': 'macOS SDK', 'iphoneos_sdk': 'iPhoneOS SDK (iOS packaging)', 'mac_metal': 'Xcode Metal compiler', 'nsz': 'NSZ decompressor'}.get(check['name'], check['name'])
        check['help_url'], check['help_text'] = DEPENDENCY_HELP[check['name']]
        if check['name'] == 'sdk' and config.get('sdk_source') == 'local':
            check['help_text'] = 'Local mode: discovers existing iPhoneOS SDKs and imports local archives. Automatic SDK network downloads are disabled.'
        check['install_method'] = install_method(check['name'], config, system, discovery)
        check['auto_install'] = check['install_method'] != 'manual'
    return dict(system=system, machine=platform.machine(), checks=checks, profiles=profiles(system), apple_tools=discovery)
