# Force local Ollama for this PowerShell window (ignores dead OpenRouter user env keys).
$ErrorActionPreference = "Stop"
$env:FORGE_BACKEND = "ollama"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue
Write-Host "FORGE_BACKEND=$env:FORGE_BACKEND"
Write-Host "OPENROUTER_API_KEY cleared for this session: $([string]::IsNullOrEmpty($env:OPENROUTER_API_KEY))"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "WARN: ollama not on PATH — start Ollama app / ollama serve"
}
Set-Location $PSScriptRoot\..
python run.py --doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python run.py --week
