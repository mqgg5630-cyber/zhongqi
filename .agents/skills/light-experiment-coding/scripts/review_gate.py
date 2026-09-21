#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_gate.py — 交付前安全 + 反模式静态扫描门（把人工 checklist 编译成可运行强制门）。

为什么有这个脚本（补 experiment-coding 最大的 claim-vs-code 缺口）
----------------------------------------------------
SKILL.md 与 CODE_REVIEW_CHECKLIST 把「不硬编码密钥/不回显敏感值/参数化查询/数据泄漏」列为
Critical，但口头清单零强制力——只写成给维护者读的人工清单，没有任何可运行 linter。通用安全
扫描器（bandit/ruff 的 flake8-bandit `S` 规则）查硬编码密钥/eval/SQL 等通用安全形态，**但都
不带 ML 数据泄漏（标准化早于 train/test 划分）这类科研特化检查**。本脚本把人工五查/红旗清单
编译成 AST + 正则扫描器，从「文字纪律」变成「强制门」——并补上通用 linter 不带的科研特化检查
（数据泄漏=fit 早于划分、浮点 == 断言）。它是 experiment-coding 的代码级（非数据件级）泄漏门。

检查项（Critical 命中→退出码 1，可挂 pre-commit / CI）
----------------------------------------------------
  Critical：硬编码密钥/token | eval/exec | shell=True / os.system | SQL 字符串拼接 |
            数据泄漏（StandardScaler.fit/fit_transform 早于 holdout/CV 划分）
  Important：裸 except（except: 无类型）| 浮点 == 断言（科研里应 assert_allclose）
  挂 _shared/findings_schema 出 light.findings.v1（producer=experiment-coding），
  被 orchestrator run_checkpoint --stage 6 聚合；也是 repro_gate 的 leakage/float/unsafe 信号源。

⚠ 诚实边界：AST + 正则启发式，**抓「形态硬错」，会漏报/误报**（如经过校验的动态 eval、有意的
  字符串 SQL；同 bandit B608 只抓 SQL 拼接形态、非污点流分析）；不替代人工 code review 与
  人/领域语义判断。每条命中给定位行号 + 修复方向。

