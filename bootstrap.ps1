# bootstrap.ps1 — Windows helper for Quality Forge
# Unblocks scripts, checks Ollama, optionally starts the marathon loop.
param(
    [switch]$Pull,
    [switch]$Marathon,
    [int]$Max = 500
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

Write-Host "=== Quality Forge bootstrap ===" -ForegroundColor Magenta

# 1) Allow local scripts for this process (fixes UnauthorizedAccess / ExecutionPolicy)
try {
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    Write-Host "[ok] ExecutionPolicy Bypass (process)" -ForegroundColor Green
} catch {
    Write-Host "[warn] Could not set ExecutionPolicy: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Unblock downloaded files (MOTW) if present
Get-ChildItem -File -Path . -Filter *.ps1 -ErrorAction SilentlyContinue | ForEach-Object {
    try { Unblock-File -Path $_.FullName -ErrorAction SilentlyContinue } catch {}
}

# 2) Prefer python runner (cross-platform, same mechanic)
$py = $null
foreach ($c in @('python', 'python3', 'py')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source; break }
}
if (-not $py) {
    Write-Host "[err] Python not found. Install Python 3, then re-run." -ForegroundColor Red
    exit 1
}
Write-Host "[ok] Python: $py" -ForegroundColor Green

# 3) Ollama check
try {
    $tags = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 5
    $names = @($tags.models | ForEach-Object { $_.name })
    Write-Host "[ok] Ollama up. Models: $($names -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "[err] Ollama not reachable at http://localhost:11434" -ForegroundColor Red
    Write-Host "      Start the Ollama app, then re-run .\bootstrap.ps1" -ForegroundColor Yellow
    exit 1
}

if ($Pull) {
    $wanted = @(
        'qwen2.5-coder:3b',
        'qwen2.5-coder:7b-2k',
        'qwen2.5-coder:3b-8k',
        'qwen2.5-coder:14b-4k'
    )
    foreach ($m in $wanted) {
        if ($names -contains $m) {
            Write-Host "[skip] already have $m" -ForegroundColor DarkGray
            continue
        }
        Write-Host "[pull] $m ..." -ForegroundColor Cyan
        & ollama pull $m
    }
}

# 4) Doctor
& $py run.py --doctor
if ($LASTEXITCODE -ne 0) {
    Write-Host "[hint] Edit forge\models.json so 'model' tags match `ollama list`" -ForegroundColor Yellow
    Write-Host "       Or: ollama pull qwen2.5-coder:7b-2k" -ForegroundColor Yellow
    if (-not $Marathon) { exit $LASTEXITCODE }
}

if ($Marathon) {
    Write-Host "=== Starting marathon (max=$Max) ===" -ForegroundColor Magenta
    & $py run.py --loop --max $Max
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  .\bootstrap.ps1 -Marathon"
Write-Host "  python run.py --loop --max 500"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\run.ps1 -Loop"
