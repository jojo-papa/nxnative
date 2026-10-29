import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from fastapi.testclient import TestClient
from webui import apple_tools as apple, dependencies as deps
from webui.capabilities import environment
from webui.server import create_app


def sdk_zip(path, version='26.5', link=None):
    base='iPhoneOS'+version+'.sdk/'
    with zipfile.ZipFile(path,'w') as output:
        output.writestr(base+'SDKSettings.json',json.dumps(dict(Version=version,CanonicalName='iphoneos'+version)))
        for name in ('usr/include/stdint.h','usr/lib/libSystem.tbd','System/Library/Frameworks/Foundation.framework/Headers/Foundation.h'):
            output.writestr(base+name,b'fixture')
        if link:
            name,target=link
            info=zipfile.ZipInfo(base+name);info.create_system=3
            info.external_attr=(stat.S_IFLNK|0o777)<<16
            output.writestr(info,target)


class RepositorySDK(unittest.TestCase):
    def test_default_missing_sdk_is_automatic_but_local_mode_can_stay_offline(self):
        self.assertEqual(deps.install_method('sdk',{'tools':'unused'},'Windows'),'repository')
        self.assertEqual(deps.install_method('sdk',{'tools':'unused','sdk_source':'local'},'Windows',{'archives':[]}),'manual')
        self.assertEqual(deps.install_method('sdk',{'tools':'unused','sdk_source':'unknown'},'Windows'),'manual')

    def test_windows_file_and_directory_link_chains_are_materialized(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'sdk.zip'
            def link(output,name,target):
                info=zipfile.ZipInfo('iPhoneOS26.5.sdk/'+name);info.create_system=3
                info.external_attr=(stat.S_IFLNK|0o777)<<16
                output.writestr(info,target)
            with zipfile.ZipFile(archive,'w') as output:
                output.writestr('iPhoneOS26.5.sdk/real/header.h',b'original header')
                link(output,'real/alias.h','header.h')
                link(output,'alias','real')
                link(output,'last.h','alias/alias.h')
            apple.unpack_sdk(archive,root/'stage')
            for name in ('real/alias.h','alias/alias.h','last.h'):
                file=root/'stage/iPhoneOS26.5.sdk'/name
                self.assertEqual(file.read_bytes(),b'original header')
                self.assertFalse(file.is_symlink())

    def test_link_cannot_leave_sdk_or_reference_absolute_path(self):
        for target in ('../../outside.txt','/outside.txt','C:/outside.txt'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);archive=root/'sdk.zip'
                sdk_zip(archive,link=('escape.h',target))
                with self.assertRaisesRegex(ValueError,'link'):
                    apple.unpack_sdk(archive,root/'stage')
                self.assertFalse((root/'outside.txt').exists())

    def test_cyclic_links_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'sdk.zip'
            sdk_zip(archive,link=('cycle.h','cycle.h'))
            with self.assertRaisesRegex(ValueError,'cyclic'):
                apple.unpack_sdk(archive,root/'stage')

    def test_repository_install_pins_download_and_keeps_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();config={'tools':str(root/'tools')}
            def download(url,destination,folder,digest,**kwargs):
                self.assertEqual(url,apple.SDK_REPOSITORY['url'])
                self.assertEqual(digest,apple.SDK_REPOSITORY['sha256'])
                self.assertEqual(kwargs['algorithm'],'sha256')
                sdk_zip(destination)
            with patch.object(deps,'download',side_effect=download):
                apple.install_sdk(task,config)
            sdk=root/'tools/ios-cross/iPhoneOS26.5.sdk'
            self.assertIsNotNone(apple.sdk_info(sdk))
            self.assertEqual(json.loads((sdk/'nxnative-sdk-source.json').read_text()),apple.SDK_REPOSITORY)
            self.assertFalse((task/'iPhoneOS26.5.sdk.zip').exists())

    def test_selected_sdk_version_downloads_that_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();config={'tools':str(root/'tools'),'sdk_version':'27.0'}
            release=apple.SDK_RELEASES['27.0']
            def download(url,destination,folder,digest,**kwargs):
                self.assertEqual(url,release['url'])
                self.assertEqual(digest,release['sha256'])
                self.assertEqual(kwargs['algorithm'],'sha256')
                sdk_zip(destination,version='27.0')
            with patch.object(deps,'download',side_effect=download):
                apple.install_sdk(task,config)
            sdk=root/'tools/ios-cross/iPhoneOS27.0.sdk'
            self.assertIsNotNone(apple.sdk_info(sdk))
            self.assertEqual(json.loads((sdk/'nxnative-sdk-source.json').read_text()),release)
            self.assertFalse((task/'iPhoneOS27.0.sdk.zip').exists())

    def test_selected_version_requires_that_exact_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tools=root/'tools';archive=root/'sdk.zip'
            sdk_zip(archive)
            apple.unpack_sdk(archive,tools/'ios-cross')
            discovery=dict(sdks=[],archives=[],metal='',releases=[],default_version='26.5',searched=[],minimum='26.5')
            with patch.object(apple.platform,'system',return_value='Windows'),patch.object(apple,'scan_apple_tools',return_value=discovery):
                resolved=apple.effective_config({'tools':str(tools),'sdk_version':'27.0'},discovery)
                checks={c['name']:c for c in environment({'tools':str(tools),'sdk_version':'27.0'})['checks']}
            self.assertNotIn('sdk',resolved)
            self.assertFalse(checks['sdk']['available'])
            self.assertTrue(checks['sdk']['path'].endswith('iPhoneOS27.0.sdk'))

    def test_checksum_failure_cannot_publish_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir()
            with patch.object(deps,'download',side_effect=ValueError('checksum mismatch')),patch.object(apple,'unpack_sdk') as unpack:
                with self.assertRaisesRegex(ValueError,'checksum'):
                    apple.install_sdk(task,{'tools':str(root/'tools')})
                unpack.assert_not_called()
            self.assertFalse((root/'tools/ios-cross/iPhoneOS26.5.sdk').exists())

    def test_existing_valid_sdk_is_reused_without_downloading(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);task=root/'task';task.mkdir();tools=root/'tools'
            archive=root/'sdk.zip';sdk_zip(archive)
            apple.unpack_sdk(archive,tools/'ios-cross')
            with patch.object(deps.platform,'system',return_value='Windows'),patch.object(deps,'download') as download:
                deps.install(task,{'dependencies':['sdk']},{'tools':str(tools)},Mock())
                download.assert_not_called()

    def test_sdk_source_persists_and_rejects_arbitrary_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(Path(directory),'token')
            try:
                with TestClient(app) as client:
                    client.headers['X-Session-Token']='token'
                    self.assertEqual(client.put('/api/config',json={'sdk_source':'local'}).status_code,200)
                    self.assertEqual(json.loads((Path(directory)/'config.json').read_text())['sdk_source'],'local')
                    self.assertEqual(client.put('/api/config',json={'sdk_source':'https://example.com/sdk.zip'}).status_code,400)
                    self.assertEqual(client.put('/api/config',json={'sdk_source':'xybp888'}).status_code,200)
            finally:app.state.jobs.close()

    def test_sdk_version_validation_and_manual_path_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(Path(directory),'token')
            try:
                with TestClient(app) as client:
                    client.headers['X-Session-Token']='token'
                    self.assertEqual(client.put('/api/config',json={'sdk_version':'99.0'}).status_code,400)
                    self.assertEqual(client.put('/api/config',json={'sdk_version':'27.0','sdk':''}).status_code,200)
                    config=json.loads((Path(directory)/'config.json').read_text())
                    self.assertEqual(config['sdk_version'],'27.0')
                    self.assertFalse(config.get('sdk'))
                    custom=Path(directory)/'custom.sdk'
                    self.assertEqual(client.put('/api/config',json={'sdk_version':'27.0','sdk':str(custom)}).status_code,200)
                    config=json.loads((Path(directory)/'config.json').read_text())
                    self.assertEqual(config['sdk_version'],'')
                    self.assertTrue(config['sdk'].endswith('custom.sdk'))
            finally:app.state.jobs.close()
