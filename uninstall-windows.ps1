[CmdletBinding()]
param(
    [string]$ServiceName = "GenesysAudioHookCollector",
    [switch]$RemoveFiles
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    if ($svc.Status -ne 'Stopped') { Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue }
    sc.exe delete $ServiceName | Out-Null
    Write-Host "Service removed: $ServiceName"
} else {
    Write-Host "Service not found: $ServiceName"
}

if ($RemoveFiles) {
    $root = "C:\ProgramData\GenesysAudioHookCollector"
    if (Test-Path $root) {
        Remove-Item -Recurse -Force $root
        Write-Host "Removed files at $root"
    }
}
