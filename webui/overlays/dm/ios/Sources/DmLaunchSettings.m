#import "DmLaunchSettings.h"
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>
#include "game_profile.h"
#include "dm_launch_options.h"
#include "dm_bundle_defaults.h"
#include <stdio.h>
#include <stdlib.h>

static NSArray<NSString *> *keys(void) {
    return @[@"language", @"mode", @"dynamicResolution", @"spatial", @"interpolation", @"spatialOutputHeight", @"performanceHUD", @"debugTextureBindings"];
}
static NSArray<NSArray<NSString *> *> *values(void) {
    return @[@[@"system", @"zh-Hans", @"zh-Hant", @"en-US", @"ja"],
             @[@"0", @"1"], @[@"0", @"1"], @[@"0", @"1"], @[@"0", @"1"],
             @[@"auto", @"720", @"900", @"1080", @"1440"], @[@"0", @"1"], @[@"0", @"1"]];
}
static NSArray<NSString *> *envKeys(void) {
    return @[@"DM_LANG", @"DM_OPMODE", @"DM_DYNAMIC_RESOLUTION", @"DM_METALFX_SPATIAL", @"DM_METALFX_INTERPOLATION", @"DM_METALFX_OUTPUT_HEIGHT", @"DM_PERF_HUD", @"DM_NVN_DRAW_TEXTURES"];
}
static NSString *storeKey(void) { return [@"LaunchSettings.v1." stringByAppendingString:@DM_GAME_ID]; }
static NSString *choice(NSUInteger row) {
    id saved = [NSUserDefaults.standardUserDefaults dictionaryForKey:storeKey()][keys()[row]];
    const char *s = [saved isKindOfClass:NSString.class] ? [saved UTF8String] : NULL;
    const char *env = getenv(envKeys()[row].UTF8String);
    return @(dm_launch_resolve((unsigned)row, s, env, dm_bundle_default(envKeys()[row])));
}
static void saveChoice(NSUInteger row, NSString *value) {
    NSMutableDictionary *d = [[NSUserDefaults.standardUserDefaults dictionaryForKey:storeKey()] mutableCopy] ?: [NSMutableDictionary dictionary];
    d[keys()[row]] = value;
    [NSUserDefaults.standardUserDefaults setObject:d forKey:storeKey()];
    fprintf(stderr,"settings: saved %s=%s readback=%s\n",keys()[row].UTF8String,value.UTF8String,choice(row).UTF8String);
}
static BOOL spatialSupported(void) {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    return device && [MTLFXSpatialScalerDescriptor supportsMetal4FX:device];
}
// These require build-specific render data. Never claim support based solely
// on the GPU's MetalFX feature bits, or turn a display resize into a render scale.
static NSString *unavailable(NSUInteger row) {
    if (row == 3 && [dm_bundle_defaults()[@"NX_GRAPHICS"] isEqual:@"vulkan"])
        return @"Spatial upscaling is not available for the Vulkan renderer.";
    if (row == 4 && [dm_bundle_defaults()[@"NX_WEBUI_RELEASE"] isEqual:@"1"])
        return @"Frame generation is not enabled in this build.";
    if (row == 2) return @"Dynamic resolution control has not been validated for this game build. The game's original behavior remains active.";
    if (row == 3 && !spatialSupported()) return @"MetalFX spatial scaling is unavailable on this device.";
    if (row == 4) return @"Frame generation is not enabled in this build.";
    return nil;
}
static NSString *systemLanguage(void) {
    NSString *tag = NSLocale.preferredLanguages.firstObject ?: @"en-US";
    if ([tag hasPrefix:@"zh"] || [tag hasPrefix:@"yue"]) {
        BOOL traditional = [tag containsString:@"Hant"] || [tag containsString:@"TW"] || [tag containsString:@"HK"] || [tag containsString:@"MO"];
        return traditional ? @"zh-Hant" : @"zh-Hans";
    }
    return [tag hasPrefix:@"ja"] ? @"ja" : @"en-US";
}
void dm_launch_settings_apply(void) {
    for (NSNumber *row in @[@0, @1, @3, @5, @6]) {
        NSUInteger i = row.unsignedIntegerValue;
        NSString *requested = choice(i), *effective = requested;
        NSString *reason = unavailable(i);
        if (reason) effective = i == 2 ? @"1" : @"0";
        if (i == 0 && [effective isEqualToString:@"system"]) effective = systemLanguage();
        setenv(envKeys()[i].UTF8String, effective.UTF8String, 1);
        if(i==4)setenv("DM_METALFX_PRESENT",effective.UTF8String,1);
        fprintf(stderr, "settings: %s requested=%s effective=%s%s%s\n", keys()[i].UTF8String,
                requested.UTF8String, effective.UTF8String, reason ? " reason=" : "", reason.UTF8String ?: "");
    }
    setenv("DM_LAUNCHER", "0", 1);   // the fork's ObjC settings screen is the launcher; keep the upstream Swift launcher out of the way
    if (getenv("DM_PERF_HUD") && atoi(getenv("DM_PERF_HUD"))) setenv("DM_SHOW_FPS", "0", 1);   // the HUD already shows FPS
    setenv("DM_DYNAMIC_RESOLUTION", "1", 1);
    setenv("DM_METALFX_INTERPOLATION", "0", 1);
    fprintf(stderr, "settings: game=%s iOS=%s\n", DM_GAME_ID, UIDevice.currentDevice.systemVersion.UTF8String);
}

