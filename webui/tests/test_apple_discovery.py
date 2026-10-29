import io
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from fastapi.testclient import TestClient
from webui import apple_tools as apple, dependencies as deps, windows_tools as windows
from webui.capabilities import environment
from webui.server import create_app


def make_sdk(path, version='26.5', canonical='iphoneos26.5'):
    path.mkdir(parents=True, exist_ok=True)
    (path/'SDKSettings.json').write_text(json.dumps(dict(Version=version, CanonicalName=canonical)))
    (path/'usr/include').mkdir(parents=True)
    (path/'usr/include/stdint.h').write_text('SDK fixture')
    for name in ('usr/lib/libSystem.tbd', 'System/Library/Frameworks/Foundation.framework/Headers/Foundation.h'):
        file=path/name; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('SDK fixture')
    return path


class AppleSDKDiscovery(unittest.TestCase):
    def test_complete_device_sdk_only_and_stable_preference(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); downloads=root/'Downloads'; downloads.mkdir()
            preferred=make_sdk(downloads/'iPhoneOS26.5.sdk')
            make_sdk(downloads/'nested/iPhoneOS26.6.sdk', '26.6', 'iphoneos26.6')
            make_sdk(downloads/'iPhoneSimulator26.5.sdk', canonical='iphonesimulator26.5')
            make_sdk(downloads/'MacOSX26.5.sdk', canonical='macosx26.5')
            make_sdk(downloads/'iPhoneOS18.0.sdk', '18.0', 'iphoneos18.0')
            incomplete=make_sdk(downloads/'iPhoneOS27.0.sdk', '27.0', 'iphoneos27.0')
            (incomplete/'usr/lib/libSystem.tbd').unlink()
            (downloads/'iPhoneOS26.5.zip.crdownload').write_bytes(b'incomplete browser download')
            with patch.object(apple, 'search_locations', return_value=[downloads]), patch.object(apple.platform, 'system', return_value='Windows'):
                found=apple.scan_apple_tools({'tools':str(root/'tools')})
                self.assertEqual([x['version'] for x in found['sdks']], ['26.5','26.6'])
                self.assertEqual(found['archives'], [])
                self.assertEqual(apple.effective_config({'tools':str(root/'tools')},found)['sdk'],str(preferred.resolve()))
                selected=found['sdks'][1]['path']
                self.assertEqual(apple.effective_config({'tools':str(root/'tools'),'sdk':selected},found)['sdk'], selected)

    def test_search_is_bounded_and_skips_project_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            make_sdk(root/'venv/iPhoneOS26.5.sdk')
            make_sdk(root/'a/b/c/d/iPhoneOS26.5.sdk')
            make_sdk(root/'first/iPhoneOS26.5.sdk')
            entries=list(apple.bounded_entries(root, depth=3))
            self.assertIn(root/'first/iPhoneOS26.5.sdk', entries)
            self.assertNotIn(root/'venv/iPhoneOS26.5.sdk', entries)
            self.assertNotIn(root/'a/b/c/d/iPhoneOS26.5.sdk', entries)

    def test_archive_import_preserves_original_and_sets_worker_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=make_sdk(root/'source/iPhoneOS26.6.sdk', '26.6', 'iphoneos26.6')
            archive=root/'Downloads/iPhoneOS26.6.zip'; archive.parent.mkdir()
            with zipfile.ZipFile(archive,'w') as output:
                for file in source.rglob('*'):
                    if file.is_file(): output.write(file, file.relative_to(source.parent))
            before=archive.read_bytes()
            task=root/'task';task.mkdir(); tools=root/'tools'
            config={'tools':str(tools), 'sdk_search':str(archive.parent), 'sdk_source':'local'}
            with patch.object(apple, 'search_locations', return_value=[archive.parent,tools/'ios-cross']), patch.object(apple.platform,'system',return_value='Windows'):
                self.assertEqual(deps.install_method('sdk',config,'Windows'),'import')
                apple.install_sdk(task,config)
                expected=tools/'ios-cross/iPhoneOS26.6.sdk'
                self.assertIsNotNone(apple.sdk_info(expected))
                self.assertEqual(apple.effective_config(config)['sdk'],str(expected.resolve()))
            self.assertEqual(archive.read_bytes(), before)
            self.assertFalse((tools/'.sdk-install-task').exists())

    def test_ambiguous_archives_require_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=root/'iPhoneOS26.5.zip';second=root/'iPhoneOS26.6.zip'
            first.touch();second.touch()
            found={'archives':[str(first),str(second)]}
            self.assertIsNone(apple.sdk_archive({'tools':directory},found))
            self.assertEqual(apple.sdk_archive({'tools':directory,'sdk_archive':str(second)},found),second)

    def test_invalid_archive_cannot_escape_or_become_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'iPhoneOS26.5.zip';task=root/'task';task.mkdir()
            with zipfile.ZipFile(archive,'w') as output: output.writestr('../escaped.txt','bad')
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                apple.install_sdk(task,{'tools':str(root/'tools'),'sdk_archive':str(archive)})
            self.assertTrue(archive.exists())
            self.assertFalse((root/'escaped.txt').exists())
            self.assertFalse((root/'tools/.sdk-install-task').exists())

    def test_metal_standard_install_is_used_in_worker_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);binary=root/'Program Files/Metal Developer Tools/bin/metal.exe'
            binary.parent.mkdir(parents=True);binary.touch();binary.with_name('metallib.exe').touch()
            config={'tools':str(root/'tools')}
            with patch.dict('os.environ',ProgramFiles=str(root/'Program Files')),patch.object(apple,'search_locations',return_value=[]),patch.object(apple.shutil,'which',return_value=None),patch.object(apple.platform,'system',return_value='Windows'):
                self.assertEqual(apple.effective_config(config)['metal'],str(binary.resolve()))

    def test_sdk_version_metadata_cannot_escape_target(self):
        with tempfile.TemporaryDirectory() as directory:
            sdk=make_sdk(Path(directory)/'iPhoneOS26.5.sdk',version='26.5/../../outside')
            self.assertIsNone(apple.sdk_info(sdk))

    def test_discovered_sdk_reaches_api_and_native_build_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sdk=make_sdk(root/'Downloads/iPhoneOS26.5.sdk')
            config={'tools':str(root/'tools')}
            with patch.object(apple,'search_locations',return_value=[root/'Downloads']),patch.object(apple.platform,'system',return_value='Windows'):
                app=create_app(root/'data','token',config)
                try:
                    with TestClient(app) as client:
                        response=client.get('/api/environment',headers={'X-Session-Token':'token'})
                        self.assertEqual(response.status_code,200)
                        data=response.json()
                        self.assertEqual(data['config']['sdk'],str(sdk.resolve()))
                        self.assertTrue(next(c for c in data['checks'] if c['name']=='sdk')['available'])
                        self.assertEqual(apple.effective_config(config)['sdk'],data['config']['sdk'])
                finally:app.state.jobs.close()


