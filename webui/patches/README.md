# Upstream hook patches

These patches keep fork behavior out of the upstream working tree. They are
applied only to the staging tree created by `webui/staging.py`.

- The current base, upstream, fork, hooks and merge-base commits are recorded in
  `UPSTREAM_BASE`; `webui/tools/sync_upstream.py` updates that file and the
  `series` comments when it regenerates the queue.
- Patches are regenerated with
  `git diff --no-ext-diff --unified=3 upstream/main -- <target>` from the ported hooks branch.
  The sync CLI ports the previous queue with `git apply` (exact context, line
  offsets allowed), then requires the regenerated queue to pass the strict
  `diffapply`/staging checks.
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
This remains one patch per target; the queue is still ten patches.

## Patch 0010 notes

`dm/tools/nso_syms.py` read the NSO dynamic section as 16-byte entries
(u32 tag, u32 pad, u64 value) and the symbol table as 24-byte `Elf64_Sym`
entries, both fixed. Some SDKs (NSMB U Deluxe, for one) write 8-byte dynamic
entries (u32 tag, u32 value) and a 16-byte `Elf32_Sym` table with
`DT_SYMENT = 16`; the old read raised `KeyError: 6` on the missing SYMTAB and
the survey of such a game died before it could write a provisional profile.
The patch reads the dynamic section at both widths and keeps the one whose
symbols fit between SYMTAB and STRTAB, and it reads the symbol table at
`DT_SYMENT` (16 or 24). The 24-byte path is byte-for-byte the old one: every
registered game's symbols are unchanged.

## New Super Mario Bros. U Deluxe is AArch32, not AArch64

`nso_code.py` notes that NSMB U Deluxe's MOD0 does not point at a valid
`.eh_frame_hdr`, and `patch_nso.py` dies on it with `KeyError: 14` (its inline
`rd()` table knows only the formats 0x3, 0xB and 0x4). The reason is not a
missing format: the modules of that NSP hold **32-bit ARM (AArch32) code**.

Evidence (Super Mario Odyssey for comparison):

| | SMO main | NSMB U main | NSMB U sdk | NSMB U rtld |
|---|---|---|---|---|
| `ret` (0xD65F03C0) | 46 716 | 0 | 0 | 0 |
| `bl` | 226 545 | 204 | 98 | 0 |
| decodable words | 100.0% | 31.0% | 37.3% | 47.3% |

The rtld's first function is `stmdb sp!, {r20,r21,r28,lr}` / `add r11,sp,#8` /
`sub sp,sp,#0x48` / `ldr r12,[pc,#0x16c]` — an ARM32 EABI prologue, and every
one of those words is a reserved encoding in AArch64. The dynamic symbol table
agrees: it exports `__aeabi_unwind_cpp_pr0`, `__aeabi_memclr`, `__aeabi_memset`
(ARM32 EABI) where the AArch64 games export `memcpy`, `memset`, `sqrtf`.
The decompression itself is fine: the rodata still holds "Course" 267 times and
the C++ symbol names.

`patch_nso.py` rewrites AArch64 only (`x18`/`w18`, `mrs tpidr_el0`, `svc`,
AArch64 branch encodings, AArch64 FDE tables), so this game cannot be built
here, and the "guess code from the decode ratio" fallback cannot stand in for
the FDE table either: 2452 of NSMB U's 2479 text pages decode below 50% and
the data is interleaved with the code at a fine grain, so a guess would
corrupt the tables (17 213 words look like x18 instructions, against 1 893 in
SMO, where every one of them is real code).

Supporting it needs a separate AArch32 rewriter, not a patch to this queue.
Details and the reproduction scripts: `D:\nxnative\out\RESEARCH_NSMBU_ISA.md`.

## Patch 0014 / 0015 notes (screen fill)

The black bars on iOS come from the host, not from Metal: `front_ios_letterbox()`
puts the Metal view in a centred 16:9 rectangle, so the canvas is 16:9 and the
Metal layer's own aspect-ratio keeping (`fmin` in `present_encode`) is a no-op
there. Filling the screen therefore needs both layers to change, and they must
agree — changing only the host leaves a second letterbox inside the canvas (a
Metal clear colour that covers the chrome), changing only Metal does nothing at
all (the canvas and the source are both 16:9, so `fmax` equals `fmin`).

