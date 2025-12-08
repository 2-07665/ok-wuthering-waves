$root = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"

$p = Start-Process -FilePath $python `
                   -ArgumentList "auto_stamina.py" `
                   -WorkingDirectory $root `
                   -PassThru -NoNewWindow -Wait

$exitCode = $p.ExitCode
if ($null -eq $exitCode) {
    Write-Host "Stamina run finished but exit code was not available (pid=$($p.Id))."
    exit 1
}

if ($exitCode -eq 0) {
    Write-Host "Process completed."
} else {
    Write-Error "Process exited with code $exitCode"
}

exit $exitCode
