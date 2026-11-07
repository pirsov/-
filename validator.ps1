param([string]$FilePath)
# Validator: returns $true if file passes, $false + reason if not
$errors = @()
$name = Split-Path $FilePath -Leaf
$content = Get-Content $FilePath -Raw -Encoding UTF8

# 1. Empty file
if (-not $content -or $content.Trim().Length -lt 10) {
    $errors += "empty or nearly empty file"
}

# 2. .server/.client MUST NOT have top-level return
if ($name -match '\.(server|client)\.luau$') {
    $lastNonEmpty = (($content -split "`n") | Where-Object { $_.Trim() -ne '' } | Select-Object -Last 1)
    if ($lastNonEmpty -and $lastNonEmpty.Trim() -match '^return\s') {
        $errors += "top-level return in Script/LocalScript"
    }
}

# 3. ModuleScript (.luau without suffix) must contain a top-level return (multi-line return { } OK)
if ($name -match '\.luau$' -and $name -notmatch '\.(server|client)\.luau$') {
    if ($content -notmatch '(?m)^return\b') {
        $errors += "ModuleScript must end with return"
    }
}

# QA: only reject PlayerRespawn when listed as a real bug line, not disclaimers
if ($name -eq 'QA_REPORT.md') {
    foreach ($line in ($content -split "`n")) {
        if ($line -match 'PlayerRespawn' -and $line -match '\[(CRIT|HIGH|MED|LOW)\]' -and $line -notmatch '(?i)false|ignore|not real|do not|never invent|hallucin') {
            $errors += "QA_REPORT lists PlayerRespawn as a bug — not in sources"
            break
        }
    }
}


# 4. Forbidden deprecated/nonexistent API
if ($content -match 'game\.Players\.PlayerRespawned')  { $errors += "PlayerRespawned does not exist" }
if ($content -match ':BreakJoints\(\)')                { $errors += "BreakJoints is deprecated" }
if ($content -match 'Humanoid\.Parent\s*=\s*nil')      { $errors += "setting Humanoid.Parent=nil breaks character" }
if ($content -match 'Humanoid\.Health\s*=\s*0')        { $errors += "killing player (Humanoid.Health=0) not allowed" }
if ($content -match 'require\([^)]*ReplicatedStorage[^)]*src\.') { $errors += "wrong require path (src.* not in ReplicatedStorage)" }
if ($content -match '(?<![\w\.])wait\s*\(')            { $errors += "use task.wait, not wait" }

# 5. Balance check (basic)
$opens = ([regex]::Matches($content, '\(')).Count
$closes = ([regex]::Matches($content, '\)')).Count
if ([Math]::Abs($opens - $closes) -gt 2) {
    $errors += "unbalanced parentheses ($opens vs $closes)"
}

# 6. APPEND-corruption detectors (undefined identifiers)
if ($name -match '\.luau$') {
    if ($content -match '\bfolder\b' -and $content -notmatch '\blocal\s+folder\b' -and $content -notmatch 'folder\s*=') {
        $errors += "uses 'folder' but never defines it (likely APPEND overwrite)"
    }
    if ($content -match '\bRemotes\b' -and $content -notmatch '\blocal\s+Remotes\b' -and $content -notmatch 'Remotes\s*=' -and $content -notmatch 'getOrCreate') {
        $errors += "uses 'Remotes' but never defines it (likely APPEND overwrite)"
    }
    if ($name -match '\.client\.luau$' -and $content -match '\bscreen\b' -and $content -notmatch '\blocal\s+screen\b' -and $content -notmatch 'screen\s*=') {
        $errors += "uses 'screen' but never defines it (likely APPEND overwrite)"
    }
    if (($content -match 'PlayerAdded|GetPlayerFromCharacter|LocalPlayer') -and $content -notmatch 'GetService\(\s*["'']Players["'']\s*\)' -and $content -notmatch '\blocal\s+Players\b') {
        $errors += "uses Players service without GetService"
    }
}

if ($errors.Count -gt 0) {
    Write-Host "  VALIDATOR FAIL [$name]: $($errors -join '; ')" -ForegroundColor Red
    return $false
}
Write-Host "  VALIDATOR PASS [$name]" -ForegroundColor Green
return $true
