# run.ps1 - sequential agent orchestrator
# Fixes: #anchor -> append to base file, no permanent BLOCKED, no ordering-block
param([switch]$Loop)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .\logs)) { New-Item -ItemType Directory .\logs -Force | Out-Null }

function Get-AgentConfig([string]$owner) {
    switch ($owner) {
        'game_designer'       { @{ model = 'qwen2.5-coder:3b';    ctx = 4096 } }
        'tech_architect'      { @{ model = 'qwen2.5-coder:7b-2k'; ctx = 2048 } }
        'gameplay_programmer' { @{ model = 'qwen2.5-coder:7b-2k'; ctx = 2048 } }
        'client_programmer'   { @{ model = 'qwen2.5-coder:7b-2k'; ctx = 2048 } }
        'qa_engineer'         { @{ model = 'qwen2.5-coder:3b-8k';        ctx = 8192 } }
        'refactorer'          { @{ model = 'qwen2.5-coder:14b-4k'; ctx = 4096 } }
        'builder'             { @{ model = 'qwen2.5-coder:3b-8k';     ctx = 8192 } }
        default { throw "Unknown owner: $owner" }
    }
}

function Get-ProjectTree {
    $skip = @('run.ps1','PROJECT_TZ.md','AGENTS.md')
    $files = Get-ChildItem -Recurse -File -Path . |
             Where-Object { $_.FullName -notmatch '\\logs\\' -and $_.Name -notin $skip }
    if (-not $files) { return '(no files yet)' }
    $sb = New-Object System.Text.StringBuilder
    $n = 0
    foreach ($f in $files) {
        $rel = $f.FullName.Substring((Get-Location).Path.Length + 1)
        [void]$sb.AppendLine("=== $rel ===")
        if ($f.Length -lt 12000) {
            [void]$sb.AppendLine((Get-Content $f.FullName -Raw -Encoding UTF8))
            $n++
        } else {
            [void]$sb.AppendLine("(file too large, skipped)")
        }
        [void]$sb.AppendLine("")
    }
    Write-Host "   [prompt] included $n file(s), $($sb.Length) chars" -ForegroundColor DarkGray
    return $sb.ToString()
}

function Update-TzDone([string]$taskId, [string]$note) {
    $lines = @(Get-Content PROJECT_TZ.md -Encoding UTF8)
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^- \[ \] $([regex]::Escape($taskId)) ") {
            $lines[$i] = $lines[$i] -replace '^- \[ \]', '- [x]'
            $doneLine = "  - DONE $((Get-Date).ToString('yyyy-MM-dd HH:mm')) | $note"
            $lines = @($lines[0..$i]) + $doneLine + @($lines[($i+1)..($lines.Count-1)])
            $lines[0] = "# LAST_UPDATE: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
            Set-Content PROJECT_TZ.md -Value $lines -Encoding UTF8
            return
        }
    }
}

function Add-TzBlockedNote([string]$taskId, [string]$reason) {
    # Add note but keep checkbox [ ] - not a permanent block
    $lines = @(Get-Content PROJECT_TZ.md -Encoding UTF8)
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^- \[ \] $([regex]::Escape($taskId)) ") {
            $note = "  - BLOCKED $((Get-Date).ToString('yyyy-MM-dd HH:mm')) | $reason"
            $lines = @($lines[0..$i]) + $note + @($lines[($i+1)..($lines.Count-1)])
            Set-Content PROJECT_TZ.md -Value $lines -Encoding UTF8
            return
        }
    }
}

