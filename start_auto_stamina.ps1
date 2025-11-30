$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"

$p = Start-Process -FilePath $python `
                   -ArgumentList "auto_stamina.py" `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow

$exited = $p.WaitForExit(600 * 1000)

if (-not $exited) {
    try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
    shutdown.exe /s /t 0
}
else {
    if ($p.ExitCode -eq 0) {
        Write-Host "Process completed."
    } else {
        Write-Error "Process exited with code $($p.ExitCode)"
    }
}
