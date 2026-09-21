#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stat_rigor_gate.py — result-analysis 的**统计严谨 / 证据强度 Critical 门 producer**。

蓝图 §4.3-7 的「及格线」:结果分析不描述好坏、解释「为什么」,并把每条结论**绑死到 claim + 证据强度**。
最让结论**不可信**的硬伤是 **p-hacking**(多重比较不校正 / 选择性报告 / garden of forking paths),要在分析阶段
当**机读门**拦住,而非靠「看着显著」。本脚本把这条编排成机读 `light.findings.v1`(producer=**result-analysis**),
**统计错误/p-hacking → critical fail** → 被总控 `run_checkpoint --stage 7` 聚合 **exit 1**。门名对齐
`STAGE_GATES[7]=[stat_validity, evidence_strength]`。**过度解读 / 效应量缺失 = warn**(spec §4.2)。

这是 **v2 净新增的接线**(与 experiment-coding `repro_gate`、research-plan `plan_gate`、data-engineering
`data_feasibility_gate`、idea 侧 `fatal_flaw_gate` 同构):**编排港来纯统计引擎 + 接 `_shared` 规范 bootstrap →
critical findings producer**,不重造统计——
  - 多重比较校正:复用同目录港来 `significance_test.benjamini_hochberg`(numpy,`__main__` 已对齐 statsmodels
    `multipletests(fdr_bh)` 数值一致);缺 numpy → 纯 stdlib BH 兜底(同款公式,确定性)。
  - 证据强度分档:**直接消费 `_shared/evidence_contract`**(q/效应量/CI → strong/moderate/weak/none + 措辞档,
    中英双语 + 否定守卫 + GRADE 词表)——**不重造措辞档**;并 emit `evidence_strength.json` 供下游。
  - (可选)从结果 CSV 导 claim:复用同目录港来 `analyze_results`(自动选检验 + 效应量 + FDR),缺 pandas 优雅降级。

**回炉发起方(与 experiment-coding 的根本区别,spec §5)**:experiment-coding 是 7→6 的**回炉落点**(被动接);
**result-analysis 是 7→6 + 7→5 两条回边的发起方(主动发)**——
  - `hypothesis_support` 判**结果不支撑假设**(grade=none:q>=.05 / CI 含 0 / 效应量过小)→ critical,issue 带
    「假设/支撑/效应」信号 → 总控 `reroute --stage 7` 命中 `ROUTES[7]` 建议 **7→5** 回 research-plan。
  - `reproducibility` 判**结果不可复现**(多种子 sign-flip / CV 过大)→ critical,issue 带「种子/复现/不可复现」
    信号 → reroute 建议 **7→6** 回 experiment-coding。
  - `stat_validity` 的 p-hacking critical = **stage 7 内重做分析**(issue 刻意不带 5/6 路由信号 → reroute 给
    action=manual,即在本阶段修),诚实落点。

四个 gate:
  ① stat_validity(统计错误/p-hacking,**critical**):多重比较未校正(裸 p<.05 经 BH-FDR 真重算后掉到 q>=.05 =
     假阳性)/ 选择性报告(跑 N 报 n<N,隐藏比较)→ critical;未声明校正但重算后仍全 q<.05 → warn;<2 比较/已校正 → pass。
  ② evidence_strength(证据强度分档,**warn**):消费 evidence_contract 给每条 claim 定档(强/中/弱/无)+ emit
     `evidence_strength.json`;过度解读(声称档强于实算档)/ 效应量缺失(只报 p)→ warn(spec §4.2 不阻断,
     硬措辞门在 stage 8 research-ethics)。
  ③ hypothesis_support(假设支撑,**critical**):声明的假设 grade=none → 结果不支撑 → critical → 7→5 回 research-plan。
  ④ reproducibility(结果可复现,**critical**):多种子 sign-flip / CV 过大 / 显式 repro_failed → 不可复现 →
     critical → 7→6 回 experiment-coding。无多种子数据 → skip。

诚实约定(名实对齐见 SKILL,铁律 2):
- **统计检查有边界**:查「多重比较有没有校正 / 假设统计上撑不撑得住 / 结果稳不稳」,**绝不「证明了方法真有效 /
  因果成立」**——效应量解读、机制因果、外推性的**终判仍需人/领域判断**。
- **forking paths 机器测不全**:隐性多重比较(数据依赖的分析选择)脚本只能据声明的「跑了几个/报了几个/校没校正」
  提示,不替你判分析选择合不合理(GIGO);未声明 → 不编造放水。
