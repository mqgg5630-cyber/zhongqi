# 决策日志 (decision_log.md) — <PROJECT_NAME>

> **ADR 式追加**:一条重大决策一行,**只追加不改写**,保留完整时间线(对标 Architecture Decision Records）。
> 格式:`[YYYY-MM-DD] 决策 — 理由 — 来源(技能名/会话)`（行首 `- `,中文破折号 ` — ` ≥2 个）。
> 相对日期(今天/上周/最近…)一律转绝对日期。取舍变更=**追加新行**(注明 supersedes 哪条决策),不删旧行。
> 引用外部可变事实(venue 计量 / 数据集许可·DOI / 外部数值)须带快照:`值 [snapshot YYYY-MM-DD, src=在线/官方源]`。

<!-- 决策从下面开始追加(去掉注释)。示例: -->
<!-- - [2026-06-17] 锁定创新点为“级联误差传播抑制” — 三模块纯串联新颖性≈0,须有方法层 delta — 来源 idea-critique -->
<!-- - [2026-06-17] 投稿首选 X 刊 — 应用型主场;h_index≈220 [snapshot 2026-06-17, src=OpenAlex:venue] — 来源 venue-matching -->