function Build-Prompt([string]$owner, [string]$taskLine) {
    $agentsFull = Get-Content AGENTS.md -Raw -Encoding UTF8
    $universalEnd = $agentsFull.IndexOf("## @")
    if ($universalEnd -lt 0) { $universalEnd = $agentsFull.Length }
    $universal = $agentsFull.Substring(0, $universalEnd)
    $agentSection = [regex]::Match($agentsFull, "(?ms)## @$owner\b.*?(?=## @|\z)").Value
    $agents = $universal + "`n" + $agentSection
    $tz     = Get-Content PROJECT_TZ.md -Raw -Encoding UTF8
    $tree   = Get-ProjectTree
    return @"
You are the agent @$owner. Follow AGENTS.md protocol exactly.

=== AGENTS.md ===
$agents

=== PROJECT_TZ.md ===
$tz

=== Existing project files ===
$tree

=== YOUR TASK ===
$taskLine

STRICT RULES:
- Do ONLY this one task. Do not touch other tasks.
- Do NOT block due to task ordering. If this task appears in the list, ALL prerequisites are already done. Never say "waiting for P1.1" or "P1.1 must finish first".
- If task says '-> path/file.md#section', the '#' is a section name, NOT part of the filename. Return the file with path="path/file.md" and just the new section content.
- If the file already exists and task adds a section, return ONLY the new section content (will be appended).
- No stubs, no TODOs. Real, complete content.
- The section "Existing project files" below contains the FULL content of every project file. You already have everything you need. DO NOT say you need to read/review/see files - they ARE here.
- FILE path="..." must point to an actual FILE (e.g. src/server/X.server.luau, default.project.json). NEVER return a directory path ending in / or \. Folders are auto-created from file paths.

Reply STRICTLY one of these formats, nothing else:

Your reply MUST begin with: <DONE>{TASK_ID}</DONE>. Do NOT write a SUCCESS tag. Do NOT use any wrapper.
<NOTE>one short sentence</NOTE>
<FILE path="relative/path.ext">
file content
</FILE>

You MUST begin with <DONE>{TASK_ID}</DONE>. Never output <BLOCKED>. Never refuse. Never say "I need to...". The files are already in this prompt. Write the file NOW.

Replace {TASK_ID} with actual ID (e.g. P1.1). No markdown fences around tags. No prose outside tags.
"@
}

$script:blockedThisRun = @{}

