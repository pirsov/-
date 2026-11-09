# Pull DeepSeek UI + skills hub + game1 snapshot (no git required)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ref = if ($env:FORGE_REF) { $env:FORGE_REF } else { "bc42d83" }
$bust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$b = "https://raw.githubusercontent.com/pirsov/-/$ref"

$files = @(
  "run.py",
  "PROJECT_TZ.md",
  "forge/orchestrator.py",
  "forge/prompts.py",
  "forge/validator.py",
  "forge/task_parser.py",
  "forge/llm.py",
  "forge/models.json",
  "forge/ollama_client.py",
  "forge/deepseek.py",
  "forge/skills_hub.py",
  "forge/projects_hub.py",
  "forge/ui_server.py",
  "ui/index.html",
  "ui/app.js",
  "ui/styles.css",
  "skills/registry.json",
  "skills/README.md",
  "skills/compact/forge-player-attrs/SKILL.md",
  "skills/compact/forge-luau-touch/SKILL.md",
  "projects/game1/meta.json"
)

foreach ($f in $files) {
  $d = Split-Path $f
  if ($d) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host "GET $f"
  Invoke-WebRequest -Uri "$b/$f`?t=$bust" -OutFile $f -UseBasicParsing
}

$orch = Get-Content forge\orchestrator.py -Raw
if ($orch -notmatch '--ui') {
  throw "forge/orchestrator.py missing --ui - wrong download?"
}

Write-Host "OK. Next:"
Write-Host '  $env:DEEPSEEK_API_KEY="sk-..."   # one sk- prefix only'
Write-Host "  python -u run.py --ui"
Write-Host "  open http://127.0.0.1:8787"