- **证据分档只吃统计强度**(继承 evidence_contract):未做 GRADE 另四域(偏倚/不一致/间接/发表偏倚)系统降级。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  python stat_rigor_gate.py --spec stat_spec.json --report stat_findings.json --evidence-out evidence_strength.json
  python stat_rigor_gate.py --selftest

spec JSON 形如:
  {"project":"goat-estrus",
   "claims":[{"claim_id":"c1","text":"ours vs baseline (acc)","p":0.012,"q_fdr":null,
              "effect_size":0.7,"effect_kind":"cohens_d","ci95":[0.2,1.1],"n":40,
              "asserted_grade":"strong",            # 可选:作者想用的措辞强度档
              "is_hypothesis":true,"hypothesis_id":"H1",
              "seeds":[0.86,0.85,0.87,0.84,0.86]}], # 可选:多种子稳定性
   "correction":"none|bh|bonferroni|holm",          # 是否对全部比较做了多重比较校正
   "comparisons_run":12,"comparisons_reported":3,    # 可选:跑了几个 / 报了几个(选择性报告)
   "results_csv":"results.csv","group":"method","metric":["acc"],"paired_by":"seed"}  # 可选:从 CSV 导 claim
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

# 同目录港来的纯统计引擎(复用不重造:多重比较校正 + 从 CSV 导 claim)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:                                              # numpy 版 BH(== statsmodels multipletests fdr_bh)
    from significance_test import benjamini_hochberg as _bh_np  # noqa: E402
    _HAS_BH_NP = True
except Exception:
    _HAS_BH_NP = False
try:                                              # 可选:从结果 CSV 自动算 claim(自动选检验+效应量+FDR)
    import analyze_results as ar                  # noqa: E402
    _HAS_AR = True
except Exception:
    _HAS_AR = False

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,治硬编码 parents[N] 之脆。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    from _shared import evidence_contract as ec                              # noqa: E402
    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False

ALPHA = 0.05
CV_THRESHOLD = 0.5          # 变异系数(std/|mean|)阈:跨种子 > 此值 = 不稳(启发式,强依赖任务)
_GRADE_ORDER = {"none": 0, "weak": 1, "moderate": 2, "strong": 3}


# ───────────────────────── 多重比较校正(复用港来件 + stdlib 兜底) ─────────────────────────
def _bh_fallback(pvals: list, alpha: float = ALPHA) -> list:
    """纯 stdlib Benjamini-Hochberg(== statsmodels fdr_bh / 港来 numpy 版),numpy 缺失时兜底。"""
    n = len(pvals)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: pvals[i])      # 升序索引
    q = [0.0] * n
    prev = 1.0
    for rank in range(n, 0, -1):                            # 从最大 rank 往小,取累积最小(单调化)
        i = order[rank - 1]
        val = min(prev, pvals[i] * n / rank)
        q[i] = val
        prev = val
    return [min(1.0, v) for v in q]


def bh_qvalues(pvals: list) -> list:
    """对一组裸 p 算 BH-FDR 后 q:优先港来 numpy 版(== statsmodels),否则 stdlib 兜底。"""
    if not pvals:
        return []
    if _HAS_BH_NP:
        try:
            _rej, q = _bh_np(pvals, ALPHA)
            return [float(x) for x in q]
        except Exception:
            pass
    return _bh_fallback(pvals, ALPHA)


# ───────────────────────── claim 收集 + q 标注 ─────────────────────────
def _has_p(c: dict) -> bool:
    return c.get("p") is not None


