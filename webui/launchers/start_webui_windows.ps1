# First-run Windows launcher. No system Python, administrator access or PATH changes.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-LaunchMessage([string]$Message) {
    Write-Host $Message
    Add-Content -LiteralPath $script:LaunchLog -Value $Message -Encoding UTF8
}

function Test-ProjectPython([string]$Executable) {
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -I -c "import sys,struct,ssl,pip,venv,ensurepip;sys.exit(0 if sys.version_info >= (3,11) and struct.calcsize('P') == 8 else 1)" 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Get-ArchiveHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Get-CheckedArchive($Entry, [string]$Archive) {
    if ((Test-Path -LiteralPath $Archive) -and ((Get-ArchiveHash $Archive) -eq $Entry.sha256)) {
        Write-LaunchMessage 'Reusing verified Python download.'
        return
    }
    foreach ($source in $Entry.sources) {
        $partial = $Archive + '.partial'
        try {
            Write-LaunchMessage ('Downloading Python: ' + $source)
            Invoke-WebRequest -UseBasicParsing -Uri $source -OutFile $partial -TimeoutSec 90
            if ((Get-ArchiveHash $partial) -ne $Entry.sha256) {
                throw 'Python archive SHA-256 mismatch; refusing to execute it.'
            }
            Move-Item -LiteralPath $partial -Destination $Archive -Force
            return
        } catch {
            Write-LaunchMessage ('Download failed: ' + $_.Exception.Message)
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
            Write-LaunchMessage 'Trying the next configured source, if available.'
        }
    }
    throw 'Python download failed from all sources. Check the network and retry this launcher.'
}

function Expand-CheckedArchive([string]$Archive, [string]$Destination) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $prefix = [IO.Path]::GetFullPath($Destination).TrimEnd('\') + '\'
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($entry in $zip.Entries) {
            $target = [IO.Path]::GetFullPath((Join-Path $Destination $entry.FullName))
            if (-not $target.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw 'Unsafe Python archive member.'
            }
        }
    } finally { $zip.Dispose() }
    [IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Destination)
}

function Get-ProjectPython([string]$Repository) {
    $data = Join-Path $Repository '.webui-data'
    $runtime = Join-Path $data 'runtime'
    $python = Join-Path $runtime 'python.exe'
    if (Test-ProjectPython $python) {
        Write-LaunchMessage ('Using project Python: ' + $python)
        return $python
    }
    $lock = $null
    $stage = $null
    try {
        try { $lock = [IO.File]::Open((Join-Path $data 'python-install.lock'), 'OpenOrCreate', 'ReadWrite', 'None') }
        catch { throw 'Another launcher is preparing Python. Wait for it to finish before starting again.' }
        if (Test-ProjectPython $python) { return $python }
        $manifest = Get-Content -LiteralPath (Join-Path $Repository 'webui/launchers/python-windows.json') -Raw | ConvertFrom-Json
        $architecture = $env:PROCESSOR_ARCHITEW6432
        if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
        if ($architecture -notin @('AMD64', 'ARM64')) { throw 'The local runtime requires 64-bit Windows (AMD64 or ARM64).' }
        $entry = $manifest.architectures.$architecture
        $downloads = Join-Path $data 'downloads'
        New-Item -ItemType Directory -Path $downloads -Force | Out-Null
        $archive = Join-Path $downloads ('python-' + $manifest.version + '-' + $architecture + '.nupkg')
        Get-CheckedArchive $entry $archive
        $stage = Join-Path $data ('python-stage-' + [Guid]::NewGuid().ToString('N'))
        Write-LaunchMessage 'Extracting and verifying project-local Python...'
        Expand-CheckedArchive $archive $stage
        $prepared = Join-Path $stage 'tools'
        if (-not (Test-ProjectPython (Join-Path $prepared 'python.exe'))) { throw 'The downloaded Python runtime could not start on this Windows installation.' }
        if (Test-Path -LiteralPath $runtime) {
            Move-Item -LiteralPath $runtime -Destination ($runtime + '.previous-' + [Guid]::NewGuid().ToString('N'))
        }
        Move-Item -LiteralPath $prepared -Destination $runtime
        Write-LaunchMessage ('Python installed: ' + $python)
        return $python
    } finally {
        if ($lock) { $lock.Dispose() }
        if ($stage -and (Test-Path -LiteralPath $stage)) {
            $resolvedStage = [IO.Path]::GetFullPath($stage)
            $allowedParent = [IO.Path]::GetFullPath($data).TrimEnd('\') + '\'
            if ($resolvedStage.StartsWith($allowedParent, [StringComparison]::OrdinalIgnoreCase)) {
                Remove-Item -LiteralPath $resolvedStage -Recurse -Force
            }
        }
    }
}

function Start-ProjectWebUI([string[]]$Arguments) {
    $repository = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
    $data = Join-Path $repository '.webui-data'
    New-Item -ItemType Directory -Path $data -Force | Out-Null
    $script:LaunchLog = Join-Path $data 'startup.log'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $env:PYTHONHOME = $null
        $env:PYTHONPATH = $null
        $env:PYTHONUTF8 = '1'
        $env:PYTHONUNBUFFERED = '1'
        [Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
        Write-LaunchMessage ('Starting WebUI: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
        $python = Get-ProjectPython $repository
        # Native Python stderr contains normal server progress as well as errors.
        $ErrorActionPreference = 'Continue'
        & $python -u (Join-Path $repository 'webui/launchers/start_webui.py') @Arguments 2>&1 | ForEach-Object { Write-LaunchMessage $_.ToString() }
        $status = $LASTEXITCODE
        if ($status -ne 0) { Write-LaunchMessage ('WebUI exited with code ' + $status + '. Startup log: ' + $script:LaunchLog) }
        return $status
    } catch {
        Write-LaunchMessage ('Startup failed: ' + $_.Exception.Message)
        return 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Start-ProjectWebUI -Arguments @($args))
}
