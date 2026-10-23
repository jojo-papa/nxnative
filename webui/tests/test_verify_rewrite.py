import struct
from pathlib import Path
import tempfile
import unittest

from webui.build.windows import verify_nso_rewrite as verifier

BUILD_ID = '00112233445566778899aabbccddeeff'


class VerifyRewrite(unittest.TestCase):
    def test_spin_edges_are_checked_instead_of_the_unchanged_head(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exefs, patched = root / 'ExeFS', root / 'patched'
            exefs.mkdir(); patched.mkdir()
            nso = bytearray(0x100 + 0xc)
            struct.pack_into('<I', nso, 0x10, 0x100)
            struct.pack_into('<I', nso, 0x14, 0)
            struct.pack_into('<I', nso, 0x18, 0xc)
            struct.pack_into('<I', nso, 0x60, 0xc)
            nso[0x40:0x50] = bytes.fromhex(BUILD_ID)
            struct.pack_into('<I', nso, 0x100, 0x39400208)   # ldrb w8, [x16]: the spin head stays original
            (exefs / 'main').write_bytes(nso)
            image = bytearray(0x30)
            struct.pack_into('<I', image, 4, 0x14000007)     # b 0x20, into the patch area
            (patched / 'main.patched.bin').write_bytes(image)
            (patched / 'main.fixups.tsv').write_text(f'# PATCH_OFF\t0x20\n# BUILD_ID\t{BUILD_ID}\n', encoding='utf-8')
            (patched / 'main.sites.tsv').write_text('0x0\tS\t0x4\n', encoding='utf-8')
            result = verifier.verify(exefs / 'main', patched, 'main')
            self.assertTrue(result['branch_targets_within_patch'])
            self.assertEqual(result['uncovered_sites'], 0)


if __name__ == '__main__':
    unittest.main()
