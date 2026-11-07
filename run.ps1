# run.ps1 - Quality Forge orchestrator (PowerShell)
# Critical fixes vs previous version:
#   1. APPEND tasks always append (do not overwrite)
#   2. DONE without <FILE> is rejected when task has → path
#   3. Validator failures roll back to snapshot and feed errors into retry
#   4. Higher num_predict + relevant-file prompt budget
#   5. Auto-decompose after persistent failure
# Prefer: python run.py --loop   (cross-platform; same mechanic)
param(
    [switch]$Loop,
    [int]$Max = -1,
    [double]$SleepSec = 0
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .\logs)) { New-Item -ItemType Directory .\logs -Force | Out-Null }
if (-not (Test-Path .\.forge\snapshots)) { New-Item -ItemType Directory .\.forge\snapshots -Force | Out-Null }
if (-not (Test-Path .\.forge\state)) { New-Item -ItemType Directory .\.forge\state -Force | Out-Null }

function Get-InstalledOllamaModels {
    try {
        $resp = Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -Method Get -TimeoutSec 5
        return @($resp.models | ForEach-Object { $_.name })
    } catch {
        return @()
    }
}

function Resolve-OllamaModel([string]$preferred, [string[]]$installed) {
    if (-not $installed -or $installed.Count -eq 0) { return $preferred }
    if ($installed -contains $preferred) { return $preferred }
    $base = ($preferred -split ':')[0]
    $hit = $installed | Where-Object { $_ -like "$base*" } | Select-Object -First 1
    if ($hit) { return $hit }
    $coder = $installed | Where-Object { $_ -match 'coder' } | Select-Object -First 1
    if ($coder) { return $coder }
    return $installed[0]
}

function Get-AgentConfig([string]$owner, [int]$attempt) {
    # Prefer the user's original custom tags (7b-2k / 14b-4k / 3b-8k), not bare :7b/:14b
    $base = switch ($owner) {
        'game_designer'       { @{ model = 'qwen2.5-coder:3b';     ctx = 4096; predict = 2048 } }
        'tech_architect'      { @{ model = 'qwen2.5-coder:7b-2k';  ctx = 2048; predict = 2048 } }
        'gameplay_programmer' { @{ model = 'qwen2.5-coder:7b-2k';  ctx = 2048; predict = 3072 } }
        'client_programmer'   { @{ model = 'qwen2.5-coder:7b-2k';  ctx = 2048; predict = 3072 } }
        'qa_engineer'         { @{ model = 'qwen2.5-coder:3b-8k';  ctx = 8192; predict = 3072 } }
        'refactorer'          { @{ model = 'qwen2.5-coder:14b-4k'; ctx = 4096; predict = 4096 } }
        'builder'             { @{ model = 'qwen2.5-coder:3b-8k';  ctx = 8192; predict = 2048 } }
        'systems_designer'    { @{ model = 'qwen2.5-coder:3b-8k';  ctx = 8192; predict = 3072 } }
        'content_author'      { @{ model = 'qwen2.5-coder:3b';     ctx = 4096; predict = 3072 } }
        'integrator'          { @{ model = 'qwen2.5-coder:7b-2k';  ctx = 2048; predict = 4096 } }
        default { throw "Unknown owner: $owner" }
    }
    if ($attempt -ge 2) {
        $ladder = @('qwen2.5-coder:3b','qwen2.5-coder:7b-2k','qwen2.5-coder:14b-4k')
        $idx = [Math]::Min($attempt - 1, $ladder.Count - 1)
        $base.model = $ladder[$idx]
        $base.predict = [Math]::Max($base.predict, 4096)
    }
    $installed = Get-InstalledOllamaModels
    $resolved = Resolve-OllamaModel $base.model $installed
    if ($resolved -ne $base.model) {
        Write-Host "   model remap: $($base.model) -> $resolved" -ForegroundColor DarkYellow
        $base.model = $resolved
    }
    return $base
}

