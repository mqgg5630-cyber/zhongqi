# typesetting · 工具真实端点/选项/配置与已知坑（2026-06-21 一手核）

> 配 `SKILL.md` 用。对标笔记（动机/竞品/venue 规则）见 `../../docs/competitors/typesetting.md`；编译错误对照表见 `references/latex_errors.md`。
> 纪律：venue 页数/双盲/模板版本**逐年变 → 上官网一手核或问用户，不内嵌本地表**（铁律 2）。

## 1. 本技能脚本（可调用）

### `scripts/compile_driver.py` —— compile 命令门入口（真编译）
- `--compile paper.tex --outdir build`：引擎自动探测 + latexmk/tectonic 真编译多轮收敛 + 报错翻译大白话 + auto-fix 建议。
- `--detect paper.tex`：只报引擎选择不编译。`--engine auto|xelatex|lualatex|pdflatex`：手动指定引擎。
- **退出码契约（铁律 2，命令门据此定 pass/fail）**：`compiled→0`、`真 compile_error→1`（critical 阻断）、
  **`tool_missing=UNAVAILABLE→0`+横幅**（本机没装 LaTeX≠编译失败，不阻断不假装）、`no_file/timeout→2`。
- 引擎触发器：`fontspec`/`xeCJK`/`ctex`/`unicode-math`/`polyglossia` 或 `\documentclass{ctex...}`→xelatex；`luacode`/`\directlua`→lualatex；否则 pdflatex。
- latexmk 引擎 flag：`-pdf`(pdflatex)/`-pdfxe`(xelatex)/`-pdflua`(lualatex)，均配 `-interaction=nonstopmode -halt-on-error`。

### `scripts/desk_reject_gate.py` —— desk-reject 一票否决 findings producer（critical 静态门）
- `--tex paper.tex --pdf build/paper.pdf --double-blind --max-pages 8 --bib refs.bib --log build/paper.log --report out.json`
- 五 gate → `light.findings.v1`（producer=typesetting）：**desk_reject(超页/双盲露名)=critical**；anonymity/residual/bib_integrity/compile_log=warn。
- `--max-pages 0`（默认，不给）→ 页数检查 skip（机器不替猜 venue 限值）。`--double-blind` 仅双盲 venue 加。
- `--report` 写 light.findings.v1（verdict=fail 时进程 exit 1）；`--strict` 把 .log 的 undefined ref/cite 升 error。
- **跨技能复用**：`--bib` 走 `light-citation/scripts/citekey_audit`（缺则优雅降级跳过对账，不重造）。

### `scripts/submission_check.py` —— 源级合规静态扫（desk_reject_gate 编排它，也可单独跑）
- `--tex paper.tex --pdf paper.pdf --double-blind --max-pages 8`：双盲未匿名 \author/\thanks/致谢/链接、PDF /Author 元数据、超页、TODO。
- 输出 `{severity:high|med|info, code, msg}`；high 项 exit 1。纯标准库，只扫静态雷区不替代 venue 投稿须知。

### `scripts/precheck_log.py` —— .log 扫描（desk_reject_gate compile_log 门复用）
- `python precheck_log.py file.log [--json] [--max N] [--strict]`：抓 undefined ref/cite、multiply-defined label、overfull/underfull、missing file、致命 error。
- **de-wrap**：先把 79/80 列硬折断的长引用名/文件名拼回再匹配（消除裸模型扫 log 的长名漏报）。`--strict`：undefined ref/cite/重复 label 升 error（交付门拦）。退出码：有致命 error→1。

## 2. 模板起手式（`templates/`，5 份本对话本机真编译复验 exit 0）

