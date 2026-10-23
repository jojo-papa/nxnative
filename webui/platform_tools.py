"""Read-only host probes shared by detection and build workers."""
import os
from pathlib import Path
import platform
import shutil
import subprocess

def tool_path(config):
    return os.pathsep.join([str(Path(config['tools']) / 'bin'), '/opt/homebrew/bin', '/usr/local/bin', os.environ.get('PATH', '')])

def probe(command):
    try:
        result = subprocess.run([str(x) for x in command], capture_output=True, text=True, timeout=5,
                                env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_GENERATE_ASPNET_CERTIFICATE='false', DOTNET_NOLOGO='true'))
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return ''

def find_dotnet(config):
    executable = 'dotnet.exe' if platform.system() == 'Windows' else 'dotnet'
    local = Path(config['tools']) / 'dotnet' / executable
    candidates = [local]
    on_path = shutil.which(executable, path=tool_path(config))
    if on_path: candidates.append(Path(on_path))
    for directory in [os.environ.get('DOTNET_ROOT'), '/usr/local/share/dotnet', '/opt/homebrew/opt/dotnet/libexec',
                      '/opt/homebrew/share/dotnet', str(Path.home() / '.dotnet'), os.environ.get('ProgramFiles', '') + '/dotnet']:
        if directory: candidates.append(Path(directory) / executable)
    seen = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen or not candidate.is_file(): continue
        seen.add(candidate)
        sdks = probe([candidate, '--list-sdks'])
        runtimes = probe([candidate, '--list-runtimes'])
        if any(line.startswith('10.') for line in sdks.splitlines()) and any(line.startswith('Microsoft.NETCore.App 10.') for line in runtimes.splitlines()):
            return str(candidate)
    return ''

def dotnet_environment(config, env):
    env = dict(env)
    binary = find_dotnet(config)
    root = str(Path(binary).parent) if binary else str(Path(config['tools']) / 'dotnet')
    env['DOTNET_ROOT'] = root
    env['PATH'] = os.pathsep.join([root, tool_path(config)])
    return env
