"""A serial subprocess queue. JSONL is the only task-state store."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from .repo import ensure_git_exclude

TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def read_events(path, offset=0, limit=256 * 1024):
    if not Path(path).exists():
        return [], 0
    rows = []
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        while stream.tell() - offset < limit:
            before = stream.tell()
            line = stream.readline()
            if not line or not line.endswith(b'\n'):
                stream.seek(before); break
            try:
                rows.append(json.loads(line))
            except (ValueError, UnicodeDecodeError):
                pass
        return rows, stream.tell()


def emit(directory, kind, **data):
    row = dict(time=time.time(), kind=kind, **data)
    with (Path(directory) / 'events.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row) + '\n')
        stream.flush()


def summary(directory):
    result = json.loads((directory / 'task.json').read_text(encoding='utf-8'))
    result.update(status='queued', artifacts=[], stage='Waiting')
    cursor = 0
    while True:
        rows, end = read_events(directory / 'events.jsonl', cursor)
        for event in rows:
            if event['kind'] == 'status':
                result['status'] = event['status']
                result['message'] = event.get('message', '')
            if event['kind'] == 'stage':
                result['stage'] = event['name']
            if event['kind'] == 'artifact':
                result['artifacts'].append(event['name'])
        if end == cursor:
            return result
        cursor = end


def terminate(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


class Jobs:
    def __init__(self, root, repo, config):
        self.root, self.repo, self.config = Path(root), Path(repo), config
        ensure_git_exclude()
        self.directory = self.root / 'tasks'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pending, self.process, self.active = [], None, None
        self.stop = threading.Event()
        self.service_file = (self.root / '.service.lock').open('a+b')
        if self.service_file.tell() == 0:
            self.service_file.write(b'0'); self.service_file.flush()
        self.service_file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.service_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.service_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.service_file.close()
            raise ValueError('Another WebUI is already using this data folder') from error
        for folder in self.directory.iterdir():
            if (folder / 'task.json').is_file():
                state = summary(folder)
                if state['status'] not in TERMINAL:
                    # Remove only an incomplete tail before appending recovery status.
                    data = (folder / 'events.jsonl').read_bytes() if (folder / 'events.jsonl').exists() else b''
                    end = data.rfind(b'\n') + 1
                    with (folder / 'events.jsonl').open('wb') as stream:
                        stream.write(data[:end])
                    emit(folder, 'status', status='interrupted', message='Service stopped before completion. Retry manually.')
                    self.clear_keys(folder)
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def folder(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity):
            raise ValueError('Invalid task ID')
        folder = self.directory / identity
        if not (folder / 'task.json').exists():
            raise ValueError('Task not found')
        return folder

    def create(self, task):
        with self.lock:
            identity = uuid.uuid4().hex
            folder = self.directory / identity
            folder.mkdir()
            task = dict(task, id=identity, created=time.time())
            write_json(folder / 'task.json', task)
            emit(folder, 'status', status='queued')
            self.pending.append(identity)
            return identity

    def clear_keys(self, folder):
        task = json.loads((folder / 'task.json').read_text(encoding='utf-8'))
        if not task.get('retain_keys'):
            (folder / 'private.keys').unlink(missing_ok=True)
        # Only delete service-owned uploads; user-imported originals stay untouched.
        source = Path(task.get('keys', '')).resolve()
        if source.parent == (self.root / 'inbox').resolve() and source.suffix == '.keys':
            waiting = [json.loads((self.directory / identity / 'task.json').read_text(encoding='utf-8'))
                       for identity in self.pending]
            if not any(item.get('keys') == str(source) for item in waiting):
                source.unlink(missing_ok=True)

    def cancel(self, identity):
        folder = self.folder(identity)
        with self.lock:
            if summary(folder)['status'] in TERMINAL:
                return
            if identity in self.pending:
                self.pending.remove(identity)
            if self.active == identity and self.process:
                terminate(self.process)
            emit(folder, 'status', status='cancelled')
            self.clear_keys(folder)

    def run(self):
        while not self.stop.wait(.25):
            with self.lock:
                if not self.pending:
                    continue
                identity = self.pending.pop(0)
                folder = self.folder(identity)
                self.active = identity
                emit(folder, 'status', status='running')
                env = dict(os.environ, PYTHONUTF8='1', PYTHONUNBUFFERED='1')
                env['NX_WEB_CONFIG'] = json.dumps(self.config)
                env['NX_STAGE_ROOT'] = str(self.root / 'stage')
                toolroot = Path(self.config.get('tools') or self.root / 'tools')
                env['PATH'] = os.pathsep.join([str(toolroot / 'dotnet'), str(toolroot / 'bin'), '/opt/homebrew/bin', '/usr/local/bin', env.get('PATH', '')])
                env['PYTHONPATH'] = os.pathsep.join([str(toolroot / 'python-packages'), str(self.repo)])
                env['DOTNET_CLI_HOME'] = str(toolroot / '.dotnet')
                from .platform_tools import dotnet_environment
                env = dotnet_environment(dict(self.config, tools=str(toolroot)), env)
                env['NUGET_PACKAGES'] = str(toolroot / 'nuget')
                env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_GENERATE_ASPNET_CERTIFICATE='false', DOTNET_NOLOGO='true')
                temporary = folder / 'tmp'; temporary.mkdir(exist_ok=True)
                env.update(TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary))
                flags = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
                try:
                    log = (folder / 'build.log').open('ab')
                    self.process = subprocess.Popen([sys.executable, '-m', 'webui.worker', str(folder)],
                        cwd=self.repo, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **flags)
                    log.close()
                except Exception as error:
                    emit(folder, 'status', status='failed', message=str(error))
                    self.clear_keys(folder)
                    self.active = None
                    continue
            self.process.wait()
            with self.lock:
                if summary(folder)['status'] not in TERMINAL:
                    emit(folder, 'status', status='failed', message='Worker exited before reporting completion. See build.log.')
                self.clear_keys(folder)
                self.process, self.active = None, None

    def close(self):
        self.stop.set()
        with self.lock:
            for identity in ([self.active] if self.active else []) + self.pending:
                folder = self.directory / identity
                if summary(folder)['status'] not in TERMINAL:
                    emit(folder, 'status', status='interrupted', message='Service stopped before completion. Retry manually.')
            if self.process:
                terminate(self.process)
        self.thread.join(timeout=20)
        with self.lock:
            pending = self.pending[:]
            self.pending.clear()
            for identity in pending: self.clear_keys(self.directory / identity)
        self.service_file.close()
