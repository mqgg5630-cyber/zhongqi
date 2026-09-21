#!/usr/bin/env python3
"""draft_lint.py — 论文草稿诚信门机检器（人判优先，机检兜底）。

检查项：
  1. 残留缺口标记：[MATERIAL GAP] / [RESULT GAP] / TODO（终稿门必须为 0）。
  2. 必备声明小节缺失：按**行首 markdown 标题**校验 Data Availability / Ethics / CRediT /
     Conflicts / Funding / AI Use（不再用全文子串，避免正文散句误判为"已有该 section"）。
  3. 高危结果句无显著性：SOTA/outperform/最优 等措辞与 p值/CI/±std 在**同句或相邻句窗口**
     共现才算通过（不再要求严格同行，治长段落/相邻句的误报）。
  4. 引用台账：抽取 DOI/arXiv（跳过 ``` 代码围栏与引用块，避免示例代码里的内容假阳），
     输出待 curl 核查清单。
  5. --claims：抽取候选事实句（含数字/比较/SOTA 措辞），播种 claim 台账（templates/claim_passport.md）。

用法：
  python draft_lint.py <draft.md> [--final] [--json] [--claims]
  python draft_lint.py --selftest

退出码：0 通过；1 发现需返工项；2 用法错误。
"""
import json
import os
import re
import sys

# 挂接共享地基契约(证据强度):消费 result-analysis 产出的 evidence_strength.json，
# 机械校验"正文措辞不强于统计证据"(evidence_contract 消费端，灭措辞夸大)。
# 规范 bootstrap(向上走目录树找含 _shared 包的仓库根)，治 v1 硬编码 ../../_shared 之脆(见 _shared/README.md)。
import pathlib  # noqa: E402
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.evidence_contract import lint_wording, load as _ev_load  # noqa: E402
    _HAS_EVIDENCE = True
except Exception:
    _HAS_EVIDENCE = False
try:
    _HERE = pathlib.Path(__file__).resolve().parent
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    import claim_binding as _claim_binding  # noqa: E402
    _HAS_CLAIM_BINDING = True
except Exception:
    _HAS_CLAIM_BINDING = False

GAP_PAT = re.compile(r"\[(?:MATERIAL GAP|RESULT GAP)\b[^\]]*\]|(?<![\w/])TODO\b")
# DOI 内部可含标点，但句末 "." / ";" 不属于 DOI。要求最后一位为字母、数字或右括号，
# 避免同一 DOI 因 prose 标点被抽成两个 citation candidates。
DOI_PAT = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]*[A-Za-z0-9)]")
ARXIV_PAT = re.compile(r"arXiv:\d{4}\.\d{4,5}", re.IGNORECASE)
HYPE_PAT = re.compile(r"\b(?:state[- ]of[- ]the[- ]art|SOTA|outperform\w*|best[- ]ever|超越|最优|优于)\b", re.IGNORECASE)
SIG_PAT = re.compile(r"p\s*[<=>]\s*0?\.\d+|95%\s*CI|±\s*\d|std", re.IGNORECASE)
# 候选事实句：含数字+百分号/指标提升/比较措辞 → 可能是需登记 claim 的事实陈述
CLAIM_HINT_PAT = re.compile(
    r"\d+(?:\.\d+)?\s*%|\bby\s+\d|提升|提高|降低|达到|improv\w*|reduc\w*|achiev\w*|"
    r"state[- ]of[- ]the[- ]art|SOTA|outperform\w*|优于|超越", re.IGNORECASE)

REQUIRED_SECTIONS = {
    "Data Availability": r"data\s+availability|数据可用",
    "Ethics": r"ethics|伦理",
    "CRediT": r"credit|author\s+contribution|作者贡献",
    "Conflicts of Interest": r"conflict|competing\s+interest|利益冲突",
    "Funding": r"funding|资助|基金",
    "AI Use Disclosure": r"ai\s+use|generative\s+ai|\bllm\b|ai\s+使用|生成式",
}


def _strip_code_fences(text):
    """剥除 ``` 围栏代码块（整段置空保留行号），避免示例代码里的 DOI/TODO/SOTA 假阳。"""
    out, in_fence = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append("")        # 围栏行本身置空，保留行号对齐
            continue
        out.append("" if in_fence else ln)
    return out


def _split_sentences(text):
    """粗切句（中英）：按 。！？.!? 和换行切，返回句列表。用于同句/相邻句共现判定。"""
    # 先把代码块剥掉再切句
    clean = "\n".join(_strip_code_fences(text))
    parts = re.split(r"(?<=[。！？.!?])\s+|\n+", clean)
    return [p.strip() for p in parts if p.strip()]


