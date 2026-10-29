// WebUI language is independent of the requested game language. Logs stay verbatim.
const zhMessages = {
"iPhoneOS SDK (iOS packaging)":"iPhoneOS SDK（用于 iOS 打包）","Xcode Metal compiler":"Xcode Metal 编译器",
"Install Python 3.11 or newer and Xcode, then run webui/launchers/start_webui.command or sh webui/launchers/start_webui.sh. Compatible installed .NET 10 SDKs are reused. Without Homebrew, XcodeGen downloads from its official release; zstd and SPIRV-Cross build from verified sources using Xcode. Tools install in the configured tools directory. Xcode and Apple SDKs still require manual setup. macOS supports macOS and iOS packaging.":"安装 Python 3.11 或更新版本及 Xcode，然后运行 webui/launchers/start_webui.command 或 sh webui/launchers/start_webui.sh。已有的兼容 .NET 10 SDK 会直接复用。无需 Homebrew：XcodeGen 使用官方发布包，zstd 和 SPIRV-Cross 使用校验后的源码，由 Xcode 编译。工具安装到配置的工具目录。Xcode 和 Apple SDK 仍需手动安装。macOS 可打包 macOS 和 iOS 应用。","Official download / local build; no Homebrew required":"官方下载 / 本地构建，无需 Homebrew","macOS checks: Xcode SDKs, Metal and native build tools. Windows cross-compilation tools are not required.":"当前检测 macOS 环境：Xcode SDK、Metal 和本机构建工具，不需要 Windows 交叉编译工具。","Windows checks: LLVM/lld, iPhoneOS SDK and Windows Metal tools. macOS builds require a Mac.":"当前检测 Windows 环境：LLVM/lld、iPhoneOS SDK 和 Windows Metal 工具。打包 macOS 应用需要 Mac。","This host is not supported for application builds.":"当前主机不支持构建应用。",".NET 10 SDK is a build-time dependency for the C# extractor and shader tools on both Mac and Windows. Existing compatible SDKs are reused; built apps do not require .NET.":".NET 10 SDK 是 Mac 和 Windows 上 C# 解包器及着色器工具的构建依赖。会复用已有的兼容 SDK，不会重复下载；打包后的应用不需要 .NET。","Provided by the selected Xcode installation. Finish Xcode setup and select its command-line tools.":"由当前选中的 Xcode 提供。请完成 Xcode 首次设置，并选择其命令行工具。",
"Save settings":"保存设置","Settings saved.":"设置已保存。","Installing ":"正在安装 ","Downloading .NET: ":"正在下载 .NET：",
"Install":"一键安装","Manual setup":"需手动安装","Installs through Homebrew":"通过 Homebrew 安装到其软件目录","install":"安装依赖","Install all supported missing dependencies":"一键安装所有可自动安装的缺失依赖","Python package source":"Python 下载源（保存后生效）","Tsinghua mirror (China)":"清华镜像（国内）","Official PyPI":"PyPI 官方源","Windows installation":"Windows 安装方式","macOS installation":"macOS 安装方式","Homebrew installation instructions":"Homebrew 官方安装说明","Python packages use the Tsinghua mirror by default. Automatic installers run locally and keep logs. Apple SDKs require manual setup.":"Python 默认使用清华镜像源。自动安装在本机执行并记录日志，Apple SDK 需要手动配置。","Double-click webui/launchers/start_webui.bat. First launch installs Python inside the project using the Huawei Cloud mirror, with official-source fallback and SHA-256 verification. Python packages use Tsinghua by default. Existing environments are reused; startup output is saved in .webui-data/startup.log. Use this panel to install .NET 10 and build nx_extract. Configure Windows LLVM, SPIRV-Cross, Apple Metal Developer Tools and your iPhoneOS SDK manually. Windows supports iOS packaging only.":"双击 webui/launchers/start_webui.bat。首次启动会从华为云镜像在项目内安装 Python，支持官方源回退并校验 SHA-256；Python 依赖默认使用清华源。已安装环境会直接复用，启动日志保存到 .webui-data/startup.log。可在此面板安装 .NET 10 并构建 nx_extract；Windows LLVM、SPIRV-Cross、Apple Metal Developer Tools 和 iPhoneOS SDK 需手动配置。Windows 仅支持打包 iOS。","Install Python 3.11 or newer and Xcode. Open Xcode once to finish its setup, then double-click webui/launchers/start_webui.command or run sh webui/launchers/start_webui.sh. This panel installs .NET 10 and builds nx_extract. With Homebrew already installed, it can also install xcodegen, zstd and spirv-cross. macOS supports macOS and iOS packaging.":"安装 Python 3.11 或更新版本及 Xcode，首次打开 Xcode 完成组件安装。双击 webui/launchers/start_webui.command，或执行 sh webui/launchers/start_webui.sh。在此面板可安装 .NET 10 并构建 nx_extract。已安装 Homebrew 时，还可一键安装 xcodegen、zstd、spirv-cross。macOS 支持打包 macOS 和 iOS 应用。","Dependency installation complete":"依赖安装完成","Wait for queued tasks before installing dependencies.":"请等待当前任务结束后再安装依赖。","Select missing dependencies that support automatic installation":"请选择缺失且支持自动安装的依赖",
  "BUILD STUDIO": "构建工作台",
  "LOCAL WORKSPACE": "本地工作区",
  "Environment & tools": "环境与工具",
  "YOUR GAMES. YOUR HARDWARE.": "你的游戏，你的设备。",
  "From cartridge to": "从游戏文件到",
  "native.": "原生应用。",
  "Convert your game files or build a standalone Apple app.": "转换游戏文件，或构建独立运行的 Apple 应用。",
  "Everything runs on this computer.": "所有处理均在本机完成。",
  "Checking environment…": "正在检查环境…",
  "Bring your files": "添加游戏文件",
  "Choose NSP, XCI & keys": "选择 NSP、XCI 和密钥文件",
  "Choose NSP, XCI, NSZ & keys": "选择 NSP、XCI、NSZ 和密钥文件",
  "Convert XCI/NSZ to NSP": "XCI/NSZ 转 NSP",
  "Base game, required updates and optional DLC": "游戏本体、所需更新和可选 DLC",
  "Files are stored in your local data folder": "上传文件保存在本地数据目录",
  "Or enter an existing local file path": "或输入已有文件的本地路径",
  "Local file path": "本地文件路径",
  "Import": "导入",
  "Choose your output": "选择输出内容",
  "Task": "任务类型",
  "Build an app": "构建应用",
  "Convert XCI to NSP": "XCI 转 NSP",
  "Inspect game metadata": "检查游戏信息",
  "Game": "游戏",
  "Detect from input": "自动识别",
  "Unsigned .ipa": "未签名 .ipa",
  "Standalone .app.zip": "独立应用 .app.zip",
  "Game language": "游戏语言",
  "System": "跟随系统",
  "Simplified Chinese": "简体中文",
  "Traditional Chinese": "繁体中文",
  "English": "英语",
  "Japanese": "日语",
  "Operation mode": "运行模式",
  "Handheld": "掌机模式",
  "Docked": "主机模式",
  "MetalFX spatial upscaling": "MetalFX 空间超分",
  "On": "开启",
  "Off": "关闭",
  "Upscale output": "超分输出分辨率",
  "Auto (screen)": "自动（屏幕）",
  "These are launch defaults. You can change them in the app before starting a game. Game saves may override language.": "这些设置作为应用的启动默认值，也可在启动游戏前调整。游戏存档中的设置可能覆盖语言选项。",
  "Exact registered game versions are required for application builds.": "构建应用需要与已登记配置匹配的游戏版本。",
  "No profile selected: an unregistered title is surveyed and built with a provisional profile; the app may not boot.": "未选择配置：未登记的游戏会先自动调查并生成临时配置进行构建，生成的 App 可能无法启动。",
  "Keep the task's keys copy for reuse": "保留该任务的密钥副本，以便重试",
  "Keep this task's keys copy for retry": "保留本任务的密钥副本，以便重试",
  "Create task": "创建任务",
  "BUILD JOURNAL": "构建日志",
  "Your tasks": "任务列表",
  "One build at a time · Logs, no database": "串行构建 · 仅使用日志，不使用数据库",
  "No tasks yet. Your next build starts above.": "暂无任务，请在上方创建。",
  "Dependency bundle folder": "依赖工具目录",
  "Windows iPhoneOS SDK": "Windows iPhoneOS SDK 路径",
  "Optional override": "可选，自定义路径",
  "Windows Metal compiler": "Windows Metal 编译器",
  "Path to metal.exe": "metal.exe 的路径",
  "Save paths": "保存路径",
  "Apple tools and SDKs are supplied by you. See webui/docs/webui.md for preparing the offline bundle.": "Apple 工具和 SDK 需自行提供。离线工具包准备方法见 webui/docs/webui.md。",
  "Build log": "构建日志",
  "Close": "关闭",
  "Native execution. Local control.": "原生执行，本地掌控。",
  "Log": "查看日志",
  "Cancel": "取消",
  "Retry": "重试",
  "Delete": "删除",
  "Auto detect": "自动识别",
  "queued": "排队中",
  "running": "运行中",
  "succeeded": "已完成",
  "failed": "失败",
  "cancelled": "已取消",
  "interrupted": "已中断",
  "build": "构建",
  "inspect": "检查",
  "convert": "转换",
  "Waiting": "等待执行",
  "Inspecting package metadata": "正在检查包信息",
  "Extracting code and RomFS manifest": "正在提取代码和 RomFS 清单",
  "Renderer and runtime-capture requirements are checked after extraction.": "解包后会检测图形接口及运行时捕获要求。",
  "Windows requires one shader version matching the package.": "Windows 构建要求着色器版本唯一，并与打包版本一致。",
  "Windows does not support Vulkan builds.": "Windows 暂不支持 Vulkan 构建。",
  "This game needs runtime shader capture on a Mac.": "此游戏需要在 Mac 上捕获运行时着色器。",
  "Application builds require Windows or Apple Silicon macOS.": "应用构建需要 Windows 或 Apple Silicon Mac。",
  "Vulkan game: MetalFX spatial upscaling is unavailable.": "Vulkan 游戏暂不可用 MetalFX 空间超分。",
  "Add exactly one prod.keys file.": "请添加一个 prod.keys 密钥文件。",
  "Select at least one output platform.": "请至少选择一个输出平台。",
  "Delete this task, its copied inputs, cache and outputs? Original imported files remain.": "删除此任务及其输入副本、缓存和输出？通过路径导入的原始文件不会删除。",
  "Tool paths saved.": "工具路径已保存。",
  "Request failed": "请求失败",
  "Add at least one game file": "请至少添加一个游戏文件",
  "Keys upload is incomplete": "密钥文件尚未上传完成",
  "Game input is incomplete": "游戏文件尚未上传完成",
  "Import keys again and create a new task": "请重新导入密钥并创建任务",
  "Task is still active": "任务仍在运行",
  "Wait for tasks before clearing imports": "请等待任务结束后再移除导入文件",
  "Wait for tasks before removing cached inputs": "请等待任务结束后再删除缓存",
  "Wait for queued tasks before changing tools.": "请等待队列中的任务结束后再更改工具路径。",
  "Not enough free space": "磁盘可用空间不足",
  "Choose an existing NSP, XCI or keys file": "请选择已有的 NSP、XCI 或 keys 文件",
  "Expected NSP, XCI or keys": "仅支持 NSP、XCI 或 keys 文件",
  "Open the URL printed by the launcher.": "请打开启动程序输出的完整地址。",
  "Upload not found": "上传记录不存在",
  "missing dependencies": "项依赖缺失",
  "Data folder: ": "数据目录：",
  "Task queued: ": "任务已加入队列：",
  "Remove ": "移除 "
};
Object.assign(zhMessages, {
  "Official instructions": "官方说明",
  "Get / install": "获取 / 安装",
  "Recheck": "重新检测",
  "Environment refreshed.": "环境检测已更新。",
  "Build nx_extract from this repository with webui/tools/prepare_tools.py; it is not a separate vendor download.": "通过本项目的 webui/tools/prepare_tools.py 构建 nx_extract，无需单独下载第三方程序。",
  "Get the .NET 10 SDK for your host and place it in the tools/dotnet folder.": "获取适合当前系统的 .NET 10 SDK，并放入工具目录的 dotnet 子目录。",
  "Get host-compatible LLVM with ARM64 and Mach-O support. Keep bin and lib/clang together under tools/ios-cross/toolchain/windows/iphone.": "获取支持 ARM64 和 Mach-O 的本机 LLVM 工具链，将 bin 与 lib/clang 一并保存在 tools/ios-cross/toolchain/windows/iphone 下。",
  "Get lld from the LLVM toolchain. The Windows build uses its Darwin linker mode.": "从 LLVM 工具链获取 lld。Windows 构建使用其 Darwin 链接模式。",
  "Obtain the iPhoneOS SDK from your Xcode installation, then set its directory below. This project does not distribute Apple SDKs.": "从自行安装的 Xcode 获取 iPhoneOS SDK，并在下方指定目录。本项目不分发 Apple SDK。",
  "Get Apple Metal Developer Tools for Windows, then set the metal.exe path below.": "获取 Apple 官方的 Windows Metal Developer Tools，并在下方填写 metal.exe 路径。",
  "Build SPIRV-Cross with its documented CMake instructions and place spirv-cross.exe in tools/spirv-cross-build.": "按照官方 CMake 说明构建 SPIRV-Cross，将 spirv-cross.exe 放入工具目录的 spirv-cross-build 子目录。",
  "Install SPIRV-Cross and add it to PATH. Follow the repository shader-tool lock requirements.": "安装 SPIRV-Cross 并加入 PATH，同时遵循项目着色器工具版本锁定要求。",
  "Install XcodeGen following its official instructions and add xcodegen to PATH.": "按照官方说明安装 XcodeGen，并将 xcodegen 加入 PATH。",
  "Install Zstandard and add zstd to PATH.": "安装 Zstandard，并将 zstd 加入 PATH。",
  "Install Xcode and its command-line tools on the Mac; check the selected developer directory.": "在 Mac 上安装 Xcode 和命令行工具，并检查当前选择的开发工具目录。",
  "Install lz4 into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.": "在 WebUI 使用的 Python 环境中安装 lz4，或对当前工具目录重新运行 webui/tools/prepare_tools.py。",
  "Install capstone into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.": "在 WebUI 使用的 Python 环境中安装 capstone，或对当前工具目录重新运行 webui/tools/prepare_tools.py。",
  "Install fonttools into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.": "在 WebUI 使用的 Python 环境中安装 fonttools，或对当前工具目录重新运行 webui/tools/prepare_tools.py。",
  "Install Pillow into the WebUI Python environment, or rerun webui/tools/prepare_tools.py for the configured tools folder.": "在 WebUI 使用的 Python 环境中安装 Pillow，或对当前工具目录重新运行 webui/tools/prepare_tools.py。"
});
Object.assign(zhMessages, {
  "SDK search folder": "SDK 搜索目录",
  "Optional additional folder": "可选，指定其他下载或存放目录",
  "Verified portable tools; no administrator access required": "校验后安装到项目内，无需管理员权限",
  "Extracts your downloaded SDK archive locally": "在本地解压用户已下载的 SDK 压缩包",
  "Searches Downloads, project tools and the optional SDK search folder. Requires a complete iPhoneOS SDK version 26.5 or newer.": "自动搜索下载目录、项目工具目录和指定的 SDK 搜索目录。需要完整的 iPhoneOS 26.5 或更新版本 SDK。",
  "Detected iPhoneOS SDKs": "找到的 iPhoneOS SDK",
  "Choose an SDK": "选择 SDK 版本与路径",
  "Extract and configure SDK": "解压并配置 SDK",
  "No complete iPhoneOS SDK found. Finish your download, then click Recheck.": "尚未找到完整的 iPhoneOS SDK。下载完成后点击“重新检测”。",
  "Downloads verified portable LLVM together with lld into the project. Checks real ARM64 Apple compilation before installation. No Visual Studio or administrator access is needed.": "自动下载并校验便携 LLVM 和 lld，安装前实际验证 ARM64 Apple 目标编译。无需 Visual Studio 或管理员权限。",
  "Installed together with clang. Verifies Darwin linking before installation; an existing complete toolchain is reused.": "与 clang 一并安装，安装前验证 Darwin 链接；已有完整工具链会直接复用。",
  "Downloads verified SPIRV-Cross sources and builds with portable LLVM. Installs the C++ compiler automatically if needed; no Visual Studio or CMake is required.": "自动下载并校验 SPIRV-Cross 源码，使用便携 LLVM 编译。缺少 C++ 编译器时自动安装，无需 Visual Studio 或 CMake。",
  "Finds complete iPhoneOS SDKs version 26.5 or newer in Downloads, the project and the configured search folder. Simulator and macOS SDKs are rejected. A discovered SDK archive can be extracted and configured locally. Obtain the SDK from your own Xcode installation.": "搜索下载目录、项目目录和指定目录中的 iPhoneOS 26.5 或更新 SDK，排除模拟器和 macOS SDK。找到压缩包后可一键解压并配置。请从自己的 Xcode 安装中取得 SDK。",
  "Sign in on the Apple website to download and install Metal Developer Tools for Windows. Recheck detects standard installations automatically. For a custom installation, select metal.exe below. Apple login stays in your browser.": "在 Apple 官网登录后下载并安装 Windows Metal Developer Tools，再点击“重新检测”自动识别标准安装目录。自定义安装目录可在下方填写 metal.exe 路径。Apple 登录始终在浏览器内完成。",
  "Double-click webui/launchers/start_webui.bat. First launch installs Python inside the project using the Huawei Cloud mirror, with official-source fallback and SHA-256 verification. Python packages use Tsinghua by default. Existing environments are reused; startup output is saved in .webui-data/startup.log. Use this panel to install .NET 10, nx_extract, clang/lld and SPIRV-Cross automatically. Download Apple tools after signing in on the Apple website. Recheck finds installed Metal tools and complete iPhoneOS SDKs; discovered SDK archives can be extracted locally. Windows supports iOS packaging only.": "双击 webui/launchers/start_webui.bat，首次从华为云镜像在项目内安装 Python，支持官方源回退及 SHA-256 校验；Python 依赖使用清华源，已有环境直接复用。面板可自动安装 .NET 10、nx_extract、clang/lld 和 SPIRV-Cross。Apple 工具在官网登录后下载；重新检测可识别标准目录的 Metal 工具及完整 iPhoneOS SDK，SDK 压缩包可一键解压配置。Windows 仅支持打包 iOS。"
});
Object.assign(zhMessages, {"Python packages use the Tsinghua mirror by default. Automatic installers keep logs. Downloaded iPhoneOS SDKs are detected and can be imported locally.": "Python 依赖默认使用清华镜像。自动安装过程会记录日志，已下载的 iPhoneOS SDK 可自动检测和本地导入。"});
Object.assign(zhMessages, {"With Xcode installed and selected, downloads and installs its Metal Toolchain through the official xcodebuild command. Finish Xcode first-launch setup before installing.": "已安装并选中 Xcode 后，可通过官方 xcodebuild 命令自动下载并安装 Metal Toolchain。请先完成 Xcode 首次启动设置。", "Installs through selected Xcode": "通过当前选中的 Xcode 安装"});
Object.assign(zhMessages, {
  "iPhoneOS SDK source": "iPhoneOS SDK 来源",
  "SDK source": "SDK 来源",
  "xybp888/iOS-SDKs (third-party, verified 26.5)": "xybp888/iOS-SDKs（第三方，已验证 26.5）",
  "Local SDK or archive only": "仅使用本地 SDK 或压缩包",
  "Third-party SDK: xybp888/iOS-SDKs, SHA-256 verified": "第三方 SDK：xybp888/iOS-SDKs，校验 SHA-256",
  "Missing SDKs download from xybp888/iOS-SDKs (third-party), pinned to iPhoneOS 26.5 with SHA-256 verification. Windows links are materialized automatically. Existing valid SDKs are reused; local archives remain supported.": "缺少 SDK 时，从第三方仓库 xybp888/iOS-SDKs 下载固定的 iPhoneOS 26.5 发布包并校验 SHA-256，自动处理 Windows 符号链接兼容性。已有可用 SDK 会直接复用，也支持本地压缩包。",
  "Double-click webui/launchers/start_webui.bat. First launch installs Python inside the project using the Huawei Cloud mirror, with official-source fallback and SHA-256 verification. Python packages use Tsinghua by default. Existing environments are reused; startup output is saved in .webui-data/startup.log. Use this panel to install .NET 10, nx_extract, clang/lld and SPIRV-Cross automatically. Missing iPhoneOS SDKs download from the verified xybp888/iOS-SDKs release. Windows Metal tools still download through Apple after sign-in. Existing SDKs and local archives remain supported. Windows supports iOS packaging only.": "双击 webui/launchers/start_webui.bat。首次从华为云镜像在项目内安装 Python，支持官方源回退和 SHA-256 校验；依赖包使用清华源，已有环境直接复用。面板可自动安装 .NET 10、nx_extract、clang/lld 和 SPIRV-Cross；缺少 iPhoneOS SDK 时从已验证的 xybp888/iOS-SDKs 发布包下载。Windows Metal 工具仍需登录 Apple 官网下载。支持已有 SDK 和本地压缩包，Windows 仅支持打包 iOS。"
});
Object.assign(zhMessages, {"Windows Metal tools come from Apple; choose the iPhoneOS SDK source above. See webui/docs/webui.md for offline bundles.": "Windows Metal 工具通过 Apple 获取，iPhoneOS SDK 可在上方选择下载来源。离线工具包说明见 webui/docs/webui.md。"});
Object.assign(zhMessages, {"Local mode: discovers existing iPhoneOS SDKs and imports local archives. Automatic SDK network downloads are disabled.": "本地模式：检测已有 iPhoneOS SDK 并导入本地压缩包，不会自动联网下载 SDK。"});
Object.assign(zhMessages, {
  "Separate IPA and RomFS (iOS only)": "IPA 与 RomFS 分开打包（仅 iOS）",
  "Install the IPA first. In the Files app, unzip the RomFS archive and move its top-level romfs folder into this app's Documents folder (Documents/romfs). macOS .app.zip builds always include their RomFS.": "请先安装 IPA。在“文件”App 中解压 RomFS 压缩包，把其中的顶层 romfs 文件夹移动到本应用的 Documents 文件夹（Documents/romfs）。macOS .app.zip 始终自带 RomFS。",
  "RomFS archive": "RomFS 压缩包",
  "Invalid RomFS packaging selection": "无效的 RomFS 打包选项",
  "Separate RomFS is only available for application builds": "只有应用打包任务可以分离 RomFS",
  "Separate RomFS requires an iOS target": "分离 RomFS 需要选择 iOS 目标",
  "macOS packaging requires a Mac.": "打包 macOS 应用需要 Mac。"
});
Object.assign(zhMessages, {
  "iPhoneOS SDK version": "iPhoneOS SDK 版本",
  "Download selected iPhoneOS SDK": "下载所选 iPhoneOS SDK",
  "Select a version to download with SHA-256 verification. Automatic uses an installed SDK.": "选择版本后按 SHA-256 校验下载；自动模式使用已安装的 SDK。",
  "Automatic (installed SDK)": "自动（使用已安装 SDK）",
  "Unsupported iPhoneOS SDK version": "不支持的 iPhoneOS SDK 版本",
  "xybp888/iOS-SDKs (third-party, SHA-256 verified)": "xybp888/iOS-SDKs（第三方，SHA-256 校验）",
  "Clear build cache": "清空构建缓存",
  "Deletes staging trees, shared shader caches and per-task intermediate files. Finished outputs, logs and uploads stay. Wait for running tasks to finish.": "删除暂存目录、共享着色器缓存和各任务的中间文件；已完成的输出、日志和上传文件会保留。请等待运行中的任务结束后再操作。",
  "Delete staging trees, shader caches and per-task intermediate files? Finished outputs and logs are kept.": "删除暂存目录、着色器缓存和各任务中间文件？已完成的输出和日志会保留。",
  "Build cache cleared.": "构建缓存已清空。",
  "NSZ decompressor": "NSZ 解压组件",
  "The MIT-licensed nsz package decompresses .nsz uploads to NSP. Install it here or let the WebUI install it at startup.": "MIT 许可的 nsz 包用于将 .nsz 上传文件解压为 NSP。可在此安装，WebUI 启动时也会自动安装。",
  "Uploading": "正在上传",
  "Uploaded": "已上传",
  "Upload failed": "上传失败",
  "Previously uploaded files": "以前上传的文件",
  "Add": "添加",
  "Added": "已添加",
  "imported": "本地导入",
  "Delete this stored upload? Existing task caches may keep a copy, but a retry may need it.": "删除这个已保存的上传文件？已有任务缓存可能仍保留副本，但之后的重试可能需要它。",
  "Output folder": "输出文件夹",
  "Optional; finished files are copied here": "可选；完成的文件会复制到这里",
  "Finished builds and converted NSPs are also copied here. Leave empty to keep them only in the task data folder.": "完成的构建产物和转换后的 NSP 也会复制到这里；留空则只保留在任务数据目录中。",
  "Wait for tasks before clearing caches": "请等待任务结束后再清空缓存",
  "Choose an iPhoneOS SDK version (26.5 or newer); missing SDKs download from xybp888/iOS-SDKs (third-party) with SHA-256 verification. Windows links are materialized automatically. Existing valid SDKs are reused; local archives remain supported.": "选择 iPhoneOS SDK 版本（26.5 或更新）；缺少的 SDK 将从第三方仓库 xybp888/iOS-SDKs 下载并校验 SHA-256，自动处理 Windows 符号链接兼容性。已有可用 SDK 会直接复用，也支持本地压缩包。"
});
let uiLanguage = localStorage.getItem('nx-ui-language') || (navigator.language.startsWith('zh') ? 'zh-CN' : 'en');
if (!['zh-CN', 'en'].includes(uiLanguage)) uiLanguage = 'en';
function t(text) {
  text = String(text ?? '');
  if (uiLanguage !== 'zh-CN') return text;
  if (Object.hasOwn(zhMessages, text)) return zhMessages[text];
  for (const prefix of ['Data folder: ', 'Task queued: ', 'Remove ', 'Installing ', 'Downloading .NET: '])
    if (text.startsWith(prefix)) return zhMessages[prefix] + text.slice(prefix.length);
  return text;
}
const originalText = new WeakMap(), originalAttributes = new WeakMap();
function translateStatic(root = document.body) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.parentElement.closest('pre,script,style,#ui-language,#inputs,.downloads,#message,.task-title,.task-stage,#host,#data-folder')) continue;
    const source = originalText.get(node) ?? node.textContent;
    originalText.set(node, source);
    node.textContent = source.replace(/\S[\s\S]*\S|\S/, value => t(value));
  }
  for (const element of root.querySelectorAll('[placeholder],[aria-label]')) {
    if (element.closest('#inputs')) continue;
    const source = originalAttributes.get(element) || Object.fromEntries(['placeholder','aria-label'].filter(k => element.hasAttribute(k)).map(k => [k, element.getAttribute(k)]));
    originalAttributes.set(element, source);
    for (const [key, value] of Object.entries(source)) element.setAttribute(key, t(value));
  }
  document.documentElement.lang = uiLanguage;
  document.title = uiLanguage === 'zh-CN' ? 'nxnative · 构建工作台' : 'nxnative · Build studio';
}
