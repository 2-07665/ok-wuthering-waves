$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$shutdownFlag = 64  # bit set by auto_daily when shutdown is requested via Google Sheets

$p = Start-Process -FilePath $python `
                   -ArgumentList "auto_daily.py" `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow

$exited = $p.WaitForExit(1200 * 1000)

if (-not $exited) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
    shutdown.exe /s /t 0
}
else {
    $rawExit = $p.ExitCode
    $shouldShutdown = ($rawExit -band $shutdownFlag) -ne 0
    $exitCode = $rawExit -band 0x3F  # strip shutdown flag

    if ($exitCode -eq 0) {
        Write-Host "Process completed."
    } else {
        Write-Error "Process exited with code $exitCode (raw $rawExit)"
    }

    if ($shouldShutdown) {
        Write-Host "Shutdown requested by sheet; powering off..."
        shutdown.exe /s /t 0
    }
}
