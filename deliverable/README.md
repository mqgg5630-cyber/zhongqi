# deliverable —— 我交付的成品

## 1. 中期检查表（Word）

- `中期.docx`：在**你的模板原件**（`sources/中期.docx`）上就地填入内容后的成品（含 Ⅱ.导师指导情况 与 检查小组成员名单）。
- `中期新.docx`：同一份内容的另一个文件名，用于"两版中期"同时提交/对比；两份文件内容一致，均为同一脚本生成。
  封面 7 栏已按 `sources/开题.docx` 填入（文绍华 / 2024110316 / 学术学位硕士研究生 / 生命科学学院 / 生物学 /
  生物化学与分子生物学 / 申亮）；正文按中期检查表篇幅扩写（研究背景与现状、目标、逐条研究内容、技术路线、进度、
  阶段性成果、尚需完成工作与对策）。
  校验：页面设置、样式、字体、表格框线与**所有非目标单元格逐字节一致**，封面内容控件"仅文字变化、格式不变"
  （`code/verify_docx.py` 输出 `RESULT: template format fully preserved`）。
- `中期检查表_填写内容.md`：正文草稿（纯文本，改这个文件最省事；开头 `# 封面信息` 段就是封面 7 栏），改完执行
  `python code/build_ops.py && python code/fill_docx.py --ops build/ops_中期.json` 即可重出 `中期.docx`。

## 2. 中期答辩 PPT（**八个**可编辑版本，挑一个用）

八版**内容口径一致**（同一份大纲 `docs/ppt_outline.json`），都是**原生可编辑 pptx**、全篇最小 **15 pt**、每页带演讲备注。

| 版本 | 文件 | 风格 |
|---|---|---|
| **H nature 风** | `中期答辩_H_nature风.pptx` | 论文汇报叙事弧 + 结论式标题 + 原生对照表（**答辩首选**；由 nature-skills 的 nature-paper2ppt 生成） |
| **F 深色科技风** | `中期答辩_F_深色科技风.pptx` | 近黑底 + 青色强调 + 网格底纹 + 深色结论条（**推荐首选**） |
| **G 学术期刊风** | `中期答辩_G_学术期刊风.pptx` | 白底纸面 + 期刊红 + 细线分隔 + 衬线标题（**推荐次选**） |
| A 学术蓝 | `中期答辩_A_学术蓝.pptx` | 深蓝 + 青绿标签块，信息密度高 |
| B 白底细线 | `中期答辩_B_白底细线.pptx` | 白底细线卡片、短下划线标题 |
| C 卡片色块 | `中期答辩_C_卡片色块.pptx` | 顶部色带 + 左侧竖条 + 卡片底色块 |
| D 双栏杂志风 | `中期答辩_D_双栏杂志风.pptx` | 正文两栏 + 细分隔线 + 右上角页码 |
| E 深色标题区 | `中期答辩_E_深色标题区.pptx` | 深色标题带 + 深色结论条 + 橙色强调 |

挑选建议与改法见 `PPT版本选择.md`；主推四版对比图 `../results/ppt_preview/四版主推对比_封面与第10页.png`，
逐页预览 `../results/ppt_preview/A版_*.png` … `G版_*.png`。

> 三条生产线：A—E 是同一套排版的换肤（python-pptx 直排）；F / G 先用 SVG 排版、再经
> [ppt-master](https://github.com/hugohe3/ppt-master) 编译成原生 DrawingML；H 版按
> [nature-skills](https://github.com/mqgg5630-cyber/nature-skills) 的 `nature-paper2ppt` 重新组织内容与版式。
> 八版口径由 `code/check_consistency.py` 统一核对。

## 3. 拿到新版后

```powershell
.\sync.ps1
copy .\deliverable\中期.docx  E:\0zhongqi\                                  # 或复制到你想要的位置
copy .\deliverable\中期答辩_H_nature风.pptx  E:\0zhongqi\                  # 答辩首选那一版
```
