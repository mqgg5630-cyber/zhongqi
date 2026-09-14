# sync.ps1 —— 一键把 Arena 工作分支的最新代码同步到本地
# 用法（在仓库目录下）：
#     .\sync.ps1
# 如果提示“禁止运行脚本”，先执行一次：
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

param(
    [string]$Branch = 'arena/01a09d79-zhongqi'
)

$ErrorActionPreference = 'Stop'

# 切到脚本所在目录（也就是仓库根目录）
Set-Location -Path $PSScriptRoot

Write-Host "== 仓库目录: $PWD" -ForegroundColor Cyan
Write-Host "== 目标分支: $Branch`n" -ForegroundColor Cyan

# 本地有未提交改动时提醒，避免 pull 失败
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "!! 本地有未提交的改动，已自动暂存（git stash）：" -ForegroundColor Yellow
    git stash push -u -m "auto-stash before sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $stashed = $true
}

git fetch origin

# 切到工作分支（已在该分支时是空操作）
git checkout $Branch

# 只允许快进合并，避免在本地产生多余的合并提交
git pull --ff-only origin $Branch

Write-Host "`n== 同步完成，当前最新提交：" -ForegroundColor Green
git log -1 --oneline --decorate
if ($stashed) {
    Write-Host "`n提示：刚才自动 stash 的本地改动仍在 stash 里，用 git stash list / git stash pop 取回。" -ForegroundColor Yellow
}
