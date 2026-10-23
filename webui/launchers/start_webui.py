#!/usr/bin/env python3
"""Start the local nxnative WebUI (terminal or Spyder F5)."""
import argparse
import os
import json
from pathlib import Path
import secrets
import sys
import threading
import webbrowser

DATA_DIR = ''
PORT = 8765
OPEN_BROWSER = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', default=DATA_DIR)
    parser.add_argument('--tools', help='Prepared tool directory (or NX_TOOLS_DIR)')
    parser.add_argument('--port', type=int, default=PORT)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    folder = args.data_dir or os.environ.get('NX_DATA_DIR') or str(repo / '.webui-data')
    root = Path(folder).expanduser().resolve()
    if root == Path(root.anchor) or root == Path.home().resolve():
        parser.error('Choose a dedicated data subdirectory, not the filesystem or home root')
    root.mkdir(parents=True, exist_ok=True)
    from webui.repo import ensure_git_exclude
    ensure_git_exclude()
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    toolroot = args.tools or os.environ.get('NX_TOOLS_DIR') or config.get('tools') or str(root / 'tools')
    sys.path.append(str(Path(toolroot).resolve() / 'python-packages'))
    from webui.bootstrap import DEFAULT_INDEX, ensure_dependencies
    try:
        child_status = ensure_dependencies(root, repo, config.get('python_index', DEFAULT_INDEX))
        if child_status is not None:
            return child_status
        import uvicorn
        from webui.server import create_app, data_directory
        root = data_directory(root)
    except (RuntimeError, ImportError, ValueError, OSError) as error:
        parser.error(str(error))
    print('Data folder: ' + str(root), flush=True)
    token = secrets.token_urlsafe(32)
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    if toolroot: config['tools'] = str(Path(toolroot).resolve())
    app = create_app(root, token, config)
    url = f'http://127.0.0.1:{args.port}/#{token}'
    print('Open in your browser: ' + url, flush=True)
    if OPEN_BROWSER and not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, access_log=False)
    finally:
        app.state.jobs.close()


if __name__ == '__main__':
    raise SystemExit(main())
