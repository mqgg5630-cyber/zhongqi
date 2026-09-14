# push.ps1 - commit your local files and push them to the Arena working branch.
#
# Usage (inside the repo folder):
#     .\push.ps1                      # auto commit message
#     .\push.ps1 "add midterm files"  # custom commit message
#
# The first push will pop up a GitHub login window (your own account). After
# that Windows remembers the credential and later pushes are silent.
#
# NOTE: this file is intentionally ASCII-only (see sync.ps1 for the reason).

param(
    [string]$Message = ''
)

$ErrorActionPreference = 'Stop'
$Branch = 'arena/01a09d79-zhongqi'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

if (-not (Test-Path (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    exit 1
}

# git refuses to commit without an identity; set a local one if missing
if (-not (git config user.name)) {
    git config user.name  'mqgg5630-cyber'
    git config user.email 'mqgg5630-cyber@users.noreply.github.com'
    Write-Host "== set a default git identity for this repo (change it with git config user.name)" -ForegroundColor Yellow
}

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

# Get the server side first so the push cannot be rejected as non-fast-forward
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
    Write-Host "  * If it asks for a password: GitHub needs a token, not your password." -ForegroundColor Yellow
    Write-Host "    Install/run GitHub Desktop or 'gh auth login', then push again." -ForegroundColor Yellow
    Write-Host "  * If it says 'rejected': the remote branch moved. Run .\sync.ps1 first." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== pushed to $Branch :" -ForegroundColor Green
git log -1 --oneline --decorate
