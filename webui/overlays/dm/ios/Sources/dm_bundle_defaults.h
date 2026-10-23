#pragma once
// Foundation-only defaults shared by the UIKit and AppKit launch settings.
#import <Foundation/Foundation.h>
static inline NSDictionary *dm_bundle_defaults(void) {
    static NSDictionary *defaults;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSString *path = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"launch-defaults.json"];
        NSData *data = [NSData dataWithContentsOfFile:path];
        id value = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        defaults = [value isKindOfClass:NSDictionary.class] ? value : @{};
    });
    return defaults;
}
static inline const char *dm_bundle_default(NSString *key) {
    id value = dm_bundle_defaults()[key];
    return [value isKindOfClass:NSString.class] ? [value UTF8String] : NULL;
}
