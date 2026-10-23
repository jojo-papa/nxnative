import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from webui import bootstrap


class Startup(unittest.TestCase):
    def test_satisfied_skips_all_subprocesses(self):
        with patch.object(bootstrap, 'missing_dependencies', return_value=[]), patch.object(bootstrap.subprocess, 'run') as run:
            self.assertIsNone(bootstrap.ensure_dependencies(Path('unused'), Path('unused')))
            run.assert_not_called()

    def test_version_bounds_and_missing_import(self):
        def version(name):
            return {'fastapi': '0.114.0', 'uvicorn': '1.0.0'}.get(name, '1.0.0')
        with patch.object(bootstrap.importlib.metadata, 'version', side_effect=version), patch.object(bootstrap.importlib, 'import_module'):
            self.assertEqual(bootstrap.missing_dependencies(), ['fastapi', 'uvicorn'])
        with patch.object(bootstrap.importlib.metadata, 'version', return_value='0.200.0'), patch.object(bootstrap.importlib, 'import_module', side_effect=ImportError):
            self.assertEqual(bootstrap.missing_dependencies(), list(bootstrap.PACKAGES))

    def test_missing_creates_environment_installs_checks_and_launches(self):
        with tempfile.TemporaryDirectory() as folder:
            results = [Mock(returncode=n) for n in (0, 1, 0, 0, 0)]
            with patch.object(bootstrap, 'missing_dependencies', return_value=['fastapi']), patch.object(bootstrap.subprocess, 'run', side_effect=results) as run:
                self.assertEqual(bootstrap.ensure_dependencies(Path(folder), Path('repo')), 0)
                calls = run.call_args_list
                self.assertIn('venv', calls[0].args[0])
                self.assertIn('install', calls[2].args[0])
                self.assertTrue(calls[2].kwargs['check'])
                self.assertIn('--check', calls[3].args[0])
                self.assertNotIn('PYTHONPATH', calls[4].kwargs['env'])

    def test_existing_environment_skips_pip(self):
        with patch.object(bootstrap, 'missing_dependencies', return_value=['uvicorn']), patch.object(bootstrap.Path, 'is_file', return_value=True), patch.object(bootstrap.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(bootstrap.ensure_dependencies(Path('data'), Path('repo')), 0)
            self.assertEqual(run.call_count, 2)
            self.assertFalse(any('install' in call.args[0] for call in run.call_args_list))

    def test_failed_install_reports_error_without_launching(self):
        with patch.object(bootstrap, 'missing_dependencies', return_value=['uvicorn']), patch.object(bootstrap.Path, 'is_file', return_value=True), patch.object(bootstrap.subprocess, 'run', side_effect=[Mock(returncode=1), subprocess.CalledProcessError(1, 'pip')]) as run:
            with self.assertRaisesRegex(RuntimeError, 'Automatic dependency setup failed'):
                bootstrap.ensure_dependencies(Path('data'), Path('repo'))
            self.assertEqual(run.call_count, 2)
