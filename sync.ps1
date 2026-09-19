# sync.ps1 (skill version) - pull the latest code from the working branch.
#
# Usage (inside the repo folder):
#     .\sync.ps1
#     .\sync.ps1 -Branch arena/01a09d79-zhongqi
#     .\sync.ps1 -NoStash              # keep local changes as they are
#     .\sync.ps1 -Retries 5            # more fetch attempts
#
# The branch defaults to sync.config.json (keys: branch / remote), so the same
# script works in any repo that carries that file.
#
# Differences from the simple version
#   * fetch is retried a few times (schannel / TLS handshakes fail on flaky or
#     filtered networks);
#   * the fast-forward uses `git merge --ff-only <remote>/<branch>` on the ref
#     that fetch just updated - so no SECOND network round-trip is needed (the
#     old script fetched, then `git pull` fetched again and that second
#     connection was the one that died with "schannel: failed to receive
#     handshake");
#   * local changes are stashed and restored automatically after the update;
#     if the restore conflicts, the stash is kept (nothing is ever lost);
#   * on a network error it prints exactly which git config to try.
#
# ASCII-only on purpose: Windows PowerShell 5.1 decodes a .ps1 without BOM as
# ANSI/GBK and Chinese text would break the parser.

param(
    [string]$Branch = '',
    [string]$Remote = '',
    [int]$Retries = 3,
    [switch]$NoStash
)

$ErrorActionPreference = 'Continue'

$repo = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location -LiteralPath $repo

