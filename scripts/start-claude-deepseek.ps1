# Launch Claude Code / FCC with DeepSeek (Anthropic-compatible API).
# Key from User env DEEPSEEK_API_KEY - never hardcode secrets.
# API models: deepseek-flash (default) | deepseek-v4-pro (set DEEPSEEK_CLAUDE_MODEL=pro)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not $env:DEEPSEEK_API_KEY) {
  $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable("DEEPSEEK_API_KEY", "User")
}
if (-not $env:DEEPSEEK_API_KEY) {
  throw "DEEPSEEK_API_KEY empty. Set User env once, open NEW shell, retry."
}
if ($env:DEEPSEEK_API_KEY.Length -lt 20) {
  throw "DEEPSEEK_API_KEY too short (len=$($env:DEEPSEEK_API_KEY.Length)). Paste full sk- key from platform.deepseek.com"
}

$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
# Claude Code warns when BOTH are set - keep AUTH_TOKEN only.
$env:ANTHROPIC_AUTH_TOKEN = $env:DEEPSEEK_API_KEY
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue

# Force model: do NOT inherit qwen from forge/ollama User env.
if ($env:DEEPSEEK_CLAUDE_MODEL -eq "pro") {
  $env:ANTHROPIC_MODEL = "deepseek-v4-pro"
} else {
  $env:ANTHROPIC_MODEL = "deepseek-flash"
}
$env:CLAUDE_CODE_USE_DEEPSEEK = "1"
$env:CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT = "1"

Write-Host "DeepSeek -> Claude | model=$($env:ANTHROPIC_MODEL) | key_len=$($env:DEEPSEEK_API_KEY.Length)"
Write-Host "  base=$($env:ANTHROPIC_BASE_URL)"

$fcc = Get-Command fcc-claude -ErrorAction SilentlyContinue
$claude = Get-Command claude -ErrorAction SilentlyContinue
$modelArgs = @("--model", $env:ANTHROPIC_MODEL) + $args
if ($fcc) {
  & fcc-claude @modelArgs
} elseif ($claude) {
  & claude @modelArgs
} else {
  Write-Host "Install FCC / Claude Code, then retry."
  throw "fcc-claude/claude not on PATH"
}
