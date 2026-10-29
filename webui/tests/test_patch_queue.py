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
    '0010-nso-sym-dynsym-widths.patch': ['dyn_tags', 'symtab_ok', '<IIIBBH'],
    '0011-ios-audio-probe-host.patch': ['DM_AUDIO_GAIN_OVERRIDE', 'dm_audio_set_user_gain'],
    '0012-ios-audio-probe-session.patch': ['DM_AUDIO_CATEGORY'],
    '0013-ios-letterbox-chrome.patch': ['DM_CHROME', 'front_ios_letterbox'],
    '0014-nvn-screen-fill.patch': ['DM_SCREEN_FILL'],
    '0015-ios-screen-fill.patch': ['DM_SCREEN_FILL'],
    '0016-shader-split-zstd-module.patch': ['zstd_mod()', "shutil.which('zstd')"],
    '0017-shader-gs-stage-layout.patch': ['def output_layout(', 'def reader(', 'def capture_input('],
    '0018-shader-gs-ssbo-slot.patch': ["'gs': 0x410", "b['flags'] & 1)"],
    '0019-nvn-gs-ssbo-base.patch': ['stage == 2 ? 0x410'],
    '0020-host-output-size-fields.patch': ['out_w, out_h'],
    '0021-host-screen-aspect-decl.patch': ['double front_screen_aspect(void);'],
    '0022-host-output-aspect-loader.patch': ['DM_ASPECT', 'DM_OUTPUT_SIZE', 'output_aspect'],
    '0023-nso-output-size-fixups.patch': ['FS_KEYS', 'ctx.keys'],
    '0024-game-aspect-key.patch': ['DM_GAME_ASPECT_ANY'],
    '0025-settings-aspect-row.patch': ['DM_ASPECT'],
    '0026-settings-cond-and.patch': ["if '&' in cond"],
    '0027-ios-wide-canvas.patch': ['front_ios_canvas_aspect', 'front_screen_aspect'],
    '0028-ios-gamepad-canvas-touch.patch': ['front_ios_canvas_aspect'],
    '0029-botw-output-size-stub.patch': ['OUTPUT_W', 'OUTPUT_H'],
    '0030-botw-aspect-any.patch': ['aspect\tany'],
    '0031-nvn-projection-probe.patch': ['DM_NVN_PROJ', 'projection candidate'],
    '0032-host-projection-widen-dm__gfx__nvn__nvn_mtl.m.patch': ['DM_PROJ_WIDEN', 'proj_scale_upload'],
    '0032-host-projection-widen-dm__ios__Sources__front_ios.m.patch': ['"wide"', 'front_ios_canvas_aspect'],
    '0033-sf-serve-connected-services.patch': ['"olsc:u", "hid"', 'the host answers it with an empty session'],
    '0034-projection-detection-range-dm__gfx__nvn__nvn_mtl.m.patch': ['ys > 0.05f && ys < 64.0f', 'proj_scan'],
    '0035-host-buttons-colour-dm__ios__Sources__DmGamepad.m.patch': ['k_hostFill', 'B_MINUS'],
    '0036-chrome-colour-no-reflection-dm__ios__Sources__front_ios.m.patch': ['DM_REFLECT", 0', 'colorWithRed:0.12 green:0.32 blue:0.82'],
    '0037-chrome-restore-button-dm__ios__Sources__front_ios.m.patch': ['restoreChrome', '显示界面'],
    # The queue stops at the baseline of 10/26 22:47, the package the player confirmed: full screen
    # without black bars, the 3D picture not distorted, the 2D text stretched, no flickering.
    # What came after it stays out. 0039 is the one that made the picture flicker: it began to
    # correct the uniform buffers the game writes itself, so the interface layer's own orthographic
    # projection was corrected as well and the 3D picture and the interface no longer had the same
    # proportions. The patches are still in webui/patches/ as files, they are simply not in the queue.
    '0044-audio-level-dm__host__hle_audio.c.patch': ['audio level #%d: peak'],
    '0045-rumble-level-dm__host__haptics_apple.m.patch': ['rumble intensity', "the phone's Taptic Engine"],
    '0046-rumble-permit-dm__host__hle_hid.c.patch': ['the game asks whether it may vibrate'],
    '0047-ios-chinese-dialogs-dm__ios__Sources__front_ios.m.patch': ['存档失败', '确定', '存储空间不足'],
    # 0048: the screen's own aspect decides how the picture fills it.  A screen wider than 16:9 (a phone) is filled
    # horizontally, the horizontal field of view is widened to match; a narrower one (a 4:3 tablet) keeps the picture's
    # 16:9 and takes the chrome in the vertical direction.
    '0048-screen-aspect-fills-dm__ios__Sources__front_ios.m.patch': ['front_ios_screen_aspect', 'front_ios_fills_screen',
                                                                    'a > 16.0 / 9.0'],
    # 0049: the projection is looked for in a copy of the bytes, not in the guest's memory (a page without an alias
    # stops the host with SIGBUS).
    '0049-proj-safe-copy-dm__gfx__nvn__nvn_mtl.m.patch': ['proj_copy', 'nvn_host_readable(addr + o, chunk)'],
    # 0050: the drawables are not thrown away for nothing, and a memory warning is logged.
    '0050-drawable-and-memory-warning-dm__ios__Sources__front_ios.m.patch': ['CGSizeEqualToSize(l.drawableSize, s)',
                                                                              'UIApplicationDidReceiveMemoryWarningNotification'],
}


class PatchQueueTests(unittest.TestCase):
    def test_patches_apply_and_add_markers(self):
        # The patches are applied in series order, each one on the result of the previous
        # patches on the same target (staging.ensure() does the same), so a patch that
        # touches a file an earlier patch already touched is based on that result.
        queue = staging.patch_queue()
        self.assertEqual(len(queue), len(MARKERS))
        contents = {}
        for patch, target in queue:
            base = contents.get(target)
            if base is None:
                base = (REPO / target).read_bytes()
            data = diffapply.apply_bytes(base, patch.read_bytes(), target)
            contents[target] = data
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
