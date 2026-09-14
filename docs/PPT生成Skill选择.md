# 两个高 star 的 PPT 生成 Skill 推荐（可编辑 PPTX）

> 结论先行：**两个都推荐，但用途不同**——
> `hugohe3/ppt-master` 是**在 AI IDE 里跑的工作流 skill**，产出**原生 DrawingML**（真·PPT 对象、可编辑到形状/连接线级别）；
> `presenton/presenton` 是**自托管的生成服务（带 API + 内置 MCP）**，网页/桌面端操作，导出**可编辑 PPTX / PDF**。
> 只想把这份中期答辩改得更好看 → 选 **ppt-master**；想以后批量做不同汇报、或想让别的程序调用 → 选 **presenton**。
> 本仓库已同时给出 **三个原生可编辑版本** 与 **机器可读大纲**（见文末"怎么把本仓库的大纲喂给它"），两者都能直接用。

数据抓取时间：**2026-09-14**（star 数取自仓库页面）。

---

## 一、对比一览

| 项目 | ppt-master | presenton |
|---|---|---|
| 仓库 | https://github.com/hugohe3/ppt-master | https://github.com/presenton/presenton |
| Star / Fork | **54.1k** / 4.3k | **10.2k** / 1.6k |
| 许可 | MIT | Apache-2.0 |
| 语言 / 形态 | Python（skill 工作流，跑在 AI 终端里） | TypeScript + Python（Docker / 桌面端 / 自托管服务） |
| 产出可编辑性 | **原生 DrawingML**：真实形状、连接线、图表、表格、OMML 公式、版式母版继承，可继续在 PowerPoint 里改 | 导出 **PPTX / PDF**（HTML+Tailwind 渲染后导出，文字可编辑） |
| 最擅长 | 从文档/主题生成**结构严谨**的学术/汇报 deck；**给已有 .pptx 填内容并保留原设计**（template-fill）；抽模板 | 提示词/PDF/DOCX/Markdown/URL → deck；**自带模板库**、可视化编辑、**API / MCP** 批量出稿 |
| 入口 | 任意有 agent 能力的 AI IDE（Claude Code、Cursor、VS Code Copilot 等）+ 本地 Python | 浏览器 http://localhost:5001 、Electron 桌面端、REST API、MCP |
| 模型 | 自带 key（推荐大上下文模型 + AI 配图） | 自带 key：OpenAI / Gemini / Claude / Azure / Ollama 本地模型… |
| 上手成本 | `git clone` + `pip install -r requirements.txt`，然后在对话里说"用这份大纲做 PPT" | 一条 docker 命令（或装桌面版），网页里点几下 |

两者都不需要 Office 授权，**成本只有模型调用费**；数据都留在本机（除调用模型外）。

---

## 二、ppt-master（54.1k★，MIT，Python）

**它解决什么**：AI 生成的 PPT 常常被"拍成图片"，没法改字、没法改颜色。ppt-master 的核心卖点是
**真·原生对象**——导出后每一个框、每一条箭头、每一张图表都是 PowerPoint 里可编辑的对象，
还带转场、动画，以及"用演讲备注自动生成配音"。对我们这份中期答辩特别有用的一点：
它支持**模板填充模式**（`template-fill-pptx`）——把内容灌进**已有的 .pptx 并保留原设计**。

**安装**（Windows 有专门的图文步骤 `docs/windows-installation.md`）：

```powershell
# 1) 只装 Python 3.10+（安装时勾选 Add to PATH）
# 2) 取项目
git clone https://github.com/hugohe3/ppt-master.git
cd ppt-master
pip install -r requirements.txt
# 3) 用任意 AI IDE 打开这个目录（Claude Code / Cursor / VS Code Copilot 均可）
```

**用法**：直接在对话里说需求，例如

```text
请用 docs/PPT大纲.md 这份大纲，做一个 16 页的学术中期答辩 PPT：
16:9，中文字体微软雅黑，最小字号 15 pt，插图用 results/figures 下同名 PNG，
输出到 exports/，要原生可编辑的 pptx。
```

它会在本机跑完整流程并导出到 `exports/`（原生 `.pptx`，另有 `_svg.pptx` 备用版；需要 Office 2016+）。

**注意事项**：作者明确说明"**harness + model = agent**"，效果上限取决于模型——建议用大上下文模型（作者推荐 Kimi K3 或 Claude），
且**不要指望一次成型**：它省掉的是排版劳动，最后的润色仍是自己的活。

