# nxnative fork: WebUI and Windows build support

This repository is a fork of [seedds/nxnative](https://github.com/seedds/nxnative).
Upstream code lives at its original paths (`dm/`, `scripts/`, `docs/`, `README.md`)
and is kept clean so that upstream can be fetched and merged without carrying fork
changes in every file.

Fork-owned code lives under `webui/`, with the root launchers and `FORK.md`
beside it and the upstream-sync workflow under `.github/`:

| Path | Purpose |
|---|---|
| `webui/` | Local build studio (FastAPI), task queue, launchers, tool preparation |
| `webui/build/windows/` | Windows iOS cross-compile, shader build and IPA packer |
| `webui/build/macos/` | macOS application wrapper and packager |
| `webui/overlays/dm/` | Fork-only source files placed into the staged `dm/` tree |
| `webui/patches/` | Upstream hook patches applied only to the build staging tree |
| `webui/launchers/` | Canonical launchers (thin wrappers are at the repository root) |
| `webui/tools/` | Staging, patch queue, sync checks and helper CLIs |
| `webui/docs/` | WebUI guide, plan, validation data and upstream sync notes |
| `.github/workflows/upstream-sync.yml` | Fork-only upstream-sync automation; other `.github` files are upstream-owned |

## Start

Windows: double-click `start-webui.bat` (or `webui\launchers\start_webui.bat`).
macOS: run `./start-webui.sh` in a terminal (or double-click `start-webui.command`; the internal launcher is `webui/launchers/start_webui.sh`).

The launchers keep their data in the repository's `.webui-data/` directory. That
directory is local-only and is added to `.git/info/exclude`; the upstream
`.gitignore` is not modified.

## Builds use a stage

A build never writes into the upstream working tree. `webui/staging.py` copies
the repository into `.webui-data/stage/<key>/tree`, applies the seven overlays and
the ten patches under `webui/patches/`, and runs the build from that copy. The
stage is reused until a source file or patch changes.

The Windows shader build gets a translation chain of its own: its Metal,
SPIRV-Cross and .NET paths differ from the repository's Mac ones, so its chain
version differs from `dm/gfx/nvn/dmsh_chain.h`. The host is compiled with that
version (a source that includes the chain version header is compiled from a
shadow copy that carries it), and the packed shader libraries are named after
it. The repository's chain header, its lock and the upstream sources stay
untouched. See `webui/docs/webui.md`.

The only intentional direct edit to an upstream file is `dm/ios/project.yml`,
which declares the iOS fullscreen launch configuration (`UIRequiresFullScreen`
and `UILaunchScreen`). Everything else is a patch or an overlay.

The optional **Separate IPA and RomFS** iOS build is off by default. When
selected, the IPA leaves out `romfs/` and the task also produces a
`<title>.romfs.zip` (top-level `romfs/`) with `webui/build/romfs_archive.py`;
the Windows builder and patches 0008/0009 carry the hooks. The app reads
`Documents/romfs` with no app-side change. macOS `.app.zip` stays self-contained.

## Windows toolchain differences

`webui/build/windows/windows_shader_build.py` builds a private copy of the
shader tool chain and has to satisfy a few assumptions the upstream macOS path
never meets:

- `dmsh_chain.py --header` writes the chain version header into
  `dm/gfx/nvn/`, so the copy needs that directory to exist.
- `dmsh_build.py` runs `c1_guard.py` and `cb_extent.py` from its own directory
  at the end of a full build, and `cb_extent.py` imports `c1_guard.py` from
  there. Both are copied into the chain tree; `c1_guard.py` is not a `dmsh_*`
  file, so a copy loop that only matches `dmsh_*.py` misses it.
- The Windows SPIRV-Cross fingerprint is taken from the executable the caller
  passes, because the upstream fingerprint looks the tool up on `PATH` and
  Windows cannot resolve it from an absolute path.
- Every `subprocess` call that captures text output uses `errors="replace"`,
  because the Windows console code page is not UTF-8 and the upstream calls
  would raise `UnicodeDecodeError` on any non-ASCII byte.

The Windows host compiler is LLVM 23, which turned
`-Wincompatible-pointer-types` into an error. Upstream code relies on it being
a warning, so `ios_cross_compile.py` adds `-Wno-incompatible-pointer-types`
instead of patching the upstream sources.

The Windows IPA is unsigned, like the upstream macOS one: the packer writes no
`_CodeSignature/` and no `embedded.mobileprovision`. See the sideloading
section in `webui/docs/webui.md` for what that means for the Increased Memory
Limit entitlement.

## Upstream sync

The upstream remote is `https://github.com/seedds/nxnative.git`. The recorded
sync refs are in `webui/patches/UPSTREAM_BASE`; `webui/docs/sync.md` is the
authoritative procedure.

GitHub Actions runs `.github/workflows/upstream-sync.yml`:

- the daily scheduled run uses `auto/upstream-sync` and fast-forwards `main`
  only after the merge, hook port, patch regeneration, staging, `sync_check`
  and tests pass;
- a manual `workflow_dispatch` uses `review/upstream-sync` and opens a PR for a
  human to merge; it never moves `main`;
- `hooks/upstream-sync` is an internal audit branch;
- any failure stops the run, keeps the evidence and opens/updates an Issue or
  draft PR. There is no automatic vendor-drop fallback or conflict resolution.

Push local `main` before enabling the workflow so the remote base is current.
The workflow needs write permissions and, for review mode, permission to
create pull requests; upstream workflow-file changes also need the
`SYNC_TOKEN` Actions secret (a PAT with Contents, Workflows, Issues and Pull
requests write). See `webui/docs/sync.md`. The local CLI is
`webui/tools/sync_upstream.py`. `webui/tools/sync_check.py` reports
upstream-owned edits and patch applicability.

See `webui/README.md` for the developer overview.
