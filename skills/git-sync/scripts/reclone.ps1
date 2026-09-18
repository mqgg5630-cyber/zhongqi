# reclone.ps1 - clone this repository into a FRESH folder on the working branch.
#
# Usage (inside an existing clone; the old folder is never touched):
#     .\reclone.ps1                                   -> ..\<repo>-arena
#     .\reclone.ps1 -Path E:\0zhongqi\zhongqi-arena
#     .\reclone.ps1 -Url https://github.com/user/repo.git -Path D:\work\repo2
#
# What it does:
#   1. reads branch / remote from sync.config.json (same lookup as sync.ps1)
#   2. figures out the remote URL from the clone you run it in (or takes -Url)
#   3. clones -b <branch> --single-branch into the NEW folder
#      (if that folder already is a clone, it fast-forwards it instead)
#   4. prints the next steps; the folder you run it from stays untouched
#
# ASCII-only on purpose (Windows PowerShell 5.1 decodes .ps1 as ANSI/GBK).

param(
    [string]$Path   = '',
    [string]$Branch = '',
    [string]$Remote = 'origin',
    [string]$Url    = ''
)

$ErrorActionPreference = 'Stop'

$here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

function Show-Next([string]$Target) {
    Write-Host ""
    Write-Host "== next steps (in the NEW folder):" -ForegroundColor Cyan
    Write-Host "   cd $Target"
    Write-Host "   .\sync.cmd        pull the latest (double-click works too)"
    Write-Host "   .\download.cmd    copy deliverable / intermediate folders to this machine"
    Write-Host "   .\doctor.cmd      health check when something looks wrong"
    Write-Host "   the old folder keeps its own branch; the two clones are independent"
}



# ------------------------------------------------------------------- config
$cfgPath = @(
    (Join-Path $here 'skills\git-sync\sync.config.json'),
    (Join-Path $here 'sync.config.json')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($cfgPath) {
    $cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if (-not $Branch -and $cfg.branch) { $Branch = [string]$cfg.branch }
    if ($cfg.remote) { $Remote = [string]$cfg.remote }
}

# ---------------------------------------------------------------------- url
if (-not $Url) {
    $ErrorActionPreference = 'Continue'
    try { $Url = (git -C $here remote get-url $Remote) } catch { $Url = '' }
    $ErrorActionPreference = 'Stop'
    if ($Url) { $Url = $Url.Trim() }
}
if (-not $Url) {
    Write-Host "[ERROR] cannot read the remote URL from here." -ForegroundColor Red
    Write-Host "        Pass it explicitly: -Url https://github.com/<user>/<repo>.git" -ForegroundColor Yellow
    exit 1
}
if (-not $Branch) { $Branch = 'main' }

# ------------------------------------------------------------------- target
$name = Split-Path -Leaf $here
if (-not $Path) {
    $Path = Join-Path (Split-Path -Parent $here) ($name + '-arena')
}

Write-Host "== url    : $Url"
Write-Host "== branch : $Branch"
Write-Host "== target : $Path"
Write-Host "== source : $here   (this folder will NOT be touched)"
Write-Host ""

if (Test-Path -LiteralPath $Path) {
    $isRepo = Test-Path -LiteralPath (Join-Path $Path '.git')
    if (-not $isRepo) {
        $count = (Get-ChildItem -LiteralPath $Path -Force | Measure-Object).Count
        if ($count -gt 0) {
            Write-Host "[ERROR] $Path exists, is not empty and is not a clone." -ForegroundColor Red
            Write-Host "        Choose another -Path, or empty that folder first." -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "== target already is a clone - fast-forwarding it instead" -ForegroundColor Yellow
        git -C $Path fetch $Remote
        if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] fetch failed (network / auth?)" -ForegroundColor Red; exit 1 }
        git -C $Path checkout $Branch
        git -C $Path pull --ff-only $Remote $Branch
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] update failed - run doctor.ps1 inside that folder" -ForegroundColor Red
            exit 1
        }
        Write-Host ""
        Write-Host "== ready. latest commit:" -ForegroundColor Green
        git -C $Path log -1 --oneline --decorate
        Show-Next $Path
        exit 0
    }
}

# -------------------------------------------------------------- clone it now
Write-Host "== cloning ..." -ForegroundColor Cyan
git clone -b $Branch --single-branch $Url $Path
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] clone failed (network / auth / branch name?)." -ForegroundColor Red
    Write-Host "        Fallback:" -ForegroundColor Yellow
    Write-Host "          git clone $Url `"$Path`"" -ForegroundColor Yellow
    Write-Host "          git -C `"$Path`" checkout $Branch" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "== ready. current branch and latest commit:" -ForegroundColor Green
git -C $Path branch --show-current
git -C $Path log -1 --oneline --decorate
Show-Next $Path
exit 0
