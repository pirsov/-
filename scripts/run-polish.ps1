# Pull polish TZ + forge (NO src wipe). Run P1.. then HITL H5..
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ref = if ($env:FORGE_REF) { $env:FORGE_REF } else { "cursor/quality-forge-orchestrator-9409" }
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
  Invoke-WebRequest -Uri "$b/$f`?t=$bust" -OutFile $f -UseBasicParsing
}

$tz = Get-Content PROJECT_TZ.md -Raw
if ($tz -notmatch '\[ \] P1 ') {
  throw "PROJECT_TZ.md missing pending P1 - wrong download?"
}

$env:FORGE_BACKEND = "ollama"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue

Write-Host "=== week polish (must start [P1]) - src kept ==="
python -u run.py --week --sleep 0 2>&1 | ForEach-Object { $_ }
if ($LASTEXITCODE -ne 0) { throw "week exited with code $LASTEXITCODE" }
Write-Host "=== eval ==="
python -u run.py --eval 2>&1 | ForEach-Object { $_ }
Write-Host "Report: docs\AGENT_RUN_REPORT.md"
