# check_deliverables.ps1 - prove that the docx / pptx the agent generated in the
# sandbox really arrived on THIS machine, byte for byte, and that the packages
# are structurally sound (a truncated or stale copy must fail the round).
#
# Source of truth: results\status\agent_manifest.json, written by
# code\build_deliverables.py right before the agent pushed the round.
#
# What is checked, per file in the manifest:
#   a. it exists, and its size is >= the manifest's min_bytes
#   b. its sha256 equals the manifest's sha256  <- "returned to this machine"
#   c. the OOXML package is a valid zip holding the part Word / PowerPoint needs
#      (word/document.xml, ppt/presentation.xml)
#   d. the structure-derived metrics agree with the manifest: slide count for
#      pptx, paragraph / table count for docx (re-derived HERE, independently)
#   e. optional -Com : really open it in Word / PowerPoint on this machine.
#      Off by default because PowerPoint COM paints a window and the watcher is
#      supposed to stay invisible. Turn it on for a one-off deep check:
#          .\code\check_deliverables.ps1 -Com
#
# Run it any time by hand:   .\code\check_deliverables.ps1
# The watcher runs it through code\local_check.ps1 (config key check_cmd).
#
# Exit 0 = everything delivered intact, >0 = number of failed files.
# ASCII-only on purpose (Windows PowerShell 5.1 decodes .ps1 as ANSI/GBK).

param(
    [string]$Manifest = 'results/status/agent_manifest.json',
    [switch]$Com
)

$ErrorActionPreference = 'Continue'
Set-Location (Join-Path $PSScriptRoot '..')   # repo root (this file lives in code\)

$bad = 0
$ok = 0
$warn = 0

function Get-TextSafe {
    param([string]$Path)
    $t = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $t) { $t = '' }
    return $t
}

