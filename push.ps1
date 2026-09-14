# push.ps1 —— 把你本地新增/修改的文件提交并推送到 Arena 工作分支
# 用法（在仓库目录下）：
#     .\push.ps1                     # 自动生成提交信息
#     .\push.ps1 "增加中期答辩PPT"    # 自定义提交信息
# 如果提示“禁止运行脚本”，先执行一次：
#     Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

param(
    [string]$Message = ''
)

$ErrorActionPreference = 'Stop'
$Branch = 'arena/01a09d79-zhongqi'

Set-Location -Path $PSScriptRoot
Write-Host "== 仓库目录: $PWD" -ForegroundColor Cyan

# 首次使用时 git 若未配置身份，commit 会失败，这里自动补上（只写本仓库的配置）
if (-not (git config user.name)) {
    git config user.name  'mqgg5630-cyber'
    git config user.email 'mqgg5630-cyber@users.noreply.github.com'
    Write-Host "== 已为本仓库设置默认 git 身份，可用 git config user.name/user.email 修改" -ForegroundColor Yellow
}

# 先拉最新，避免和 Arena 的提交分叉
git fetch origin
git checkout $Branch
git pull --ff-only origin $Branch

git add -A
if (-not (git status --porcelain)) {
    Write-Host "`n== 本地没有新变化，无需提交。" -ForegroundColor Green
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Message)) {
    $Message = "sync: 本地更新 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

Write-Host "`n== 以下文件将被提交：" -ForegroundColor Cyan
git status --short

git commit -m $Message
git push origin $Branch

Write-Host "`n== 已推送到 $Branch：" -ForegroundColor Green
git log -1 --oneline --decorate
