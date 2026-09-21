#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""citation_verify_gate.py — citation 的**防幻觉引用(诚信门 critical) producer**。

蓝图 §4.3-10 的「及格线」:引用真实性 + 关联/权威/时效/中外占比 + 格式合规。本脚本把"引用核实"
编排成机读 `light.findings.v1`(producer=**citation**)。门名对齐 `STAGE_GATES[10]=[citation_verify]`
(spec §4.2 citation Critical=**幻觉引用/查无此文(诚信门)**;warn=locator 不支撑、格式):

  ① **citation_verify(查无此文/嵌合引用)= critical(诚信门)**:编排同目录 `verify_refs` 的多源核实。
     两种且仅两种 critical 形态:
       - **CONFIRMED-MISSING**:DOI RA 明确不存在且 Crossref+DataCite 都 404。
       - **CHIMERIC(嵌合)**:真实标识符与声称 title/authors/year 多字段冲突。
     任一 → 阻断 → 被总控 `run_checkpoint --stage 10` 聚合 **exit 1**。
     **诚实分野(铁律 2)**:**网络不可达(code=0/`unverified_offline`)= UNRESOLVED,绝不判幻觉** →
     降级 warn(「未核验,联网重跑」,不放行也不诬陷),区别于"连上了但查无"的 CONFIRMED-MISSING。
     issue **不带任何跨阶段路由信号** → `reroute --stage 10` 给 **manual = 本阶段内修**(找到真实引用 /
     换正确 DOI / 删除查无来源的引用)。**citation 无回边出边(ROUTES 无 key 10),自身门 fail 在 stage 10 内修**,
     不回炉上游(与 figure/result-analysis/paper-writing 不同——它不是回边发起方)。

  ② **metadata_match(元数据不符)= warn**:DOI 能解析但所引标题/年份/作者与 DOI 实际元数据不符
     (所引标题 vs 实际标题相似度低 / 作者删漏换序 / 跨源不一致)。**warn 非 critical**:可能引错 DOI 或
     副标题·译名差异,机器分不清"引错"与"幻觉",诚实降级交人核对(嵌合「真标题配错作者」已单列 critical)。
  ③ **reference_quality(时效/自引/预印本)= warn**:近 2 年前沿缺失、自引率偏高、含预印本(未经同行评审)。
     中外占比只如实报数不判对错(诚实:无放之四海的正确比例,依领域/venue 而定)。
  ④ **format_compliance(\\cite↔.bib 对账)= warn**:编排同目录 `citekey_audit`——引了但 .bib 未定义(编译出 ??)、
     .bib 重复定义、冗余键。**warn 非 critical**(编译报错的硬门归 typesetting stage 11;格式细节是 warn)。
  ⑤ **relevance_edge=warn**:同时消费 claim↔citation review 与论文 A→B 开放索引边。
     元数据命中不等于语义支持；RELATED_ONLY/PARTIAL/UNSUPPORTED/REVIEW_REQUIRED 都留人工复核警报。
   ※ **retraction_xref = 不判定,只指针(skip/info)**:`verify_refs` 从 Crossref `updated-by` 读取适用于原文的更新事实
     **不进 citation 门的 verdict**——**撤稿是 research-ethics `check_retractions.py` 的域(非重叠)**,本门只把命中
     条目作 info 指针交它复核。查重同理归 research-ethics `text_overlap.py`。citation 只管**存在性/元数据/格式/关联**。

这是 **v2 净新增的接线**(与 paper-writing `claim_evidence_gate`、figure `visual_honesty_gate`、result-analysis
`stat_rigor_gate` 同构):**编排港来纯工具 + 接 `_shared` 规范 bootstrap → critical findings producer**,**不重造取数**——
  - 在线核实:同目录 `verify_refs`(DOI RA + Crossref/DataCite 注册源 + PubMed/S2/OpenAlex 独立字段源)。
  - 引用边:同目录港来 `verify_citation_edge`(OpenCitations/Semantic Scholar,免 key)。
  - 格式对账:同目录港来 `citekey_audit`(纯 stdlib 离线)。

诚实约定(名实对齐见 SKILL,铁律 2):
- **网络查无 ≠ 一定不存在**:端点限流(Crossref 50 req/s)、收录滞后会假阴 → 分 UNRESOLVED vs CONFIRMED-MISSING,
  绝不把"暂时查不到"硬判成"幻觉"。**critical 仅对"连上了但查无"+"嵌合"两种确定形态生效。**
- **元数据不符 = warn 非 critical**:DOI 能解析却与所引不符,可能引错 DOI(typo)亦可能幻觉,机器分不清 → 交人。
- **格式机检有边界**:citekey 对账只核 \\cite↔.bib 键集,GB/T 7714/IEEE/APA 的精确排版由 `doi_to_any` 出件、终判靠人/typesetting。
- **免 key**:DOI RA/Crossref/DataCite/PubMed/OpenCitations/doi.org 为核心公开路径；
  OpenAlex 需免费 key，仅作增强。缺 key 不等于缺第二源，且绝不导致 missing。
- **_shared 不可达** → findings 诚实降级 None(不假装产机读交接)。

用法:
  # 离线:消费已产出的 verify_refs 报告 + 可选 citekey 对账 + 引用边报告 → 出 findings
  python citation_verify_gate.py --refs-report verify_refs.json --tex paper.tex --bib refs.bib --report cite_findings.json
  # 在线:直接核一份参考文献清单(每条 {doi,title,first_author,authors,year}),实跑 verify_refs
  python citation_verify_gate.py --refs-spec refs.json --online --report cite_findings.json
  python citation_verify_gate.py --selftest

refs-spec / refs.json(在线核实输入,列表):
  [{"doi":"10.1038/...","title":"声称标题","first_author":"Smith","authors":["Smith","Wang"],"year":2023}, ...]
