# 从文件到可追溯理解：资源地图 + 工作流（真实用户视角 · Round 2 R2）

> 真实研究者读文件不是“选一个 PDF 库把全文倒出来”，而是：
> **先判文件与任务 → 看结构地图 → 只抽需要的内容并保留定位 → 核抽取覆盖/质量 →
> 形成可追溯理解笔记并交给下游**。
>
> 本文件与既有资料**互补、不重叠**：
>
> - [`tools.md`](tools.md) / `PDF-REF.md` / `DOCX-REF.md` 等回答“某个工具的 API/命令怎么用”；
> - 本文件回答“**一个真实用户先去哪、何时升级解析器、怎样把资源接成闭环**”；
> - [`docs/competitors/file-reading.md`](../../../docs/competitors/file-reading.md) 是 R1 对标判据 SSOT，
>   本文件不重复竞品拆表。
>
> **硬约束**：Light 完成任务不依赖注册、付费 key、MCP 或云上传；受限资源只列备选。
> 未发表论文、审稿材料、含隐私/密钥的文件默认留在本机；任何云上传先 ASK。

---

## §A 真实用户工作流（5 步闭环）

### Step 1 · 先判“这是什么文件、为什么读、能不能离开本机”

先记四件事：

1. **任务意图**：只要摘要、查某个数字、抽全部表、读论文论证链、读模板硬约束，还是跨文件比较？
2. **输入形态**：格式、页数/行列/文件数、是否加密/损坏、是否含修订、是否 unpublished/敏感。
3. **PDF 类型**：born-digital / mixed / scanned / sparse-or-unknown。
4. **完成证据**：最终要给页码/表号/图号/sheet-cell，还是只给高层摘要？

PDF 先跑：

```powershell
$env:PYTHONUTF8 = "1"
python scripts/pdf_ops.py triage paper.pdf
```

输出 `light.file_reading.input_profile.v1`：

- `born_digital` → **OCR 关闭**，文本层一次抽取；
- `mixed` → 文本页与疑似扫描页分路，最后按原页号合并；
- `scanned` → OCR/视觉读取，不能把空文本当“文档无内容”；
- `sparse_or_unknown` → 先渲染 1–3 个样页看，未知就写 unknown。

> `triage` 是几何启发式 advisory，不是 findings 门；封面大图、海报页、矢量字形可能误分。

### Step 2 · 先建结构地图，再决定读哪些段

**小文件/单点问题**：宿主原生 Read 最省。

**长文件**：解析一次到临时文件，先导航、后局部读；不要每个问题重复解析整份，也不要一次把全文灌进上下文。

| 输入 | 结构地图 | 局部深读 |
|---|---|---|
| born-digital PDF | PDF 目录/书签、`pdftotext -layout`、章节标题；科研论文重路径可用 GROBID TEI | 页号 + 标题/关键词窗口；复杂表图再单页渲染 |
| scanned/mixed PDF | `triage` 的逐页分组 + OCRmyPDF/Tesseract sidecar | 只 OCR 候选页；随机抽样数字/负号/小数点 |
| DOCX | `docx_read.py headings/layout/headers/props` | 目标标题下段落；修订稿用 pandoc `--track-changes=all` |
| PPTX | markitdown 文本 + slide thumbnail/逐页渲染 | 目标 slide，同时看文字与像素版式 |
| XLSX | `xlsx_read.py sheets` + 公式/值双视图 | 目标 sheet/range；定位写 `Sheet!A1:D20` |
| 多文件 | 先按格式/来源/时间建清单；10+ 文件先 metadata-first | 每份一张理解卡，再做跨文件关系 |

科研论文建议先定位：Abstract → Introduction/Related Work → Method → Experiments/Results →
Limitations/Discussion → Conclusion → References；但**用户只问一个数字时不要强行全文精读**。

### Step 3 · 抽“元素 + 论证链”，每条结果带 locator

不要只抽段落。按任务选择：

- **论文**：claim → evidence → boundary；CRGP（Context/Related work/Gap/Proposal）；
  数据集、baseline、指标、主结果、消融、局限。
- **表格**：表题、表头、单位、脚注、合并/跨行表头；PDF 表跑 `verify-tables`。
- **图**：caption、轴/单位、legend、panel、图中关键结论；需要读像素时渲染目标页。
- **引用**：只抽作者/题名/DOI/引用位置；**真假核验交 citation**。
- **模板**：页边距、纸张、字号、行距、章节、匿名、页数与引用风格；交 typesetting。
- **数据表**：shape/dtype/missing/公式/缓存值；深度质量与泄漏交 data-engineering。

定位格式：

```text
p.7 §3.2 / Table 2 row “Ours” / Figure 4b / Appendix C / Sheet Results!F12
```

找不到精确位置就写“locator unknown”，不要给无来源数字；但 `unknown` 不能作为
`reading_contract.py` 的通过证据，交下游前必须补真实 locator 或降级覆盖声明。

### Step 4 · 做覆盖与抽取质量核验，真抓错再修

交付前至少核四项：

