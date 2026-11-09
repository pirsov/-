# Launch Claude Code / FCC with DeepSeek (Anthropic-compatible API).
# Key from User env DEEPSEEK_API_KEY - never hardcode secrets in this file.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY) {
  $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
}
if (-not $env:DEEPSEEK_API_KEY) {
  throw "DEEPSEEK_API_KEY empty. Set User env once, open NEW shell, retry."
}

$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_API_KEY = $env:DEEPSEEK_API_KEY
$env:ANTHROPIC_AUTH_TOKEN = $env:DEEPSEEK_API_KEY
if (-not $env:ANTHROPIC_MODEL) { $env:ANTHROPIC_MODEL = "deepseek-chat" }

Write-Host "DeepSeek -> Claude harness | model=$($env:ANTHROPIC_MODEL) | key_len=$($env:DEEPSEEK_API_KEY.Length)"

$fcc = Get-Command fcc-claude -ErrorAction SilentlyContinue
$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($fcc) {
  & fcc-claude @args
} elseif ($claude) {
  & claude @args
} else {
  Write-Host "Install FCC:"
  Write-Host '  & ([scriptblock]::Create((irm "https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/install.ps1")))'
  throw "fcc-claude/claude not on PATH"
}
