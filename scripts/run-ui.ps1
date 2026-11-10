# Start Quality Forge control UI (projects / skills / DeepSeek / smoke)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:PYTHONUNBUFFERED = "1"
Write-Host "Set DEEPSEEK_API_KEY for compress+TZ (optional; heuristic works without)."
Write-Host "UI: http://127.0.0.1:8787"
python -u run.py --ui --ui-port 8787
