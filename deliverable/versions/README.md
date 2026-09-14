# deliverable/versions —— 另外两版中期答辩 PPT（供挑选）

三版内容**完全一致**，都来自同一份大纲 `docs/ppt_outline.json`；区别只在**版式与配色**。
三版都是**原生可编辑 pptx**（真实文本框与形状，不是图片化），最小字号 **15 pt**，并且**每页都写入了"演讲备注"**（口播稿）。

| 版本 | 文件 | 风格 | 适合 |
|---|---|---|---|
| **A 学术蓝** | `../中期答辩.pptx` | 深蓝 + 青绿标签块，信息密度较高 | 想一次讲清全部内容、偏"信息型"汇报 |
| **B 极简线框** | `中期答辩_B_极简线框.pptx` | 白底、细线卡片、短下划线标题、左侧竖条结论 | 投影仪/打印都干净，最耐看，**推荐作为首选** |
| **C 卡片色块** | `中期答辩_C_卡片色块.pptx` | 顶部浅蓝色带 + 左侧深蓝竖条 + 卡片底色块 | 想要"设计感"、颜色对比更强 |

三版预览图：`../../results/ppt_preview/预览_第*-*页.png`（A 版）、`B版_第*-*.png`、`C版_第*-*.png`。

## 怎么改

- **改文字**：直接在 PowerPoint / WPS 里改即可（全部是文本框）；若想批量重出，改 `docs/ppt_outline.json` 后运行
  `python code/make_ppt_variants.py`（重出 B、C 两版）与 `python code/make_ppt2.py`（重出 A 版）。
- **换配色 / 换版式**：`code/make_ppt_variants.py` 顶部的 `STYLES` 字典里改色值即可（`accent` 主色、`accent2` 强调色、`card_fill` 卡片底色）。
- **换成自己的图**：把 `results/figures/figA—figG*.png` 换成自己的同名文件，再重跑上面两条命令。
- **字号底线**：重出后请跑 `python code/check_ppt.py <文件>`，确认仍是"最小 15 pt、无越界、文字不压图"。

## 生成命令

```bash
python code/make_ppt2.py                 # A 版 -> deliverable/中期答辩.pptx
python code/add_notes.py deliverable/中期答辩.pptx      # A 版补演讲备注
python code/make_ppt_variants.py         # B + C 版 -> deliverable/versions/
python code/check_ppt.py deliverable/versions/中期答辩_B_极简线框.pptx
python code/preview_ppt.py deliverable/versions/中期答辩_C_卡片色块.pptx -o build/prevC
```

> 用别的工具（ppt-master / presenton）重做时，把这套大纲与图片一起交给它：
> 见 `../../docs/PPT生成Skill选择.md` 与 `../../docs/PPT大纲.md`。