| 模板 | 文件 | 起手式 | 引擎 | 双盲 | 复验 |
|---|---|---|---|---|---|
| IEEE 会议 | `ieee_bare_conf.tex` | `\documentclass[conference]{IEEEtran}`；`\IEEEauthorblockN/A`；宽图 `figure*` | pdflatex | `\thanks` 注释作者 | ✓ 72KB |
| ACM 会议 | `acm_sigconf.tex` | `\documentclass[sigconf]{acmart}`（v2.17 2026-03）；缺版权出红框 | pdflatex | `[sigconf,review,anonymous]` | ✓ 372KB |
| Springer LNCS | `springer_llncs.tex` | `\documentclass{llncs}`；必填 `\titlerunning/\authorrunning`；`\bibliographystyle{splncs04}` | pdflatex | — | ✓ 104KB |
| Elsevier | `elsevier_elsarticle.tex` | `\documentclass[preprint,review,12pt]{elsarticle}`；`frontmatter` | pdflatex | — | ✓ 94KB |
| 中文 | `ctex_chinese.tex` | `\documentclass{ctexart}` 或 `\usepackage{ctex}` | **xelatex(自动探测)** | — | ✓ 35KB |

- 取模板优先级：venue 官网 author kit > Overleaf 官方模板页 > CTAN 包。**会议模板有年度版本，务必用当届指定版本**（旧版被 desk-reject）。
- 从官方骨架改（IEEE `bare_conf.tex`、ACM `sample-*.tex`），不从空文件起。

## 3. venue desk-reject 硬规则（**示例，投稿前必上官网一手核** · 2026-06）
见 `../../docs/competitors/typesetting.md §2` 完整表。量级速记（**会变，仅参考**）：
- NeurIPS：9 页正文（图含），refs/checklist/附录不计；双盲（omit final+preprint 匿名 + 自动行号）。
- CVPR/ICCV/WACV：8 页（图表含），refs 不计；双盲；**超页/未匿名/不用模板→不送审拒**。
- ACL/ARR：长 8 / 短 4 页，Ethics+**Limitations** 不计；评审双盲（2024-02 起无匿名期）；**超长/缺 Limitations→desk-reject**。

## 4. 已知坑（一手核 / 本对话踩出）
- **UNAVAILABLE vs ERROR**（v1 旧坑，v2 已修）：v1 `compile_driver.main()` 把 `tool_missing` 也 return 1，会把「本机没装 LaTeX」误判成「论文编译失败」。v2 退出码已分野（见 §1）。
- **tectonic 不内置 biber**：`biblatex+biber` 路线在 tectonic 下需外置 biber（issue #1010）；传统 bibtex 路线 tectonic 自动跑。
- **pdfLaTeX 不支持中文/eps**：中文必 xelatex/lualatex（`ctex`）；eps 图 pdfLaTeX 需 epstopdf 或改 xelatex。
- **\cite 缺键不致编译失败**：latexmk 仍 exit 0 只出 ?? + warning → 归 desk_reject 的 bib_integrity warn，不是 compile_error；真编译成败只看命令门退出码。
- **页数从 PDF 数**：submission_check 正则数 `/Type/Page`，压缩流 PDF 可能数不准 → 命中是高风险提示，非绝对（渲染版式级合规靠人/官方 analyzer）。
- **MiKTeX 首次编译**：缺包会弹窗/自动装（设 auto 则静默），CI 环境建议预装或用 tectonic 自带按需下载。
- **Windows/Python（铁律 4）**：给 Python 读的 JSON 无 BOM；判编译成败只看 `$LASTEXITCODE`，别给原生 python 加 `2>&1`。

## 5. 分工边界（诚实）
- **compile（命令门）** vs **desk_reject（findings 门）**：前者真编译退出码定成败，后者静态扫 desk-reject 雷区产 findings。
- **typesetting** vs **figure(9)**：figure 出版级出图（栏宽/字号/dpi/视觉诚实）；typesetting 把图编进 LaTeX 并真编译。
- **typesetting** vs **citation(10)**：citation 核引用真实性 + 出 .bib + citekey 对账；typesetting 复用 citekey_audit 查 \cite↔.bib 键集（编译就绪），不核引用真实性。
- **Word 路线**：v2 不内置（v1 docx-js 依赖 npm，已砍）。需 Word 走 Pandoc `pandoc in.md -o out.docx --reference-doc=ref.docx`（指针，不内置）。
