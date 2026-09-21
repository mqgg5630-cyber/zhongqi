#!/usr/bin/env python3
"""Evidence-strength -> wording binder for the "conclusion overclaim" gate
(light-research-ethics asset). Gives SKILL §8 ("结论夸大/过度包装") an executable
tool instead of prose-only judgement.

What it does
------------
Reads three things and binds them:
  1. result-analysis evidence_strength.json (light.evidence_strength.v1) — the
     claim->grade source (shared contract _shared/evidence_contract).
  2. a paper-writing draft (draft.md / results section) — the prose to lint.
  3. paper-writing claim_plan.json (light.paper_claims.v1) — every exact draft
     claim span -> its own evidence claim_id(s) + source locator(s).
For every strong assertion in the draft, it checks only the evidence bound to
that claim. A strong A can never license unsupported B. Missing claim maps,
unregistered strong assertions, unknown evidence IDs, none-only bindings, and
wording that outranks the bound evidence are blocking integrity findings.

Shared-contract hookups (no wheel re-invention):
  - _shared/evidence_contract.py : grade_evidence / allowed_verb_tier / lint_wording
    do the grade->verb-tier mapping and the per-claim lint.
  - _shared/findings_schema.py + gate_runner.py : the result is emitted as a
    light.findings.v1 FindingsReport, so orchestrator passport / memory-pm consume
    a machine-readable verdict (not prose). This IS the research-ethics "overclaim
    gate" wired into the shared gate-runner, aggregated by run_checkpoint.
  - light-paper-writing/scripts/claim_binding.py : canonical
    light.paper_claims.v1 evaluator. This consumer loads that existing evaluator
    instead of growing a second, drifting claim-matching implementation.

HONEST LIMITS:
- Exact-span coverage is deterministic only for claims registered in
  light.paper_claims.v1. The shared wording vocabulary is still heuristic and a
  flag is a needs-revision signal, not proof that a scientific conclusion is false.
- A strong assertion plus evidence_strength.json but no claim map fails closed:
  the gate cannot know which evidence belongs to that assertion.
- No evidence file => the gate runs in "unbacked-claims" mode: every strong claim
  verb without ANY backing evidence is flagged as "assertion with no evidence
  grade on record", which is itself the integrity finding.

Usage:
    python claim_evidence_bind.py --draft draft.md --evidence evidence_strength.json \
        --claim-map claim_plan.json
    python claim_evidence_bind.py --draft draft.md            # unbacked mode
    python claim_evidence_bind.py --draft draft.md --json
    python claim_evidence_bind.py --selftest
"""
import sys
import re
import json
import pathlib
import argparse
import importlib.util
import hashlib

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Hook the shared contracts: 规范 bootstrap(向上走目录树找含 _shared/ 的仓库根)──
# 治 v1 硬编码 ../../_shared 在三 harness / 全局安装 / 任意嵌套深度下必断的脆。见 _shared/README.md。
_r = pathlib.Path(__file__).resolve()
while _r != _r.parent and not (_r / "_shared" / "__init__.py").exists():
    _r = _r.parent
sys.path.insert(0, str(_r))
from _shared import evidence_contract as ec                              # noqa: E402
from _shared.findings_schema import Finding, GateResult, FindingsReport  # noqa: E402
from _shared.gate_runner import run_gates                                # noqa: E402

