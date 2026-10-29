import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
import zipfile

from webui.build.romfs_archive import (archive_path, discard_archive, pack_command, prepare_archive,
                                       verify_archive, verify_no_romfs)

REPO = Path(__file__).resolve().parents[2]


class RomfsArchiveTests(unittest.TestCase):
    def test_archive_path(self):
        self.assertEqual(archive_path(Path('Game.ipa')), Path('Game.romfs.zip'))
        self.assertEqual(archive_path(Path('Game')), Path('Game.romfs.zip'))

    def test_pack_and_verify_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            romfs = root / 'RomFS'
            (romfs / 'System').mkdir(parents=True)
            (romfs / 'System' / 'Resource').write_bytes(b'marker')
            (romfs / 'data').mkdir()
            (romfs / 'data' / 'thing.zs').write_bytes(b'compressed-looking payload')
            (romfs / 'data' / 'plain.bin').write_bytes(b'plain')
            archive = root / 'Game.romfs.zip'
            (root / 'Game.romfs.zip.partial').write_bytes(b'stale')
            prepare_archive(archive, romfs, 'System/Resource')
            self.assertFalse((root / 'Game.romfs.zip.partial').exists())
            subprocess.run(pack_command(sys.executable, REPO / 'dm/ios/tools/pack_ipa.py',
                                        archive, romfs, '.zs'), check=True, capture_output=True)
            verify_archive(archive, 'System/Resource')
            with zipfile.ZipFile(archive) as value:
                names = value.namelist()
                self.assertIn('romfs/System/Resource', names)
                self.assertTrue(all(name.startswith('romfs/') for name in names if name not in ('romfs', 'romfs/')))
                self.assertEqual(value.getinfo('romfs/data/thing.zs').compress_type, zipfile.ZIP_STORED)
            discard_archive(archive)
            self.assertFalse(archive.exists())

    def test_missing_marker_and_layout_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            romfs = root / 'RomFS'
            (romfs / 'other').mkdir(parents=True)
            (romfs / 'other' / 'file').write_bytes(b'x')
            with self.assertRaises(ValueError):
                prepare_archive(root / 'a.romfs.zip', romfs, 'System/Resource')
            archive = root / 'b.romfs.zip'
            with zipfile.ZipFile(archive, 'w') as value:
                value.writestr('outside/file', b'x')
            with self.assertRaises(ValueError):
                verify_archive(archive, 'System/Resource')
            with zipfile.ZipFile(archive, 'w') as value:
                value.writestr('romfs/other/file', b'x')
            with self.assertRaises(ValueError):
                verify_archive(archive, 'System/Resource')
            (romfs / 'System').mkdir()
            (romfs / 'System' / 'Resource').write_bytes(b'marker')
            with self.assertRaises(OSError):
                prepare_archive(root / 'c.romfs.zip', romfs, 'System/Resource', margin=10**18)

    def test_ipa_romfs_detection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            good = root / 'good.ipa'
            with zipfile.ZipFile(good, 'w') as value:
                value.writestr('Payload/DmIOS.app/DmIOS', b'x')
            verify_no_romfs(good)
            bad = root / 'bad.ipa'
            with zipfile.ZipFile(bad, 'w') as value:
                value.writestr('Payload/DmIOS.app/romfs/System/Resource', b'x')
            with self.assertRaises(ValueError):
                verify_no_romfs(bad)


if __name__ == '__main__':
    unittest.main()