def _section_titles(text):
    """抽行首 markdown 标题（# / ## …）的文本，用于校验真有该 section 而非全文子串。"""
    titles = []
    for ln in _strip_code_fences(text):
        m = re.match(r"^#{1,6}\s+(.*)", ln)
        if m:
            titles.append(m.group(1).strip().lower())
    return titles


def check_evidence(text, evidence_path, claim_map_path=None):
    """消费 result-analysis 的 evidence_strength.json，校验正文措辞不强于证据(evidence_contract 消费端)。

    对每条 claim：用其证据 grade 的允许措辞档，扫正文是否出现超档断言动词。
    超档 → FAIL 级 finding(定位+建议降级)。还检查：正文出现的数值 claim 措辞
    是否有对应证据支撑(grade=none 却用强断言尤其危险)。
    返回 (findings, n_violations)。
    """
    findings = []
    if not _HAS_EVIDENCE:
        findings.append(("WARN", "evidence_contract 契约不可用(_shared 未就位)，跳过措辞校验"))
        return findings, 0
    if not os.path.exists(evidence_path):
        findings.append(("WARN", f"未找到 evidence_strength.json: {evidence_path}"
                         "（先在 result-analysis 跑 stat_rigor_gate.py --evidence-out 产出）"))
        return findings, 0
    ev = _ev_load(evidence_path)
    if ev.get("schema") != "light.evidence_strength.v1":
        findings.append(("WARN", f"证据文件 schema 非预期: {ev.get('schema')}"))
        return findings, 0
    if claim_map_path is not None:
        if not _HAS_CLAIM_BINDING:
            findings.append(("FAIL", "claim_binding 模块不可用，不能执行逐 claim 措辞核验"))
            return findings, 1
        if not os.path.exists(claim_map_path):
            findings.append(("FAIL", f"未找到 light.paper_claims.v1: {claim_map_path}"))
            return findings, 1
        claim_map = _claim_binding.load_claim_map(claim_map_path)
        report = _claim_binding.evaluate_bindings(text, ev, claim_map)
        findings.append(("INFO", f"逐 claim 证据核验：登记 {len(report['claims'])} 条；"
                                 "每条只使用自己的 evidence_claim_ids"))
        for item in report["coverage_errors"]:
            findings.append((
                "FAIL",
                f"{item.get('locator')}: {item.get('message')}"
                f" [claim={item.get('claim_id') or '<unregistered>'}]"))
        for item in report.get("result_card_errors", []):
            findings.append((
                "FAIL",
                f"{item.get('locator')}: {item.get('message')}"
                f" [claim={item.get('claim_id') or '<unregistered>'}] → {item.get('suggestion')}"))
        for item in report["overclaims"]:
            findings.append((
                "FAIL",
                f"{item.get('locator')}: {item.get('message')}"
                f" [claim={item.get('claim_id')}] → {item.get('suggestion')}"))
        for item in report["traceability_warnings"]:
            findings.append((
                "WARN",
                f"{item.get('locator')}: {item.get('message')}"
                f" [claim={item.get('claim_id')}]"))
        for item in report.get("guardrail_warnings", []):
            findings.append((
                "WARN",
                f"{item.get('locator')}: {item.get('message')}"
                f" [claim={item.get('claim_id')}] → {item.get('suggestion')}"))
        total = (
            len(report["coverage_errors"])
            + len(report.get("result_card_errors", []))
            + len(report["overclaims"])
        )
        if total == 0:
            findings.append(("INFO", "✓ 逐 claim 覆盖、result-card guardrail handoff 与措辞强度通过；"
                                     "无关最高证据档未参与兜底"))
        return findings, total
    claims = ev.get("claims", [])
    findings.append(("INFO", f"证据校验：载入 {len(claims)} 条 claim 的证据档"
                     f"（来源 {ev.get('source','?')}）"))
    findings.append(("WARN", "未提供 --claim-map：本次仅运行旧式全文×每档启发式，可能误报；"
                             "canonical stage-8 门要求 light.paper_claims.v1 逐 claim 绑定"))
    total_viol = 0
    for cl in claims:
        viols = lint_wording(text, cl)
        hard = [v for v in viols if v.get("matched")]
        if hard:
            total_viol += len(hard)
            grade = cl.get("evidence_grade")
            findings.append(("FAIL", f"措辞强于证据[{grade}] · claim '{cl.get('claim_id')}': "
                             f"{len(hard)} 处超档"))
            for v in hard[:5]:
                findings.append(("  ", f"{v['loc']}: '{v['matched']}' → {v['suggestion']}"))
    if total_viol == 0 and claims:
        findings.append(("INFO", "✓ 正文措辞未超过任何 claim 的证据档"))
    return findings, total_viol


