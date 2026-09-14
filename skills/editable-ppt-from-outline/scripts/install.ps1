# install.ps1 - copy the editable-PPT pipeline into another project
# Usage:  .\install.ps1 -Target C:\MyNewProject
# The generated project then only needs docs\ppt_outline.json + results\figures\*.png

param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Source = (Resolve-Path "$PSScriptRoot\..\..\..").Path
)

$ErrorActionPreference = "Stop"

$scripts = @(
    "code\make_ppt.py",
    "code\make_ppt2.py",
    "code\make_ppt_variants.py",
    "code\outline_to_md.py",
    "code\add_notes.py",
    "code\check_ppt.py",
    "code\preview_ppt.py",
    "code\get_cjk_font.py",
    "code\make_figures2.py"
)

Write-Host "source : $Source"
Write-Host "target : $Target"

foreach ($dir in @("code", "docs", "results\figures", "deliverable\versions", "build")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Target $dir) | Out-Null
}

foreach ($rel in $scripts) {
    $src = Join-Path $Source $rel
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $Target $rel)
        Write-Host "  copied $rel"
    } else {
        Write-Host "  MISSING $rel" -ForegroundColor Yellow
    }
}

$outline = Join-Path $Target "docs\ppt_outline.json"
if (-not (Test-Path $outline)) {
    Copy-Item -Force (Join-Path $PSScriptRoot "..\outline.template.json") $outline
    Write-Host "  created docs\ppt_outline.json (from template)"
} else {
    Write-Host "  kept existing docs\ppt_outline.json"
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  cd $Target"
Write-Host "  pip install python-pptx matplotlib pillow fonttools noto-cjk-sans-otc"
Write-Host "  python code/get_cjk_font.py"
Write-Host "  python code/make_ppt_variants.py --style B"
Write-Host "  python code/check_ppt.py deliverable\*.pptx"
