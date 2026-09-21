#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""repro_gate.py — experiment-coding 的**数据泄漏 / 可复现 Critical 门 producer**。

蓝图 §4.3-6 的「及格线」:科研代码可复现优先于优雅。最让结果**不可信**的两类硬伤是
**数据泄漏**(测试集信息漏进训练 → 指标虚高)与**不可复现**(种子不全 → 换机/换次跑结果飘,
别人复跑不出同一个数)。本脚本把这两点编排成机读 `light.findings.v1`(producer=**experiment-coding**),
**有泄漏 / 种子不全 → critical fail** → 被总控 `run_checkpoint --stage 6` 聚合 **exit 1**。
门名对齐 `STAGE_GATES[6]=[leakage, reproducible]`。**浮点==断言 = warn**(spec §4.2);**安全/反
模式 = warn**(在研究检查点不阻断 DAG;交付硬阻断由 `review_gate.py` 独立 pre-commit 门负责)。

这是 **v2 净新增的接线**(与 research-plan `plan_gate`、data-engineering `data_feasibility_gate`、
idea 侧 `fatal_flaw_gate` 同构):**编排港来/复用的纯工具 + 接 `_shared` 规范 bootstrap → critical
findings producer**,不重造任何检测逻辑——
  - reproducible:复用本目录 `seed_audit.py`(种子覆盖度静态机检,v2 净新增灵魂);
  - leakage(代码级):复用本目录港来的 `review_gate.py` 的 DATA-LEAKAGE(fit 早于划分);
  - leakage(数据件级):**直接复用 data-engineering 的 `split_leakage.py`**(行/实体/近重/目标编码穿越,
    `STAGE_GATES[6]` 引的 leakage 标准件,**不重造**)——给了产物 train/test 才跑,缺 pandas 优雅降级;
  - float_assert / unsafe_scan:复用 `review_gate.py` 的 FLOAT-EQ / 安全反模式。

与 data-engineering 泄漏门的分工(诚实):data-engineering `split_leakage` 是**划分阶段**查数据件泄漏;
experiment-coding 是**代码落地阶段**查泄漏——既扫**代码**里 fit 穿越(review_gate),又可**复跑**
split_leakage 复核代码真产出的 split(防代码 bug 引入新泄漏)。**该复用就复用,不重造。**

回炉语义(spec §5):experiment-coding **自身门 fail = 改代码,在 stage 6 内修复**(**无 `ROUTES[6]`
出边**);它是 **7→6**(result-analysis 判不可复现/bug)的**回炉落点**——那条由总控 `reroute --stage 7`
命中 `ROUTES[7]`(信号 reproduc/repro/bug/seed/种子/复现)建议、`passport add-back-edge --to 6` 落账。

四个 gate:
  ① leakage(数据泄漏,**critical**):代码里 fit/fit_transform 早于 train_test_split(review_gate),
     或给定产物 split 经 split_leakage 检出 HIGH(精确重复/实体重叠/目标编码穿越)→ critical。MED→warn。
  ② reproducible(可复现,**critical**):seed_audit 按实际框架核查种子覆盖,缺 critical 机制
     (PYTHONHASHSEED/框架种子/cuDNN deterministic/DataLoader worker——★最常漏)→ critical;
     委托未扫描 helper 的缺失 → warn;无随机性 → skip。
  ③ float_assert(浮点==断言,**warn**):浮点字面量参与 == 断言(应 isclose/assert_allclose/approx)。
  ④ unsafe_scan(安全/反模式,**warn**):硬编码密钥/eval/shell/SQL 拼接/裸 except(review_gate)。
     **在研究检查点是 warn**(不阻断 DAG);**交付阶段请跑 `review_gate.py` 独立门**(那里这些是 critical→exit 1)。

诚实约定(名实对齐见 SKILL,铁律 2):
- **静态扫描有边界**:查「有没有设种子 / 代码里有没有 fit 穿越」,**绝不"证明了无泄漏 / 绝对可复现"**——
  可复现的**终判 = 同种子真跑两次结果一致**;泄漏的终判仍需人/领域判断(合法组统计可能误命中)。
