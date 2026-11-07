# Rebuild build/game.rbxlx from current src/ (requires Rojo on PATH)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
if (-not (Get-Command rojo -ErrorAction SilentlyContinue)) {
    Write-Host "Rojo not found. Install: https://rojo.space/docs/installation/"
    Write-Host "Or use Rojo plugin: rojo serve  + Connect in Studio (preferred)."
    exit 1
}
New-Item -ItemType Directory -Force -Path build | Out-Null
rojo build default.project.json --output build/game.rbxlx
Write-Host "OK -> build/game.rbxlx  (File > Open in Studio, or prefer rojo serve)"
