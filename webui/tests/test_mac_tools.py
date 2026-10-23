import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from webui import platform_tools as tools, dependencies as deps
from webui.capabilities import environment

class MacTools(unittest.TestCase):
    def test_reuse_system_sdk_instead_of_local_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = root/'tools/dotnet/dotnet'; local.parent.mkdir(parents=True); local.touch()
            system = root/'system/dotnet'; system.parent.mkdir(); system.touch()
            def probe(command):
                if Path(command[0]) == local.resolve(): return 'Microsoft.NETCore.App 10.0.1' if command[1] == '--list-runtimes' else ''
                return '10.0.100 [/system/sdk]' if command[1] == '--list-sdks' else 'Microsoft.NETCore.App 10.0.1 [/system/shared]'
            config = {'tools':str(root/'tools')}
            with patch.object(tools.platform, 'system', return_value='Darwin'), patch.object(tools.shutil, 'which', return_value=str(system)), patch.object(tools, 'probe', side_effect=probe):
                self.assertEqual(tools.find_dotnet(config), str(system.resolve()))
                env = tools.dotnet_environment(config, {'CUSTOM':'preserved'})
                self.assertEqual(env['DOTNET_ROOT'], str(system.parent.resolve()))
                self.assertEqual(env['CUSTOM'], 'preserved')
                self.assertTrue(env['PATH'].startswith(str(system.parent.resolve())))

    def test_platform_checks_do_not_mix_windows_and_mac(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'tools':directory}
            with patch('webui.capabilities.platform.system', return_value='Darwin'), patch.object(tools, 'find_dotnet', return_value='/system/dotnet'), patch.object(tools, 'probe', return_value=''), patch.object(deps, 'brew_path', return_value=None):
                checks = {c['name']:c for c in environment(config)['checks']}
                self.assertTrue(checks['dotnet']['available'])
                self.assertIn('macos_sdk', checks)
                self.assertIn('iphoneos_sdk', checks)
                self.assertIn('mac_metal', checks)
                self.assertNotIn('lld', checks)
                self.assertNotIn('sdk', checks)
                self.assertNotIn('metal', checks)
                self.assertTrue(all(checks[n]['auto_install'] for n in deps.BREW_PACKAGES))
            with patch('webui.capabilities.platform.system', return_value='Windows'), patch.object(tools, 'find_dotnet', return_value=''):
                names = {c['name'] for c in environment(config)['checks']}
                self.assertIn('lld', names)
                self.assertNotIn('macos_sdk', names)
                self.assertNotIn('xcodebuild', names)

    def test_xcodegen_installs_resources_and_probes_before_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder=root/'task'; folder.mkdir(); dest=root/'tools'
            def unpack(archive, work):
                source = work/'xcodegen'; (source/'bin').mkdir(parents=True)
                (source/'bin/xcodegen').write_bytes(b'test binary')
                (source/'share/xcodegen').mkdir(parents=True)
                (source/'share/xcodegen/preset.yml').write_text('preset')
                (source/'LICENSE').write_text('license')
            def run(folder, command):
                self.assertFalse((dest/'bin/xcodegen').exists())
                self.assertEqual(command[1], '--version')
            with patch.object(deps.platform, 'system', return_value='Darwin'), patch.object(deps, 'download') as download, patch.object(deps, 'unpack', side_effect=unpack):
                deps.install_mac_tool(folder, dest, 'xcodegen', run)
                self.assertEqual(download.call_args.kwargs['algorithm'], 'sha256')
            self.assertTrue((dest/'bin/xcodegen').exists())
            self.assertTrue((dest/'share/xcodegen/preset.yml').exists())
            self.assertTrue((dest/'licenses/xcodegen/LICENSE').exists())

    def test_source_fallback_needs_xcode_before_download(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(deps.platform, 'system', return_value='Darwin'), patch.object(deps, 'probe', return_value=''), patch.object(deps, 'download') as download:
            with self.assertRaisesRegex(RuntimeError, 'configure Xcode'):
                deps.install_mac_tool(Path(directory), Path(directory)/'tools', 'zstd', Mock())
            download.assert_not_called()

    def test_brew_failure_uses_local_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); available={'value':False}
            def environment(config): return {'checks':[dict(name='zstd',available=available['value'])]}
            def fallback(*args): available['value']=True
            with patch.object(deps.platform, 'system', return_value='Darwin'), patch.object(deps, 'brew_path', return_value='/brew'), patch('webui.capabilities.environment', side_effect=environment), patch.object(deps, 'install_mac_tool', side_effect=fallback) as install:
                deps.install(root, {'dependencies':['zstd']}, {'tools':str(root/'tools')}, Mock(side_effect=RuntimeError('brew failed')))
                install.assert_called_once()

    def test_metal_installer_requires_full_xcode(self):
        with patch.object(deps, 'probe', return_value='Xcode 26.5\nBuild version 17F1'):
            self.assertEqual(deps.install_method('mac_metal', {}, 'Darwin'), 'xcode')
            self.assertEqual(deps.install_method('mac_metal', {}, 'Windows'), 'manual')
        with patch.object(deps, 'probe', return_value=''):
            self.assertEqual(deps.install_method('mac_metal', {}, 'Darwin'), 'manual')

    def test_metal_uses_only_official_component_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ready={'value':False}
            def environment(config):return {'checks':[dict(name='mac_metal',available=ready['value'])]}
            def run(folder,command):
                self.assertEqual(command,['/usr/bin/xcodebuild','-downloadComponent','metalToolchain'])
                ready['value']=True
            with patch.object(deps.platform,'system',return_value='Darwin'),patch.object(deps,'probe',return_value='Xcode 26.5'),patch('webui.capabilities.environment',side_effect=environment):
                deps.install(root,{'dependencies':['mac_metal']},{'tools':str(root/'tools')},run)