**与本仓库的配合方式（推荐）**：
1. 把 `docs/PPT大纲.md`（人读版）或 `docs/ppt_outline.json`（机器版）连同 `results/figures/` 给模型；
2. 想要和现在完全一致的风格，可用**模板填充模式**，源文件用 `deliverable/` 下的 A—E 任选一版；
3. 生成后仍建议跑一遍 `python code/check_ppt.py <新文件>` 复核"最小字号 ≥15 pt、无越界"。

---

## 三、presenton（10.2k★，Apache-2.0，TypeScript）

**它解决什么**：把"做 PPT"变成一条服务——网页里填提示词或丢文档进去，选模板、选模型，导出可编辑 PPTX；
也可以**先上传一份自己的 .pptx 生成专属模板**（`AI Template Generation`），还能把它当 API / MCP 服务用。

**安装（二选一）**

```powershell
# 方式一：Docker（Windows PowerShell，一条命令起服务）
docker run -it --name presenton -p 5001:80 -v "${PWD}\app_data:/app_data" ghcr.io/presenton/presenton:latest
# 然后浏览器打开 http://localhost:5001

# 方式二：桌面版（免浏览器）
# 到 https://presenton.ai/download 下载 Windows 安装包，或从源码：
cd electron
npm run setup:env
npm run dev
```

**用法要点**
- 生成模式：`standard` / `smart`（`PRESENTATION_GENERATION_MODE=both` 两种都开）；
- 模型：设置里填自己的 key（OpenAI / Gemini / Azure / Anthropic / Ollama 本地模型…），**不收订阅费**；
- 模板：可上传现成 PPTX 让它学版式；也有官方模板库；
- 导出：PPTX + PDF，**PPTX 文字可继续编辑**；
- 自动化：内置 **MCP Server**，可被支持 MCP 的客户端/程序调用（`/api/v1/ppt/...` 系列 REST 接口）。

**与本仓库的配合方式**：把 `docs/PPT大纲.md` 正文粘进提示词（或上传 `docs/中期答辩PPT大纲.md` 作为素材文档），
要求"16 页、16:9、中文字体微软雅黑、每页保留备注、插图按顺序使用我提供的图片"；
想统一风格可以先上传 `deliverable/中期答辩_A_学术蓝.pptx`（或 B—E 任选一版）当作模板来源。

---

## 四、备选（更底层，给会写代码的情况）

| 项目 | Star | 说明 |
|---|---|---|
| [MiniMax-AI/skills](https://github.com/MiniMax-AI/skills)（`pptx-generator`） | — | 基于 **PptxGenJS** 的生成 skill，风格偏"AI 一键出稿"，可编辑 |
| [gitbrent/PptxGenJS](https://github.com/gitbrent/PptxGenJS) | 6.1k | JavaScript 库，直接写代码生成原生 PPTX；我们三版 PPT 就是同一思路的 Python 版（python-pptx） |

> 本仓库的做法（`code/make_ppt_variants.py`）与 ppt-master 的取向一致：**只用 python-pptx 的原生形状与文本框**，
> 不把页面拍成图片，因此三版 PPT 全部可以继续手改（改字、改色、改框位置、换图）。

---

## 五、怎么把本仓库的大纲喂给它

| 文件 | 用途 |
|---|---|
| `docs/ppt_outline.json` | **机器可读**：16 页的标题/正文/卡片/步骤/结论条/演讲备注/配图文件名，可直接给程序或 AI 读 |
| `docs/PPT大纲.md` | **人读版大纲**（由上一个文件自动生成，含配色字号规范与一段现成的提示词模板） |
| `docs/中期答辩PPT大纲.md` | 导师意见落实对照表 + 逐页清单 + 7 个答辩预判问答（给"讲什么"用的） |
| `results/figures/figA_*.png … figG_*.png` | 大纲里点名要用的 7 张示意图，文件名与大纲一一对应 |
| `deliverable/中期答辩_*.pptx`（A—G 七版） | 已经做好的七版可编辑成果；其中 F / G **就是用 ppt-master 的原生导出通路做的**（`code/make_ppt_svg.py`），可作为"本仓库已跑通"的参考实现 |

**一句话提示词**（两个 skill 都能用）：

```text
按 docs/ppt_outline.json 生成 16 页学术中期答辩 PPT：
16:9、中文微软雅黑/Arial、全文最小字号 15 pt、内容不得增删要点、不得加入大纲之外的数字、
每页写入大纲里的 note 作为演讲备注、按 figure 字段插入 results/figures 下同名图片、
输出原生可编辑 pptx。
```

> 提醒：无论用哪个 skill，**出稿后都建议跑一次 `python code/check_ppt.py <文件>`**，
> 它会用真实中文字体估算换行高度，帮我们确认"最小字号 ≥15 pt、形状不越界、文字不压图"这三条硬要求。
