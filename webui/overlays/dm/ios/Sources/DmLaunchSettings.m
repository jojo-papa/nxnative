#import "DmLaunchSettings.h"
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>
#import "game_profile.h"
#import "dm_launch_options.h"
#import "dm_bundle_defaults.h"
#import <stdio.h>
#import <stdlib.h>

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
        return @"Vulkan 渲染器不支持空间放大。";
    if (row == 4 && [dm_bundle_defaults()[@"NX_WEBUI_RELEASE"] isEqual:@"1"])
        return @"此版本未启用帧生成。";
    if (row == 2) return @"动态分辨率控制尚未在此游戏上验证，游戏保持原本的行为。";
    if (row == 3 && !spatialSupported()) return @"此设备不支持 MetalFX 空间放大。";
    if (row == 4) return @"此版本未启用帧生成。";
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

// The names the settings are shown with (the values themselves are stored in English)
static NSArray<NSArray<NSString *> *> *displayNames(void) {
    return @[@[@"跟随系统", @"简体中文", @"繁体中文", @"英文", @"日文"],
             @[@"掌机", @"主机"], @[@"关", @"开"], @[@"关", @"开"], @[@"关", @"开"],
             @[@"自动（屏幕）", @"720p", @"900p", @"1080p", @"1440p"], @[@"关", @"开"], @[@"关", @"开"]];
}
static NSArray<NSString *> *rowLabels(void) {
    return @[@"游戏语言", @"运行模式", @"动态分辨率", @"MetalFX 空间放大", @"MetalFX 帧生成（实验性）",
             @"放大目标分辨率", @"性能信息", @"调试贴图绑定"];
}

// ===== The player's own picture for the bars around the game =====
// The chrome (front_ios.m) shows Documents/frame.png in the bars; the files app can put one there as
// well, this screen can pick one from the photo library. The picture is scaled down to 2048 pixels
// (the bars are small; a full-size photo would only take space in the app's container).
static NSString *background_path(void) {
    NSString *doc = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    return [doc stringByAppendingPathComponent:@"frame.png"];
}
static BOOL background_set(void) {
    return [[NSFileManager defaultManager] fileExistsAtPath:background_path()];
}
static void background_write(UIImage *im) {
    CGSize sz = im.size;
    CGFloat s = MAX(sz.width, sz.height);
    if (s > 2048) { CGFloat k = 2048.0 / s; sz = CGSizeMake(round(sz.width * k), round(sz.height * k)); }
    UIGraphicsImageRenderer *r = [[UIGraphicsImageRenderer alloc] initWithSize:sz];
    UIImage *small = [r imageWithActions:^(UIGraphicsImageRendererContext *c) { (void)c; [im drawInRect:CGRectMake(0, 0, sz.width, sz.height)]; }];
    NSData *png = UIImagePNGRepresentation(small);
    if (png) [png writeToFile:background_path() atomically:YES];
}

@interface DmLaunchSettings : UITableViewController <UIImagePickerControllerDelegate, UINavigationControllerDelegate>
@property(copy) void (^start)(void);
@property BOOL started;
@end
@implementation DmLaunchSettings
- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"游戏设置";
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"开始游戏" style:UIBarButtonItemStyleDone target:self action:@selector(startGame)];
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"恢复默认" style:UIBarButtonItemStylePlain target:self action:@selector(resetSettings)];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)table { return 2; }
- (NSInteger)tableView:(UITableView *)table numberOfRowsInSection:(NSInteger)section { return section == 0 ? 5 : 1; }
- (NSString *)tableView:(UITableView *)table titleForFooterInSection:(NSInteger)section {
    if (section != 0) return nil;
    return @"设置按游戏保存，启动时生效，改完要重启这个 App。「性能信息」显示 FPS、输入/输出分辨率和内存占用。调试贴图绑定会把每次绘制的贴图绑定记录到 draw-textures.tsv（两份合计约 64 MiB，滚动覆盖），调试记录会拖慢性能，比帧率时请关掉。帧生成还是实验功能，iPhone 上的显示与稳定性尚未验证，画面可能轻微变形。放大目标分辨率只影响 MetalFX 的输出，自动模式跟随屏幕，目标低于输入尺寸时不放大。游戏语言还取决于游戏本身支持的语言和存档里的设置。";
}
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)path {
    if (path.section == 1) {   // the picture for the bars around the game
        UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleValue1 reuseIdentifier:nil];
        cell.textLabel.text = @"背景图片";
        cell.detailTextLabel.text = background_set() ? @"已设置" : @"默认渐变";
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
        return cell;
    }
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    NSUInteger i = ((NSUInteger[]){0, 1, 3, 5, 6})[path.row];
    cell.textLabel.text = rowLabels()[i];
    NSArray *names = displayNames();
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
    if (path.section == 1) { [self pickBackground]; return; }
    NSUInteger i = ((NSUInteger[]){0, 1, 3, 5, 6})[path.row]; if (unavailable(i)) return;
    if(i==3 || i==4 || i==6 || i==7)return;
    NSArray *names = displayNames();
    UIAlertController *a = [UIAlertController alertControllerWithTitle:[table cellForRowAtIndexPath:path].textLabel.text message:nil preferredStyle:UIAlertControllerStyleAlert];
    for (NSUInteger j = 0; j < values()[i].count; j++) {
        [a addAction:[UIAlertAction actionWithTitle:names[i][j] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            saveChoice(i, values()[i][j]); [self.tableView reloadData];
        }]];
    }
    [a addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [self presentViewController:a animated:YES completion:nil];
}
// The picture for the bars: from the photo library, or back to the plain gradient.
- (void)pickBackground {
    UIAlertController *a = [UIAlertController alertControllerWithTitle:@"背景图片" message:@"游戏画面四周的黑边可以放一张自己的图" preferredStyle:UIAlertControllerStyleActionSheet];
    __weak DmLaunchSettings *weakSelf = self;
    [a addAction:[UIAlertAction actionWithTitle:@"从相册选择" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        if (![UIImagePickerController isSourceTypeAvailable:UIImagePickerControllerSourceTypePhotoLibrary]) return;
        UIImagePickerController *p = [UIImagePickerController new];
        p.sourceType = UIImagePickerControllerSourceTypePhotoLibrary;
        p.delegate = weakSelf;
        p.modalPresentationStyle = UIModalPresentationFullScreen;   // on the iPad a picker has to be a popover with an anchor; full screen is simpler
        [weakSelf presentViewController:p animated:YES completion:nil];
    }]];
    if (background_set())
        [a addAction:[UIAlertAction actionWithTitle:@"恢复默认渐变" style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
            [[NSFileManager defaultManager] removeItemAtPath:background_path() error:nil];
            [weakSelf.tableView reloadData];
        }]];
    [a addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    a.popoverPresentationController.sourceView = self.view;   // an action sheet needs a source on the iPad
    a.popoverPresentationController.sourceRect = CGRectMake(CGRectGetMidX(self.view.bounds), CGRectGetMaxY(self.view.bounds) - 40, 1, 1);
    [self presentViewController:a animated:YES completion:nil];
}
- (void)imagePickerController:(UIImagePickerController *)picker didFinishPickingMediaWithInfo:(NSDictionary<UIImagePickerControllerInfoKey,id> *)info {
    UIImage *im = info[UIImagePickerControllerOriginalImage];
    [picker dismissViewControllerAnimated:YES completion:nil];
    if (!im) return;
    background_write(im);
    [self.tableView reloadData];
}
- (void)imagePickerControllerDidCancel:(UIImagePickerController *)picker {
    [picker dismissViewControllerAnimated:YES completion:nil];
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
