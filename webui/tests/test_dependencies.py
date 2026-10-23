import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import zipfile
from fastapi.testclient import TestClient
from webui import dependencies as deps
from webui.server import create_app
from webui.worker import execute

class Installation(unittest.TestCase):
    def test_platform_methods(self):
        with patch.object(deps.platform, 'machine', return_value='arm64'), patch.object(deps, 'brew_path', return_value='/opt/homebrew/bin/brew'):
            self.assertEqual(deps.install_method('xcodegen', {}, 'Darwin'), 'homebrew')
            self.assertEqual(deps.install_method('xcodegen', {}, 'Windows'), 'manual')
            self.assertEqual(deps.install_method('dotnet', {}, 'Darwin'), 'local')
            self.assertEqual(deps.install_method('sdk', {}, 'Darwin'), 'manual')
            self.assertEqual(deps.install_method('PIL', {}, 'Windows'), 'python')
        with patch.object(deps, 'brew_path', return_value=None):
            self.assertEqual(deps.install_method('xcodegen', {}, 'Darwin'), 'direct')

    def test_download_checksum_failure_removes_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / 'sdk.zip'
            response = io.BytesIO(b'incorrect'); response.headers = {}
            with patch.object(deps.urllib.request, 'urlopen', return_value=response):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    deps.download('https://builds.dotnet.microsoft.com/sdk.zip', archive, root, '0' * 128)
            self.assertFalse(archive.exists())

    def test_dotnet_verified_archive_is_published_after_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = root / 'task'; folder.mkdir()
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('dotnet.exe', 'test executable')
            payload = archive.getvalue()
            asset = dict(rid='win-x64', url='https://builds.dotnet.microsoft.com/sdk.zip', hash=hashlib.sha512(payload).hexdigest())
            metadata = {'latest-sdk':'10.0.100', 'releases':[{'sdk':{'version':'10.0.100', 'files':[asset]}}]}
            response = io.BytesIO(payload); response.headers = {'Content-Length':str(len(payload))}
            run = Mock()
            with patch.object(deps.platform, 'system', return_value='Windows'), patch.object(deps.platform, 'machine', return_value='AMD64'), patch.object(deps.urllib.request, 'urlopen', side_effect=[io.BytesIO(json.dumps(metadata).encode()), response]):
                deps.install_dotnet(folder, root/'tools', run)
            self.assertTrue((root/'tools/dotnet/dotnet.exe').is_file())
            self.assertFalse((folder/'dotnet.zip').exists())
            self.assertEqual(run.call_args.args[1][1], '--version')

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); archive = root / 'sdk.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                output.writestr('../escape', 'unsafe')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                deps.unpack(archive, root / 'stage')
            self.assertFalse((root / 'escape').exists())

    def test_python_install_uses_mirror_and_skips_installed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = {'tools': str(root / 'tools')}
            state = {'available': False}
            def environment(config):
                return {'checks': [dict(name='lz4', **state)]}
            def run(*args):
                state['available'] = True
            command = Mock(side_effect=run)
            with patch('webui.capabilities.environment', side_effect=environment):
                deps.install(root, {'dependencies': ['lz4']}, config, command)
                deps.install(root, {'dependencies': ['lz4']}, config, command)
            self.assertEqual(command.call_count, 1)
            self.assertIn(deps.DEFAULT_INDEX, command.call_args.args[1])
            self.assertIn('--target', command.call_args.args[1])
            self.assertEqual(command.call_args.args[2]['PIP_EXTRA_INDEX_URL'], '')

    def test_extract_installs_dotnet_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); installed = set()
            def environment(config):
                return {'checks': [dict(name=n, available=n in installed) for n in ('dotnet','extractor')]}
            def dotnet(*args): installed.add('dotnet')
            def run(*args):
                self.assertIn('dotnet', installed)
                installed.add('extractor')
            with patch('webui.capabilities.environment', side_effect=environment), patch.object(deps, 'install_dotnet', side_effect=dotnet), patch.object(deps, 'install_method', return_value='local'), patch.object(deps, 'find_dotnet', return_value='dotnet'), patch.object(deps, 'dotnet_environment', side_effect=lambda c, e: e):
                deps.install(root, {'dependencies':['extractor']}, {'tools':str(root/'tools')}, run)
            self.assertEqual(installed, {'dotnet','extractor'})

    def test_install_worker_does_not_require_keys_or_extractor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'task.json').write_text(json.dumps({'kind':'install','dependencies':['lz4']}))
            with patch.dict('os.environ', NX_WEB_CONFIG='{}'), patch.object(deps, 'install') as install:
                execute(root)
                install.assert_called_once()

class InstallAPI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, 'test-token')
        self.client = TestClient(self.app)
        self.client.headers['X-Session-Token'] = 'test-token'

    def tearDown(self):
        self.app.state.jobs.close(); self.client.close(); self.temp.cleanup()

    def test_install_allowlist_and_keys_free_request(self):
        checks = [dict(name='dotnet', available=False, auto_install=True), dict(name='sdk', available=False, auto_install=False)]
        with patch('webui.server.environment', return_value={'checks':checks}), patch.object(self.app.state.jobs, 'create', return_value='fake') as create:
            self.assertEqual(self.client.post('/api/dependencies/install', json={'names':['sdk']}).status_code, 400)
            self.assertEqual(self.client.post('/api/dependencies/install', json={'names':['dotnet; rm -rf /']}).status_code, 400)
            self.assertEqual(self.client.post('/api/dependencies/install', json={'names':[{}]}).status_code, 400)
            self.assertEqual(self.client.post('/api/dependencies/install', json={}).status_code, 200)
            task = create.call_args.args[0]
            self.assertEqual(task['dependencies'], ['dotnet'])
            self.assertNotIn('keys', task)

    def test_config_mirror_persists_without_path_conversion(self):
        url = 'https://pypi.org/simple'
        response = self.client.put('/api/config', json={'python_index':url})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads((self.root/'config.json').read_text())['python_index'], url)
        self.assertEqual(self.client.put('/api/config', json={'python_index':'https://unknown.example/simple'}).status_code, 400)

    def test_install_requires_auth_and_idle_queue(self):
        self.assertEqual(self.client.post('/api/dependencies/install', json={}, headers={'X-Session-Token':'bad'}).status_code, 401)
        checks = [dict(name='dotnet', available=False, auto_install=True)]
        with patch('webui.server.environment', return_value={'checks':checks}), patch.object(self.app.state.jobs, 'active', 'busy'):
            self.assertEqual(self.client.post('/api/dependencies/install', json={}).status_code, 400)

    def test_retry_install_does_not_ask_for_keys(self):
        folder = self.app.state.jobs.directory / ('a'*32); folder.mkdir()
        (folder/'task.json').write_text(json.dumps(dict(kind='install', dependencies=['lz4'], created=0)))
        (folder/'events.jsonl').write_text(json.dumps(dict(kind='status', status='failed'))+'\n')
        with patch.object(self.app.state.jobs, 'create', return_value='retry'):
            self.assertEqual(self.client.post('/api/tasks/'+'a'*32+'/retry').status_code, 200)
