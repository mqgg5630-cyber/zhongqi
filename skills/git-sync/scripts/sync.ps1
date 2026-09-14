# sync.ps1 (skill version) - pull the latest code from the working branch.
#
# Usage (inside the repo folder):
#     .\sync.ps1
#     .\sync.ps1 -Branch arena/01a09d79-zhongqi
#
# The branch defaults to sync.config.json (keys: branch / remote), so the same
# script works in any repo that carries that file.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes a .ps1 without BOM as
# ANSI/GBK and Chinese text would break the parser.

param(
    [string]$Branch = '',
    [string]$Remote = ''
)

$ErrorActionPreference = 'Stop'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    Write-Host "        Run this from the cloned folder (e.g. E:\0zhongqi\zhongqi)." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------- config
$cfgPath = @(
    (Join-Path $repo 'skills\git-sync\sync.config.json'),
    (Join-Path $PSScriptRoot 'sync.config.json')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($cfgPath) {
    $cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if (-not $Branch -and $cfg.branch) { $Branch = [string]$cfg.branch }
    if (-not $Remote -and $cfg.remote) { $Remote = [string]$cfg.remote }
}
if (-not $Remote) { $Remote = 'origin' }
if (-not $Branch) { $Branch = (git rev-parse --abbrev-ref HEAD).Trim() }

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

# Stash local changes so the pull cannot fail
$stashed = $false
if (git status --porcelain) {
    Write-Host "!! local changes found, stashing them first ..." -ForegroundColor Yellow
    git stash push -u -m ("auto-stash before sync " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
    $stashed = $true
}

git fetch $Remote
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] git fetch failed (network / proxy?)." -ForegroundColor Red; exit 1 }

git checkout $Branch
git pull --ff-only $Remote $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] pull failed. Your branch has local commits that conflict." -ForegroundColor Red
    Write-Host "        Fix with: git status   /   git stash list   /   git reset --hard $Remote/$Branch" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== up to date. latest commit:" -ForegroundColor Green
git log -1 --oneline --decorate

if ($stashed) {
    Write-Host ""
    Write-Host "NOTE: your previous local changes are still in the stash. See: git stash list" -ForegroundColor Yellow
}
