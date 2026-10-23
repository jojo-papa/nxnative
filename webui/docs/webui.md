# Local build studio

The WebUI uploads NSP/XCI/NSZ files and keys, inspects content metadata, converts standard XCI files to NSP, decompresses NSZ files to NSP, and queues native Apple application builds. It runs on `127.0.0.1` with a per-launch browser session. No SQLite, database server, Node build, or queue service is used.

## Start

Windows installs its own Python on first launch; macOS requires Python 3.11 or newer. Run `./start-webui.sh` from the repository root on macOS (or double-click `start-webui.command`), `start-webui.bat` on Windows, or:

```sh
python3 webui/launchers/start_webui.py
```

Startup does not ask for a data path. It defaults to `.webui-data/` inside the repository (ignored by Git), including uploads, keys, tasks, caches and a local Python environment. Existing compatible Python dependencies are reused without running pip. Missing or incompatible dependencies are automatically installed into `.webui-data/venv`; a completed environment is reused on later launches. The system Python environment is not modified. On Windows, the BAT launcher downloads Python 3.13.16 into `.webui-data/runtime` on first launch and reuses it afterward. The official CPython NuGet archive includes pip, venv and its license; no global Python installation, PATH changes or administrator rights are required. First-time runtime and dependency setup needs network access. macOS still requires an existing Python 3.11 or newer.

You may still override the location with `--data-dir` or `NX_DATA_DIR`, including a repository sibling under your home folder. `--tools` selects an existing prepared tools folder. Dependencies and caches follow the chosen data directory.

Open the URL printed by the launcher. The token is exchanged for a local session cookie and removed from the address bar. The service rejects foreign origins and non-loopback hosts. It is a local, single-user tool; do not expose it through a proxy or a public interface. Only one process may use a given data folder.

`start-webui.bat`, `start-webui.sh` and `start-webui.command` are launch shortcuts (the internal launchers are under `webui/launchers/`). Set `NX_TOOLS_DIR` to use an external prepared tools folder. Windows always uses the project-local runtime; the Mac launcher uses the optional `runtime/bin/python3` in that tools folder or system Python. In Spyder, edit the settings at the top of `start_webui.py` and press F5.

## Tools and platforms

Open **Environment & tools** to configure the tools directory and, on Windows, the Apple SDK and Metal compiler paths. Dependency checks report missing files and Python packages. Each check links to the official download or installation instructions; missing entries also show the expected path and a localized setup hint. Missing supported dependencies have an **Install** button; **Install all supported missing dependencies** queues them together. Installation uses the existing serial task queue, `events.jsonl` and `build.log`; view progress, cancel or retry like other tasks. Completed installations trigger a fresh check. Already present dependencies are skipped. Manual entries keep their official instructions. Offline bundle preparation remains available:

```sh
python webui/tools/prepare_tools.py --out /path/to/external/tools --source-tools /path/to/existing/tools
```

The preparer installs Python dependencies, builds the LibHac extractor, and writes package/license metadata and file SHA-256 hashes. `--wheelhouse` supports offline Python installation; `--python-runtime` includes a separately supplied redistributable Python runtime with its license. Supply a .NET 10 SDK. The preparer does not download or redistribute Apple SDKs, Metal tools, game files, fonts, or keys. Keep third-party tool licenses with a redistributed bundle.

| Host | iOS output | macOS output |
| --- | --- | --- |
| Apple Silicon macOS with the repository's build dependencies | Unsigned IPA | Standalone app ZIP |
| Windows with LLVM/lld, Apple SDK, Metal compiler, .NET and spirv-cross | Offline NVN subset | Unavailable |

Windows uses `webui/build/windows/build_ipa_windows.py`. It requires one shader version matching the packaged version and rejects games whose extracted sources require Vulkan, runtime shader capture, Unreal decoding, or Oodle capture. Graphics requirements are detected from the extracted game, not guessed from its name. macOS uses the existing NSP pipeline and its capture support.

A title ID without a registered profile is surveyed from the base game and the newest supplied update, then built from a provisional profile in the task folder. This mirrors the upstream `scripts/build_ipa_from_nsp.py` fallback: the profile values are guessed from the game files and the resulting app may not boot. The task publishes `provisional.json` and `provisional-profile.tsv`, and the profile is never written into `dm/games`. Windows applies the same offline NVN restrictions to provisional builds; a game needing Mac capture is rejected with the reason. Inspection works without a profile and does not need this fallback.

