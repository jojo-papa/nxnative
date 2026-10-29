#undef main
#import <Cocoa/Cocoa.h>
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>
#include "../../../dm/ios/Sources/dm_launch_options.h"
#include "../../../dm/ios/Sources/dm_bundle_defaults.h"
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int dm_main(int argc, char **argv);
static void envpath(const char *key, NSString *value) { setenv(key, value.fileSystemRepresentation, 1); }

static BOOL launchSettings(void) {
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    NSArray *keys = @[@"DM_LANG", @"DM_OPMODE", @"DM_METALFX_SPATIAL", @"DM_METALFX_OUTPUT_HEIGHT"];
    NSArray *values = @[@[@"system", @"zh-Hans", @"zh-Hant", @"en-US", @"ja"], @[@"0", @"1"], @[@"0", @"1"], @[@"auto", @"720", @"900", @"1080", @"1440"]];
    NSArray *labels = @[@"Game language", @"Operation mode", @"MetalFX spatial upscaling", @"Output resolution"];
    NSArray *titles = @[@[@"System", @"Simplified Chinese", @"Traditional Chinese", @"English", @"Japanese"], @[@"Handheld", @"Docked"], @[@"Off", @"On"], @[@"Auto (screen)", @"720p", @"900p", @"1080p", @"1440p"]];
    unsigned rows[] = {0, 1, 3, 5};
    NSString *store = @"LaunchSettings.v1";
    NSDictionary *saved = [NSUserDefaults.standardUserDefaults dictionaryForKey:store] ?: @{};
    NSMutableArray<NSPopUpButton *> *controls = [NSMutableArray array];
    NSView *view = [[NSView alloc] initWithFrame:NSMakeRect(0, 0, 410, 170)];
    BOOL supported = ![dm_bundle_defaults()[@"NX_GRAPHICS"] isEqual:@"vulkan"] &&
        [MTLFXSpatialScalerDescriptor supportsMetal4FX:MTLCreateSystemDefaultDevice()];
    for (NSUInteger i = 0; i < keys.count; i++) {
        NSTextField *label = [NSTextField labelWithString:labels[i]];
        label.frame = NSMakeRect(0, 135 - i * 40, 195, 25); [view addSubview:label];
        NSPopUpButton *popup = [[NSPopUpButton alloc] initWithFrame:NSMakeRect(200, 135 - i * 40, 210, 28) pullsDown:NO];
        [popup addItemsWithTitles:titles[i]];
        id savedValue = saved[keys[i]];
        const char *s = [savedValue isKindOfClass:NSString.class] ? [savedValue UTF8String] : NULL;
        const char *env = getenv([keys[i] UTF8String]);
        NSString *choice = @(dm_launch_resolve(rows[i], s, env, dm_bundle_default(keys[i])));
        [popup selectItemAtIndex:[values[i] indexOfObject:choice]];
        if ((i == 2 || i == 3) && !supported) popup.enabled = NO;
        [view addSubview:popup]; [controls addObject:popup];
    }
    NSAlert *alert = [NSAlert new]; alert.messageText = @"Launch settings";
    alert.informativeText = supported ? @"Settings apply before the game starts." : @"Spatial upscaling is unavailable for this renderer or device.";
    alert.accessoryView = view;
    [alert addButtonWithTitle:@"Start Game"]; [alert addButtonWithTitle:@"Cancel"]; [alert addButtonWithTitle:@"Restore Defaults"];
    [NSApp activateIgnoringOtherApps:YES];
    NSModalResponse response;
    while ((response = [alert runModal]) == NSAlertThirdButtonReturn) {
        for (NSUInteger i = 0; i < keys.count; i++) {
            NSString *choice = @(dm_launch_choice(rows[i], NULL, dm_bundle_default(keys[i])));
            [controls[i] selectItemAtIndex:[values[i] indexOfObject:choice]];
        }
    }
    if (response != NSAlertFirstButtonReturn) return NO;
    NSMutableDictionary *choices = [NSMutableDictionary dictionary];
    for (NSUInteger i = 0; i < keys.count; i++) {
        NSString *value = values[i][controls[i].indexOfSelectedItem]; choices[keys[i]] = value;
        if (i == 2 && !supported) value = @"0";
        if (i == 0 && [value isEqual:@"system"]) {
            NSString *tag = NSLocale.preferredLanguages.firstObject ?: @"en-US";
            value = [tag hasPrefix:@"ja"] ? @"ja" : [tag hasPrefix:@"zh"] ?
                (([tag containsString:@"Hant"] || [tag containsString:@"TW"] || [tag containsString:@"HK"] || [tag containsString:@"MO"]) ? @"zh-Hant" : @"zh-Hans") : @"en-US";
        }
        setenv([keys[i] UTF8String], value.UTF8String, 1);
    }
    [NSUserDefaults.standardUserDefaults setObject:choices forKey:store];
    return YES;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        NSBundle *bundle = NSBundle.mainBundle;
        NSString *resources = bundle.resourcePath;
        NSString *root = getenv("DM_ROOT") ? @(getenv("DM_ROOT")) :
            [NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES)[0]
                stringByAppendingPathComponent:bundle.bundleIdentifier ?: @"org.nxnative.game"];
        for (NSString *part in @[@"save", @"temp"]) {
            NSError *error = nil;
            if (![NSFileManager.defaultManager createDirectoryAtPath:[root stringByAppendingPathComponent:part]
                withIntermediateDirectories:YES attributes:nil error:&error]) {
                fprintf(stderr, "Cannot create game data directory: %s\n", error.localizedDescription.UTF8String); return 1;
            }
        }
        envpath("DM_ROOT", root); envpath("DM_SAVE", [root stringByAppendingPathComponent:@"save"]);
        envpath("DM_TEMP", [root stringByAppendingPathComponent:@"temp"]);
        envpath("DM_ROMFS", [resources stringByAppendingPathComponent:@"romfs"]);
        envpath("DM_MSL_DIR", [resources stringByAppendingPathComponent:@"shaders"]);
        envpath("DM_FONT_DIR", [resources stringByAppendingPathComponent:@"font"]);
        envpath("DM_AOC_DIR", [resources stringByAppendingPathComponent:@"aoc"]);
        envpath("DM_NVN_SHMAP", [resources stringByAppendingPathComponent:@"profile/shader_map.tsv"]);
        setenv("DM_WINDOW", "1", 1); setenv("DM_AUDIO", "1", 1);
        if (!launchSettings()) return 0;
        if (!freopen([root stringByAppendingPathComponent:@"log.txt"].fileSystemRepresentation, "w", stdout)) return 1;
        if (dup2(fileno(stdout), fileno(stderr)) < 0 || chdir(root.fileSystemRepresentation)) return 1;
        char *args[] = {argv[0], (char *)[resources stringByAppendingPathComponent:@"patched"].fileSystemRepresentation, NULL};
        return dm_main(2, args);
    }
}
