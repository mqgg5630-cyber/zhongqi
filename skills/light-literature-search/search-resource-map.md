# 文献调研：真实研究者工作流 + 资源地图（真实用户视角 · Round 2 R2）

> **真实研究者做文献调研不是"丢个词进搜索框"**——是**雪球式引用链 + 多源交叉 + 持续追踪**的工作流:找一两篇最对口的种子 → 前后向滚雪球追引用链 → 多源补盲 → 建地图找 gap → 存检索式持续追新。本文件把这套**真实工作方式内化进本技能**:每一步**接进本技能既有脚本/门的闭环**,不是方法论罗列。
>
> **与既有文件不重叠声明**(范本 resource-map.md 同款):
> - [`references.md`](references.md) = **API 端点真相源 + 协议库**(逐源端点/参数/限流 + screen-extract/深读/追踪/灰文献协议);"某个源怎么调"看那里。
> - 本文件 = **研究者视角的"去哪找、按什么顺序、access 怎么分级"导航地图**;"这一步该去哪、怎么接进脚本"看这里。两层互补,不复写端点参数。
>
> **零本地库铁律**:下表是**资源地图(哪类需求去哪)+ 工作流(按什么顺序)**——相对稳;**可达性/计费/反爬会腐**,引用前当天核(命令见文末),查不到标 unknown,**绝不编**。star/可达性均 **2026-06-26 一手核**,外部可变带 snapshot。
>
> **诚实重述(防做偏 · figure scipilot 教训)**:"雪球式引用链 + 多源交叉 + 建地图"是**真实研究者 + 同类 skill(K-Dense/borghei/STORM/Connected Papers)的强共识**,Light **不是"唯一想到滚雪球"**。Light 的真增量 = **把这套工作流落成确定性脚本编排(三层分别排序)+ 产机读 findings(覆盖度/撞车/年代偏斜)被下游门消费 + 全程零 key 免费骨架 + 离线降级**(对标见 [`docs/competitors/literature-search.md`](../../docs/competitors/literature-search.md) §0.C/§2)。

---

## §A 文献调研工作流（雪球式引用链 5 步闭环 · 可执行非口号 · 每步接脚本/门）

> 前置:检索范围/深度已在 [SKILL「ASK 决策点」] 用 AskUserQuestion 由用户拍板(速览/中等/穷尽 · 时间窗 · 中英文)。下面是"定了范围后怎么找"。

**Step 1 · 找种子(最对口的一两篇,不是一上来求全)**
- 宽主题先 `domain_map.py "<方向>" --require-terms <领域词> --current-year 2026`——三层分别排序直接出**前沿/经典/跨领域**三层,头部即高质量种子。
- 已知一篇关键论文(用户给的/读过的)→ 直接进 Step 2 滚雪球,跳过盲搜。
- **守硬约束**:OpenAlex(免 key 灰度)+ Crossref/arXiv/Europe PMC(真免 key)作骨架;Google/百度学术只当"发现入口",命中后**回 OpenAlex/Crossref 按 DOI 核**再入表(NEVER 第 7 条),不直接采信其页面被引。

**Step 2 · 滚雪球追引用链(研究者建脉络的真实主力,关键词检索的盲区在这补)**
- 有种子 DOI → `snowball.py <DOI> --two-hop-direction backward`(后向=它引了谁=思想来路) + `forward`(前向=谁引了它=后续发展)。
- **为什么这步不能省**:好综述的脉络不是搜出来的,是**沿引用链追出来的**;纯关键词会漏掉"措辞不同但同源"的工作。Connected Papers/ResearchRabbit 这类工具的核心也正是引用链(共被引+文献耦合)——本技能用 OpenAlex `referenced_works` **零额外 API** 算文献耦合簇(`domain_map` 方法谱系层),拿到等价信号。

**Step 3 · 多源交叉补盲(没有单一源覆盖全,互补盲区)**
- 生医方向 → `biomedical_search.py`(Europe PMC 免 key 主力 + PubMed MeSH 受控词,这俩独有);系统综述 → `prisma_flow.py` 计数勾稽(审稿人必查)。
- 中文方向 → `cn_journal_probe.py` + ISSN→OpenAlex(CNKI/万方无免费 API,标题英译坑见 references.md「中文文献检索途径」)。
- 窄领域近三年文稀 → `cross_domain_search.py --application <你的领域> --method <要迁移的前沿技术>`(应用轴×方法轴正交,不拼词)。

