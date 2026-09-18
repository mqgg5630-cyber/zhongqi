# 本地 ↔ Agent 同步 skill —— 使用说明与扩展清单

> 目标是：**取、传、下载、打包、排障各一个命令**，不需要 git 知识；
> 一份配置（`sync.config.json`）驱动全部脚本，换个仓库直接复用。
> 本仓库根目录已经放好同款脚本（`sync.ps1 / push.ps1 / upload.ps1 / download.ps1 / doctor.ps1 / pack.ps1 / bootstrap.ps1`），
> 这份 skill 是**通用版 + 说明书**。

## 〇、最快上手（三步）

1. 进文件夹：`E:\0zhongqi\zhongqi`（仓库根目录，**不是** `E:\0zhongqi`）
2. 双击 **`sync.cmd`** —— 就是一键拉取最新（等价于 `.\sync.ps1`）
3. 双击 **`download.cmd`** —— 把交付物复制到本机（等价于 `.\download.ps1 -Set final`）

`.cmd` 是 `.ps1` 的双击外壳（自动 `-ExecutionPolicy Bypass`），参数照样能传：
`download.cmd -Set all`。一页纸速查见 `docs/本地同步怎么用.md`。

**如果当前文件夹已经被别的分支占了**：双击 **`reclone.cmd`**，它会在上一层另建一个干净文件夹
（默认 `<repo>-arena`）并直接检出工作分支，**绝不改动你运行它的那个文件夹**；
目标文件夹若已是克隆，则只做 fetch + 切分支 + 快进。命令行等价写法：

```powershell
git clone -b <branch> --single-branch <url> ..\<repo>-arena
```

（远端有多个 `arena/*` 分支时，一定要写对**本会话的**分支名；`reclone.ps1` 会自己从
`sync.config.json` 读，不用手打。）
旧克隆里如果还没有这些文件，先做一次裸 git：`git fetch origin` → `git checkout arena/01a09d79-zhongqi` → `git pull`。

## 一、最短用法（在仓库目录里）

```powershell
.\sync.cmd                     # 同 .\sync.ps1，双击可用
.\sync.ps1                     # 取：拉最新（本地有改动会自动 stash）
.\upload.ps1                   # 传：附件归位到 sources\ code\ results\ 后 commit + push
.\download.ps1 -Set final      # 下载：把 deliverable\ 等目录镜像到本机
.\download.ps1 -List           # 看有哪些集合（final / docs / source / preview / all）
.\pack.ps1 -Set final          # 打包：生成 _export\20260914_1830_final.zip
.\doctor.ps1                   # 排障：环境 / 分支 / 远端 / 未提交 / stash 一次看清
```

助手那一侧是两个脚本（本仓库的 `skills/git-sync/scripts/`）：

```bash
bash skills/git-sync/scripts/agent-sync.sh "feat: 新增中间版 2"   # 守卫 + fetch + 自检 + commit + push
bash skills/git-sync/scripts/agent-sync.sh --status              # 只看状态，不动文件
bash skills/git-sync/scripts/agent-recover.sh                    # 沙箱 .git 被重置后的恢复
```

## 二、脚本与配置

