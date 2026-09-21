# LaTeX 日志根因手册

先读 `compile-report.json` 的第一条 source-located diagnostic，再查本页。
修最早根因后重编；不要从连锁错误末尾猜。完整交付状态定义见
`build_contract.md`。

## 状态不是错误消息

| 状态 | 证据 | 处置 |
|---|---|---|
| `PASS` | 编译器 exit 0、PDF 存在、无 rerun/undefined cite/ref | 继续 desk-reject 检查 |
| `ERROR` | 稿件、输入、backend 或编译命令导致非零/无 PDF | 按首个 `file:line` 修稿件 |
| `UNAVAILABLE` | 工具、引擎、backend、宏包或资源不能启动/超时 | 修环境；不得说论文有错 |
| `UNRESOLVED` | PDF 已生成但引用/交叉引用仍未收敛 | 查 key、backend、aux/bbl 与轮次 |

## 致命根因

| 日志症状 | 常见根因 | 最小修法 |
|---|---|---|
| `Undefined control sequence` | 命令拼错或缺宏包 | 在报告所指行核拼写；添加实际所属宏包 |
| `File 'x.sty' not found` | 本地宏包不可用 | 将环境标 `UNAVAILABLE`；安装/切换完整发行版后重跑 |
| `File 'figure.pdf' not found` | 快照未声明图件或相对路径错 | 修输入 spec/target 或 `\includegraphics` 路径 |
| `Missing $ inserted` | 数学符号出现在文本模式 | 用 `\(…\)`；普通下划线写 `\_` |
| `Missing } inserted` / `Runaway argument` | 花括号或命令参数未闭合 | 从报告行向前找最近未配对 `{` |
| `\begin{x} ... \end{y}` | 环境不匹配 | 修为相同环境名并检查嵌套 |
| `Unicode character ... not set up` | pdfLaTeX 遇到不支持字符 | 用户同意后切 XeLaTeX/LuaLaTeX 或修输入编码 |
| `Emergency stop` / `Fatal error` | 前面已有首个致命错误 | 忽略本行，修第一条 source-located error |

## 引用与 backend

| 症状 | 根因 | 修法 |
|---|---|---|
| `Citation 'k' undefined` | `k` 不在 staged `references.bib`，或 backend 未运行 | 先看 live citekey audit，再核 BibTeX/Biber |
| `I couldn't open database file` | `\bibliography{}` 路径与快照不一致 | 修 staged BibTeX 文件名/相对路径 |
| `.bbl is wrong format` | Biber 工程被 BibTeX 跑过，或反之 | 以 source + profile 选唯一 backend，清理旧中间件重编 |
| preflight `BIB_BACKEND_MISMATCH` | profile 与源码声明冲突 | 修 profile 或经作者同意迁移源码；不要混跑 |
| delivered audit ok、live audit fail | citation 交付对应的稿件版本与当前稿不同 | 让 citation 对最终稿重出 audit，或修当前 citekey |

引用 DOI 真实性、元数据冲突、撤稿关系与 claim relevance 仍归 citation；
typesetting 只处理 key、backend 与编译收敛。

## warning 与未收敛

| 日志症状 | 分级 | 处置 |
|---|---|---|
| `Reference ... undefined` | `UNRESOLVED` | 核 `\label` 拼写和 latexmk 轮次 |
| `Label(s) may have changed. Rerun` | `UNRESOLVED` | 继续编译；重复签名则停下报告 |
| `Label ... multiply defined` | error/preflight | 给 label 唯一命名 |
| `Overfull \hbox` | warning | 查长 URL、表格、公式；渲染后人工看 |
| `Underfull \hbox` | warning | 通常是美观问题；避免无谓强制换行 |
| `Token not allowed in a PDF string` | warning | 为数学标题加 `\texorpdfstring` |

## Windows 工具探测陷阱

`where pdfinfo`/`where pdffonts` 可能先返回失效的 `.cmd` wrapper，后面仍有
可用 `.exe`。本技能优先真实 exe；不能只凭 `shutil.which()` 宣布工具可用。

`pdffonts` 的 `type` 可能是 `Type 1`、`CID TrueType` 等多词值，不能用固定
split 列号读取 `emb`。`submission_check.py` 用末端 `yes/no` 列结构解析并有
回归，避免把已嵌入字体误报为未嵌入。

stage-11 command gate 在 Windows 使用：

```powershell
python scripts/compile_driver.py --compile paper.tex `
  --json-out compile-report.json --quiet
```

`--quiet` 只关闭 UTF-8 人读输出以避开父进程本地代码页；完整诊断保留在 JSON。