- **委托式播种不误报**(seed_audit):调 set_global_seed 类 helper 而 helper 未纳入扫描 → 缺失降级 warn。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  python repro_gate.py --spec repro_spec.json --report repro_findings.json
  python repro_gate.py --selftest

spec JSON 形如:
  {"project":"goat-estrus",
   "code":"<内联实验源码>",                       # 或
   "code_files":["src/train.py","src/model.py"],  # 训练代码路径(seed_audit 取并集;review_gate 逐个扫)
   "leakage":{"train":"data/train.csv","test":"data/test.csv",
              "group_col":"user_id","target":"y"}}  # 可选:复用 split_leakage 复核产物 split
"""

from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 同目录港来/新建的纯工具(复用不重造)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import seed_audit as sa  # noqa: E402  种子覆盖度静态机检(v2 净新增)
import review_gate as rg  # noqa: E402  安全/反模式 + 代码级数据泄漏(fit 早于划分)+ 浮点==

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates  # noqa: E402

    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False

# 跨技能复用 data-engineering 的数据件级泄漏门(不重造);缺 pandas / 路径不在树内 → 优雅降级。
_DE_SCRIPTS = _ROOT / "skills" / "light-data-engineering" / "scripts"
try:
    if _DE_SCRIPTS.is_dir():
        sys.path.insert(0, str(_DE_SCRIPTS))
    import split_leakage as sl  # noqa: E402

    _HAS_SL = True
except Exception:
    _HAS_SL = False


# ───────────────────────── 收集代码 / 产物证据 ─────────────────────────
def gather_code(spec: dict) -> list[tuple[str, str]]:
    """汇集要扫的 (filename, source):内联 code 优先,叠加 code_files 路径。"""
    out = []
    if spec.get("code"):
        out.append((spec.get("code_name", "<inline>"), spec["code"]))
    for p in spec.get("code_files", []) or []:
        try:
            out.append((p, pathlib.Path(p).read_text(encoding="utf-8")))
        except OSError as e:
            out.append((p, f"# READ-ERROR {e}\n"))
    return out


def scan_review(sources: list[tuple[str, str]]) -> list[dict]:
    """逐文件跑 review_gate.scan_source,汇总 issues(带 code/severity/loc/msg)。"""
    issues = []
    for fn, src in sources:
        issues += rg.scan_source(src, fn)
    return issues


def run_split_leakage(spec_leak: dict) -> dict | None:
    """复用 split_leakage 复核产物 split。返回 {rows, available, reason}。"""
    if not spec_leak:
        return None
    if not _HAS_SL:
        return {
            "rows": [],
            "available": False,
            "reason": "split_leakage 不可用(缺 pandas 或不在 Light-Skills 树内)——代码级泄漏门仍生效。",
        }

    class _A:  # 模拟 split_leakage 的 argparse.Namespace
        train = spec_leak.get("train")
        test = spec_leak.get("test")
        csv = spec_leak.get("csv")
        split_col = spec_leak.get("split_col")
        cols = spec_leak.get("cols")
        group_col = spec_leak.get("group_col")
        target = spec_leak.get("target")
        bins = int(spec_leak.get("bins", 20))
        rtol = float(spec_leak.get("rtol", 1e-3))

    try:
        combined, split_values = sl.load_combined(_A)
        feature_cols = sl.pick_feature_cols(combined, _A)
        rows = sl.build_findings(combined, feature_cols, _A, split_values)
        return {"rows": rows, "available": True, "reason": ""}
    except Exception as e:  # 文件缺失/列名错等如实报,不静默
        return {"rows": [], "available": False, "reason": f"split_leakage 复核失败:{e}"}


# ───────────────────────── 四个 gate 函数(接 _shared) ─────────────────────────
_REVIEW_LEAK = {"DATA-LEAKAGE"}
_REVIEW_FLOAT = {"FLOAT-EQ"}
_REVIEW_UNSAFE = {
    "HARDCODED-SECRET",
    "OS-SYSTEM",
    "SHELL-TRUE",
    "EVAL-EXEC",
    "SQL-CONCAT",
    "BARE-EXCEPT",
    "SYNTAX-ERROR",
    "READ-ERROR",
}


def _leakage_gate_fn(art: dict) -> "GateResult":
    """数据泄漏门(critical):代码级 fit 穿越(review_gate)+ 数据件级 split_leakage HIGH。"""
    loc = f"{art['project']}:leakage"
    has_code = art["has_code"]
    sl_res = art["sl"]
    if not has_code and not (sl_res and sl_res.get("available")):
        return GateResult(
            "leakage",
            "skip",
            "info",
            [],
            note="未提供训练代码,也未提供产物 split:数据泄漏门跳过。",
        )
    crit, warns = [], []
    # 代码级:review_gate 的 DATA-LEAKAGE
    for i in art["review"]:
        if i["code"] in _REVIEW_LEAK:
            crit.append(
                Finding(
                    loc=i["loc"],
                    issue=i["msg"],
                    fix="先 train_test_split 再仅在训练折 fit;交叉验证用 Pipeline 把预处理装进 CV 内",
                    rule="leakage.fit_before_split",
                )
            )
    # 数据件级:split_leakage 复核产物(HIGH=critical, MED=warn)
    if sl_res and sl_res.get("available"):
        for r in sl_res["rows"]:
            f = Finding(
                loc=",".join(r.get("columns", [])) or "(rows)",
                issue=r["detail"],
                fix="去重/按实体重划分/目标编码移入 CV 内(复用 data-engineering split_leakage)",
                rule=f"leakage.{r['check']}",
            )
            (crit if r["severity"] == "HIGH" else warns).append(f)
    elif sl_res and not sl_res.get("available") and sl_res.get("reason"):
        warns.append(
            Finding(
                loc=loc,
                issue=sl_res["reason"],
                fix="装 pandas 或把脚本放回 Light-Skills 树内,以复用 split_leakage 复核产物",
                rule="leakage.split_check_unavailable",
            )
        )
    if crit:
        return GateResult(
            "leakage",
            "fail",
            "critical",
            crit,
            note="检出数据泄漏(critical):测试集信息漏进训练 → 指标虚高,结论不可信,在 stage 6 内修复。",
        )
    if warns:
        return GateResult(
            "leakage",
            "warn",
            "major",
            warns,
            note="数据泄漏疑点(warn,可能巧合/合法组统计):人工核对来源。",
        )
    return GateResult(
        "leakage",
        "pass",
        "info",
        [],
        note="未检出代码级 fit 穿越 / 产物 split 泄漏(静态+数据件层面;终判仍需人/领域判断)。",
    )


def _reproducible_gate_fn(art: dict) -> "GateResult":
    """可复现门(种子不全=critical):seed_audit 按实际框架核查种子覆盖。"""
    loc = f"{art['project']}:reproducible"
    if not art["has_code"]:
        return GateResult(
            "reproducible", "skip", "info", [], note="未提供训练代码:种子覆盖检查跳过。"
        )
    rep = art["seed"]
    if not rep["has_randomness"]:
        return GateResult(
            "reproducible",
            "skip",
            "info",
            [],
            note="未检出 random/numpy/torch/tf 用法:无随机性需固定(或随机性藏在未 import 的三方库,GIGO)。",
        )
    crit = [m for m in rep["missing"] if m["severity"] == "critical"]
    warn = [m for m in rep["missing"] if m["severity"] == "warn"]
    if crit:
        detail = "；".join(f"{m['mechanism']}(应:{m['fix']})" for m in crit)
        return GateResult(
            "reproducible",
            "fail",
            "critical",
            [
                Finding(
                    loc=loc,
                    issue=f"随机种子不全 → 不可复现(critical):缺 {detail}",
                    fix="在训练入口最早处一次性设全所有种子(见 reproducibility-checklist + set_global_seed)",
                    evidence=f"用到框架={','.join(rep['frameworks'])};GPU迹象={rep['uses_gpu']};"
                    f"DataLoader={rep['uses_dataloader']}",
                    rule="reproducible.incomplete_seed",
                )
            ],
            note="种子不全 = 不可复现 = critical(spec §4.2):换机/换次跑结果会飘,别人复跑不出同一个数。",
        )
    if warn:
        detail = "；".join(m["mechanism"] for m in warn)
        return GateResult(
            "reproducible",
            "warn",
            "major",
            [
                Finding(
                    loc=loc,
                    issue=f"种子可能由未扫描的 set_global_seed 类 helper 设置(缺:{detail})",
                    fix="把该 helper 文件一并纳入扫描(--code_files),以按真覆盖判定",
                    rule="reproducible.delegated_unscanned",
                )
            ],
            note="委托式播种未核实(warn):把 helper 一并扫描即可确认。",
        )
    return GateResult(
        "reproducible",
        "pass",
        "info",
        [],
        note=f"种子覆盖齐({','.join(rep['set'])});终判仍需同种子真跑两次比对。",
    )


def _float_assert_gate_fn(art: dict) -> "GateResult":
    """浮点==断言门(warn,spec §4.2):浮点字面量参与 == 断言应改 isclose/assert_allclose。"""
    if not art["has_code"]:
        return GateResult(
            "float_assert", "skip", "info", [], note="未提供训练代码:浮点==检查跳过。"
        )
    hits = [i for i in art["review"] if i["code"] in _REVIEW_FLOAT]
    if hits:
        return GateResult(
            "float_assert",
            "warn",
            "major",
            [
                Finding(
                    loc=i["loc"],
                    issue=i["msg"],
                    fix="改 math.isclose / numpy.testing.assert_allclose(rtol=...) / pytest.approx",
                    rule="float_assert.eq",
                )
                for i in hits
            ],
            note="浮点 == 断言(warn,spec §4.2):浮点有舍入误差,断言用容差比较。",
        )
    return GateResult("float_assert", "pass", "info", [], note="未检出浮点 == 断言。")


def _unsafe_scan_gate_fn(art: dict) -> "GateResult":
    """安全/反模式门(warn):硬编码密钥/eval/shell/SQL/裸except。研究检查点 warn;交付硬门见 review_gate.py。"""
    if not art["has_code"]:
        return GateResult(
            "unsafe_scan",
            "skip",
            "info",
            [],
            note="未提供训练代码:安全/反模式扫描跳过。",
        )
    hits = [i for i in art["review"] if i["code"] in _REVIEW_UNSAFE]
    if hits:
        return GateResult(
            "unsafe_scan",
            "warn",
            "major",
            [
                Finding(
                    loc=i["loc"],
                    issue=i["msg"],
                    fix="见 review_gate 提示",
                    rule=f"unsafe.{i['code']}",
                )
                for i in hits
            ],
            note="安全/反模式命中(在研究检查点为 warn;交付前请跑 review_gate.py 独立门,那里为 critical→exit 1)。",
        )
    return GateResult(
        "unsafe_scan",
        "pass",
        "info",
        [],
        note="未检出硬编码密钥/eval/shell/SQL 拼接/裸 except。",
    )


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装数据泄漏/可复现 critical findings:seed_audit + review_gate + split_leakage → 四 gate。"""
    project = str(spec.get("project", "unnamed"))
    sources = gather_code(spec)
    has_code = bool(sources)
    seed_rep = (
        sa.audit(sources)
        if has_code
        else {
            "has_randomness": False,
            "missing": [],
            "frameworks": [],
            "set": [],
            "uses_gpu": False,
            "uses_dataloader": False,
            "missing_critical": [],
        }
    )
    review = scan_review(sources) if has_code else []
    sl_res = run_split_leakage(spec.get("leakage"))
    art = {
        "project": project,
        "has_code": has_code,
        "seed": seed_rep,
        "review": review,
        "sl": sl_res,
    }

    report = None
    if _SHARED_OK:
        report = run_gates(
            [
                _leakage_gate_fn,
                _reproducible_gate_fn,
                _float_assert_gate_fn,
                _unsafe_scan_gate_fn,
            ],
            art,
            producer="experiment-coding",
            target=project,
            summary="experiment-coding 代码门:数据泄漏 + 可复现(种子)critical + 浮点==/安全反模式 warn → "
            "泄漏/种子不全 → run_checkpoint --stage 6 exit 1(在 stage 6 内修复,无出边);"
            "experiment-coding 是 7→6 回炉落点。",
            fresh_evidence=True,
        )
    return {
        "project": project,
        "seed": seed_rep,
        "review_issues": review,
        "split_leakage": sl_res,
        "has_code": has_code,
        "findings": report.to_dict() if report else None,
        "findings_available": _SHARED_OK,
    }


