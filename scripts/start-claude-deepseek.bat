@echo off
REM Launch Claude Code / FCC routed to DeepSeek Anthropic-compatible API.
REM Do NOT paste your key into this file. Set User env DEEPSEEK_API_KEY once.
REM DeepSeek Anthropic endpoint accepts ONLY: deepseek-flash | deepseek-v4-pro

setlocal EnableExtensions EnableDelayedExpansion

if "%DEEPSEEK_API_KEY%"=="" (
  for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')"`) do set "DEEPSEEK_API_KEY=%%A"
)

if "%DEEPSEEK_API_KEY%"=="" (
  echo ERROR: DEEPSEEK_API_KEY is empty.
  echo Set it once:
  echo   powershell -Command "[Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY','sk-YOUR_KEY','User')"
  echo Then open a NEW cmd window and run this bat again.
  exit /b 1
)

REM Force DeepSeek Anthropic endpoint. Clear Ollama/qwen bleed from User env.
set "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic"
REM Claude Code: use AUTH_TOKEN only (both vars together break auth).
set "ANTHROPIC_AUTH_TOKEN=%DEEPSEEK_API_KEY%"
set "ANTHROPIC_API_KEY="

REM Always force model - ignore leftover ANTHROPIC_MODEL=qwen... from forge/ollama.
if /I "%DEEPSEEK_CLAUDE_MODEL%"=="pro" (
  set "ANTHROPIC_MODEL=deepseek-v4-pro"
) else (
  set "ANTHROPIC_MODEL=deepseek-flash"
)
set "CLAUDE_CODE_USE_DEEPSEEK=1"
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1"

cd /d "%~dp0\.."

REM No raw pipe chars in echo - cmd treats | as pipe.
echo DeepSeek -^> Claude
echo   model=!ANTHROPIC_MODEL!
echo   base=!ANTHROPIC_BASE_URL!
powershell -NoProfile -Command "if ($env:DEEPSEEK_API_KEY.Length -lt 20) { exit 2 } else { Write-Host ('  key_len=' + $env:DEEPSEEK_API_KEY.Length) }"
if errorlevel 2 (
  echo ERROR: key looks too short - need full sk-... from platform.deepseek.com
  exit /b 2
)

where fcc-claude >nul 2>nul
if !ERRORLEVEL!==0 (
  echo Starting fcc-claude --model !ANTHROPIC_MODEL! ...
  fcc-claude --model !ANTHROPIC_MODEL! %*
  exit /b !ERRORLEVEL!
)

where claude >nul 2>nul
if !ERRORLEVEL!==0 (
  echo Starting claude --model !ANTHROPIC_MODEL! ...
  claude --model !ANTHROPIC_MODEL! %*
  exit /b !ERRORLEVEL!
)

echo Neither fcc-claude nor claude found on PATH.
echo Install Free Claude Code first, then re-run this bat.
exit /b 3