1. **覆盖**：总页数多少，读了哪些页/章节，哪些未覆盖；mixed PDF 的 OCR 候选页是否都处理。
2. **文本**：抽取页数与原 PDF 页数对得上；是否出现多栏阅读序错、重复页眉脚、乱码或空页。
3. **表/图**：`verify-tables` 低于 0.6 的表不直接喂下游；表/图关键数字回看原页。
4. **OCR**：抽样核 `0/O`、`1/l`、负号、小数点、上标/下标、中文标点；方向/倾斜先修再重 OCR。

```powershell
python scripts/pdf_ops.py verify-tables paper.pdf --debug-png-dir .upgrade/_e2e/debug
python scripts/reading_contract.py --input reading-contract.json --output reading-contract.report.json
```

`reading_contract.json` 是"能否宣称读懂"的硬门：把每个请求页/通道标成
`IDENTIFIED → EXTRACTED → STRUCTURE_RECOVERED → CROSS_CHECKED → SEMANTICALLY_REVIEWED`。
解析器返回成功通常只证明 EXTRACTED；若双栏顺序未核、跨页表未拼、扫描页无文本、公式丢失、
隐藏 prompt-like 文本未隔离、局部页超时，或 Docling/Tika 等 adapter 的局部失败未下沉为 page/channel issue，
就只能降级为 partial/unknown，不能写"全文已读懂"。source、extract、structure、cross-check、
semantic review 与全局结构图的 locator 也必须是真实定位符；`{{...}}`、`unknown`、`TODO` 等模板值不得通过契约门。

形成理解笔记后，必须把当前源文件、契约输入和保存的 PASS 报告一起交给最终门：

```powershell
python scripts/understanding_note_gate.py --note understanding-note.md --source source.pdf `
  --contract reading-contract.json --contract-report reading-contract.report.json --json