用法：
  python review_gate.py path/to/*.py            # 扫文件
  python review_gate.py src/ --json             # 扫目录，输出 light.findings.v1
  python review_gate.py --selftest              # 离线合成坏代码自测
"""
from __future__ import annotations
import argparse
import ast
import json
import os
import pathlib
import re
import sys

# ── 挂接共享 findings 契约：规范 bootstrap（向上走目录树找含 _shared 包的仓库根）──
# 治 v1 硬编码 `../../_shared` 之脆：v2 的 _shared 在仓库根、与 skills/ 平级、脚本嵌套深度也变了，
# 硬编码必断。规范 bootstrap 不依赖深度，三 harness / 全局安装 / 任意嵌套都可靠（见 _shared/README.md）。
try:
    _r = pathlib.Path(__file__).resolve()
    while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
        _r = _r.parent
    if not (_r / "_shared" / "__init__.py").exists():
        raise ImportError("向上未找到 _shared 包目录（请确保脚本在 Light-Skills 树内）")
    sys.path.insert(0, str(_r))
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    _HAS_FINDINGS = True
except Exception:
    _HAS_FINDINGS = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 硬编码密钥：变量名暗示敏感 + 赋了非空字面量（排除占位/环境读取）
_SECRET_NAME = re.compile(r"(?:password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
                          r"private[_-]?key|aws_secret)", re.I)
_PLACEHOLDER = re.compile(r"^(?:|x+|\.+|<.*>|\{\{.*\}\}|your[_-].*|changeme|todo|none|null|example|\*+)$", re.I)
_AWS_AKIA = re.compile(r"AKIA[0-9A-Z]{16}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
# SQL 拼接：execute/cursor 调用里有 SQL 关键字 + 拼接迹象
_SQL_KW = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|WHERE)\b", re.I)
_PREPROC = re.compile(r"(scaler|normaliz|standardiz|minmax|encoder|imputer|pca|vectorizer|"
                      r"StandardScaler|MinMaxScaler|RobustScaler)", re.I)
_CV_SPLITTER = re.compile(
    r"(?:KFold|ShuffleSplit|LeaveOneOut|LeavePOut|PredefinedSplit|TimeSeriesSplit)$"
)


def _is_secret_value(node) -> bool:
    """赋值右侧是否像真密钥（非空、非占位、足够长，或匹配 AWS/PEM 形态）。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        v = node.value.strip()
        if _AWS_AKIA.search(v) or _PEM.search(v):
            return True
        if len(v) >= 6 and not _PLACEHOLDER.match(v) and not v.startswith("$") \
                and "os.environ" not in v and "getenv" not in v:
            return True
    return False


def _func_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def scan_source(source: str, filename: str = "<src>") -> list:
    """对一段源码做 AST + 正则扫描，返回 issues。语法错误也如实报（不静默吞）。"""
    issues = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [{"loc": f"{filename}:{e.lineno or 0}", "code": "SYNTAX-ERROR",
                 "severity": "important",
                 "msg": f"无法解析（语法错误：{e.msg}）——先修语法再扫。"}]
    lines = source.splitlines()

    # 收集 holdout/CV 边界与 preprocessor.fit 的行号，做数据泄漏顺序判定。
    # 先找已知 sklearn splitter 实例名，避免把普通 str.split() 误当实验划分。
    split_lines, fit_lines = [], []
    cv_splitters = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            if isinstance(value, ast.Call) and _CV_SPLITTER.search(_func_name(value)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                cv_splitters.update(t.id for t in targets if isinstance(t, ast.Name))

    for node in ast.walk(tree):
        # 硬编码密钥：赋值 / 关键字参数
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(_SECRET_NAME.search(n) for n in names) and _is_secret_value(node.value):
                issues.append({"loc": f"{filename}:{node.lineno}", "code": "HARDCODED-SECRET",
                               "severity": "critical",
                               "msg": f"疑似硬编码密钥（变量 {names}）——改从环境变量/密钥管理读取，绝不入库。"})
        if isinstance(node, ast.Call):
            fn = _func_name(node)
            # eval / exec
            if fn in ("eval", "exec"):
                issues.append({"loc": f"{filename}:{node.lineno}", "code": "EVAL-EXEC",
                               "severity": "critical",
                               "msg": f"使用 {fn}() ——任意代码执行风险，用显式解析/dispatch 替代。"})
            # os.system
            if fn == "system" and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                issues.append({"loc": f"{filename}:{node.lineno}", "code": "OS-SYSTEM",
                               "severity": "critical",
                               "msg": "os.system() ——命令注入风险，用 subprocess.run([...]) 列表参数、不走 shell。"})
            # shell=True
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    issues.append({"loc": f"{filename}:{node.lineno}", "code": "SHELL-TRUE",
                                   "severity": "critical",
                                   "msg": "subprocess(..., shell=True) ——命令注入风险，传列表参数并去掉 shell=True。"})
            # secret 作为关键字参数 token=\"...\"
            for kw in node.keywords:
                if kw.arg and _SECRET_NAME.search(kw.arg) and _is_secret_value(kw.value):
                    issues.append({"loc": f"{filename}:{node.lineno}", "code": "HARDCODED-SECRET",
                                   "severity": "critical",
                                   "msg": f"疑似硬编码密钥（参数 {kw.arg}=...）——改从环境变量读取。"})
            # 数据泄漏顺序：记录 split 与 preprocessor.fit 行号
            if fn in ("train_test_split", "cross_val_score", "cross_validate",
                      "cross_val_predict"):
                split_lines.append(node.lineno)
            if fn == "split" and isinstance(node.func, ast.Attribute):
                obj = node.func.value
                known_instance = isinstance(obj, ast.Name) and obj.id in cv_splitters
                direct_constructor = (
                    isinstance(obj, ast.Call)
                    and _CV_SPLITTER.search(_func_name(obj)) is not None
                )
                if known_instance or direct_constructor:
                    split_lines.append(node.lineno)
            if fn in ("fit", "fit_transform") and isinstance(node.func, ast.Attribute):
                obj = node.func.value
                obj_name = obj.id if isinstance(obj, ast.Name) else (
                    obj.attr if isinstance(obj, ast.Attribute) else "")
                if _PREPROC.search(obj_name) or _PREPROC.search(ast.dump(node.func)):
                    fit_lines.append(node.lineno)
        # 裸 except
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append({"loc": f"{filename}:{node.lineno}", "code": "BARE-EXCEPT",
                           "severity": "important",
                           "msg": "裸 except: ——会吞掉 KeyboardInterrupt/SystemExit 并掩盖真错，捕获具体异常类型。"})
        # 浮点 == 断言（Compare 含 Eq/NotEq 且一端是 float 字面量）
        if isinstance(node, ast.Compare):
            ops_eq = any(isinstance(o, (ast.Eq, ast.NotEq)) for o in node.ops)
            operands = [node.left] + list(node.comparators)
            has_float = any(isinstance(o, ast.Constant) and isinstance(o.value, float) for o in operands)
            if ops_eq and has_float:
                issues.append({"loc": f"{filename}:{node.lineno}", "code": "FLOAT-EQ",
                               "severity": "important",
                               "msg": "浮点数 == 比较 ——浮点有舍入误差，科研断言用 math.isclose/np.allclose/pytest.approx。"})

    # 数据泄漏：有 preprocessor.fit 出现在最早的 holdout/CV 划分之前
    if split_lines and fit_lines:
        earliest_split = min(split_lines)
        leaks = [ln for ln in fit_lines if ln < earliest_split]
        for ln in leaks:
            issues.append({"loc": f"{filename}:{ln}", "code": "DATA-LEAKAGE",
                           "severity": "critical",
                           "msg": f"标准化/编码器在第 {ln} 行 fit，早于第 {earliest_split} 行 holdout/CV 划分"
                                  f"——评估折统计泄漏进预处理（data leakage）；应先划分后仅在训练折 fit，"
                                  f"交叉验证优先用 sklearn Pipeline。"})

    # SQL 拼接（行级正则：execute/format/% 拼接 + SQL 关键字）
    for i, ln in enumerate(lines, 1):
        if _SQL_KW.search(ln) and ("execute(" in ln or "cursor" in ln.lower() or "query" in ln.lower()):
            if (" % " in ln or ln.count("+") >= 1 and '"' in ln) or ".format(" in ln \
                    or re.search(r'f["\'].*\{', ln):
                issues.append({"loc": f"{filename}:{i}", "code": "SQL-CONCAT",
                               "severity": "critical",
                               "msg": "SQL 字符串拼接（%/+/format/f-string）——SQL 注入风险，用参数化查询（占位符 + 参数元组）。"})
    return issues


def scan_paths(paths: list) -> dict:
    all_issues = []
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, fs in os.walk(p):
                files += [os.path.join(root, f) for f in fs if f.endswith(".py")]
        elif p.endswith(".py"):
            files.append(p)
    for fp in sorted(set(files)):
        try:
            with open(fp, encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            all_issues.append({"loc": fp, "code": "READ-ERROR", "severity": "important",
                               "msg": f"读取失败: {e}"})
            continue
        all_issues += scan_source(src, fp)
    by = {"critical": 0, "important": 0}
    for i in all_issues:
        by[i["severity"]] = by.get(i["severity"], 0) + 1
    return {"n_files": len(files), "n_issues": len(all_issues), "by_severity": by, "issues": all_issues}


# 本扫描器内部 severity → findings_schema 词表（important 非 findings 合法值，映射为 major）
_SEV_MAP = {"critical": "critical", "important": "major"}


def to_findings(rep: dict) -> dict:
    if not _HAS_FINDINGS:
        gates = [{"gate": i["code"], "status": "fail" if i["severity"] == "critical" else "warn",
                  "severity": _SEV_MAP.get(i["severity"], "minor"),
                  "findings": [{"loc": i["loc"], "issue": i["msg"], "fix": "", "rule": i["code"]}]}
                 for i in rep["issues"]]
        verdict = "fail" if rep["by_severity"].get("critical") else ("warn" if rep["issues"] else "pass")
        return {"schema": "light.findings.v1", "producer": "experiment-coding", "target": "code_diff",
                "verdict": verdict, "gates": gates, "summary": f"安全/反模式扫描:{rep['n_issues']}问题",
                "fresh_evidence": True, "_degraded": True}
    r = FindingsReport(producer="experiment-coding", target="code_diff", fresh_evidence=True,
                       summary=f"交付前安全+反模式扫描：{rep['n_files']}文件/{rep['n_issues']}问题")
    if not rep["issues"]:
        r.gates.append(GateResult("review_gate", "pass", "info"))
    for i in rep["issues"]:
        status = "fail" if i["severity"] == "critical" else "warn"
        r.gates.append(GateResult(i["code"], status, _SEV_MAP.get(i["severity"], "minor"),
                                  [Finding(i["loc"], i["msg"], rule=i["code"])]))
    return r.finalize().to_dict()


def to_markdown(rep: dict) -> str:
    lines = [f"# 交付前安全+反模式扫描 — {rep['n_files']} 文件，{rep['n_issues']} 问题"
             f"（critical={rep['by_severity'].get('critical',0)} important={rep['by_severity'].get('important',0)}）\n"]
    if not rep["issues"]:
        lines.append("✓ 未命中硬编码密钥/eval/shell=True/SQL 拼接/数据泄漏/裸except/浮点==。")
    for i in rep["issues"]:
        lines.append(f"- [{i['severity']}] {i['code']} @ {i['loc']}：{i['msg']}")
    lines.append("\n> AST+正则启发式，抓形态硬错，会漏/误报，不替代人工 review 与 人/领域语义判断。")
    return "\n".join(lines)


def _selftest() -> int:
    print("### review_gate 离线自测", file=sys.stderr)

    bad = '''
import os, subprocess
API_KEY = "sk-" "selftest-abcdef123456789"   # 硬编码密钥
def run(cmd):
    os.system("rm " + cmd)                     # os.system 命令注入
    subprocess.run(cmd, shell=True)            # shell=True
    eval("1+1")                                # eval
def q(db, uid):
    db.execute("SELECT * FROM u WHERE id=" + uid)   # SQL 拼接
def train(X, y):
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)               # 泄漏:fit 早于 split
    return train_test_split(Xs, y)
def check(loss):
    assert loss == 0.5                         # 浮点 ==
    try:
        pass
    except:                                    # 裸 except
        pass
'''
    rep = scan_source(bad, "bad.py")
    codes = {i["code"] for i in rep}
    print(to_markdown({"n_files": 1, "n_issues": len(rep),
                       "by_severity": {"critical": sum(1 for i in rep if i["severity"] == "critical"),
                                       "important": sum(1 for i in rep if i["severity"] == "important")},
                       "issues": rep}), file=sys.stderr)
    for need in ("HARDCODED-SECRET", "OS-SYSTEM", "SHELL-TRUE", "EVAL-EXEC",
                 "SQL-CONCAT", "DATA-LEAKAGE", "FLOAT-EQ", "BARE-EXCEPT"):
        assert need in codes, f"{need} 未命中: {codes}"
    print("[1] 八类坏模式全命中 ... OK", file=sys.stderr)

    cv_bad = '''
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
def train(X, y):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    return list(splitter.split(Xs, y))
'''
    cv_codes = {i["code"] for i in scan_source(cv_bad, "cv_bad.py")}
    assert "DATA-LEAKAGE" in cv_codes, f"CV fit 穿越未命中: {cv_codes}"
    print("[1b] CV splitter 前 fit 穿越命中 ... OK", file=sys.stderr)

    # 干净代码不误报
    good = '''
import os
api_key = os.environ["API_KEY"]               # 从环境读，不报
def run(cmd_list):
    import subprocess
    subprocess.run(cmd_list, check=True)       # 列表参数，无 shell
def q(db, uid):
    db.execute("SELECT * FROM u WHERE id=?", (uid,))   # 参数化
def train(X, y):
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    Xtr, Xte, ytr, yte = train_test_split(X, y)
    scaler = StandardScaler()
    Xtr = scaler.fit_transform(Xtr)            # split 之后 fit，正确
    return Xtr
def check(loss):
    import math
    assert math.isclose(loss, 0.5)             # 正确浮点比较
    try:
        pass
    except ValueError:
        pass
'''
    rg = scan_source(good, "good.py")
    assert not rg, f"干净代码不应报: {[i['code'] for i in rg]}"
    print("[2] 干净代码零误报（环境读密钥/参数化/split后fit/isclose/具名except）... OK", file=sys.stderr)

    # 占位符密钥不报
    ph = 'password = "changeme"\ntoken = "your-token-here"\nsecret = ""\n'
    assert not any(i["code"] == "HARDCODED-SECRET" for i in scan_source(ph)), "占位符不应报密钥"
    print("[3] 占位符/空值不误报密钥 ... OK", file=sys.stderr)

    # 语法错误如实报
    assert any(i["code"] == "SYNTAX-ERROR" for i in scan_source("def f(:\n")), "语法错应报"
    # findings 转换 + verdict
    f = to_findings({"n_files": 1, "n_issues": len(rep), "issues": rep,
                     "by_severity": {"critical": 5, "important": 2}})
    assert f["schema"] == "light.findings.v1" and f["verdict"] == "fail", f
    assert f["producer"] == "experiment-coding", f"producer 应为 experiment-coding: {f.get('producer')}"
    print("[4] 语法错报告 + findings verdict=fail + producer=experiment-coding ... OK", file=sys.stderr)

    print("[selftest] PASS review_gate offline")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="交付前安全+反模式扫描门")
    ap.add_argument("paths", nargs="*", help="要扫的 .py 文件或目录")
    ap.add_argument("--json", action="store_true", help="输出 light.findings.v1 JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest or not args.paths:
        return _selftest()
    rep = scan_paths(args.paths)
    print(json.dumps(to_findings(rep), ensure_ascii=False, indent=2) if args.json else to_markdown(rep))
    return 1 if rep["by_severity"].get("critical") else 0


if __name__ == "__main__":
    sys.exit(main())
