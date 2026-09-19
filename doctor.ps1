# doctor.ps1 - one-shot health check for the local <-> Arena sync setup.
#
# Usage (inside the repo folder):
#     .\doctor.ps1
#
# Prints: PowerShell / git versions, repo path, execution policy, branch vs the
# branch recorded in sync.config.json, remote URL, ahead/behind, uncommitted
# files, stash entries and the last three commits. Run this first whenever
# "something does not sync".
#
# ASCII-only on purpose (Windows PowerShell 5.1 decodes .ps1 as ANSI/GBK).

param()

$ErrorActionPreference = 'Continue'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

function Line($label, $value, $color = 'Gray') {
    Write-Host ("{0,-14} {1}" -f $label, $value) -ForegroundColor $color
}

Write-Host "== environment" -ForegroundColor Cyan
Line 'PowerShell' $PSVersionTable.PSVersion.ToString()
Line 'git' ((git --version) 2>&1)
try { Line 'policy' (Get-ExecutionPolicy -Scope CurrentUser) } catch { Line 'policy' '(unknown)' 'Yellow' }
Line 'repo' $repo

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] not a git repository - run this from the cloned folder" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------- config
$cfgPath = @(
    (Join-Path $repo 'skills\git-sync\sync.config.json'),
    (Join-Path $PSScriptRoot 'sync.config.json')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$wantBranch = ''
if ($cfgPath) {
    $cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $wantBranch = [string]$cfg.branch
    Line 'config' $cfgPath
} else {
    Line 'config' '(missing - using the branch from git)' 'Yellow'
}

Write-Host ""
Write-Host "== network" -ForegroundColor Cyan
# can we reach the remote at all? (the usual cause of a failed sync)
$probe = (& git ls-remote --heads origin 2>&1 | Out-String).Trim()
$probeCode = $LASTEXITCODE
if ($probeCode -eq 0) {
    Line 'remote' 'reachable (git ls-remote OK)' 'Green'
} else {
    Line 'remote' 'NOT reachable - sync will fail' 'Red'
    Write-Host "               $probe" -ForegroundColor DarkGray
    Write-Host "               try: git config --global http.sslBackend openssl" -ForegroundColor Yellow
    Write-Host "                    git config --global http.version HTTP/1.1" -ForegroundColor Yellow
    Write-Host "                    git config --global http.proxy http://127.0.0.1:7890   (if you use a proxy)" -ForegroundColor Yellow
    Write-Host "               undo: git config --global --unset http.sslBackend" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "== git state" -ForegroundColor Cyan
git fetch origin --quiet 2>$null

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Line 'branch' $branch
if ($wantBranch -and $branch -ne $wantBranch) {
    Line 'expected' ("$wantBranch   <-- run .\sync.ps1 to switch") 'Yellow'
}
Line 'remote' ((git remote get-url origin) 2>&1)

$ahead  = (git rev-list --count ("{0}..HEAD" -f $wantBranch) 2>$null)
$behind = (git rev-list --count ("HEAD..{0}" -f $wantBranch) 2>$null)
if ($wantBranch) {
    if ($ahead -and $ahead -ne '0') { Line 'ahead' "$ahead local commit(s) not on the remote" 'Yellow' }
    if ($behind -and $behind -ne '0') { Line 'behind' "$behind commit(s) on the remote - run .\sync.ps1" 'Yellow' }
    if ((-not $ahead -or $ahead -eq '0') -and (-not $behind -or $behind -eq '0')) { Line 'sync' 'in step with the remote' 'Green' }
}

$dirty = @(git status --porcelain)
Line 'uncommitted' ("$($dirty.Count) file(s)")
if ($dirty.Count -gt 0 -and $dirty.Count -le 10) { $dirty | ForEach-Object { Write-Host "               $_" } }
if ($dirty.Count -gt 10) { Write-Host ("               ... and {0} more" -f ($dirty.Count - 10)) }

$stash = @(git stash list)
Line 'stash' ("$($stash.Count) entr(y|ies)")
if ($stash.Count -gt 0) {
    Write-Host "               recover with: git stash pop   (or 'git stash drop' to throw away)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "== last commits" -ForegroundColor Cyan
git log -3 --oneline --decorate

Write-Host ""
Write-Host "== next steps" -ForegroundColor Cyan
Write-Host "   .\sync.ps1                       pull the latest from the working branch"
Write-Host "   .\upload.ps1                     put local attachments in and push"
Write-Host "   .\download.ps1 -Set final        copy deliverables out of the repo"
Write-Host "   .\download.ps1 -List             show the download sets"
