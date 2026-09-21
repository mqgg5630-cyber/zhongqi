# frontend-design 参考索引（薄索引,非本地库）

> **零本地设计库铁律**:对标判据/竞品矩阵/栈版本的**唯一真相源 = [`docs/competitors/frontend-design.md`](../../docs/competitors/frontend-design.md)**(当天上网一手核)。
> 本目录只留**方法论**(怎么判、怎么选——几乎不过时),**不内嵌**会腐的版本号/工具目录/设计风格库。设计「事实」(趋势/字体/版本/组件库)**在线查 + 标 last_checked**,查不到标 unknown。
> （v1 曾在此堆 237 行竞品+版本目录 + 绑 `db05` 视觉库;v2 删——竞品进 SSOT 竞品文档,版本当天 `npm view`,无 db05。）

## 设计思考四问（写码前必答 · 方法论锚,反 AI-slop 的正面方向）

1. **Purpose**:解决什么问题 / 谁在什么场景用(学术海报 / 数据大屏 / 管理后台 / 移动端 / 营销 landing——信息密度与审美各不同)。
2. **Tone**:选定一个明确基调(brutally-minimal / editorial / luxury / playful / industrial / soft-pastel…),**刻意执行**胜过强度。
3. **Constraints**:框架 / 性能 / 可访问性(WCAG)/ 落地栈 / 是否已有品牌资产与代码库。
4. **Differentiation**:有什么**会被记住的唯一点**(signature element)?——没有记忆点 = 一眼 AI 模板。

> **principle-based direction**(Anthropic frontend-design 锚):告诉模型「想什么」而非「产什么」,并**显式点名不要的默认值**(Inter/紫蓝渐变/16px 圆角卡/巨型 hero/居中堆叠)。
> 配色/风格/框架/字体是**决策点**——给推荐 + 理由 + 备选,**AskUserQuestion 停下问用户**,绝不替用户拍板(SKILL 的 ASK 档)。

## 方法论参考文件（本目录,几乎不过时）

| 文件 | 是什么(方法论) |
|---|---|
| [`visual-a11y-rules.md`](references/visual-a11y-rules.md) | WCAG 2.2 对比度/触控/栅格/焦点**硬阈值**——**对比度数学已落 `_shared/visual_qa`,contrast_lint 复用,不在此重造** |
| [`redesign-audit.md`](references/redesign-audit.md) | 改造已有项目协议:preserve-vs-overhaul 判定 + Layout/Spacing/Hierarchy/Styling 四轴体检 + 守住不能动的 |
| [`fonts-and-colors.md`](references/fonts-and-colors.md) | 字体配对原则(display+body)+ 已成 AI-tell 的**禁用字体/禁用色族**(反 slop 取用池;字体名相对稳,引用前仍可在线复核可用性) |
| [`design-systems-map.md`](references/design-systems-map.md) | brief 信号 → 选哪套**官方组件库底座**的**决策逻辑**(一仓一套;版本号**不内嵌**,装前 `npm view` 当天核) |
| [`resource-map.md`](references/resource-map.md) | **真实用户找料改料**:组件/模板/动效**资源地图**(React Bits/HyperUI/21st.dev/shadcn registry/ShaderGradient + 灵感画廊) + **5 步闭环**(找料→去 slop→配 token→过三门→回看;access 诚实分级、付费/登录站不依赖) |
| [`ecosystem-2026.md`](references/ecosystem-2026.md) | 现代栈取向(Next/Vite/Tailwind/shadcn/Motion 何时用何者)+ **`npm view` 复检命令**(版本快照仅作时间锚、当天复检) |

## 在线找灵感 + 找现成料 + 取数（零本地库的落地;可达性诚实分级）

- **找现成组件料(真实用户不从零写)**:React Bits / HyperUI / 21st.dev / shadcn registry 免费 copy 现成组件 → **必走 5 步闭环**(找料→去 slop→配 token→过三门→回看,见 [`resource-map.md`](references/resource-map.md))。**付费/登录站(21st Magic MCP / MotionSites / Mobbin / Dribbble)不依赖**,诚实标 unavailable。
- **灵感站**:Awwwards `https://www.awwwards.com/websites/`(✓ WebFetch 实测可达 2026-06-22)· GSAP Showcase `https://gsap.com/showcase/` · Bento Grids `https://bentogrids.com/` · shadcn registry directory `https://ui.shadcn.com/docs/directory` · Mobbin/Dribbble(login/JS 受限→转 WebSearch 摘要,诚实标 unavailable)。
- **栈版本(装前当天核,绝不信内嵌快照)**:`npm view next version` / `npm view tailwindcss version` / `npm view shadcn version` …(全清单见 ecosystem-2026.md)。
- **规范**:WCAG 2.2 `https://www.w3.org/TR/WCAG22/`(SC 1.4.3 文本 4.5/3 · 1.4.11 非文本 3 · 2.4.11 焦点外观)。
- **竞品雷达**:`npx skills find "frontend design"` / Hallmark / Anthropic frontend-design plugin(依赖前先复验克隆可用性,同 SSOT 竞品文档)。

## 脚本（自查门;运行时真相,以 `--selftest` 为准）

- `scripts/contrast_lint.py` — 配色抽取(DTCG/CSS/显式 pairs)→ **委托 `_shared/visual_qa` 判 WCAG**(不重造数学);`--qa-report` 出 `light.visual_qa.v1`。
- `scripts/ai_tell_lint.py` — 机械抓 AI-slop 痕迹 T1–T8(scroll-cue / 装饰编号 eyebrow / version-footer / 英文 em-dash / 紫粉渐变 / emoji 当图标 / gradient-orb / 玻璃拟物);**启发式非终判**。
- `scripts/audit_checklist.py` — 可数版面门 R1–R7(eyebrow 上限 / 连续 image-text / 布局家族多样性 / hero 字数 / nav 高 / bento 配平 / 标注覆盖),带阈值非「看着行」。
- `scripts/browser_qa.py` — 真实 Chromium 三视口、运行错误、overflow、名称/alt、键盘、焦点启发式与截图。
- `scripts/design_delivery_gate.py` — 最终真实性门：必需决策不可 `not_required`，日期不可在未来，token/QA/截图必须是项目内
  真实文件且 sha256 吻合，Chromium/对比度报告状态必须与声明一致，render review 必须绑定已看截图。
- `assets/*.tsx` — GSAP/Motion 动效**参考片段**(给用户项目用,**非本技能运行依赖**)。
