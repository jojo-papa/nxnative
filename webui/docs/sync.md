# Syncing with upstream

Upstream: <https://github.com/seedds/nxnative>

## Current state

| Ref | Commit |
|---|---|
| fork base | `233f18f421344fcd3b61559459ef8649d6c38a54` |
| fork reference | `a8bfd0ddac3a976b770e05db64f3932d29772ce8` |
| upstream main (2026-10-23) | `a08bbdd3ba144a6de4db39576cd0512786573eb7` |

The histories have diverged (the GitHub compare reported 125 commits ahead and
27 behind relative to the base). The nine hook patches in `webui/patches/` are
pinned to the fork base. Patches 0008/0009 also carry the optional separate
RomFS hooks (`NX_SEPARATE_ROMFS` / `--separate-romfs`); keep them when porting.
Do not merge upstream blind; port the hooks first.

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