The header language selector switches between Simplified Chinese and English and remembers the choice in this browser. This affects only the WebUI; game language is a separate launch setting. Build-tool logs remain unchanged.

## Windows installation

1. Clone or download this branch, then double-click `start-webui.bat` (or run `webui/launchers/start_webui.bat`). The launcher downloads a portable Python into the project on first launch, verifies its pinned SHA-256, and reuses a working runtime on subsequent launches. Windows AMD64 and ARM64 packages are selected by host architecture; AMD64 startup has been exercised end to end. No system `python` command is needed.
2. Startup installs missing Python dependencies into `.webui-data/venv` and opens the local WebUI. No data-folder prompt or global pip configuration is needed. Startup output and failures are appended to `.webui-data/startup.log`; the BAT window stays open on failure. Retry the launcher after fixing network problems: verified archives and working environments are reused. Runtime files and the startup log remain in the repository even when `--data-dir` selects another task-data directory.
3. Open **Environment & tools**, keep the default `.webui-data/tools` directory (or save a different directory), then select **Install all supported missing dependencies**. This downloads the official .NET 10 SDK for the host architecture, verifies its SHA-512 hash, and builds this repository's `nx_extract`. Python build packages can also be installed individually.
4. Use **Install** for clang/lld and SPIRV-Cross, or include them in **Install all supported missing dependencies**. LLVM-MinGW is pinned to `20261020`, with AMD64/ARM64 archives and SHA-256 hashes. Installation verifies a real ARM64 Apple compile and Darwin link. SPIRV-Cross builds from verified sources with static C++ linkage. No Visual Studio, CMake, system PATH changes or administrator command is needed. A manually prepared Apple compiler is preserved if a separate native C++ builder is needed. AMD64 installation was exercised on Windows; ARM64 is not tested natively.
5. Download Windows Metal Developer Tools through [Apple’s official page](https://developer.apple.com/download/all/?q=metal%20developer%20tools%20for%20windows). Apple account login and that package’s download/installation take place outside the WebUI. Recheck detects `metal.exe` with its sibling `metallib.exe` on PATH or under standard Program Files installations. A custom Metal path can still be entered. Xcode itself only runs on macOS. The iPhoneOS SDK entry can download the verified third-party release described below; Xcode is not required on the Windows host.
6. Select **Recheck**, then upload/import the game packages and keys. Windows produces unsigned iOS packages for the supported offline NVN subset; it cannot produce macOS applications or capture runtime shaders.

## macOS installation

1. Use an Apple Silicon Mac. Install [Python 3.11 or newer](https://www.python.org/downloads/macos/) and [Xcode](https://developer.apple.com/xcode/). Open Xcode once and finish its requested component/license setup. If developer tools point at the standalone Command Line Tools instead of Xcode, choose Xcode in **Xcode > Settings > Locations > Command Line Tools**.
2. Run `./start-webui.sh` from the repository root (or double-click `start-webui.command`). Missing Python dependencies install automatically; data defaults to `.webui-data`.
3. Open **Environment & tools**. Mac checks show Xcode SDKs, Xcode Metal and Mac tools; Windows SDK/Metal path inputs and Windows LLVM/lld checks are hidden. .NET is required on both platforms because the extractor and shader tools use C#; the generated applications do not require it. The detector probes SDK and runtime versions and reuses an existing .NET 10 SDK from PATH, Homebrew, standard system locations or `~/.dotnet`. Workers use that same SDK and runtime root. Only a missing compatible SDK needs downloading into the configured tools directory.
4. Homebrew is optional. If present, the panel first uses its normal prefix. If Homebrew is absent or its install command fails, XcodeGen 2.46.0 comes from its official universal Mac ZIP; zstd 1.5.7 and SPIRV-Cross (Vulkan SDK 1.4.363.0 commit `f11ba9f0b21ba8fc15153d50a2a1ae31ab1cf8f7`) are built from pinned official source archives with Xcode's clang and make. All three archives have pinned SHA-256 checksums. No Homebrew bootstrap, CMake or administrator command runs. Fallback binaries install in `tools/bin`, XcodeGen resources in `tools/share`, and licenses in `tools/licenses`. Source compilation requires a configured Xcode installation. Xcode and Apple SDKs remain manual. Standard `/opt/homebrew/bin` and `/usr/local/bin` locations are detected even when launched from Finder.
5. Select **Recheck**, then choose macOS and/or iOS output. Tool presence does not establish shader-chain compatibility; the existing build checks still enforce the repository's tool fingerprints. macOS installation and builds need validation on an actual Mac.

With full Xcode already installed and selected, the Mac Metal compiler entry can run Apple’s official `xcodebuild -downloadComponent metalToolchain` through the same logged installation queue. Xcode first-launch setup must be completed by the user. The detector runs `xcrun metal --version` to distinguish a working compiler from a launcher stub. This path is covered by command-selection tests; native Mac installation was not exercised on the Windows test host.

## iPhoneOS SDK discovery on Windows

The environment panel searches the configured tools directory, the project and the user's Downloads directory (including Windows redirected Downloads). **SDK search folder** adds another folder. Search depth and entry counts are bounded; hidden folders and dependency trees are skipped. It does not scan entire drives. Opening settings or clicking **Recheck** scans immediately; while settings remain open, discovery repeats every 15 seconds unless the form has unsaved edits.

Only complete device SDKs identifying iPhoneOS, version 26.5 or newer, with system libraries and Foundation headers qualify. macOS SDKs, simulator SDKs, old versions and incomplete downloads are rejected. The Windows settings offer **Automatic** (an installed SDK) and specific repository versions (currently 26.5 and 27.0); choosing a version requires that exact SDK and enables its download. With **Automatic**, version 26.5 is preferred because it matches the cross-build target, and another complete detected SDK can be selected explicitly. Build workers resolve the same selected path; saving an automatically found path is unnecessary.

When the SDK is missing, **Extract and configure SDK** imports a discovered `iPhoneOS*.zip`, `.tar`, `.tar.gz`, `.tgz` or `.tar.xz` through the logged task queue into `tools/ios-cross/iPhoneOS<version>.sdk`. Multiple archives require selection; a single archive can be included in the automatic install queue. Archives must contain exactly one complete device SDK. The original archive is preserved, archive traversal is rejected, and existing SDK directories are not overwritten. Full Xcode `.xip` installers are not SDK archives and are not extracted on Windows.

Windows defaults to **xybp888/iOS-SDKs (third-party, SHA-256 verified)** when an SDK is missing. Choose **iPhoneOS SDK version** and click **Download selected iPhoneOS SDK**, or use **Install** / **Install all supported missing dependencies**. Each selectable release is pinned in the WebUI with its SHA-256; 26.5 and 27.0 are currently offered from [xybp888/iOS-SDKs releases](https://github.com/xybp888/iOS-SDKs/releases). GitHub serves these public archives without Apple account login. The installer does not follow the repository's latest branch or release automatically. It materializes the archive's internal Unix links as real files/directories, so Windows Developer Mode and administrator symlink privileges are unnecessary. Escaping, missing and cyclic link targets are rejected. Download origin, release and digest are recorded in `nxnative-sdk-source.json`; the downloaded ZIP is removed after successful installation.

Existing complete SDKs are reused. Choose **Local SDK or archive only** and save to disable SDK network downloads. An explicit archive import selects local mode. Windows Metal still uses Apple's official authenticated download flow; this third-party SDK source does not supply Xcode or Windows Metal tools. The SDK archive is fetched by each user's installer and is not bundled in the repository.

## Python mirror and installer behavior

The Windows Python runtime downloads from the Huawei Cloud NuGet mirror first, with an explicitly logged fallback to official NuGet if the mirror fails or has not synchronized the pinned release. Both sources must match the same pinned SHA-256 in `webui/launchers/python-windows.json`. A partial or mismatched download is never executed. An installation lock prevents simultaneous downloads; a broken existing runtime is preserved with a `.previous-...` suffix when replaced.

Startup, WebUI Python installation and the offline bundle preparer default to the [Tsinghua PyPI mirror](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/) at `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`. In **Environment & tools**, choose **Official PyPI** and save to switch sources. The saved selection applies to subsequent installs and restarts. The preparer also accepts `--index-url`; `--wheelhouse` bypasses network indexes entirely. This does not change the machine's global pip settings. .NET, Homebrew and NuGet keep their own download sources.

The WebUI does not accept arbitrary commands, package names or download URLs. Installation is serialized with builds. A failed network or package-manager operation remains in the task log and can be retried; successful dependencies are skipped on retry. Cancelling installation stops its process group, but tools already installed remain installed. Full Xcode and Windows Metal downloads remain external flows. Locally supplied iPhoneOS SDK archives can be imported, or a selected pinned xybp888 release can be downloaded. Windows LLVM and SPIRV-Cross install automatically.

## Workflow

1. Upload files, or import existing absolute file paths to avoid another large upload. Chunk uploads resume after reselecting the same file in the same browser. The newest saved keys file is selected automatically; previously uploaded files can be re-added from the upload history. Supply the base game and all profile-required updates.
2. Choose **Build an app**, **Convert XCI/NSZ to NSP**, or **Inspect game metadata**. For builds, choose iOS and/or macOS and the initial game language, handheld/docked mode, spatial upscaling, and output resolution. For iOS you can also tick **Separate IPA and RomFS** (off by default). NSZ files can also be added directly to a build; they are decompressed before inspection. If the base title ID has no profile, the task first surveys the supplied base and newest update and continues with a provisional profile; review `provisional.json` and expect that the app may need bring-up.
3. Follow the task journal and log. Cancel stops the worker process tree. Downloads are limited to published artifacts. A target failure preserves any successful output from another target.

### Separate IPA and RomFS (optional, iOS)

When the checkbox is ticked, the iOS IPA is built without `Payload/DmIOS.app/romfs` and the task also produces:

- `<title>.ipa` — the small IPA;
- `<title>.ipa.sha256`;
- `<title>.romfs.zip` — a Zip64 archive whose top level is `romfs/`;
- `<title>.romfs.zip.sha256`.

Install the IPA first. In the Files app, open **On My iPhone/iPad → \<App Name\> → Documents**, unzip the archive and move the inner `romfs` folder directly into `Documents`, so the game marker ends up at `Documents/romfs/<romfs_marker>`. Do not leave an extra `romfs/romfs` level, and delete an old `Documents/romfs` before copying. The app checks `Documents/romfs` before its bundled RomFS; without it the log says `game files not found`.

macOS `.app.zip` always includes its RomFS. If both targets are selected, the iOS build produces the one archive and the macOS app stays self-contained. AOC/DLC stays in the IPA. A sideloading reinstall can create a new Documents container, so copy `romfs` again; the host needs roughly one extra RomFS of output space, and the device needs room for both the archive and the extracted folder.

Language and operating mode apply before game launch. Both app launchers allow changing the defaults and restoring the packaged choices. Spatial upscaling uses Metal 4 FX on supported NVN devices, with ordinary presentation as fallback. It does not add frame generation or force the game's dynamic resolution off. Vulkan output disables the spatial option. The iOS Game Settings also has a **Performance HUD** toggle showing presented FPS, game input and presented output resolution, and app memory use/headroom. Game settings/save data can override the requested language. Device gameplay and scaling quality still require testing on Apple hardware.

XCI conversion validates container bounds, partition hashes, CNMT content membership and content hashes, then streams the original encrypted NCA files into standard NSP containers. Multi-title secure partitions produce separate NSPs. Compressed/split XCI formats are not supported. The converter does not acquire keys or game files.

NSZ uploads are losslessly decompressed to NSP with the pinned MIT-licensed `nsz` package, using the task's uploaded keys. The resulting NSPs are published as artifacts; a converted NSZ can then be used in a build like any other NSP. A modified/corrupt NSZ or XCI whose NCA hashes no longer match its metadata is rejected rather than converted into an invalid NSP.

## Local data and recovery

```
data/
  config.json
  inbox/                  # owned uploads or references to existing files
  stage/                  # staged source trees (rebuilt on demand)
  tasks/<id>/
    task.json             # immutable request configuration
    events.jsonl          # append-only status/progress journal
    build.log
    inputs/               # normalized inputs and incremental build cache
    outputs/              # downloadable artifacts
```

Restart marks unfinished jobs interrupted; retry is manual. Retry can reuse an existing extraction/shader cache when the original inputs still match. Cache timestamps that differ are checked by SHA-256 before reuse. Build scripts also validate their own fingerprints and shader evidence. Deleting task data is disabled while work is queued/running. Retrying a removed cache performs a fresh build.

Build and conversion tasks show a stage-weighted progress bar in the task list, together with the current stage and a running elapsed time. Long single stages such as `shader_split` keep their percentage until the stage completes; the bar pulses while the task is active so a CPU-bound stage is not mistaken for a stalled one. The task log also receives a timestamped heartbeat every ten seconds while a step runs, and shader/host compilation include completed/total counters. Each step logs its elapsed time when it finishes.

**Clear build cache** in Environment & tools deletes the staging tree (`data/stage`), the shared shader cache (`tools/shader-cache`) and each task's `inputs/` directory (normalized inputs plus extraction and build caches). Task records, logs, retained keys and finished `outputs/` stay. The action is rejected while a task is queued or running; the next build recreates the caches, and retries need the original inputs to still be available. Files copied to the optional output folder are not removed.

**Output folder** in Environment & tools optionally copies finished artifacts out of the task data: the IPA, macOS `.app.zip`, separate RomFS archive and their `.sha256` files, plus converted NSPs from conversion tasks. Same-named files are overwritten by later builds; the task's own `outputs/` directory and its download links remain. Leave the setting empty to keep files only in the task data folder.

Keys are never published as artifacts. Uploaded keys stay in the data folder and appear in **Previously uploaded files**; the newest saved key is selected automatically for later tasks. Delete a saved key from the upload history when it should no longer be stored. Private task copies are removed after completion/cancellation unless explicitly retained, which keeps a retry working even if the saved upload is deleted. Original files imported by path are never deleted. Logs contain file paths and tool output, so keep the data directory private to your OS account.

## Validation

```sh
python -m pip install httpx
python -m unittest discover -s webui/tests -t . -v
python -m webui.tests.integration_nsp --nsp /path/to/game.nsp --keys /path/to/prod.keys --tools /path/to/tools --out /path/to/test-data --build
```

The integration runner exercises the real HTTP task API, metadata inspection, extraction manifest, and optional full build. Results stay on the game drive. IPAs are unsigned; this workflow neither signs nor installs them on a device. macOS packages are ad-hoc signed for local use and need separate Mac validation.

Validated on Windows: Hades II base version 0.0.126424 produced an unsigned IPA with 88 shader keys and 5,418 archive entries. See [the verification summary](webui-hades2-validation.json). The WebUI regression suite includes startup and dependency-help regression tests. Browser checks cover inspection/download links and Chinese/English switching, persistence, and independent game language.

Windows installer validation (2026-10-21): fresh AMD64 LLVM download/extraction passed real ARM64 Mach-O compile and Darwin link probes. SPIRV-Cross compiled from the pinned source and ran with only System32 on PATH. All 62 WebUI tests passed. The new compiler built all 129 Hades II host sources; the linker produced a validated unsigned iOS executable using the previously extracted game embed. This validation did not repack a new IPA or test gameplay on a device.

Repository SDK validation (2026-10-21): the actual xybp888 26.5 release passed SHA-256 validation, full Windows adaptation and fresh installer execution. All 129 Hades II host sources compiled against this SDK and linked into a validated unsigned iOS executable (SHA-256 `00ec3ba0c62bf9f150c272133b0a83ece569ed4b23daac617a967aaae4c4ad55`). All 70 WebUI tests passed. A new IPA was not repacked and gameplay was not tested on a device.

Windows .NET installation uses extended-length filesystem paths and a shorter staging directory, including analyzer resources beyond the legacy 260-character limit. A verified archive is cached under `tools/downloads` while installation is incomplete. Retrying the same SDK version rechecks SHA-512 and reuses that archive; successful installation removes it. Unverified `.partial` downloads are never published. Extractor compilation is skipped when its prerequisite .NET installation fails. The 74-test suite includes the original failing analyzer-resource path and cross-task cache reuse.
