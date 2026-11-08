# Fresh week: clear forge runtime state. Does NOT wipe src/ seeds.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$env:FORGE_BACKEND = "ollama"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue

if (Test-Path .forge\state) {
    Remove-Item -Recurse -Force .forge\state
    Write-Host "cleared .forge/state"
}
if (Test-Path logs) {
    Get-ChildItem logs -File | Remove-Item -Force
    Write-Host "cleared logs/"
}

# Ensure TZ is the fresh Z-sprint from repo copy if present next to script — user may overwrite PROJECT_TZ.md
Write-Host "FORGE_BACKEND=$env:FORGE_BACKEND"
Write-Host "Next:"
Write-Host "  python run.py --doctor"
Write-Host "  python run.py --validate"
Write-Host "  python run.py --week"
Write-Host "After agent: rojo serve + Studio Connect (not a stale .rbxlx alone)"
