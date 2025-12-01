$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$shutdownFlag = 64  # bit set by auto_daily when shutdown is requested via Google Sheets
$logFile = Join-Path $root "start_auto_daily.log"

function Write-Log($message) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "$timestamp`t$message"
}

try {
    $logDir = Split-Path $logFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
} catch {}

$p = Start-Process -FilePath $python `
                   -ArgumentList "auto_daily.py" `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow

$exited = $p.WaitForExit(1200 * 1000)

if (-not $exited) {
    Write-Log "Daily run exceeded timeout; killing process and shutting down."
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { Write-Log "Failed to stop process: $($_.Exception.Message)" }
    shutdown.exe /s /t 0
    exit 1
}

$rawExit = $p.ExitCode
$shouldShutdown = ($rawExit -band $shutdownFlag) -ne 0
$exitCode = $rawExit -band 0x3F  # strip shutdown flag

Write-Log "Daily run finished: rawExit=$rawExit exitCode=$exitCode shutdown=$shouldShutdown"

if ($exitCode -eq 0) {
    Write-Host "Process completed."
} else {
    Write-Error "Process exited with code $exitCode (raw $rawExit)"
}

if ($shouldShutdown) {
    Write-Host "Shutdown requested by sheet; powering off..."
    shutdown.exe /s /t 0
}

exit $exitCode
