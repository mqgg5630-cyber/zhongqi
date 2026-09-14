# download.ps1 - copy chosen folders FROM the repo TO a local folder (robocopy).
#
# Usage (inside the repo folder):
#     .\download.ps1                    # default set "final" -> <parent>\<repo>_out
#     .\download.ps1 -Set final         # the deliverable folders (see -List)
#     .\download.ps1 -Set preview       # results\ppt_preview + results\figures
#     .\download.ps1 -Set all -Dest "E:\submission"
#     .\download.ps1 -List              # show the sets defined in sync.config.json
#
# Folder names (including Chinese ones) live in sync.config.json, NOT in this
# file: Windows PowerShell 5.1 decodes a .ps1 without BOM as ANSI/GBK, so this
# script must stay pure ASCII. JSON is read explicitly as UTF-8.
#
# robocopy exit codes: 0-7 = OK/nothing to do, 8+ = real error.

param(
    [string]$Set   = 'final',
    [string]$Dest  = '',
    [switch]$Mirror,
    [switch]$List
)

$ErrorActionPreference = 'Stop'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

# ------------------------------------------------------------------- config
$cfgPath = @(
    (Join-Path $repo 'skills\git-sync\sync.config.json'),
    (Join-Path $PSScriptRoot 'sync.config.json')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $cfgPath) {
    Write-Host "[ERROR] sync.config.json not found next to this script or in skills\git-sync\." -ForegroundColor Red
    exit 1
}
$cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
Write-Host "== config: $cfgPath" -ForegroundColor Cyan

$setNames = @($cfg.download_sets.PSObject.Properties | ForEach-Object { $_.Name })

if ($List) {
    Write-Host "== available sets:" -ForegroundColor Cyan
    foreach ($p in $cfg.download_sets.PSObject.Properties) {
        Write-Host ("   {0,-8} {1}" -f $p.Name, ($p.Value -join ', '))
    }
    exit 0
}

if ($setNames -notcontains $Set) {
    Write-Host ("[ERROR] unknown set '{0}'. Available: {1}" -f $Set, ($setNames -join ', ')) -ForegroundColor Red
    exit 1
}
$folders = @($cfg.download_sets.$Set)

if (-not $Dest) {
    if ($cfg.download_dir) {
        $Dest = $cfg.download_dir
    } else {
        $Dest = Join-Path (Split-Path -Parent $repo) ((Split-Path -Leaf $repo) + '_out')
    }
}
if (-not (Test-Path -LiteralPath $Dest)) { New-Item -ItemType Directory -Force -Path $Dest | Out-Null }

Write-Host "== set    : $Set  ($($folders.Count) folder(s))" -ForegroundColor Cyan
Write-Host "== dest   : $Dest" -ForegroundColor Cyan

$fail = 0
foreach ($rel in $folders) {
    $src = Join-Path $repo $rel
    if (-not (Test-Path -LiteralPath $src)) {
        Write-Host ("   skip  {0}  (not in the repo)" -f $rel) -ForegroundColor DarkGray
        continue
    }
    $dst = Join-Path $Dest $rel
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    $roboArgs = @($src, $dst, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/R:1', '/W:1')
    if ($Mirror) { $roboArgs += '/MIR' }
    Write-Host ("   copy  {0}  ->  {1}" -f $rel, $Dest) -ForegroundColor Green
    robocopy @roboArgs | Out-Null
    $code = $LASTEXITCODE
    if ($code -ge 8) {
        Write-Host ("   [ERROR] robocopy failed on {0} (exit {1})" -f $rel, $code) -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
if ($fail -eq 0) {
    Write-Host "== done. latest commit:" -ForegroundColor Green
    git log -1 --oneline
} else {
    Write-Host ("== finished with {0} error(s)" -f $fail) -ForegroundColor Red
    exit 1
}