def to_markdown(result: dict) -> str:
    lines = [f"# experiment-coding 代码门(数据泄漏/可复现):{result['project']}", ""]
    # reproducible
    sr = result["seed"]
    lines += ["## 可复现 (reproducible, critical)", ""]
    if not result["has_code"]:
        lines.append("- (未提供训练代码 → skip)")
    elif not sr.get("has_randomness"):
        lines.append("- (未检出随机框架用法 → skip)")
    else:
        lines.append(
            f"- 用到框架:{', '.join(sr['frameworks'])} | GPU迹象={sr['uses_gpu']} "
            f"DataLoader={sr['uses_dataloader']}"
        )
        lines.append(f"- 已设种子:{', '.join(sr['set']) or '(无)'}")
        if sr["missing"]:
            for m in sr["missing"]:
                lines.append(
                    f"- ✗ 缺 {m['mechanism']}(**{m['severity']}**)→ {m['fix']}"
                )
        else:
            lines.append("- ✅ 种子覆盖齐(静态层面)")
    # leakage
    lines += ["", "## 数据泄漏 (leakage, critical)", ""]
    leaks = [i for i in result["review_issues"] if i["code"] == "DATA-LEAKAGE"]
    if leaks:
        for i in leaks:
            lines.append(f"- ✗ 代码级 fit 穿越 @ {i['loc']}")
    sl_res = result.get("split_leakage")
    if sl_res and sl_res.get("available"):
        highs = [r for r in sl_res["rows"] if r["severity"] == "HIGH"]
        lines.append(
            f"- 产物 split 复核(split_leakage):HIGH {len(highs)} / 共 {len(sl_res['rows'])} 项"
        )
    elif sl_res and sl_res.get("reason"):
        lines.append(f"- (产物 split 复核未跑:{sl_res['reason']})")
    if not leaks and not (sl_res and sl_res.get("available") and sl_res["rows"]):
        lines.append("- ✅ 未检出代码级 fit 穿越 / 产物 split 泄漏")
    # findings
    if result.get("findings"):
        f = result["findings"]
        lines += [
            "",
            f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=experiment-coding);"
            f"run_checkpoint --stage 6 聚合,泄漏/种子不全→critical fail→exit 1"
            f"(在 stage 6 内修复;experiment-coding 是 7→6 回炉落点)。",
        ]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
