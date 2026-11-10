# Pull Studio-fix TZ + forge (NO src wipe). ASCII-only. RU-locale safe.
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
if ($tz -notmatch '\[ \] F1 ') {
  throw "PROJECT_TZ.md missing pending F1 - wrong download?"
}
$orch = Get-Content forge\orchestrator.py -Raw
if ($orch -notmatch 'add_argument\("--week"') {
  throw "forge/orchestrator.py missing --week - wrong download?"
}
if ($orch -notmatch 'add_argument\("--eval"') {
  throw "forge/orchestrator.py missing --eval - wrong download?"
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw "python not on PATH" }
Write-Host "python: $($py.Source)"

$env:FORGE_BACKEND = "ollama"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SPACE_BUNNY_API_KEY -ErrorAction SilentlyContinue

Write-Host "=== pending F1 check ==="
python -c "from forge.task_parser import find_pending_tasks; t=open('PROJECT_TZ.md',encoding='utf-8').read(); p=find_pending_tasks(t); print('next=', p[0].task_id if p else None); raise SystemExit(0 if p and p[0].task_id=='F1' else 1)"
if ($LASTEXITCODE -ne 0) { throw "pending task is not F1" }

Write-Host "=== week (F1..) sleep=0 - src kept ==="
# sleep 0 so fix sprint does not idle 30s between tasks; surface stderr
python -u run.py --week --sleep 0 2>&1 | ForEach-Object { $_ }
if ($LASTEXITCODE -ne 0) { throw "week exited with code $LASTEXITCODE" }

Write-Host "=== eval ==="
python -u run.py --eval 2>&1 | ForEach-Object { $_ }
Write-Host "Report: docs\AGENT_RUN_REPORT.md"
