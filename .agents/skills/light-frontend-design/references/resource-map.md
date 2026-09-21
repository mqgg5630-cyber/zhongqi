# 找料改料：组件/模板资源地图 + 工作流（真实用户视角 · Round 2 R2）

> **真实用户不从零写界面**——去资源站找现成组件/模板/动效 → 挑 → **改成自己的**（去 AI-slop、配项目 token、保可访问）。
> 本文件补的是 [`design-systems-map.md`](design-systems-map.md) 不覆盖的一层：那张表是「brief → 选哪套**官方组件库**」（Fluent/Carbon/Polaris，一仓一套底座）；
> 本文件是「要一个 hero / dashboard 卡 / 动效背景 → **去哪找现成料、怎么改成自己的**」（copy-paste / CLI 装的零散料）。两层互补，不重叠。
>
> **零本地库铁律**：下表是**资源地图（哪类料去哪找）+ 方法论（怎么挑怎么改）**——相对稳；**star/版本/可达性会腐**，引用前当天核（命令见文末），查不到标 unknown，**绝不编**。
> star 均 **2026-06-24 一手核 GitHub repo 页**（外部可变，带 snapshot）。
>
> **诚实重述超越点（§0.C ③ + figure scipilot 教训）**：「维护组件目录 → 按需选 → 装 → 改」是**真实用户 + 同类 skill 的强共识**
> （shadcnblocks 1,338 blocks 目录 / ui-ux-pro-max search.py BM25 选型 / superdesign 找灵感画布）——Light **不是「唯一想到去找现成料」**。
> Light 的真增量是**把找来的料过质量闭环**：找料 → **去 slop（ai_tell_lint）→ 配项目 token →
> 过 contrast/audit + 真实 Chromium browser QA（截图+SHA）→ render-then-look（截图+SHA）**。
> 部分同类更重生成/检索，是否具备同等输出验证须按版本核验；Light 明确把
> 「找料 ≠ 去 slop ≠ 配 token ≠ 浏览器可用 ≠ 视觉复核」落成可运行步骤（见 §A）。

---

## §A 找料改料工作流（5 步闭环 · 可执行非口号）

> 前置：场景与设计方向已在 [SKILL 步骤 ①] 用 `AskUserQuestion` 由用户拍板（绝不替用户定）。下面是「定了方向后，怎么找料落地」。

**Step 1 · 知道要找什么**（按 SKILL「适配场景表」拆成具体料）
- landing → hero / 特性 bento / 定价表 / CTA；dashboard → 指标卡 / 图表壳 / 侧边导航 / 数据表；学术 → 标题区 / 时间线 / 出版物列表。
- 一次只找**一类具体料**，别整页抄（整页抄 = 把别人的 slop 和场景错配全搬进来）。

**Step 2 · 去对的资源站找**（§B 资源地图：copy 料去 B1，看审美去 B2，付费/登录站诚实跳过去 B3）
- 现成组件代码 → React Bits / HyperUI / 21st.dev / shadcn registry（§B1，免费可 copy）。
- 只要审美/动效灵感 → GSAP Showcase / Bento Grids / Awwwards（§B2，看不抄码）。
- **守硬约束**：付费/登录站（21st Magic MCP / MotionSites / Mobbin / Dribbble）**不依赖**——能看的公开页当灵感，要登录/付费才出料的**诚实标 unavailable 走 WebSearch 摘要**，不假装拿到了料。

**Step 3 · 去 slop（确定性 lint；这些站常见高装饰风险）**
- 把抄来的片段存成文件 → `python scripts/ai_tell_lint.py <片段>` → 命中 T1–T8 **逐条人核 + 改**。
- **为什么这步不能省**：动效/hero/渐变类资源站的料**天然带 AI-slop**——ShaderGradient 出的就是紫粉渐变（T5）、React Bits 多 gradient-orb 光斑（T7）、社区 hero 爱 glassmorphism（T8）/ emoji 当图标（T6）/「scroll to explore」（T1）。**原样保留 = 一眼 AI**。

**Step 4 · 配项目 token（改成自己的，不是用别人的）**
- 把片段里**硬编码的 `#hex` / `px` 圆角 / 字体名**换成**项目自己的 CSS 变量 token**（`var(--color-accent)` / `var(--radius)` / `var(--font-display)`）。
- **一仓一套**：别因为抄了一个组件就引入第二套字体/圆角/间距体系（design token 自治，见 [`design-systems-map.md`] 硬约束）。
- 别把别人的品牌色直接搬来——配色是 [SKILL 步骤 ①] 用户拍板的方向，token 是落点。

