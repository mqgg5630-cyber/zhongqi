# Typesetting 真实作者资源闭环

> 本页是执行地图。`SKILL.md` 定流程和红线；`references/build_contract.md`
> 定工件；`references/latex_errors.md` 定诊断；`templates/` 提供输入与 venue
> 起手骨架；`scripts/` 执行。`docs/competitors/typesetting.md` 只保存 R1
> 对标证据，不是运行说明。

## Round 3 handoff guard

`build_submission.py` now treats upstream handoffs as versioned artifacts, not
loose filenames. Citation delivery must be `DELIVERED`, must declare
`sha256:` hashes for BibTeX/citekey-audit/failure/review files, and must have
empty failures/review leftovers. Declared citation deliverable paths must stay
inside the delivery directory, and the build snapshot preserves the audit,
failure and claim-review sidecars under `source/provenance/citation/`. Figure manifests must be
`light.figure_delivery.v1` or `light.figure_build.v1`; the staged figure file
hash must match a declared output hash, and empirical deliveries must carry
confirmed result-analysis evidence binding. These checks are stage-11
preflight `ERROR`s, while citation authenticity and figure scientific QA remain
owned by their upstream skills.

## 八步闭环

### 1. 冻结输入与 provenance

从 `templates/typesetting_input.json` 建 `light.typesetting_input.v1`。正文只收
paper-writing 已交付稿；figure 行登记图件路径、目标嵌入路径、尺寸/DPI 与 figure
manifest；citation 行只指向 `delivery.json`；venue profile 必带来源类型、URL（若有）
与核查日期。缺来源的页限/双盲/模板/字体规则保留 `null/0`，不猜。

### 2. 选择工具链

扫描正文选择 pdfLaTeX/XeLaTeX/LuaLaTeX；扫描 `biblatex` options 或
`\bibliography` 选择 Biber/BibTeX。profile 可锁定选择；声明与源码冲突立即
`ERROR`，不靠编译器连锁报错猜根因。`compile-report.json` 保存绝对工具路径、
版本探测结果、工作目录与可复现命令。

### 3. 构建隔离快照并预检

```powershell
python scripts/build_submission.py --spec typesetting-input.json --preflight-only
```

预检依次核：声明文件及 SHA-256、citation delivery schema 与已交 citekey audit、
当前稿 `\cite`↔BibTeX、`\input`、图片路径、label/ref、宏包可用性、
documentclass/required packages、figure 交付路径。缺稿件/键/标签/图片是
`ERROR`；本机缺 `kpsewhich`/宏包/引擎是 `UNAVAILABLE` 或 `SKIP`，不怪论文。

### 4. 真多轮编译

```powershell
python scripts/build_submission.py --spec typesetting-input.json
```

核心优先 `latexmk`，本地没有时可对简单 BibTeX/无参考文献工程降级 Tectonic。
驱动在稿件目录运行、输出到隔离 `compile/`，保存 `latexmk` rule/run 次数与
PDF/log 哈希。成功但仍有 undefined citation/reference 或 rerun signal 时状态是
`UNRESOLVED`，不是假 PASS。

### 5. 根因定位

`compile_driver.py` 给引擎加 file-line diagnostics；先报第一个
`file.tex:line` 根因，再列 warning。错误分 `error`；未收敛引用/交叉引用分
`UNRESOLVED`；overfull/font/package warning 留在报告。工具启动失败/超时分
`UNAVAILABLE`。修复时只动 stage 11 排版源，保留失败件和修前报告。

### 6. desk-reject 前检

```powershell
python scripts/desk_reject_gate.py --tex typesetting-build/source/paper.tex `
  --pdf typesetting-build/compile/paper.pdf --bib typesetting-build/source/references.bib `
  --log typesetting-build/compile/paper.log --profile venue-profile.json `
  --report desk-reject-findings.json
```

页数、双盲作者/PDF Author metadata、profile 明示的 documentclass、required
package、page size、font embedding 可成为客观 critical。TODO、致谢、自指、
匿名链接与 overfull 是 warn，除非当前权威规范另有明确机器可判规则。语义泄露、
规则解释和最终视觉品质必须人工/官方 analyzer 复核。

### 7. canonical 交付

只有 compile=`PASS`、compliance=`PASS` 且 compliance critical=0 才写
`DELIVERED`。profile 明示要求的 page-box/font/page 检查若因本地 PDF 工具
不可用而无法给事实，整体为 `UNAVAILABLE`，不假装通过。交付包括
build manifest、compile report/log、compliance report、PDF、failure（若有）与
venue handoff。figure 的尺寸/DPI/视觉诚实不在这里重判；typesetting 只核嵌入路径、
浮动体、版面和编译。

### 8. stage 11 与 venue-matching

```powershell
python ../light-orchestrator/scripts/run_checkpoint.py `
  --file .light/passport.yaml --stage 11 `
  --gate "compile=python scripts/compile_driver.py --compile paper.tex --outdir build --json-out compile-report.json --quiet" `
  --findings desk-reject-findings.json --ts <ISO8601> --write
```

坏稿 exit 1 / `gate_failed`；根因修复后重跑到 exit 0 / `delivered`。typesetting
自身在 stage 11 内修；`ROUTES` 无 11，不伪造 back-edge。把
`venue-handoff.json` 的 PDF、页数、page size、profile/source 与 compliance
report 交 venue-matching。Windows 闸门用 `--quiet` 避免父进程按本地代码页解码
UTF-8 人读报告；完整诊断仍写 `compile-report.json`。

## 资源访问分层

| 层级 | 资源 | 用法与边界 |
|---|---|---|
| 本地免费核心 | Python stdlib、latexmk、TeX Live/MiKTeX、Tectonic、BibTeX/Biber、pdfinfo/pdffonts、ChkTeX/lacheck | 核心路径；缺失明确 `UNAVAILABLE` |
| 免费公开 | CTAN/TeXdoc、venue 官方 author kit/guidelines、官方 LaTeX analyzer、arXiv 提交说明 | 取得当前 template/profile；记录 URL/日期 |
| 免费登录/key | Overleaf 免费版、部分投稿系统、免费 API/key 服务 | 可选协作/核对；不得成为核心前提 |
| 机构受限 | IEEE/ACM 机构工具、学校字体/模板、内部投稿清单 | 用户提供或机构登录；标来源权限 |
| 付费闭源 | Overleaf premium、商业 preflight/编辑服务 | 只列可选；不得阻塞本地闭环 |

核心路径不依赖付费 Overleaf、私有 API key、浏览器插件或 npm 重依赖。
