#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_leakage.py — train/test 行级·实体级·近重复 泄漏审计（纯 pandas）。

【data-engineering 的数据泄漏 Critical 门 producer】：本脚本是 stage 2 的 leakage 机读门——
产 light.findings.v1（producer=data-engineering，HIGH→critical）→ 总控 run_checkpoint --stage 2
聚合 → critical fail exit 1 确定性阻断。输出名 `leak_findings.json` 即 run_checkpoint STAGE_GATES[2]
引用的标准件。对齐 Kapoor-Narayanan(2207.07048) 8 类泄漏里可机检的几类、Deepchecks train_test_validation。

补 data-engineering 泄漏防护的最后一块拼图：
  - safe_split.py 防的是 **fit 穿越**（预处理在划分前对全量拟合）；
  - drift_check.py 比的是 **分布**（train/test 是否同分布）；
  - 二者都发现不了"**同一/近似样本同时落进 train 和 test**"这类污染——
    原始数据里重复行被分到两个 split，会让评测指标虚高（模型在测试集见过原题）。
    这正是 Deepchecks train_test_validation 明确覆盖、Light 此前缺的一类泄漏。

四类检查（HIGH=直接污染，MED=需人工复核）：
  (a) 跨 split **精确重复行**：特征列完全相同的行同时出现在 ≥2 个 split（HIGH）。
  (b) 跨 split **近重复行**：数值列分箱 + 类别列原值 的指纹相同（MED，可能巧合）。
  (c) **实体重叠**（--group-col）：同一实体（用户/患者/牧场）跨 split（HIGH，复用 SPLIT-02 概念）。
  (d) **目标编码式泄漏**（可选，--target）：某数值特征在某类别列各水平内近乎常量，
      且该常量≈用 **全量(含 test)** 算的该水平目标均值——典型 target-mean-encoding 穿越（HIGH/MED）。

输入两种模式（其一）：
  - 双文件：--train train.csv --test test.csv
  - 单文件带 split 列：--csv data.csv --split-col split   （支持 ≥2 个 split 值，按"特征跨 ≥2 split"判定）

输出：
  - leak_audit.md（HIGH/MED 分级报告）
  - findings.json（挂 _shared/findings_schema 的 light.findings.v1；不可用时优雅降级为
    {check,severity,columns,detail} 列表，绝不静默假成功）。每条 finding 额外带机读 columns 数组。
  - 任一 HIGH（critical）→ 退出码 1，可当 CI 数据门禁 / stage 2 数据泄漏 critical 门（run_checkpoint --stage 2 聚合）。

纯 pandas/numpy，无网络。selftest 造"10 行同时塞进两 split + 实体重叠 + 目标编码列"验证全部命中。

用法：
  python split_leakage.py --train train.csv --test test.csv --group-col user_id --target y --out leak_audit.md
  python split_leakage.py --csv data.csv --split-col split
  python split_leakage.py --selftest
