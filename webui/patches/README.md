# Upstream hook patches

These patches keep fork behavior out of the upstream working tree. They are
applied only to the staging tree created by `webui/staging.py`.

- Upstream base: `eab15b5a7e339d172ba7cd6b1a298ec3cf1e16b6` (seedds/nxnative main, 2026-10-23)
- Fork tree: `77dee3dab542d19a76e0cbb7175d3b6726ad275c` (the WebUI/fork commit copied into the sync branch)
- Hooks commit: `18e488271dd3a0bbd17a7a5d2acadc6b1f648cf1`
- Patches were regenerated with
  `git diff --no-ext-diff --unified=3 upstream/main -- <target>` from the ported hooks branch.
- The sync branch `sync/upstream-20261023` is a vendor drop of upstream `eab15b5`; the fork's previous main (based on `233f18f`) remains the stable branch until this one is validated.
- `series` lists the patch file and its target. The applier rejects a target
  that differs from the series entry or escapes the tree.
- Patch files are LF. The source checkout uses CRLF; `webui/diffapply.py`
  normalizes both sides and writes LF into the stage.

## Patch 0009 notes

The original fork patch added a top-level `import json` because the WebUI
launch-defaults block used `json` while the module imported it only inside
`Progress.stage`. Upstream now imports `json` itself; the port keeps the WebUI
`@NXEVENT` hooks, the macOS target path (`webui/build/macos/pack_app.py`), the
launch-defaults block and the separate-RomFS block. The rest of the patch is
rebased onto upstream's newer `build_ipa_from_nsp.py` (derived profiles,
`--prepare-xcode`, `--language`, `--show-fps`, `--progress json`).

## Separate RomFS hooks (0008/0009)

Patches 0008 (`dm/ios/tools/build_ipa.sh`) and 0009
(`scripts/build_ipa_from_nsp.py`) also carry the optional `--separate-romfs`
hooks. Patch 0008 skips the `MAPS` RomFS entry when
`NX_SEPARATE_ROMFS=1`; patch 0009 adds the flag, sets that environment value,
and creates the separate archive with `webui/build/romfs_archive.py`. The
archive layout is a top-level `romfs/`, created by the upstream `pack_ipa.py`.
This remains one patch per target; the queue is still nine patches.

## Do not regenerate

`.gitignore`, `README.md` and `dm/ios/project.yml` are not part of the patch
queue. The first two are restored to upstream; `project.yml` is the single
intentional direct edit (fullscreen launch keys).

After an upstream sync, port the hooks onto a temporary hooks branch and run
`python webui/tools/patch_queue.py regenerate`. See `webui/docs/sync.md`.
