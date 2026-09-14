---
name: git-local-arena-sync
description: 本机（Windows PowerShell）与远端 Agent 之间的双向文件同步技能：拉取、上传、下载交付物、打包提交、体检排障，以及助手侧的"提交+推送"与沙箱 .git 被重置后的历史恢复。Use when a user needs repeatable pull / upload / download / pack helpers for a repo shared with an AI agent, when .ps1 files must stay ASCII-only (Windows PowerShell 5.1 GBK decoding), when a stray push to main must be blocked, or when the sandbox repository silently resets to its baseline commit and the worktree must be kept.
---

# 本地 ↔ Agent 双向同步（skill）

一个仓库、两条链路：**你在本机按一个命令，Agent 在远端按一个命令**，中间只有 git。
所有脚本都是幂等的、可以直接复制到别的项目复用。

## 0. 一句话流程

```
本机                                    远端（Agent 沙箱 / Arena）
  .\sync.ps1          <---- push ----   agent-sync.sh "feat: ..."   （提交+推送，带守卫与自检）
  .\upload.ps1        ---- pull ---->   （附件按扩展名归位 -> sources/ code/ results/）
  .\download.ps1      <---- pull ----   （把 deliverable/ 等目录镜像到本机）
  .\pack.ps1          （打成 zip 交付，本地生成，不进 git）
```

## 1. 脚本清单

| 脚本 | 方向 | 作用 | 典型用法 |
|---|---|---|---|
| `scripts/sync.ps1` | 取 | fetch + 切分支 + `pull --ff-only`；本地有改动先自动 stash | `.\sync.ps1` |
| `scripts/upload.ps1` | 传 | 附件按 `upload_map` 归位到 `sources/ code/ results/`，再调用 `push.ps1` | `.\upload.ps1 -Src "E:\0zhongqi\附件"` |
| `scripts/push.ps1` | 传 | `pull --ff-only` → `add -A` → commit → push；**拒绝推 main/master** | `.\push.ps1 "add files"` |
| `scripts/download.ps1` | 下载 | 按 `download_sets` 用 robocopy 把仓库目录镜像到本机 | `.\download.ps1 -Set final` |
| `scripts/pack.ps1` | 打包 | 把某个集合压成一个 zip（默认 `_export\<日期>_<集合>.zip`） | `.\pack.ps1 -Set final` |
| `scripts/doctor.ps1` | 排障 | 环境/分支/远端/落后领先/未提交/stash/最近提交 一次体检 | `.\doctor.ps1` |
| `scripts/bootstrap.ps1` | 初始化 | 执行策略、git 身份、fetch、切分支、首次拉取 | `.\bootstrap.ps1` |
| `scripts/install.ps1` | 复用 | 把整套脚本 + 配置装到另一个仓库 | `.\install.ps1 -Target C:\MyProject` |
| `scripts/agent-sync.sh` | 传（远端） | 分支守卫 → fetch → 发散自愈 → 跑 gate → commit + push | `bash skills/git-sync/scripts/agent-sync.sh "feat: ..."` |
| `scripts/agent-recover.sh` | 修复（远端） | 沙箱 `.git` 被重置回基线提交后，保住工作区恢复历史 | `bash skills/git-sync/scripts/agent-recover.sh` |

## 2. 配置：`sync.config.json`

脚本里**不写中文、不写死分支**；分支名、远端、要下载的目录、扩展名归位规则都在这个 UTF-8 JSON 里：

```json
{
  "branch": "arena/01a09d79-zhongqi",
  "remote": "origin",
  "download_dir": "",
  "download_sets": { "final": ["deliverable", "中间版"], "preview": ["results/ppt_preview"] },
  "upload_map":    { ".docx": "sources", ".py": "code", ".xlsx": "results" },
  "gate": "bash code/check_all.sh"
}
```

* `download_dir` 留空 → 下载到仓库上一级的 `<仓库名>_out`；
* `download_sets` 里的目录名可以是中文（JSON 不是 `.ps1`，不受 GBK 影响）；
* `gate` 是助手侧 `agent-sync.sh` 提交前运行的检查命令，失败就**不提交**。

## 3. 铁律（踩过的坑）

1. **`.ps1` 只用 ASCII**。Windows PowerShell 5.1 读无 BOM 的 `.ps1` 时按 GBK 解码，中文注释会把引号吃掉，报 `字符串缺少终止符` / `InvalidArgument`。中文放在 `.md` 与 `.json` 里。提交前跑 `python code/check_ps1.py`（本仓库会自动扫全部 `.ps1`）。
2. **只在自己的工作分支上动**。脚本默认从配置读分支；`push.ps1` 直接拒绝 `main`/`master`；`agent-sync.sh` 发现 HEAD 不是配置里的分支就退出。
3. **不要 `git init` 再推同一分支**（历史不一致会被拒），也不要在冲突时 `--force`。
4. **推送前先 `pull --ff-only`**（两个脚本都内建），避免 non-fast-forward。
5. **大文件不进 git**。镜像、数据集放 `build/` 之类被 ignore 的目录，或本地用 `pack.ps1` 打包外发；需要跟踪的大文件改用 Git LFS。

## 4. 故障对照表

| 现象 | 处理 |
|---|---|
| `cannot be loaded because running scripts is disabled` | `.\bootstrap.ps1`（内部设 CurrentUser RemoteSigned），或 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 提示输入密码 | GitHub 不接受密码 → 用 token / `gh auth login` / GitHub Desktop |
| `rejected - non-fast-forward` | 先 `.\sync.ps1` 再推；助手侧 `agent-sync.sh` 会自动对齐远端 |
| `pull --ff-only` 失败 | 本机有分叉提交：`.\doctor.ps1` 看清状态，必要时 `git stash` 或 `git reset --hard origin/<分支>` |
| 你的改动进了 stash | `git stash list` → `git stash pop` |
| robocopy 报 8 以上错误码 | 目标目录被占用/权限不足；`download.ps1` 只在 ≥8 时报失败，0—7 都是正常 |
| **助手侧**：`git log` 只剩 `Initial commit`，`git status` 全是新文件 | `.git` 被静默重置：`bash skills/git-sync/scripts/agent-recover.sh`（工作区不动，只把 HEAD 挪回分支），然后 `agent-sync.sh` 提交 |
| 助手侧 fetch 拉不到远端分支 | 先补全 refspec：`git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"` |

## 5. 首次使用

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned      # 只做一次
.\bootstrap.ps1                                          # 身份 / 分支 / 首拉
.\doctor.ps1                                             # 确认状态
```

## 6. 与 Agent 协作的约定

1. Agent 每轮 `agent-sync.sh` 提交推送，**只推约定分支**；
2. 你这边只记两条：`.\sync.ps1`（取）和 `.\upload.ps1`（传）；
3. 交付物要落地用 `.\download.ps1 -Set final`；要交给老师用 `.\pack.ps1`；
4. 任何"不对劲"先 `.\doctor.ps1`，把输出贴给 Agent。
