// MetalFX presentation resources. A commit feedback block retains each packet
// until GPU completion, including when a resize or memory warning evicts it.
#import <MetalFX/MetalFX.h>
#import <MetalFX/MTL4FXSpatialScaler.h>

// Last present sizes and whether MetalFX was used, read by the in-app performance HUD.
static _Atomic unsigned g_hud_in_w, g_hud_in_h, g_hud_out_w, g_hud_out_h;
static _Atomic int g_hud_active;
void dm_gfx_hud_sizes(unsigned *iw, unsigned *ih, unsigned *ow, unsigned *oh, int *active) {
    *iw = atomic_load(&g_hud_in_w); *ih = atomic_load(&g_hud_in_h);
    *ow = atomic_load(&g_hud_out_w); *oh = atomic_load(&g_hud_out_h);
    *active = atomic_load(&g_hud_active);
}

@interface NvSpatial : NSObject {
@public
    id<MTL4FXSpatialScaler> scaler;
    id<MTLTexture> input, output;
    id<MTLFence> fence;
    id<MTLResidencySet> residency;
    id<MTL4CommandQueue> queue;
    _Atomic int busy;
}
@end
@implementation NvSpatial
- (void)dealloc { if (residency && queue) [queue removeResidencySet:residency]; }
@end
static NvSpatial *g_spatial[3];
static _Atomic int g_memory_pressure;
void dm_gfx_spatial_trim(void) {
    @synchronized (NvSpatial.class) {
        for (int i = 0; i < 3; i++) g_spatial[i] = nil;
        atomic_store(&g_hud_active, 0);
    }
}
void dm_gfx_memory_pressure(void) {
    if (atomic_exchange(&g_memory_pressure, 1)) return;
    dm_gfx_spatial_trim();
    MLOG("Memory pressure: disabling spatial scaling and releasing its resources after GPU completion");
}
static int optional_memory_ok(void) {
    if (atomic_load(&g_memory_pressure)) return 0;
#if TARGET_OS_IPHONE
    // Leave room for streaming and compilation. This is a headroom threshold,
    // not a limit on guest memory or a sum of overlapping GPU/CPU accounting.
    if (os_proc_available_memory() < (512ull << 20)) {
        dm_gfx_memory_pressure(); return 0;
    }
#endif
    return 1;
}
static NvSpatial *spatial_prepare(int slot, NSUInteger w, NSUInteger h, NSUInteger ow, NSUInteger oh) {
  @synchronized (NvSpatial.class) {
    atomic_store(&g_hud_in_w, (unsigned)w); atomic_store(&g_hud_in_h, (unsigned)h);
    atomic_store(&g_hud_out_w, (unsigned)ow); atomic_store(&g_hud_out_h, (unsigned)oh);
    atomic_store(&g_hud_active, 0);
    static int enabled = -1;
    if (enabled < 0) { const char *e = getenv("DM_METALFX_SPATIAL"); enabled = e && !strcmp(e, "1"); }
    if (!enabled) return nil;
    if (!optional_memory_ok()) { dm_gfx_spatial_trim(); return nil; }
    if (!w || !h || ow <= w || oh <= h || fabs((double)w / h - (double)ow / oh) > 0.02) return nil;
    NvSpatial *p = g_spatial[slot];
    if (p && atomic_load(&p->busy)) return nil;
    if (p && p->input.width == w && p->input.height == h && p->output.width == ow && p->output.height == oh) {
        atomic_store(&g_hud_active, 1); return p;
    }
    if (![MTLFXSpatialScalerDescriptor supportsMetal4FX:g_dev]) {
        MLOG("MetalFX spatial: unsupported; using ordinary scaling"); enabled = 0; return nil;
    }
    p = [NvSpatial new];
    NSError *err = nil;
    id<MTL4Compiler> compiler = [g_dev newCompilerWithDescriptor:[MTL4CompilerDescriptor new] error:&err];
    MTLFXSpatialScalerDescriptor *d = [MTLFXSpatialScalerDescriptor new];
    d.inputWidth = w; d.inputHeight = h; d.outputWidth = ow; d.outputHeight = oh;
    d.colorTextureFormat = d.outputTextureFormat = MTLPixelFormatBGRA8Unorm;
    d.colorProcessingMode = MTLFXSpatialScalerColorProcessingModePerceptual;
    if (compiler) p->scaler = [d newSpatialScalerWithDevice:g_dev compiler:compiler];
    if (!p->scaler) { MLOG("MetalFX spatial: creation failed; using ordinary scaling"); enabled = 0; return nil; }
    MTLTextureDescriptor *td = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:d.colorTextureFormat width:w height:h mipmapped:NO];
    td.storageMode = MTLStorageModePrivate;
    td.usage = p->scaler.colorTextureUsage | MTLTextureUsageRenderTarget;
    p->input = [g_dev newTextureWithDescriptor:td];
    td.width = ow; td.height = oh; td.usage = p->scaler.outputTextureUsage | MTLTextureUsageShaderRead;
    p->output = [g_dev newTextureWithDescriptor:td];
    p->fence = [g_dev newFence];
    p->residency = [g_dev newResidencySetWithDescriptor:[MTLResidencySetDescriptor new] error:&err];
    if (!p->input || !p->output || !p->fence || !p->residency) {
        MLOG("MetalFX spatial: resource allocation failed; using ordinary scaling"); enabled = 0; return nil;
    }
    [p->residency addAllocation:p->input]; [p->residency addAllocation:p->output]; [p->residency commit];
    p->queue = g_q4; [p->queue addResidencySet:p->residency];
    p->scaler.colorTexture = p->input; p->scaler.outputTexture = p->output;
    p->scaler.inputContentWidth = w; p->scaler.inputContentHeight = h; p->scaler.fence = p->fence;
    g_spatial[slot] = p;
    atomic_store(&g_hud_active, 1);
    MLOG("MetalFX spatial: %lux%lu -> %lux%lu (slot %d)", (unsigned long)w, (unsigned long)h, (unsigned long)ow, (unsigned long)oh, slot);
    return p;
  }
}