@interface DmLaunchSettings : UITableViewController
@property(copy) void (^start)(void);
@property BOOL started;
@end
@implementation DmLaunchSettings
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"Game Settings";
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"Start Game" style:UIBarButtonItemStyleDone target:self action:@selector(startGame)];
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"Restore Defaults" style:UIBarButtonItemStylePlain target:self action:@selector(resetSettings)];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)table { return 1; }
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section { return 5; }
- (NSString *)tableView:(UITableView *)table titleForFooterInSection:(NSInteger)section {
    return @"Settings are saved per game and applied at launch. Restart the app to change them. Performance HUD shows FPS, input/output resolution and memory use. Unknown scene sizes show --. Debug Texture Bindings records every encoded game draw's bindings to draw-textures.tsv and draw-textures.prev.tsv (about 64 MiB combined, rolling). Debug logging reduces performance; leave it off for FPS comparisons. Frame Generation is experimental; iPhone display and stability are not yet verified. Local image distortion may occur. Upscale Target Resolution controls MetalFX output only. Auto follows the screen. A target at or below the input size skips upscaling. Game language also depends on supported languages and save settings.";
}
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    NSUInteger i = ((NSUInteger[]){0, 1, 3, 5, 6})[path.row];
    cell.textLabel.text = @[@"Game Language", @"Operation Mode", @"Dynamic Resolution", @"MetalFX Spatial Upscaling", @"MetalFX Frame Generation (Experimental)", @"Upscale Target Resolution", @"Performance HUD", @"Debug Texture Bindings"][i];
    NSArray *names = @[@[@"System", @"Simplified Chinese", @"Traditional Chinese", @"English", @"Japanese"],
                       @[@"Handheld", @"Docked"], @[@"Off", @"On"], @[@"Off", @"On"], @[@"Off", @"On"],
                       @[@"Auto (Screen)", @"720p", @"900p", @"1080p", @"1440p"], @[@"Off", @"On"], @[@"Off", @"On"]];
    NSString *reason = unavailable(i);
    cell.detailTextLabel.text = reason ?: names[i][[values()[i] indexOfObject:choice(i)]];
    cell.detailTextLabel.numberOfLines = 0;
    cell.accessoryType = reason ? UITableViewCellAccessoryNone : UITableViewCellAccessoryDisclosureIndicator;
    cell.selectionStyle = reason ? UITableViewCellSelectionStyleNone : UITableViewCellSelectionStyleDefault;
    if(i==3 || i==4 || i==6 || i==7) {
        UISwitch *toggle=[UISwitch new];toggle.tag=(NSInteger)i;
        toggle.on=!reason && [choice(i) isEqualToString:@"1"];toggle.enabled=reason==nil;
        toggle.accessibilityLabel=cell.textLabel.text;
        [toggle addTarget:self action:@selector(toggleChanged:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView=toggle;cell.selectionStyle=UITableViewCellSelectionStyleNone;
    }
    return cell;
}
- (void)toggleChanged:(UISwitch *)toggle {
    NSUInteger row=(NSUInteger)toggle.tag;if(unavailable(row))return;
    saveChoice(row,toggle.on?@"1":@"0");[self.tableView reloadData];
}
- (void)tableView:(UITableView *)table didSelectRowAtIndexPath:(NSIndexPath *)path {
    [table deselectRowAtIndexPath:path animated:YES];
    NSUInteger i = ((NSUInteger[]){0, 1, 3, 5, 6})[path.row]; if (unavailable(i)) return;
    if(i==3 || i==4 || i==6 || i==7)return;
    NSArray *names = @[@[@"System", @"Simplified Chinese", @"Traditional Chinese", @"English", @"Japanese"],
                       @[@"Handheld", @"Docked"], @[@"Off", @"On"], @[@"Off", @"On"], @[@"Off", @"On"],
                       @[@"Auto (Screen)", @"720p", @"900p", @"1080p", @"1440p"], @[@"Off", @"On"], @[@"Off", @"On"]];
    UIAlertController *a = [UIAlertController alertControllerWithTitle:[table cellForRowAtIndexPath:path].textLabel.text message:nil preferredStyle:UIAlertControllerStyleAlert];
    for (NSUInteger j = 0; j < values()[i].count; j++) {
        [a addAction:[UIAlertAction actionWithTitle:names[i][j] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            saveChoice(i, values()[i][j]); [self.tableView reloadData];
        }]];
    }
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [self presentViewController:a animated:YES completion:nil];
}
- (void)resetSettings {
    for (NSUInteger i = 0; i < keys().count; i++) saveChoice(i, @(dm_launch_choice((unsigned)i, NULL, dm_bundle_default(envKeys()[i]))));
    [self.tableView reloadData];
}
- (void)startGame {
    if (self.started) return;
    self.started = YES; self.navigationItem.rightBarButtonItem.enabled = NO;
    dm_launch_settings_apply(); self.start();
}
- (UIInterfaceOrientationMask)supportedInterfaceOrientations { return UIInterfaceOrientationMaskLandscape; }
@end
UIViewController *dm_launch_settings_controller(void (^start)(void)) {
    DmLaunchSettings *vc = [[DmLaunchSettings alloc] initWithStyle:UITableViewStyleInsetGrouped];
    vc.start = start;
    return [[UINavigationController alloc] initWithRootViewController:vc];
}
