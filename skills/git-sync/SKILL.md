---
name: git-local-sync
description: Windows PowerShell 一键同步工作流：从远端拉取最新代码（自动 stash 本地改动）与把本地文件提交推送回去。Use when a user on Windows needs repeatable "pull latest" / "upload my files + push" helpers for a repo, especially when they must avoid Chinese text in .ps1 files (Windows PowerShell 5.1 GBK decoding) or when git asks for credentials on first push.
---

# 本地同步脚本（sync / push / upload）

## 适用场景

- 用户不熟悉 git 命令，只想**双击一个脚本**就同步；
- 助手在远端提交代码，用户在自己电脑（Windows + PowerShell）拉取；
- 用户手上有文件（Word/PPT/Excel/数据）需要一键归位到仓库并推送；
- **关键陷阱**：Windows PowerShell 5.1 在没有 BOM 时按 **ANSI/GBK** 解码 `.ps1`，
  脚本里的中文注释会被解成乱码，可能吃掉引号导致 `字符串缺少终止符` / `InvalidArgument`。
  → 本 skill 的三个脚本**全 ASCII**，中文只出现在控制台输出所用的英文提示里。

## 三个脚本

| 脚本 | 作用 | 典型用法 |
|---|---|---|
| `sync.ps1` | 拉取：`git fetch` → 切分支 → `pull --ff-only`；**本地有改动先自动 stash**，避免 pull 失败 | `.\sync.ps1` |
| `push.ps1` | 推送：`fetch` + `pull --ff-only` → `git add -A` → `commit` → `push`；缺 git 身份时自动设一个本地身份 | `.\push.ps1 "add midterm files"` |
| `upload.ps1` | 上传：自动找到仓库旁边含有 docx/pptx/pdf 的目录，按扩展名归位（文档→`sources\`，脚本→`code\`，表格→`results\`），然后调用 `push.ps1` | `.\upload.ps1` |

两者的关系：`upload.ps1` 末尾调用 `push.ps1`，所以只需要记住 `.\sync.ps1`（取）和 `.\upload.ps1`（传）。

## 分支名

脚本里用 `param([string]$Branch = ...)` 指定分支，也可以只写 `$Branch = (git rev-parse --abbrev-ref HEAD)`：
**默认跟随当前分支**，这样脚本可以原样复制到任何仓库使用。

## 首次使用（Windows）

```powershell
# 允许执行本地脚本（只做一次）
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 首次 push 会弹 GitHub 登录窗；若提示输密码，那里必须填 token（或改用 gh auth login / GitHub Desktop）
```

## 与 AI 助手协作的约定（推荐写进仓库 README）

1. 助手每轮都 `commit + push` 到自己承诺的分支；
2. 用户侧只需 `.\sync.ps1` 拉取，`.\upload.ps1` 上传；
3. **不要**让用户在本地 `git init` 新仓库再推同一分支：历史不一致会被拒；
   强推（`--force`）会覆盖远端内容；
4. 助手在 `push` 前先 `git fetch` + `pull --ff-only`，避免非快进被拒。

## 常见报错

| 报错 | 原因 / 处理 |
|---|---|
| `字符串缺少终止符` / `InvalidArgument` | `.ps1` 里有中文（GBK 解码）→ 把脚本改成纯 ASCII，用 `check_ps1.py` 校验 |
| `cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `Updates were rejected because the remote contains work...` | 远端有新提交 → 先 `.\sync.ps1`，再推送 |
| 提示要密码 | GitHub 已不接受密码：用 token，或 `gh auth login` / GitHub Desktop |
| `fatal: not a git repository` | 脚本不在克隆目录里运行：`cd` 到仓库目录再执行 |
