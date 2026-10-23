"""Assemble a relocatable native macOS app from the NSP build outputs."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('patched', 'romfs', 'shaders', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--graphics', choices=('nvn', 'vulkan'), required=True)
    parser.add_argument('--game', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--version', default='1.0')
    parser.add_argument('--aoc', type=Path)
    parser.add_argument('--launch-defaults', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo / 'dm/games'))
    import game
    profile = game.load(args.game)
    chain = re.search(r'#define DMSH_CHAIN "([a-f0-9]+)"', profile.table('dmsh_chain.h').read_text())[1]
    graphics = args.graphics
    shaders = args.shaders / ('vk' if graphics == 'vulkan' else 'b-' + chain)
    if not shaders.is_dir() or not list(shaders.glob('*.metallib')):
        raise ValueError('No matching macOS shader libraries')
    for module in profile.words('modules'):
        if not (args.patched / (module + '.patched.bin')).is_file():
            raise ValueError('Missing rewritten module: ' + module)
    # Keep all large packaging work on the input/output volume.
    staging = args.out.parent / (args.game + '-mac-stage')
    if staging.exists():
        if staging.resolve().parent != args.out.parent.resolve(): raise ValueError('Invalid staging directory')
        shutil.rmtree(staging)
    app = staging / (args.game + '.app')
    resources = app / 'Contents/Resources'
    (app / 'Contents/MacOS').mkdir(parents=True)
    resources.mkdir()
    def copy_tree(source, destination):
        result = subprocess.run(['cp', '-cR', str(source), str(destination)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode: shutil.copytree(source, destination, dirs_exist_ok=True)
    for src, name in ((args.patched, 'patched'), (args.romfs, 'romfs'), (profile.dir, 'profile')):
        copy_tree(src, resources / name)
    (resources / 'shaders').mkdir()
    copy_tree(shaders, resources / 'shaders' / shaders.name)
    if args.aoc: copy_tree(args.aoc, resources / 'aoc')
    if args.launch_defaults: shutil.copyfile(args.launch_defaults, resources / 'launch-defaults.json')
    font = resources / 'font'; font.mkdir()
    shutil.copyfile(os.environ.get('STD_FONT', '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'), font / 'standard.ttf')
    subprocess.run([sys.executable, str(repo / 'dm/tools/make_ext_font.py'), str(font / 'nintendo_ext.ttf')], check=True)
    plist = dict(CFBundleExecutable='Launch', CFBundleIdentifier='org.nxnative.' + args.game.lower(),
                 CFBundleName=args.name, CFBundleDisplayName=args.name, CFBundlePackageType='APPL',
                 CFBundleVersion=args.version, CFBundleShortVersionString=args.version,
                 NSHighResolutionCapable=True, LSMinimumSystemVersion='26.0',
                 NSSupportsAutomaticGraphicsSwitching=True)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
    subprocess.run([sys.executable, str(Path(__file__).with_name('build_app.py')), '--game', args.game, '--app', str(app)], check=True)
    subprocess.run(['codesign', '--force', '--sign', '-', str(app)], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    temporary = args.out.with_name(args.out.name + '.partial')
    subprocess.run(['ditto', '-c', '-k', '--keepParent', str(app), str(temporary)], check=True)
    import zipfile
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip() is not None: raise ValueError('Archive verification failed')
    os.replace(temporary, args.out)
    print('Mac application: ' + str(args.out))


if __name__ == '__main__':
    main()