$manRel = ($Manifest -replace '\\', '/')
$manAbs = Join-Path (Get-Location) ($manRel -replace '/', '\')

if (-not (Test-Path -LiteralPath $manAbs)) {
    Write-Output ('[WARN] ' + $manRel + ' is missing - no agent build round has landed here yet.')
    Write-Output '       The generic success criteria below are the only deliverable check this round.'
    exit 0
}

$man = $null
try {
    $man = (Get-TextSafe $manAbs) | ConvertFrom-Json
} catch {
    Write-Output ('[FAIL] cannot parse ' + $manRel + ' as JSON - ' + $_.Exception.Message)
    exit 1
}
if (-not $man) {
    Write-Output ('[FAIL] ' + $manRel + ' parsed to nothing')
    exit 1
}

Write-Output ('== agent manifest: round ' + [string]$man.round + ' | built ' + [string]$man.generated_at_utc)
Write-Output ('   branch ' + [string]$man.branch + ' | base commit ' + [string]$man.base_commit +
              ' | generator ' + [string]$man.generator)
Write-Output ('   agent-side verdict: ' + [string]$man.verdict +
              ' | rebuilt=' + [string]$man.rebuilt + ' | only=' + [string]$man.only)
if ([string]$man.verdict -ne 'pass') {
    Write-Output ('[FAIL] the agent marked its own round "' + [string]$man.verdict +
                  '" - a round like that must not be sent for a local check')
    $bad = $bad + 1
}

# what the agent said it changed / kept, so the local log tells the same story
$prom = @()
$rest = @()
if ($man.qa) {
    if ($man.qa.promoted) { $prom = @($man.qa.promoted) }
    if ($man.qa.restored_identical) { $rest = @($man.qa.restored_identical) }
    Write-Output ('   content changed this round: ' + $prom.Count +
                  ' file(s) | identical to HEAD (bytes restored): ' + $rest.Count + ' file(s)')
}

Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

$wordApp = $null
$ppApp = $null
if ($Com) {
    try { $wordApp = New-Object -ComObject Word.Application } catch { $wordApp = $null }
    if ($wordApp) {
        try { $wordApp.DisplayAlerts = 0 } catch { }
        try { $wordApp.AutomationSecurity = 3 } catch { }
    } else {
        Write-Output '[WARN] -Com asked for Word but Word.Application could not be created'
        $warn = $warn + 1
    }
    try { $ppApp = New-Object -ComObject PowerPoint.Application } catch { $ppApp = $null }
    if (-not $ppApp) {
        Write-Output '[WARN] -Com asked for PowerPoint but PowerPoint.Application could not be created'
        $warn = $warn + 1
    }
}

foreach ($f in @($man.files)) {
    if (-not $f) { continue }
    $rel = [string]$f.path
    if (-not $rel) { continue }
    $kind = [string]$f.kind
    $fp = Join-Path (Get-Location) ($rel -replace '/', '\')

    # the manifest lists itself - a self-hash can never match, so only report it
    if ($kind -eq 'manifest') {
        if (Test-Path -LiteralPath $fp) {
            Write-Output ('   OK   ' + $rel + ' (self-reference, not hash-checked)')
            $ok = $ok + 1
        }
        continue
    }

    if (-not (Test-Path -LiteralPath $fp)) {
        Write-Output ('   FAIL missing       ' + $rel)
        $bad = $bad + 1
        continue
    }

    $sz = [int64](Get-Item -LiteralPath $fp).Length
    $minSz = [int64]0
    if ($f.min_bytes) { $minSz = [int64]$f.min_bytes }
    if ($sz -lt $minSz) {
        Write-Output ('   FAIL too small     ' + $rel + ' (' + $sz + ' B < ' + $minSz + ' B)')
        $bad = $bad + 1
        continue
    }

    # b. the hash - this is the "it came back to my machine" proof
    $want = ''
    if ($f.sha256) { $want = ([string]$f.sha256).ToLowerInvariant() }
    $got = ''
    try { $got = (Get-FileHash -LiteralPath $fp -Algorithm SHA256).Hash.ToLowerInvariant() } catch { $got = '' }
    if ($want -and $got -ne $want) {
        Write-Output ('   FAIL sha256        ' + $rel)
        Write-Output ('        this machine ' + $got)
        Write-Output ('        agent built  ' + $want)
        Write-Output '        (stale or truncated copy - run .\sync.ps1 and let the round repeat)'
        $bad = $bad + 1
        continue
    }

    $detail = ''
    if ($kind -eq 'docx' -or $kind -eq 'pptx') {
        $zip = $null
        try { $zip = [System.IO.Compression.ZipFile]::OpenRead($fp) } catch { $zip = $null }
        if (-not $zip) {
            Write-Output ('   FAIL not a package ' + $rel + ' (zip open failed - the file is corrupt)')
            $bad = $bad + 1
            continue
        }
        try {
            $names = @($zip.Entries | ForEach-Object { $_.FullName })
            if ($kind -eq 'docx') { $need = 'word/document.xml' } else { $need = 'ppt/presentation.xml' }
            if ($names -notcontains $need) {
                Write-Output ('   FAIL bad package  ' + $rel + ' (no ' + $need + ')')
                $bad = $bad + 1
                continue
            }

            # d. re-derive the metrics here, independently of the agent
            if ($kind -eq 'pptx') {
                $slides = @($names | Where-Object { $_ -match '^ppt/slides/slide[0-9]+\.xml$' }).Count
                $detail = 'slides=' + $slides
                if ($f.metrics -and $f.metrics.slides) {
                    $wantSlides = [int]$f.metrics.slides
                    if ($slides -ne $wantSlides) {
                        Write-Output ('   FAIL slide count  ' + $rel + ' (here ' + $slides +
                                      ', agent ' + $wantSlides + ')')
                        $bad = $bad + 1
                        continue
                    }
                }
            } else {
                $entry = $zip.Entries | Where-Object { $_.FullName -eq 'word/document.xml' } | Select-Object -First 1
                $xml = ''
                if ($entry) {
                    $sr = New-Object System.IO.StreamReader($entry.Open())
                    $xml = $sr.ReadToEnd()
                    $sr.Close()
                }
                $paras = ([regex]::Matches($xml, '<w:p[ >/]')).Count
                $tbls = ([regex]::Matches($xml, '<w:tbl[ >/]')).Count
                $detail = 'paragraphs=' + $paras + ' tables=' + $tbls
                if ($f.metrics) {
                    if ($f.metrics.paragraphs -and $paras -ne [int]$f.metrics.paragraphs) {
                        Write-Output ('   FAIL paragraph count ' + $rel + ' (here ' + $paras +
                                      ', agent ' + [int]$f.metrics.paragraphs + ')')
                        $bad = $bad + 1
                        continue
                    }
                    if ($f.metrics.tables -and $tbls -ne [int]$f.metrics.tables) {
                        Write-Output ('   FAIL table count  ' + $rel + ' (here ' + $tbls +
                                      ', agent ' + [int]$f.metrics.tables + ')')
                        $bad = $bad + 1
                        continue
                    }
                }
            }
        } finally {
            try { $zip.Dispose() } catch { }
        }
    } elseif ($kind -eq 'md' -or $kind -eq 'manifest') {
        $lines = @(Get-Content -LiteralPath $fp -Encoding UTF8 -ErrorAction SilentlyContinue)
        $detail = 'lines=' + $lines.Count
    }

    # e. optional: let the real Office on this machine open it
    if ($Com) {
        if ($kind -eq 'docx' -and $wordApp) {
            $doc = $null
            try {
                $doc = $wordApp.Documents.Open($fp, $false, $true, $false)
                $pages = $doc.ComputeStatistics(2)     # 2 = wdStatisticPages
                $words = $doc.ComputeStatistics(0)     # 0 = wdStatisticWords
                $detail = $detail + ' word-pages=' + $pages + ' word-words=' + $words
                $doc.Close($false)
                $doc = $null
            } catch {
                Write-Output ('   FAIL Word cannot open ' + $rel + ' - ' + $_.Exception.Message)
                $bad = $bad + 1
                if ($doc) { try { $doc.Close($false) } catch { } }
                continue
            }
        }
        if ($kind -eq 'pptx' -and $ppApp) {
            $pres = $null
            try {
                $pres = $ppApp.Presentations.Open($fp, $true, $false, $false)
                $detail = $detail + ' pp-slides=' + $pres.Slides.Count
                $pres.Close()
                $pres = $null
            } catch {
                Write-Output ('   FAIL PowerPoint cannot open ' + $rel + ' - ' + $_.Exception.Message)
                $bad = $bad + 1
                if ($pres) { try { $pres.Close() } catch { } }
                continue
            }
        }
    }

    $prefix = $got
    if ($got.Length -ge 12) { $prefix = $got.Substring(0, 12) }
    Write-Output ('   OK   ' + ([string]$rel).PadRight(46) + ([string]$sz).PadLeft(9) +
                  ' B  sha256 ' + $prefix + '  ' + $detail)
    $ok = $ok + 1
}

if ($wordApp) { try { $wordApp.Quit() } catch { } }
if ($ppApp) { try { $ppApp.Quit() } catch { } }

Write-Output ('== deliverables on this machine: ' + $ok + ' intact, ' + $bad + ' failed, ' + $warn + ' warning(s)')
if ($bad -eq 0) {
    Write-Output '== the docx / pptx of this round are on this machine and byte-identical to what the agent built'
} else {
    Write-Output '== run .\sync.ps1 (or let the watcher auto_pull) and let the agent repeat the round'
}
exit $bad