def lint(text, final=False, want_claims=False, evidence_path=None, claim_map_path=None):
    findings = []
    code_stripped = _strip_code_fences(text)   # 行级、保留行号
    lines = code_stripped

    # 1. 残留缺口标记（跳过代码块后）
    gaps = [(i + 1, m.group(0)) for i, ln in enumerate(lines) for m in GAP_PAT.finditer(ln)]
    if gaps:
        sev = "FAIL" if final else "WARN"
        findings.append((sev, f"残留缺口标记 {len(gaps)} 处" + (" — 终稿门要求清零" if final else " — 初稿可暂留")))
        for ln_no, tok in gaps[:20]:
            findings.append(("  ", f"L{ln_no}: {tok}"))

    # 2. 必备声明：按行首 markdown 标题校验（不再全文子串）
    titles = _section_titles(text)
    title_blob = " | ".join(titles)
    missing = [name for name, pat in REQUIRED_SECTIONS.items() if not re.search(pat, title_blob, re.I)]
    if missing:
        findings.append(("WARN", "缺必备声明小节(按标题校验): " + ", ".join(missing)))

    # 3. 高危结果句缺显著性：SOTA 措辞与显著性在同句或相邻句窗口共现才算通过
    sents = _split_sentences(text)
    for i, s in enumerate(sents):
        if HYPE_PAT.search(s):
            window = " ".join(sents[max(0, i - 1):i + 2])  # 前一句+本句+后一句
            if not SIG_PAT.search(window):
                findings.append(("WARN", f"夸大/SOTA 措辞但邻近无显著性(p/CI/±std): {s[:70]}"))

    # 4. 引用台账（代码块已剥）
    clean_text = "\n".join(code_stripped)
    dois = sorted(set(DOI_PAT.findall(clean_text)))
    arxivs = sorted(set(ARXIV_PAT.findall(clean_text)))
    if dois or arxivs:
        findings.append(("INFO", f"引用待核: {len(dois)} DOI + {len(arxivs)} arXiv（需 curl 实测记 HTTP 码）"))
        for d in dois[:20]:
            findings.append(("  ", f'curl -sI -H "Accept: application/vnd.citationstyles.csl+json" https://doi.org/{d}'))
        for a in arxivs[:20]:
            aid = a.split(":", 1)[1]
            findings.append(("  ", f"curl -sI https://arxiv.org/abs/{aid}"))

    # 5. 候选事实句抽取（播种 claim 台账）
    claims = []
    if want_claims:
        for s in sents:
            if CLAIM_HINT_PAT.search(s) and not GAP_PAT.search(s):
                claims.append(s[:160])
        if claims:
            findings.append(("INFO", f"候选事实句 {len(claims)} 条（登记到 templates/claim_passport.md 逐条核查）"))
            for c in claims[:20]:
                findings.append(("  ", f"claim? {c}"))

    # 6. 证据强度措辞门（--evidence，evidence_contract 消费端）
    n_evidence_viol = 0
    if evidence_path is not None:
        ev_findings, n_evidence_viol = check_evidence(
            text, evidence_path, claim_map_path=claim_map_path)
        findings.extend(ev_findings)

    failed = any(sev == "FAIL" for sev, _ in findings)
    result = {
        "findings": findings, "failed": failed,
        "n_gaps": len(gaps), "missing_sections": missing,
        "n_doi": len(dois), "n_arxiv": len(arxivs),
        "candidate_claims": claims,
        "n_evidence_violations": n_evidence_viol,
    }
    return findings, failed, result


