import plistlib
import re
from pathlib import Path
import unittest

from webui.build.windows.ios_cross_pack import base_info_plist

REPO = Path(__file__).resolve().parents[2]


class FullscreenTests(unittest.TestCase):
    def test_project_yml_launch_keys(self):
        text = (REPO / 'dm/ios/project.yml').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^\s*UIRequiresFullScreen:\s*true\s*$')
        self.assertRegex(text, r'(?m)^\s*UILaunchScreen:\s*\{\s*\}\s*$')
        self.assertRegex(text, r'(?m)^\s*UIFileSharingEnabled:\s*true\b')
        self.assertRegex(text, r'(?m)^\s*LSSupportsOpeningDocumentsInPlace:\s*true\b')
        self.assertNotIn('UILaunchStoryboardName', text)

    def test_windows_pack_plist(self):
        value = base_info_plist(
            game_id='0100A00019DE0000',
            display_name='Fixture',
            app_version='1.0',
            app_category='public.app-category.games',
        )
        self.assertIs(value['UIRequiresFullScreen'], True)
        self.assertEqual(value['UILaunchScreen'], {})
        self.assertIs(value['UIFileSharingEnabled'], True)
        self.assertIs(value['LSSupportsOpeningDocumentsInPlace'], True)
        self.assertNotIn('UILaunchStoryboardName', value)
        loaded = plistlib.loads(plistlib.dumps(value, fmt=plistlib.FMT_BINARY))
        self.assertIs(loaded['UIRequiresFullScreen'], True)
        self.assertEqual(loaded['UILaunchScreen'], {})


if __name__ == '__main__':
    unittest.main()
