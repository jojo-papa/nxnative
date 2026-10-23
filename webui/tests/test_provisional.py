import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collections import Counter
import zipfile

from webui import provisional, worker
from webui.capabilities import game

TITLE = '010054B01AD92000'


def facts():
    romfs = {
        'n': 10, 'bytes': 4096,
        'tops': Counter({'/data': 10}), 'topb': Counter({'/data': 4096}),
        'exts': Counter({'.bnsh': 10}), 'extb': Counter({'.bnsh': 4096}),
        'extc': Counter(), 'mags': Counter({'BNSH': 10}),
        'magb': Counter({'BNSH': 4096}), 'dirs': Counter({'data': 10}),
        'biggest': (2048, 'data/big.bnsh'), 'root': set(),
    }
    F = {
        'mods': {'main': {'bid': '11' * 16, 'kind': 'the game', 'bss': 0, 'far': False,
                           'sizes': [1, 1, 1], 'imports': set(), 'exports': set(), 'comps': set()},
                 'sdk': {'bid': '22' * 16, 'kind': 'nnSdk', 'bss': 0, 'far': False,
                         'sizes': [1, 1, 1], 'imports': set(), 'exports': set(), 'comps': set()}},
        'program': 0x010054B01AD92000, 'sysres': 0, 'sdk': 16,
        'romfs': romfs, 'main_markers': {'NVN'}, 'glsl_src': 0, 'gl_names': 0,
    }
    guessed = {'modules': ('main sdk', 'every module main imports from')}
    sources = {'graphics': ('nvn', 'main imports nvnBootstrapLoader')}
    for name in ('glslc_capture', 'vk_capture', 'ue_decode', 'oodle_packs', 'ue_legacy'):
        sources[name] = (False, '')
    return dict(F=F, guess=guessed, sources=sources, name='Test Game', display='1.0.0',
                version='v0', survey='survey')


class ProvisionalProfile(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_profile_is_written_outside_the_repository(self):
        folder = self.root / 'profile' / TITLE
        self.assertTrue(provisional.write_profile(folder, TITLE, facts()))
        self.assertFalse(provisional.write_profile(folder, TITLE, facts()))
        profile = game.load(str(folder))
        self.assertEqual(profile.id, TITLE)
        self.assertEqual(profile.title_id, int(TITLE, 16))
        self.assertEqual(profile.get('program_id'), TITLE)
        self.assertEqual(profile.get('package'), 'v0')
        self.assertEqual(profile.get('name'), 'Test Game')
        self.assertEqual(profile.builds()['v0']['display'], '1.0.0')
        self.assertEqual(profile.words('modules'), ['main', 'sdk'])
        self.assertEqual(profile.get('romfs_marker'), 'data/big.bnsh')
        for name in provisional.EMPTY_TABLES:
            self.assertTrue((folder / name).is_file(), name)

    def test_report_is_json_safe_and_marks_a_provisional_build(self):
        value = provisional.report(facts())
        json.dumps(value)
        self.assertEqual(value['graphics'], 'nvn')
        self.assertIn('may not boot', value['warning'])
        self.assertEqual(value['modules']['main']['build_id'], '11' * 16)


class ProvisionalWorker(unittest.TestCase):
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

    def test_unknown_title_is_surveyed_and_built_with_its_profile(self):
        value = dict(kind='build', files=[str(self.source)], keys=str(self.keys), game=TITLE,
                     targets=['ios'], settings={}, separate_romfs=False)
        (self.folder / 'task.json').write_text(json.dumps(value), encoding='utf-8')
        commands = []

        def fake_run(folder, command, env=None, cwd=None):
            command = [str(x) for x in command]
            commands.append(command)
            output = Path(command[command.index('--out') + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output, 'w') as archive:
                archive.writestr('Payload/DmIOS.app/DmIOS', b'x')

        with patch.dict(os.environ, NX_WEB_CONFIG=json.dumps({'tools': str(self.root / 'tools')}),
                        NX_STAGE_ROOT=str(self.root / 'stage-root')), \
             patch.object(worker.platform, 'system', return_value='Windows'), \
             patch.object(worker, 'profiles', return_value=[]), \
             patch.object(worker, 'entries', return_value=[]), \
             patch.object(worker, 'catalog', side_effect=lambda extractor, keys, path: [
                 dict(title_id=TITLE, version=0, type=0x80)]), \
             patch.object(worker, 'provisional') as support, \
             patch.object(worker.staging, 'ensure', return_value=self.stage), \
             patch.object(worker, 'run', side_effect=fake_run):
            support.survey.return_value = facts()
            support.write_profile.side_effect = lambda folder, title, value: provisional.write_profile(folder, title, value)
            support.report.side_effect = provisional.report
            worker.execute(self.folder)
        self.assertTrue(commands)
        command = commands[0]
        self.assertIn('--provisional', command)
        self.assertEqual(command[command.index('--game') + 1], str(self.folder / 'profile' / TITLE))
        report = json.loads((self.folder / 'outputs' / 'provisional.json').read_text())
        self.assertEqual(report['title_id'], TITLE)
        events = [json.loads(line) for line in (self.folder / 'events.jsonl').read_text().splitlines()]
        self.assertTrue(any(event.get('name') == 'Surveying unregistered title ' + TITLE for event in events))
        self.assertTrue(any(event.get('name', '').startswith('Provisional profile:') for event in events))

    def test_mac_provisional_build_reuses_the_task_profile(self):
        value = dict(kind='build', files=[str(self.source)], keys=str(self.keys), game=TITLE,
                     targets=['ios'], settings={}, separate_romfs=False)
        (self.folder / 'task.json').write_text(json.dumps(value), encoding='utf-8')
        commands = []

        def fake_run(folder, command, env=None, cwd=None):
            command = [str(x) for x in command]
            commands.append(command)
            output = Path(command[command.index('--out') + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b'ipa')

        with patch.dict(os.environ, NX_WEB_CONFIG=json.dumps({'tools': str(self.root / 'tools')}),
                        NX_STAGE_ROOT=str(self.root / 'stage-root')), \
             patch.object(worker.platform, 'system', return_value='Darwin'), \
             patch.object(worker, 'profiles', return_value=[]), \
             patch.object(worker, 'entries', return_value=[]), \
             patch.object(worker, 'catalog', side_effect=lambda extractor, keys, path: [
                 dict(title_id=TITLE, version=0, type=0x80)]), \
             patch.object(worker, 'provisional') as support, \
             patch.object(worker.staging, 'ensure', return_value=self.stage), \
             patch.object(worker, 'run', side_effect=fake_run):
            support.survey.return_value = facts()
            support.write_profile.side_effect = lambda folder, title, value: provisional.write_profile(folder, title, value)
            support.report.side_effect = provisional.report
            worker.execute(self.folder)
        command = commands[0]
        self.assertIn('--provisional', command)
        self.assertEqual(command[command.index('--profile-out') + 1], str((self.folder / 'profile').resolve()))


if __name__ == '__main__':
    unittest.main()
