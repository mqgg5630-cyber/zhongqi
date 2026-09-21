# watch-visible.ps1 - resident visible window watcher (ASCII-only, PS5.1 safe)
# Fixes flash issue: keeps ONE window resident showing pull info
# Usage:
#   .\watch-visible.ps1                 # foreground resident, every 2 min auto pull
#   .\watch-visible.ps1 -Interval 2     # custom interval minutes
#   .\watch-visible.ps1 -RegisterVisible # register auto-start visible task at logon
#   .\watch-visible.ps1 -Status
#   .\watch-visible.ps1 -UnregisterVisible
#
# Features:
# - No hidden launcher, window stays visible
# - Real-time sync.ps1 pull info, timestamp, branch, heartbeat
# - Supports hands-free auto push
# - Can coexist with original watch.ps1 zero-window version

param(
    [int]$Interval = 2,
    [switch]$RegisterVisible,
    [switch]$UnregisterVisible,
    [switch]$Status,
    [string]$Config = ''
)

$ErrorActionPreference = 'Continue'
$repo = $PSScriptRoot
while ($repo -and -not (Test-Path -LiteralPath (Join-Path $repo '.git'))) {
    $up = Split-Path -Parent $repo
    if (-not $up -or $up -eq $repo) { break }
    $repo = $up
}
Set-Location -LiteralPath $repo
$repoName = Split-Path -Leaf $repo

# config
$cfgPath = @()
if ($Config) { $cfgPath += $Config }
$cfgPath += @(
    (Join-Path $repo 'skills\git-sync\sync.config.json'),
    (Join-Path $PSScriptRoot 'sync.config.json')
)
$cfgPath = $cfgPath | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$Branch = ''
$Remote = 'origin'
$HandsFree = $true
$AutoPull = $true
$AutoPush = $true
if ($cfgPath) {
    try {
        $cfg = Get-Content -LiteralPath $cfgPath -Encoding UTF8 -Raw | ConvertFrom-Json
        if ($cfg.branch) { $Branch = [string]$cfg.branch }
        if ($cfg.remote) { $Remote = [string]$cfg.remote }
        if ($null -ne $cfg.hands_free) { $HandsFree = [bool]$cfg.hands_free }
        if ($null -ne $cfg.auto_pull) { $AutoPull = [bool]$cfg.auto_pull }
        if ($null -ne $cfg.auto_push) { $AutoPush = [bool]$cfg.auto_push }
    } catch {}
}
if (-not $Branch) { try { $Branch = (git rev-parse --abbrev-ref HEAD).Trim() } catch { $Branch = 'arena/01a0a949-zhongqi' } }

$taskNameVisible = "git-sync-watch-visible-$repoName"

function Get-VisibleTask {
    try { return Get-ScheduledTask -TaskName $taskNameVisible -ErrorAction Stop } catch { return $null }
}

if ($Status) {
    Write-Host "== visible watcher status" -ForegroundColor Cyan
    Write-Host "   repo   : $repo"
    Write-Host "   branch : $Branch (remote $Remote)"
    Write-Host "   task   : $taskNameVisible"
    $t = Get-VisibleTask
    if ($t) {
        Write-Host "   scheduled : $($t.State)" -ForegroundColor Green
        try { $info = Get-ScheduledTaskInfo -TaskName $taskNameVisible -ErrorAction Stop; Write-Host "   last run : $($info.LastRunTime) result $($info.LastTaskResult) next $($info.NextRunTime)" } catch {}
    } else {
        Write-Host "   scheduled : NOT REGISTERED" -ForegroundColor Yellow
    }
    exit 0
}

if ($UnregisterVisible) {
    try { Unregister-ScheduledTask -TaskName $taskNameVisible -Confirm:$false -ErrorAction Stop; Write-Host "== removed $taskNameVisible" -ForegroundColor Green } catch { Write-Host "not found" }
    exit 0
}

if ($RegisterVisible) {
    $psExe = (Get-Command powershell -ErrorAction SilentlyContinue).Source
    if (-not $psExe) { $psExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" }
    $scriptPath = Join-Path $repo 'watch-visible.ps1'
    $action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -NoExit -File `"$scriptPath`" -Interval $Interval" -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Days 3650)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $desc = "git-sync visible watcher (resident window) | $repo | every ${Interval}m"
    try {
        Register-ScheduledTask -TaskName $taskNameVisible -Action $action -Trigger @($trigger,$trigger2) -Settings $settings -Description $desc -Force | Out-Null
        Write-Host "== registered visible watcher: $taskNameVisible (window will stay)" -ForegroundColor Green
        Write-Host "   it will open a PowerShell window at logon that stays resident and shows pull info"
        Write-Host "   to test now: .\watch-visible.ps1"
        Write-Host "   to remove: .\watch-visible.ps1 -UnregisterVisible"
    } catch {
        Write-Host "[ERROR] register failed: $($_.Exception.Message)" -ForegroundColor Red
    }
    exit 0
}

