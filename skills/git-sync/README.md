# 本地同步脚本（skill）——使用说明

> 目标是让"取最新代码 / 把本地文件传上去"各只用一个命令，且**不依赖 git 知识**。
> 本仓库里配合 AI 助手的实际脚本就在仓库根目录：`sync.ps1`、`push.ps1`、`upload.ps1`；
> 这里放的是**通用版**（分支名可配），可以复制到其他项目重复使用。

## 一、最短用法（放在仓库根目录）

```powershell
.\sync.ps1      # 拉取：fetch + 切分支 + pull --ff-only（本地有改动会先 stash）
.\upload.ps1    # 上传：把旁边附件目录里的 docx/pptx/pdf/xlsx/py 归位后 commit + push
.\push.ps1 "提交说明"   # 只提交推送当前改动
```

## 二、通用版脚本

```
skills/git-sync/scripts/sync.ps1     # 拉取（参数 -Branch，默认当前分支）
skills/git-sync/scripts/push.ps1     # 提交推送（参数 -Message / -Branch）
```

复制到你的项目根目录即可：

```powershell
copy .\skills\git-sync\scripts\*.ps1 C:\MyProject\
```

如果你希望像本仓库一样做成"上传附件"的版本，可在 `push.ps1` 前加一段按扩展名归位的逻辑
（参考本仓库根目录的 `upload.ps1`）。

## 三、为什么脚本里绝对不能写中文

Windows PowerShell 5.1 读取没有 BOM 的 `.ps1` 时按 **GBK** 解码。UTF-8 的中文注释会被解成乱码，
一旦乱码里出现引号字符，就会把后面的字符串吃掉，报 `字符串缺少终止符` / `InvalidArgument`。
所以本仓库约定：**`.ps1` 文件只用 ASCII**，中文一律放在 `.md` 文档里；
仓库脚本用 `python code/check_ps1.py` 自动校验（会扫描全部 `.ps1`，含 `skills\` 下的）。

## 四、首次使用

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # 只做一次
# 首次 push 弹 GitHub 登录窗；若提示输密码，应填 token（或用 gh auth login / GitHub Desktop）
```

详细说明、分支配置与常见报错见 `SKILL.md`。
