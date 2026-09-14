# push.ps1 - commit local changes and push them to the remote branch.
#
# Usage (inside the repo folder):
#     .\push.ps1
#     .\push.ps1 "add report files"
#     .\push.ps1 -Branch main -Message "update"
#
# NOTE: ASCII only on purpose (see sync.ps1).

param(
    [string]$Message = '',
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

if (-not (git config user.name)) {
    git config user.name  'local user'
    git config user.email 'local@example.com'
    Write-Host "== set a default git identity for this repo" -ForegroundColor Yellow
}

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

git fetch origin
git checkout $Branch
git pull --ff-only origin $Branch

git add -A
if (-not (git status --porcelain)) {
    Write-Host ""
    Write-Host "== nothing new to commit. done." -ForegroundColor Green
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "sync: local update " + (Get-Date -Format 'yyyy-MM-dd HH:mm')
}

Write-Host ""
Write-Host "== files to be committed:" -ForegroundColor Cyan
git status --short

git commit -m $Message
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] commit failed." -ForegroundColor Red; exit 1 }

git push origin $Branch
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] push failed." -ForegroundColor Red
    Write-Host "  * If it asks for a password: GitHub needs a token, not a password." -ForegroundColor Yellow
    Write-Host "    Install/run GitHub Desktop or 'gh auth login', then push again." -ForegroundColor Yellow
    Write-Host "  * If it says 'rejected': the remote moved. Run .\sync.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== pushed to $Branch :" -ForegroundColor Green
git log -1 --oneline --decorate
