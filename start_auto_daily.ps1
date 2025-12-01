$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$shutdownFlag = 64  # bit set by auto_daily when shutdown is requested via Google Sheets

$p = Start-Process -FilePath $python `
                   -ArgumentList "auto_daily.py" `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow -Wait

$rawExit = $p.ExitCode
if ($null -eq $rawExit) {
    Write-Host "Daily run finished but exit code was not available (pid=$($p.Id))."
    exit 1
}
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
