# resume_watch.ps1 - restart the local resident watcher after a reboot (ASCII only, PS5.1 safe)
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\code\resume_watch.ps1              # foreground visible watcher
#   powershell -ExecutionPolicy Bypass -File .\code\resume_watch.ps1 -Register    # register auto-start at logon + start now
#   powershell -ExecutionPolicy Bypass -File .\code\resume_watch.ps1 -Status      # show watcher status only
#   powershell -ExecutionPolicy Bypass -File .\code\resume_watch.ps1 -Interval 1  # custom pull interval (minutes)
param(
    [switch]$Register,
    [switch]$Status,
    [switch]$Unregister,
    [int]$Interval = 2
)
$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
$repo = $here
while ($repo -and -not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    $up = Split-Path -Parent $repo
    if (-not $up -or $up -eq $repo) { break }
    $repo = $up
}
Set-Location -LiteralPath $repo
$watch = Join-Path $repo 'watch-visible.ps1'
if (-not (Test-Path -LiteralPath $watch)) {
    $watch = Join-Path $repo 'watch.ps1'
}
Write-Host "== resume_watch" -ForegroundColor Cyan
Write-Host "   repo   : $repo"
Write-Host "   watcher: $watch"
if (-not (Test-Path -LiteralPath $watch)) {
    Write-Host "   [FAIL] watcher script not found - run: git pull origin arena/01a0a949-zhongqi" -ForegroundColor Red
    exit 1
}
if ($Status -or $Unregister) {
    if ($Unregister) { & $watch -UnregisterVisible } else { & $watch -Status }
    exit 0
}
# quick sync first (never overwrite local work: only fast-forward when the tree is clean)
$dirty = (git status --porcelain | Measure-Object -Line).Lines
if ($dirty -eq 0) {
    Write-Host "   tree   : clean - fast-forward pull ..." -ForegroundColor Green
    git fetch origin 2>&1 | Out-Null
    $br = (git rev-parse --abbrev-ref HEAD).Trim()
    git merge --ff-only "origin/$br" 2>&1 | Out-Null
    Write-Host ("   head   : " + (git rev-parse --short HEAD))
} else {
    Write-Host "   tree   : $dirty modified file(s) - skip pull, keep local work" -ForegroundColor Yellow
}
if ($Register) {
    Write-Host "   action : register auto-start at logon + start now" -ForegroundColor Green
    & $watch -RegisterVisible -Interval $Interval
} else {
    Write-Host "   action : foreground resident watcher (Ctrl+C to stop)" -ForegroundColor Green
    & $watch -Interval $Interval
}
