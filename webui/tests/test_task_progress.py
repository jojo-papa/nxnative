from pathlib import Path
import tempfile
import unittest

from webui.jobs import emit, summary, write_json


class TaskProgress(unittest.TestCase):
    def task(self, kind='build', targets=('ios',)):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        write_json(folder / 'task.json', dict(kind=kind, files=[], keys='', targets=list(targets), settings={}))
        emit(folder, 'status', status='running')
        return folder

    def test_build_stages_advance_and_completion_is_full(self):
        folder = self.task()
        for stage, expected in (
            ('Preparing staged sources', 2),
            ('extract_v1114112', 15),
            ('shader_split', 45),
            ('windows_shaders', 62),
            ('host_compile', 82),
        ):
            emit(folder, 'stage', name=stage)
            self.assertEqual(summary(folder)['progress'], expected, stage)
        emit(folder, 'target', target='ios', status='succeeded')
        self.assertEqual(summary(folder)['progress'], 100)
        emit(folder, 'status', status='succeeded')
        self.assertEqual(summary(folder)['progress'], 100)

    def test_progress_covers_each_target(self):
        folder = self.task(targets=('ios', 'mac'))
        emit(folder, 'stage', name='Building ios')
        self.assertEqual(summary(folder)['progress'], 1)
        emit(folder, 'stage', name='shader_split')
        self.assertEqual(summary(folder)['progress'], 22)
        emit(folder, 'target', target='ios', status='succeeded')
        self.assertEqual(summary(folder)['progress'], 50)
        emit(folder, 'stage', name='Building mac')
        self.assertEqual(summary(folder)['progress'], 51)
        emit(folder, 'target', target='mac', status='succeeded')
        self.assertEqual(summary(folder)['progress'], 100)

    def test_failed_target_keeps_the_progress_reached(self):
        folder = self.task()
        emit(folder, 'stage', name='shader_split')
        emit(folder, 'target', target='ios', status='failed')
        emit(folder, 'status', status='failed')
        self.assertEqual(summary(folder)['progress'], 45)

    def test_detailed_stage_labels_keep_their_phase(self):
        folder = self.task()
        for stage, expected in (
            ('shader_split running 12:30', 45),
            ('windows_shaders 123/19593 shaders (0.6%)', 62),
            ('host_compile 5/129 sources', 82),
            ('ipa_pack running 1:20', 95),
        ):
            emit(folder, 'stage', name=stage)
            self.assertEqual(summary(folder)['progress'], expected, stage)

    def test_convert_uses_byte_progress_and_completion(self):
        folder = self.task(kind='convert')
        emit(folder, 'progress', done=2, total=5)
        self.assertEqual(summary(folder)['progress'], 40)
        emit(folder, 'status', status='succeeded')
        self.assertEqual(summary(folder)['progress'], 100)

    def test_inspect_has_no_progress_bar(self):
        folder = self.task(kind='inspect')
        emit(folder, 'stage', name='Inspecting package metadata')
        self.assertIsNone(summary(folder)['progress'])


if __name__ == '__main__':
    unittest.main()
