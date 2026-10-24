# Syncing with upstream

Upstream: <https://github.com/seedds/nxnative>

## Current state

| Ref | Commit |
|---|---|
| sync branch (fast-forwarded into `main`) | `sync/upstream-20261024-merge` |
| pre-sync main (backup branch) | `c586dd15b01e52cb7a31732163786ab4a54101b9` on `backup/main-before-upstream-20261024` |
| upstream main (2026-10-24) | `fa69e20a280413d56e64edcb8736bf9329957f77` |
| ported hooks | `7f222f206bac6664c4a9923a56cac8807751936b` on `hooks/upstream-20261024` |
| vendor-drop equivalent | `sync/upstream-20261024` (same tree) |
| merge base | `eab15b5a7e339d172ba7cd6b1a298ec3cf1e16b6` |

The 2026-10-24 sync merges upstream `fa69e20` into `main`. Upstream-owned
files are pristine except `dm/ios/project.yml`, so the merge is clean: the
merge base is `eab15b5` and the fork tree (`webui/`, `FORK.md`, root launchers
and `.gitattributes`) does not overlap upstream. The nine hook patches were
ported onto `hooks/upstream-20261024` and regenerated; the vendor-drop
equivalent `sync/upstream-20261024` has the same tree. The pre-sync main is
kept on `backup/main-before-upstream-20261024`. Patches 0008/0009 carry the
optional separate RomFS hooks (`NX_SEPARATE_ROMFS` / `--separate-romfs`); keep
them when porting. `webui/provisional.py` mirrors upstream
`scripts/build_ipa_from_nsp.py`'s survey and provisional-profile format for the
WebUI; recheck it when that upstream code changes. The fork's ObjC launch
settings remain the launcher on both iOS paths; the Windows cross-build
compiles `launcher_stub.m` instead of the upstream SwiftUI `Launcher.swift`,
and the Mac build sets `DM_LAUNCHER=0` so the Swift launcher stays out of the
way.

The 2026-10-23 sync force-pushed `main` to a vendor drop of upstream
`eab15b5`; that history is preserved on
`backup/main-before-upstream-20261024`.

## One-time setup

```sh
python webui/tools/init_fork.py --fetch
```

This adds `upstream = https://github.com/seedds/nxnative.git` (never changes
`origin`), fetches it, and writes `.webui-data/` to `.git/info/exclude`.
Use `GIT_EXE=/path/to/git` if the shell's `git` shim is broken.

## Recommended sync: merge upstream/main

Because `main` already descends from upstream through the previous vendor drop,
a normal merge is the smallest change while upstream-owned files stay pristine.

```sh
git fetch upstream --prune
git switch -c sync/upstream-$(date +%Y%m%d) main
git merge --no-ff upstream/main
```

Then port the hooks onto a temporary branch from upstream:

```sh
git switch -c hooks/upstream-$(date +%Y%m%d) upstream/main
# Replay the previous hooks commit onto the new upstream, or apply
# webui/patches/*.patch, and resolve the hunks upstream changed:
#   git rebase --onto upstream/main <old upstream> <old hooks branch>
# Keep the fork-only behaviour (POSIX paths, no_dead_strip, MetalFX, the
# ObjC launch settings, --target mac, --separate-romfs and @NXEVENT).
git commit -am "port fork hooks onto upstream main"
```

Regenerate the patches from the sync branch (which has `webui/`), then run the
checks:

```sh
git switch sync/upstream-$(date +%Y%m%d)
python webui/tools/patch_queue.py regenerate --base upstream/main --hooks hooks/upstream-$(date +%Y%m%d)
git add webui/patches && git commit -m "regenerate hook patches against upstream main"
python webui/tools/patch_queue.py check
python webui/tools/stage.py ensure --rebuild
python webui/tools/stage.py verify
python webui/tools/sync_check.py --base upstream/main --ref upstream/main
python -m unittest discover -s webui/tests -t . -v
```

Then move `main` (fast-forward, no force needed because the sync branch starts
at `main`) and push:

```sh
git switch main && git merge --ff-only sync/upstream-$(date +%Y%m%d)
git push origin main
```

If a hook no longer exists upstream (for example `nvn_mtl.m` was rewritten),
port it by hand and record the new context in the patch; do not force the old
hunk. `sync_check.py --ref upstream/main` applies every patch with
`git apply --check` in a temporary worktree and reports failures.

## Alternative: vendor drop

When the histories have diverged too far for a clean merge, start from
upstream and copy the fork tree:

```sh
git fetch upstream --prune
git switch -c sync/upstream-$(date +%Y%m%d) upstream/main
git checkout main -- webui FORK.md .gitattributes start-webui.bat start-webui.command start-webui.sh
# Re-apply the fullscreen edit to the new dm/ios/project.yml:
#   remove UILaunchStoryboardName, add UILaunchScreen: {}, keep UIRequiresFullScreen: true
git commit -am "vendor drop: upstream main + fork webui"
```

Port the hooks as above, regenerate the patches, run the same checks, then move
`main` to the vendor-drop branch. That rewrite needs a force push: create a
fresh backup branch first and push only a verified branch.

## Publishing the fork

`origin` is `https://github.com/xbunax/nxnative.git`. Push verified branches
normally:

```sh
git push origin main
```

Do not force-push without first creating a fresh backup branch.

## Rollback

- The stage lives only in `.webui-data/stage/`; delete it to rebuild.
- The fork-only layout is a set of new/moved files; `git restore`/`git revert`
  on the refactor commit restores the old layout.
- Patches are plain text; keep the previous `webui/patches/` directory in git
  history so a failed sync can be reverted without re-deriving the diff.
