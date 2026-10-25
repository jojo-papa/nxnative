# Upstream hook patches

These patches keep fork behavior out of the upstream working tree. They are
applied only to the staging tree created by `webui/staging.py`.

- The current base, upstream, fork, hooks and merge-base commits are recorded in
  `UPSTREAM_BASE`; `webui/tools/sync_upstream.py` updates that file and the
  `series` comments when it regenerates the queue.
- Patches are regenerated with
  `git diff --no-ext-diff --unified=3 upstream/main -- <target>` from the ported hooks branch.
- The 2026-10-24 sync merged upstream `fa69e20` into `main`;
  `sync/upstream-20261024` is the vendor-drop equivalent with the same tree.
  The pre-sync main (`c586dd1`) is preserved on
  `backup/main-before-upstream-20261024`. `webui/docs/sync.md` records the
  automation and manual fallback procedures.
- `series` lists the patch file and its target. The applier rejects a target
  that differs from the series entry or escapes the tree.
- Patch files are LF. The source checkout uses CRLF; `webui/diffapply.py`
  normalizes both sides and writes LF into the stage.

## 2026-10-24 port notes

Upstream's `gen_embed.py` now packs NRO modules through a `place()` helper; the
fork's POSIX paths and `no_dead_strip` section attributes are applied to both
the module and NRO section directives. The host Makefile line carries upstream's
new headers (`pad_slots.h`, `hle_haptics.h`, `haptics_apple.h`, CoreHaptics) and
no longer names the per-game `dmsh_chain.h`, while keeping `-framework MetalFX`.
`scripts/build_ipa_from_nsp.py` keeps the `--target mac`, `--separate-romfs` and
`@NXEVENT` hooks beside upstream's new `--platform` option.

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
