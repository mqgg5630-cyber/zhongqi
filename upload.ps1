# upload.ps1 - ONE command: copy your files from the sibling attachment folder
# into this repo, then commit + push them to the Arena working branch.
#
# Usage (inside the repo folder):
#     .\upload.ps1
#     .\upload.ps1 -Message "add midterm files"
#     .\upload.ps1 -Src "E:\0zhongqi\attachments"      # explicit source folder
#
# What it does:
#     <any folder next to the repo that contains .docx/.pptx/.pdf files>
#         *.docx *.doc *.pptx *.ppt *.pdf *.md *.txt  ->  sources\
#         *.py                                        ->  code\
#         *.xlsx *.xls *.csv                          ->  results\
#     then it runs push.ps1 (pull --ff-only, git add -A, commit, push).
#
# NOTE: this file is intentionally ASCII-only, and it never contains the
# Chinese folder/file names - they are discovered at runtime by wildcard,
# which is exactly what avoids the GBK decoding problem.

param(
    [string]$Src     = '',
    [string]$Message = ''
)

$ErrorActionPreference = 'Stop'

$repo   = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$parent = Split-Path -Parent $repo

Set-Location -LiteralPath $repo

if (-not (Test-Path (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    Write-Host "        Run this from the cloned folder, e.g. E:\0zhongqi\zhongqi" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- find source
if (-not $Src) {
    $docExt = @('.docx', '.doc', '.pptx', '.ppt', '.pdf')
    $cand = Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -ne $repo } |
        Where-Object {
            @(Get-ChildItem -LiteralPath $_.FullName -File -ErrorAction SilentlyContinue |
              Where-Object { $docExt -contains $_.Extension.ToLower() }).Count -gt 0
        } |
        Select-Object -First 1
    if ($cand) { $Src = $cand.FullName }
}

if (-not $Src -or -not (Test-Path -LiteralPath $Src)) {
    Write-Host "[ERROR] Cannot locate your attachment folder automatically." -ForegroundColor Red
    Write-Host "        Pass it explicitly, e.g.:" -ForegroundColor Yellow
    Write-Host '        .\upload.ps1 -Src "E:\0zhongqi\<your folder>"' -ForegroundColor Yellow
    exit 1
}

$files = @(Get-ChildItem -LiteralPath $Src -File -ErrorAction SilentlyContinue)
if ($files.Count -eq 0) {
    Write-Host "[ERROR] No files found in: $Src" -ForegroundColor Red
    exit 1
}

Write-Host "== source folder: $Src" -ForegroundColor Cyan
Write-Host ("== {0} file(s) found" -f $files.Count) -ForegroundColor Cyan

# ------------------------------------------------------------------ copy them
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'sources') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'code')    | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $repo 'results') | Out-Null

$copied = 0
foreach ($f in $files) {
    $ext = $f.Extension.ToLower()
    $dest = switch ($ext) {
        { $_ -in '.docx', '.doc', '.pptx', '.ppt', '.pdf', '.md', '.txt' } { 'sources' }
        { $_ -in '.py', '.ipynb', '.m', '.r' }                             { 'code'    }
        { $_ -in '.xlsx', '.xls', '.csv' }                                 { 'results' }
        default                                                            { $null     }
    }
    if ($null -eq $dest) {
        Write-Host ("   skip  {0}  (extension not mapped)" -f $f.Name) -ForegroundColor DarkGray
        continue
    }
    Copy-Item -LiteralPath $f.FullName -Destination (Join-Path (Join-Path $repo $dest) $f.Name) -Force
    Write-Host ("   add   {0}  ->  {1}\" -f $f.Name, $dest) -ForegroundColor Green
    $copied++
}

if ($copied -eq 0) {
    Write-Host "[ERROR] Nothing was copied - check the file extensions." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------- and push
$push = Join-Path $repo 'push.ps1'
if (Test-Path -LiteralPath $push) {
    if ([string]::IsNullOrWhiteSpace($Message)) { $Message = 'upload: local documents and data' }
    Write-Host ""
    & $push $Message
} else {
    Write-Host "push.ps1 not found, doing it inline:" -ForegroundColor Yellow
    git add -A
    git commit -m 'upload: local documents and data'
    git push origin arena/01a09d79-zhongqi
}
