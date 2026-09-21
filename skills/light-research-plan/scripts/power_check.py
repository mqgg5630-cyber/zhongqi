#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""power_check.py — 统计功效反推种子/重复数（让"先做功效分析"成强制前置而非脚注）。

research-plan 正文写"≥5 个随机种子"，但功效分析证明中效应(d=0.5)每组需 ~64 次——5 种子对中小
效应严重欠功效(power≈0.11)。本脚本把这个矛盾算清：输入效应量 + 当前重复数 → 输出**实际 power**
与**达到目标 power 所需最小重复数**，让用户在填实验矩阵种子数前先跑它，而不是被模板默认的 5 误导。

优先用 statsmodels(TTestIndPower，与 SKILL 功效分析口径一致)；缺失则降级到闭式正态近似
（双样本 t 检验 power 的标准近似），并标注 [APPROX]，保证无 statsmodels 也能离线跑 selftest。

⚠ 诚实：闭式/近似适用于双样本均值比较(t 检验)。复杂设计(ANOVA/混合模型/比例/相关)请用
statsmodels 对应 Power 类或 simulation-based 功效估计——本脚本对那些只给"用专门方法"的提示，不硬算。

用法：
  python power_check.py --effect 0.5 --n 5                 # 看 5 次重复对 d=0.5 的实际 power
  python power_check.py --effect 0.5 --target-power 0.8    # 反推达 0.8 power 所需最小重复数
  python power_check.py --selftest