```

笔记元信息要记录三份工件各自的原始字节 SHA-256。最终门会重算 reading contract，并核报告确由当前
契约生成、`document.sha256` 确实等于当前源文件；源文件替换、旧契约或手改 PASS 报告均 fail-closed。

**修复路线**：

- 文本层有但顺序乱 → `pdftotext -layout` / pdfplumber layout / GROBID；
- 无文本层 → OCRmyPDF/Tesseract 或宿主多模态；
- 复杂表/公式 → Docling/MinerU 重路径，仍需抽样核；
- 提取器全部失败 → 标 unavailable/unknown，报告尝试过什么，不脑补。

### Step 5 · 形成理解笔记并交下游，不在 file-reading 越权下判决

用 [`../assets/understanding-note.template.md`](../assets/understanding-note.template.md) 写五面：

1. 结构与逻辑；
2. 关键内容；
3. 格式与要求；
4. 视觉风格；
5. 可复用内容；

再补**输入分级、读取覆盖、locator、未覆盖项、抽取风险**，最后映射下游：

| 读出的东西 | file-reading 做到哪 | 下游负责什么 |
|---|---|---|
| 参考文献/DOI/引用位置 | 抽出并保 locator | **citation** 核真实存在、元数据、嵌合与格式 |
| 跨文件术语/指标/claim | 分别抽出并标来源 | **consistency** 对项目权威源做跨材料漂移门 |
| p 值/效应量/统计结论 | 抽出原值与出处 | **result-analysis / research-ethics** 重算与诚信判断 |
| 表格/数据 | 抽出 + 低置信度 advisory | **data-engineering** 做质量、泄漏与可行性 |
| 图/视觉规范 | 描述 + 原页定位 | **figure / frontend-design** 重绘或实现 |

**边界句**：解析成功 ≠ 引用真实 ≠ claim 一致 ≠ 统计正确；file-reading 不冒领下游门。
`reading_contract.py PASS` 也只说明请求页/通道达到声明状态机，不证明未请求范围或科学判断正确。

---

## §B 资源地图（按成本与数据去向分级）

### B1 · 零 key、本地轻路径（默认主力）

| 资源 | 适合 | access / 依赖 | 怎么接现有闭环 |
|---|---|---|---|
| **宿主原生 Read** | 小 PDF、图片、单页图表、轻摘要 | ✓ 已有能力 | Step 1 判轻任务后直读；仍记录页码/覆盖 |
| **Light `pdf_ops.py`** | PDF 元数据、input triage、layout text、表、合并拆分 | ✓ 本地；pdfplumber/pypdf/pandas | Step 1 分级 → Step 3 抽取 → Step 4 `verify-tables` |
| **Light `docx_read.py`** | 标题、段落、runs、表、页边距、页眉脚、属性 | ✓ 本地；python-docx | 模板/修订前先建结构与格式地图 |
| **Light `xlsx_read.py`** | sheets、公式字符串、缓存值、画像 | ✓ 本地；openpyxl/pandas | 公式/值双视图；不冒充公式已求值 |
| **Poppler (`pdftotext/pdftoppm/pdfimages`)** | 快速保版面抽文、目标页渲染、抽内嵌图 | ✓ 免费本地；需安装 | 长文 parse-once；单页 150–200dpi 视觉复核 |
| **pandoc** | DOCX 修订、媒体抽取、格式转换 | ✓ 免费本地；需安装 | `--track-changes=all` 读增删/批注；转换有损要标 |
| **LibreOffice headless** | Office→PDF、XLSX 公式重算 | ✓ 免费本地；需安装 | PPT/DOCX 渲染；公式重算后再读缓存值 |

### B2 · 零 key、本地重路径（复杂论文/扫描/版面）

| 资源 | 真强项 | access / 代价 | 何时升级 |
|---|---|---|---|
| **GROBID**（Apache-2.0） | 科研 PDF→TEI：header、sections、references、citation contexts、figures/tables/formulas | ✓ 免费；Java/Docker 服务较重 | 论文要精确章节/引用结构，轻解析阅读序不可靠时 |
| **Docling**（MIT） | reading order、复杂表结构、公式、图片分类、OCR、lossless JSON | ✓ 免费；模型/依赖重 | 嵌套表、复杂多栏、公式/图结构是核心交付时 |
| **OCRmyPDF + Tesseract**（MPL-2.0 + Apache-2.0） | 扫描 PDF 加可搜索文本层；rotate/deskew；多语言 | ✓ 免费；需 Ghostscript/Tesseract 语言包 | `triage=scanned/mixed`；**born-digital 不盲 OCR** |
| **MinerU local** | VLM 版面、表/公式/图、多栏阅读序 | ✓ 模型可本地；GPU/模型重 | Docling/GROBID 不适配或需 VLM 结构恢复时 |
| **PyMuPDF/PyMuPDF4LLM** | 高速渲染、page chunks、reading order、图片/表 | ⚠ AGPL-3.0 或商业授权 | 用户环境已有且用途合规时；嵌入/分发闭源或网络应用前核许可 |

> 许可提醒不是法律结论：本技能只报告官方许可与使用形态；具体项目是否触发义务需用户/法务判断。

Docling/Tika 这类 adapter 的输出必须接入 `reading_contract.py`：Docling 的 `PARTIAL_SUCCESS`、page/channel
error 不能被上层摘要吞掉；Tika 只可作为 text/metadata 抽取证据，不能单独支撑 layout、table grid 或 formula
语义结构声明。

### B3 · 免费公开结构源（论文有则优先）

| 资源 | 用处 | access | 诚实用法 |
|---|---|---|---|
| **arXiv HTML** | 原生章节、公式、figure URL，比 PDF 结构更易读 | ✓ 免费公开；并非每篇都有 | 有 HTML 就先建结构；缺失标 unavailable，回 PDF |
| **PMC/JATS XML** | 生医论文结构化全文、表、引用 | ✓ OA 条目免费 | 仅对开放全文；不把“PMC 无全文”判论文不存在 |
| **出版社开放 HTML/XML** | 标题层级、图表、补充材料 | 部分免费/部分受限 | 能访问才用；登录墙不绕过 |

这些资源只改善**结构读取**；DOI/引用真实性仍交 citation，文献补全仍交 literature-search。

### B4 · 登录/付费/云上传（不依赖；仅用户明确同意时备选）

| 资源 | 受限点 | 诚实做法 |
|---|---|---|
| **LlamaParse** | `LLAMA_CLOUD_API_KEY`、上传云端、tier 可能计费 | 不作为完成任务前提；敏感文件默认不用 |
| **Nutrient DWS** | API key、联网、额度/计费 | 只在用户已有账号并同意上传时用 |
| **Mathpix** | 公式/表 OCR 强，但需登录/API/付费 | 单公式可先用本地 pix2tex；不可用就标 unavailable |
| **MinerU Cloud** | API key、上传第三方 | 本地 MinerU/Docling/GROBID 优先 |

---

## §C 三条硬约束

1. **隐私优先**：未发表稿、审稿材料、合同、病历、密钥/个人数据默认只走本地；云服务/代理先 ASK，
   说明服务会收到什么文件。
2. **覆盖诚实**：理解笔记必须写“读了哪些、没读哪些、哪里低置信度”；不许以局部成功冒充全文覆盖。
3. **解析不越权**：file-reading 只负责抽取、结构、locator 与理解笔记；citation/consistency/
   research-ethics/result-analysis 的 verdict 不在这里重造。

---

## 复核入口

```powershell
# 本地能力
python scripts/pdf_ops.py --selftest
python scripts/docx_read.py --selftest
python scripts/xlsx_read.py --selftest

# 可选重工具当前 star / license（外部可变，引用前当天核）
gh api repos/grobidOrg/grobid --jq '{stars:.stargazers_count,license:.license.spdx_id}'
gh api repos/docling-project/docling --jq '{stars:.stargazers_count,license:.license.spdx_id}'
gh api repos/ocrmypdf/OCRmyPDF --jq '{stars:.stargazers_count,license:.license.spdx_id}'
gh api repos/pymupdf/PyMuPDF --jq '{stars:.stargazers_count,license:.license.spdx_id}'
```

> star/版本/可达性会腐；引用前当天重核。查不到写 unknown，绝不编。