def claims_from_csv(spec: dict) -> tuple:
    """可选:从结果 CSV 复用 analyze_results 导 claim(每个 pairwise 比较 = 一条 claim)。
    返回 (claims, note);缺 pandas/analyze_results/路径 → ([], 原因)。"""
    if not spec.get("results_csv"):
        return [], ""
    if not _HAS_AR:
        return [], "analyze_results 不可用(不在 Light-Skills 树内):results_csv 路径跳过,用显式 claims。"
    try:
        import pandas as pd
    except Exception:
        return [], "pandas 不可用:results_csv 路径跳过,用显式 claims。"
    try:
        df = pd.read_csv(spec["results_csv"])
        group = spec.get("group", "method")
        metrics = spec.get("metric") or [c for c in df.columns
                                         if c != group and pd.api.types.is_numeric_dtype(df[c])]
        pair = spec.get("paired_by")
        out = []
        for m in metrics:
            res = ar.analyze_metric(df, group, m, pair)
            mode, comparisons = ar.primary_comparisons(res)
            for c in comparisons:
                if c.get("p") is None:
                    continue
                is_paired = mode == "paired"
                out.append({
                    "claim_id": (f"{m}:{c['group1']}_vs_{c['group2']}"
                                 + (":paired" if is_paired else "")),
                    "text": (f"{m}: {c['group1']} vs {c['group2']}"
                             + (" (paired)" if is_paired else "")),
                    "p": c.get("p"), "q_fdr": c.get("q_fdr"),
                    "effect_size": c.get("cohens_dz" if is_paired else "cohens_d"),
                    "effect_kind": "cohens_dz" if is_paired else "cohens_d",
                    "ci95": c.get("diff_ci95"),
                    "n": c.get("n_pairs") if is_paired else int(len(df)),
                })
        return out, ""
    except Exception as e:                                  # 文件缺失/列名错如实报,不静默
        return [], f"从 results_csv 导 claim 失败:{e}(用显式 claims)。"


def annotate_q(claims: list) -> None:
    """对全部带 p 的 claim 算 BH-FDR 后 q(_q_computed),并定 _q_used(优先作者给的 q_fdr,否则重算 q,否则 p)。"""
    idx = [i for i, c in enumerate(claims) if _has_p(c)]
    if idx:
        ps = [float(claims[i]["p"]) for i in idx]
        qs = bh_qvalues(ps)
        for j, i in enumerate(idx):
            claims[i]["_q_computed"] = qs[j]
    for c in claims:
        if c.get("q_fdr") is not None:
            c["_q_used"] = c["q_fdr"]
        elif c.get("_q_computed") is not None:
            c["_q_used"] = c["_q_computed"]
        elif _has_p(c):
            c["_q_used"] = float(c["p"])
        else:
            c["_q_used"] = None


def _grade_of(c: dict) -> str:
    """据 _q_used / 效应量 / CI / n 定证据档(消费 evidence_contract,不重造)。"""
    return ec.grade_evidence(c.get("_q_used"), c.get("effect_size"), c.get("ci95"), c.get("n"))


def _to_ec_claim(c: dict) -> dict:
    """转成 evidence_contract.build_evidence_json 吃的 claim(q 用校正后 _q_used)。"""
    return {"claim_id": c.get("claim_id"), "text": c.get("text", ""),
            "q_fdr": c.get("_q_used"), "effect_size": c.get("effect_size"),
            "effect_kind": c.get("effect_kind", "cohens_d"),
            "ci95": c.get("ci95"), "n": c.get("n")}


def _fmt(x) -> str:
    return f"{x:.4g}" if isinstance(x, (int, float)) else str(x)


