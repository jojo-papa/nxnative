"""Repository paths and small fork-wide helpers (no imports from upstream code)."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
UPSTREAM_URL = 'https://github.com/seedds/nxnative.git'
DOCS_URL = 'https://github.com/xbunax/nxnative/blob/main/webui/docs/webui.md'

# Local git excludes.  The upstream .gitignore is an upstream-owned file, so
# the fork's own build products are excluded here instead of by editing it.
# out/ holds the packaged IPAs, the screenshots and the research notes: it is
# output, not source, and it must never reach the repository or a stage tree
# (rule R-16).
DATA_EXCLUDES = ('.webui-data/', 'out/')


def load_game_module():
    """Import dm/games/game.py from the upstream tree without polluting sys.path."""
    games = REPO / 'dm' / 'games'
    if str(games) not in sys.path:
        sys.path.insert(0, str(games))
    import game
    return game


def ensure_git_exclude(entries=DATA_EXCLUDES):
    """Keep local WebUI data out of git without editing the upstream .gitignore."""
    git = REPO / '.git'
    if not git.is_dir():
        return False
    exclude = git / 'info' / 'exclude'
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        lines = exclude.read_text(encoding='utf-8').splitlines() if exclude.exists() else []
        changed = False
        for entry in entries:
            if entry not in lines:
                lines.append(entry)
                changed = True
        if changed:
            exclude.write_text('\n'.join(lines).rstrip('\n') + '\n', encoding='utf-8')
        return True
    except OSError:
        return False
