# WebUI package

The WebUI is the fork-owned local build studio. Upstream nxnative code stays at
its original paths; everything here is safe to change without touching upstream.

## Layout

- `server.py`, `jobs.py`, `worker.py`: loopback FastAPI service and serial tasks.
- `capabilities.py`, `dependencies.py`, `apple_tools.py`, `windows_tools.py`:
  environment checks and tool installation.
- `packages.py`, `file_tools.py`: NSP/XCI inspection, XCI conversion and NSZ decompression helpers.
- `repo.py`: repository root, upstream game module import and git exclude helper.
- `staging.py`: materializes the build staging tree (source snapshot + overlays + patches).
- `diffapply.py`: line-ending-normalizing unified-diff applier used by staging and tests.
- `build/windows/`: Windows cross-compile, shader build and IPA packer.
- `build/macos/`: macOS application wrapper and packager.
- `overlays/dm/`: fork-only source files copied into the staged `dm/` tree.
- `patches/`: ordered upstream hook patches (`series`).
- `launchers/`: canonical Python/PowerShell/shell launchers.
- `tools/`: staging CLI, patch queue, sync check, upstream sync CLI, tool preparation and XCI helper.
- `tests/`: unittest suite (`python -m unittest discover -s webui/tests -t . -v`).

## Build flow

1. The worker calls `staging.ensure()` to create or reuse a stage tree under
   `.webui-data/stage/<key>/tree`.
2. The stage is a full copy of the repository excluding generated/local folders.
   Overlay files are written into `dm/`, then the patch queue is applied with the
   pure-Python applier. The working tree is never modified.
3. The Windows builder runs the staged
   `webui/build/windows/build_ipa_windows.py`; macOS runs the staged
   `scripts/build_ipa_from_nsp.py` (patched to accept `--target mac` and launch
   defaults). nx_extract is built from the staged, patched C# project.
4. With the optional `--separate-romfs` (WebUI: **Separate IPA and RomFS**,
   default off), the iOS IPA omits `Payload/DmIOS.app/romfs` and
   `webui/build/romfs_archive.py` uses the upstream `pack_ipa.py` to write
   `<ipa>.romfs.zip` with a top-level `romfs/`. The worker verifies both and
   publishes the IPA, archive and their SHA-256 files.
5. Stage reuse is keyed by the source file manifest, platform, patch bytes and
   overlay bytes. `NX_STAGE_REBUILD=1` forces a rebuild; `NX_STAGE_KEEP`
   controls garbage collection.

## Adding an upstream hook

1. Add a patch file to `webui/patches/` and an entry to `series` (patch file and
   repository-relative target).
2. If the hook adds a new source file to an upstream directory, put it under
   `webui/overlays/dm/...` instead and list its target in the overlay allowlist.
3. Add a marker assertion to `tests/test_patch_queue.py`.
4. Run `python webui/tools/sync_check.py` and the full test suite.

See `docs/sync.md` and `docs/webui.md` for the user-facing workflow.
