# Syncing with upstream

Upstream: <https://github.com/seedds/nxnative>

## Current state

| Ref | Commit |
|---|---|
| stable fork main (previous) | `77dee3dab542d19a76e0cbb7175d3b6726ad275c` (based on `233f18f`) |
| upstream main (2026-10-23) | `eab15b5a7e339d172ba7cd6b1a298ec3cf1e16b6` |
| sync branch | `sync/upstream-20261023` (vendor drop of upstream `eab15b5`) |
| ported hooks | `18e488271dd3a0bbd17a7a5d2acadc6b1f648cf1` |
| merge base | `bc5815acc975ba223dff72df8a5cc98c43e97e0e` |

The sync branch is a vendor drop: it starts at upstream `eab15b5`, the fork
tree (`webui/`, `FORK.md`, root launchers and `.gitattributes`) was copied
from `77dee3d`, and the nine hook patches were ported and regenerated against
`upstream/main`. The previous fork main stays stable until this branch is
validated on Apple hardware. Patches 0008/0009 carry the optional separate
RomFS hooks (`NX_SEPARATE_ROMFS` / `--separate-romfs`); keep them when porting.
The fork's ObjC launch settings remain the launcher on both iOS paths; the
Windows cross-build compiles `launcher_stub.m` instead of the upstream
SwiftUI `Launcher.swift`, and the Mac build sets `DM_LAUNCHER=0` so the Swift
launcher stays out of the way.

## One-time setup

```sh
python webui/tools/init_fork.py --fetch
```

This adds `upstream = https://github.com/seedds/nxnative.git` (never changes
`origin`), fetches it, and writes `.webui-data/` to `.git/info/exclude`.
Use `GIT_EXE=/path/to/git` if the shell's `git` shim is broken.

## Recommended sync: vendor drop

Because all upstream-owned files are pristine except `dm/ios/project.yml`,
a vendor drop has the smallest conflict surface.

```sh
git fetch upstream --prune
git switch -c sync/upstream-$(date +%Y%m%d) upstream/main
git checkout main -- webui FORK.md .gitattributes start-webui.bat start-webui.command
# Re-apply the fullscreen edit to the new dm/ios/project.yml:
#   remove UILaunchStoryboardName, add UILaunchScreen: {}, keep UIRequiresFullScreen: true
git commit -am "vendor drop: upstream main + fork webui"
```

Then port the hooks onto a temporary branch:

```sh
git switch -c hooks/upstream-$(date +%Y%m%d) upstream/main
python webui/tools/patch_queue.py check --tree .
# Manually port the nine targets; keep the patch 0009 fixes:
#   top-level import json, and webui/build/macos/pack_app.py
git commit -am "port nxnative fork hooks to upstream/main"
python webui/tools/patch_queue.py regenerate --base upstream/main --hooks HEAD
```

Merge the refreshed patches into the sync branch, then run the checks:

```sh
python webui/tools/stage.py ensure --rebuild
python webui/tools/stage.py verify
python webui/tools/sync_check.py --base upstream/main --offline
python -m unittest discover -s webui/tests -t . -v
```

If a hook no longer exists upstream (for example `nvn_mtl.m` was rewritten),
port it by hand and record the new context in the patch; do not force the old
hunk. `sync_check.py --ref upstream/main` applies every patch with
`git apply --check` in a temporary worktree and reports failures.

## Ordinary merge alternative

`git merge upstream/main` is possible but will produce broad conflicts because
the histories diverged. Resolve on a dedicated branch, run the same patch
refresh and checks, and keep `dm/ios/project.yml` as the only direct upstream
edit.

## Publishing the fork

After the refactor, upstream sync and tests are complete:

```sh
git push origin main
```

`origin` is `https://github.com/xbunax/nxnative.git`. Push only a verified
branch; do not force-push. If the sync branch is reviewed separately, push that
branch first and open a pull request instead of rewriting `main`.

## Rollback

- The stage lives only in `.webui-data/stage/`; delete it to rebuild.
- The fork-only layout is a set of new/moved files; `git restore`/`git revert`
  on the refactor commit restores the old layout.
- Patches are plain text; keep the previous `webui/patches/` directory in git
  history so a failed sync can be reverted without re-deriving the diff.