`DM_SCREEN_FILL` in `Documents/env.txt` picks the mode at run time: `fit`
(default, as before), `cover` (scale up until the canvas is covered, the edges
are cut off) and `stretch` (fill without keeping the aspect ratio). The
fragment shader clamps the UV to the valid area and the blit sampler keeps
Metal's default clamp-to-edge, so `cover` cannot sample out of bounds.

## Patch 0016 notes (the shader splitter needs no zstd command)

`dm/gfx/tools/shader_split.py` decompresses the game's zstd files with the `zstd`
command when the frame names no dictionary, and with the zstd module otherwise. On a
machine without a zstd command the split dies with `FileNotFoundError` before it looks
at a single file - Nintendo Switch Sports' RomFS alone holds 10,751 `.zs` files. The
patch keeps the command when there is one and uses the module (the same dependency the
file already has for the dictionary frames) otherwise. The two give the same bytes: the
game's own files were checked against the `zstandard` package, and the SARC and BYML
magics come out right.

The zstd module is `compression.zstd` on Python 3.14 and its `backports.zstd` backport
before; on Python 3.13 it needs `pip install backports.zstd` (the venv in
`.webui-data/venv` has it).

## Patch 0017 / 0018 / 0019 notes (geometry-stage shaders)

Nintendo Switch Sports stopped the packer with

```
ValueError: 0 shaders missing, 223 unresolved bindings;
experimental packaging requires --allow-incomplete-shaders
```

All 223 unresolved bindings are `kind='sbuf'` on geometry-stage shaders
(`msl_name='gp_s0'`, `msl_type='device _35*'`). The cause is in
`dm/gfx/tools/dmsh_build.py`: the per-stage storage-buffer base table

```python
SSBO = {'vs': 0x110, 'cs': 0x310, 'ps': 0x510}
```

has no `'gs'` key, so `reflect()` computes `base = None` for the geometry
stage and leaves `e['reg'] = None`. `dm/gfx/nvn/nvn_refl.m` refuses such a
binding (`"B binding %s has no resolved slot number"`), `nvn_refl_from_json`
returns 1 and `nvn_mtl.m` prints
`[RED] shader %s reflection conversion failed` and loads nothing. The
`--allow-incomplete-shaders` escape would only move the failure from packaging
time to run time.

The patch ports the upstream fix (`seedds/nxnative` commit `31b5944`, "Port
NieR Automata with 60 fps and geometry fixes"), without the parts of that
commit that need a rebuilt translator DLL:

- `dmsh_build.py`: `SSBO` gains `'gs': 0x410`; the storage-buffer write flag
  is read as `flags & 1` (`BufferUsageFlags.Write`, confirmed by reflecting
  `Ryujinx.Graphics.Shader.dll`; the old `& 2` marked every write buffer
  read-only).
- `dm/gfx/nvn/nvn_mtl.m`: `c0_ssbo_base()` returns `0x410` for NVN stage 2, so
  the driver's c0 storage-buffer table is written where the geometry shader
  reads it. The runtime side was already complete (`S.ssbo[2][reg]`).

Upstream's commit also rebuilt the pinned translator, so its `dmsh_chain.lock`
hashes do not match this machine's (`eb315f0da558ca5a` / `08d31903d666ea0c` /
`16bbef6c762573ee` here). The parts below are pure Python and were ported
one by one instead:

- `dmsh_geometry.output_layout(code, input_topology)`: the ShaderDefinitions
  passthrough override. All 232 of Switch Sports' geometry shaders set the
  override bit, and the raw SPH bound says **one** vertex where the triangle
  kernel writes three (six index words per invocation). The old code used the
  raw bound for all five input topologies, so the replay was told the wrong
  vertex count.
