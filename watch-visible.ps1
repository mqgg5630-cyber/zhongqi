# watch-visible.ps1 - 常驻可见窗口版值守，解决“闪窗”问题，满足“一直一个窗口常驻，上面有拉取信息”
# 用法：
#   .\watch-visible.ps1                 # 前台常驻，每2分钟自动拉取，窗口一直显示拉取信息
#   .\watch-visible.ps1 -Interval 2     # 自定义间隔分钟
#   .\watch-visible.ps1 -RegisterVisible # 注册为开机自启动的可见任务（会在登录后打开一个常驻窗口）
#
# 特点：
# - 不使用隐藏launcher，窗口一直可见
# - 实时显示 sync.ps1 拉取信息、时间戳、分支、heartbeat
# - 支持 hands-free 自动推送本地修改
# - 可与原有 watch.ps1 共存，原有零窗口任务可保留或暂停

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
    # 注册一个可见窗口的任务，登录后启动 powershell -NoExit 保持窗口
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
Write-Host "  git-sync 常驻可见窗口版值守" -ForegroundColor Cyan
Write-Host "  仓库: $repo" -ForegroundColor Gray
Write-Host "  分支: $Remote/$Branch" -ForegroundColor Gray
Write-Host "  间隔: 每 $Interval 分钟自动拉取" -ForegroundColor Gray
Write-Host "  模式: 常驻窗口，实时显示拉取信息" -ForegroundColor Gray
Write-Host "  关闭此窗口 = 暂停值守 (10分钟后keeper会重启，或手动再运行)" -ForegroundColor Yellow
Write-Host "  另开窗口执行命令，不在此窗口输入" -ForegroundColor DarkGray
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$loopCount = 0
while ($true) {
    $loopCount++
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] ===== 第 $loopCount 轮轮询 =====" -ForegroundColor Cyan
    
    # 1. 显示当前状态
    try {
        $status = git status --porcelain -uall 2>$null
        if ($status) {
            Write-Host "[$now] 本地有未提交修改 ($($status.Count) 文件):" -ForegroundColor Yellow
            $status | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkYellow }
        } else {
            Write-Host "[$now] 本地干净" -ForegroundColor DarkGray
        }
    } catch {}

    # 2. 自动拉取
    if ($AutoPull) {
        Write-Host "[$now] -> 正在拉取 $Remote/$Branch ..." -ForegroundColor Green
        $syncScript = Join-Path $repo 'sync.ps1'
        if (Test-Path $syncScript) {
            try {
                $out = & $syncScript 2>&1 | Out-String
                if ($out) {
                    $lines = $out -split "`r?`n" | Where-Object { $_ -match '\S' } | Select-Object -Last 20
                    foreach ($l in $lines) {
                        if ($l -match 'ERROR|FAIL|conflict|diverg') {
                            Write-Host "  $l" -ForegroundColor Red
                        } elseif ($l -match 'Already up|up to date|ok|pulled|fetch') {
                            Write-Host "  $l" -ForegroundColor Green
                        } else {
                            Write-Host "  $l" -ForegroundColor Gray
                        }
                    }
                }
            } catch {
                Write-Host "  拉取异常: $($_.Exception.Message)" -ForegroundColor Red
            }
        } else {
            Write-Host "  sync.ps1 未找到，尝试 git pull" -ForegroundColor Yellow
            try { git fetch $Remote --quiet; git pull --ff-only $Remote $Branch 2>&1 | ForEach-Object { Write-Host "  $_" } } catch {}
        }
    }

    # 3. 显示最新提交
    try {
        $last = git log --oneline -5 2>$null
        if ($last) {
            Write-Host "[$now] 最新5条提交:" -ForegroundColor DarkCyan
            $last | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
        }
    } catch {}

    # 4. 自动推送
    if ($AutoPush) {
        $dirty = git status --porcelain -uall 2>$null
        if ($dirty) {
            Write-Host "[$now] -> 本地有修改，尝试自动推送..." -ForegroundColor Yellow
            $pushScript = Join-Path $repo 'push.ps1'
            if (Test-Path $pushScript) {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                try {
                    $out = & $pushScript -NoPrompt "local: auto $stamp" 2>&1 | Out-String
                    if ($out) { $out -split "`r?`n" | Select-Object -Last 10 | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray } }
                } catch { Write-Host "  推送异常: $($_.Exception.Message)" -ForegroundColor Red }
            }
        }
    }

    # 5. 检查 handshake 是否需要本地验证
    try {
        $hsPath = Join-Path $repo 'results/status/handshake.json'
        if (Test-Path $hsPath) {
            $hs = Get-Content $hsPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction SilentlyContinue
            if ($hs -and $hs.arena_state -eq 'awaiting_check' -and $hs.local_state -eq 'pending') {
                Write-Host "[$now] !!! Agent请求本地检查 round $($hs.round) !!!" -ForegroundColor Red -BackgroundColor Yellow
                Write-Host "  正在执行本地检查..." -ForegroundColor Yellow
                $checkScript = Join-Path $repo 'code/local_check.ps1'
                if (Test-Path $checkScript) {
                    try { & $checkScript 2>&1 | ForEach-Object { Write-Host "  $_" } } catch {}
                }
            }
        }
    } catch {}

    # 6. 显示心跳和下次时间
    $next = (Get-Date).AddMinutes($Interval).ToString('HH:mm:ss')
    Write-Host "[$now] 本轮完成，下次拉取: $next (Ctrl+C 停止)" -ForegroundColor DarkGray
    Write-Host ""

    # 7. 等待
    Start-Sleep -Seconds ($Interval * 60)
}
