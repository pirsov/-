# Update forge files without a .git folder (zip / Cursor export).
# Run from the project root that contains run.py
$ErrorActionPreference = "Stop"
$branch = if ($env:FORGE_BRANCH) { $env:FORGE_BRANCH } else { "cursor/quality-forge-orchestrator-9409" }
$base = "https://raw.githubusercontent.com/pirsov/-/$branch"
$files = @(
    "forge/validator.py",
    "forge/prompts.py",
    "forge/orchestrator.py",
    "forge/llm.py",
    "forge/task_parser.py",
    "forge/models.json",
    "AGENTS.md",
    "docs/WEEK.md",
    "docs/FORGE_CONTRACT.md"
)
Set-Location $PSScriptRoot\..
foreach ($rel in $files) {
    $url = "$base/$rel"
    $dest = Join-Path (Get-Location) $rel
    $dir = Split-Path $dest -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Write-Host "GET $rel"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
}
Write-Host "OK. Prefer a real git clone next time:"
Write-Host "  git clone -b $branch https://github.com/pirsov/-.git forge-pull"
Write-Host "Then: python run.py --week"
