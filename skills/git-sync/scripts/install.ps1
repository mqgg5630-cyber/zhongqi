# install.ps1 - copy the sync toolkit into another repo and write its config.
#
# Usage (from anywhere):
#     .\install.ps1 -Target C:\MyProject
#     .\install.ps1 -Target C:\MyProject -Branch main -DownloadDir "C:\out"
#
# It copies sync/push/upload/download/doctor/pack/bootstrap into the target repo
# root (plus the .cmd wrappers that can be double-clicked), and creates
# <target>\sync.config.json (UTF-8) with the branch, remote and folder sets. The .ps1 files stay ASCII; only the JSON carries folder names.
#
# ASCII-only on purpose (Windows PowerShell 5.1 decodes .ps1 as ANSI/GBK).

param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Branch      = '',
    [string]$Remote      = 'origin',
    [string]$DownloadDir = ''
)

$ErrorActionPreference = 'Stop'

$here = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$src  = Resolve-Path (Join-Path $here '..').Path          # the skill folder

if (-not (Test-Path -LiteralPath $Target)) {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
}

$files = @('sync.ps1', 'push.ps1', 'upload.ps1', 'download.ps1',
           'doctor.ps1', 'pack.ps1', 'bootstrap.ps1', 'reclone.ps1',
           'sync.cmd', 'download.cmd', 'doctor.cmd', 'bootstrap.cmd', 'reclone.cmd')

Write-Host "source : $src"
Write-Host "target : $Target"
foreach ($f in $files) {
    $from = Join-Path $src ('scripts\' + $f)
    if (Test-Path -LiteralPath $from) {
        Copy-Item -Force -LiteralPath $from -Destination (Join-Path $Target $f)
        Write-Host "  copied $f"
    } else {
        Write-Host "  MISSING $f" -ForegroundColor Yellow
    }
}

# write the config (UTF-8, no BOM: git and PowerShell both read it fine)
$cfgSrc = Join-Path $src 'sync.config.json'
$cfgDst = Join-Path $Target 'sync.config.json'
if (Test-Path -LiteralPath $cfgSrc) {
    $cfg = Get-Content -LiteralPath $cfgSrc -Encoding UTF8 -Raw | ConvertFrom-Json
    if ($Branch)      { $cfg.branch = $Branch }
    if ($Remote)      { $cfg.remote = $Remote }
    if ($DownloadDir) { $cfg.download_dir = $DownloadDir }
    $cfg | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $cfgDst -Encoding UTF8
    Write-Host "  wrote  sync.config.json"
} else {
    Write-Host "  sync.config.json template missing - skipped" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "== next steps in $Target" -ForegroundColor Cyan
Write-Host "   .\bootstrap.ps1                 first-time setup (policy, identity, branch)"
Write-Host "   .\sync.ps1 / .\upload.ps1       pull / upload"
Write-Host "   .\download.ps1 -List            show the download sets"
Write-Host "   (or just double-click sync.cmd / download.cmd / reclone.cmd)"
Write-Host "   edit sync.config.json to change the branch, sets or download folder"
