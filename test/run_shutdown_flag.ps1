$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
$script = Join-Path $root "test\test_shutdown_flag.py"
$shutdownFlag = 64

$p = Start-Process -FilePath $python `
                   -ArgumentList $script `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow -Wait

$rawExit = $p.ExitCode
$shouldShutdown = ($rawExit -band $shutdownFlag) -ne 0

Write-Host "shutdown_after_daily flag from sheet: $shouldShutdown"
Write-Host "Raw exit code: $rawExit"

exit $rawExit
