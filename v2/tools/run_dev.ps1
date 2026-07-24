param()
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$V2 = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Server = Start-Process -FilePath "cargo" -ArgumentList @("run", "-p", "rust-companion-v2-server") -WorkingDirectory $V2 -PassThru
try { Set-Location (Join-Path $V2 "apps\desktop"); npm run tauri dev }
finally { if (-not $Server.HasExited) { Stop-Process -Id $Server.Id -Force } }