# ───────────────────────── 四个 gate 函数(接 _shared) ─────────────────────────
def _stat_validity_gate(art: dict) -> "GateResult":
    """统计错误/p-hacking 门(critical):多重比较未校正(真重算 BH)/ 选择性报告。在 stage 7 内修(issue 不带 5/6 路由信号)。"""
    claims = art["claims"]
    corr = str(art["correction"]).lower()
    reported = art["reported"]
    run_total = art["run_total"]
    loc = f"{art['project']}:stat_validity"
    with_p = [c for c in claims if _has_p(c)]
    if not with_p:
        return GateResult("stat_validity", "skip", "info", [],
                          note="无带 p 值的比较:统计严谨门跳过(请给 claims 的 p,或交 analyze_results 从 CSV 算)。")
    crit, warns = [], []
    # ① 多重比较未校正:真重算 BH,看裸 p<.05 中有几个被校正掉
    if len(with_p) >= 2 and corr in ("none", "no", ""):
        raw_sig = [c for c in with_p if float(c["p"]) < ALPHA]
        demoted = [c for c in raw_sig if c.get("_q_computed", 1.0) >= ALPHA]
        if raw_sig and demoted:
            ids = ",".join(str(c.get("claim_id", "?")) for c in demoted)
            crit.append(Finding(
                loc=loc,
                issue=f"{len(with_p)} 个比较未做多重比较校正:{len(raw_sig)} 个裸 p<.05 中 {len(demoted)} 个经 "
                      f"BH-FDR 校正后 q>=.05(假阳性);claim={ids}",
                fix="对全部比较做 BH-FDR / Bonferroni 校正,显著性一律以校正后 q 为准(statsmodels multipletests)",
                evidence=f"raw p={[round(float(c['p']), 4) for c in raw_sig]};"
                         f"BH q={[round(c.get('_q_computed', 1.0), 4) for c in demoted]}",
                rule="phacking.multiple_comparisons_uncorrected"))
        elif raw_sig:
            warns.append(Finding(
                loc=loc,
                issue=f"{len(with_p)} 个比较未声明多重比较校正(虽 BH 校正后仍全部 q<.05)",
                fix="显式报 BH-FDR 校正后 q,以免被审稿人质疑 family-wise 假阳性",
                rule="phacking.correction_undeclared"))
    # ② 选择性报告:跑 N 报 n<N
    if run_total is not None and int(run_total) > int(reported):
        hidden = int(run_total) - int(reported)
        crit.append(Finding(
            loc=loc,
            issue=f"跑了 {run_total} 个比较只报 {reported} 个(隐藏 {hidden} 个);选择性报告 = garden of "
                  f"forking paths,family-wise 假阳性被低估",
            fix="报告全部比较(含未达阈值的),或预注册比较族 + 统一校正;不得只挑成功的报(HARKing)",
            rule="phacking.selective_reporting"))
    if crit:
        return GateResult("stat_validity", "fail", "critical", crit,
                          note="统计错误/p-hacking(critical,spec §4.2):多重比较未校正 / 选择性报告 → 假阳性,"
                               "在 stage 7 内重做分析(校正后 q 为准);reroute 给 manual(本阶段修,非回上游)。")
    if warns:
        return GateResult("stat_validity", "warn", "major", warns,
                          note="多重比较校正未显式声明(warn,重算后结果尚稳):补报校正后 q。")
    return GateResult("stat_validity", "pass", "info", [],
                      note=f"多重比较已校正({corr}) / 比较数<2 / 无选择性报告;"
                           "统计严谨终判仍需人核分析选择(forking paths 机器测不全)。")


def _evidence_strength_gate(art: dict) -> "GateResult":
    """证据强度分档门(warn):消费 evidence_contract 定档 + 过度解读/效应量缺失 warn(硬措辞门在 stage 8)。"""
    claims = art["claims"]
    if not claims:
        return GateResult("evidence_strength", "skip", "info", [],
                          note="无 claim:证据强度门跳过(请给 claims,或交 analyze_results 从 CSV 算)。")
    warns = []
    for c in claims:
        g = _grade_of(c)
        asserted = c.get("asserted_grade")
        if asserted and _GRADE_ORDER.get(asserted, 0) > _GRADE_ORDER.get(g, 0):
            warns.append(Finding(
                loc=f"claim:{c.get('claim_id', '?')}",
                issue=f"过度解读:声称证据档『{asserted}』强于实算档『{g}』(grade_evidence:q/效应量/CI 机械定档)",
                fix=f"措辞降到『{g}』档,或补更强证据(更小 q / 更大 |效应量| / 更窄 CI);"
                    "写作时由 research-ethics stage-8 硬门复核",
                rule="evidence_strength.over_interpretation"))
    for c in claims:
        if _has_p(c) and c.get("effect_size") is None:
            warns.append(Finding(
                loc=f"claim:{c.get('claim_id', '?')}",
                issue="只报了 p,缺效应量(只看 p 不看效应量 = 统计常见误用,p 小不代表差异大)",
                fix="补 Cohen's d(参数检验,Hedges 小样本校正)或 Cliff's δ(非参/序数),并配 95% CI",
                rule="evidence_strength.effect_size_missing"))
    if warns:
        return GateResult("evidence_strength", "warn", "major", warns,
                          note="过度解读 / 效应量缺失(warn,spec §4.2 不阻断):evidence_strength.json 已产,"
                               "下游 research-ethics 在 stage 8 卡『措辞不强于证据』硬门。")
    grades = {str(c.get("claim_id", "?")): _grade_of(c) for c in claims}
    return GateResult("evidence_strength", "pass", "info", [],
                      note=f"各 claim 证据档已定:{grades};evidence_strength.json 供下游卡措辞"
                           "(强证据强措辞、弱证据 hedge、none 只报『未见显著差异』)。")


