# Continue pending TZ tasks (e.g. after Generator FAIL). No wipe.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$env:FORGE_BACKEND = "ollama"
$env:PYTHONUNBUFFERED = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
Write-Host "Continuing --week from first pending task..."
python -u run.py --week --sleep 0 --hitl y
Write-Host "Done. Re-open UI panel 4 or run: python -u run.py --eval"