**Step 5 · 静态三门 + 真实 Chromium + render-then-look**
- `contrast_lint.py`（复用 `_shared/visual_qa` 真算 WCAG 比值）：抄来的配色**未必达标**——浅灰文字/低对比 badge 是 copy 料的高频坑。
- `ai_tell_lint.py`：去 slop 后**再扫一遍**确认 0 命中。
- `audit_checklist.py`：R1–R7 版面（eyebrow 上限 / hero 字数 / bento 配平 / 标注覆盖）。
- `browser_qa.py --url <本地站点>`：真实 Chromium 三视口，抓 console/page error、横向溢出、
  interactive name、image alt、Tab 可达、截图和 `screenshot_sha256`；Playwright 缺失必须报 `UNAVAILABLE`。
- **render-then-look**：复核真实截图（三门/DOM 检查抓不到「徽章竖排折行」等审美与像素级错）。
  没做视觉复核必须明说，不静默假成功；复核记录要列每张截图 locator + sha256，防止回看后截图被替换。
- `design_delivery_gate.py --root <项目根> --as-of <核验日>`：把用户/继承决策、source locator/license/access/last_checked、
  单一 token 源、QA artifact/sha256、三视口截图 hash 和 render-review 元数据汇成交付合同；它会核文件真实存在、hash 吻合、
  Chromium/对比度报告状态与声明一致。浏览器不可用只能声明 `PARTIAL_BROWSER_UNAVAILABLE`，不能写成 `READY`。
- 任一 critical → 修 → 重过 → 直到无 critical（SKILL 步骤 ⑤ fix-loop）。

> **一句话**：step 1–2 找料，step 3–5 把料改进项目体系并用真实浏览器验证；二者缺一不可。

---

## §B 资源地图（按「要什么」分 · access 诚实分级 · 装前当天核）

### B1 · 现成组件代码（免费、无登录、可 copy/CLI 装——找料主力）

| 资源 | 是什么 | 拿料方式 | License | access |
|---|---|---|---|---|
| **React Bits**（DavidHDev/react-bits，**41.8K★**） | 130+ 动效 React 组件（文字/UI/背景动画）；JS/TS × CSS/Tailwind 四味可选 | 组件页 copy-paste，或 CLI（`npx shadcn` / `jsrepo`）装进自己代码库 | **MIT + Commons Clause**（个人/商用免费，**但不可转卖该库本身**） | ✓ 免费无登录 |
| **HyperUI**（markmead/hyperui） | 200+ 免费 Tailwind 组件（按钮/导航/表单/卡片/定价表）；纯 HTML+Tailwind 无需装包 | 站上 copy markup → 直接粘进 Tailwind 项目 | **MIT**（个人/商用免费） | ✓ 免费无登录 |
| **21st.dev**（serafimcloud/21st，**5.3K★**） | shadcn/ui 为底的社区 React+Tailwind 组件/blocks/hooks 市场 | **`npx shadcn` 命令**装（推荐，带齐依赖）或站上 copy | **MIT**（repo） | ✓ 浏览+`npx shadcn` 免费；⚠ **Magic MCP（AI 生成）是 freemium**（需 API key、免费额度 ~5 次/月）——见 B3 |
| **shadcn registry directory**（ui.shadcn.com/docs/directory） | 官方索引：各 shadcn 兼容组件源（含第三方 registry） | `npx shadcn add @<registry>/<item>` | 各源不同（逐源核，查不到标 unknown） | ✓ 免费 |
| **ShaderGradient**（ruucm/shadergradient，**1.7K★**，shadergradient.co） | WebGL 移动渐变生成器（颜色/形状/颗粒/光照可调） | 站上调好 → 导出 `<ShaderGradient/>` 组件码串；装 `@shadergradient/react`+`@react-three/fiber`+`three` | **MIT**（可商用，留版权 notice） | ✓ 免费；⚠ 产物是渐变背景——**正是 ai_tell_lint T5 抓的紫粉渐变重灾区**，配色须换项目 token + 过门 |

### B2 · 灵感画廊（看审美/动效，**学思路不抄码**——找方向用）

