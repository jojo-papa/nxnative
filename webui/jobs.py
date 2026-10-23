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


BUILD_STAGE_PROGRESS = (
    ('preparing staged sources', 0.02),
    ('building ', 0.03),
    ('converting xci', 0.04),
    ('decompress', 0.04),
    ('build nx_extract', 0.05),
    ('survey', 0.05),
    ('prepare xcode', 0.70),
    ('verify', 0.36),
    ('rewrite', 0.30),
    ('dlc', 0.22),
    ('extract', 0.15),
    ('glslc', 0.32),
    ('decode', 0.34),
    ('capture', 0.34),
    ('heap check', 0.35),
    ('shader split', 0.45),
    ('shader_split', 0.45),
    ('windows_shaders', 0.62),
    ('shaders', 0.62),
    ('app build', 0.80),
    ('host_compile', 0.82),
    ('embed_', 0.87),
    ('host_link', 0.92),
    ('ipa pack', 0.95),
    ('ipa_pack', 0.95),
    ('romfs_archive', 0.98),
    ('copied output', 0.99),
)


def stage_progress(name):
    text = str(name).lower()
    for needle, fraction in BUILD_STAGE_PROGRESS:
        if needle in text:
            return fraction
    return None


def task_progress(task, status, events):
    kind = task.get('kind')
    if kind == 'convert':
        if status == 'succeeded':
            return 100
        last = None
        for event in events:
            if event.get('kind') == 'progress' and event.get('total'):
                last = event
        if last:
            return max(0, min(99, int(100 * last['done'] / last['total'])))
        return 0
    if kind != 'build':
        return None
    targets = task.get('targets') or []
    if not targets:
        return None
    if status == 'succeeded':
        return 100
    done, fraction, target_fraction = 0, 0.0, 0.0
    failed_target_fraction = None
    for event in events:
        if event.get('kind') == 'target':
            if len(targets) == 1 and event.get('status') == 'failed':
                failed_target_fraction = target_fraction
            done += 1
            fraction = 0.0
            target_fraction = 0.0
        elif event.get('kind') == 'stage':
            value = stage_progress(event.get('name', ''))
            if value is not None:
                fraction = max(fraction, value)
                target_fraction = max(target_fraction, value)
    progress = int(100 * (done + fraction) / len(targets))
    if failed_target_fraction is not None:
        progress = int(100 * failed_target_fraction)
    elif status in ('failed', 'cancelled', 'interrupted'):
        progress = min(progress, 99)
    return max(0, min(100, progress))


def summary(directory):
    result = json.loads((directory / 'task.json').read_text(encoding='utf-8'))
    result.update(status='queued', artifacts=[], stage='Waiting')
    cursor, events = 0, []
    while True:
        rows, end = read_events(directory / 'events.jsonl', cursor)
        events.extend(rows)
        for event in rows:
            if event['kind'] == 'status':
                result['status'] = event['status']
                result['message'] = event.get('message', '')
            if event['kind'] == 'stage':
                result['stage'] = event['name']
            if event['kind'] == 'artifact':
                result['artifacts'].append(event['name'])
        if end == cursor:
            result['progress'] = task_progress(result, result['status'], events)
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
        # The keys upload stays in the inbox for reuse. Delete it explicitly from
        # the upload history when it is no longer needed.

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