class PortableWindowsTools(unittest.TestCase):
    def test_install_methods_are_platform_specific(self):
        with patch.object(deps.platform,'machine',return_value='AMD64'):
            for name in ('clang','lld','spirv_cross'):
                self.assertEqual(deps.install_method(name,{},'Windows'),'portable')
                self.assertEqual(deps.install_method(name,{},'Darwin'),'manual')
            self.assertEqual(deps.install_method('metal',{},'Windows'),'manual')

    def test_probe_failure_never_replaces_existing_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();tools=root/'tools'
            existing=tools/windows.TOOLCHAIN;existing.mkdir(parents=True);(existing/'keep.txt').write_text('original')
            def unpack(archive, stage):
                binary=stage/('llvm-mingw-'+windows.LLVM_VERSION+'-ucrt-x86_64')/'bin';binary.mkdir(parents=True)
                for name in ('clang-23.exe','ld.lld.exe'):(binary/name).write_bytes(b'fixture')
            with patch.object(windows.platform,'system',return_value='Windows'),patch.object(windows.platform,'machine',return_value='AMD64'),patch.object(deps,'download'),patch.object(deps,'unpack',side_effect=unpack),patch.object(windows,'check_apple_compiler',side_effect=RuntimeError('compiler probe failed')):
                with self.assertRaisesRegex(RuntimeError,'probe failed'):windows.install_llvm(task,tools,Mock())
            self.assertEqual((existing/'keep.txt').read_text(),'original')
            self.assertFalse((tools/'.llvm-install-task').exists())

    def test_successful_pair_install_reuses_the_same_verified_compiler(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();tools=root/'tools'
            def unpack(archive, stage):
                binary=stage/('llvm-mingw-'+windows.LLVM_VERSION+'-ucrt-x86_64')/'bin';binary.mkdir(parents=True)
                for name in ('clang-23.exe','clang++.exe','ld.lld.exe'):(binary/name).write_bytes(b'fixture')
            with patch.object(windows.platform,'system',return_value='Windows'),patch.object(windows.platform,'machine',return_value='AMD64'),patch.object(deps,'download') as download,patch.object(deps,'unpack',side_effect=unpack),patch.object(windows,'check_apple_compiler'):
                first=windows.install_llvm(task,tools,Mock())
                second=windows.install_llvm(task,tools,Mock())
                self.assertEqual(first,second)
                self.assertEqual(download.call_count,1)
                self.assertEqual(download.call_args.kwargs['algorithm'],'sha256')

    def test_spirv_publish_retries_a_transient_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.exe';destination=root/'destination.exe'
            source.write_bytes(b'fixture')
            real_replace=os.replace;calls=[]
            def flaky_replace(a,b):
                calls.append((a,b))
                if len(calls)<3:raise PermissionError(13,'file is in use')
                return real_replace(a,b)
            with patch.object(windows.os,'replace',side_effect=flaky_replace),patch.object(windows.time,'sleep'):
                windows.replace_with_retry(source,destination)
            self.assertEqual(len(calls),3)
            self.assertEqual(destination.read_bytes(),b'fixture')

    def test_spirv_publish_reports_a_persistent_file_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.exe';destination=root/'destination.exe'
            source.write_bytes(b'fixture')
            with patch.object(windows.os,'replace',side_effect=PermissionError(13,'file is in use')),patch.object(windows.time,'sleep'):
                with self.assertRaisesRegex(RuntimeError,'another program is using it'):
                    windows.replace_with_retry(source,destination,attempts=2)
            self.assertTrue(source.is_file())
            self.assertFalse(destination.exists())

    def test_spirv_build_is_static_and_probed_before_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();tools=root/'tools'
            compiler=root/'compiler'; commands=[]
            source_name=deps.MAC_DOWNLOADS['spirv-cross'][2]
            def unpack(archive,stage,**kwargs):
                source=stage/source_name;source.mkdir()
                for name in ('main.cpp','spirv_test.cpp','LICENSE'):(source/name).write_text('fixture')
            def run(folder,command,env=None):
                commands.append([str(x) for x in command])
                self.assertFalse((tools/'spirv-cross-build/spirv-cross.exe').exists())
                if '-o' in command: Path(command[-1]).write_bytes(b'fixture exe')
                if '--revision' in command:self.assertNotIn(str(compiler),env['PATH'])
            with patch.object(windows,'install_llvm',return_value=compiler),patch.object(deps,'download'),patch.object(deps,'unpack',side_effect=unpack):
                windows.install_spirv_cross(task,tools,run)
            self.assertIn('-static',commands[0])
            self.assertTrue((tools/'spirv-cross-build/spirv-cross.exe').is_file())
            self.assertTrue((tools/'licenses/spirv-cross/LICENSE').is_file())