| 资源 | 是什么 | 怎么用 | access |
|---|---|---|---|
| **GSAP Showcase**（gsap.com/showcase）+ **Demos**（demos.gsap.com） | 顶级 agency 的 GSAP 动效站精选 + 可交互 demo（含 scrubbed bento gallery 等） | 看动效如何**传达层级/交互**（不是为炫而炫）；demo 多带 CodePen 源码可学手法 | ✓ 免费看；demo 有码 |
| **Bento Grids**（bentogrids.com） | 策展的 bento 布局灵感集 | 学 bento 模块化排布（配 `audit_checklist` R6 bento 配平：items==cells） | ✓ 免费看（灵感，不出码） |
| **Awwwards**（awwwards.com/websites，已在 references.md） | 获奖站画廊 + 趋势 filter | 当场看获奖站学审美/动效/配色趋势（WebFetch 实测可达） | ✓ 免费看 |

### B3 · 受限/付费（守硬约束**不依赖**；诚实标 unavailable，能看的公开页只当灵感）

| 资源 | 为何受限 | 诚实做法 |
|---|---|---|
| **21st.dev Magic MCP** | AI 生成组件是 **freemium**（需登录拿 API key、免费额度 ~5 次/月，超额付费） | **不依赖付费 MCP**；改用 B1 的浏览+`npx shadcn` 免费 copy 现成组件 |
| **MotionSites** | **付费** AI-prompt 资产库（卖「premium hero section」提示词，粘进 Lovable 等 AI builder） | **不买不依赖**；公开 gallery 可当 hero 灵感看，但其卖点是 prompt 非免费组件码 |
| **Mobbin / Dribbble** | login-gated / JS-heavy，WebFetch 多受限 | 诚实标 unavailable → 转 WebSearch 摘要（同 references.md 既有口径） |

---

## §C 改料三原则（把「抄来的」变成「自己的」——step 3–4 的判据）

1. **去 slop**：别原样保留这些站的 AI-tell——紫粉渐变（T5）/ gradient-orb 光斑（T7）/ glassmorphism 玻璃拟物（T8）/ emoji 当图标（T6）/「scroll to explore」（T1）/ 装饰编号 eyebrow（T2）/ 巨型空话 hero。`ai_tell_lint` 机械抓，逐条人核改。
2. **配 token 不搬色**：硬编码 `#hex`/`px` → 项目 CSS 变量 token；用户在 ① 拍板的配色/字体是真相，抄来的料只是结构骨架。一仓一套，不引第二套字体/圆角体系。
3. **守可访问 + 守 license**：抄来的对比度/触控目标/焦点态**未必达标** → `contrast_lint`（复用 visual_qa 真算）补齐；**MIT** 可商用（留版权 notice），**Commons Clause**（React Bits）可用于产品**但不可转卖该库本身**，license 查不到标 unknown，绝不假设可用；最终由 `design_delivery_gate.py` 拦住未知 license 却 copy code 的交付。

---

## 取数端点 + 当天复核（零本地库——值当天核，标 last_checked）

```powershell
# 组件源仓库是否仍活跃 / 当前 star / 是否换维护方（引用前当天核，绝不信本文件内嵌快照）
# React Bits / 21st / ShaderGradient star + license：直接看 GitHub repo 页
#   github.com/DavidHDev/react-bits · github.com/serafimcloud/21st · github.com/ruucm/shadergradient
# 装包前当天核版本（同 ecosystem-2026.md）
npm view @shadergradient/react version ; npm view three version ; npm view @react-three/fiber version
```

- 现成组件（免费 copy）：React Bits `reactbits.dev` · HyperUI `hyperui.dev` · 21st.dev `21st.dev` · shadcn registry `ui.shadcn.com/docs/directory`
- 灵感（看不抄码）：GSAP `gsap.com/showcase` + `demos.gsap.com` · Bento Grids `bentogrids.com` · Awwwards `awwwards.com/websites`
- 渐变生成：ShaderGradient `shadergradient.co`（导出码须换项目 token + 过 ai_tell_lint T5）
- 受限（不依赖）：21st Magic MCP（freemium API key）· MotionSites（付费 prompt）· Mobbin/Dribbble（login）→ 诚实标 unavailable

> **唯一真相源声明**：对标判据 SSOT 仍是 [`docs/competitors/frontend-design.md`](../../../docs/competitors/frontend-design.md)；本文件是其 §0.C ③「组件找料」横向结论的**落地工作流**。star/版本/可达性随时间变，引用前按上方命令当天复检；查不到标 unknown，绝不编。
</content>
</invoke>