- `dmsh_geometry.reader(src)`: the raster vertex reader. `ResourceReservations`
  stores ViewportMask as one word but the generator treats it as a scalar
  while the IoMap declares `int[1]`; SPIRV-Cross then emits
  `spvArrayCopyFromStackToStack(gl_BuiltIn_5253, as_type<int>(_129).elements)`,
  which is not valid MSL. All 232 `_bgv.metal` files of Switch Sports failed
  to compile with
  `member reference base type 'int' is not a structure or union`. The rewrite
  keeps the culling decision: viewport zero's bit, a zero moves the vertex
  past the X clip plane.
- `dmsh_geometry.capture_input(src)`: the capture-input reads become
  `volatile`. Copying all 128 contiguous generic components can make Metal's
  optimized AIR fail AGX pipeline compilation on the device; 223 of this
  game's shaders read `vertex_output`.

`dmsh_atomic.lower_msl` (the SPIRV-Cross image-atomic helper) was **not**
ported: it would add a new file to the tree, and only two shaders of this
game use `spvImage2DAtomicCoord`, both on a plain `texture2d` where the
32-bit address wraparound the helper avoids cannot happen. The macro the local
SPIRV-Cross emits is byte-identical to the one upstream validates, so the
port is possible later without a translator rebuild.

The three patches change the shader chain version (`fa59c36a9d6a` ->
`73421f6c1c08`), so every shader is compiled again.

Details: `D:\nxnative\out\RESEARCH_GS_SSBO.md`.

## Patches 0020-0030 notes (native widescreen)

Port of upstream `seedds/nxnative` PR #117 (`aspect any`, `OUTPUT_W`/`OUTPUT_H`,
`DM_ASPECT=wide`) and the Breath of the Wild output-size stubs of PR #76, so a
game can render at the screen's own aspect instead of being stretched.

- 0020 `dm/host/dm.h`: `module_t` gains `out_w` / `out_h`.
- 0021 `dm/host/front.h`: declares `front_screen_aspect()`.
- 0022 `dm/host/loader.c`: reads `OUTPUT_W` / `OUTPUT_H` from the rewriter table,
  adds `output_aspect()` (width = height x the screen's aspect, a multiple of 8,
  never narrower than 16:9) and `DM_OUTPUT_SIZE` (`WxH`, `1080p`, `1440p`, `4k`);
  the state page grows from 0x40 to 0x50 bytes (+0x40 the output size, +0x48 its
  width as a float).
- 0023 `dm/tools/patch_nso.py`: `ctx.keys` adds rows to the fixups table
  (`FS_KEYS`); the state page size is `FS_STATE_SIZE`.
- 0024 `dm/games/game.py`: the profile key `aspect` (`16:9` / `any`) becomes
  `DM_GAME_ASPECT_ANY`.
- 0025 `dm/games/settings.tsv`: the launcher's Picture row (`DM_ASPECT`:
  Wide / 16:9), shown when `DM_GAME_ASPECT_ANY==1&fixups:OUTPUT_W`.
- 0026 `dm/games/settings.py`: a `shown` condition may join several with `&`.
- 0027 `dm/ios/Sources/front_ios.m`: the canvas is the screen's aspect in the
  wide mode (the game view covers the screen), `front_ios_canvas_aspect()` and
  `front_screen_aspect()`; the chrome's buttons float over the picture.