def _hypothesis_support_gate(art: dict) -> "GateResult":
    """假设支撑门(critical → 7→5):声明的假设 grade=none(不显著/CI 含 0/效应量过小)= 结果不支撑假设。"""
    claims = art["claims"]
    hyps = [c for c in claims if c.get("is_hypothesis")]
    if not hyps:
        return GateResult("hypothesis_support", "skip", "info", [],
                          note="未声明假设(claim.is_hypothesis=true):假设支撑门跳过。")
    finds = []
    for c in hyps:
        if _grade_of(c) == "none":
            hid = c.get("hypothesis_id") or c.get("claim_id", "H?")
            q = c.get("_q_used")
            ci = c.get("ci95")
            finds.append(Finding(
                loc=f"hypothesis:{hid}",
                issue=f"假设 {hid} 未被结果支撑:经 BH-FDR 后 q={_fmt(q)}>=.05 或 CI={ci} 含 0 或效应量过小 → "
                      f"结果不支撑该假设",
                fix="回 research-plan(7→5)重审假设 / 设计(或 H 本就不成立,或需更强实验);"
                    "绝不 HARKing 删掉换个『成功』的假设重报",
                evidence=f"q_used={_fmt(q)};effect_size={c.get('effect_size')};ci95={ci};n={c.get('n')}",
                rule="hypothesis_support"))
    if finds:
        return GateResult("hypothesis_support", "fail", "critical", finds,
                          note="结果不支撑假设(critical):本技能是 7→5 回炉发起点,回 research-plan 重审假设/设计"
                               "(reroute 按『假设/支撑/效应』信号路由到 stage 5)。")
    return GateResult("hypothesis_support", "pass", "info", [],
                      note="所有声明的假设都被结果支撑(证据档非 none);机制/因果终判仍需人判。")


