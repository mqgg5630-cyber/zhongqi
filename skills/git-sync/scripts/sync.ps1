# sync.ps1 - pull the latest code, keeping local edits safe.
#
# Usage (inside the repo folder):
#     .\sync.ps1
#     .\sync.ps1 -Branch main
#
# NOTE: ASCII only on purpose - Windows PowerShell 5.1 decodes a .ps1 without a
# BOM as ANSI/GBK, and non-ASCII text can break the parser.

param(
    [string]$Branch = ''
)

$ErrorActionPreference = 'Stop'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

if (-not (Test-Path (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    exit 1
}

if (-not $Branch) {
    $Branch = (git rev-parse --abbrev-ref HEAD).Trim()
    if (-not $Branch -or $Branch -eq 'HEAD') { $Branch = 'main' }
}

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

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
    Write-Host "[ERROR] pull failed - local commits conflict with the remote." -ForegroundColor Red
    Write-Host "        Try: git status  /  git stash list  /  git reset --hard origin/$Branch" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== up to date. latest commit:" -ForegroundColor Green
git log -1 --oneline --decorate

if ($stashed) {
    Write-Host ""
    Write-Host "NOTE: your earlier local changes are still in the stash. See: git stash list" -ForegroundColor Yellow
}
