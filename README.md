# zhongqi

本仓库用于和 Arena 的编码会话同步代码。

> **工作分支（唯一需要你关注的分支）：`arena/01a09d79-zhongqi`**
>
> 仓库地址：<https://github.com/mqgg5630-cyber/zhongqi>
> 公开仓库，克隆不需要登录/密码。

---

## 一、第一次：把代码克隆到本地

你的本地目录是 `E:\0zhongqi`，里面已经有 `附件\` 文件夹，
**不要**直接克隆到 `E:\0zhongqi`（目录非空会报错），克隆到子目录即可：

```powershell
cd E:\0zhongqi
git clone -b arena/01a09d79-zhongqi https://github.com/mqgg5630-cyber/zhongqi.git zhongqi
```

克隆完后本地结构为：

```
E:\0zhongqi\
├── 附件\
│   ├── 中期.docx
│   └── 开题.docx
└── zhongqi\          <-- 克隆下来的代码仓库
    ├── README.md
    └── sync.ps1
```

> 如果之前已经克隆过一次，不用再克隆，直接做下面的「同步」即可。

---

## 二、以后每次：把分支最新代码同步到本地

### 方式 A：一条命令（推荐）

```powershell
cd E:\0zhongqi\zhongqi
.\sync.ps1
```

（如果提示脚本被禁止运行，先执行一次：
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`）

### 方式 B：手打 git 命令

```powershell
cd E:\0zhongqi\zhongqi
git fetch origin
git checkout arena/01a09d79-zhongqi
git pull --ff-only origin arena/01a09d79-zhongqi
```

同步完成后看最新提交，确认拉到了东西：

```powershell
git log -1 --stat
```

---

## 三、约定

1. Arena 会话里所有改动都会 **提交并推送到 `arena/01a09d79-zhongqi`**，
   所以你只要重复第二步就能拿到最新代码。
2. 你和 Arena 不要同时改同一个文件：你本地如果改了文件，先 `git stash`
   或提交后再 `sync.ps1`，避免 `pull` 冲突。
3. 你本地产生的临时文件（`~$*.docx`、`__pycache__`、`.venv` 等）已被
   `.gitignore` 忽略，不会污染仓库。
4. 需要我从 `开题.docx` / `中期.docx` 里取内容时，把文件复制到仓库里再推上来：

   ```powershell
   cd E:\0zhongqi\zhongqi
   copy ..\附件\开题.docx .\docs\
   copy ..\附件\中期.docx .\docs\
   git add .\docs
   git commit -m "add 开题/中期 文档"
   git push origin arena/01a09d79-zhongqi
   ```
