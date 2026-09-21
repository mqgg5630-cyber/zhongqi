# Brief → 官方设计系统映射表（决策逻辑;版本不内嵌）

> **方法论**——给 brief 信号 → 选哪套官方设计系统。**一个项目只用一套**（混用产生 token 冲突、双倍 bundle、视觉漂移）。
> **零本地库铁律**:下表只给**包名 + 选型理由**,**不写死版本号**(版本会腐——v1 曾 `curl 实测 200` 钉死 `@9.74.1` 等,几个月即过期)。
> 装前**当天** `npm view <pkg> version` 一手核,或直接 `@latest`;查不到标 unknown。
> （**v2 诚实更正**:v1 这里把「风格实例卡」指向 `db05/databases/db05-frontend-styles/`——**一手核 v2 无 db05、无该数据库**;v2 改为**在线找灵感**(Awwwards/Mobbin/shadcn directory)替代本地风格卡,见 [`references.md`](../references.md)。）

## 决策表（命中即选;装前 `npm view <pkg> version` 当天核）

| brief 信号 | 选哪套 | 理由 | 包名（版本当天核） |
|---|---|---|---|
| 企业内网 / Office 风 / Windows 生态 / Teams 类 | **Fluent UI v9** | 微软官方,深 Office 视觉,主题 token 体系成熟 | `@fluentui/react-components` |
| 数据密集后台 / 监控 / IBM 风 / 工业 SaaS | **Carbon** | IBM 设计语言,强表格/数据网格,可访问性扎实 | `@carbon/react` |
| 电商 / 商家后台 / Shopify 生态 | **Polaris** | Shopify 官方,电商语义组件(Card/ResourceList)齐全 | `@shopify/polaris` |
| 项目管理 / 协作工具 / Jira-Confluence 风 | **Atlaskit** | Atlassian 官方,分包按需装 | `@atlaskit/primitives` `@atlaskit/button` … |
| 开发者工具 / 代码平台 / GitHub 风 | **Primer** | GitHub 官方,深色友好,开发者审美 | `@primer/react` |
| 英国政府 / 公共服务 / 极致可访问性合规 | **govuk-frontend** | GOV.UK,WCAG/渐进增强标杆,非 React(Nunjucks+原生 JS) | `govuk-frontend` |
| 美国联邦政府 / 公共部门 / Section 508 | **USWDS** | 美国政府标准,508 合规,框架无关 | `@uswds/uswds` |
| 需要无样式可完全定制的底座 / 自建设计系统 | **Radix Primitives** | 只给行为+可访问性,样式全自定义,配 Tailwind(shadcn/ui 的底座) | `@radix-ui/react-*`(按需逐组件装) |
| 品牌定制落地页/展示页(都不命中) | **不装组件库** | 用 Tailwind v4 + 自有 token + 本技能 `assets/` 的 GSAP/Motion 骨架 | — |

## 选择决策树（逐条判定,命中即停）

1. 强合规公共部门? 英国→govuk-frontend;美国→USWDS。
2. 绑定某商业生态? Office/Teams→Fluent;Shopify→Polaris;Atlassian→Atlaskit;GitHub/devtool→Primer。
3. 数据密集型企业后台、要现成数据表格? → Carbon。
4. 要自己掌控全部视觉、只借无障碍行为? → Radix Primitives + Tailwind。
5. 都不命中(品牌定制落地页/展示页)? → 不装组件库,Tailwind v4 + 自有 token + assets/ 骨架。

## 硬约束

- **一仓一套**:选定后 `package.json` 只保留这一套 UI 库;新增组件先看库内有没有,没有再自建,不引第二套。
- **版本当天核 + pin 到核到的版本**:`npm view <pkg> version` 拿到当天版本号 → `npm i pkg@<核到的版本>`(用确切版本非 `^`/`~`,避免无意升级破坏 token);**绝不信任何文档里内嵌的版本号**。
- **Radix 是底座不是成品**:`@radix-ui/react-*` 按组件逐个装(dialog/dropdown-menu/tooltip…),样式自己写。
- **govuk-frontend / USWDS 非 React 组件库**:CSS + 原生 JS 模块(USWDS 框架无关,govuk 用 Nunjucks);React 项目里用要包一层或只取其 CSS/设计 token。

> 选型逻辑(哪类 brief 配哪套)相对稳;**包是否仍活跃维护、当前版本号、是否换了维护方**——装前当天 `npm view` 一手核,不靠本文件。