# 全种子覆盖 + split 之后 fit + isclose(干净代码)
_CLEAN = """
import os, random
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

def main(X, y, seed=42):
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    Xtr, Xte, ytr, yte = train_test_split(X, y, random_state=seed)
    scaler = StandardScaler(); Xtr = scaler.fit_transform(Xtr); Xte = scaler.transform(Xte)
    import math
    assert math.isclose(float(ytr[0]), 1.0, rel_tol=1e-6)
    return Xtr
"""

# 种子不全(漏 PYTHONHASHSEED) + fit 早于 split(泄漏) + 浮点==(warn) + 硬编码密钥(unsafe warn)
_BAD = """
import numpy as np
import torch
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

API_KEY = "sk-" "selftest-abcdef123456789"

def main(X, y, seed=42):
    np.random.seed(seed); torch.manual_seed(seed)     # 漏 PYTHONHASHSEED
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)                       # fit 早于 split → 泄漏
    Xtr, Xte, ytr, yte = train_test_split(Xs, y)
    assert ytr[0] == 0.5                               # 浮点 ==
    return Xtr
"""


def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 干净代码 → 全 pass(无 critical)
    r1 = build({"project": "p1", "code": _CLEAN})
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(
            f1["producer"] == "experiment-coding",
            f"producer 应 experiment-coding,得 {f1['producer']}",
        )
        names = {g["gate"] for g in f1["gates"]}
        check(
            {"leakage", "reproducible"} <= names,
            f"门名应含 STAGE_GATES[6] 的 leakage/reproducible,得 {names}",
        )
        check(f1["verdict"] == "pass", f"干净代码应整体 pass,得 {f1['verdict']}")

    # 2. 种子不全 + fit 穿越 + 浮点== + 硬编码密钥 → leakage & reproducible 双 critical → verdict fail
    r2 = build({"project": "p2", "code": _BAD})
    if _SHARED_OK:
        f2 = r2["findings"]
        check(f2["verdict"] == "fail", f"坏代码应整体 fail,得 {f2['verdict']}")
        lk = next(g for g in f2["gates"] if g["gate"] == "leakage")
        rp = next(g for g in f2["gates"] if g["gate"] == "reproducible")
        check(
            lk["status"] == "fail" and lk["severity"] == "critical",
            "fit 穿越应 leakage critical",
        )
        check(
            rp["status"] == "fail" and rp["severity"] == "critical",
            "漏 PYTHONHASHSEED 应 reproducible critical",
        )
        fl = next(g for g in f2["gates"] if g["gate"] == "float_assert")
        check(
            fl["status"] == "warn" and fl["severity"] != "critical",
            "浮点==应 warn 非 critical",
        )
        us = next(g for g in f2["gates"] if g["gate"] == "unsafe_scan")
        check(
            us["status"] == "warn" and us["severity"] != "critical",
            "硬编码密钥在研究检查点应 warn(交付门 review_gate 才 critical)",
        )
        rep = FindingsReport.from_json(json.dumps(f2, ensure_ascii=False))
        check(
            rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1,
            "findings 应可往返且有阻断 gate",
        )

    # 3. 只漏种子(无泄漏无浮点)→ 仅 reproducible critical
    only_seed = """
import numpy as np
def main(seed=42):
    np.random.seed(seed)       # 漏 PYTHONHASHSEED
    return np.random.rand(3)
"""
    r3 = build({"project": "p3", "code": only_seed})
    if _SHARED_OK:
        f3 = r3["findings"]
        rp3 = next(g for g in f3["gates"] if g["gate"] == "reproducible")
        lk3 = next(g for g in f3["gates"] if g["gate"] == "leakage")
        check(
            rp3["status"] == "fail" and rp3["severity"] == "critical",
            "应 reproducible critical",
        )
        check(
            lk3["status"] in ("skip", "pass"),
            f"无泄漏迹象 leakage 应 skip/pass,得 {lk3['status']}",
        )
        check(f3["verdict"] == "fail", "仅种子不全也应 fail(critical)")

    # 4. 无代码无产物 → 门 skip(不静默当 pass)
    r4 = build({"project": "p4"})
    if _SHARED_OK:
        f4 = r4["findings"]
        lk4 = next(g for g in f4["gates"] if g["gate"] == "leakage")
        rp4 = next(g for g in f4["gates"] if g["gate"] == "reproducible")
        check(lk4["status"] == "skip" and rp4["status"] == "skip", "无输入应双 skip")

    # 5. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 6. markdown 不崩
    check("代码门" in to_markdown(r2), "markdown 应含代码门标题")

    if failures:
        print("[SELFTEST][repro_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print(
        "[SELFTEST][repro_gate] OK:干净 pass / fit穿越+种子不全 双 critical fail / 仅种子不全 fail / "
        "浮点==&安全 warn / 无输入 skip / findings(experiment-coding) 往返"
        + ("" if _SHARED_OK else "(_shared 不可达,走诚实降级)")
        + "。"
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="experiment-coding 数据泄漏/可复现 Critical 门 producer(泄漏/种子不全→critical→stage 6 内修复)"
    )
    ap.add_argument("--spec", help="repro_spec JSON(project/code(_files)/leakage)")
    ap.add_argument(
        "--report", default="", help="把 light.findings.v1 写到该 JSON 路径"
    )
    ap.add_argument("--json-out", default="", help="把完整代码门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.spec:
        ap.error("需要 --spec repro_spec.json(或 --selftest)")

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    result = build(spec)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[JSON] 完整代码门 → {args.json_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print(
                "[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr
            )
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                f"[REPORT] light.findings.v1 → {args.report}"
                f"(verdict={result['findings']['verdict']})",
                file=sys.stderr,
            )
    sys.exit(
        1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0
    )


if __name__ == "__main__":
    main()
