"""Install missing runtime dependencies into a workspace-local virtual environment."""
import importlib
import importlib.metadata
import os
from pathlib import Path
import re
import subprocess
import sys

DEFAULT_INDEX = 'https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple'
PYTHON_INDEXES = (DEFAULT_INDEX, 'https://pypi.org/simple')

PACKAGES = {'fastapi': 'fastapi', 'uvicorn': 'uvicorn', 'lz4': 'lz4',
            'capstone': 'capstone', 'fonttools': 'fontTools', 'Pillow': 'PIL', 'nsz': 'nsz'}
MINIMUM = {'fastapi': (0, 115), 'uvicorn': (0, 34)}

def missing_dependencies():
    missing = []
    for package, module in PACKAGES.items():
        try:
            version = importlib.metadata.version(package)
            importlib.import_module(module)
            if package in MINIMUM:
                parts = tuple(int(x) for x in re.findall(r'\d+', version)[:2])
                if parts < MINIMUM[package] or parts >= (1, 0):
                    missing.append(package)
        except (ImportError, OSError, importlib.metadata.PackageNotFoundError):
            missing.append(package)
    return missing

def ensure_dependencies(root, repo, index_url=DEFAULT_INDEX):
    if index_url not in PYTHON_INDEXES:
        raise ValueError('Unsupported Python package source')
    missing = missing_dependencies()
    if not missing:
        return
    runtime = Path(root) / 'venv'
    python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python3')
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_EXTRA_INDEX_URL='', PIP_CACHE_DIR=str(Path(root) / 'pip-cache'))
    try:
        if not python.is_file():
            subprocess.run([sys.executable, '-m', 'venv', str(runtime)], check=True)
        probe = [str(python), str(Path(__file__).resolve()), '--check']
        if subprocess.run(probe, stdout=subprocess.DEVNULL, env=env).returncode:
            print('Installing missing Python dependencies: ' + ', '.join(missing), flush=True)
            subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--index-url', index_url,
                            '-r', str(Path(repo) / 'webui/requirements.txt')], check=True, env=env)
            subprocess.run(probe, check=True, env=env)
        else:
            print('Reusing existing Python dependency environment: ' + str(runtime), flush=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError('Automatic dependency setup failed. Check your network and Python venv/pip installation, then restart. ' + str(error)) from error
    # Use the same interpreter for the server and all build workers.
    return subprocess.run([str(python), str(Path(repo) / 'webui/launchers/start_webui.py'), *sys.argv[1:]], env=env).returncode

if __name__ == '__main__':
    raise SystemExit(bool(missing_dependencies()))
