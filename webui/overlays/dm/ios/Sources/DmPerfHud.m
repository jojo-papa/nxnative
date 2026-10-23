// Built-in performance HUD: presented FPS, game input and presented output size, memory.
// It is created only after the launcher applies DM_PERF_HUD=1 (Game Settings → Performance HUD).
#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>
#import <mach/mach.h>
#import <mach/task_info.h>
#import <os/proc.h>
#include <math.h>
#include <stdlib.h>

uint64_t mtl_present_count(void);
void dm_gfx_hud_sizes(unsigned *in_w, unsigned *in_h, unsigned *out_w, unsigned *out_h, int *active);

@interface DmPerfHud : UIView
@property(nonatomic, strong) UILabel *label;
@end

@implementation DmPerfHud
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        self.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
        self.layer.cornerRadius = 8;
        self.layer.masksToBounds = YES;
        self.userInteractionEnabled = NO;
        _label = [[UILabel alloc] initWithFrame:UIEdgeInsetsInsetRect(self.bounds, UIEdgeInsetsMake(6, 8, 6, 8))];
        _label.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
        _label.numberOfLines = 0;
        _label.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightMedium];
        _label.textColor = UIColor.whiteColor;
        [self addSubview:_label];
    }
    return self;
}
- (void)layoutSubviews {
    [super layoutSubviews];
    self.label.frame = UIEdgeInsetsInsetRect(self.bounds, UIEdgeInsetsMake(6, 8, 6, 8));
}
@end

static DmPerfHud *g_hud;
static uint64_t g_last_present;
static double g_last_time;
static double g_fps;

static UIWindow *dm_hud_window(void) {
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class]) continue;
        for (UIWindow *window in ((UIWindowScene *)scene).windows)
            if (window.isKeyWindow) return window;
    }
    return UIApplication.sharedApplication.windows.firstObject;   // Settings / early launch window
}

static void dm_hud_text(DmPerfHud *hud, UIWindow *window) {
    double now = CACurrentMediaTime();
    uint64_t presents = mtl_present_count();
    if (now - g_last_time >= 0.9) {
        g_fps = (presents - g_last_present) / (now - g_last_time);
        g_last_present = presents;
        g_last_time = now;
    }
    unsigned iw = 0, ih = 0, ow = 0, oh = 0;
    int active = 0;
    dm_gfx_hud_sizes(&iw, &ih, &ow, &oh, &active);

    // Without MetalFX the drawable is the presented output. The game view fits 16:9 inside the screen.
    CGSize bounds = window.bounds.size;
    CGFloat scale = UIScreen.mainScreen.nativeScale;
    CGFloat w = bounds.width, h = bounds.height;
    unsigned screen_w = 0, screen_h = 0;
    if (w > 0 && h > 0) {
        if (w / h > 16.0 / 9.0) w = h * 16.0 / 9.0; else h = w * 9.0 / 16.0;
        screen_w = (unsigned)lround(w * scale);
        screen_h = (unsigned)lround(h * scale);
    }
    unsigned out_w = active ? ow : screen_w, out_h = active ? oh : screen_h;

    task_vm_info_data_t vm;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    uint64_t used = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vm, &count) == KERN_SUCCESS
                    ? (uint64_t)vm.phys_footprint : 0;
    size_t free_bytes = os_proc_available_memory();

    NSMutableString *text = [NSMutableString string];
    [text appendFormat:@"FPS   %.0f\n", g_fps];
    if (iw && ih) [text appendFormat:@"IN    %ux%u\n", iw, ih]; else [text appendString:@"IN    --\n"];
    if (out_w && out_h) [text appendFormat:@"OUT   %ux%u (%s)\n", out_w, out_h, active ? "MetalFX" : "screen"];
    else [text appendString:@"OUT   --\n"];
    if (used) [text appendFormat:@"MEM   %.2f GB used", used / 1073741824.0]; else [text appendString:@"MEM   --"];
    if (free_bytes != (size_t)-1) [text appendFormat:@" / %zu MB free", free_bytes >> 20];
    hud.label.text = text;
}

static void dm_hud_poll(void) {
    const char *setting = getenv("DM_PERF_HUD");
    BOOL on = setting && atoi(setting) != 0;
    UIWindow *window = dm_hud_window();
    if (on && window && !g_hud) {
        g_hud = [[DmPerfHud alloc] initWithFrame:CGRectZero];
        [window addSubview:g_hud];
        g_last_present = mtl_present_count();
        g_last_time = CACurrentMediaTime();
    }
    if (g_hud && (!on || !window)) {
        [g_hud removeFromSuperview];
        g_hud = nil;
    }
    if (g_hud) {
        UIEdgeInsets insets = window.safeAreaInsets;
        g_hud.frame = CGRectMake(insets.left + 8, insets.top + 8, 220, 84);
        dm_hud_text(g_hud, window);
    }
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{ dm_hud_poll(); });
}

__attribute__((constructor)) static void dm_hud_start(void) {
    dispatch_async(dispatch_get_main_queue(), ^{ dm_hud_poll(); });
}
