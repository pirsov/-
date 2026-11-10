# Full wipe src + pull LATEST forge (cache-busted) + week + eval
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ref = if ($env:FORGE_REF) { $env:FORGE_REF } else { "cursor/quality-forge-orchestrator-9409" }
# Locale-safe cache bust (RU Windows breaks [int](Get-Date -UFormat %s))
$bust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$b = "https://raw.githubusercontent.com/pirsov/-/$ref"
$files = @(
  "docs/TZ_GREENFIELD.md",
  "forge/models.json",
  "forge/orchestrator.py",
  "forge/ollama_client.py",
  "forge/prompts.py",
  "forge/validator.py",
  "forge/task_parser.py",
  "forge/llm.py"
)
foreach ($f in $files) {
  $d = Split-Path $f
  if ($d) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host "GET $f"
  Invoke-WebRequest "$b/$f`?t=$bust" -OutFile $f -UseBasicParsing
}

Copy-Item -Force docs\TZ_GREENFIELD.md PROJECT_TZ.md
$tz = Get-Content PROJECT_TZ.md -Raw
if ($tz -notmatch '\[ \] G1 ') {
  throw "PROJECT_TZ.md is not greenfield (no pending G1). Delete local PROJECT_TZ.md and re-run."
}
$orch = Get-Content forge\orchestrator.py -Raw
if ($orch -notmatch '--eval') {
  throw "forge/orchestrator.py missing --eval. Download failed; check network."
}

Get-ChildItem src -Recurse -Filter *.luau -File -ErrorAction SilentlyContinue | Remove-Item -Force
New-Item -ItemType Directory -Force -Path src/server/Gameplay,src/server/Level,src/server/Data,src/shared/Gameplay,src/shared/Content,src/client | Out-Null
if (Test-Path .forge\state) { Remove-Item -Recurse -Force .forge\state }
if (Test-Path logs) { Get-ChildItem logs -File -EA SilentlyContinue | Remove-Item -Force }

$env:FORGE_BACKEND = "ollama"
$env:OLLAMA_NUM_PARALLEL = "1"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue

Write-Host "=== doctor ==="
python run.py --doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "=== week (must start [G1]) ==="
python run.py --week
Write-Host "=== eval ==="
python run.py --eval
Write-Host "Report: docs\AGENT_RUN_REPORT.md"
