"""Exercise a real NSP through the HTTP task API; keep output on the game's drive."""
import argparse
import json
from pathlib import Path
import time
from fastapi.testclient import TestClient
from webui.server import create_app, data_directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('nsp', 'keys', 'tools', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--build', action='store_true', help='Also submit an iOS build after inspection')
    args = parser.parse_args()
    root = data_directory(args.out)
    app = create_app(root, 'integration-session', {'tools':args.tools})
    with TestClient(app) as client:
        client.headers['X-Session-Token'] = 'integration-session'
        def import_file(path):
            result = client.post('/api/import', json={'path':str(Path(path).resolve())})
            result.raise_for_status(); return result.json()['id']
        nsp, keys = import_file(args.nsp), import_file(args.keys)
        results = []
        for kind in (['inspect', 'build'] if args.build else ['inspect']):
            result = client.post('/api/tasks', json=dict(kind=kind, files=[nsp], keys=keys, targets=['ios']))
            result.raise_for_status(); identity = result.json()['id']
            deadline = time.monotonic() + 7200
            previous = None
            while time.monotonic() < deadline:
                state = next(t for t in client.get('/api/tasks').json() if t['id'] == identity)
                marker = state['status'], state['stage']
                if marker != previous: print(kind, *marker, flush=True); previous = marker
                if state['status'] in ('succeeded', 'failed', 'cancelled', 'interrupted'): break
                time.sleep(1)
            else:
                client.post(f'/api/tasks/{identity}/cancel')
                raise TimeoutError('Integration task exceeded two hours')
            results.append(dict(id=identity, kind=kind, status=state['status'], message=state.get('message', ''), artifacts=state['artifacts']))
            if kind == 'inspect' and state['status'] != 'succeeded':
                raise RuntimeError(state.get('message', 'Inspection failed'))
        (root / 'integration-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__': main()
