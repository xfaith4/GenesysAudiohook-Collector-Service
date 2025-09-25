<#
.SYNOPSIS
Installs Genesys AudioHook Collector as a Windows service.

.NOTES
- Creates a venv under C:\ProgramData\GenesysAudioHookCollector\venv
- Copies collector.py, topics.json, .env (if present)
- Registers service 'GenesysAudioHookCollector' running run-collector.ps1
- Works on PowerShell 5.1 and 7+
#>

[CmdletBinding()]
param(
    [string]$InstallRoot = "C:\ProgramData\GenesysAudioHookCollector",
    [string]$ServiceName = "GenesysAudioHookCollector",
    [string]$DisplayName = "Genesys AudioHook Collector",
    [string]$Description = "Streams Genesys AudioHook operational events to Elastic.",
    [switch]$StartAfterInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# -- Prep folders -------------------------------------------------------------
if (-not (Test-Path $InstallRoot)) { New-Item -ItemType Directory -Path $InstallRoot | Out-Null }
$venvPath = Join-Path $InstallRoot "venv"
$logDir   = Join-Path $InstallRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

# -- Copy app files -----------------------------------------------------------
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Required: collector.py
Copy-Item -LiteralPath (Join-Path $here "collector.py") -Destination (Join-Path $InstallRoot "collector.py") -Force

# Optional: topics.json, .env, run-collector.ps1 (we always copy our launcher)
if (Test-Path (Join-Path $here "topics.json")) { Copy-Item (Join-Path $here "topics.json") $InstallRoot -Force }
if (Test-Path (Join-Path $here ".env")) { Copy-Item (Join-Path $here ".env") $InstallRoot -Force }
Copy-Item -LiteralPath (Join-Path $here "run-collector.ps1") -Destination (Join-Path $InstallRoot "run-collector.ps1") -Force

# -- Python + venv ------------------------------------------------------------
# Find python.exe (prefer py launcher, then PATH python)
function Get-Python {
    try {
        $py = (Get-Command py -ErrorAction Stop).Path
        # Resolve to actual python path
        $ver = & $py -3 -c "import sys,shutil;print(shutil.which('python'))"
        if ($LASTEXITCODE -eq 0 -and $ver) { return $ver.Trim() }
    } catch {}
    try {
        return (Get-Command python -ErrorAction Stop).Path
    } catch {
        throw "Python not found. Install Python 3.9+ and re-run."
    }
}
$python = Get-Python

# Create venv
if (-not (Test-Path $venvPath)) {
    & $python -m venv $venvPath
}
# Upgrade pip + install deps
$pip = Join-Path $venvPath "Scripts\pip.exe"
& $pip install --upgrade pip | Out-Null
& $pip install aiohttp | Out-Null

# -- Register service ---------------------------------------------------------
# We run the launcher script under powershell.exe so we can load .env before Python.
$pwsh = (Get-Command powershell.exe -ErrorAction SilentlyContinue).Path
if (-not $pwsh) { throw "powershell.exe not found." }

$launcher = Join-Path $InstallRoot "run-collector.ps1"
# IMPORTANT: BinPath must be quoted properly
$binPath = '"{0}" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "{1}"' -f $pwsh, $launcher

# Stop and remove existing service if present
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne 'Stopped') { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue }
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 2
}

# Create service
New-Service -Name $ServiceName -BinaryPathName $binPath -DisplayName $DisplayName -Description $Description -StartupType Automatic | Out-Null

Write-Host "Service '$ServiceName' installed."
Write-Host "Files in: $InstallRoot"
Write-Host "Logs in:  $logDir"

if ($StartAfterInstall) {
    Start-Service -Name $ServiceName
    Write-Host "Service started."
} else {
    Write-Host "Start it with: Start-Service $ServiceName"
}