- 0028 `dm/ios/Sources/DmGamepad.m`: the touches map on the same canvas.
- 0029 `dm/games/01007EF00011E000/patches.py`: Breath of the Wild's output-size
  stubs (upstream PR #76): the output size global (three sites), the docked
  output width, the render size and the window crop.
- 0030 `dm/games/01007EF00011E000/game.tsv`: `aspect any`.

Only Breath of the Wild carries the stubs, so only it can render wide; every
other game keeps `DM_SCREEN_FILL` (fit / cover / stretch). Nothing here has run
on a device yet: the upstream author never checked BotW wide either.

Details: `D:\nxnative\out\RESEARCH_XHS_FULLSCREEN.md`.

## Patches 0031-0032: the host widens the view (any game)

The BotW stubs need the engine to build a wide render target. A game that never
asks for the display resolution (Super Mario Odyssey) cannot be given one that
way, but its projection matrix reaches the vertex shader as four `float4` rows
in a uniform buffer, and the host can widen the view from there.

- 0031 `dm/gfx/nvn/nvn_mtl.m`: `DM_NVN_PROJ`, a read-only probe. It looks for
  the perspective matrix in the uniform buffers the vertex stage binds (four
  consecutive `float4` slots, the `-1` of the perspective in the w row, the
  off-diagonal terms zero, the two scales in range) and logs what it finds.
  Nothing is changed.
- 0032 `dm/gfx/nvn/nvn_mtl.m`: `DM_SCREEN_FILL=wide` (a fourth mode next to fit
  / cover / stretch) and `DM_PROJ_WIDEN`. The picture fills the canvas and the
  host widens the horizontal field of view by exactly the factor the picture is
  stretched by, so the picture keeps its proportions (the same geometry a
  native render at the screen's aspect gives) while the HUD and the depth stay
  as they are. The projection is found at runtime by the signature of 0031
  (the ratio of the two scales has to match the aspect of the game's own
  picture, which tells the camera's projection from a shadow map's), and it is
  scaled on the host's own copy of the game's upload, so the game and the GPU
  read the same matrix and no upload is scaled twice. Without a projection the
  mode falls back to `cover` rather than stretching the picture wrongly.
- 0032 `dm/ios/Sources/front_ios.m`: the canvas takes the screen's shape in
  the wide mode (the picture covers the screen), so the touches map on it.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md`.

## Patches 0033-0036: the empty service session, the detection, the chrome

- 0033 `dm/host/hle_sf.c`: the host answers **every** service the game asks for with a
  session of its own, instead of refusing the ones it does not know. A refusal is
  fatal here: Super Mario Odyssey links the `hid` client into its own main, the SDK's
  client code does not check the failure and walks on the handle it was given
  (SIGSEGV at `sdk+0x24254c`, a few minutes into the game). An empty session that
  answers every request with zeros keeps the game alive.
- 0034 `dm/gfx/nvn/nvn_mtl.m`: the detection of 0032 never matched anything: the
  range it accepted for the y scale (`0.6 .. 4.0`) cut off Odyssey's own projection
  (`m00 = 4.27261`, `m11 = 7.59575`, the ratio `16:9`). The range is now wide
  (`0.05 .. 64`) and a translation in the first two rows is allowed (that is the
  camera's view-projection, the projection times the view); the aspect of the two
  scales stays the thing that tells the camera's matrix from a shadow map's.
- 0035 `dm/ios/Sources/DmGamepad.m`: the host's own buttons at the top (the volume
  `−` / `+` and the layout switch `2D` / `3D` / `Tap`) are painted in the host's
  colour. The game's own keys stay neutral white, so the two are not mixed up.
- 0036 `dm/ios/Sources/front_ios.m`: the reflection of the picture into the bar is
  **off by default** (a mirrored menu reads as a second, upside-down copy of the
  options); `DM_REFLECT=1` in `Documents/env.txt` brings it back. The shortcut
  buttons (screenshot / FPS / hide) and the volume slider get the host's colour.
- 0037 `dm/ios/Sources/front_ios.m`: the chrome can be brought back. The hide
  button took the chrome off the screen together with the only way to turn it on
  again; a small button in the corner of the picture now appears while the
  chrome is hidden and restores it.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md`.

## Patch 0038: the shader step that hung the build

- 0038 `dm/gfx/tools/cb_extent.py`: the step that measures how far into each
  uniform slot a shader can read ran its work in a **process** pool. On Windows
  that pool's result handler thread can die and leave the parent waiting for a
  result that never arrives: the build stopped at this step with every worker
  idle, no CPU spent and nothing written to disk (it looked alive because the
  build prints a heartbeat every ten seconds). The step only reads one small
  file per shader and matches a few patterns in it, so it now uses a **thread**
  pool, which cannot lose a result over a pipe.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md`.

## Patch 0039: the 2D interface was stretched by 22%

- 0039 `dm/gfx/nvn/nvn_mtl.m`: `proj_scale_upload()` scales the x row of the
  projection **when the game uploads it** (`mtl_sub_update`). A buffer the game
  writes itself — its own memory pool, mapped, so the bytes never travel through
  that path — kept the game's own matrix, and the GPU read it unscaled. On
  Super Mario Odyssey the 2D interface uses such a matrix (the second family:
  `cb1`, float4[6..9], `(6.4294,0,0,0) (0,11.4301,0,0)`), while the 3D camera
  uses the first (`cb0`, float4[0..3], `(4.27261,…) (0,7.59575,…)`). The 3D was
  compensated, the 2D was not: the menu's white highlight box went from an
  aspect of 9.00 in the game's own picture to 11.41 on the phone — stretched by
  22% horizontally, which is exactly the 19.5:9 / 16:9 difference.

  The host now binds a **copy** of such a buffer with the x scale corrected
  (`proj_shadow()`): the copy lives in the per-frame scratch arena, so the
  game's own memory stays exactly as the game wrote it and the game still
  computes its interface layout and its touch hit boxes from the matrix it
  wrote. Only what the GPU reads is scaled.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md` (section 4.13).

## Patch 0040: the projection probe flooded the log

- 0040 `dm/gfx/nvn/nvn_mtl.m`: `proj_probe_on()` turned the read-only probe on
  when the variable `DM_NVN_PROJ` was merely **present**, not when it was
  **set to a true value**: an environment file that sets `DM_NVN_PROJ=0` (the
  switch that says "no probe") kept it running. The probe scans the uniform
  buffers of every draw and writes a line for each matrix it finds, so the
  same matrix was written again in every frame: 528282 lines in half an hour,
  85 MB. That I/O slows the game down and buries everything else in the log.

  The switch now reads its value (`DM_NVN_PROJ=1` on, `=0` off), and even with
  the probe on only a matrix that is **new** at that address is written, and one
  that **changed** at most once every 300 frames.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md` (section 4.14).

## Patch 0041: every projection of a uniform buffer, not only the first one

- 0041 `dm/gfx/nvn/nvn_mtl.m`: the host looked for the picture's projection in a
  uniform buffer and kept **the first** matrix of that shape it found
  (`proj_scan()`), and it only accepted a **perspective** matrix. Two things
  follow from what the game does:

  - a uniform buffer can hold several matrices of that shape, and the interface's
    own matrix is not the first one (on Super Mario Odyssey the layout shaders
    bind only the uniform slot 0, the same slot the camera's matrices live in);
  - a 2D layer is drawn with an **orthographic** projection: its w row is
    `(0,0,0,1)` instead of carrying the `-1` of a perspective, and its scales are
    in canvas pixels (1/1280, 1/720), far below the range a field of view has.

  Both were invisible to the host, so the interface's matrix was never corrected
  and the present stretched it by 22% like everything else in the picture.

  Now every matrix of that shape in a buffer is found (perspective **or**
  orthographic) and corrected, the copy the GPU reads holds the whole binding so
  a matrix further down the buffer is corrected as well, and the log says what
  each buffer holds (address, rows, the matrix itself).

  - `DM_PROJ_ORTHO=0` leaves the orthographic projection alone (only a camera's
    perspective is corrected), so the change can be switched off without a new
    build.
  - `DM_PROJ_DUMP=1` writes the beginning of every uniform buffer the vertex
    stage binds to the app's Documents folder (`projbuf_<address>.bin`), once
    per buffer: it is how the interface's own matrix is found whatever shape it
    has.

Details: `D:\nxnative\out\RESEARCH_ODYSSEY_FULLSCREEN.md` (section 4.16).

## Do not regenerate

`.gitignore`, `README.md` and `dm/ios/project.yml` are not part of the patch
queue. The first two are restored to upstream; `project.yml` is the single
intentional direct edit (fullscreen launch keys).

After an upstream sync, port the hooks onto a temporary hooks branch and run
`python webui/tools/patch_queue.py regenerate`. See `webui/docs/sync.md`.