# ---- main loop (visible resident) ----
$Host.UI.RawUI.WindowTitle = "git-sync visible watcher - $repoName [$Branch] - resident"
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  git-sync resident visible watcher" -ForegroundColor Cyan
Write-Host "  repo: $repo" -ForegroundColor Gray
Write-Host "  branch: $Remote/$Branch" -ForegroundColor Gray
Write-Host "  interval: every $Interval minutes auto pull" -ForegroundColor Gray
Write-Host "  mode: resident window, real-time pull info" -ForegroundColor Gray
Write-Host "  closing this window = pause watcher (keeper restarts in 10 min)" -ForegroundColor Yellow
Write-Host "  open NEW window for your commands, not here" -ForegroundColor DarkGray
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$loopCount = 0
while ($true) {
    $loopCount++
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] ===== round $loopCount =====" -ForegroundColor Cyan
    
    # 1. dirty status
    try {
        $status = git status --porcelain -uall 2>$null
        if ($status) {
            $cnt = @($status).Count
            Write-Host "[$now] local dirty ($cnt files):" -ForegroundColor Yellow
            $status | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
        } else {
            Write-Host "[$now] local clean" -ForegroundColor DarkGray
        }
    } catch {}

    # 2. auto pull with schannel auto-fix (2026-09-21 hands-free)
    if ($AutoPull) {
        Write-Host "[$now] -> pulling $Remote/$Branch ..." -ForegroundColor Green
        $syncScript = Join-Path $repo 'sync.ps1'
        if (Test-Path $syncScript) {
            try {
                $out = & $syncScript 2>&1 | Out-String
                if ($out) {
                    $lines = $out -split "`r?`n" | Where-Object { $_ -match '\S' } | Select-Object -Last 30
                    $hasError = $false
                    foreach ($l in $lines) {
                        if ($l -match 'ERROR|FAIL|conflict|diverg|schannel|server closed abruptly|unable to access') {
                            Write-Host "  $l" -ForegroundColor Red
                            $hasError = $true
                        } elseif ($l -match 'Already up|up to date|ok|pulled|fetch|Fast-forward|Updating') {
                            Write-Host "  $l" -ForegroundColor Green
                        } else {
                            Write-Host "  $l" -ForegroundColor Gray
                        }
                    }
                    if ($hasError -and ($out -match 'schannel|server closed abruptly|SSL|TLS')) {
                        Write-Host "  [AUTO-FIX] schannel failure detected, switching to openssl + HTTP/1.1 (hands-free)" -ForegroundColor Yellow
                        try { git config --global http.sslBackend openssl 2>$null; Write-Host "    -> set global http.sslBackend openssl" -ForegroundColor DarkGray } catch {}
                        try { git config --global http.version HTTP/1.1 2>$null; Write-Host "    -> set global http.version HTTP/1.1" -ForegroundColor DarkGray } catch {}
                        try { git config --global http.postBuffer 524288000 2>$null } catch {}
                        try { git config http.sslBackend openssl 2>$null } catch {}
                        try { git config http.version HTTP/1.1 2>$null } catch {}
                        Write-Host "  [AUTO-FIX] will retry next round ($Interval min), no manual action needed" -ForegroundColor Green
                    }
                }
            } catch {
                Write-Host "  pull error: $($_.Exception.Message)" -ForegroundColor Red
                Write-Host "  [AUTO-FIX] will retry next round, hands-free" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  sync.ps1 not found, try git pull" -ForegroundColor Yellow
            try { git fetch $Remote --quiet; git pull --ff-only $Remote $Branch 2>&1 | ForEach-Object { Write-Host "  $_" } } catch {}
        }
    }

    # 3. last commits
    try {
        $last = git log --oneline -5 2>$null
        if ($last) {
            Write-Host "[$now] last 5 commits:" -ForegroundColor DarkCyan
            $last | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        }
    } catch {}

    # 4. auto push
    if ($AutoPush) {
        $dirty = git status --porcelain -uall 2>$null
        if ($dirty) {
            Write-Host "[$now] -> local changes, trying auto push..." -ForegroundColor Yellow
            $pushScript = Join-Path $repo 'push.ps1'
            if (Test-Path $pushScript) {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                try {
                    $out = & $pushScript -NoPrompt "local: auto $stamp" 2>&1 | Out-String
                    if ($out) { $out -split "`r?`n" | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray } }
                } catch { Write-Host "  push error: $($_.Exception.Message)" -ForegroundColor Red }
            }
        }
    }

    # 5. handshake check
    try {
        $hsPath = Join-Path $repo 'results/status/handshake.json'
        if (Test-Path $hsPath) {
            $hs = Get-Content $hsPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($hs -and $hs.arena_state -eq 'awaiting_check' -and $hs.local_state -eq 'pending') {
                Write-Host "[$now] !!! Agent requests local check round $($hs.round) !!!" -ForegroundColor Red -BackgroundColor Yellow
                Write-Host "  running local check..." -ForegroundColor Yellow
                $checkScript = Join-Path $repo 'code/local_check.ps1'
                if (Test-Path $checkScript) {
                    try { & $checkScript 2>&1 | ForEach-Object { Write-Host "  $_" } } catch {}
                }
            }
        }
    } catch {}

    # 6. heartbeat
    $next = (Get-Date).AddMinutes($Interval).ToString('HH:mm:ss')
    Write-Host "[$now] round done, next pull at $next (Ctrl+C to stop)" -ForegroundColor DarkGray
    Write-Host ""

    Start-Sleep -Seconds ($Interval * 60)
}
