# 版本记录 (version_history.md) — <PROJECT_NAME>

> **Keep a Changelog 式 + 与 git tag 对齐**。格式:`[YYYY-MM-DD] 材料(论文/PPT/图/代码) vN — 变更摘要`。
> 出正式版本(代码可复现 / 论文定稿 / 投稿)时追加并打 **annotated** `git tag -a vN -m ...`
> （`version_tag_reconcile.py` 双向核对 version_history ↔ git tag;`git describe` 只认 annotated tag）。
> **未出正式版本前只记当前态、不编造历史版本**;说明行含“骨架/草稿/未定稿/未出”即跳过 tag 对齐。

<!-- 版本从下面开始追加(去掉注释)。示例: -->
<!-- - [2026-06-17] 代码 v0.1.0 — 检测+跟踪可运行骨架,pytest 2 项通过 -->
<!-- - [2026-06-17] 代码 骨架态(未打 tag) — 下游训练脚本未落地,实现完成度约 25% -->
