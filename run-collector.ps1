<#
.SYNOPSIS
Service entry script: loads .env then runs collector.py in the venv.
Writes stdout/stderr to rolling log files.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root    = "C:\ProgramData\GenesysAudioHookCollector"
$Venv    = Join-Path $Root "venv"
$Py      = Join-Path $Venv "Scripts\python.exe"
$App     = Join-Path $Root "collector.py"
$EnvFile = Join-Path $Root ".env"
$LogDir  = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Load .env if present (KEY=VALUE lines)
if (Test-Path $EnvFile) {
    Get-Content -LiteralPath $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -eq "" -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -gt 0) {
            $k = $line.Substring(0, $idx).Trim()
            $v = $line.Substring($idx+1).Trim()
            # Expand quotes if present
            if ($v.StartsWith('"') -and $v.EndsWith('"')) { $v = $v.Trim('"') }
            if ($v.StartsWith("'") -and $v.EndsWith("'")) { $v = $v.Trim("'") }
            [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
        }
    }
}

# Simple daily rolling logs
$stamp   = Get-Date -Format "yyyyMMdd"
$OutLog  = Join-Path $LogDir "collector-$stamp.out.log"
$ErrLog  = Join-Path $LogDir "collector-$stamp.err.log"

# Run
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Py
$psi.Arguments = '-u "{0}"' -f $App
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError  = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
[void]$proc.Start()

$swOut = [System.IO.StreamWriter]::new($OutLog, $true)
$swErr = [System.IO.StreamWriter]::new($ErrLog, $true)

try {
    while (-not $proc.HasExited) {
        if (-not $proc.StandardOutput.EndOfStream) { $swOut.WriteLine($proc.StandardOutput.ReadLine()) }
        if (-not $proc.StandardError.EndOfStream)  { $swErr.WriteLine($proc.StandardError.ReadLine()) }
        Start-Sleep -Milliseconds 100
    }
} finally {
    $swOut.Close(); $swErr.Close()
}
exit $proc.ExitCode
