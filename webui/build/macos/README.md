# Native macOS application wrapper

`pack_app.py` assembles the rewritten modules, RomFS, matching shaders, profile and fonts into a relocatable application and ZIP. `build_app.py` compiles the native host using the existing Makefile and replaces the executable only after a successful build.

The AppKit launch dialog provides game language, handheld/docked mode, MetalFX spatial upscaling and output resolution. Choices are stored in the application bundle ID's NSUserDefaults domain; Restore Defaults reloads the packaged defaults. Unsupported spatial scaling is disabled. Frame generation is not included.

Saves and temporary data default to `~/Library/Application Support/<bundle ID>/`. `DM_ROOT` overrides that location. Build inputs and packaging work stay on the supplied game/output drive. Full builds require Apple Silicon macOS and the repository's native build dependencies. This wrapper has not yet been runtime-tested on a Mac.

See [the WebUI guide](../../docs/webui.md) for the end-to-end workflow.
