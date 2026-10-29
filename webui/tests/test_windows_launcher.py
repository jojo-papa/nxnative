"""Offline checks for the Windows runtime downloader's trust boundaries."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[2]

@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell launcher')
class WindowsLauncherTests(unittest.TestCase):
    def run_script(self, code, directory):
        launcher = str(REPO / 'webui/launchers/start_webui_windows.ps1').replace("'", "''")
        path = Path(directory) / 'check.ps1'
        path.write_text(". '" + launcher + "'\n$script:LaunchLog = Join-Path $PSScriptRoot 'startup.log'\n" + code, encoding='utf-8')
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        result = subprocess.run([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_checksum_fallback_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.run_script(r'''$script:requests = @()
function Invoke-WebRequest($Uri, $OutFile, $TimeoutSec, [switch]$UseBasicParsing) {
    $script:requests += $Uri
    if ($Uri -eq 'mirror') { [IO.File]::WriteAllText($OutFile, 'tampered') }
    else { [IO.File]::WriteAllText($OutFile, 'abc') }
}
$entry = [PSCustomObject]@{sources=@('mirror','official');sha256='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'}
$archive = Join-Path $PSScriptRoot 'python.nupkg'
Get-CheckedArchive $entry $archive
Get-CheckedArchive $entry $archive
if (($script:requests -join ',') -ne 'mirror,official') { throw 'Wrong source order or unnecessary re-download' }
if ([IO.File]::ReadAllText($archive) -ne 'abc') { throw 'Accepted corrupted download' }
if (Test-Path ($archive + '.partial')) { throw 'Partial download remains' }
''', directory)
            self.assertIn('SHA-256 mismatch', output)
            self.assertIn('Reusing verified', output)

    def test_all_sources_fail_without_publishing_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_script(r'''function Invoke-WebRequest($Uri, $OutFile, $TimeoutSec, [switch]$UseBasicParsing) { throw 'offline' }
$entry = [PSCustomObject]@{sources=@('mirror','official');sha256='unused'}
$archive = Join-Path $PSScriptRoot 'python.nupkg'
$rejected = $false
try { Get-CheckedArchive $entry $archive } catch { $rejected = $true }
if (-not $rejected -or (Test-Path $archive)) { throw 'Failed download was accepted' }
''', directory)

    def test_archive_cannot_escape_install_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with zipfile.ZipFile(Path(directory) / 'unsafe.zip', 'w') as archive:
                archive.writestr('../escaped.txt', 'outside')
            self.run_script(r'''$rejected = $false
try { Expand-CheckedArchive (Join-Path $PSScriptRoot 'unsafe.zip') (Join-Path $PSScriptRoot 'stage') } catch { $rejected = $true }
if (-not $rejected -or (Test-Path (Join-Path $PSScriptRoot 'escaped.txt'))) { throw 'Unsafe extraction accepted' }
''', directory)

    def test_missing_runtime_fails_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_script("if (Test-ProjectPython (Join-Path $PSScriptRoot 'missing.exe')) { throw 'Missing Python accepted' }", directory)