**Step 4 · 建地图找 gap + 撞车自检(产出不是列表,是可喂 idea 的地图)**
- `domain_map.py ... --idea "<你设想的 idea>" --report findings.json`——出领域地图三件套(脉络/方法谱系/未解问题)+ **撞车信号**(`semantic_sim` 找最像的前作 + facet 槽位)+ **覆盖度门** + **★年代分布偏斜 advisory**(R1 新增,借 imbad0202,判据按真实数据校准:近三年占多数且缺 ≥8 年奠基作→提示 backward 滚雪球补奠基根;全 ≥8 年→提示 cross_domain 嫁接)。
- findings 交总控 `run_checkpoint --stage 1` 聚合 → 喂 idea-generation/idea-critique。**撞车只产信号,novel 判决归 idea-critique**(NEVER 第 2 条)。

**Step 5 · 存检索式持续追新(长期项目的高频真实需求)**
- `search_normalize.py "<检索式>" --from-date <上次运行日> --known-dois known_dois.txt`——增量重跑只看 diff(新增了什么、是否影响本项目结论),不全量重检;`tracker.py` 持久 SQLite 库按 DOI 记 new/seen。
- 协议细节(saved_search.yaml / 月跑节律 / 宽 query 必人工筛再入库)见 references.md「文献定期追踪协议」。
- 系统性/快速检索协议先过 `scripts/search_protocol_gate.py --as-of YYYY-MM-DD`：source family 使用受控枚举，
  `SEARCHED` source 与 `RUN` query 必须有 `raw_locator + raw_sha256`，停止声明必须有
  `observed_locator + observed_sha256`，冻结/检索/修订日期不得晚于 `--as-of`。

> **一句话**:同类工具帮你**搜到论文**;Light 帮你把"找种子→滚雪球→多源补盲→建地图→追新"这套真实研究者工作流**落成确定性脚本 + 机读 findings**,每步可复验、可喂下游、可离线降级。

---

## §B 资源地图（按"要什么"分 · access 诚实分级 · 引用前当天核）

### B1 · 免 key 学术取数（无登录、可程序化、本技能骨架——找料主力）

| 资源 | 要什么时用 | 接哪个脚本 | access |
|---|---|---|---|
| **OpenAlex**(2.5 亿+ works) | 主源:跨学科检索/被引/`referenced_works` 算文献耦合/`group_by` 年度脉络 | `search_normalize`/`domain_map`/`snowball` | ⚠ **官方 2026 起称需免费 key($1/天)**,匿名+mailto 灰度仍 200——**不硬依赖**(详 references.md「OpenAlex 接入真相源」) |
| **Crossref**(DOI 注册局) | DOI 去重真相源 + 中文刊按 ISSN 检 | `search_normalize` 第二源 | ✓ 真免 key(带 mailto 进礼貌池) |
| **arXiv API** | 近三年前沿/跨域方法 SOTA(CS/物理/数学/q-bio 预印本) | `arxiv_search` | ✓ 真免 key(**须 https**,间隔≥3s) |
| **Europe PMC**(EMBL-EBI) | 生医免 key 主力 + 滚雪球 citations/references 端点 | `biomedical_search`/`snowball` | ✓ **完全免 key** |
| **PubMed E-utilities** | 生医 MeSH 受控词检索 + Clinical Queries(此源独有) | `biomedical_search --source pubmed` | ✓ 免 key(3 req/s;注册免费 key 提到 10) |
| **DOAJ** | 开放获取相关度排序补盲 | `search_normalize` 第三源 | ⚠ **2026-06-17 实测 403**(疑 WAF)→降级跳过,覆盖度门如实标 |
| **bioRxiv/medRxiv** | 最新未发表预印本(比正式发表早数月) | references.md 端点(按需) | ✓ 免 key(预印本须标可信度分级) |

### B2 · 引用链/语义发现工具（研究者建脉络的真实主力 · 看思路,机制本技能已等价实现）

| 资源 | 是什么 | 本技能怎么拿到等价信号 | access |
|---|---|---|---|
| **Connected Papers** | 力导向图,共被引+文献耦合聚相关(不靠直接引用) | OpenAlex `referenced_works` 零额外 API 算文献耦合簇 → `domain_map` 方法谱系层(出结构化簇表非交互图) | ✓ 免费看(每月限额);⚠ 无 API,本技能不依赖其站 |
| **ResearchRabbit** | 种子论文→直接引用/文献耦合/合著网络/语义相似四类连边 | `snowball` 前后向 + `semantic_sim` 语义近邻;合著网络本技能暂不建(诚实 P2) | ✓ 免费(需注册登录)→**本技能不依赖,走 OpenAlex/S2 引用端点** |
| **Semantic Scholar** | SPECTER2 768 维语义嵌入 + influentialCitationCount + tldr | `snowball` 引用端点;嵌入档可注入 `_shared/semantic_sim` 强化撞车检测 | ✓ 匿名可用(限速严 429);免费 key 走 x-api-key 提配额 |
| **arXiv listing / Papers with Code** | 看某方向最新预印本流 + SOTA 排行 | `arxiv_search` 取元数据;PwC 当 SOTA 线索(回学术源核) | ✓ 免费 |

