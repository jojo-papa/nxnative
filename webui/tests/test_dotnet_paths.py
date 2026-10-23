import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from webui import dependencies as deps
from webui.file_tools import filesystem_path, remove_stage


class DotnetPathAndRetry(unittest.TestCase):
    def test_extracts_real_failure_member_beyond_windows_max_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); archive=root/'dotnet.zip'
            member='packs/Microsoft.AspNetCore.App.Ref/10.0.13/analyzers/dotnet/cs/pt-BR/Microsoft.Extensions.Configuration.Binder.SourceGeneration.resources.dll'
            destination=root/('nested-repository-'+'x'*90)/'.webui-data/tools/.dotnet-regression'
            target=destination/member
            self.assertGreater(len(str(target.resolve())),260)
            with zipfile.ZipFile(archive,'w') as output:output.writestr(member,b'resource fixture')
            deps.unpack(archive,destination)
            self.assertEqual(filesystem_path(target).read_bytes(),b'resource fixture')
            remove_stage(destination,root)
            self.assertFalse(filesystem_path(destination).exists())

    def test_dotnet_failure_retains_verified_cache_for_next_task(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);first=root/'first-task';second=root/'retry-task'
            first.mkdir();second.mkdir();tools=root/'tools'
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as output:output.writestr('dotnet.exe',b'fixture')
            payload=archive.getvalue()
            asset=dict(rid='win-x64',url='https://builds.dotnet.microsoft.com/sdk.zip',hash=hashlib.sha512(payload).hexdigest())
            metadata=json.dumps({'latest-sdk':'10.0.100','releases':[{'sdk':{'version':'10.0.100','files':[asset]}}]}).encode()
            response=io.BytesIO(payload);response.headers={}
            with patch.object(deps.platform,'system',return_value='Windows'),patch.object(deps.platform,'machine',return_value='AMD64'),patch.object(deps.urllib.request,'urlopen',side_effect=[io.BytesIO(metadata),response,io.BytesIO(metadata)]) as urlopen:
                with self.assertRaisesRegex(RuntimeError,'probe failed'):
                    deps.install_dotnet(first,tools,Mock(side_effect=RuntimeError('probe failed')))
                cached=tools/'downloads/dotnet-10.0.100-win-x64.zip'
                self.assertEqual(cached.read_bytes(),payload)
                self.assertFalse((tools/'dotnet').exists())
                self.assertFalse((tools/'.dotnet-first-task').exists())
                deps.install_dotnet(second,tools,Mock())
                self.assertEqual(urlopen.call_count,3)
            self.assertTrue((tools/'dotnet/dotnet.exe').is_file())
            self.assertFalse(cached.exists())

    def test_corrupt_cached_file_is_replaced_and_never_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'dotnet.zip';archive.write_bytes(b'bad cached bytes')
            payload=b'verified bytes';response=io.BytesIO(payload);response.headers={}
            with patch.object(deps.urllib.request,'urlopen',return_value=response) as urlopen:
                deps.download('https://builds.dotnet.microsoft.com/sdk.zip',archive,root,hashlib.sha512(payload).hexdigest())
                self.assertEqual(urlopen.call_count,1)
            self.assertEqual(archive.read_bytes(),payload)
            self.assertFalse(archive.with_name('dotnet.zip.partial').exists())

    def test_extractor_is_not_run_after_dotnet_installation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            checks={'checks':[dict(name=name,available=False) for name in ('dotnet','extractor')]}
            with patch('webui.capabilities.environment',return_value=checks),patch.object(deps,'install_method',return_value='local'),patch.object(deps,'install_dotnet',side_effect=RuntimeError('unpack failed')),patch.object(deps,'find_dotnet') as finder:
                run=Mock()
                with self.assertRaisesRegex(RuntimeError,'dotnet, extractor'):
                    deps.install(root,{'dependencies':['extractor']},{'tools':str(root/'tools')},run)
                finder.assert_not_called();run.assert_not_called()
