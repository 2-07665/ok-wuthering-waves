$root = Split-Path -Parent $MyInvocation.MyCommand.Path; Set-Location $root
$p = Start-Process "$root/.venv/Scripts/python.exe" "auto_stamina.py" -WorkingDirectory $root -PassThru
Wait-Process -Id $p.Id -Timeout 600
if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force }
shutdown /s /t 0