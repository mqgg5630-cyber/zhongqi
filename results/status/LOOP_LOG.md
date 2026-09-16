# 自循环轮次日志（docx / pptx）

agent 侧每轮由 `code/build_deliverables.py` 追加一行；本机侧的结论见
`results/status/check_r*_*.txt` 与 `handshake.json`。协议全文：`docs/自循环任务.md`。

> 下面前三行是**工具自测**（还没请本机核验时的调试迭代），从"正式第 1 轮"起才是交付轮次。
> 第一行那条 `fail` 是断言真的抓到了问题：当时用 python-docx 的 `doc.paragraphs` 数段落、
> 看不到 `w:sdt` 内容控件里的封面 7 栏，于是误判"封面没填"；改成直接读 `word/document.xml`
> 后通过。**判据会咬人，闭环才有意义。**

| 轮次 | 时间(UTC) | 侧 | 结论 | 摘要 | 备注 |
|---|---|---|---|---|---|
| 自测 | 2026-09-16 08:55:27 UTC | agent | fail | 重生成 13 步 / 内容变更 0 个 / 与 HEAD 一致 8 个 | 度量方式写错：正文里找不到 '文绍华' / '2024110316'，paras=22 < 60（改为读 document.xml 后修正） |
| 自测 | 2026-09-16 09:05:21 UTC | agent | pass | 重生成 13 步 / 内容变更 0 个 / 与 HEAD 一致 8 个 | 断言与闸门全部通过 |
| 自测 | 2026-09-16 09:18:29 UTC | agent | pass | 重生成 13 步 / 内容变更 0 个 / 与 HEAD 一致 8 个 | 负向自测：给 中间版/中期.docx 追加 1 字节 → sha256 判失败；截断到 1 000 B → 体积判失败；`git checkout --` 还原后恢复 pass |
| 1 | 2026-09-16 09:19:22 UTC | agent | pass | 重生成 13 步 / 内容变更 0 个 / 与 HEAD 一致 8 个 | 断言 + 闸门 + **预演本机核验**全过；已 `--request`，handshake：round 1 / arena=awaiting_check / local=pending —— 等本机值守起来接管 |
