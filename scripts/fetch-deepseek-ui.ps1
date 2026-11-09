# Pull DeepSeek UI + compact skills + game1 src (no git required)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

$ref = if ($env:FORGE_REF) { $env:FORGE_REF } else { "b4cba5c3b8894b91118f3e3f666af40919a4dfa2" }
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
  "skills/compact/forge-ui-animation/SKILL.md",
  "skills/compact/forge-ui-modern/SKILL.md",
  "scripts/start-claude-deepseek.ps1",
  "scripts/start-claude-deepseek.bat",
  "forge/progress_hub.py",
  "forge/run_hub.py",
  "scripts/continue-week.ps1",
  "ui/index.html",
  "ui/app.js",
  "ui/styles.css",
  "skills/registry.json",
  "skills/README.md",
  "skills/compact/forge-player-attrs/SKILL.md",
  "skills/compact/forge-luau-touch/SKILL.md",
  "projects/game1/meta.json",
  "projects/game1/PROJECT_TZ.md",
  "projects/game1/src/shared/Gameplay/Remotes.luau",
  "projects/game1/src/shared/Content/LevelConfig.luau",
  "projects/game1/src/server/InitRemotes.server.luau",
  "projects/game1/src/server/Level/Generator.server.luau",
  "projects/game1/src/server/Gameplay/Checkpoints.server.luau",
  "projects/game1/src/server/Gameplay/Coins.server.luau",
  "projects/game1/src/server/Gameplay/Void.server.luau",
  "projects/game1/src/server/Gameplay/Puzzles.server.luau",
  "projects/game1/src/server/Data/PlayerData.server.luau",
  "projects/game1/src/server/Example.server.luau",
  "projects/game1/src/client/HUD.client.luau",
  "projects/game1/src/client/Effects.client.luau",
  "projects/game1/src/client/Leaderboard.client.luau",
  # curated raw (so DeepSeek can pick; small set)
  "skills/raw/ash/roblox-luau-architecture/SKILL.md",
  "skills/raw/ash/roblox-debugging-bugfix/SKILL.md",
  "skills/raw/ash/roblox-ui-implementation/SKILL.md",
  "skills/raw/ash/roblox-game-ux/SKILL.md",
  "skills/raw/ash/roblox-world-level-design/SKILL.md",
  "skills/raw/sypho/roblox-code/SKILL.md",
  "skills/raw/sypho/roblox-ui/SKILL.md",
  "skills/raw/sypho/roblox-map/SKILL.md",
  "skills/raw/sypho/roblox-code/references/traps.md",
  "skills/raw/sypho/roblox-code/references/patterns.md"
)

foreach ($f in $files) {
  $d = Split-Path $f
  if ($d) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
  Write-Host "GET $f"
  try {
    Invoke-WebRequest -Uri "$b/$f`?t=$bust" -OutFile $f -UseBasicParsing
  } catch {
    Write-Host "SKIP $f ($($_.Exception.Message))"
  }
}

$orch = Get-Content forge\orchestrator.py -Raw
if ($orch -notmatch '--ui') {
  throw "forge/orchestrator.py missing --ui - wrong download?"
}
$ds = Get-Content forge\deepseek.py -Raw
if ($ds -notmatch 'horror_coins_tz_fallback') {
  Write-Host "WARN: deepseek.py may be stale; re-run with newer ref"
}

$luau = @(Get-ChildItem projects\game1\src -Recurse -Filter *.luau -ErrorAction SilentlyContinue)
Write-Host "game1 luau files: $($luau.Count)"
$raw = @(Get-ChildItem skills\raw -Recurse -Filter SKILL.md -ErrorAction SilentlyContinue)
Write-Host "raw skills: $($raw.Count)"

Write-Host "OK. Restart UI:"
Write-Host "  python -u run.py --ui"
Write-Host "  http://127.0.0.1:8787"
