import unittest
from pathlib import Path

from webui import diffapply, staging

REPO = Path(__file__).resolve().parents[2]

MARKERS = {
    '0001-shader-split-posix-paths.patch': ['os.sep'],
    '0002-gen-embed-posix-paths-sections.patch': ['no_dead_strip'],
    '0003-hle-count-targetconditionals.patch': ['TargetConditionals'],
    '0004-nx-extract-catalog.patch': ['--catalog'],
    '0005-host-makefile-metalfx.patch': ['MetalFX'],
    '0006-nvn-mtl-spatial-upscaling.patch': ['nvn_spatial.inc'],
    '0007-main-launch-settings.patch': ['DmLaunchSettings.h'],
    '0008-build-ipa-launch-defaults.patch': ['NX_LAUNCH_DEFAULTS', 'NX_SEPARATE_ROMFS'],
    '0009-build-ipa-from-nsp-webui.patch': ['@NXEVENT', 'webui/build/macos/pack_app.py',
                                            '--separate-romfs', 'NX_SEPARATE_ROMFS',
                                            'RomFS archive'],
}


class PatchQueueTests(unittest.TestCase):
    def test_patches_apply_and_add_markers(self):
        queue = staging.patch_queue()
        self.assertEqual(len(queue), 9)
        for patch, target in queue:
            data = diffapply.apply_file(REPO / target, patch.read_bytes(), target)
            text = data.decode('utf-8')
            for marker in MARKERS[patch.name]:
                self.assertIn(marker, text, f'{patch.name}: {marker}')
            self.assertNotIn('\r\n', text)

    def test_second_application_is_rejected(self):
        patch, target = staging.patch_queue()[0]
        once = diffapply.apply_file(REPO / target, patch.read_bytes(), target)
        with self.assertRaises(diffapply.DiffError):
            diffapply.apply_bytes(once, patch.read_bytes(), target)

    def test_target_mismatch_is_rejected(self):
        patch, _target = staging.patch_queue()[0]
        with self.assertRaises(diffapply.DiffError):
            diffapply.apply_file(REPO / 'dm/host/Makefile', patch.read_bytes(), 'dm/host/Makefile')

    def test_path_escape_is_rejected(self):
        patch = (b'--- a/x\n+++ b/../x\n@@ -1 +1 @@\n-a\n+b\n')
        with self.assertRaises(diffapply.DiffError):
            diffapply.apply_bytes(b'a\n', patch, None)

    def test_crlf_target_is_normalized(self):
        patch = b'--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n'
        self.assertEqual(diffapply.apply_bytes(b'a\r\nb\r\n', patch, 'x'), b'a\nc\n')


if __name__ == '__main__':
    unittest.main()
