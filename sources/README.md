# sources —— 你的原件放这里

在仓库目录下运行 `.\upload.ps1` 会自动把相邻文件夹（如 `E:\0zhongqi\附件`）里的
docx / pptx / pdf / md / txt 复制到本目录，然后提交推送，不需要手动 copy。

也可以手动：

```powershell
cd E:\0zhongqi\zhongqi
copy ..\附件\*.docx .\sources\
.\push.ps1 "加入原件"
```

需要的文件：
- `开题.docx` —— 报告第 2、6 节和进度对照的事实来源
- `中期.docx` —— **学校模板**，我只在这份文件上就地填内容，保留其格式
- `已完成1.docx` —— 你这段时间已做的工作
- `1.md` / `1.py` —— 补充说明与实验脚本
- 后续：`中期答辩_A_学术蓝.pptx` … `_E_深色标题区.pptx`（五版）
