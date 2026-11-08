# Full wipe src + pull forge TZ + run week. After HITL: python run.py --eval
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$b = "https://raw.githubusercontent.com/pirsov/-/cursor/quality-forge-orchestrator-9409"
$files = @(
  "PROJECT_TZ.md",
  "forge/models.json",
  "forge/orchestrator.py",
  "forge/ollama_client.py",
  "forge/prompts.py",
  "forge/validator.py",
  "forge/task_parser.py"
)
foreach ($f in $files) {
  $d = Split-Path $f
  if ($d) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host "GET $f"
  Invoke-WebRequest "$b/$f" -OutFile $f -UseBasicParsing
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
Write-Host "=== week (G1… then H* y/n) ==="
python run.py --week
Write-Host "=== eval report ==="
python run.py --eval
Write-Host "Report: docs\AGENT_RUN_REPORT.md"