"""
from __future__ import annotations
import argparse
import datetime
import json
import os
import pathlib
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

THIS_YEAR = datetime.date.today().year

# 同目录港来的纯工具(复用不重造:在线核实 / 引用边 / \cite↔.bib 对账)。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    import verify_refs as vr            # noqa: E402  在线多源核实 + 嵌合 + publication updates
    _HAS_VR = True
except Exception:
    _HAS_VR = False
try:
    import citekey_audit as cka         # noqa: E402  \cite↔.bib 对账(纯 stdlib 离线)
    _HAS_CKA = True
except Exception:
    _HAS_CKA = False

# 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根,治硬编码 parents[N] 之脆。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
    from _shared.gate_runner import run_gates                                # noqa: E402
    _SHARED_OK = True
except ImportError:
    _SHARED_OK = False

_TITLE_SIM_WARN = getattr(vr, "TITLE_SIM_WARN", 0.6) if _HAS_VR else 0.6


def _hash(value) -> bool:
    return bool(re.fullmatch(r"sha256:[0-9a-fA-F]{64}", str(value or "")))


# ───────────────────────── 工具:把一条 verify_refs 记录判成四态 ─────────────────────────
def _classify_ref(rec: dict) -> str:
    """CONFIRMED / CHIMERIC / CONFIRMED-MISSING / UNAVAILABLE / UNRESOLVED。

    诚实分野(铁律 2)——网络查无 ≠ 一定不存在:
      - CHIMERIC   : 真 DOI/标题 + 幻觉作者(verify_refs is_chimeric)→ critical。
      - CONFIRMED  : 注册源字段 + 第二独立字段源一致确认。
      - CONFIRMED-MISSING : DOI RA 明确不存在且 Crossref+DataCite 都 404。
      - UNAVAILABLE: 网络/限流/5xx；UNRESOLVED: 注册/字段证据不完整。二者都不判幻觉。
    """
    if rec.get("is_chimeric"):
        return "CHIMERIC"
    declared = str(rec.get("status") or "").upper()
    if declared in {"CONFIRMED", "CONFIRMED-MISSING", "UNAVAILABLE", "UNRESOLVED"}:
        return declared
    if rec.get("unverified_offline"):
        return "UNRESOLVED"
    if rec.get("found_crossref") or rec.get("found_openalex"):
        return "CONFIRMED"
    cr = (rec.get("http") or {}).get("crossref")
    if cr in (0, None):
        return "UNRESOLVED"   # 网络失败/未查到响应码 → 未核验
    # 旧 v1 报告没有 DOI RA/DataCite 联合证据，不能把 Crossref 单个非零状态升级成 missing。
    return "UNRESOLVED"


def _ref_label(rec: dict) -> str:
    dois = (rec.get("identifiers") or {}).get("doi") or []
    meta = rec.get("metadata") or {}
    return (rec.get("doi") or (dois[0] if dois else "")
            or rec.get("title") or meta.get("title") or "(无 DOI/标题)")[:80]


# ───────────────────────── 六个 gate 函数(接 _shared) ─────────────────────────
# critical 措辞红线:citation 无回边出边(ROUTES 无 key 10),issue **只指本阶段内修**
# (找到真引用/换正确 DOI/删查无 claim),不带任何跨阶段路由信号 → reroute --stage 10 给 manual。
def _citation_verify_gate(art: dict) -> "GateResult":
    """防幻觉引用(critical,诚信门):查无此文 / 嵌合引用 → 阻断 → 本阶段内修(reroute→manual)。"""
    refs = art["refs"]
    if not refs:
        return GateResult("citation_verify", "skip", "info", [],
                          note="未提供参考文献核验记录(--refs-report / --refs-spec --online):防幻觉引用门跳过。")
    finds, n_unresolved, n_unavailable, n_confirmed = [], 0, 0, 0
    for rec in refs:
        cls = _classify_ref(rec)
        if cls == "CONFIRMED":
            n_confirmed += 1
            continue
        if cls == "UNRESOLVED":
            n_unresolved += 1
            continue
        if cls == "UNAVAILABLE":
            n_unavailable += 1
            continue
        label = _ref_label(rec)
        if cls == "CONFIRMED-MISSING":
            http = rec.get("http") or {}
            finds.append(Finding(
                loc=f"ref:{label}",
                issue=f"查无此文:DOI『{label}』经 DOI RA 明确不存在且 Crossref/DataCite 均 404",
                fix="在本阶段内修:核对并替换为该文献的真实 DOI,或删除这条无法核实来源的引用;"
                    "切勿保留查无此文的引用(citation 无回边,自身门在 stage 10 内修)",
                evidence=("verdict=CONFIRMED-MISSING;"
                          f"http.doi_ra={http.get('doi_ra')};http.crossref={http.get('crossref')};"
                          f"http.datacite={http.get('datacite')}"),
                rule="citation_verify.doi_not_found"))
        else:  # CHIMERIC
            chi = [e.get("msg", "") for e in rec.get("errors", []) if "嵌合" in e.get("msg", "")]
            finds.append(Finding(
                loc=f"ref:{label}",
                issue=("嵌合引用(Chimeric):真实标识符与声称的 title/authors/year 多字段冲突"
                       f"（{rec.get('mismatch_fields') or 'author mismatch'}）"),
                fix="在本阶段内修:逐源核对真实题名/作者/年份，换正确 DOI 或删除该引用；不自动覆盖原引用",
                evidence=(chi[0] if chi else "is_chimeric=True"),
                rule="citation_verify.chimeric"))
    if not finds:
        if n_unresolved or n_unavailable:
            return GateResult(
                "citation_verify", "warn", "major",
                [Finding(loc="refs",
                         issue=(f"{n_unavailable} 条 UNAVAILABLE、{n_unresolved} 条 UNRESOLVED"
                                "（网络/限流/第二源证据不完整，均非查无此文）"),
                         fix="联网重跑 verify_refs 再判真实性;在此之前不可当作已核验通过",
                         rule="citation_verify.unresolved")],
                note=(f"{n_confirmed} 条双源 CONFIRMED；{n_unavailable} 条 UNAVAILABLE、"
                      f"{n_unresolved} 条 UNRESOLVED。安全/网络不可达不扩大 critical 面。"))
        return GateResult("citation_verify", "pass", "info", [],
                           note=f"{n_confirmed} 条引用均经注册源 + 第二独立字段源确认,无查无此文/嵌合引用。"
                               "诚实局限:在线核实只证'存在 + 作者匹配',不证内容/结论正确。")
    note = (f"防幻觉引用(critical,诚信门,spec §4.2):查无此文/嵌合引用 {len(finds)} 条 → run_checkpoint "
            f"--stage 10 exit 1。**本阶段内修**(找到真引用/换正确 DOI/删查无 claim;citation 无回边出边→"
             f"reroute 给 manual)。{n_unresolved + n_unavailable} 条不可用/未解决证据不判幻觉。")
    return GateResult("citation_verify", "fail", "critical", finds, note=note)


def _metadata_match_gate(art: dict) -> "GateResult":
    """元数据不符(warn):DOI 能解析但所引标题/作者/年与实际不符(嵌合已单列 critical;此处为可疑非确凿)。"""
    refs = art["refs"]
    if not refs:
        return GateResult("metadata_match", "skip", "info", [], note="无核验记录:元数据一致性门跳过。")
    finds = []
    for rec in refs:
        if _classify_ref(rec) != "CONFIRMED":
            continue   # 查无/嵌合/未核验归 citation_verify,不在此门重复
        label = _ref_label(rec)
        sim = rec.get("claimed_title_sim")
        if sim is not None and sim < _TITLE_SIM_WARN:
            finds.append(Finding(
                loc=f"ref:{label}",
                issue=f"所引标题与 DOI 实际标题相似度低({sim})——DOI 可能指向无关论文或引错 DOI",
                fix="核对:要么 DOI 错(换正确 DOI),要么所引文献信息有误;确认非'真 DOI 配错论文'式幻觉",
                evidence=f"claimed_title_sim={sim}", rule="metadata_match.title_mismatch"))
        adiff = rec.get("author_set_diff") or {}
        if adiff.get("verdict") in ("author_deletion", "reordered"):
            finds.append(Finding(
                loc=f"ref:{label}",
                issue=f"作者列表与真实不一致({adiff['verdict']}):删 {adiff.get('removed')} 换序 {adiff.get('reordered')}",
                fix="核对作者顺序/完整性后改正", rule="metadata_match.author_diff"))
        for conflict in rec.get("field_conflicts") or []:
            finds.append(Finding(
                loc=f"ref:{label}",
                issue=f"逐源字段冲突:{conflict.get('field')}={conflict.get('values')}",
                fix="保留逐源值并人工裁决；不得用 fuzzy match 自动覆盖原引用",
                evidence=json.dumps(conflict, ensure_ascii=False),
                rule="metadata_match.cross_source"))
    if not finds:
        return GateResult("metadata_match", "pass", "info", [],
                          note="已确认存在的引用元数据(标题/作者/年)与 DOI 实际一致。")
    return GateResult("metadata_match", "warn", "major", finds,
                      note="元数据不符(warn,非阻断):DOI 能解析但所引与实际不符,可能引错 DOI 或副标题/译名差异,"
                           "机器分不清'引错'与'幻觉'(嵌合'真标题配错作者'已单列 critical),诚实降级交人核对。")


def _reference_quality_gate(art: dict) -> "GateResult":
    """关联/时效/占比(warn):近 2 年前沿缺失、自引率偏高、含预印本;中外占比只如实报数不判对错。"""
    refs = [r for r in art["refs"] if _classify_ref(r) == "CONFIRMED"]
    if not refs:
        return GateResult("reference_quality", "skip", "info", [], note="无已确认引用:质量门跳过。")
    n = len(refs)
    cn = sum(1 for r in refs if r.get("is_cn"))
    self_n = sum(1 for r in refs if r.get("is_self_cite"))
    recent = sum(1 for r in refs if (
        r.get("year") or (r.get("metadata") or {}).get("year") or 0) >= THIS_YEAR - 2)
    preprint = sum(1 for r in refs if r.get("oa_type") == "preprint")
    finds = []
    if n >= 5 and recent == 0:
        finds.append(Finding(loc="refs", issue=f"近 2 年前沿引用缺失(0/{n} 条 ≥ {THIS_YEAR - 2})——时效性存疑",
                             fix="补近 2-3 年代表作;确属成熟领域可在文中说明", rule="reference_quality.no_recent"))
    if n >= 5 and self_n / n > 0.3:
        finds.append(Finding(loc="refs", issue=f"自引率偏高({self_n}/{n}={self_n / n:.0%})——部分 venue 视为操纵信号",
                             fix="核查自引必要性,删非必需自引", rule="reference_quality.self_cite"))
    if preprint:
        finds.append(Finding(loc="refs", issue=f"含 {preprint} 条预印本(未经同行评审)",
                             fix="引用须注明 preprint,或换正式发表版 DOI", rule="reference_quality.preprint"))
    note_ratio = f"中外占比:中文 {cn}/{n}、外文 {n - cn}/{n}(如实报数,正确比例依领域/venue 而定,不机判对错)。"
    if not finds:
        return GateResult("reference_quality", "pass", "info", [], note="时效/自引/预印本无显著问题。" + note_ratio)
    return GateResult("reference_quality", "warn", "minor", finds,
                      note="关联/时效/权威(warn,非阻断):" + note_ratio + " 权威性(分区/掠夺刊)须人工查 DOAJ/预警名单。")


def _format_compliance_gate(art: dict) -> "GateResult":
    """格式对账(warn):\\cite↔.bib 缺失/重复/冗余键(编译硬门归 typesetting,此处为 warn)。"""
    ck = art["citekey_audit"]
    if ck is None:
        return GateResult("format_compliance", "skip", "info", [],
                          note="未提供 --tex/--bib:\\cite↔.bib 对账门跳过(格式排版另见 doi_to_any 出件)。")
    finds = []
    for k in ck.get("missing_keys", []):
        finds.append(Finding(loc=f"cite:{k}", issue=f"\\cite{{{k}}} 引了但 .bib 未定义(编译出 ??)",
                             fix="在 .bib 补该条或改正键名", rule="format_compliance.missing_key"))
    for k in ck.get("duplicate_bib_keys", []):
        finds.append(Finding(loc=f"bib:{k}", issue=f".bib 重复定义键 `{k}`",
                             fix="合并/删除重复条目", rule="format_compliance.duplicate_key"))
    uncited = ck.get("uncited_keys", [])
    sev = "major" if (ck.get("missing_keys") or ck.get("duplicate_bib_keys")) else "minor"
    if uncited:
        finds.append(Finding(loc="bib", issue=f".bib 有 {len(uncited)} 个冗余键(定义但正文未引)",
                             fix="投稿前清理冗余条目(审稿人嫌库脏)", rule="format_compliance.uncited_key"))
    if not finds:
        return GateResult("format_compliance", "pass", "info", [], note="\\cite↔.bib 键集完全对齐,无缺失/重复/冗余。")
    return GateResult("format_compliance", "warn", sev, finds,
                      note="格式对账(warn,非阻断):\\cite↔.bib 键集不齐。**编译报错的硬门归 typesetting(stage 11)**;"
                           "GB/T 7714/IEEE/APA 精确排版由 doi_to_any 出件、终判靠人。")


def _relevance_edge_gate(art: dict) -> "GateResult":
    """Claim support plus paper A→B index edges. Metadata never proves support."""
    edges = art["edges"]
    claim_edges = art.get("claim_edges") or []
    if not edges and not claim_edges:
        return GateResult("relevance_edge", "skip", "info", [],
                          note="未提供 claim↔citation review 或 A→B 引用边报告。")
    finds = []
    for edge in claim_edges:
        status = str(edge.get("status") or "REVIEW_REQUIRED").upper()
        if status == "SUPPORTS":
            missing = []
            if not edge.get("source_locator"):
                missing.append("source_locator")
            if not _hash(edge.get("source_evidence_sha256")):
                missing.append("source_evidence_sha256")
            claim_hash = edge.get("claim_text_sha256")
            reviewed_hash = edge.get("reviewed_claim_sha256")
            if not _hash(claim_hash):
                missing.append("claim_text_sha256")
            if not _hash(reviewed_hash):
                missing.append("reviewed_claim_sha256")
            elif _hash(claim_hash) and reviewed_hash != claim_hash:
                missing.append("reviewed_claim_sha256_mismatch")
            if not edge.get("reviewer"):
                missing.append("reviewer")
            if not edge.get("reviewed_at"):
                missing.append("reviewed_at")
            access = str(edge.get("access") or "").upper()
            if access in {"", "METADATA_ONLY", "UNAVAILABLE"}:
                missing.append("fulltext_or_abstract_access")
            support_scope = str(edge.get("support_scope") or edge.get("scope") or "").upper()
            abstract_claim_explicit = (
                edge.get("abstract_claim_explicit") is True
                or support_scope == "ABSTRACT_EXPLICIT"
            )
            if access == "ABSTRACT_ONLY" and not abstract_claim_explicit:
                missing.append("abstract_claim_explicit")
            if not missing:
                continue
            edge = dict(edge)
            edge["status"] = "REVIEW_REQUIRED"
            edge["missing_review_fields"] = missing
            status = "REVIEW_REQUIRED"
        claim_id = edge.get("claim_id") or "unknown-claim"
        cite = edge.get("citekey") or edge.get("work_id") or "unknown-work"
        issue = {
            "RELATED_ONLY": "文献与主题相关，但现有 locator/evidence 不能支持该命题",
            "PARTIAL": "文献只部分支持该命题，正文强度或范围需收窄",
            "UNSUPPORTED": "locator-backed review 判定该文献不支持该命题",
            "REVIEW_REQUIRED": "尚无 locator-backed 语义复核；元数据命中不能冒充内容支持",
        }.get(status, "未知 claim↔citation review 状态，需人工复核")
        if status == "REVIEW_REQUIRED" and edge.get("missing_review_fields"):
            issue += "；缺/失配 " + ", ".join(edge.get("missing_review_fields") or [])
        finds.append(Finding(
            loc=f"claim:{claim_id}->citation:{cite}",
            issue=issue,
            fix="打开原文定位页码/章节/图表，记录 supports/partial/related_only/unsupported；"
                "相关但不支持时改 claim、换引用或删除",
            evidence=(edge.get("source_locator") or "source_locator missing"),
            rule=f"relevance_edge.claim_{status.lower()}"))
    for e in edges:
        st = e.get("status")
        if st == "confirmed":
            continue
        a, b = e.get("citing", "?"), e.get("cited", "?")
        if st == "not_in_open_index":
            finds.append(Finding(loc=f"edge:{a}->{b}",
                                 issue="开放索引(OpenCitations/Semantic Scholar)已响应但未收录该引用边",
                                 fix="开放索引未覆盖≠未引用——人工核全文参考文献,或用 WoS/Scopus 确认",
                                 rule="relevance_edge.not_in_open_index"))
        else:  # unknown
            finds.append(Finding(loc=f"edge:{a}->{b}",
                                 issue="开放索引端点非 200(限速/网络),引用边无法判定",
                                 fix="稍后重试或换源;切勿据此断言引用关系存在与否",
                                 rule="relevance_edge.unknown"))
    if not finds:
        return GateResult("relevance_edge", "pass", "info", [], note="引用边均经开放索引实证(confirmed)。")
    return GateResult("relevance_edge", "warn", "major", finds,
                      note="claim↔citation relevance 是语义/locator 审计，不由元数据命中替代；"
                           "A→B 开放索引又只证明引用关系，不证明命题支持。均为 warn/人工复核。")


def _retraction_xref_gate(art: dict) -> "GateResult":
    """撤稿 = 不判定只指针(skip/info):白嫖自 Crossref message 的撤稿信号交 research-ethics 复核,非重叠。"""
    refs = art["refs"] or []
    flagged = [r for r in refs if (r.get("is_retracted") or r.get("retraction_flags")
                                   or r.get("publication_updates"))]
    if not flagged:
        return GateResult("retraction_xref", "skip", "info", [],
                          note="未见撤稿信号;撤稿/查重的权威判定归 research-ethics(check_retractions/text_overlap),本门不重叠。")
    finds = [Finding(loc=f"ref:{_ref_label(r)}",
                     issue=f"检出撤稿/更正事实信号(Crossref updated-by / 标题前缀):{_ref_label(r)}",
                     fix="交 research-ethics `check_retractions.py` 复核;撤稿文献严禁作有效证据引用",
                     rule="retraction_xref.deferred") for r in flagged]
    return GateResult("retraction_xref", "skip", "info", finds,
                      note=f"检出 {len(flagged)} 条带撤稿信号(白嫖自同一份 Crossref message,零额外 HTTP)→ "
                           "**交 research-ethics check_retractions.py 复核(非重叠)**;citation 门不就撤稿下 verdict。"
                           "无信号≠保证未撤稿,高风险引用须交叉查 Retraction Watch。")


# ───────────────────────── 编排入口 ─────────────────────────
def build(spec: dict) -> dict:
    """组装防幻觉引用 critical findings:消费 verify_refs 记录 + citekey 对账 + 引用边 → 六 gate。
    **build() 不打网**(consume 已核验/已算的数据)→ 可离线 selftest;在线核实由 CLI 编排 verify_refs。"""
    project = str(spec.get("project", "unnamed"))
    refs = spec.get("refs") or []
    citekey_audit = spec.get("citekey_audit")   # dict | None(已算)
    edges = spec.get("edges") or []
    claim_edges = spec.get("claim_edges") or []

    art = {"project": project, "refs": refs, "citekey_audit": citekey_audit,
           "edges": edges, "claim_edges": claim_edges}

    report = None
    if _SHARED_OK:
        report = run_gates(
            [_citation_verify_gate, _metadata_match_gate, _reference_quality_gate,
             _format_compliance_gate, _relevance_edge_gate, _retraction_xref_gate],
            art, producer="citation", target=project,
            summary="citation 防幻觉引用门:查无此文/嵌合引用(critical,诚信门,本阶段内修→reroute manual)+ "
                    "元数据不符/时效/格式/关联(warn)→ 任一 critical → run_checkpoint --stage 10 exit 1。"
                    "citation 无回边出边(自身门在 stage 10 内修);撤稿/查重归 research-ethics(非重叠)。",
            fresh_evidence=True)

    n_unresolved = sum(1 for r in refs if _classify_ref(r) in {"UNRESOLVED", "UNAVAILABLE"})
    return {"project": project, "n_refs": len(refs),
            "n_unresolved": n_unresolved, "has_citekey": citekey_audit is not None,
            "n_edges": len(edges), "n_claim_edges": len(claim_edges),
            "findings": report.to_dict() if report else None,
            "findings_available": _SHARED_OK}


def to_markdown(result: dict) -> str:
    lines = [f"# citation 防幻觉引用门:{result['project']}", ""]
    lines.append(f"- 参考文献核验记录:{result.get('n_refs', 0)} 条"
                 f"(未核验/网络不可达 {result.get('n_unresolved', 0)} 条);"
                 f"\\cite↔.bib 对账:{'有' if result.get('has_citekey') else '无(跳过)'};"
                 f"A→B 引用边:{result.get('n_edges', 0)} 条;"
                 f"claim↔citation:{result.get('n_claim_edges', 0)} 条")
    if result.get("findings"):
        f = result["findings"]
        lines += ["", f"> findings: light.findings.v1 **verdict={f['verdict']}** (producer=citation);"
                  f"run_checkpoint --stage 10 聚合,查无此文/嵌合引用→critical fail→exit 1;"
                  f"citation **无回边出边**(自身门在 stage 10 内修);撤稿/查重归 research-ethics。"]
        for g in f["gates"]:
            lines.append(f">   - {g['gate']}: {g['status']}/{g['severity']}  {g.get('note', '')[:56]}")
            for x in g.get("findings", [])[:4]:
                lines.append(f">       · {x['loc']}: {x['issue'][:80]}")
    else:
        lines += ["", "> _shared 不可达:findings 诚实降级 None(不假装产机读交接)。"]
    return "\n".join(lines)


# ───────────────────────── selftest(离线,确定性) ─────────────────────────
def _mk_ref(**kw) -> dict:
    """造一条 verify_refs 风格记录(默认 = 已确认存在的干净引用)。"""
    rec = {"doi": kw.get("doi", "10.1/ok"), "status": "CONFIRMED",
           "found_crossref": True, "found_openalex": True,
           "http": {"crossref": 200, "openalex": 200}, "title": "A Real Paper", "year": THIS_YEAR,
           "cited_by_count": 20, "is_cn": False, "is_self_cite": False,
           "is_oa": True, "oa_status": "gold", "venue": "J", "is_in_doaj": True,
           "oa_type": "journal-article", "version": "publishedVersion",
           "is_retracted": False, "retraction_flags": [], "is_chimeric": False,
           "claimed_title_sim": None, "unverified_offline": False, "errors": [], "warnings": [],
           "author_set_diff": {}}
    rec.update(kw)
    return rec


def _selftest() -> int:
    failures = []

    def check(cond, msg):
        if not cond:
            failures.append(msg)

    # 1. 查无此文(Crossref 连上 404)→ citation_verify critical → 整体 fail
    missing = _mk_ref(doi="10.0/ghost", found_crossref=False, found_openalex=False,
                      status="CONFIRMED-MISSING",
                      http={"doi_ra": 200, "crossref": 404, "datacite": 404, "openalex": 404})
    r1 = build({"project": "p1", "refs": [_mk_ref(), missing]})
    if _SHARED_OK:
        f1 = r1["findings"]
        check(f1["schema"] == "light.findings.v1", "应产 light.findings.v1")
        check(f1["producer"] == "citation", f"producer 应 citation,得 {f1['producer']}")
        names = {g["gate"] for g in f1["gates"]}
        check("citation_verify" in names, f"门名应含 STAGE_GATES[10] 的 citation_verify,得 {names}")
        cv = next(g for g in f1["gates"] if g["gate"] == "citation_verify")
        check(cv["status"] == "fail" and cv["severity"] == "critical", "查无此文应 citation_verify critical")
        check(f1["verdict"] == "fail", f"查无此文应整体 fail,得 {f1['verdict']}")
        check(any(x["rule"] == "citation_verify.doi_not_found" for x in cv["findings"]), "应命中 doi_not_found")
        # critical issue 只指本阶段内修,绝不带跨阶段路由信号(citation 无回边出边)
        blob = " ".join(x["issue"] + x["fix"] + x.get("rule", "") for x in cv["findings"])
        for sig in ("回 result-analysis", "回 experiment", "7→", "8→", "9→", "回炉上游"):
            check(sig not in blob, f"citation critical issue 不应带跨阶段信号『{sig}』(本阶段内修)")
        check("本阶段" in blob or "删除" in blob, "citation critical fix 应指本阶段内修")

    # 2. 嵌合引用 → citation_verify critical
    chimeric = _mk_ref(doi="10.0/chi", is_chimeric=True,
                       errors=[{"severity": "high", "msg": "疑似嵌合引用(Chimeric):真标题配错作者"}])
    r2 = build({"project": "p2", "refs": [chimeric]})
    if _SHARED_OK:
        cv2 = next(g for g in r2["findings"]["gates"] if g["gate"] == "citation_verify")
        check(cv2["status"] == "fail" and cv2["severity"] == "critical", "嵌合引用应 citation_verify critical")
        check(any(x["rule"] == "citation_verify.chimeric" for x in cv2["findings"]), "应命中 chimeric")

    # 3. UNRESOLVED(网络不可达)→ citation_verify warn(**绝不判幻觉**,不阻断)
    offline = _mk_ref(doi="10.0/net", found_crossref=False, found_openalex=False,
                      status="UNAVAILABLE", http={"crossref": 0, "openalex": 0},
                      unverified_offline=True)
    r3 = build({"project": "p3", "refs": [_mk_ref(), offline]})
    if _SHARED_OK:
        f3 = r3["findings"]
        cv3 = next(g for g in f3["gates"] if g["gate"] == "citation_verify")
        check(cv3["status"] == "warn" and cv3["severity"] != "critical",
              f"仅未核验应 citation_verify warn 非 critical,得 {cv3['status']}/{cv3['severity']}")
        check(f3["verdict"] != "fail", "网络不可达不应判幻觉/整体 fail")
        check(any(x["rule"] == "citation_verify.unresolved" for x in cv3["findings"]), "应命中 unresolved")

    # 4. 全部已确认且干净 → citation_verify pass → 整体非 fail
    r4 = build({"project": "p4", "refs": [_mk_ref(doi="10.1/a"), _mk_ref(doi="10.1/b")]})
    if _SHARED_OK:
        cv4 = next(g for g in r4["findings"]["gates"] if g["gate"] == "citation_verify")
        check(cv4["status"] == "pass", f"干净引用应 citation_verify pass,得 {cv4['status']}")
        check(r4["findings"]["verdict"] != "fail", "干净引用不应 fail")

    # 5. 元数据不符(所引标题 vs 实际相似度低)→ metadata_match warn(非 critical)
    mism = _mk_ref(doi="10.1/m", claimed_title_sim=0.12)
    r5 = build({"project": "p5", "refs": [mism]})
    if _SHARED_OK:
        f5 = r5["findings"]
        mm = next(g for g in f5["gates"] if g["gate"] == "metadata_match")
        check(mm["status"] == "warn" and mm["severity"] != "critical",
              f"标题不符应 metadata_match warn 非 critical,得 {mm['status']}/{mm['severity']}")
        check(f5["verdict"] != "fail", "仅元数据不符不应整体 fail")
        # 元数据不符是 CONFIRMED 上的 warn,不应反而触发 citation_verify critical
        cv5 = next(g for g in f5["gates"] if g["gate"] == "citation_verify")
        check(cv5["status"] == "pass", "DOI 能解析的元数据不符不应误升 citation_verify critical")

    # 6. 关联/时效:无近 2 年 + 预印本 + 高自引 → reference_quality warn
    old = [_mk_ref(doi=f"10.q/{i}", year=2000, is_self_cite=(i < 4),
                   oa_type=("preprint" if i == 0 else "journal-article")) for i in range(6)]
    r6 = build({"project": "p6", "refs": old})
    if _SHARED_OK:
        rq = next(g for g in r6["findings"]["gates"] if g["gate"] == "reference_quality")
        check(rq["status"] == "warn" and rq["severity"] != "critical", f"陈旧/预印本/高自引应 reference_quality warn,得 {rq['status']}")
        rules = {x["rule"] for x in rq["findings"]}
        check("reference_quality.no_recent" in rules and "reference_quality.preprint" in rules, f"应含时效+预印本,得 {rules}")

    # 7. 格式对账:citekey 缺失/重复 → format_compliance warn(消费 citekey_audit)
    ck = {"missing_keys": ["ghost2099"], "duplicate_bib_keys": ["dup2020"], "uncited_keys": ["unused2019"]}
    r7 = build({"project": "p7", "refs": [_mk_ref()], "citekey_audit": ck})
    if _SHARED_OK:
        fc = next(g for g in r7["findings"]["gates"] if g["gate"] == "format_compliance")
        check(fc["status"] == "warn" and fc["severity"] != "critical", f"citekey 缺失应 format_compliance warn,得 {fc['status']}")
        check(any(x["rule"] == "format_compliance.missing_key" for x in fc["findings"]), "应命中 missing_key")
        check(r7["findings"]["verdict"] != "fail", "仅格式问题不应整体 fail")

    # 8. 关联边:not_in_open_index → relevance_edge warn
    edges = [{"citing": "10.a/x", "cited": "10.b/y", "status": "not_in_open_index"},
             {"citing": "10.a/x", "cited": "10.c/z", "status": "confirmed"}]
    r8 = build({"project": "p8", "refs": [_mk_ref()], "edges": edges})
    if _SHARED_OK:
        re_ = next(g for g in r8["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(re_["status"] == "warn", f"未覆盖引用边应 relevance_edge warn,得 {re_['status']}")
        check(any(x["rule"] == "relevance_edge.not_in_open_index" for x in re_["findings"]), "应命中 not_in_open_index")

    # 8b. claim↔citation 相关但不支持 → relevance warn；元数据 CONFIRMED 不得冒充语义支持
    claim_edges = [{"claim_id": "C1", "work_id": "W1", "citekey": "smith2024",
                    "status": "RELATED_ONLY", "source_locator": "abstract"}]
    r8b = build({"project": "p8b", "refs": [_mk_ref()], "claim_edges": claim_edges})
    if _SHARED_OK:
        rel = next(g for g in r8b["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(rel["status"] == "warn" and any(
            x["rule"] == "relevance_edge.claim_related_only" for x in rel["findings"]),
            "related_only claim edge 应 relevance warn")
        check(r8b["findings"]["verdict"] != "fail", "claim relevance 警报不扩大 stage-10 critical")

    # 8c. 声称 SUPPORTS 但缺 review provenance/hash → relevance warn，不能静默 pass
    incomplete_support = [{
        "claim_id": "C1", "work_id": "W1", "citekey": "smith2024",
        "status": "SUPPORTS", "source_locator": "p.3",
    }]
    r8c = build({"project": "p8c", "refs": [_mk_ref()], "claim_edges": incomplete_support})
    if _SHARED_OK:
        rel = next(g for g in r8c["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(rel["status"] == "warn" and any(
            x["rule"] == "relevance_edge.claim_review_required" for x in rel["findings"]),
            "缺 reviewer/hash/access 的 SUPPORTS 应降为 review_required warn")

    # 8d. ABSTRACT_ONLY 的 SUPPORTS 必须声明 claim 在摘要中明确出现
    h = "sha256:" + "a" * 64
    claim_h = "sha256:" + "b" * 64
    abstract_support = [{
        "claim_id": "C1", "work_id": "W1", "citekey": "smith2024",
        "status": "SUPPORTS", "source_locator": "abstract",
        "source_evidence_sha256": h, "reviewer": "selftest",
        "reviewed_at": "2026-07-04T00:00:00+00:00", "access": "ABSTRACT_ONLY",
        "claim_text_sha256": claim_h, "reviewed_claim_sha256": claim_h,
    }]
    r8d = build({"project": "p8d", "refs": [_mk_ref()], "claim_edges": abstract_support})
    if _SHARED_OK:
        rel = next(g for g in r8d["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(rel["status"] == "warn" and any(
            "abstract_claim_explicit" in x["issue"] for x in rel["findings"]),
            "ABSTRACT_ONLY SUPPORTS 缺 abstract_claim_explicit 应降级")
        abstract_support_ok = [dict(abstract_support[0],
                                    support_scope="ABSTRACT_EXPLICIT",
                                    abstract_claim_explicit=True)]
        r8d_ok = build({"project": "p8d-ok", "refs": [_mk_ref()],
                        "claim_edges": abstract_support_ok})
        rel_ok = next(g for g in r8d_ok["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(rel_ok["status"] == "pass", f"ABSTRACT_EXPLICIT 应允许摘要直接支持, 得 {rel_ok['status']}")
        stale_claim_hash = [dict(abstract_support_ok[0],
                                 reviewed_claim_sha256="sha256:" + "0" * 64)]
        r8d_stale = build({"project": "p8d-stale", "refs": [_mk_ref()],
                           "claim_edges": stale_claim_hash})
        rel_stale = next(g for g in r8d_stale["findings"]["gates"] if g["gate"] == "relevance_edge")
        check(rel_stale["status"] == "warn" and any(
            "reviewed_claim_sha256_mismatch" in x["issue"] for x in rel_stale["findings"]),
            "SUPPORTS 的 reviewed_claim_sha256 与当前 claim_text_sha256 不一致应降级")

    # 9. 撤稿:不进 verdict,只作 skip/info 指针交 research-ethics(非重叠)
    retr = _mk_ref(doi="10.0/retr", is_retracted=True,
                   retraction_flags=[{"type": "retraction", "source": "crossref:updated-by"}])
    r9 = build({"project": "p9", "refs": [retr]})
    if _SHARED_OK:
        f9 = r9["findings"]
        rx = next(g for g in f9["gates"] if g["gate"] == "retraction_xref")
        check(rx["status"] == "skip", f"撤稿 xref 应 skip(不判定),得 {rx['status']}")
        check(f9["verdict"] != "fail", "撤稿信号不应让 citation 门 fail(归 research-ethics)")
        check(any("research-ethics" in (x.get("fix", "") + rx.get("note", "")) for x in rx["findings"]) or
              "research-ethics" in rx.get("note", ""), "应指针 research-ethics")

    # 10. findings 往返 + 阻断 gate + producer
    if _SHARED_OK:
        rep = FindingsReport.from_json(json.dumps(r1["findings"], ensure_ascii=False))
        check(rep.compute_verdict() == "fail" and len(rep.blocking_gates()) >= 1, "findings 应可往返且有阻断 gate")
        check(rep.producer == "citation", "往返后 producer 仍 citation")

    # 11. _shared 不可达时 findings 诚实 None
    if not _SHARED_OK:
        check(r1["findings"] is None, "_shared 不可达时 findings 应为 None")

    # 12. markdown 不崩
    check("防幻觉引用门" in to_markdown(r1), "markdown 应含防幻觉引用门标题")

    if failures:
        print("[SELFTEST][citation_verify_gate] FAIL:")
        for m in failures:
            print("  -", m)
        return 1
    print("[SELFTEST][citation_verify_gate] OK:查无此文 critical(本阶段内修,不带跨阶段信号) / 嵌合引用 critical / "
          "网络不可达 warn(绝不判幻觉) / 干净 pass / 元数据不符 warn / 时效·预印本·自引 warn / citekey warn / "
          "关联边 warn / 摘要直接支持显式门 / claim hash 防漂移 / 撤稿 skip 指针 research-ethics / findings(citation) 往返"
          + ("" if _SHARED_OK else "(_shared 不可达,走诚实降级)") + "。")
    return 0


# ───────────────────────── CLI(在线核实在此层,build 不打网) ─────────────────────────
def _load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _refs_from_report(report: dict) -> list:
    """verify_refs 报告({summary, items})→ items 列表。也容忍直接给 items 列表。"""
    if isinstance(report, dict) and "items" in report:
        return report["items"]
    if isinstance(report, dict) and "works" in report:
        return report["works"]
    if isinstance(report, list):
        return report
    return []


def _online_verify(refs_spec: list, self_authors: list) -> list:
    """实跑 verify_refs.verify_one 逐条在线核实(带 claimed 元数据,触发嵌合/标题不符检测)。"""
    out = []
    for ref in refs_spec:
        doi = (ref.get("doi") or "").strip()
        claimed = {k: ref[k] for k in ("title", "first_author", "authors") if ref.get(k)}
        out.append(vr.verify_one(doi, self_authors, claimed=claimed))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="citation 防幻觉引用 Critical 门 producer"
                    "(查无此文/嵌合引用→critical→stage 10 exit 1;citation 无回边,自身门在 stage 10 内修)")
    ap.add_argument("--refs-report", help="已产出的 verify_refs JSON 报告({summary,items} 或 items 列表)")
    ap.add_argument("--registry", help="light.citation_registry.v1（同时消费 works + claim_edges）")
    ap.add_argument("--refs-spec", help="参考文献清单 JSON(每条 {doi,title,first_author,authors,year}),配 --online 实跑核实")
    ap.add_argument("--online", action="store_true", help="对 --refs-spec 实跑 verify_refs 在线核实(默认 off,需联网)")
    ap.add_argument("--self-author", action="append", default=[], help="本文作者姓(判自引),可多次")
    ap.add_argument("--tex", help="正文 .tex/.md(配 --bib 跑 \\cite↔.bib 对账)")
    ap.add_argument("--bib", help=".bib 路径")
    ap.add_argument("--edges-report", help="verify_citation_edge 结果 JSON(单条 dict 或列表)")
    ap.add_argument("--mailto", default="", help="礼貌池邮箱(也可设环境变量 CROSSREF_MAILTO);不传则匿名")
    ap.add_argument("--project", default="unnamed")
    ap.add_argument("--report", default="", help="把 light.findings.v1 写到该 JSON 路径")
    ap.add_argument("--json-out", default="", help="把完整引用门 JSON 写到该路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(_selftest())

    if args.mailto and _HAS_VR:
        vr._MAILTO = args.mailto.strip()

    # ① 参考文献核验记录:--refs-report 优先(离线消费);否则 --refs-spec [--online]
    refs = []
    claim_edges = []
    if args.registry:
        registry = _load_json(args.registry)
        refs = _refs_from_report(registry)
        claim_edges = registry.get("claim_edges") or []
    elif args.refs_report:
        refs = _refs_from_report(_load_json(args.refs_report))
    elif args.refs_spec:
        spec_list = _load_json(args.refs_spec)
        if args.online:
            if not _HAS_VR:
                print("[citation_verify_gate] 致命:verify_refs 不可导入,无法在线核实。", file=sys.stderr)
                sys.exit(2)
            refs = _online_verify(spec_list, args.self_author)
        else:
            print("[citation_verify_gate] 注意:--refs-spec 未加 --online,未做在线核实;"
                  "如需实跑加 --online(需联网),或用 --refs-report 喂已核验记录。", file=sys.stderr)

    # ② \cite↔.bib 对账(离线纯 stdlib)
    citekey_audit = None
    if args.tex and args.bib and _HAS_CKA:
        with open(args.tex, encoding="utf-8") as f:
            tex_text = f.read()
        with open(args.bib, encoding="utf-8") as f:
            bib_text = f.read()
        citekey_audit = cka.audit(tex_text, bib_text)

    # ③ 引用边(已产出报告)
    edges = []
    if args.edges_report:
        e = _load_json(args.edges_report)
        edges = e if isinstance(e, list) else [e]

    result = build({"project": args.project, "refs": refs,
                    "citekey_audit": citekey_audit, "edges": edges,
                    "claim_edges": claim_edges})
    print(to_markdown(result))
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[JSON] 完整引用门 → {args.json_out}", file=sys.stderr)
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
