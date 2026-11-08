# Fresh greenfield week: clear forge runtime. Optional -WipeSrc clears all *.luau under src/
param([switch]$WipeSrc)
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
    Get-ChildItem logs -File -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host "cleared logs/"
}
if ($WipeSrc -and (Test-Path src)) {
    Get-ChildItem src -Recurse -Filter *.luau -File | Remove-Item -Force
    Write-Host "wiped src/**/*.luau (greenfield)"
}

Write-Host "FORGE_BACKEND=$env:FORGE_BACKEND"
Write-Host "Next: python run.py --doctor ; python run.py --week"
Write-Host "After G*: rojo serve + Studio Connect"