def _reproducibility_gate(art: dict) -> "GateResult":
    """结果可复现门(critical → 7→6):多种子 sign-flip / CV 过大 / 显式 repro_failed = 换次跑会飘。"""
    claims = art["claims"]
    flagged, has_any = [], False
    for c in claims:
        if c.get("repro_failed"):
            has_any = True
            flagged.append((c, "显式标记 repro_failed", None))
            continue
        seeds = c.get("seeds")
        if not seeds or len(seeds) < 2:
            continue
        has_any = True
        vals = [float(v) for v in seeds]
        lo, hi = min(vals), max(vals)
        mean = sum(vals) / len(vals)
        sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
        cv = abs(sd / mean) if mean != 0 else float("inf")
        sign_flip = lo < 0 < hi
        if sign_flip:
            flagged.append((c, f"跨种子 sign-flip(范围=[{lo:.4g},{hi:.4g}])", cv))
        elif cv > CV_THRESHOLD:
            flagged.append((c, f"跨种子变异系数 CV={cv:.2f}>{CV_THRESHOLD}", cv))
    if not has_any:
        return GateResult("reproducibility", "skip", "info", [],
                          note="无多种子结果(claim.seeds)且无 repro_failed 标记:可复现门跳过"
                               "(终判=同种子真跑两次一致,那是 experiment-coding 的硬验收)。")
    if flagged:
        finds = []
        for c, reason, cv in flagged:
            cid = c.get("claim_id", "?")
            finds.append(Finding(
                loc=f"claim:{cid}",
                issue=f"结果不可复现:claim {cid} 的指标{reason} → 换次跑结论会飘,复现失败(种子层面不稳)",
                fix="回 experiment-coding(7→6)查随机种子覆盖 / 实现 bug;或多种子报均值±std 并 hedge,不报单次峰值",
                evidence=f"seeds={c.get('seeds')}",
                rule="reproducible"))
        return GateResult("reproducibility", "fail", "critical", finds,
                          note="结果不可复现(critical):本技能是 7→6 回炉发起点,回 experiment-coding 查种子/bug"
                               "(reroute 按『种子/复现』信号路由到 stage 6)。")
    return GateResult("reproducibility", "pass", "info", [],
                      note="多种子结果稳定(无 sign-flip、CV 在阈内);终判=同种子真跑两次一致(experiment-coding 硬验收)。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict, evidence_out: str = "") -> dict:
    """组装统计严谨/证据强度 critical findings:港来 BH 重算 + 消费 evidence_contract → 四 gate。"""
    project = str(spec.get("project", "unnamed"))
    claims = list(spec.get("claims") or [])
    csv_claims, csv_note = claims_from_csv(spec)
    claims = claims + csv_claims
    annotate_q(claims)
    correction = spec.get("correction", "none")
    reported = spec.get("comparisons_reported")
    if reported is None:
        reported = sum(1 for c in claims if _has_p(c))
    run_total = spec.get("comparisons_run")

    evidence_json = None
    if _SHARED_OK and claims:
        evidence_json = ec.build_evidence_json([_to_ec_claim(c) for c in claims])
        evidence_json["source"] = "result-analysis:stat_rigor_gate"

    art = {"project": project, "claims": claims, "correction": correction,
           "reported": reported, "run_total": run_total, "evidence_json": evidence_json,
           "csv_note": csv_note}

    report = None
    if _SHARED_OK:
        report = run_gates(
            [_stat_validity_gate, _evidence_strength_gate,
             _hypothesis_support_gate, _reproducibility_gate],
            art, producer="result-analysis", target=project,
            summary="result-analysis 结果门:统计错误/p-hacking(critical)+ 证据强度分档(warn,emit "
                    "evidence_strength.json)+ 假设支撑(critical→7→5)+ 可复现(critical→7→6)→ "
                    "p-hacking/不支撑假设/不可复现 → run_checkpoint --stage 7 exit 1;本技能是 7→5/7→6 回炉发起方。",
            fresh_evidence=True)

    if evidence_out and evidence_json is not None:
        pathlib.Path(evidence_out).write_text(
            json.dumps(evidence_json, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"project": project, "claims": claims, "correction": correction,
            "reported": reported, "run_total": run_total,
            "evidence_strength": evidence_json, "csv_note": csv_note,
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# result-analysis 结果门(统计严谨/证据强度):{result['project']}", ""]
    if result.get("csv_note"):
        lines += [f"> 注:{result['csv_note']}", ""]
    # 证据强度分档表
    ev = result.get("evidence_strength")
    lines += ["## 证据强度分档 (evidence_strength)", ""]
    if ev and ev.get("claims"):
        lines += ["| claim | q(校正后) | 效应量 | 证据档 | GRADE | 须 hedge |",
                  "|---|---|---|---|---|---|"]
        for c in ev["claims"]:
            lines.append(f"| {c.get('claim_id')} | {_fmt(c.get('q_fdr'))} | {_fmt(c.get('effect_size'))} "
                         f"| **{c.get('evidence_grade')}** | {c.get('grade_level')} "
                         f"| {'是' if c.get('hedge_required') else '否'} |")
    else:
        lines.append("- (无 claim / _shared 不可达 → 无证据分档)")
    # findings
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=result-analysis);"
                  f"run_checkpoint --stage 7 聚合,p-hacking/不支撑假设/不可复现→critical fail→exit 1;"
                  f"本技能是 7→5(不支撑假设)/7→6(不可复现)回炉发起方。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 0. BH 兜底 == 港来 numpy 版(== statsmodels)的交叉核对
    pv = [0.001, 0.012, 0.03, 0.04, 0.2, 0.7]
    qf = _bh_fallback(pv)
    if _HAS_BH_NP:
        _r, qn = _bh_np(pv, ALPHA)
        check(all(abs(a - float(b)) < 1e-9 for a, b in zip(qf, qn)),
              "stdlib BH 兜底应与港来 numpy 版(==statsmodels)数值一致")

    # 1. 干净:已校正 + 假设被支撑 + 多种子稳 → 全 pass
    clean = {"project": "p1", "correction": "bh", "comparisons_run": 2,
             "claims": [
                 {"claim_id": "c1", "text": "ours vs base (acc)", "p": 0.002, "effect_size": 0.8,
                  "ci95": [0.3, 1.2], "n": 40, "is_hypothesis": True, "hypothesis_id": "H1",
                  "seeds": [0.85, 0.86, 0.84, 0.86, 0.85]},
                 {"claim_id": "c2", "text": "ours vs abl (acc)", "p": 0.004, "effect_size": 0.7,
                  "ci95": [0.2, 1.1], "n": 40}]}
    r1 = build(clean)
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f1["producer"] == "result-analysis", f"producer 应 result-analysis,得 {f1['producer']}")
        names = {g["gate"] for g in f1["gates"]}
        check({"stat_validity", "evidence_strength"} <= names,
              f"门名应含 STAGE_GATES[7] 的 stat_validity/evidence_strength,得 {names}")
        check(f1["verdict"] == "pass", f"干净结果应整体 pass,得 {f1['verdict']}")
        # evidence_strength.json 结构 + 强证据定档
        ev = r1["evidence_strength"]
        check(ev and ev["schema"] == "light.evidence_strength.v1", "应产 light.evidence_strength.v1")
        g1 = next(c for c in ev["claims"] if c["claim_id"] == "c1")
        check(g1["evidence_grade"] == "strong", f"c1(q<.01,d.8,CI 不含0,n40)应 strong,得 {g1['evidence_grade']}")

    # 2. p-hacking:5 比较未校正,裸 p<.05 经 BH 后掉出 → stat_validity critical → fail
    phack = {"project": "p2", "correction": "none",
             "claims": [{"claim_id": f"c{i}", "text": f"comp{i}", "p": p, "effect_size": 0.3,
                         "ci95": [0.05, 0.5], "n": 50}
                        for i, p in enumerate([0.01, 0.045, 0.048, 0.049, 0.2])]}
    r2 = build(phack)
    if _SHARED_OK:
        f2 = r2["findings"]
        check(f2["verdict"] == "fail", f"未校正多重比较应整体 fail,得 {f2['verdict']}")
        sv = next(g for g in f2["gates"] if g["gate"] == "stat_validity")
        check(sv["status"] == "fail" and sv["severity"] == "critical", "多重比较未校正应 stat_validity critical")
        check(any(x["rule"] == "phacking.multiple_comparisons_uncorrected" for x in sv["findings"]),
              "应命中 multiple_comparisons_uncorrected 规则")
        # 诚实:p-hacking issue 不带 5/6 路由信号(reroute 应给 manual=本阶段修,非回上游)
        blob = " ".join(x["issue"] for x in sv["findings"])
        for sig in ("假设", "支撑", "效应", "显著", "种子", "复现", "seed", "repro"):
            check(sig not in blob, f"stat_validity p-hacking issue 不应含路由信号『{sig}』(否则误路由),含了:{blob}")
        rep = FindingsReport.from_json(json.dumps(f2, ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1, "findings 应可往返且有阻断 gate")

    # 3. 选择性报告:跑 12 报 1 → stat_validity critical
    sel = {"project": "p3", "correction": "bh", "comparisons_run": 12, "comparisons_reported": 1,
           "claims": [{"claim_id": "c1", "p": 0.001, "effect_size": 0.9, "ci95": [0.5, 1.3], "n": 60}]}
    r3 = build(sel)
    if _SHARED_OK:
        sv3 = next(g for g in r3["findings"]["gates"] if g["gate"] == "stat_validity")
        check(sv3["status"] == "fail" and any(x["rule"] == "phacking.selective_reporting" for x in sv3["findings"]),
              "跑 12 报 1 应命中 selective_reporting critical")

    # 4. 假设不被支撑(p=.2,CI 含 0)→ hypothesis_support critical → 7→5 信号
    hypf = {"project": "p4", "correction": "bh",
            "claims": [{"claim_id": "H1", "text": "main hypo", "p": 0.2, "effect_size": 0.1,
                        "ci95": [-0.2, 0.4], "n": 50, "is_hypothesis": True, "hypothesis_id": "H1"}]}
    r4 = build(hypf)
    if _SHARED_OK:
        f4 = r4["findings"]
        hs = next(g for g in f4["gates"] if g["gate"] == "hypothesis_support")
        check(hs["status"] == "fail" and hs["severity"] == "critical", "假设不被支撑应 hypothesis_support critical")
        check(f4["verdict"] == "fail", "不支撑假设应整体 fail")
        blob4 = hs["gate"] + " " + " ".join(x["issue"] + x.get("rule", "") for x in hs["findings"])
        check(any(s in blob4 for s in ("假设", "支撑", "效应", "hypothesis", "support")),
              "hypothesis_support 应带 7→5 路由信号")
        check(not any(s in " ".join(x["issue"] for x in hs["findings"]) for s in ("种子", "复现", "seed", "repro")),
              "hypothesis_support issue 不应含 7→6 信号(否则误路由到 6)")

    # 5. 不可复现(多种子 sign-flip)→ reproducibility critical → 7→6 信号
    repro = {"project": "p5", "correction": "bh",
             "claims": [{"claim_id": "c1", "text": "effect", "p": 0.03, "effect_size": 0.5,
                         "ci95": [0.1, 1.0], "n": 40, "seeds": [0.4, -0.3, 0.5, -0.2, 0.3]}]}
    r5 = build(repro)
    if _SHARED_OK:
        f5 = r5["findings"]
        rp = next(g for g in f5["gates"] if g["gate"] == "reproducibility")
        check(rp["status"] == "fail" and rp["severity"] == "critical", "多种子 sign-flip 应 reproducibility critical")
        check(f5["verdict"] == "fail", "不可复现应整体 fail")
        blob5 = rp["gate"] + " " + " ".join(x["issue"] + x.get("rule", "") for x in rp["findings"])
        check(any(s in blob5 for s in ("种子", "复现", "reproduc")), "reproducibility 应带 7→6 路由信号")

    # 6. 过度解读(声称 strong 实算 weak)→ evidence_strength warn(非 critical)
    over = {"project": "p6", "correction": "bh",
            "claims": [{"claim_id": "c1", "p": 0.03, "effect_size": 0.2, "ci95": [0.02, 0.4],
                        "n": 200, "asserted_grade": "strong"}]}
    r6 = build(over)
    if _SHARED_OK:
        es = next(g for g in r6["findings"]["gates"] if g["gate"] == "evidence_strength")
        check(es["status"] == "warn" and es["severity"] != "critical",
              f"过度解读应 evidence_strength warn 非 critical,得 {es['status']}/{es['severity']}")
        check(any(x["rule"] == "evidence_strength.over_interpretation" for x in es["findings"]),
              "应命中 over_interpretation 规则")
        check(r6["findings"]["verdict"] == "warn", "仅过度解读应整体 warn(不阻断)")

    # 7. 效应量缺失(有 p 无 effect_size)→ evidence_strength warn
    effmiss = {"project": "p7", "correction": "bh",
               "claims": [{"claim_id": "c1", "p": 0.01, "effect_size": None, "ci95": None, "n": 40}]}
    r7 = build(effmiss)
    if _SHARED_OK:
        es7 = next(g for g in r7["findings"]["gates"] if g["gate"] == "evidence_strength")
        check(es7["status"] == "warn" and any(x["rule"] == "evidence_strength.effect_size_missing"
                                              for x in es7["findings"]),
              "有 p 无效应量应命中 effect_size_missing warn")

    # 8. 无 claim → 四门 skip(不静默当 pass)
    r8 = build({"project": "p8", "claims": []})
    if _SHARED_OK:
        st = {g["gate"]: g["status"] for g in r8["findings"]["gates"]}
        check(all(st[k] == "skip" for k in ("stat_validity", "evidence_strength",
                                            "hypothesis_support", "reproducibility")),
              f"无 claim 应四门 skip,得 {st}")

    # 9. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 10. markdown 不崩
    check("结果门" in to_markdown(r2), "markdown 应含结果门标题")

    if failures:
        print("[SELFTEST][stat_rigor_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][stat_rigor_gate] OK:干净 pass / 未校正多重比较 critical / 选择性报告 critical / "
          "不支撑假设 critical(7→5 信号) / 不可复现 critical(7→6 信号) / 过度解读&效应量缺失 warn / "
          "无 claim skip / BH 兜底==numpy / findings(result-analysis) 往返"
          + ("" if _SHARED_OK else "(_shared 不可达,走诚实降级)") + "。")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(
        description="result-analysis 统计严谨/证据强度 Critical 门 producer"
                    "(p-hacking/不支撑假设/不可复现→critical→stage 7 exit 1;7→5/7→6 回炉发起方)")
    ap.add_argument("--spec", help="stat_spec JSON(project/claims/correction/comparisons_*/results_csv)")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--evidence-out", default="", help="把 evidence_strength.json 写到该路径(供下游卡措辞)")
    ap.add_argument("--json-out", default="", help="把完整结果门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())
    if not args.spec:
        ap.error("需要 --spec stat_spec.json(或 --selftest)")

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    result = build(spec, evidence_out=args.evidence_out)
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整结果门 → {args.json_out}", file=sys.stderr)
    if args.evidence_out and result.get("evidence_strength"):
        print(f"[EVIDENCE] evidence_strength.json → {args.evidence_out}", file=sys.stderr)
    if args.report:
        if result["findings"] is None:
            print("[WARN] _shared 不可达,无 findings 可写(诚实不假装)。", file=sys.stderr)
        else:
            pathlib.Path(args.report).write_text(
                json.dumps(result["findings"], ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[REPORT] light.findings.v1 → {args.report}"
                  f"(verdict={result['findings']['verdict']})", file=sys.stderr)
    sys.exit(1 if result.get("findings") and result["findings"]["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