function Get-TaskMode([string]$taskLine) {
    if ($taskLine -match '\bAPPEND\b') { return 'append' }
    if ($taskLine -match '\bRewrite\b|\bfrom scratch\b|\bwith exactly\b') { return 'rewrite' }
    if ($taskLine -match '\bCreate\b|\bWrite\b') { return 'create' }
    if ($taskLine -match '→\s+[^\s#]+#[^\s|]+') { return 'append' }
    return 'rewrite'
}

function Get-TaskTarget([string]$taskLine) {
    if ($taskLine -match '→\s+([^\s|#]+)') { return $Matches[1].Trim() }
    return $null
}

function Save-Snapshot([string]$rel) {
    if (-not (Test-Path $rel -PathType Leaf)) { return }
    $dest = Join-Path '.\.forge\snapshots' ($rel -replace '[\\/]', '__')
    $dir = Split-Path $dest -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    Copy-Item $rel $dest -Force
}

function Restore-Snapshot([string]$rel) {
    $src = Join-Path '.\.forge\snapshots' ($rel -replace '[\\/]', '__')
    if (Test-Path $src -PathType Leaf) {
        $dir = Split-Path $rel -Parent
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Copy-Item $src $rel -Force
        return $true
    }
    return $false
}

function Get-RelevantTree([string]$targetPath) {
    $paths = New-Object System.Collections.Generic.List[string]
    if ($targetPath -and (Test-Path $targetPath -PathType Leaf)) { $paths.Add($targetPath) }
    foreach ($extra in @(
        'default.project.json',
        'src/shared/Gameplay/Remotes.luau',
        'docs/ARCHITECTURE.md',
        'docs/GDD.md',
        'docs/QA_REPORT.md'
    )) {
        if ((Test-Path $extra -PathType Leaf) -and -not $paths.Contains($extra)) { $paths.Add($extra) }
    }
    if ($paths.Count -lt 4 -and (Test-Path .\src)) {
        Get-ChildItem -Recurse -File -Path .\src -Filter *.luau | ForEach-Object {
            $rel = $_.FullName.Substring((Get-Location).Path.Length + 1) -replace '\\','/'
            if (-not $paths.Contains($rel)) { $paths.Add($rel) }
        }
    }
    $sb = New-Object System.Text.StringBuilder
    $budget = 24000
    foreach ($rel in $paths) {
        if (-not (Test-Path $rel)) { continue }
        $body = Get-Content $rel -Raw -Encoding UTF8
        $chunk = "=== $rel ===`n$body`n`n"
        if (($sb.Length + $chunk.Length) -gt $budget) { break }
        [void]$sb.Append($chunk)
    }
    if ($sb.Length -eq 0) { return '(no files yet)' }
    Write-Host "   [prompt] included $($paths.Count) file(s), $($sb.Length) chars" -ForegroundColor DarkGray
    return $sb.ToString()
}

function Update-TzDone([string]$taskId, [string]$note) {
    $lines = @(Get-Content PROJECT_TZ.md -Encoding UTF8)
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^- \[ \] $([regex]::Escape($taskId)) ") {
            $lines[$i] = $lines[$i] -replace '^- \[ \]', '- [x]'
            $doneLine = "  - DONE $((Get-Date).ToString('yyyy-MM-dd HH:mm')) | $note"
            $lines = @($lines[0..$i]) + $doneLine + @($lines[($i+1)..([Math]::Max($i+1,$lines.Count-1))])
            if ($lines.Count -gt 0 -and $lines[0] -match '^# LAST_UPDATE:') {
                $lines[0] = "# LAST_UPDATE: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
            }
            Set-Content PROJECT_TZ.md -Value $lines -Encoding UTF8
            return
        }
    }
}

