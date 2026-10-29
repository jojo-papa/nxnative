// Read-only view of the upstream's MetalFX scaler (DM_PRESENT_UPSCALE=metalfx).
//
// The upstream grew the present's spatial upscaling itself (dm/gfx/nvn/nvn_mtl.m,
// fx_state / fx_encode / g_fx_present), so this fork does not implement a
// scaler of its own: it only reads the state the upstream keeps, for the
// performance HUD, which shows the game picture's size and the presented one.
//
// This file is included into nvn_mtl.m by patch 0010, right after the upstream's
// g_fx_present, so the HUD sees the same textures the present encodes with.

void dm_gfx_hud_sizes(unsigned *iw, unsigned *ih, unsigned *ow, unsigned *oh, int *active) {
    if (!g_fx_present.sc || !g_fx_present.in || !g_fx_present.out) {
        *iw = *ih = *ow = *oh = 0; *active = 0;
        return;
    }
    *iw = (unsigned)g_fx_present.in.width;  *ih = (unsigned)g_fx_present.in.height;
    *ow = (unsigned)g_fx_present.out.width; *oh = (unsigned)g_fx_present.out.height;
    *active = 1;
}
