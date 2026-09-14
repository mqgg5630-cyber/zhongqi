# sync.ps1 - pull the latest code from the Arena working branch.
#
# Usage (inside the repo folder):
#     .\sync.ps1
# If PowerShell blocks the script, run this once:
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#
# NOTE: this file is intentionally ASCII-only. Chinese text in a .ps1 file
# gets mis-decoded by Windows PowerShell 5.1 (GBK) and breaks the parser.

param(
    [string]$Branch = 'arena/01a09d79-zhongqi'
)

$ErrorActionPreference = 'Stop'

# Work in the folder that contains this script (fall back to current dir if pasted)
$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

if (-not (Test-Path (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    Write-Host "        Run this script from the cloned folder (E:\0zhongqi\zhongqi)." -ForegroundColor Red
    exit 1
}

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

# Stash local changes so the pull cannot fail
$stashed = $false
if (git status --porcelain) {
    Write-Host "!! local changes found, stashing them first ..." -ForegroundColor Yellow
    git stash push -u -m ("auto-stash before sync " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    $stashed = $true
}

git fetch origin
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git fetch failed (network / proxy?)." -ForegroundColor Red; exit 1 }

git checkout $Branch
git pull --ff-only origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pull failed. Your branch has local commits that conflict." -ForegroundColor Red
    Write-Host "        Fix with: git status   /   git stash list   /   git reset --hard origin/$Branch" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== up to date. latest commit:" -ForegroundColor Green
git log -1 --oneline --decorate

if ($stashed) {
    Write-Host ""
    Write-Host "NOTE: your previous local changes are still in the stash. See: git stash list" -ForegroundColor Yellow
}