### B3 · 发现入口/SaaS（看趋势 · 受限/付费**不依赖**;诚实标 unavailable 走 WebSearch）

| 资源 | 为何受限 | 诚实做法 |
|---|---|---|
| **Google Scholar / 百度学术** | **无官方 API + 反爬强**;页面被引数口径不透明 | 仅当**发现入口**;命中后**回 OpenAlex/Crossref 按 DOI 核**再入表(NEVER 第 7),不直接采信其被引;批量取数需浏览器式抓取=非确定须二次核 |
| **Elicit / undermind / Consensus / scite** | **付费 SaaS**(无机读交接) | 不依赖;其方法论(PRISMA 可审计筛选/召回估计/引用情感)已提炼进本技能门与 references.md 协议(对标见 competitors §0.B) |
| **CNKI / 万方 / 维普 / CSCD** | **无免费 API + 订阅墙** | OpenAlex/Crossref 按 ISSN 检中文刊(低门槛主力);独有成果让用户机构账号导题录(RIS/EndNote);精确中文被引免费源不可得→诚实标 unknown |
| **PaperQA2 / OpenScholar** | 全文 RAG **需 PDF 库** | 本技能守合规**只取元数据/摘要**;单篇深读靠宿主多模态 + OA 版(走 light-citation Unpaywall 口径) |

---

## §C 守硬约束三原则（把"真实工作流"落地的判据）

1. **零 key 骨架优先**:真正免 key 的 **Crossref + arXiv + Europe PMC + PubMed** 作保底骨架,OpenAlex 匿名灰度可用则用作主力增强;**全程零 MCP、零付费、零强制注册**(守硬约束「不要求注册账号」)。任一付费/登录站(Elicit/ResearchRabbit/CNKI)→**诚实标 unavailable,转 OpenAlex/Crossref 或 WebSearch 摘要**,不假装拿到了料。
2. **可达性当天核,失败诚实降级**:DOAJ 今天 403、OpenAlex 灰度——**不假设可用**;`domain_map` 覆盖度门按**真实 HTTP 码**标 covered/失败/unknown,免 key 接口配额/覆盖限**不保证召全**,不写"已穷尽检索"。无网时各脚本回退 `[OFFLINE]` 合成样本,管线仍可验证。
3. **发现入口 ≠ 真相源**:Google/百度学术、SaaS、行业报告、竞赛方案是**发现线索**,关键结论(被引/DOI/年份)一律**回学术真相源(OpenAlex/Crossref/DOI)交叉核**再入表;查不到写 `unknown`,**宁缺毋造**(NEVER 第 1/7)。

---

## 取数端点 + 当天复核（零本地库——可达性当天核,标 last_checked）

```bash
# 免 key 骨架当天连通性(引用前核,绝不信本文件内嵌快照)
curl -sI "https://api.crossref.org/works?rows=1&mailto=you@example.com" | head -1   # Crossref
curl -sI "https://export.arxiv.org/api/query?search_query=all:test&max_results=1" | head -1  # arXiv(须 https)
curl -sI "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=test&format=json" | head -1  # Europe PMC
curl -sI "https://api.openalex.org/works?search=test&mailto=you@example.com" | head -1  # OpenAlex(灰度)
curl -sI "https://doaj.org/api/v2/search/articles/test" | head -1                   # DOAJ(2026-06 曾 403)
```

- 端点/参数/限流逐源真相源:[`references.md`](references.md)(本文件不复写,只给指针)
- 引用链工具(看思路不依赖其站):Connected Papers `connectedpapers.com` · ResearchRabbit `researchrabbit.ai`(登录) · Semantic Scholar `api.semanticscholar.org`
- 受限(不依赖):Google/百度学术(无 API)· Elicit/undermind/Consensus/scite(付费)· CNKI/万方/维普(订阅墙)→ 诚实标 unavailable

> **唯一真相源声明**:对标判据 SSOT = [`docs/competitors/literature-search.md`](../../docs/competitors/literature-search.md);端点参数 SSOT = [`references.md`](references.md);本文件是二者的**研究者视角工作流落地导航**。可达性/计费随时间变,引用前当天复检;查不到标 unknown,绝不编。