function Add-TzNote([string]$taskId, [string]$kind, [string]$text) {
    $lines = @(Get-Content PROJECT_TZ.md -Encoding UTF8)
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^- \[ \] $([regex]::Escape($taskId)) ") {
            $note = "  - $kind $((Get-Date).ToString('yyyy-MM-dd HH:mm')) | $text"
            $lines = @($lines[0..$i]) + $note + @($lines[($i+1)..([Math]::Max($i+1,$lines.Count-1))])
            Set-Content PROJECT_TZ.md -Value $lines -Encoding UTF8
            return
        }
    }
}

function Build-Prompt([string]$owner, [string]$taskLine, [string]$mode, [string]$target, [string]$validatorFeedback) {
    $agentsFull = Get-Content AGENTS.md -Raw -Encoding UTF8
    $universalEnd = $agentsFull.IndexOf("## @")
    if ($universalEnd -lt 0) { $universalEnd = $agentsFull.Length }
    $universal = $agentsFull.Substring(0, $universalEnd)
    $agentSection = [regex]::Match($agentsFull, "(?ms)## @$owner\b.*?(?=## @|\z)").Value
    $agents = $universal + "`n" + $agentSection
    $tz     = Get-Content PROJECT_TZ.md -Raw -Encoding UTF8
    $tree   = Get-RelevantTree $target
    $taskId = [regex]::Match($taskLine, '\]\s+(P\d+(?:\.\d+)*)').Groups[1].Value

    $modeBlock = switch ($mode) {
        'append'  { "WRITE MODE = APPEND.`n- Return ONLY new lines to append.`n- Do NOT rewrite the whole file.`n- Target: $target" }
        'create'  { "WRITE MODE = CREATE.`n- Return COMPLETE file content.`n- Target: $target" }
        default   { "WRITE MODE = REWRITE.`n- Return COMPLETE file content.`n- Target: $target" }
    }

    $feedback = ''
    if ($validatorFeedback) {
        $feedback = "`n=== VALIDATOR FEEDBACK (fix this) ===`n$validatorFeedback`n"
        if ($mode -eq 'append' -and $target -and (Test-Path $target)) {
            $cur = Get-Content $target -Raw -Encoding UTF8
            $feedback += "`n=== CURRENT FILE (append AFTER this) ===`n$cur`n"
        }
    }

    return @"
You are the agent @$owner. Follow AGENTS.md protocol exactly.

=== AGENTS.md ===
$agents

=== PROJECT_TZ.md ===
$tz

=== Existing project files (relevant) ===
$tree
$feedback
=== YOUR TASK ===
$taskLine

$modeBlock

STRICT RULES:
- Do ONLY this one task. Do not touch other tasks.
- Do NOT block due to task ordering. Prerequisites are already done.
- If task says '-> path/file.md#section', '#' is a section name, NOT part of the filename.
- No stubs, no TODOs. Real, complete content.
- NEVER use wait() — always task.wait().
- *.server.luau / *.client.luau MUST NOT end with return.
- ModuleScript *.luau MUST end with return.
- You MUST include at least one <FILE path="..."> when the task has a → path.
- Reply MUST begin with <DONE>$taskId</DONE>. Never output <BLOCKED>.

Format:
<DONE>$taskId</DONE>
<NOTE>one short sentence</NOTE>
<FILE path="$(if ($target) { $target } else { 'src/server/Example.server.luau' })">
file content
</FILE>
Never use path relative/path.ext — always the real target path.
"@
}

function Write-Heartbeat($obj) {
    $obj | ConvertTo-Json -Depth 5 | Set-Content '.\.forge\state\heartbeat.json' -Encoding UTF8
}

