@echo off
REM Launch Claude Code (or FCC) routed to DeepSeek via Anthropic-compatible API.
REM Do NOT paste your key into this file. Set User env DEEPSEEK_API_KEY once.

setlocal EnableExtensions

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

REM DeepSeek Anthropic-compatible endpoint (Claude Code / FCC)
set "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic"
set "ANTHROPIC_API_KEY=%DEEPSEEK_API_KEY%"
set "ANTHROPIC_AUTH_TOKEN=%DEEPSEEK_API_KEY%"
if "%ANTHROPIC_MODEL%"=="" set "ANTHROPIC_MODEL=deepseek-chat"
if "%CLAUDE_CODE_USE_DEEPSEEK%"=="" set "CLAUDE_CODE_USE_DEEPSEEK=1"

cd /d "%~dp0\.."

echo DeepSeek key: loaded (len check only)
powershell -NoProfile -Command "if ($env:DEEPSEEK_API_KEY.Length -lt 12) { exit 2 } else { Write-Host ('  length=' + $env:DEEPSEEK_API_KEY.Length) }"
if errorlevel 2 (
  echo ERROR: key looks too short
  exit /b 2
)

where fcc-claude >nul 2>nul
if %ERRORLEVEL%==0 (
  echo Starting fcc-claude ...
  fcc-claude %*
  exit /b %ERRORLEVEL%
)

where claude >nul 2>nul
if %ERRORLEVEL%==0 (
  echo Starting claude ...
  claude %*
  exit /b %ERRORLEVEL%
)

echo Neither fcc-claude nor claude found on PATH.
echo Install Free Claude Code first:
echo   powershell -Command "& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/Alishahryar1/free-claude-code/main/scripts/install.ps1')))"
echo Then re-run this bat.
exit /b 3
