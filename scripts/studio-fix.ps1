# Pull Studio-fix TZ + forge (NO src wipe). Use after greenfield HITL fails.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ref = if ($env:FORGE_REF) { $env:FORGE_REF } else { "cursor/quality-forge-orchestrator-9409" }
# Locale-safe cache bust (RU Windows breaks [int](Get-Date -UFormat %s))
$bust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$b = "https://raw.githubusercontent.com/pirsov/-/$ref"
foreach ($f in @(
  "PROJECT_TZ.md",
  "forge/models.json",
  "forge/orchestrator.py",
  "forge/ollama_client.py",
  "forge/prompts.py",
  "forge/validator.py",
  "forge/task_parser.py",
  "forge/llm.py"
)) {
  $d = Split-Path $f
  if ($d) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host "GET $f"
  Invoke-WebRequest "$b/$f`?t=$bust" -OutFile $f -UseBasicParsing
}

$tz = Get-Content PROJECT_TZ.md -Raw
if ($tz -notmatch '\[ \] F1 ') {
  throw "PROJECT_TZ.md missing pending F1 - wrong download?"
}

$env:FORGE_BACKEND = "ollama"
$env:OLLAMA_NUM_PARALLEL = "1"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue

Write-Host "=== week (must start [F1] LevelConfig) - src kept ==="
python run.py --week
Write-Host "=== eval ==="
python run.py --eval
Write-Host "Report: docs\AGENT_RUN_REPORT.md"