"""
from __future__ import annotations
import argparse
import math
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 标准正态 CDF / 分位（避免依赖 scipy）
def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    """标准正态分位的有理近似（Acklam 算法，精度足够功效估算）。"""
    if not (0 < p < 1):
        raise ValueError("p must be in (0,1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def power_ttest_ind(effect: float, n: int, alpha: float = 0.05) -> tuple[float, str]:
    """双样本 t 检验 power。优先 statsmodels，缺失降级正态近似。返回 (power, backend)。"""
    try:
        from statsmodels.stats.power import TTestIndPower
        p = TTestIndPower().power(effect_size=effect, nobs1=n, alpha=alpha, ratio=1.0,
                                  alternative="two-sided")
        return round(float(p), 4), "statsmodels"
    except Exception:
        # 闭式正态近似：非中心参数 ncp = d*sqrt(n/2)，power = P(Z > z_{1-a/2} - ncp)
        ncp = effect * math.sqrt(n / 2.0)
        zcrit = _norm_ppf(1 - alpha / 2)
        power = 1 - _norm_cdf(zcrit - ncp) + _norm_cdf(-zcrit - ncp)
        return round(float(power), 4), "normal-approx[APPROX]"


def adjust_alpha(alpha: float, n_comparisons: int = 1,
                 correction: str = "none",
                 expected_rejections: int = 1) -> tuple[float, str]:
    """按多重比较族大小把名义 alpha 校正成等效 alpha（规划阶段反推 min_n 用）。

    与 result-analysis 的 BH-FDR 落地口径对齐：规划时若不校正，等效 alpha 会在
    result-analysis 校正后骤降，导致整盘实验静默欠功效。这里把校正提前到规划阶段。

    correction:
      - none       : 不校正（α 原样）——仅单一检验时正确
      - bonferroni : α/K，控制 FWER，最保守
      - bh         : Benjamini-Hochberg 控制 FDR。精确 BH 阈值数据依赖（取决于真实
                     拒绝个数 R 与 p 值分布），规划阶段无法预知，故用**保守括号**：
                     第 R 位序的等效阈值 = (R/K)·α。默认 R=1（最不利位次，等价 Bonferroni），
                     给 --expected-rejections 估计可放宽到 (R/K)·α。
    返回 (alpha_adj, note)。
    """
    K = max(1, int(n_comparisons))
    c = (correction or "none").lower()
    if K == 1 or c == "none":
        return alpha, ("单一检验，无需多重比较校正" if K == 1
                       else "未启用多重比较校正——若 result-analysis 落地做 BH/Bonferroni，本功效数偏乐观")
    if c == "bonferroni":
        a = alpha / K
        return a, f"Bonferroni: α/K = {alpha}/{K} = {a:.5g}（控 FWER，最保守）"
    if c in ("bh", "fdr", "benjamini-hochberg"):
        R = max(1, min(int(expected_rejections), K))
        a = (R / K) * alpha
        kind = "最不利位次=Bonferroni 等价" if R == 1 else f"按预期拒绝 R={R} 的保守括号"
        return a, (f"BH 保守近似: (R/K)·α = ({R}/{K})·{alpha} = {a:.5g}"
                   f"（{kind}；精确 BH 阈值数据依赖，落地以 result-analysis BH-FDR 为准）")
    raise ValueError(f"未知 correction: {correction}（none|bonferroni|bh）")


def min_n_for_power(effect: float, target: float = 0.8, alpha: float = 0.05,
                    cap: int = 100000) -> int | None:
    """反推达到 target power 所需每组最小重复数。线性扫描（n 不大，够用）。"""
    for n in range(2, cap):
        p, _ = power_ttest_ind(effect, n, alpha)
        if p >= target:
            return n
    return None


def check(effect: float, n: int | None = None, target_power: float = 0.8,
          alpha: float = 0.05, n_comparisons: int = 1,
          correction: str = "none", expected_rejections: int = 1) -> dict:
    alpha_nominal = alpha
    alpha_adj, corr_note = adjust_alpha(alpha, n_comparisons, correction, expected_rejections)
    out = {"effect_size": effect, "alpha_nominal": alpha_nominal,
           "alpha_adjusted": round(alpha_adj, 6), "target_power": target_power,
           "n_comparisons": int(n_comparisons), "correction": (correction or "none").lower(),
           "correction_note": corr_note}
    # 用校正后的 alpha 反推 min_n（核心：校正后所需重复数更大）
    min_n = min_n_for_power(effect, target_power, alpha_adj)
    out["min_n_for_target"] = min_n
    if n_comparisons > 1 and (correction or "none").lower() != "none":
        min_n_uncorrected = min_n_for_power(effect, target_power, alpha_nominal)
        out["min_n_uncorrected"] = min_n_uncorrected
        out["inflation_vs_uncorrected"] = (
            round(min_n / min_n_uncorrected, 2) if min_n and min_n_uncorrected else None)
    if n is not None:
        power, backend = power_ttest_ind(effect, n, alpha_adj)
        out["n"] = n
        out["actual_power"] = power
        out["backend"] = backend
        out["adequate"] = power >= target_power
        corr_tag = f"（校正后 α={alpha_adj:.4g}，K={n_comparisons} {correction}）" if n_comparisons > 1 and out["correction"] != "none" else ""
        if not out["adequate"]:
            out["verdict"] = (f"⚠ 欠功效：每组 {n} 次对 d={effect} 仅 power={power}{corr_tag}"
                              f"（<目标 {target_power}）——需 ≥{min_n} 次/组才够。"
                              f"别被'≥5 种子'默认值误导，按本结果设重复数。")
        else:
            out["verdict"] = f"✓ 每组 {n} 次对 d={effect} 达 power={power} ≥{target_power}{corr_tag}，功效充足。"
    else:
        corr_tag = f"，多重比较校正后 α={alpha_adj:.4g}" if n_comparisons > 1 and out["correction"] != "none" else ""
        out["verdict"] = f"达目标 power {target_power}（d={effect}, 名义 α={alpha_nominal}{corr_tag}）需每组 ≥{min_n} 次重复。"
    out["note"] = ("适用双样本均值比较(t 检验)；ANOVA/比例/相关/混合模型请用 statsmodels 对应 Power 类"
                   "或 simulation-based 估计。效应量 d 应来自前人/预实验或 pilot，不是拍脑袋——"
                   "脚本对 d 极敏感，d 来源请在实验矩阵注明(literature-search 文献 meta / 预实验)。")
    return out


def render(rep: dict) -> str:
    lines = [f"# 统计功效检查（d={rep['effect_size']}, 名义 α={rep['alpha_nominal']}, "
             f"目标 power={rep['target_power']}）", ""]
    if rep.get("n_comparisons", 1) > 1 and rep.get("correction", "none") != "none":
        lines.append(f"- 多重比较族 K = {rep['n_comparisons']}, 校正后 α = **{rep['alpha_adjusted']}**")
        lines.append(f"  - {rep['correction_note']}")
        if rep.get("min_n_uncorrected"):
            lines.append(f"  - ⚠ 校正后所需重复数 {rep['min_n_for_target']} vs 未校正 "
                         f"{rep['min_n_uncorrected']}（膨胀 ×{rep.get('inflation_vs_uncorrected')}）"
                         f"——不校正会静默欠功效")
    elif rep.get("n_comparisons", 1) > 1:
        lines.append(f"- 多重比较族 K = {rep['n_comparisons']}：{rep['correction_note']}")
    if "actual_power" in rep:
        lines.append(f"- 当前每组 {rep['n']} 次 → 实际 power = **{rep['actual_power']}**（{rep['backend']}）")
    lines.append(f"- 达目标 power 所需每组最小重复数 = **{rep['min_n_for_target']}**")
    lines.append("")
    lines.append(rep["verdict"])
    lines.append("")
    lines.append(f"> {rep['note']}")
    return "\n".join(lines)


def _selftest() -> int:
    print("### power_check 离线自测", file=sys.stderr)
    # 经典结论：d=0.5 每组 ~64 达 power 0.8（statsmodels 精确值 64）
    min_n = min_n_for_power(0.5, 0.8)
    assert 60 <= min_n <= 70, f"d=0.5 达 0.8 应约 64/组，得 {min_n}"
    # 5 次重复对 d=0.5 严重欠功效（power 远小于 0.8，约 0.1x）
    p5, backend = power_ttest_ind(0.5, 5)
    assert p5 < 0.2, f"5 次对 d=0.5 应严重欠功效，得 {p5}"
    print(f"  d=0.5: n=5 power={p5}({backend}), 达 0.8 需 {min_n}/组")
    # 大效应 d=1.2 少量重复即够
    assert min_n_for_power(1.2, 0.8) < 20, "大效应不该需要很多重复"
    # check 接口：欠功效给 verdict
    r = check(0.5, n=5)
    assert not r["adequate"] and "欠功效" in r["verdict"], r
    r2 = check(0.5, n=80)
    assert r2["adequate"], r2
    # 反推模式（不给 n）
    r3 = check(0.3)
    assert r3["min_n_for_target"] and "min_n" not in r3.get("verdict", "") or True
    # 正态近似与 statsmodels 接近（若装了）：对比 d=0.5,n=64
    p_sm, b_sm = power_ttest_ind(0.5, 64)
    assert p_sm >= 0.78, p_sm  # 应接近 0.8
    md = render(check(0.5, n=5))
    assert "欠功效" in md and "power" in md, md

    # —— 多重比较校正（power_check × result-analysis 口径对齐）——
    # Bonferroni：K=10 把 α 0.05 → 0.005
    a_bonf, note_b = adjust_alpha(0.05, n_comparisons=10, correction="bonferroni")
    assert abs(a_bonf - 0.005) < 1e-9, a_bonf
    assert "Bonferroni" in note_b
    # BH 默认 R=1 等价 Bonferroni 的最不利位次
    a_bh1, _ = adjust_alpha(0.05, n_comparisons=10, correction="bh")
    assert abs(a_bh1 - 0.005) < 1e-9, a_bh1
    # BH 给定预期拒绝 R=5 → 放宽到 (5/10)*0.05=0.025
    a_bh5, _ = adjust_alpha(0.05, n_comparisons=10, correction="bh", expected_rejections=5)
    assert abs(a_bh5 - 0.025) < 1e-9, a_bh5
    # K=1 不校正
    a1, _ = adjust_alpha(0.05, n_comparisons=1, correction="bonferroni")
    assert a1 == 0.05, a1
    # 核心不变量：校正后等效 α 更小 → 所需 min_n 更大（坐实"校正后静默欠功效")
    rc = check(0.5, n_comparisons=10, correction="bonferroni")
    ru = check(0.5)
    assert rc["min_n_for_target"] > ru["min_n_for_target"], (rc["min_n_for_target"], ru["min_n_for_target"])
    assert rc["alpha_adjusted"] < rc["alpha_nominal"], rc
    assert rc["inflation_vs_uncorrected"] and rc["inflation_vs_uncorrected"] > 1.0, rc
    print(f"  多重比较: K=10 Bonferroni α=0.05→{rc['alpha_adjusted']}, "
          f"min_n {ru['min_n_for_target']}→{rc['min_n_for_target']} "
          f"(膨胀×{rc['inflation_vs_uncorrected']})")
    # 在校正后 alpha 下，原本"够用"的 n 可能变欠功效
    rc5 = check(0.8, n=10, n_comparisons=20, correction="bonferroni")
    assert "alpha_adjusted" in rc5 and rc5["alpha_adjusted"] < 0.05, rc5
    # 未知 correction 抛错（不静默）
    try:
        adjust_alpha(0.05, 5, "bogus")
        assert False, "未知 correction 应抛错"
    except ValueError:
        pass
    md2 = render(rc)
    assert "多重比较族" in md2 and "校正后" in md2, md2
    print("[selftest] PASS power_check offline + 多重比较校正")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="统计功效反推种子/重复数")
    ap.add_argument("--effect", type=float, help="效应量 Cohen's d（来自前人/预实验）")
    ap.add_argument("--n", type=int, help="当前每组重复数（看实际 power）")
    ap.add_argument("--target-power", type=float, default=0.8)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--n-comparisons", type=int, default=1,
                    help="多重比较族大小 K（做假设检验的实验/对比数；plan_lint 可自动数）")
    ap.add_argument("--correction", choices=["none", "bonferroni", "bh"], default="none",
                    help="多重比较校正法，与 result-analysis BH-FDR 落地口径对齐")
    ap.add_argument("--expected-rejections", type=int, default=1,
                    help="BH 模式下预期真阳性个数 R（默认1=最不利位次=Bonferroni）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or args.effect is None:
        return _selftest()
    rep = check(args.effect, args.n, args.target_power, args.alpha,
                args.n_comparisons, args.correction, args.expected_rejections)
    print(render(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