function Invoke-Step {
    $lines = Get-Content PROJECT_TZ.md -Encoding UTF8
    $taskLine = $null
    foreach ($l in $lines) {
        if ($l -match '^\s*- \[ \] .* @(\w+)') { $taskLine = $l; break }
    }
    if (-not $taskLine) {
        Write-Host '=== No more actionable tasks. ===' -ForegroundColor Green
        Write-Heartbeat @{ status = 'idle'; ts = (Get-Date).ToString('o') }
        return $false
    }

    $owner  = [regex]::Match($taskLine, '@(\w+)').Groups[1].Value
    $taskId = [regex]::Match($taskLine, '\]\s+(P\d+(?:\.\d+)*)').Groups[1].Value
    $mode   = Get-TaskMode $taskLine
    $target = Get-TaskTarget $taskLine
    $requiresFile = [bool]$target

    if ($owner -eq 'human') {
        Write-Host "HITL: $taskId needs human action." -ForegroundColor Yellow
        Write-Host "   Edit PROJECT_TZ.md, change '- [ ] $taskId' to '- [x]', then re-run." -ForegroundColor Yellow
        Write-Heartbeat @{ status = 'waiting_human'; task = $taskId }
        return $false
    }

    Write-Host "[$taskId] -> @$owner  mode=$mode" -ForegroundColor Cyan
    Write-Heartbeat @{ status = 'running'; task = $taskId; owner = $owner }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $maxAttempts = 3
    $validatorFeedback = $null

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $cfg = Get-AgentConfig $owner $attempt
        Write-Host "   attempt $attempt/$maxAttempts model=$($cfg.model) predict=$($cfg.predict)" -ForegroundColor DarkCyan
        $prompt = Build-Prompt $owner $taskLine.Trim() $mode $target $validatorFeedback
        Set-Content ".\logs\$stamp-$taskId-prompt.txt" -Value $prompt -Encoding UTF8

        $temp = if ($attempt -eq 1) { 0.1 } else { 0.0 }
        $body = @{
            model   = $cfg.model
            prompt  = $prompt
            stream  = $false
            options = @{ num_ctx = $cfg.ctx; temperature = $temp; num_predict = $cfg.predict }
        } | ConvertTo-Json -Depth 5

        try {
            $resp = Invoke-RestMethod -Uri 'http://localhost:11434/api/generate' -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 1800
            $out = $resp.response
        } catch {
            Write-Host "   API abort: $($_.Exception.Message)" -ForegroundColor Yellow
            $validatorFeedback = "API error: $($_.Exception.Message)"
            continue
        }
        Set-Content ".\logs\$stamp-$taskId-attempt$attempt-response.txt" -Value $out -Encoding UTF8

        if ($out -match '<BLOCKED>\s*(P\d+(?:\.\d+)*)\s*</BLOCKED>') {
            Write-Host "   model refused (BLOCKED) - retrying" -ForegroundColor Yellow
            $validatorFeedback = 'Do not output BLOCKED. Produce DONE and FILE now.'
            continue
        }

        if ($out -notmatch '<(?:DONE|SUCCESS)>\s*(P\d+(?:\.\d+)*)\s*</(?:DONE|SUCCESS)>') {
            Write-Host "   attempt $attempt/$maxAttempts malformed, retrying..." -ForegroundColor Yellow
            $validatorFeedback = "Reply MUST start with <DONE>$taskId</DONE> then <NOTE> and <FILE>."
            continue
        }
        $id = $Matches[1]
        if ($id -ne $taskId) {
            Write-Host "   model DONE $id, current task is $taskId - wrong ID, retrying" -ForegroundColor Yellow
            $validatorFeedback = "Wrong id. Use <DONE>$taskId</DONE>."
            continue
        }
        $note = if ($out -match '<NOTE>([\s\S]*?)</NOTE>') { $Matches[1].Trim() } else { '' }

        $fileMatches = @([regex]::Matches($out, '<FILE\s+path="([^"]+)">\r?\n?([\s\S]*?)</FILE>'))
        # BUG FIX: DONE without FILE rejected when path required
        if ($requiresFile -and $fileMatches.Count -eq 0) {
            Write-Host "   REJECTED: DONE without <FILE> but task requires a file write" -ForegroundColor Red
            $validatorFeedback = "You returned DONE without <FILE>. Task requires writing $target."
            continue
        }

        $written = @()
        foreach ($m in $fileMatches) {
            $rawPath = $m.Groups[1].Value.Trim()
            $content = $m.Groups[2].Value.Trim("`r","`n")
            $path = $rawPath
            $isAppend = ($mode -eq 'append')
            if ($rawPath -match '^(.+?)#(.+)$') {
                $path = $Matches[1]
                $isAppend = $true
            }
            if ($target -and $fileMatches.Count -eq 1) { $path = $target }
            $path = $path -replace '[<>:"|?*]', '_'

            $leaf = Split-Path $path -Leaf
            $isDirLike = ($path -match '[/\\]$') -or ($leaf -notmatch '\.[A-Za-z0-9]{1,6}$')
            if ($isDirLike) {
                Write-Host "   skip directory-like path: $path" -ForegroundColor DarkGray
                continue
            }

            $dir = Split-Path $path -Parent
            if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
            Save-Snapshot $path

            try {
                if ($isAppend -and (Test-Path $path -PathType Leaf)) {
                    $existing = Get-Content $path -Raw -Encoding UTF8
                    if ($existing -and $existing.Contains($content.Trim()) -and $content.Trim().Length -gt 0) {
                        Write-Host "   skip duplicate append $path" -ForegroundColor DarkGray
                    } else {
                        $sep = if ($existing -and -not $existing.EndsWith("`n")) { "`n" } else { '' }
                        [System.IO.File]::AppendAllText((Join-Path (Get-Location) $path), $sep + $content + "`n", (New-Object System.Text.UTF8Encoding($false)))
                        Write-Host "   appended $path" -ForegroundColor DarkGray
                    }
                } else {
                    if (Test-Path $path -PathType Container) { Remove-Item $path -Recurse -Force }
                    [System.IO.File]::WriteAllText((Join-Path (Get-Location) $path), $content + "`n", (New-Object System.Text.UTF8Encoding($false)))
                    Write-Host "   wrote $path" -ForegroundColor DarkGray
                }
                $written += $path
            } catch {
                Write-Host "   FAILED write $path : $($_.Exception.Message)" -ForegroundColor Red
            }
        }

        $allValid = $true
        $errMsgs = @()
        foreach ($vp in $written) {
            if (Test-Path $vp -PathType Leaf) {
                $ok = & "$PSScriptRoot\validator.ps1" -FilePath $vp
                if (-not $ok) {
                    $allValid = $false
                    $errMsgs += "validator failed for $vp"
                    Restore-Snapshot $vp | Out-Null
                    Write-Host "   rolled back $vp" -ForegroundColor Yellow
                }
            }
        }
        if ($written.Count -gt 0 -and -not $allValid) {
            Write-Host "   VALIDATOR REJECTED $id - retrying" -ForegroundColor Red
            $validatorFeedback = "Fix validator errors:`n- " + ($errMsgs -join "`n- ")
            continue
        }

        Update-TzDone $id $note
        Write-Host "   DONE: $id - $note" -ForegroundColor Green
        Write-Heartbeat @{ status = 'done_step'; task = $id }
        return $true
    }

    Write-Host '   AGENT FAILED after retries. See logs\.' -ForegroundColor Red
    Add-TzNote $taskId 'FAILED' 'needs decomposition or different model — run python run.py for auto-split'
    Write-Heartbeat @{ status = 'failed'; task = $taskId }
    return $false
}

$maxSteps = if ($Max -ge 0) { $Max } elseif ($Loop) { 500 } else { 1 }
Write-Host "Quality Forge (ps1) | max=$maxSteps" -ForegroundColor Magenta
for ($i = 0; $i -lt $maxSteps; $i++) {
    if (-not (Invoke-Step)) { break }
    if ($SleepSec -gt 0 -and ($i + 1) -lt $maxSteps) { Start-Sleep -Seconds $SleepSec }
}
