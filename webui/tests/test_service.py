import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from webui.jobs import Jobs, emit, read_events, summary, write_json
from webui.server import create_app, data_directory
from webui.capabilities import profiles, environment, REPO


class Service(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, 'test-token')
        self.client = TestClient(self.app)
        self.client.headers['X-Session-Token'] = 'test-token'

    def tearDown(self):
        self.app.state.jobs.close(); self.client.close(); self.temp.cleanup()

    def upload(self, name='base.nsp', data=b'123'):
        response = self.client.post('/api/uploads', json=dict(name=name,size=len(data)))
        self.assertEqual(response.status_code, 200, response.text)
        identity = response.json()['id']
        response = self.client.put('/api/uploads/'+identity, content=data)
        self.assertEqual(response.status_code, 200, response.text)
        return identity

    def test_auth_origin_and_host(self):
        self.assertEqual(self.client.get('/api/tasks', headers={'X-Session-Token':'bad'}).status_code,401)
        self.assertEqual(self.client.get('/api/tasks', headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/tasks', headers={'Host':'evil.example'}).status_code,403)

    def test_session_cookie(self):
        self.assertEqual(self.client.post('/api/session').status_code,200)
        del self.client.headers['X-Session-Token']
        self.assertEqual(self.client.get('/api/tasks').status_code,200)

    def test_upload_resume_conflict(self):
        response=self.client.post('/api/uploads',json=dict(name='base.nsp',size=6))
        identity=response.json()['id']
        self.assertEqual(self.client.put('/api/uploads/'+identity,content=b'123').json()['offset'],3)
        self.assertEqual(self.client.put('/api/uploads/'+identity,content=b'123').status_code,400)
        self.assertEqual(self.client.get('/api/uploads/'+identity).json()['offset'],3)
        self.assertEqual(self.client.put('/api/uploads/'+identity+'?offset=3',content=b'456').json()['offset'],6)

    def test_traversal_rejected(self):
        for name in ('../a.nsp','a\\b.nsp','x.exe'):
            self.assertEqual(self.client.post('/api/uploads',json=dict(name=name,size=1)).status_code,400)

    def test_oversized_chunk(self):
        identity=self.client.post('/api/uploads',json=dict(name='a.nsp',size=10*1024**2)).json()['id']
        self.assertEqual(self.client.put('/api/uploads/'+identity,content=b'a'*(8*1024**2+1)).status_code,400)

    def test_delete_import_preserves_original(self):
        path=self.root/'original.nsp';path.write_bytes(b'x')
        identity=self.client.post('/api/import',json={'path':str(path)}).json()['id']
        self.assertEqual(self.client.delete('/api/uploads/'+identity).status_code,200)
        self.assertTrue(path.exists())

    def test_upload_history_lists_complete_uploads_without_paths(self):
        complete=self.upload('base.nsp',b'123')
        self.client.post('/api/uploads',json=dict(name='update.nsp',size=10))
        response=self.client.get('/api/uploads')
        self.assertEqual(response.status_code,200,response.text)
        rows=response.json()
        self.assertEqual([row['name'] for row in rows],['base.nsp'])
        self.assertEqual(rows[0]['id'],complete)
        self.assertEqual(rows[0]['size'],3)
        self.assertNotIn('path',rows[0])
        self.assertNotIn('keys',rows[0])

    def test_nsz_upload_and_convert_task(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        game=self.upload('update.nsz',b'nsz')
        keys=self.upload('prod.keys',b'fixture')
        response=self.client.post('/api/tasks',json=dict(files=[game],keys=keys,kind='convert',targets=['ios']))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.post(f"/api/tasks/{response.json()['id']}/cancel").status_code,200)

    def test_invalid_settings(self):
        game=self.upload();keys=self.upload('prod.keys',b'fixture')
        response=self.client.post('/api/tasks',json=dict(files=[game],keys=keys,settings={'DM_LANG':'invalid'}))
        self.assertEqual(response.status_code,400)

    def test_separate_romfs_validation_and_persistence(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        game=self.upload();(self.root/'prod.keys').write_bytes(b'fixture')
        keys=self.client.post('/api/import',json={'path':str(self.root/'prod.keys')}).json()['id']
        base=dict(files=[game],keys=keys,kind='build',targets=['ios'],retain_keys=True)
        for value in ('true', 1, None):
            response=self.client.post('/api/tasks',json=dict(base,separate_romfs=value))
            self.assertEqual(response.status_code,400,value)
        for payload in (dict(base,kind='convert',separate_romfs=True),
                        dict(base,targets=['mac'],separate_romfs=True)):
            self.assertEqual(self.client.post('/api/tasks',json=payload).status_code,400)
        with patch('webui.server.platform.system',return_value='Darwin'):
            response=self.client.post('/api/tasks',json=dict(base,targets=['ios','mac'],separate_romfs=True))
        self.assertEqual(response.status_code,200,response.text)
        identity=response.json()['id']
        task=json.loads((jobs.folder(identity)/'task.json').read_text())
        self.assertIs(task['separate_romfs'],True)
        self.assertNotIn('separate_romfs',task['settings'])
        self.assertEqual(self.client.post(f'/api/tasks/{identity}/cancel').status_code,200)
        retry=self.client.post(f'/api/tasks/{identity}/retry')
        self.assertEqual(retry.status_code,200,retry.text)
        retried=json.loads((jobs.folder(retry.json()['id'])/'task.json').read_text())
        self.assertIs(retried['separate_romfs'],True)
        with patch('webui.server.platform.system',return_value='Darwin'):
            default=self.client.post('/api/tasks',json=dict(base,targets=['mac'],separate_romfs=False))
        self.assertEqual(default.status_code,200,default.text)
        default_task=json.loads((jobs.folder(default.json()['id'])/'task.json').read_text())
        self.assertIs(default_task['separate_romfs'],False)

    def test_macos_target_requires_mac(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        game=self.upload();keys=self.upload('prod.keys',b'fixture')
        base=dict(files=[game],keys=keys,kind='build',targets=['mac'])
        with patch('webui.server.platform.system',return_value='Windows'):
            response=self.client.post('/api/tasks',json=base)
        self.assertEqual(response.status_code,400)
        self.assertIn('macOS packaging requires a Mac',response.json()['detail'])
        with patch('webui.server.platform.system',return_value='Darwin'):
            response=self.client.post('/api/tasks',json=base)
        self.assertEqual(response.status_code,200,response.text)
        self.client.post(f"/api/tasks/{response.json()['id']}/cancel")

    def test_output_folder_setting_persists(self):
        output=str(self.root/'delivered')
        response=self.client.put('/api/config',json={'output':output})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(json.loads((self.root/'config.json').read_text())['output'],str(Path(output).resolve()))

    def test_clear_cache_removes_intermediates_and_keeps_outputs(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        identity='a'*32;folder=jobs.directory/identity;folder.mkdir()
        write_json(folder/'task.json',dict(id=identity,files=[],keys='',kind='build',targets=['ios']))
        emit(folder,'status',status='succeeded')
        (folder/'inputs/sub').mkdir(parents=True);(folder/'inputs/sub/cache.bin').write_bytes(b'cache')
        (folder/'outputs').mkdir();(folder/'outputs/game.ipa').write_bytes(b'output')
        (folder/'private.keys').write_bytes(b'keys')
        (folder/'build.log').write_text('log')
        stage=self.root/'stage'/'key'/'tree';stage.mkdir(parents=True);(stage/'file').write_text('x')
        cache=self.root/'tools'/'shader-cache'/'cas';cache.mkdir(parents=True);(cache/'entry').write_text('x')
        jobs.active='busy'
        try:
            self.assertEqual(self.client.post('/api/cache/clear').status_code,400)
        finally:
            jobs.active=None
        response=self.client.post('/api/cache/clear')
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse((self.root/'stage').exists())
        self.assertFalse((self.root/'tools'/'shader-cache').exists())
        self.assertFalse((folder/'inputs').exists())
        self.assertTrue((folder/'outputs/game.ipa').is_file())
        self.assertTrue((folder/'private.keys').is_file())
        self.assertTrue((folder/'build.log').is_file())
        self.assertTrue((folder/'task.json').is_file())

    def test_multiple_artifacts_are_downloadable(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        identity=jobs.create(dict(files=[],keys='none',kind='build',targets=['ios'],separate_romfs=True))
        folder=jobs.folder(identity);outputs=folder/'outputs';outputs.mkdir()
        names=('Game.ipa','Game.ipa.sha256','Game.romfs.zip','Game.romfs.zip.sha256')
        for name in names:
            (outputs/name).write_text(name)
            emit(folder,'artifact',name=name)
        (outputs/'unlisted.bin').write_text('x')
        for name in names:
            self.assertEqual(self.client.get(f'/api/tasks/{identity}/artifacts/{name}').status_code,200,name)
        self.assertEqual(self.client.get(f'/api/tasks/{identity}/artifacts/unlisted.bin').status_code,404)

    def test_cancel_queued(self):
        jobs=self.app.state.jobs
        jobs.stop.set();jobs.thread.join()
        game=self.upload();keys=self.upload('prod.keys',b'fixture')
        identity=self.client.post('/api/tasks',json=dict(files=[game],keys=keys)).json()['id']
        self.assertEqual(self.client.post(f'/api/tasks/{identity}/cancel').status_code,200)
        self.assertEqual(summary(jobs.folder(identity))['status'],'cancelled')

    def test_artifact_allowlist(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        identity=jobs.create(dict(files=[],keys='none',kind='inspect'))
        folder=jobs.folder(identity);(folder/'outputs').mkdir();(folder/'outputs/private.keys').write_text('fixture')
        self.assertEqual(self.client.get(f'/api/tasks/{identity}/artifacts/private.keys').status_code,404)

    def test_data_directory_policy(self):
        with self.assertRaises(ValueError): data_directory(Path.home())
        with self.assertRaises(ValueError): data_directory(Path(self.root.anchor))
        with patch('webui.server.REPO', self.root), patch('pathlib.Path.home', return_value=self.root):
            self.assertEqual(data_directory(self.root/'.webui-data'), self.root/'.webui-data')

    def test_one_service_per_data_folder(self):
        with self.assertRaisesRegex(ValueError, 'already using'):
            Jobs(self.root, REPO, {})

    def test_uploaded_keys_are_kept_for_reuse(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        game=self.upload();keys=self.upload('prod.keys',b'fixture')
        identity=self.client.post('/api/tasks',json=dict(files=[game],keys=keys)).json()['id']
        source=Path(json.loads((jobs.folder(identity)/'task.json').read_text())['keys'])
        self.client.post(f'/api/tasks/{identity}/cancel')
        self.assertTrue(source.exists())

    def test_uploaded_keys_are_shared_and_kept(self):
        jobs=self.app.state.jobs;jobs.stop.set();jobs.thread.join()
        game=self.upload();keys=self.upload('prod.keys',b'fixture')
        identities=[self.client.post('/api/tasks',json=dict(files=[game],keys=keys)).json()['id'] for _ in range(2)]
        source=Path(json.loads((jobs.folder(identities[0])/'task.json').read_text())['keys'])
        self.client.post(f'/api/tasks/{identities[0]}/cancel')
        self.assertTrue(source.exists())
        self.client.post(f'/api/tasks/{identities[1]}/cancel')
        self.assertTrue(source.exists())

    def test_missing_dependencies_have_official_help(self):
        with patch('webui.capabilities.platform.system', return_value='Windows'):
            checks=environment({'tools':str(self.root/'missing-tools')})['checks']
        for check in checks:
            self.assertTrue(check['help_url'].startswith('https://'))
            self.assertTrue(check['help_text'])
        self.assertFalse(next(c for c in checks if c['name']=='metal')['available'])
        self.assertEqual(next(c for c in checks if c['name']=='metal')['help_url'],'https://developer.apple.com/download/all/?q=metal%20developer%20tools%20for%20windows')

    def test_windows_capabilities(self):
        for profile in profiles('Windows'):
            self.assertFalse(profile['mac'])
            if profile['graphics']=='vulkan':self.assertFalse(profile['ios'])


class Recovery(unittest.TestCase):
    def test_recover_torn_event_and_clean_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);folder=root/'tasks'/('a'*32);folder.mkdir(parents=True)
            write_json(folder/'task.json',dict(id='a'*32,retain_keys=False))
            emit(folder,'status',status='running')
            with (folder/'events.jsonl').open('ab') as stream:stream.write(b'{"incomplete":')
            (folder/'private.keys').write_text('fixture')
            jobs=Jobs(root,REPO,{})
            try:
                self.assertEqual(summary(folder)['status'],'interrupted')
                self.assertFalse((folder/'private.keys').exists())
                self.assertEqual(len(read_events(folder/'events.jsonl')[0]),2)
            finally:jobs.close()


if __name__ == '__main__': unittest.main()
