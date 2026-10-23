#import <UIKit/UIKit.h>

// Launch-only settings. Apply before any guest module or graphics initialization.
UIViewController *dm_launch_settings_controller(void (^start)(void));
void dm_launch_settings_apply(void);