if (-not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    Write-Host "[ERROR] Not a git repository: $repo" -ForegroundColor Red
    Write-Host "        Run this from the cloned folder (e.g. E:\0zhongqi\zhongqi)." -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------- helpers
function Invoke-Git {
    param([string[]]$GitArgs)
    $out = & git $GitArgs 2>&1
    $code = $LASTEXITCODE
    return @{ Code = $code; Out = (($out | Out-String).Trim()) }
}

function Get-LastLine {
    param([string]$Text)
    $lines = @($Text -split "`r?`n" | Where-Object { $_.Trim() })
    if ($lines.Count -eq 0) { return '' }
    return $lines[$lines.Count - 1].Trim()
}

function Show-NetworkHelp {
    param([string]$Detail)
    Write-Host ""
    Write-Host "[ERROR] git cannot reach the remote (network / TLS / proxy)." -ForegroundColor Red
    if ($Detail) { Write-Host "        last error: $Detail" -ForegroundColor DarkGray }
    Write-Host ""
    Write-Host "Try these, one at a time (each line is a separate command):" -ForegroundColor Yellow
    Write-Host "  1) just retry - handshake failures are often transient:"
    Write-Host "       .\sync.ps1"
    Write-Host "  2) force the OpenSSL TLS backend (fixes most 'schannel' errors):"
    Write-Host "       git config --global http.sslBackend openssl"
    Write-Host "  3) force HTTP/1.1 (old schannel + HTTP/2 handshake flakes):"
    Write-Host "       git config --global http.version HTTP/1.1"
    Write-Host "  4) go through your local proxy if you run one (Clash / V2Ray port 7890):"
    Write-Host "       git config --global http.proxy http://127.0.0.1:7890"
    Write-Host "       git config --global https.proxy http://127.0.0.1:7890"
    Write-Host "  5) SSH over port 443 (needs an SSH key registered on GitHub):"
    Write-Host "       git remote set-url origin git@github.com:mqgg5630-cyber/zhongqi.git"
    Write-Host "       ssh -T -p 443 git@ssh.github.com"
    Write-Host ""
    Write-Host "Undo any of the settings above with:" -ForegroundColor DarkGray
    Write-Host "       git config --global --unset http.sslBackend" -ForegroundColor DarkGray
    Write-Host "       git config --global --unset http.version" -ForegroundColor DarkGray
    Write-Host "       git config --global --unset http.proxy" -ForegroundColor DarkGray
    Write-Host "       git config --global --unset https.proxy" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Nothing was changed and nothing was lost. Check the state with:" -ForegroundColor Yellow
    Write-Host "       .\doctor.ps1        (shows branch / ahead / behind / stash)"
}

# ------------------------------------------------------------------- config
$cfgPath = @(
    (Join-Path $repo 'skills\git-sync\sync.config.json'),
    (Join-Path $PSScriptRoot 'sync.config.json')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($cfgPath) {
    $cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if (-not $Branch -and $cfg.branch) { $Branch = [string]$cfg.branch }
    if (-not $Remote -and $cfg.remote) { $Remote = [string]$cfg.remote }
}
if (-not $Remote) { $Remote = 'origin' }
if (-not $Branch) { $Branch = (git rev-parse --abbrev-ref HEAD).Trim() }

Write-Host "== repo  : $repo" -ForegroundColor Cyan
Write-Host "== branch: $Branch" -ForegroundColor Cyan

# ------------------------------------------------------------------- fetch
$fetched = $false
for ($try = 1; $try -le [Math]::Max($Retries, 1); $try++) {
    $fetch = Invoke-Git @('fetch', $Remote, '--prune')
    if ($fetch.Code -eq 0) { $fetched = $true; break }
    Write-Host ("!! fetch attempt {0}/{1} failed: {2}" -f $try, $Retries, (Get-LastLine $fetch.Out)) -ForegroundColor Yellow
    if ($try -lt $Retries) { Start-Sleep -Seconds (2 * $try) }
}
if (-not $fetched) {
    Show-NetworkHelp (Get-LastLine $fetch.Out)
    exit 1
}
Write-Host "OK fetch $Remote" -ForegroundColor Green

# ------------------------------------------------------------------- stash
$stashed = $false
$stashName = ''
if (-not $NoStash) {
    $dirty = @(git status --porcelain)
    if ($dirty.Count -gt 0) {
        Write-Host ("!! local changes found ({0} file(s)), stashing them first ..." -f $dirty.Count) -ForegroundColor Yellow
        $stashName = "auto-stash before sync " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
        $st = Invoke-Git @('stash', 'push', '-u', '-m', $stashName)
        if ($st.Code -ne 0) {
            Write-Host "[ERROR] git stash failed." -ForegroundColor Red
            Write-Host $st.Out -ForegroundColor DarkGray
            exit 1
        }
        $stashed = $true
    }
}

# ------------------------------------------------------------------- update
$co = Invoke-Git @('checkout', $Branch)
if ($co.Code -ne 0) {
    Write-Host "[ERROR] git checkout $Branch failed." -ForegroundColor Red
    Write-Host $co.Out -ForegroundColor DarkGray
    if ($stashed) { Write-Host "        Your changes are in the stash: git stash pop" -ForegroundColor Yellow }
    exit 1
}

$target = "$Remote/$Branch"
# fast-forward onto the ref that fetch just updated: no second network call
$merge = Invoke-Git @('merge', '--ff-only', $target)
if ($merge.Code -ne 0) {
    Write-Host "[ERROR] cannot fast-forward to $target." -ForegroundColor Red
    Write-Host $merge.Out -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "        If it says 'local commits / diverged', your local branch has commits" -ForegroundColor Yellow
    Write-Host "        that the remote does not. Look first, then decide:" -ForegroundColor Yellow
    Write-Host "          git status" -ForegroundColor Yellow
    Write-Host "          git log --oneline --graph --decorate -15" -ForegroundColor Yellow
    Write-Host "          git reset --hard $target        # throw the local commits away" -ForegroundColor Yellow
    if ($stashed) { Write-Host "        Your changes are in the stash: git stash pop" -ForegroundColor Yellow }
    exit 1
}

Write-Host ""
Write-Host "== up to date. latest commit:" -ForegroundColor Green
git log -1 --oneline --decorate

# ------------------------------------------------------------------- restore
if ($stashed) {
    $pop = Invoke-Git @('stash', 'pop')
    if ($pop.Code -eq 0) {
        Write-Host ""
        Write-Host "== your local changes were restored (git stash pop)" -ForegroundColor Green
        Write-Host ($pop.Out | Select-Object -First 1)
    } else {
        Write-Host ""
        Write-Host "!! could not restore the stashed changes (probably a conflict)." -ForegroundColor Yellow
        Write-Host "   Nothing is lost - the stash is still there. See and fix:" -ForegroundColor Yellow
        Write-Host "     git stash list" -ForegroundColor Yellow
        Write-Host "     git status" -ForegroundColor Yellow
        Write-Host "   Or throw the local changes away:" -ForegroundColor DarkGray
        Write-Host "     git checkout -- .   /   git stash drop" -ForegroundColor DarkGray
    }
}

exit 0
