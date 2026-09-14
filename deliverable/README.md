# deliverable —— 我交付的成品

## 1. 中期检查表（Word）

- `中期.docx`：在**你的模板原件**（`sources/中期.docx`）上就地填入内容后的成品。
  封面 7 栏已按 `sources/开题.docx` 填入（文绍华 / 2024110316 / 学术学位硕士研究生 / 生命科学学院 / 生物学 /
  生物化学与分子生物学 / 申亮）；正文按中期检查表篇幅扩写（研究背景与现状、目标、逐条研究内容、技术路线、进度、
  阶段性成果、尚需完成工作与对策）。
  校验：页面设置、样式、字体、表格框线与**所有非目标单元格逐字节一致**，封面内容控件"仅文字变化、格式不变"
  （`code/verify_docx.py` 输出 `RESULT: template format fully preserved`）。
- `中期检查表_填写内容.md`：正文草稿（纯文本，改这个文件最省事；开头 `# 封面信息` 段就是封面 7 栏），改完执行
  `python code/build_ops.py && python code/fill_docx.py --ops build/ops_中期.json` 即可重出 `中期.docx`。

## 2. 中期答辩 PPT（三个可编辑版本，挑一个用）

三版**内容一致**（同一份大纲 `docs/ppt_outline.json`），都是**原生可编辑 pptx**、全篇最小 **15 pt**、每页带演讲备注。

| 版本 | 文件 | 风格 |
|---|---|---|
| A 学术蓝 | `中期答辩.pptx` | 深蓝 + 青绿标签块，信息密度高 |
| B 极简线框 | `versions/中期答辩_B_极简线框.pptx` | 白底细线卡片、短下划线标题（**推荐首选**，投影最干净） |
| C 卡片色块 | `versions/中期答辩_C_卡片色块.pptx` | 顶部色带 + 左侧竖条 + 卡片底色块 |

改法与重出命令见 `versions/README.md`；版式预览图在 `../results/ppt_preview/`。

## 3. 拿到新版后

```powershell
.\sync.ps1
copy .\deliverable\中期.docx  E:\0zhongqi\        # 或复制到你想要的位置
copy .\deliverable\versions\中期答辩_B_极简线框.pptx E:\0zhongqi\
```
