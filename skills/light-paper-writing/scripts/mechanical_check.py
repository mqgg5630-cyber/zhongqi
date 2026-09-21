#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mechanical_check.py — offline (no-API) mechanical issues for academic prose.

Catches what LanguageTool's generic grammar pass tends to miss in research
papers, and what reviewers flag fastest:

  1. Overclaim words      — unsupported strength adjectives/adverbs.
  2. AI-tone / filler      — phrases that read as machine-generated boilerplate.
  3. Hedge stacking        — piled-up hedges ("may possibly suggest").
  4. Passive overuse       — per-paragraph passive ratio over a threshold.
  5. Punctuation hygiene   — em-dash spacing, fullwidth punctuation in English,
                             double spaces, space-before-punctuation, Oxford-ish.

No network needed. Emits structured findings {line, col, category, issue,
suggestion, context}. Pure stdlib; runs anywhere.

Usage:
  python mechanical_check.py --file paper.txt
  python mechanical_check.py --text "..." --json
  echo "..." | python mechanical_check.py
"""
import argparse
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

# 挂接地基契约2(语义相似度)：把 result-analysis 证据强度卡里的 strong-档 claim 语义定位到草稿句子，
# 使 claim_strength 检查"措辞强度匹配证据强度"——强证据的强词不再误报降级，强证据被过度
# hedge 反而提示 under-claim（治"确定结果写得心虚"）。无 semantic_sim 时降级到子串匹配。
# 规范 bootstrap(向上走目录树找含 _shared 包的仓库根)，治 v1 硬编码 ../../_shared 在 v2 仓库根上移后必断之脆(见 _shared/README.md)。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.semantic_sim import similarity as _sem_sim  # noqa: E402
    _HAS_SEM = True
except Exception:
    _HAS_SEM = False

# 被动语态告警阈值：单段被动句占比超过此值 → 提示改写。经验默认值、可调（CLI --passive-threshold）。
# 0.4 = 一段里多数仍应是主动句的宽松线（学术写作允许方法段适度被动，故不设太低）；
# 仅对 ≥3 句的段落判定（短段被动占比噪声大）。非数据反推，按学科/期刊风格可调。
PASSIVE_RATIO_WARN = 0.4

# --- blacklists --------------------------------------------------------------
OVERCLAIM = [
    "significant", "significantly", "seminal", "novel", "groundbreaking",
    "revolutionary", "state-of-the-art", "cutting-edge", "remarkable",
    "remarkably", "dramatically", "drastically", "vastly", "tremendously",
    "extremely", "very", "highly effective", "extensive", "comprehensive",
    "superior", "outperforms", "best", "optimal", "perfect", "unprecedented",
    "clearly", "obviously", "undoubtedly", "certainly",
]
AI_TONE = [
    "in conclusion", "it is worth noting", "it is important to note",
    "it should be noted", "in today's world", "in the modern era",
    "delve into", "delving into", "a testament to", "plays a crucial role",
    "plays a vital role", "plays a pivotal role", "navigating the",
    "in the realm of", "shed light on", "pave the way", "paves the way",
    "leverage the power", "harness the power", "rich tapestry",
    "ever-evolving", "ever-changing", "first and foremost", "furthermore",
    "moreover", "in summary", "to summarize", "needless to say",
]
HEDGES = ["may", "might", "could", "possibly", "perhaps", "seem", "seems",
          "appear", "appears", "suggest", "suggests", "potentially",
          "arguably", "likely", "probably", "somewhat", "relatively"]

# 中文最小支撑（借英文词表思路，覆盖中文稿的夸大/AI腔；技能服务对象多为中文研究者）。
# 仅子串匹配（中文无词边界），命中即提示，是否真夸大仍由作者判断。
OVERCLAIM_ZH = ["显著", "极大提升", "大幅提升", "前所未有", "完美解决", "彻底解决",
                "首次", "突破性", "革命性", "最优", "最佳", "远超", "碾压",
                "毫无疑问", "显而易见", "众所周知", "完美", "极其有效"]
AI_TONE_ZH = ["综上所述", "值得注意的是", "需要指出的是", "在当今", "在当今时代",
              "随着……的发展", "扮演着重要角色", "起着至关重要的作用", "为……铺平了道路",
              "深入探讨", "首先", "其次", "总而言之", "不言而喻", "众所周知"]

# Hedging 校准阶梯：强主张词 → 建议的降级替换（证据不足时往右降）。
# 见 references/argument_review.md 第 2 节。只在出现这些强词时提示，
# 是否真该降级仍需看证据强度，由作者判断。
CLAIM_DOWNGRADE = {
    "prove": "show / demonstrate（除非是数学证明，否则别用 prove）",
    "proves": "shows / demonstrates",
    "proven": "shown",
    "conclusively": "（删，或换 the results indicate）",
    "definitively": "（删，或换 indicate）",
    "unprecedented": "to our knowledge the first",
    "guarantees": "is expected to / typically",
    "always": "in our experiments / consistently",
    "never": "in no observed case",
    "proves that": "suggests that / indicates that",
}

# passive: form of "be" + past participle (heuristic, accepts -ed and common irregulars)
PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being|am)\s+(\w+ed|done|made|shown|given|"
    r"found|seen|taken|used|built|set|known|held|kept|sent|put|drawn|"
    r"chosen|written|proposed|obtained|achieved|performed|trained)\b",
    re.IGNORECASE,
)

# 句切分缩写保护：这些缩写后的 . 不算句末，避免 et al./e.g./Fig. 1 被错误断句。
_ABBREV = ["et al", "e.g", "i.e", "cf", "vs", "Fig", "Eq", "Tab", "Sec", "Ref",
           "No", "Dr", "Prof", "approx", "etc", "resp"]


def strip_latex(text):
    """剥除 LaTeX 命令/数学/注释/环境，保留纯 prose 且**维护行号**（删的内容用等量空格/空行占位）。
    让 mechanical_check 能直接吃 .tex 不把 \\cite/$...$/宏命令当 prose 而爆误报。"""
    def _blank(m):
        # 用等长空白替换（保留换行以维持行号），$$...$$/environment 跨行也对齐
        return re.sub(r"[^\n]", " ", m.group(0))
    # 1. 行注释 % ...（非 \%）
    text = re.sub(r"(?<!\\)%[^\n]*", _blank, text)
    # 2. 行间/行内公式 $$...$$ / \[...\] / $...$（数学里的标点/significant 不算 prose）
    text = re.sub(r"\$\$.*?\$\$", _blank, text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", _blank, text, flags=re.S)
    text = re.sub(r"(?<!\\)\$[^$\n]*\$", _blank, text)
    # 3. 整段 environment（equation/align/figure/table/lstlisting/verbatim 等）剥成空白
    text = re.sub(r"\\begin\{(equation|align|gather|figure|table|lstlisting|verbatim|tabular|matrix)\*?\}.*?\\end\{\1\*?\}",
                  _blank, text, flags=re.S)
    # 4. 引用/标签类命令整体剥（\cite{..}/\ref{..}/\label{..}/\eqref{..}）
    text = re.sub(r"\\(cite[a-z]*|ref|eqref|label|autoref|cref)\s*\{[^}]*\}", _blank, text)
    # 5. 其余命令：\cmd[opt]{arg} → 保留 arg 文本（如 \textbf{重要} 留"重要"），去命令壳
    text = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?\s*\{([^{}]*)\}", lambda m: " " * (len(m.group(0)) - len(m.group(2))) + m.group(2), text)
    # 6. 无参命令 \alpha \\ \item 等 → 空白
    text = re.sub(r"\\[a-zA-Z]+\*?|\\\\|\\[,;:%&#_{}]", _blank, text)
    return text


def split_sentences(text):
    """缩写保护的句切分：先把缩写里的 . 临时替换成哨兵，切完再还原。比 (?<=[.!?])\\s+ 稳。"""
    SENT = "\x00"   # 哨兵：临时占位被保护的点
    tmp = text
    for ab in _ABBREV:
        tmp = re.sub(r"\b" + re.escape(ab) + r"\.", ab + SENT, tmp)
    # 小数点保护：数字.数字（用函数式替换避免替换串里的转义问题）
    tmp = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + SENT + m.group(2), tmp)
    parts = re.split(r"(?<=[.!?])\s+", tmp)
    return [p.replace(SENT, ".") for p in parts]


SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def linecol(text, off):
    prefix = text[:off]
    return prefix.count("\n") + 1, off - (prefix.rfind("\n") + 1) + 1


def ctx(text, s, e):
    return text[max(0, s - 25):e + 25].replace("\n", " ")


def add(out, text, s, e, cat, issue, sug):
    line, col = linecol(text, s)
    out.append({"line": line, "col": col, "category": cat, "issue": issue,
                "suggestion": sug, "context": ctx(text, s, e)})


def scan_phrases(text, out, words, cat, issue_tmpl, sug, exempt=None):
    for w in words:
        pat = r"\b" + re.escape(w).replace(r"\ ", r"\s+") + r"\b"
        for m in re.finditer(pat, text, re.IGNORECASE):
            if exempt and exempt(text, m):
                continue
            add(out, text, m.start(), m.end(), cat,
                issue_tmpl.format(w=m.group(0)), sug)


def _overclaim_exempt(text, m):
    """overclaim 上下文豁免：统计语境的 significant 合法；项目白名单（方法名）跳过。"""
    word = m.group(0).lower()
    window = text[max(0, m.start() - 25):m.end() + 30].lower()
    if word in ("significant", "significantly"):
        # 统计显著：后跟 difference/level/p< / 前有 statistically / 邻近有 p 值
        if re.search(r"statistical|p\s*[<=>]\s*0?\.\d|significan\w*\s+(difference|level|effect|at)", window):
            return True
    # 项目级白名单：方法/模型名（如 NovelNet、Optimal-X）——大写开头连写视为专名，跳过
    if word in ("novel", "optimal", "best", "superior"):
        # 命中词紧邻大写专名（NovelNet / the Optimal Transport）则可能是名字一部分
        tail = text[m.end():m.end() + 15]
        if re.match(r"[A-Z][a-zA-Z]", tail.lstrip()):
            return True
    return False


def check_passive(text, out, threshold=PASSIVE_RATIO_WARN):
    """Flag paragraphs whose passive-sentence ratio exceeds threshold."""
    para_start = 0
    for para in re.split(r"(\n\s*\n)", text):
        if para.strip() and not para.isspace():
            sents = [s for s in split_sentences(para) if s.strip()]
            if len(sents) >= 3:
                npass = sum(1 for s in sents if PASSIVE_RE.search(s))
                ratio = npass / len(sents)
                if ratio > threshold:
                    line, col = linecol(text, para_start)
                    out.append({
                        "line": line, "col": col, "category": "passive_overuse",
                        "issue": f"{npass}/{len(sents)} sentences passive "
                                 f"({ratio:.0%} > {threshold:.0%}).",
                        "suggestion": "Rewrite some sentences in active voice "
                                      "(e.g. 'We trained...' not 'was trained').",
                        "context": para.strip()[:60].replace("\n", " "),
                    })
        para_start += len(para)
    # also flag every individual passive (fine-grained), capped
    for i, m in enumerate(PASSIVE_RE.finditer(text)):
        if i >= 50:
            break
        add(out, text, m.start(), m.end(), "passive_voice",
            f"Passive construction '{m.group(0)}'.",
            "Consider active voice if the agent matters.")


def check_punctuation(text, out):
    for m in re.finditer(r"\w-{2,3}\w|\s—\w|\w—\s", text):
        add(out, text, m.start(), m.end(), "punctuation",
            "Em-dash spacing inconsistent (mix of -- and — / missing or stray spaces).",
            "Pick one style: spaced em-dash ' — ' or unspaced '—'; be consistent.")
    for m in re.finditer(r"[，。；：（）！？、“”‘’]", text):
        add(out, text, m.start(), m.end(), "punctuation",
            f"Fullwidth/CJK punctuation '{m.group(0)}' in English text.",
            "Replace with ASCII equivalent (, . ; : ( ) ! ? \" ').")
    for m in re.finditer(r"\S {2,}\S", text):
        add(out, text, m.start(), m.end(), "punctuation",
            "Multiple consecutive spaces.", "Collapse to a single space.")
    for m in re.finditer(r"\s+[,.;:!?]", text):
        add(out, text, m.start(), m.end(), "punctuation",
            "Space before punctuation.", "Remove the space before the mark.")


def check_hedge_stack(text, out):
    """Two+ hedges within a short window = wishy-washy。用迭代 offset 而非 text.find
    （修句子重复时定位到错误 offset 的 bug）。"""
    hedge_pat = r"\b(" + "|".join(HEDGES) + r")\b"
    cursor = 0
    for sent in split_sentences(text):
        s = text.find(sent, cursor)   # 从游标处往后找，避免重复句定位回开头
        if s < 0:
            s = cursor
        else:
            cursor = s + len(sent)
        hits = list(re.finditer(hedge_pat, sent, re.IGNORECASE))
        if len(hits) >= 2:
            words = ", ".join(h.group(0) for h in hits)
            add(out, text, s, s + len(sent), "hedge_stacking",
                f"Stacked hedges ({words}) weaken the claim.",
                "Keep at most one hedge; commit to the finding.")


def locate_strong_spans(text, evidence_strength):
    """用 semantic_sim 把 evidence_strength.json 里 evidence_grade=strong 的 claim 定位到草稿
    句子 span（char 偏移）。返回 [(start,end), ...]。绑定 result-analysis 证据强度，供 claim_strength 双向校准。"""
    spans = []
    if not evidence_strength:
        return spans
    sents = [(m.group().strip(), m.start(), m.end())
             for m in re.finditer(r"[^.!?。！？\n]+[.!?。！？]?", text) if m.group().strip()]
    for cl in (evidence_strength.get("claims") or []):
        if (cl.get("evidence_grade") or "").lower() != "strong":
            continue
        ctext = cl.get("text", "")
        best, bs = None, 0.0
        for s, st, en in sents:
            sim = _sem_sim(ctext, s) if _HAS_SEM else (1.0 if ctext and ctext in s else 0.0)
            if sim > bs:
                bs, best = sim, (st, en)
        if best and bs >= 0.5:
            spans.append(best)
    return spans


def _in_spans(off, spans):
    return any(a <= off < b for a, b in spans)


def check_claim_strength(text, out, strong_spans=None):
    """Hedging 校准阶梯：强主张词给降级替换建议（见 argument_review.md §2）。

    strong_spans：result-analysis 判为强证据的 claim 在草稿中的 span。命中其中的强主张词**豁免降级**
    （强证据配强词是对的，不该催降级）；同时若强证据 span 内堆叠 hedge → 反向提示 under-claim
    （确定结果写得心虚）。这把上下文无关词表升级为"措辞强度↔证据强度"双向校准。"""
    spans = strong_spans or []
    for word, repl in CLAIM_DOWNGRADE.items():
        pat = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        for m in pat.finditer(text):
            if _in_spans(m.start(), spans):
                continue  # 强证据豁免：强词有证据支撑，不催降级
            add(out, text, m.start(), m.end(), "claim_strength",
                f"Strong claim '{m.group(0)}' — match assertion strength to evidence.",
                f"If evidence is not conclusive, downgrade: {repl}")
    # under-claim：强证据 span 内出现 hedge → 提示上调措辞（治"确定结果写得心虚"）
    if spans:
        hedge_pat = re.compile(r"\b(" + "|".join(HEDGES) + r")\b", re.IGNORECASE)
        for a, b in spans:
            hm = hedge_pat.search(text, a, b)
            if hm:
                add(out, text, hm.start(), hm.end(), "under_claim",
                    f"Hedge '{hm.group(0)}' on a strong-evidence claim — under-claiming.",
                    "证据强（result-analysis 判 strong）却 hedge，可上调措辞（如 may improve→improves），别把确定结果写心虚。")


def scan_substr(text, out, words, cat, issue_tmpl, sug):
    """中文等无词边界语言：直接子串匹配（不加 \\b）。"""
    for w in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            add(out, text, i, i + len(w), cat, issue_tmpl.format(w=w), sug)
            start = i + len(w)


def run(text, passive_threshold=PASSIVE_RATIO_WARN, latex=False, evidence_strength=None):
    if latex:
        text = strip_latex(text)   # 行号保持，offset 仍对原文有效
    out = []
    strong_spans = locate_strong_spans(text, evidence_strength)
    scan_phrases(text, out, OVERCLAIM, "overclaim",
                 "Overclaim/unsupported intensifier '{w}'.",
                 "Replace with measurable evidence or delete.", exempt=_overclaim_exempt)
    scan_phrases(text, out, AI_TONE, "ai_tone",
                 "AI-tone / filler phrase '{w}'.",
                 "Cut or rewrite directly; reviewers read it as boilerplate.")
    # 中文稿支撑：中文夸大词/AI腔（子串匹配）
    scan_substr(text, out, OVERCLAIM_ZH, "overclaim",
                "中文夸大/无证据强调词「{w}」。", "改为可量化证据或删除（除非确有数据支撑，如'统计显著'）。")
    scan_substr(text, out, AI_TONE_ZH, "ai_tone",
                "中文 AI 腔/套话「{w}」。", "删或直接改写，审稿人视作模板腔。")
    check_hedge_stack(text, out)
    check_claim_strength(text, out, strong_spans=strong_spans)
    check_passive(text, out, threshold=passive_threshold)
    check_punctuation(text, out)
    out.sort(key=lambda f: (f["line"], f["col"]))
    cats = {}
    for f in out:
        cats[f["category"]] = cats.get(f["category"], 0) + 1
    return {"_meta": {"n_findings": len(out), "by_category": cats, "latex_stripped": latex},
            "findings": out}



def _selftest() -> int:
    sample = ("In conclusion, our novel method significantly outperforms all baselines. "
              "It is worth noting that the results was obtained and were evaluated . "
              "This may possibly suggest a remarkable improvement ， which proves that the method is state-of-the-art.")
    result = run(sample)
    meta = result["_meta"]
    cats = meta["by_category"]
    assert meta["n_findings"] >= 6, meta
    for cat in ("overclaim", "ai_tone", "hedge_stacking", "punctuation", "claim_strength"):
        assert cats.get(cat, 0) >= 1, cats

    # PP-2 overclaim 上下文豁免：统计语境的 significant 不报，裸 significant 报
    r_stat = run("The difference is statistically significant (p<0.01).")
    assert not any(f["category"] == "overclaim" and "significant" in f["issue"].lower()
                   for f in r_stat["findings"]), "统计语境 significant 不应报 overclaim"
    r_bare = run("This is a significant improvement over prior art.")
    assert any(f["category"] == "overclaim" for f in r_bare["findings"]), "裸 significant 应报"

    # PP-2 句切分缩写保护：et al./e.g. 不被错误断句
    sents = split_sentences("Smith et al. proposed X. We extend it, e.g. by adding Y. Done.")
    assert len(sents) == 3, f"缩写保护后应 3 句，得 {len(sents)}: {sents}"

    # PP-1 strip_latex：\cite/$...$/注释/environment 被剥，prose 保留且行号不变
    tex = ("We achieve \\textbf{good} results \\cite{smith2023}.\n"
           "$\\alpha = \\sum_i x_i$ shows significant gain.\n"
           "% TODO: this novel comment should vanish\n"
           "\\begin{equation} E=mc^2 \\end{equation}\n")
    stripped = strip_latex(tex)
    assert "smith2023" not in stripped, "\\cite 内容应被剥"
    assert "alpha" not in stripped and "mc^2" not in stripped, "数学/environment 应被剥"
    assert "good" in stripped, "\\textbf 的文本应保留"
    assert "TODO" not in stripped, "注释应被剥"
    assert stripped.count("\n") == tex.count("\n"), "行号(换行数)应保持"
    # latex 模式下注释里的 novel 不触发 overclaim
    r_tex = run(tex, latex=True)
    assert not any("smith2023" in f.get("context", "") for f in r_tex["findings"])

    # PP-5 中文支撑：中文夸大词/AI 腔被检出
    r_zh = run("本文首次提出该方法，大幅提升了性能，综上所述效果完美。")
    zh_cats = {f["category"] for f in r_zh["findings"]}
    assert "overclaim" in zh_cats, f"中文夸大词应报 overclaim: {r_zh['findings']}"
    assert "ai_tone" in zh_cats, f"中文 AI 腔(综上所述)应报: {r_zh['findings']}"

    # 证据强度绑定(挂 _shared/semantic_sim + result-analysis evidence_strength.json)：
    claim_txt = "Our method conclusively proves a clear improvement on accuracy."
    es_strong = {"claims": [{"text": "method conclusively proves clear improvement on accuracy",
                             "evidence_grade": "strong"}]}
    # 无证据卡：proves/conclusively 触发 claim_strength 降级建议
    base = run(claim_txt)
    assert any(f["category"] == "claim_strength" for f in base["findings"]), base["findings"]
    # 强证据卡：同一强词被豁免，不再催降级（强证据配强词是对的）
    bound = run(claim_txt, evidence_strength=es_strong)
    assert not any(f["category"] == "claim_strength" for f in bound["findings"]), \
        f"强证据应豁免强词降级: {bound['findings']}"
    # under-claim：强证据却 hedge → 提示上调
    hedged = "Our method may improve accuracy on all datasets."
    es_h = {"claims": [{"text": "method may improve accuracy on all datasets", "evidence_grade": "strong"}]}
    uc = run(hedged, evidence_strength=es_h)
    assert any(f["category"] == "under_claim" for f in uc["findings"]), \
        f"强证据 + hedge 应提示 under_claim: {uc['findings']}"
    # 弱证据卡：不豁免（强词仍催降级）
    es_weak = {"claims": [{"text": "method conclusively proves clear improvement on accuracy",
                           "evidence_grade": "weak"}]}
    weak = run(claim_txt, evidence_strength=es_weak)
    assert any(f["category"] == "claim_strength" for f in weak["findings"]), "弱证据不应豁免"

    print(f"[selftest] PASS mechanical_check findings={meta['n_findings']} "
          f"(+latex/豁免/缩写/中文/证据强度双向校准)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Offline mechanical paper check.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--text")
    g.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--passive-threshold", type=float, default=PASSIVE_RATIO_WARN,
                    help=f"段被动句占比告警阈值(默认 {PASSIVE_RATIO_WARN}，经验值可调，见脚本注释)")
    ap.add_argument("--latex", action="store_true",
                    help="输入是 .tex：先 strip_latex 去命令/数学/注释/环境再检查，避免误报")
    ap.add_argument("--evidence-map", help="result-analysis evidence_strength.json：strong 档 claim 豁免降级"
                                           "+过度 hedge 提示 under-claim（措辞强度↔证据强度双向校准）")
    ap.add_argument("--selftest", action="store_true", help="run offline synthetic self-test")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if args.text is not None:
        text = args.text
    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = ("In conclusion, our novel method significantly outperforms "
                "all baselines. It is worth noting that the results was "
                "obtained and were evaluated . This may possibly suggest a "
                "remarkable improvement ， which is clearly state-of-the-art.")
        print("[self-test: no input given, using built-in sample]\n", file=sys.stderr)

    # 自动识别 .tex 后缀
    latex = args.latex or bool(args.file and args.file.endswith(".tex"))
    evidence_strength = None
    if args.evidence_map:
        with open(args.evidence_map, encoding="utf-8") as f:
            evidence_strength = json.load(f)
    result = run(text, passive_threshold=args.passive_threshold, latex=latex,
                 evidence_strength=evidence_strength)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    m = result["_meta"]
    print(f"findings={m['n_findings']}  by_category={m['by_category']}")
    for f in result["findings"]:
        print(f"  L{f['line']}:C{f['col']} [{f['category']}] {f['issue']}")
        print(f"      → {f['suggestion']}")


if __name__ == "__main__":
    main()
