"""Repository paths and small fork-wide helpers (no imports from upstream code)."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
UPSTREAM_URL = 'https://github.com/seedds/nxnative.git'
DOCS_URL = 'https://github.com/xbunax/nxnative/blob/main/webui/docs/webui.md'

DATA_EXCLUDES = ('.webui-data/',)


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
