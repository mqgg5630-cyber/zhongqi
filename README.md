# zhongqi —— 中期报告协作仓库

和 Arena 编码会话同步用的仓库。当前任务：**依据《开题报告》撰写《中期报告》**，后续还会加入中期答辩 PPT。

> **工作分支（唯一需要关注的分支）：`arena/01a09d79-zhongqi`**
> 仓库地址：<https://github.com/mqgg5630-cyber/zhongqi>（公开仓库，克隆/拉取不需要登录）

## 目录说明

```
zhongqi\
├── README.md               本说明
├── sync.ps1                一键拉取：把 Arena 分支上的最新内容同步到本地
├── push.ps1                一键推送：把你本地新增的文件提交并推到 Arena 分支
├── docs\
│   ├── 开题要点.md          《开题报告》要点提炼（等 sources\开题.docx）
│   ├── 中期报告.md          中期报告正文（框架已搭好，【待填】处待补内容）
│   └── 中期答辩PPT大纲.md   答辩 PPT 逐页大纲 + 预判问题
├── sources\                放原件：开题.docx、中期.docx、答辩.pptx（可选，便于我直接解析）
├── results\                你做出的结果：数据表、图、截图；插图统一放 results\figures\
└── code\                   实验/数据处理/画图脚本
```

---

## 一、第一次：克隆到本地（不要用 git init）

你的本地是 `E:\0zhongqi`，里面有 `附件\` 文件夹，所以**不要**克隆到 `E:\0zhongqi` 根目录（非空会报错），克隆到子目录：

```powershell
cd E:\0zhongqi
git clone -b arena/01a09d79-zhongqi https://github.com/mqgg5630-cyber/zhongqi.git zhongqi
```

> ⚠️ 不要 `git init` 一个新仓库再往这个分支推：历史对不上，push 会被拒绝；一旦用 `--force` 强推，远端已有的内容会被整支覆盖。克隆下来的仓库本身就是这个分支，直接 pull/push 即可。

克隆后的本地结构：

```
E:\0zhongqi\
├── 附件\           （原样不动：中期.docx、开题.docx）
└── zhongqi\        （克隆下来的仓库）
```

## 二、每次拿我的最新内容：同步

```powershell
cd E:\0zhongqi\zhongqi
.\sync.ps1
```

（脚本会 fetch → 切到工作分支 → `pull --ff-only`；本地若有未提交改动，会先自动 `git stash` 防止冲突。
若提示"禁止运行脚本"，先执行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`。）

不想用脚本就手打：

```powershell
git fetch origin
git checkout arena/01a09d79-zhongqi
git pull --ff-only origin arena/01a09d79-zhongqi
```

## 三、把本地内容（docx / PPT / 结果）传给我：推送

**推荐**：把文件复制进仓库对应目录，再跑一次脚本：

```powershell
cd E:\0zhongqi\zhongqi
copy ..\附件\开题.docx .\sources\
copy ..\附件\中期.docx .\sources\
.\push.ps1 "加入开题、中期文档"
```

`push.ps1` 会先 `pull --ff-only` 再 `git add -A`（自动跳过无变化的情况），最后 push 到 `arena/01a09d79-zhongqi`。
首次运行若 git 没配身份，它会自动为本仓库补上默认身份。

对应关系：

| 你本地的东西 | 放进仓库的位置 |
|---|---|
| 开题.docx / 中期.docx / 答辩.pptx 原件 | `sources\` |
| 实验数据、结果表、图 | `results\`，插图进 `results\figures\` |
| Python / Spyder 脚本 | `code\` |

## 四、约定

1. 所有改动我都会提交并推到 `arena/01a09d79-zhongqi`，你重复第二步即可拿到。
2. 尽量避免我们同时改同一个文件：你先 `.\push.ps1` 推上来，我改完你 `.\sync.ps1` 拉下去。
3. `~$*.docx` 临时文件、`__pycache__`、`.venv` 等已在 `.gitignore` 忽略；`.docx/.pptx` 在 `.gitattributes` 里按二进制处理。
4. docx 是二进制文件，git 看不到内容差异——所以我每次都会把提炼后的内容落成 `docs\` 里的 Markdown，正文修改都在 Markdown 上做，需要 Word 版时我再用脚本导出。