| 文件 | 说明 |
|---|---|
| `sync.config.json` | **唯一的配置**：`branch` / `remote` / `download_dir` / `download_sets` / `upload_map` / `gate` |
| `scripts/sync.ps1` | 拉取；`push.ps1` 一样的配置来源（先找仓库内 `skills\git-sync\sync.config.json`，再找脚本旁边） |
| `scripts/push.ps1` | 提交推送；**拒绝推 `main` / `master`** |
| `scripts/upload.ps1` | 附件归位：扩展名 → 目录映射取自 `upload_map`，也可 `-Ext`/`-Dest` 临时指定 |
| `scripts/download.ps1` | robocopy 镜像下载；`-Set` 选集合，`-Mirror` 变为完全镜像（删多余文件） |
| `scripts/pack.ps1` | 压缩包交付；输出到 `_export\`（已在 `.gitignore` 里，不会被推送） |
| `scripts/doctor.ps1` | 体检报告；"哪里不对劲"先跑它 |
| `scripts/bootstrap.ps1` | 首次准备：执行策略、git 身份、fetch、切分支、首拉 |
| `scripts/reclone.ps1` | 另拉一个干净文件夹：`.\reclone.ps1 -Path E:\0zhongqi\zhongqi-arena`（不碰当前文件夹；目标已是克隆则快进） |
| `scripts/install.ps1` | 把整套脚本装到另一个仓库：`.\install.ps1 -Target C:\MyProject -Branch main`（含 `.cmd` 双击外壳） |
| `scripts/*.cmd` | 五个双击外壳：`sync.cmd` / `download.cmd` / `doctor.cmd` / `bootstrap.cmd` / `reclone.cmd`（ASCII + CRLF，`check_ps1.py` 一并检查） |
| `scripts/agent-sync.sh` | 助手侧一键：分支守卫 → fetch → 发散自愈 → gate → commit + push |
| `scripts/agent-recover.sh` | 助手侧修复：`.git` 被重置回基线提交时，保住工作区把 HEAD 挪回分支 |

下载集合（可以在配置里任意增删，目录名支持中文）：

| 集合 | 目录 |
|---|---|
| `final` | `deliverable`、`中间版`、`中间版2` |
| `docs` | `deliverable` |
| `source` | `sources`、`docs` |
| `preview` | `results/ppt_preview`、`results/figures` |
| `all` | 上面全部 + `code`、`skills` |

## 三、为什么 `.ps1` 里绝对不能写中文

Windows PowerShell 5.1 读**没有 BOM** 的 `.ps1` 时按 **ANSI/GBK** 解码；UTF-8 的中文注释会变成乱码，
乱码里一旦出现引号就会把后面的字符串吞掉，报 `字符串缺少终止符` / `InvalidArgument`。
约定：**`.ps1` 只用 ASCII，中文只出现在 `.md` / `.json`**；
本仓库提交前跑 `python code/check_ps1.py`（扫描全部 `.ps1`，含 `skills\` 下的），非 ASCII 直接 FAIL。

中文目录名（如 `中间版`）因此**只写在 `sync.config.json` 里**，脚本用 `Get-Content -Encoding UTF8` 读取，
再拼路径——这样既有中文目录，又不会有 GBK 问题。

## 四、两道安全阀

1. **分支守卫**
   * `push.ps1`：分支是 `main` / `master` 直接拒绝执行；
   * `agent-sync.sh`：HEAD 与配置里的分支不一致就退出（不会误推到别处），并且只 `git push origin <配置分支>`。
2. **提交前自检（gate）**
   `sync.config.json` 的 `gate`（本仓库是 `bash code/check_all.sh`：docx 格式 + PPT 版式 + 口径核对）
   失败时 `agent-sync.sh` **不提交**，因此远端历史里的每个提交都是自检通过的。

## 五、故障对照表

| 现象 | 处理 |
|---|---|
| `running scripts is disabled` | 跑一次 `.\bootstrap.ps1` |
| 要密码 / 认证失败 | GitHub 不接受密码：token、`gh auth login` 或 GitHub Desktop |
| `Updates were rejected`（远端有新提交） | 先 `.\sync.ps1`，再 `.push.ps1` |
| `pull --ff-only` 失败（本地有分叉提交） | `.\doctor.ps1` 看状态；`git stash` 或 `git reset --hard origin/<分支>` |
| 本地改动"消失"了 | 多半在 stash：`git stash list` → `git stash pop` |
| 下载后文件是旧的 | 先 `.\sync.ps1` 再 `.\download.ps1`（下载只复制工作区文件） |
| robocopy 返回 1—7 | 正常（有文件被复制 / 无变化 / 有额外文件），只有 ≥8 才算失败 |
| **助手侧**工作区正常但历史回到基线提交 | `bash skills/git-sync/scripts/agent-recover.sh` → `agent-sync.sh` |
| 文件夹被别的分支占了 / 切不回来 | 双击 `reclone.cmd` 另拉一个干净文件夹，旧文件夹不动 |

## 六、装到别的项目

```powershell
.\skills\git-sync\scripts\install.ps1 -Target C:\MyProject -Branch arena/xxx
cd C:\MyProject
.\bootstrap.ps1
```

装完只需要 **编辑 `sync.config.json`**：换分支、换下载集合、换扩展名归位规则，都不需要动脚本。

## 七、扩展清单（还想加的 / 已经留好接口的）

已实现（本次）：

- [x] 取 / 传 / 下载 / 打包 / 体检 / 首次准备 / 复用安装 七个脚本
- [x] 配置化：分支、远端、下载集合、扩展名归位、gate 命令
- [x] 分支守卫 + 提交前自检
- [x] 助手侧 `agent-sync.sh`（含发散自愈）与 `agent-recover.sh`（沙箱 `.git` 重置恢复）

留好接口、按需再扩：

- [ ] **`doctor.ps1 -Fix`**：自动 stash 多余改动、切回配置分支、重建 refspec
- [ ] **`gh` 流程**：`pr.ps1` / `agent-pr.sh`（`gh pr create`、`gh pr checks` 看 CI）
- [ ] **GitHub Actions**：push 后自动跑 `code/check_all.sh`，把结果贴到 commit 状态
- [ ] **Git LFS**：大文件（测序数据、模型权重）走 LFS，脚本里加 `lfs install/status` 检查
- [ ] **增量清单**：`download.ps1 -Since <日期>` 只取最近变更的文件（配 `git log --name-only`）
- [ ] **多环境 profile**：`sync.config.<profile>.json`（实验室电脑 / 笔记本各自一套下载目录）
- [ ] **同步报告**：`agent-sync.sh` 把本轮的 `git diff --stat` 写进 `results/`，方便你在本机一眼看到改了什么
- [ ] **附件回执**：`upload.ps1` 结束后打印"新文件是否已被 Agent 拉到"（对比远端最新提交时间）
