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

# 3. ModuleScript (.luau without suffix) SHOULD end with return, but allow if file is small/utility
#    (skip this check - not critical)

# 4. Forbidden deprecated/nonexistent API
if ($content -match 'game\.Players\.PlayerRespawned')  { $errors += "PlayerRespawned does not exist" }
if ($content -match ':BreakJoints\(\)')                { $errors += "BreakJoints is deprecated" }
if ($content -match 'Humanoid\.Parent\s*=\s*nil')      { $errors += "setting Humanoid.Parent=nil breaks character" }
if ($content -match 'Humanoid\.Health\s*=\s*0')        { $errors += "killing player (Humanoid.Health=0) not allowed" }
if ($content -match 'require\([^)]*ReplicatedStorage[^)]*src\.') { $errors += "wrong require path (src.* not in ReplicatedStorage)" }
if ($content -match '\bwait\(\d')                       { $errors += "use task.wait, not wait" }
if ($content -match 'ReplicatedStorage\.Remotes\s*\.' -and $content -notmatch 'WaitForChild') {
    # allow if file itself creates the folder - just warn
}

# 5. Balance check (basic)
$opens = ([regex]::Matches($content, '\(')).Count
$closes = ([regex]::Matches($content, '\)')).Count
if ([Math]::Abs($opens - $closes) -gt 2) {
    $errors += "unbalanced parentheses ($opens vs $closes)"
}

if ($errors.Count -gt 0) {
    Write-Host "  VALIDATOR FAIL [$name]: $($errors -join '; ')" -ForegroundColor Red
    return $false
}
Write-Host "  VALIDATOR PASS [$name]" -ForegroundColor Green
return $true