"""

from __future__ import annotations
import argparse
import io
import json
import os
import pathlib
import sys

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 挂接共享 findings 契约：规范 bootstrap（向上走目录树找含 _shared 包的仓库根）──
# 治 v1 硬编码 `../../_shared` 之脆：v2 的 _shared 在仓库根、与 skills/ 平级，脚本嵌套深度也变了，
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

SPLIT = "__split__"  # 内部统一的 split 标记列名（避免撞用户列名）


# ---------------------------------------------------------------- 数据装载
def load_combined(args) -> tuple[pd.DataFrame, list[str]]:
    """把两种输入模式统一成一份带 SPLIT 列的 combined 表。返回 (combined, split_values)。"""
    if args.train and args.test:
        tr = pd.read_csv(args.train)
        te = pd.read_csv(args.test)
        tr = tr.assign(**{SPLIT: "train"})
        te = te.assign(**{SPLIT: "test"})
        combined = pd.concat([tr, te], ignore_index=True)
        return combined, ["train", "test"]
    if args.csv and args.split_col:
        df = pd.read_csv(args.csv)
        if args.split_col not in df.columns:
            raise ValueError(
                f"--split-col '{args.split_col}' 不在列中：{list(df.columns)}"
            )
        df = df.rename(columns={args.split_col: SPLIT})
        vals = sorted(map(str, df[SPLIT].dropna().unique()))
        if len(vals) < 2:
            raise ValueError(
                f"split 列只有 {len(vals)} 个取值，无法做跨 split 泄漏检查"
            )
        df[SPLIT] = df[SPLIT].astype(str)
        return df, vals
    raise ValueError("请提供 --train+--test 或 --csv+--split-col")


def pick_feature_cols(combined: pd.DataFrame, args) -> list[str]:
    """特征列 = 全列 - {SPLIT, group_col, target}（除非 --cols 显式指定）。"""
    if args.cols:
        want = [c.strip() for c in args.cols.split(",")]
        missing = [c for c in want if c not in combined.columns]
        if missing:
            raise ValueError(f"--cols 指定的列不存在：{missing}")
        return want
    drop = {SPLIT}
    if args.group_col:
        drop.add(args.group_col)
    if args.target:
        drop.add(args.target)
    return [c for c in combined.columns if c not in drop]


# ---------------------------------------------------------------- 检查 a：精确重复
def check_exact_dup(combined: pd.DataFrame, feature_cols: list[str]) -> dict:
    """特征列完全相同的行跨 ≥2 个 split 即精确重复污染。用 groupby+transform(nunique) 统一处理 N 个 split。"""
    if not feature_cols:
        return {"hit": False, "n_rows": 0, "n_keys": 0, "cols": []}
    nsplit = combined.groupby(feature_cols, dropna=False)[SPLIT].transform("nunique")
    mask = nsplit > 1
    n_rows = int(mask.sum())
    n_keys = (
        int(combined.loc[mask, feature_cols].drop_duplicates().shape[0])
        if n_rows
        else 0
    )
    return {
        "hit": n_rows > 0,
        "n_rows": n_rows,
        "n_keys": n_keys,
        "cols": feature_cols,
        "mask": mask,
    }


# ---------------------------------------------------------------- 检查 b：近重复
def _fingerprint(
    combined: pd.DataFrame, feature_cols: list[str], bins: int
) -> pd.DataFrame:
    """数值列按分位分箱成 bin 码、类别列取原值字符串，构成近重复指纹。"""
    fp = pd.DataFrame(index=combined.index)
    for c in feature_cols:
        s = combined[c]
        if pd.api.types.is_numeric_dtype(s):
            x = s.to_numpy(dtype="float64", na_value=np.nan)
            finite = x[np.isfinite(x)]
            if finite.size and np.unique(finite).size > 1:
                qs = np.unique(np.quantile(finite, np.linspace(0, 1, bins + 1)))
                qs[0], qs[-1] = -np.inf, np.inf
                codes = np.digitize(x, qs[1:-1], right=False).astype("float64")
                codes[~np.isfinite(x)] = -1  # NaN 自成一箱
                fp[c] = codes
            else:
                fp[c] = 0.0
        else:
            fp[c] = s.astype(str)
    return fp


def check_near_dup(
    combined: pd.DataFrame, feature_cols: list[str], exact_mask, bins: int = 20
) -> dict:
    """近重复 = 指纹相同跨 ≥2 split，但**排除已是精确重复**的行（只报"近而不精确"）。"""
    if not feature_cols:
        return {"hit": False, "n_rows": 0, "cols": []}
    fp = _fingerprint(combined, feature_cols, bins)
    fp[SPLIT] = combined[SPLIT].values
    nsplit = fp.groupby(feature_cols, dropna=False)[SPLIT].transform("nunique")
    near_mask = (nsplit > 1) & (~exact_mask)
    n_rows = int(near_mask.sum())
    return {"hit": n_rows > 0, "n_rows": n_rows, "cols": feature_cols, "bins": bins}


# ---------------------------------------------------------------- 检查 c：实体重叠
def check_group_overlap(combined: pd.DataFrame, group_col: str) -> dict:
    """同一实体（group 值）跨 ≥2 split 即实体泄漏（SPLIT-02）。"""
    if group_col not in combined.columns:
        raise ValueError(
            f"--group-col '{group_col}' 不在列中：{list(combined.columns)}"
        )
    nsplit = combined.groupby(group_col, dropna=False)[SPLIT].transform("nunique")
    mask = nsplit > 1
    n_rows = int(mask.sum())
    bad_entities = combined.loc[mask, group_col].dropna().unique().tolist()
    return {
        "hit": n_rows > 0,
        "n_rows": n_rows,
        "n_entities": len(bad_entities),
        "entities": bad_entities[:20],
        "col": group_col,
    }


# ---------------------------------------------------------------- 检查 d：目标编码式泄漏
def check_target_encoding(
    combined: pd.DataFrame, feature_cols: list[str], target: str, rtol: float = 1e-3
) -> dict:
    """目标编码穿越签名：数值特征 f 在某类别列 c 各水平内近乎常量，
    且该常量≈用全量(含 test)算的该水平 target 均值 → f 很可能是用 test 一起算的 target 编码。
    保守：要求 ≥2 个水平命中且 f 水平内方差极小。诚实：合法的组统计也可能命中，须人工核对来源。"""
    if target not in combined.columns:
        raise ValueError(f"--target '{target}' 不在列中：{list(combined.columns)}")
    y = pd.to_numeric(combined[target], errors="coerce")
    if y.notna().sum() == 0:
        return {"hit": False, "suspects": []}
    cat_cols = [
        c
        for c in feature_cols
        if not pd.api.types.is_numeric_dtype(combined[c]) or combined[c].nunique() <= 20
    ]
    num_cols = [
        c
        for c in feature_cols
        if pd.api.types.is_numeric_dtype(combined[c]) and combined[c].nunique() > 2
    ]
    suspects = []
    for c in cat_cols:
        lvl_y = y.groupby(combined[c]).mean()  # 全量(含 test) 的水平目标均值
        for f in num_cols:
            if f == c:
                continue
            grp = combined.groupby(c)[f]
            within_std = grp.std(ddof=0).fillna(0.0)
            lvl_f = grp.mean()
            const_levels = within_std[within_std < 1e-9].index
            if len(const_levels) < 2:
                continue
            a = lvl_f.reindex(const_levels).to_numpy(dtype="float64")
            b = lvl_y.reindex(const_levels).to_numpy(dtype="float64")
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() >= 2 and np.allclose(a[ok], b[ok], rtol=rtol, atol=1e-6):
                suspects.append({"feature": f, "by": c, "levels": int(ok.sum())})
    return {"hit": len(suspects) > 0, "suspects": suspects}


# ---------------------------------------------------------------- 汇总成 findings
def build_findings(
    combined: pd.DataFrame, feature_cols: list[str], args, split_values: list[str]
) -> list[dict]:
    """跑全部检查，产出统一的 {check,severity,columns,detail} 列表（机读 schema）。"""
    out: list[dict] = []

    ex = check_exact_dup(combined, feature_cols)
    exact_mask = ex.get("mask", pd.Series(False, index=combined.index))
    if ex["hit"]:
        out.append(
            {
                "check": "exact_duplicate_across_split",
                "severity": "HIGH",
                "columns": feature_cols,
                "detail": (
                    f"{ex['n_rows']} 行（{ex['n_keys']} 个唯一特征组合）的特征值完全相同"
                    f"却跨 ≥2 个 split（{'/'.join(split_values)}）。测试集出现训练集见过的原样本，"
                    f"指标会虚高。请去重后重划分，或确认这些是合法的天然重复。"
                ),
            }
        )

    nd = check_near_dup(combined, feature_cols, exact_mask, bins=args.bins)
    if nd["hit"]:
        out.append(
            {
                "check": "near_duplicate_across_split",
                "severity": "MED",
                "columns": feature_cols,
                "detail": (
                    f"{nd['n_rows']} 行在数值列{args.bins}分箱指纹下跨 ≥2 split 相同（已排除精确重复）。"
                    f"可能是近似样本泄漏，也可能是分箱巧合——请人工抽查这些行是否实为同一样本。"
                ),
            }
        )

    if args.group_col:
        gr = check_group_overlap(combined, args.group_col)
        if gr["hit"]:
            shown = ", ".join(map(str, gr["entities"]))
            more = "…" if gr["n_entities"] > len(gr["entities"]) else ""
            out.append(
                {
                    "check": "entity_overlap_across_split",
                    "severity": "HIGH",
                    "columns": [args.group_col],
                    "detail": (
                        f"实体列 '{args.group_col}' 有 {gr['n_entities']} 个实体、共 {gr['n_rows']} 行"
                        f"跨 ≥2 split（SPLIT-02 违例）。同一实体同时在训练/测试会泄漏个体信息。"
                        f"请改用 GroupKFold/按实体划分。样例实体：{shown}{more}"
                    ),
                }
            )

    if args.target:
        te = check_target_encoding(combined, feature_cols, args.target, rtol=args.rtol)
        if te["hit"]:
            for s in te["suspects"]:
                out.append(
                    {
                        "check": "target_mean_encoding_leak",
                        "severity": "HIGH",
                        "columns": [s["feature"], s["by"]],
                        "detail": (
                            f"数值特征 '{s['feature']}' 在 '{s['by']}' 的 {s['levels']} 个水平内近乎常量，"
                            f"且≈用全量(含 test)算的该水平 '{args.target}' 均值——疑似目标均值编码穿越。"
                            f"目标编码须仅用训练折在 CV 内拟合。若确为合法组统计，可忽略。"
                        ),
                    }
                )
    return out


def to_findings_report(rows: list[dict], target_name: str) -> "FindingsReport":
    """把 {check,severity,...} 列表转成 light.findings.v1（HIGH→critical fail）。"""
    sev_map = {"HIGH": "critical", "MED": "major", "LOW": "minor"}
    gates = []
    for r in rows:
        sev = sev_map.get(r["severity"], "info")
        status = "fail" if r["severity"] == "HIGH" else "warn"
        loc = ",".join(r.get("columns", [])) or "(rows)"
        gates.append(
            GateResult(
                gate=r["check"],
                status=status,
                severity=sev,
                findings=[
                    Finding(
                        loc=loc,
                        issue=r["detail"],
                        fix="去重/按实体重划分/目标编码移入 CV 内",
                        rule=r["check"],
                    )
                ],
            )
        )
    rep = FindingsReport(
        producer="data-engineering",
        target=target_name,
        summary=f"split_leakage 审计：{len(rows)} 项发现",
        fresh_evidence=True,
    )
    rep.gates = gates
    return rep.finalize()


def emit_findings_json(rows: list[dict], target_name: str, path: str) -> None:
    """优先用共享契约写 light.findings.v1；契约不可用则降级写裸 {check,severity,columns,detail} 列表。"""
    if _HAS_FINDINGS:
        payload = to_findings_report(rows, target_name).to_dict()
        # 额外保留机读 columns（findings_schema 的 loc 是字符串，这里附原数组方便 consistency/research-ethics 回扫）
        payload["raw_findings"] = rows
    else:
        payload = {
            "_schema_degraded": "findings_schema 不可用，降级裸列表",
            "producer": "data-engineering",
            "target": target_name,
            "findings": rows,
        }
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 渲染报告
def render(rows: list[dict], split_values: list[str], n_total: int) -> str:
    highs = [r for r in rows if r["severity"] == "HIGH"]
    meds = [r for r in rows if r["severity"] == "MED"]
    L = ["# Train/Test Split Leakage Audit", ""]
    L.append(f"- split：{' / '.join(split_values)}  |  总行数：{n_total}")
    L.append(f"- 发现：**HIGH {len(highs)}** · MED {len(meds)}")
    L.append("")
    if not rows:
        L.append("✅ 未检出跨 split 的精确重复 / 近重复 / 实体重叠 / 目标编码穿越。")
        L.append("")
        L.append(
            "> 注：本检查覆盖"
            "(a)精确重复 (b)分箱近重复 (c)实体重叠 (d)目标编码式泄漏；"
            "不替代 safe_split 的 fit-穿越断言与 drift_check 的分布比对。"
        )
        return "\n".join(L)
    L.append("| severity | check | columns | detail |")
    L.append("| --- | --- | --- | --- |")
    for r in highs + meds:
        cols = ", ".join(f"`{c}`" for c in r.get("columns", [])) or "-"
        detail = r["detail"].replace("\n", " ")
        L.append(f"| **{r['severity']}** | {r['check']} | {cols} | {detail} |")
    L.append("")
    if highs:
        L.append(
            "> ⚠ 存在 HIGH 级污染：测试集与训练集有共享样本/实体，评测指标不可信。"
            "**修复前不要把这套 split 的结果当真**（退出码已置 1）。"
        )
    L.append("")
    L.append(
        "<!-- 由 split_leakage.py 生成；HIGH=直接污染，MED=需人工复核（可能巧合）。 -->"
    )
    return "\n".join(L)


# ---------------------------------------------------------------- selftest
def _make_synth_leaky():
    """造一份带已知泄漏的 train/test：精确重复 10 行 + 实体重叠 + 目标编码列。

    关键：city_te（目标编码穿越列）必须在**最终 combined**（含注入的重复行）上计算，
    才能精确等于"用全量(含 test)算的该水平 y 均值"——这正是检查 d 要逮的签名。
    若在加重复之前算，重复行会改变 combined 的 per-city 均值，allclose 不再成立。"""
    rng = np.random.default_rng(0)
    n = 300
    base = pd.DataFrame(
        {
            "f1": rng.normal(0, 1, n).round(6),
            "f2": rng.integers(0, 100, n),
            "city": rng.choice(["bj", "sh", "gz", "sz"], n),
            "user_id": rng.integers(1000, 1000 + n, n),
        }
    )
    base["y"] = (base["f1"] + rng.normal(0, 0.3, n) > 0).astype(int)
    train = base.iloc[:200].reset_index(drop=True)
    test = base.iloc[200:].reset_index(drop=True)
    # 注入精确重复：把 train 前 10 行原样塞进 test
    test = pd.concat([test, train.iloc[:10]], ignore_index=True)
    # 注入实体重叠：让 test 前 5 行 user_id 与 train 重合（不动 city，city_te 仍一致）
    test.loc[test.index[:5], "user_id"] = train["user_id"].iloc[20:25].values
    # 在最终 combined 上计算目标编码穿越列，写回 train/test
    combined = pd.concat([train, test], ignore_index=True)
    city_te = combined.groupby("city")["y"].transform("mean")
    train["city_te"] = city_te.iloc[: len(train)].values
    test["city_te"] = city_te.iloc[len(train) :].values
    return train, test


def _selftest() -> int:
    print("### split_leakage 离线自测", file=sys.stderr)
    train, test = _make_synth_leaky()
    combined = pd.concat(
        [train.assign(**{SPLIT: "train"}), test.assign(**{SPLIT: "test"})],
        ignore_index=True,
    )

    class A:  # 模拟 args
        cols = None
        group_col = "user_id"
        target = "y"
        bins = 20
        rtol = 1e-3

    feature_cols = [c for c in combined.columns if c not in {SPLIT, "user_id", "y"}]

    rows = build_findings(combined, feature_cols, A, ["train", "test"])
    checks = {r["check"] for r in rows}

    assert "exact_duplicate_across_split" in checks, f"精确重复未命中: {checks}"
    assert "entity_overlap_across_split" in checks, f"实体重叠未命中: {checks}"
    assert "target_mean_encoding_leak" in checks, f"目标编码穿越未命中: {checks}"
    # 精确重复行数应 ≥ 注入的 10*2（train10 + test10 都被标）
    ex = next(r for r in rows if r["check"] == "exact_duplicate_across_split")
    assert "10 个唯一特征组合" in ex["detail"], ex["detail"]
    # 目标编码 suspect 的 feature 应是 city_te
    te = next(r for r in rows if r["check"] == "target_mean_encoding_leak")
    assert "city_te" in te["columns"], te["columns"]

    # 干净数据应零 HIGH：把 test 换成独立采样、无重复无实体重叠无编码列
    rng = np.random.default_rng(9)
    clean_tr = pd.DataFrame(
        {"a": rng.normal(0, 1, 150), "b": rng.choice(list("xyz"), 150)}
    )
    clean_te = pd.DataFrame(
        {"a": rng.normal(0, 1, 150), "b": rng.choice(list("xyz"), 150)}
    )
    cc = pd.concat(
        [clean_tr.assign(**{SPLIT: "train"}), clean_te.assign(**{SPLIT: "test"})],
        ignore_index=True,
    )

    class B:
        cols = None
        group_col = None
        target = None
        bins = 20
        rtol = 1e-3

    clean_rows = build_findings(cc, ["a", "b"], B, ["train", "test"])
    assert not [r for r in clean_rows if r["severity"] == "HIGH"], (
        f"干净数据误报 HIGH: {clean_rows}"
    )

    # findings.json 落盘（契约可用则校验 light.findings.v1）。
    # 用 try/finally 保证即使断言失败也清掉临时文件（CI 的零工件残留门禁）。
    tmp = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "_st_leak_findings.json"
    )
    emit_findings_json(rows, "selftest", tmp)
    try:
        with io.open(tmp, encoding="utf-8") as fh:
            payload = json.load(fh)
        if _HAS_FINDINGS:
            assert payload["schema"] == "light.findings.v1", payload.get("schema")
            assert payload["verdict"] == "fail", "有 HIGH 应推导 verdict=fail"
            assert payload["raw_findings"], "应附机读 raw_findings"
        else:
            assert payload["_schema_degraded"], "降级路径应标注"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # 渲染含表与诚实声明
    md = render(rows, ["train", "test"], len(combined))
    assert "HIGH" in md and "exact_duplicate_across_split" in md, md
    assert "退出码已置 1" in md, md

    print(
        f"[selftest] PASS split_leakage offline "
        f"(findings_schema {'on' if _HAS_FINDINGS else 'degraded'})"
    )
    return 0


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="train/test 行级·实体级·近重复 泄漏审计")
    ap.add_argument("--train", help="训练集 CSV（与 --test 配对）")
    ap.add_argument("--test", help="测试集 CSV（与 --train 配对）")
    ap.add_argument("--csv", help="单文件模式：带 split 列的整表")
    ap.add_argument("--split-col", help="单文件模式：split 标记列名")
    ap.add_argument(
        "--cols", help="逗号分隔的特征列子集，默认全列减去 group/target/split"
    )
    ap.add_argument("--group-col", help="实体列（检查 c：跨 split 实体重叠）")
    ap.add_argument("--target", help="目标列（检查 d：目标编码式泄漏）")
    ap.add_argument("--bins", type=int, default=20, help="近重复分箱数（默认 20）")
    ap.add_argument("--rtol", type=float, default=1e-3, help="目标编码匹配相对容差")
    ap.add_argument("--out", help="leak_audit.md 输出路径（默认 stdout）")
    ap.add_argument(
        "--findings", help="findings.json 输出路径（机读，挂 light.findings.v1）"
    )
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if not ((args.train and args.test) or (args.csv and args.split_col)):
        ap.error("提供 --train+--test 或 --csv+--split-col，或 --selftest")

    combined, split_values = load_combined(args)
    feature_cols = pick_feature_cols(combined, args)
    rows = build_findings(combined, feature_cols, args, split_values)

    md = render(rows, split_values, len(combined))
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        print(md)

    if args.findings:
        emit_findings_json(rows, args.out or args.csv or "train_test", args.findings)
        print(f"Wrote {args.findings}", file=sys.stderr)

    n_high = sum(1 for r in rows if r["severity"] == "HIGH")
    if n_high:
        print(f"[leak] {n_high} 项 HIGH 泄漏 → 退出码 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