# Strong-assertion vocabulary (English + Chinese) used in unbacked-claims mode.
_STRONG_EN = [
    "prove", "proves", "proven", "proved",
    "demonstrate", "demonstrates", "demonstrated",
    "establish", "establishes", "established",
    "confirm", "confirms", "confirmed",
    "significantly outperform", "significantly outperforms",
    "state-of-the-art", "sota", "novel", "first to",
    "guarantee", "guarantees",
]
_STRONG_CN = ["证明", "证实", "确证", "首次", "显著优于", "远超", "全面超越", "突破性"]
# softened wording suggestions for unbacked strong verbs
_SOFTEN = {
    "prove": "is consistent with", "proves": "is consistent with",
    "proved": "was consistent with", "proven": "consistent with",
    "demonstrate": "indicate", "demonstrates": "indicates",
    "demonstrated": "indicated", "establish": "suggest",
    "establishes": "suggests", "established": "suggested",
    "confirm": "is consistent with", "confirms": "is consistent with",
    "guarantee": "is expected to", "guarantees": "is expected to",
    "证明": "与……一致 / 表明", "证实": "表明", "确证": "表明",
    "首次": "据我们所知较早地", "显著优于": "在本实验中优于",
    "远超": "高于", "全面超越": "在所测维度上优于", "突破性": "值得关注的",
}


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def _claim_binding_module():
    """Load paper-writing's canonical claim-map evaluator without copying it."""
    path = _r / "skills" / "light-paper-writing" / "scripts" / "claim_binding.py"
    if not path.exists():
        raise RuntimeError(
            "light.paper_claims.v1 evaluator unavailable: install light-paper-writing "
            "with light-research-ethics; refusing to fall back to whole-draft strongest grade")
    spec = importlib.util.spec_from_file_location("_light_claim_binding", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load canonical claim_binding.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _binding_findings(draft_text, evidence, claim_map):
    """Return canonical per-claim binding result plus integrity findings."""
    result = _claim_binding_module().evaluate_bindings(draft_text, evidence, claim_map)
    rows = {str(row.get("claim_id") or ""): row for row in result.get("claims", [])}
    findings = []
    raw_items = result.get("coverage_errors", []) + result.get("overclaims", [])
    # evidence_contract accepts inflected English terms. The canonical evaluator
    # can consequently surface the same span as both "outperform" and
    # "outperforms". At this consumer boundary, keep the longer matched form when
    # rule/claim/locator are identical; retain genuinely different signals on the
    # same line (e.g. "significantly" and "state-of-the-art").
    items = []
    for item in raw_items:
        matched = str(item.get("matched") or "").casefold()
        key = (item.get("code"), item.get("claim_id"), item.get("locator"))
        replaced = False
        for index, existing in enumerate(items):
            existing_key = (
                existing.get("code"), existing.get("claim_id"), existing.get("locator"))
            existing_matched = str(existing.get("matched") or "").casefold()
            if (key == existing_key and matched and existing_matched
                    and (matched.startswith(existing_matched)
                         or existing_matched.startswith(matched))):
                if len(matched) > len(existing_matched):
                    items[index] = item
                replaced = True
                break
        if not replaced:
            items.append(item)

    for item in items:
        claim_id = str(item.get("claim_id") or "")
        row = rows.get(claim_id, {})
        source_locators = row.get("source_locators") or []
        evidence_bits = []
        if claim_id:
            evidence_bits.append("claim_id=" + claim_id)
        evidence_ids = item.get("evidence_claim_ids") or row.get("evidence_claim_ids") or []
        if evidence_ids:
            evidence_bits.append("evidence_claim_ids=" + ",".join(evidence_ids))
        if source_locators:
            evidence_bits.append("source_locators=" + ",".join(source_locators))
        findings.append(Finding(
            loc=item.get("locator") or "claim-map",
            issue=item.get("message") or item.get("code") or "claim binding failed",
            fix=item.get("suggestion") or "bind this exact claim to its own evidence or soften it",
            evidence=";".join(evidence_bits),
            rule=item.get("code") or "claim_binding"))
    return result, findings


def lint_unbacked(draft_text):
    """No evidence file: flag every strong assertion verb as unbacked."""
    findings = []
    low = draft_text.lower()
    for verb in _STRONG_EN:
        pat = re.compile(r"(?<![a-z])" + re.escape(verb.lower()) + r"(?![a-z])")
        for m in pat.finditer(low):
            sug = _SOFTEN.get(verb, "(hedge / cite evidence)")
            findings.append(Finding(
                loc="line %d" % _line_of(draft_text, m.start()),
                issue="strong claim '%s' with no evidence grade on record" % verb,
                fix="back with result-analysis evidence or soften to '%s'" % sug,
                rule="claim_evidence_bind.unbacked"))
    for verb in _STRONG_CN:
        for m in re.finditer(re.escape(verb), draft_text):
            sug = _SOFTEN.get(verb, "（加证据或弱化措辞）")
            findings.append(Finding(
                loc="line %d" % _line_of(draft_text, m.start()),
                issue="强主张『%s』无证据等级支撑" % verb,
                fix="用 result-analysis 证据支撑,或弱化为『%s』" % sug,
                rule="claim_evidence_bind.unbacked"))
    return findings


def overclaim_gate(artifact):
    """gate_runner-compatible per-claim integrity gate."""
    draft = artifact["draft"]
    evidence = artifact.get("evidence")
    claim_map = artifact.get("claim_map")
    if claim_map is not None:
        result, findings = _binding_findings(draft, evidence, claim_map)
        note = ("per-claim binding; claims=%d; unique_integrity_findings=%d"
                % (len(result.get("claims", [])),
                   len(findings)))
        if findings:
            return GateResult("conclusion_overclaim", "fail", "critical", findings,
                              note=note)
        return GateResult("conclusion_overclaim", "pass", "info", [], note=note)

    if evidence:
        # An evidence file proves that some evidence exists, not that it belongs
        # to this assertion. Fail closed instead of reviving the old whole-file
        # strongest-grade shortcut.
        findings = lint_unbacked(draft)
        if findings:
            for finding in findings:
                finding.issue = (
                    "strong assertion cannot be linked to its own evidence: "
                    "light.paper_claims.v1 claim map missing")
                finding.fix = (
                    "provide --claim-map with exact claim text, locator, "
                    "evidence_claim_ids, and source_locators")
                finding.rule = "claim_binding.map_missing"
            return GateResult(
                "conclusion_overclaim", "fail", "critical", findings,
                note="evidence supplied but claim map missing; strongest grade is never a fallback")
        return GateResult(
            "conclusion_overclaim", "pass", "info", [],
            note="evidence supplied without claim map; no strong assertion detected")

    # No evidence file: softer signal (could just be a missing artifact), but many
    # unbacked strong claims still blocks.
    findings = lint_unbacked(draft)
    if findings:
        sev = "critical" if len(findings) >= 3 else "major"
        return GateResult("conclusion_overclaim", "fail", sev, findings,
                          note="no evidence file: every strong claim treated as unbacked")
    return GateResult("conclusion_overclaim", "pass", "info", [],
                      note="no evidence file; no strong unbacked claims found")


def bind(draft_text, evidence=None, claim_map=None,
         producer="research-ethics", target="draft.md"):
    """Run the overclaim gate through the shared gate-runner -> FindingsReport."""
    artifact = {"draft": draft_text, "evidence": evidence, "claim_map": claim_map}
    report = run_gates([overclaim_gate], artifact,
                       producer=producer, target=target,
                       summary="evidence-strength->wording binding (research-ethics overclaim gate)",
                       fresh_evidence=bool(evidence))
    return report


def _emit(report, as_json):
    if as_json:
        print(report.to_json())
        return
    print("claim_evidence_bind -> verdict: %s" % report.verdict)
    for g in report.gates:
        print("  [%s/%s] %s — %s" % (g.status, g.severity, g.gate, g.note))
        for f in g.findings:
            print("    - %s : %s" % (f.loc, f.issue))
            if f.fix:
                print("      fix: %s" % f.fix)


def _selftest():
    evidence = ec.build_evidence_json([
        {"claim_id": "A", "text": "A>B", "q_fdr": 0.001, "effect_size": 0.9,
         "ci95": [0.4, 1.3], "n": 120},
        {"claim_id": "B", "text": "B~C", "q_fdr": 0.3, "effect_size": 0.1,
         "ci95": [-0.2, 0.4], "n": 120},
        {"claim_id": "W", "text": "W>B", "q_fdr": 0.03, "effect_size": 0.2,
         "ci95": [0.05, 0.4], "n": 200},
    ])

    def cmap(draft_text, *rows):
        return {
            "schema": "light.paper_claims.v1",
            "draft_sha256": hashlib.sha256(draft_text.encode("utf-8")).hexdigest(),
            "claims": list(rows),
        }

    def row(cid, text, evidence_id, line):
        return {
            "claim_id": "C-" + cid, "text": text, "locator": "draft.md:L%d" % line,
            "evidence_claim_ids": [evidence_id] if evidence_id else [],
            "source_locators": (
                ["analysis/evidence_strength.json#" + evidence_id] if evidence_id else []),
        }

    # 1. Strong claim with its own strong evidence passes.
    a = "Claim A demonstrates a reliable improvement."
    rep = bind(a, evidence=evidence, claim_map=cmap(a, row("A", a, "A", 1)))
    assert rep.verdict == "pass", rep.to_json()
    print("[selftest] per-claim strong evidence passes PASS")

    # 2. Weak claim with over-strong wording blocks at the ethics gate.
    w = "Claim W demonstrates a significant improvement."
    rep2 = bind(w, evidence=evidence, claim_map=cmap(w, row("W", w, "W", 1)))
    assert rep2.verdict == "fail", rep2.to_json()
    assert any("强于" in f.issue for g in rep2.gates for f in g.findings)
    print("[selftest] per-claim weak+demonstrate critical PASS")

    # 3. Strong A must not shield a mapped none-grade B.
    b = "Claim B significantly outperforms every baseline."
    mixed = a + "\n" + b
    rep3 = bind(mixed, evidence=evidence,
                claim_map=cmap(mixed, row("A", a, "A", 1), row("B", b, "B", 2)))
    assert rep3.verdict == "fail", rep3.to_json()
    assert any("C-B" in f.evidence for g in rep3.gates for f in g.findings)
    print("[selftest] strong A cannot shield none-grade B PASS")

    # 4. Strong A must not shield an unregistered B.
    rep4 = bind(mixed, evidence=evidence, claim_map=cmap(mixed, row("A", a, "A", 1)))
    assert rep4.verdict == "fail", rep4.to_json()
    unregistered = [
        f for g in rep4.gates for f in g.findings
        if f.rule == "claim_binding.unregistered_assertion"
    ]
    assert len(unregistered) == 2, [f.issue for f in unregistered]
    print("[selftest] unregistered strong B fails closed PASS")

    # 5. Evidence without a claim map no longer falls back to strongest grade.
    rep5 = bind(a, evidence=evidence)
    assert rep5.verdict == "fail", rep5.to_json()
    assert any(f.rule == "claim_binding.map_missing"
               for g in rep5.gates for f in g.findings)
    print("[selftest] evidence without claim map fails closed PASS")

    # 6. No-evidence mode still catches English and Chinese strong assertions.
    rep6 = bind("We prove our approach and establish that it is state-of-the-art.")
    rep7 = bind("本文首次证明该方法显著优于现有方案。")
    assert rep6.verdict == rep7.verdict == "fail"
    print("[selftest] unbacked English/Chinese assertions flagged PASS")

    # 7. Clean hedged draft passes in unbacked mode.
    rep8 = bind("Our results suggest the method may improve accuracy in some settings.")
    assert rep8.verdict == "pass", rep8.to_json()
    print("[selftest] hedged draft passes PASS")

    # 8. FindingsReport round-trips as light.findings.v1 JSON.
    s = rep.to_json()
    d = json.loads(s)
    assert d["schema"] == "light.findings.v1" and d["producer"] == "research-ethics"
    assert FindingsReport.from_json(s).verdict == rep.verdict
    print("[selftest] light.findings.v1 JSON round-trip PASS")

    print("[selftest] all assertions PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Evidence-strength -> wording binder (research-ethics overclaim gate)")
    ap.add_argument("--draft", help="draft / results text file")
    ap.add_argument("--text", help="inline draft text")
    ap.add_argument("--evidence", help="result-analysis evidence_strength.json")
    ap.add_argument(
        "--claim-map",
        help="paper-writing light.paper_claims.v1 claim plan; required for strong "
             "assertions when --evidence is supplied")
    ap.add_argument("--target", default="draft.md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    if args.text is not None:
        draft = args.text
    elif args.draft:
        with open(args.draft, encoding="utf-8", errors="replace") as f:
            draft = f.read()
    else:
        ap.error("provide --draft, --text, or --selftest")
    evidence = None
    if args.evidence:
        evidence = ec.load(args.evidence)
    claim_map = None
    if args.claim_map:
        with open(args.claim_map, encoding="utf-8") as f:
            claim_map = json.load(f)
    report = bind(draft, evidence=evidence, claim_map=claim_map, target=args.target)
    _emit(report, args.json)
    return 0 if report.verdict != "fail" else 2


if __name__ == "__main__":
    sys.exit(main())
