import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from webui import worker
from webui.build.romfs_archive import archive_path

TITLE = '0100A00019DE0000'


class WorkerSeparateRomfsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'task'
        self.folder.mkdir()
        self.source = self.root / 'game.nsp'
        self.source.write_bytes(b'nsp')
        self.keys = self.root / 'prod.keys'
        self.keys.write_bytes(b'keys')
        tools = self.root / 'tools'
        self.extractor = tools / 'nx_extract' / ('nx_extract.exe' if os.name == 'nt' else 'nx_extract')
        self.extractor.parent.mkdir(parents=True)
        self.extractor.write_bytes(b'extractor')
        self.stage = self.root / 'fake-stage'
        self.stage.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def task(self, targets=('ios',), separate=False):
        value = dict(kind='build', files=[str(self.source)], keys=str(self.keys), game=TITLE,
                     targets=list(targets), settings={}, separate_romfs=separate)
        (self.folder / 'task.json').write_text(json.dumps(value), encoding='utf-8')
        return value

    def run_build(self, targets=('ios',), separate=False, system='Windows', output=None):
        task = self.task(targets, separate)
        commands = []
        marker = worker.game.load(TITLE).get('romfs_marker')

        def fake_run(folder, command, env=None, cwd=None):
            command = [str(x) for x in command]
            commands.append(command)
            output = Path(command[command.index('--out') + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr('Payload/DmIOS.app/DmIOS', b'x')
            if '--separate-romfs' in command:
                with zipfile.ZipFile(archive_path(output), 'w') as archive:
                    archive.writestr('romfs/' + marker, b'marker')

        config = {'tools': str(self.root / 'tools')}
        if output is not None: config['output'] = str(output)
        profiles = [{'id': TITLE, 'graphics': 'nvn', 'ios': True, 'mac': True, 'reason': ''}]
        with patch.dict(os.environ, NX_WEB_CONFIG=json.dumps(config), NX_STAGE_ROOT=str(self.root / 'stage-root')), \
             patch.object(worker.platform, 'system', return_value=system), \
             patch.object(worker, 'profiles', return_value=profiles), \
             patch.object(worker, 'entries', return_value=[]), \
             patch.object(worker, 'catalog', side_effect=lambda extractor, keys, path: [dict(title_id=TITLE, version=0, type=0x80)]), \
             patch.object(worker.staging, 'ensure', return_value=self.stage), \
             patch.object(worker, 'run', side_effect=fake_run):
            if separate and 'ios' not in targets:
                with self.assertRaises(ValueError):
                    worker.execute(self.folder)
                return [], []
            worker.execute(self.folder)
        events = [json.loads(line) for line in (self.folder / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        artifacts = [event['name'] for event in events if event['kind'] == 'artifact']
        return artifacts, commands

    def test_separate_ios_emits_archive(self):
        artifacts, commands = self.run_build(separate=True)
        self.assertEqual(artifacts, ['inspection.json', TITLE + '.ipa', TITLE + '.ipa.sha256',
                                     TITLE + '.romfs.zip', TITLE + '.romfs.zip.sha256'])
        self.assertEqual(len(commands), 1)
        self.assertIn('--separate-romfs', commands[0])

    def test_default_keeps_bundled_romfs(self):
        artifacts, commands = self.run_build(separate=False)
        self.assertEqual(artifacts, ['inspection.json', TITLE + '.ipa', TITLE + '.ipa.sha256'])
        self.assertNotIn('--separate-romfs', commands[0])
        self.assertFalse((self.folder / 'outputs' / (TITLE + '.romfs.zip')).exists())

    def test_both_targets_archive_only_for_ios(self):
        artifacts, commands = self.run_build(targets=('mac', 'ios'), separate=True, system='Darwin')
        self.assertEqual(artifacts, ['inspection.json', TITLE + '.app.zip', TITLE + '.app.zip.sha256',
                                     TITLE + '.ipa', TITLE + '.ipa.sha256',
                                     TITLE + '.romfs.zip', TITLE + '.romfs.zip.sha256'])
        self.assertEqual(len(commands), 2)
        self.assertNotIn('--separate-romfs', commands[0])
        self.assertIn('--separate-romfs', commands[1])

    def test_output_folder_receives_finished_artifacts(self):
        delivered = self.root / 'delivered'
        artifacts, commands = self.run_build(separate=True, output=delivered)
        self.assertIn(TITLE + '.ipa', artifacts)
        for name in (TITLE + '.ipa', TITLE + '.ipa.sha256', TITLE + '.romfs.zip', TITLE + '.romfs.zip.sha256'):
            self.assertTrue((delivered / name).is_file(), name)
        self.assertEqual((delivered / (TITLE + '.ipa')).read_bytes(),
                         (self.folder / 'outputs' / (TITLE + '.ipa')).read_bytes())

    def test_mac_only_separate_is_rejected(self):
        self.task(('mac',), True)
        with patch.dict(os.environ, NX_WEB_CONFIG=json.dumps({'tools': str(self.root / 'tools')})):
            with self.assertRaisesRegex(ValueError, 'iOS target'):
                worker.execute(self.folder)

    def test_selected_missing_sdk_blocks_build(self):
        self.task()
        config = {'tools': str(self.root / 'tools'), 'sdk_version': '27.0'}
        with patch.dict(os.environ, NX_WEB_CONFIG=json.dumps(config)), \
             patch.object(worker.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(ValueError, 'SDK version'):
                worker.execute(self.folder)


if __name__ == '__main__':
    unittest.main()