def _selftest():
    bad = """# Title
We achieve state-of-the-art results, outperforming all baselines.
Tail accuracy improves by [RESULT GAP: 待实验].
Prior work [MATERIAL GAP: 需引用] showed something.
See doi 10.1109/CVPR.2016.90 and arXiv:1512.03385 for ResNet.
TODO: add ablation.
"""
    good = """# Title
We improve tail accuracy by 4.2 points (p<0.001, ±0.3 std) over the baseline.
## Data Availability
Synthetic data; code at anonymous repo.
## Ethics Statement
No human or animal subjects.
## CRediT Author Contributions
A.B.: all.
## Conflicts of Interest
None.
## Funding
No specific grant.
## AI Use Disclosure
LLM used for language editing; authors verified all content.
"""
    print("=== selftest: BAD draft (初稿门) ===")
    f1, fail1, r1 = lint(bad, final=False)
    for sev, msg in f1:
        print(f"[{sev}] {msg}")
    print(f"final-mode fail? {lint(bad, final=True)[1]}")

    print("\n=== selftest: GOOD draft (终稿门) ===")
    f2, fail2, r2 = lint(good, final=True)
    for sev, msg in f2:
        print(f"[{sev}] {msg}")

    # 断言：bad 在终稿门必失败；good 在终稿门不因 GAP 失败且无缺失声明
    assert lint(bad, final=True)[1] is True, "BAD 应在终稿门 FAIL"
    assert fail2 is False, "GOOD 不应有 FAIL 级问题"
    assert not any("缺必备声明" in m for _, m in f2), "GOOD 不应缺声明"
    assert any("引用待核" in m for _, m in f1), "BAD 应抽出引用待核"
    assert any("无显著性" in m for _, m in f1), "BAD 应标出无显著性的 SOTA 句"
    punctuated_doi = ("Dataset DOI 10.24432/C5DW2B. "
                      "The same DOI 10.24432/C5DW2B; metadata follows.")
    _, _, rd = lint(punctuated_doi)
    assert rd["n_doi"] == 1, "句末标点不得制造重复 DOI candidate"

    # 新增断言1：相邻句共现——SOTA 句与 p 值分处相邻句应判通过（不误报）
    adjacent = ("We achieve state-of-the-art results.\n"
                "The improvement is significant (p<0.001, ±0.2 std).")
    fa, _, _ = lint(adjacent)
    assert not any("无显著性" in m for _, m in fa), "相邻句有显著性不应误报"

    # 新增断言2：代码块里的 TODO/DOI/SOTA 不应被当真命中
    fenced = ("# Title\n```python\n# TODO: refactor\nx = 'state-of-the-art'\n"
              "# see 10.1109/CVPR.2016.90\n```\nReal text with no issues.\n"
              "## Data Availability\nx\n## Ethics\nx\n## CRediT\nx\n## Conflicts of Interest\nx\n"
              "## Funding\nx\n## AI Use Disclosure\nx\n")
    ff, _, rf = lint(fenced, final=True)
    assert rf["n_gaps"] == 0, f"代码块里的 TODO 不应计入 gap: {rf['n_gaps']}"
    assert rf["n_doi"] == 0, f"代码块里的 DOI 不应抽取: {rf['n_doi']}"
    assert not any("无显著性" in m for _, m in ff), "代码块里的 SOTA 字符串不应触发"

    # 新增断言3：必备声明按标题校验——正文散句含 'ethics' 但无标题 → 仍报缺失
    body_only = "# Title\nWe discuss ethics and funding informally in this paragraph.\n"
    fb, _, rb = lint(body_only, final=True)
    assert "Ethics" in rb["missing_sections"], "正文散句不应算作有 Ethics section"
    assert "Funding" in rb["missing_sections"], "正文散句不应算作有 Funding section"

    # 新增断言4：--claims 抽候选事实句
    fc, _, rc = lint("We improve accuracy by 4.2% over baseline.\nThe sky is blue.",
                     want_claims=True)
    assert rc["candidate_claims"], "应抽出含数字提升的候选事实句"
    assert any("4.2%" in c for c in rc["candidate_claims"]), rc["candidate_claims"]

    # 新增断言5：证据强度措辞门（--evidence，evidence_contract 消费端）
    if _HAS_EVIDENCE:
        import tempfile
        from _shared.evidence_contract import build_evidence_json, save as _save
        # 构造一条 weak 证据的 claim
        ev = build_evidence_json([{
            "claim_id": "acc:ours_vs_base", "text": "ours vs base",
            "q_fdr": 0.03, "effect_size": 0.2, "ci95": [0.05, 0.4], "n": 200}])
        with tempfile.TemporaryDirectory() as td:
            ep = os.path.join(td, "evidence_strength.json")
            _save(ev, ep)
            # 超档措辞 → FAIL
            over = "We demonstrate that ours significantly outperforms the baseline."
            fo, failo, ro = lint(over, evidence_path=ep)
            assert failo and ro["n_evidence_violations"] > 0, "弱证据下强断言应 FAIL"
            assert any("措辞强于证据" in m for _, m in fo), fo
            # 合规措辞 → 不因证据门 FAIL
            ok = "Our results may suggest a modest gain over the baseline."
            fok, failok, rok = lint(ok, evidence_path=ep)
            assert rok["n_evidence_violations"] == 0, f"合规弱措辞不应违规: {fok}"
            # 逐 claim 回归：strong A 不能兜底未登记的强断言 B
            mixed_ev = build_evidence_json([{
                "claim_id": "A", "text": "A", "q_fdr": 0.001,
                "effect_size": 0.9, "ci95": [0.4, 1.3], "n": 120}, {
                "claim_id": "B", "text": "B", "q_fdr": 0.3,
                "effect_size": 0.1, "ci95": [-0.2, 0.4], "n": 120}])
            _save(mixed_ev, ep)
            mixed_draft = ("Claim A demonstrates a reliable improvement.\n"
                           "Claim B significantly outperforms every baseline.")
            claim_map = {
                "schema": "light.paper_claims.v1",
                "draft_sha256": _claim_binding.draft_sha256(mixed_draft),
                "claims": [{
                    "claim_id": "C-A",
                    "text": "Claim A demonstrates a reliable improvement.",
                    "locator": "draft.md:L1",
                    "claim_type": "RESULT",
                    "evidence_claim_ids": ["A"],
                    "source_locators": ["evidence_strength.json#A"],
                    "result_card": {
                        "claim_id": "A",
                        "locator": "analysis/result-card-A.json",
                        "sha256": "c" * 64,
                        "decision": "CLAIM_READY",
                        "language_strength": "IMPROVES",
                        "guardrail_summary": {
                            "required": True,
                            "status": "PASS",
                            "claim_impact": "允许主 claim。",
                            "evidence_locator": "analysis/guardrails.json#A",
                        },
                    },
                }],
            }
            cp = os.path.join(td, "claim_plan.json")
            pathlib.Path(cp).write_text(
                json.dumps(claim_map, ensure_ascii=False), encoding="utf-8")
            fm, failm, _ = lint(
                mixed_draft, evidence_path=ep, claim_map_path=cp)
            assert failm and any(
                "未落入任何 claim text" in msg for _, msg in fm), fm
        print("[selftest] 证据强度措辞门：弱证据下 demonstrate/significantly 被拦，hedge 措辞放行")
    else:
        print("[selftest] WARN: evidence_contract 不可用，跳过 --evidence 测试")

    print("\nALL SELFTEST ASSERTIONS PASSED")


