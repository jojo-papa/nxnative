# WebUI implementation plan

Integration base: `xbunax/nxnative` main at `233f18f421344fcd3b61559459ef8649d6c38a54`.

- [x] Isolate integration from the original checkout's uncommitted native changes.
- [x] Add a small FastAPI service and plain HTML/CSS/JavaScript UI.
- [x] Use task configuration files, JSONL events and text logs, without SQLite.
- [x] Support chunked uploads, local path imports, metadata inspection, serial jobs, cancellation and interrupted-job recovery.
- [x] Convert standard XCI secure partitions into per-title NSP files with integrity validation.
- [x] Connect macOS/iOS packagers and Windows offline NVN iOS cross-compilation.
- [x] Migrate language, operation mode and MetalFX spatial launch settings.
- [x] Keep tool/runtime preparation separate from proprietary SDKs, keys and game inputs.
- [x] Complete Hades II NSP-to-IPA integration acceptance and record verification results.
- [x] Finish browser verification, including Chinese/English switching.
- [x] Prepare the tested integration for GitHub synchronization on `codex/lightweight-webui`.

Acceptance: use Hades II base NSP `0100A00019DE0000`, version `0.0.126424`. Verify extraction/build IDs, unchanged shader evidence, shader-chain compilation, rewritten embedded module bytes, unsigned ARM64 iOS executable, archive integrity and included launch defaults. A successfully produced IPA is build acceptance; device playability and macOS execution remain separate hardware tests.

- [x] Add a persistent Chinese/English interface switch, independent from game language.

Build results: [Hades II verification summary](webui-hades2-validation.json). macOS packaging and iOS gameplay were not executed on Apple hardware.

## Startup defaults

- Start without a directory prompt; use the Git-ignored `.webui-data` directory in the repository.
- Reuse compatible installed Python dependencies, or automatically install them in a local venv without modifying system Python.
- Allow repository-local data and dedicated subdirectories under the user home.

## Dependency installation

- Add allowlisted install tasks to the existing queue with JSONL/text logs, cancellation and retry.
- Default Python to the Tsinghua mirror; allow selecting official PyPI without changing global pip settings.
- Install Python packages, local .NET 10 SDK and nx_extract automatically; on Mac use existing Homebrew for xcodegen, zstd and spirv-cross.
- Provide separate Windows/macOS instructions in the bilingual UI and documentation; retain manual Apple-tool and Windows native-tool setup.

## Host-specific tools and Mac fallback

- Show Mac-only Xcode/SDK/Metal checks on macOS and Windows cross-toolchain checks on Windows.
- Probe and reuse existing .NET 10 SDK/runtime installations for detection and workers.
- Fall back from absent/failed Homebrew to pinned, SHA-256-verified official Mac downloads and Xcode source builds in the local tools directory.
