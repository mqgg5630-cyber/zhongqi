# zhongqi —— 中期报告协作仓库

目标：依据《开题报告》和你这段时间的实际进展，**直接填好《中期.docx》，完整保留学校模板的原有格式**；后续再补中期答辩 PPT。
所有改动我都会提交并推送到分支 **`arena/01a09d79-zhongqi`**。

仓库地址：<https://github.com/mqgg5630-cyber/zhongqi>（公开仓库，拉取不需要登录）

---

## 现在只需要两步

**① 拿我更新（你在 `E:\0zhongqi\zhongqi` 目录下）：**

```powershell
.\sync.ps1
```

**② 把你本地的文件传给我（一条命令）：**

```powershell
.\upload.ps1
```

`upload.ps1` 会自动在你仓库旁边的文件夹里找到 `附件`（按扩展名搜索，不写死中文文件名），按类型归位后提交推送：

| 你的文件 | 传到哪里 |
|---|---|
| `开题.docx` `中期.docx` `已完成1.docx` `1.md` | `sources\` |
| `1.py` | `code\` |
| `.xlsx` `.xls` `.csv` 结果表 | `results\` |

> 第一次 push 会弹出 GitHub 登录窗口（你自己的账号 mqgg5630-cyber），登录一次以后就不再问了。
> 如果 push 时让你输**密码**：那里要填的是 token 而不是账号密码 —— 这种情况直接改用 GitHub Desktop 打开 `E:\0zhongqi\zhongqi` 点 Push，或跟我说，我改用别的方式收文件。
> 不想动 git 的话，把 5 个文件在 Arena 里直接作为附件发给我也一样，我这边立刻开始写。

---

## 一、第一次：克隆（已完成，仅供重建时参考）

> ⚠️ 不要 `git init` 一个新仓库再往这个分支推：历史对不上会被拒；强推（`--force`）会把远端已有内容整支覆盖。
> 克隆下来的仓库本身就是这个分支，直接 pull / push 即可。

```powershell
cd E:\0zhongqi
git clone -b arena/01a09d79-zhongqi https://github.com/mqgg5630-cyber/zhongqi.git zhongqi
```

本地结构：

```
E:\0zhongqi\
├── 附件\           （原样不动）
└── zhongqi\        （克隆下来的仓库）
```

## 二、如果脚本报错

| 报错 | 处理 |
|---|---|
| `无法加载文件…因为在此系统上禁止运行脚本` | 执行一次 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`，或改用等价命令（见下） |
| `InvalidArgument` / `找不到接受实际参数"push"的位置形式参数` | 说明你拿到的是**旧版脚本**（脚本里的中文被 PowerShell 5.1 按 GBK 解码，把引号吃掉了）。我已经把脚本改成纯英文输出，`.\sync.ps1` 拉到新版即可 |
| `git push` 被拒（rejected） | 先 `.\sync.ps1` 再 push：说明远端有新提交 |

不用脚本时的等价命令：

```powershell
# 拉取
git fetch origin; git checkout arena/01a09d79-zhongqi; git pull --ff-only origin arena/01a09d79-zhongqi

# 推送
git add -A; git commit -m "加入本地文件"; git push origin arena/01a09d79-zhongqi
```

## 三、目录说明

```
zhongqi\
├── sync.ps1                  ① 拉取我的最新内容
├── upload.ps1                ② 自动找到你的附件文件夹 → 归位 → 提交推送
├── push.ps1                  upload.ps1 调用的推送脚本（也可单独用）
├── sources\                  你的原件：开题.docx / 中期.docx / 已完成1.docx / 1.md
├── code\                     1.py 及后续脚本，另有：
│   ├── inspect_docx.py       解析 docx：段落/表格/字体/字号/占位符 → txt + json
│   └── fill_docx.py          按 ops.json 把内容**就地写进** docx，格式零改动
├── results\                  你做出的结果：数据表、图、截图（插图放 results\figures\）
├── deliverable\              我交付的成品：填好的 中期.docx（与模板同格式）+ 导出 PDF
└── docs\                     写作辅助资料（开题要点、PPT 大纲、模板结构记录）
```

## 四、我这份报告要怎么"填"，格式为什么不会变

1. 你把 `中期.docx` 传上来后，我用 `code/inspect_docx.py` 读出它的完整结构：每一段的样式、字体（含中文 eastAsia 字体）、字号、缩进、居中对齐，每个表格的行列与单元格内容，还有模板里 `＿＿＿＿`、`（  ）` 这类空位。
2. 内容写进 `ops.json`：**只做"改字"和"加段"两种动作**——改字是往段落原有的第一个 run 里写（继承该 run 的字体字号），加段是**深拷贝**一个已有段落再把文字换掉（继承缩进、行距、编号）。表格单元格同理。
3. 用 `code/fill_docx.py` 生成 `deliverable\中期.docx`，再重新解析一遍做校验（字号/字体/表格行列数与模板一致），然后推给你。

这样处理的原始模板 XML（页面设置、页眉页脚、表格框线、样式表）**一个字节都不动**，所以格式和学校模板完全一致。

## 五、约定

1. 改动我都提交推送到 `arena/01a09d79-zhongqi`，你 `.\sync.ps1` 即可拿到。
2. 尽量别和我同时改同一个文件：你 `.\upload.ps1` 推上来 → 我改完 → 你 `.\sync.ps1` 拉下去。
3. `~$*.docx` 临时文件、`__pycache__`、`.venv` 等已在 `.gitignore` 忽略；`docx/pptx/xlsx/pdf` 在 `.gitattributes` 里按二进制处理。
4. docx 是二进制，git 看不到内容差异，所以内容层面的讨论我都落在 `docs\` 的 Markdown 上，最终成品再回流到 docx。
