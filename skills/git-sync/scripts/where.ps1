# where.ps1 - which folder is which? (repo / branch / commit / download dir)
#
# Usage (double-click where.cmd, or inside a repo folder):
#     .\where.ps1
#     .\where.ps1 -Want arena/01a09d79-zhongqi      # mark the folder you want
#     .\where.ps1 -All                              # also list every sibling clone
#
# Why: one machine can hold several clones of this project, and each clone can be
# sitting on a different Arena session branch. Files from another branch are NOT
# your files. For this folder and for every sibling clone this script prints:
#   * the branch that is checked out
#   * the branch its sync.config.json asks for (the branch it will always pull)
#   * the latest commit
#   * where .\download.ps1 would copy the deliverables to, and what is already there
# The folder you want is the one whose "config" branch is your session branch.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes a .ps1 without BOM as
# ANSI/GBK, and non-ASCII text would break the parser.

param(
    [string]$Want = '',
    [switch]$All
)

$ErrorActionPreference = 'Continue'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

function Read-Config([string]$folder) {
    $result = [ordered]@{ branch = ''; download = '' }
    $p = Join-Path $folder 'skills\git-sync\sync.config.json'
    if (Test-Path -LiteralPath $p) {
        try {
            $cfg = Get-Content -LiteralPath $p -Encoding UTF8 -Raw | ConvertFrom-Json
            $result.branch = [string]$cfg.branch
            if ($cfg.download_dir) { $result.download = [string]$cfg.download_dir }
        } catch { }
    }
    if (-not $result.download) {
        $parent = Split-Path -Parent $folder
        $leaf = Split-Path -Leaf $folder
        $result.download = Join-Path $parent ($leaf + '_out')
    }
    return $result
}

function Show-Folder([string]$folder, [switch]$IsHere) {
    if (-not (Test-Path -LiteralPath (Join-Path $folder '.git'))) { return }

    Push-Location -LiteralPath $folder
    $branch = (git rev-parse --abbrev-ref HEAD 2>$null)
    $commit = (git log -1 --oneline 2>$null)
    $remote = (git remote get-url origin 2>$null)
    Pop-Location

    $cfg = Read-Config $folder
    $dl = $cfg.download

    $files = 0
    if (Test-Path -LiteralPath $dl) {
        $files = @(Get-ChildItem -LiteralPath $dl -Recurse -File -ErrorAction SilentlyContinue).Count
    }

    $mark = '  '
    $color = 'Gray'
    if ($Want -and $cfg.branch -eq $Want) { $mark = '->'; $color = 'Green' }
    elseif (-not $Want -and $IsHere) { $mark = '->'; $color = 'Green' }

    Write-Host ("{0} {1}" -f $mark, $folder) -ForegroundColor $color
    Write-Host ("     branch  : {0}" -f $branch)
    if ($cfg.branch) {
        if ($cfg.branch -eq $branch) {
            Write-Host ("     config  : {0}   (this folder always pulls this branch)" -f $cfg.branch)
        } else {
            Write-Host ("     config  : {0}   (MISMATCH - run .\sync.ps1 to switch)" -f $cfg.branch) -ForegroundColor Yellow
        }
    } else {
        Write-Host "     config  : (none - uses the branch from git)" -ForegroundColor Yellow
    }
    Write-Host ("     commit  : {0}" -f $commit)
    Write-Host ("     remote  : {0}" -f $remote)
    Write-Host ("     download: {0}" -f $dl)
    Write-Host ("               {0} file(s) already there" -f $files)
    if (Test-Path -LiteralPath (Join-Path $dl 'deliverable')) {
        $newest = Get-ChildItem -LiteralPath (Join-Path $dl 'deliverable') -Filter '*.docx' -ErrorAction SilentlyContinue |
                  Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($newest) {
            Write-Host ("     newest  : {0}  ({1:yyyy-MM-dd HH:mm})" -f $newest.Name, $newest.LastWriteTime) -ForegroundColor Green
        }
    }
    Write-Host ""
}

Write-Host "== this folder" -ForegroundColor Cyan
Show-Folder $repo -IsHere

$parent = Split-Path -Parent $repo
Write-Host "== other clones next to this one ($parent)" -ForegroundColor Cyan
$found = 0
foreach ($dir in @(Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue)) {
    if ($dir.FullName -eq $repo) { continue }
    if (-not (Test-Path -LiteralPath (Join-Path $dir.FullName '.git'))) { continue }
    $found = $found + 1
    Show-Folder $dir.FullName
}
if ($found -eq 0) {
    Write-Host "   (no other clone found - this is the only one)" -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "== which one should I use?" -ForegroundColor Cyan
Write-Host "   use the folder whose 'config' branch is your session branch."
if ($Want) {
    Write-Host ("   you asked for : {0}" -f $Want) -ForegroundColor Green
}
Write-Host "   inside that folder:"
Write-Host "     1) double-click sync.cmd        (or .\sync.ps1)          pull the latest"
Write-Host "     2) double-click download.cmd    (or .\download.ps1 -Set final)"
Write-Host "   the deliverables then appear under the 'download' path printed above"
Write-Host ""
Write-Host "   tip: .\where.ps1 -Want <branch>   marks the matching folder with '->'"