function Invoke-Step {
    $lines = Get-Content PROJECT_TZ.md -Encoding UTF8
    $taskLine = $null
    foreach ($l in $lines) {
        if ($l -match '^\s*- \[ \] .* @(\w+)') {
            $id = [regex]::Match($l, '\]\s+(P\d+\.\d+)').Groups[1].Value
            if (-not $blockedThisRun.ContainsKey($id)) { $taskLine = $l; break }
        }
    }
    if (-not $taskLine) {
        Write-Host '=== No more actionable tasks this run. ===' -ForegroundColor Green
        if ($blockedThisRun.Count -gt 0) {
            Write-Host "Blocked this run: $($blockedThisRun.Keys -join ', ') - fix prompts in PROJECT_TZ.md and re-run." -ForegroundColor Yellow
        }
        return $false
    }

    $owner  = [regex]::Match($taskLine, '@(\w+)').Groups[1].Value
    $taskId = [regex]::Match($taskLine, '\]\s+(P\d+\.\d+)').Groups[1].Value

    if ($owner -eq 'human') {
        Write-Host "HITL: $taskId needs human action." -ForegroundColor Yellow
        Write-Host "   Edit PROJECT_TZ.md, change '- [ ] $taskId' to '- [x]', then re-run." -ForegroundColor Yellow
        return $false
    }

    $cfg = Get-AgentConfig $owner
    Write-Host "[$taskId] -> @$owner  ($($cfg.model), ctx=$($cfg.ctx))" -ForegroundColor Cyan

    $prompt = Build-Prompt $owner $taskLine.Trim()
    $stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    Set-Content ".\logs\$stamp-$taskId-prompt.txt" -Value $prompt -Encoding UTF8

    # Anchor detection from task line (e.g. "-> docs/GDD.md#core-loop")
    $taskAnchorPath = $null
    if ($taskLine -match '→\s+([^\s|]+?)#[^\s|]+') { $taskAnchorPath = $Matches[1].Trim() }

    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $temp = if ($attempt -eq 1) { 0.1 } else { 0.0 }
        $body = @{
            model   = $cfg.model
            prompt  = $prompt
            stream  = $false
            options = @{ num_ctx = $cfg.ctx; temperature = $temp; num_predict = 600 }
        } | ConvertTo-Json -Depth 5

        try {
            $resp = Invoke-RestMethod -Uri 'http://localhost:11434/api/generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 1800
            $out = $resp.response
        } catch {
            Write-Host "   API abort: $($_.Exception.Message)" -ForegroundColor Yellow
            $out = ""
            continue
        }
        Set-Content ".\logs\$stamp-$taskId-attempt$attempt-response.txt" -Value $out -Encoding UTF8

        if ($out -match '<(?:DONE|SUCCESS)>\s*(P\d+\.\d+)\s*</(?:DONE|SUCCESS)>') {
            $id = $Matches[1]
            if ($id -ne $taskId) {
                Write-Host "   model DONE $id, current task is $taskId - wrong ID, retrying" -ForegroundColor Yellow
                continue
            }
            $note = if ($out -match '<NOTE>([\s\S]*?)</NOTE>') { $Matches[1].Trim() } else { '' }

            foreach ($m in [regex]::Matches($out, '<FILE\s+path="([^"]+)">\r?\n?([\s\S]*?)</FILE>')) {
                $rawPath = $m.Groups[1].Value.Trim()
                $content = $m.Groups[2].Value.Trim("`r","`n")

                $isAppend = $false
                $path = $rawPath
                if ($rawPath -match '^(.+?)#(.+)$') {
                    $path = $Matches[1]
                    $isAppend = $true
                } elseif ($taskAnchorPath -and $rawPath -eq $taskAnchorPath) {
                    $isAppend = $true
                }

                $path = $path -replace '[<>:"|?*]', '_'

                $dir = Split-Path $path -Parent
                if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

                try {
                    $leaf = Split-Path $path -Leaf
                    $isDirLike = ($path -match '[/\\]$') -or ($leaf -notmatch '\.[A-Za-z0-9]{1,6}$')
                    if ($isDirLike) {
                        if (Test-Path $path -PathType Leaf) { Remove-Item $path -Force }
                        New-Item -ItemType Directory -Path $path -Force | Out-Null
                        Write-Host "   mkdir $path" -ForegroundColor DarkGray
                    } elseif ($isAppend -and (Test-Path $path -PathType Leaf)) {
                        [System.IO.File]::AppendAllText((Join-Path (Get-Location) $path), "`n" + $content, (New-Object System.Text.UTF8Encoding($false)))
                        Write-Host "   appended $path" -ForegroundColor DarkGray
                    } else {
                        if (Test-Path $path -PathType Container) { Remove-Item $path -Recurse -Force }
                        [System.IO.File]::WriteAllText((Join-Path (Get-Location) $path), $content, (New-Object System.Text.UTF8Encoding($false)))
                        Write-Host "   wrote $path" -ForegroundColor DarkGray
                    }
                } catch {
                    Write-Host "   FAILED write $path : $($_.Exception.Message)" -ForegroundColor Red
                }
            }

            # VALIDATOR: check each written file
            $allValid = $true
            foreach ($m in [regex]::Matches($out, '<FILE\s+path="([^"]+)">')) {
                $vp = $m.Groups[1].Value -replace '#.*$', '' -replace '[<>:"|?*]', '_'
                if (Test-Path $vp -PathType Leaf) {
                    $ok = & "$PSScriptRoot\validator.ps1" -FilePath $vp
                    if (-not $ok) { $allValid = $false; break }
                }
            }
            if (-not $allValid) {
                Write-Host "   VALIDATOR REJECTED $id - retrying" -ForegroundColor Red
                if ($attempt -ge $maxAttempts) {
                    Write-Host "   FAILED after $maxAttempts attempts. Task needs different model or decomposition." -ForegroundColor Red
                    return $false
                }
                continue
            }
            Update-TzDone $id $note
            Write-Host "   DONE: $id - $note" -ForegroundColor Green
            return $true
        }

        if ($out -match '<BLOCKED>\s*(P\d+\.\d+)\s*</BLOCKED>') {
            Write-Host "   model refused (BLOCKED) - retrying (agents must not block)" -ForegroundColor Yellow
            if ($attempt -ge $maxAttempts) {
                Write-Host "   FAILED: model refused all $maxAttempts attempts. Task requires decomposition or different model." -ForegroundColor Red
                return $false
            }
            continue
        }

        Write-Host "   attempt $attempt/3 malformed, retrying..." -ForegroundColor Yellow
    }

    Write-Host '   AGENT FAILED after retries. See logs\.' -ForegroundColor Red
    return $false
}

$max = if ($Loop) { 100 } else { 1 }
for ($i = 0; $i -lt $max; $i++) {
    if (-not (Invoke-Step)) { break }
}