def main(argv):
    if len(argv) == 2 and argv[1] == "--selftest":
        _selftest()
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    final = "--final" in argv
    as_json = "--json" in argv
    want_claims = "--claims" in argv
    # --evidence <path>：消费 result-analysis 的 evidence_strength.json 做措辞门
    evidence_path = None
    if "--evidence" in argv:
        ei = argv.index("--evidence")
        if ei + 1 < len(argv) and not argv[ei + 1].startswith("--"):
            evidence_path = argv[ei + 1]
        else:
            print("[用法] --evidence 需跟 evidence_strength.json 路径")
            return 2
    claim_map_path = None
    if "--claim-map" in argv:
        ci = argv.index("--claim-map")
        if ci + 1 < len(argv) and not argv[ci + 1].startswith("--"):
            claim_map_path = argv[ci + 1]
        else:
            print("[用法] --claim-map 需跟 light.paper_claims.v1 路径")
            return 2
    pos = [a for i, a in enumerate(argv[1:], 1)
           if not a.startswith("--")
           and not (evidence_path and a == evidence_path)
           and not (claim_map_path and a == claim_map_path)]
    path = pos[0]
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    findings, failed, result = lint(text, final=final, want_claims=want_claims,
                                    evidence_path=evidence_path,
                                    claim_map_path=claim_map_path)
    if as_json:
        print(json.dumps({"failed": result["failed"], "n_gaps": result["n_gaps"],
                          "missing_sections": result["missing_sections"],
                          "n_doi": result["n_doi"], "n_arxiv": result["n_arxiv"],
                          "n_candidate_claims": len(result["candidate_claims"]),
                          "n_evidence_violations": result.get("n_evidence_violations", 0),
                          "findings": [{"sev": s.strip(), "msg": m} for s, m in findings]},
                         ensure_ascii=False, indent=2))
    else:
        for sev, msg in findings:
            print(f"[{sev}] {msg}")
        print("\n==> " + ("FAIL: 有需返工项" if failed else "PASS: 无 FAIL 级问题（WARN 仍需人判）"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
