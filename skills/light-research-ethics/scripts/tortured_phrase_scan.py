#!/usr/bin/env python3
"""Tortured-phrase / paper-mill screener (light-research-ethics asset, stdlib).

Scans a draft (and, optionally, the titles/abstracts of cited references) for
known "tortured phrases" — the synonym-laundered fingerprints of paper-mill /
machine-paraphrased text (e.g. "artificial neural organization" for "artificial
neural network", "bosom peril" for "breast cancer"). Inspired by the Problematic
Paper Screener (Cabanac, Labbé & Magazinov 2021). The dictionary lives in
references/tortured_phrases.json and is meant to grow.

Cross-skill reach-back: pass --refs <file> with one reference title/abstract per
line to screen the works you are about to CITE — this lets light-citation (batch 1)
run a paper-mill pre-warning on its reference list during citation verification,
without re-implementing the dictionary.

HONEST LIMITS:
- A hit is a "needs human review" signal of suspected mill/MT laundering, NOT a
  verdict. Some phrases can appear innocently; confirm in context and contact the
  author/editor before any action.
- The dictionary is finite and curated from published cases; absence of a hit is
  NOT proof of authenticity. Substring matching is case-insensitive.

Usage:
    python tortured_phrase_scan.py draft.txt
    python tortured_phrase_scan.py draft.txt --refs reflist.txt --json
    python tortured_phrase_scan.py --text "We used an artificial neural organization."
    python tortured_phrase_scan.py --selftest
"""
import sys
import os
import re
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "references", "tortured_phrases.json")

# Inline fallback so --selftest never depends on the JSON file being present.
_FALLBACK = {
    "artificial neural organization": "artificial neural network",
    "bosom peril": "breast cancer",
    "irregular timberland": "random forest",
    "huge information": "big data",
    "bolster vector machine": "support vector machine",
}


def load_dictionary(path=None):
    """Load the tortured-phrase map; fall back to the inline set on any error."""
    path = path or _DICT_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        phrases = data.get("phrases", {})
        if phrases:
            return phrases, path
    except (OSError, ValueError):
        pass
    return dict(_FALLBACK), "(inline fallback)"


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def scan(text, phrases, source="draft"):
    """Find all tortured-phrase hits in text. Returns a list of hit dicts."""
    hits = []
    low = text.lower()
    for distorted, canonical in phrases.items():
        d = distorted.lower()
        # word-boundary-aware substring search (phrases are multiword usually)
        pat = re.compile(r"(?<![a-z])" + re.escape(d) + r"(?![a-z])")
        for m in pat.finditer(low):
            hits.append({
                "source": source,
                "line": _line_of(text, m.start()),
                "matched": distorted,
                "canonical": canonical,
                "issue": "tortured phrase '%s' (expected '%s')" % (distorted, canonical),
            })
    hits.sort(key=lambda h: (h["source"], h["line"]))
    return hits


def screen(draft_text, refs_text=None, phrases=None):
    """Screen a draft and (optionally) a reference list. Returns a report."""
    if phrases is None:
        phrases, _ = load_dictionary()
    hits = scan(draft_text, phrases, source="draft")
    if refs_text:
        hits += scan(refs_text, phrases, source="reference")
    n = len(hits)
    return {
        "tool": "tortured_phrase_scan",
        "n_hits": n,
        "verdict": "SUSPECT" if n else "CLEAN",
        "risk_class": "paper-mill / machine-paraphrase laundering",
        "hits": hits,
        "honest_note": ("A hit is a needs-human-review signal, not a verdict; "
                        "absence of hits is not proof of authenticity."),
    }


def _emit(report, as_json):
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    icon = "🛑" if report["n_hits"] else "✅"
    print("%s tortured_phrase_scan: %d hit(s) [%s]"
          % (icon, report["n_hits"], report["verdict"]))
    for h in report["hits"]:
        print("   [%s L%d] '%s' -> likely '%s'"
              % (h["source"], h["line"], h["matched"], h["canonical"]))
    if report["n_hits"]:
        print("   -> register under risk_checklist 'suspected paper-mill / MT'.")
    print("   " + report["honest_note"])


def _selftest():
    phrases, _ = load_dictionary()  # uses real JSON if present, else fallback

    # 1. Dictionary loads and has the canonical seed entries.
    assert "artificial neural organization" in phrases
    assert phrases["bosom peril"] == "breast cancer"
    print("[selftest] dictionary load + seed entries PASS")

    # 2. A planted tortured phrase is caught.
    rep = screen("We trained an artificial neural organization on the data.",
                 phrases=phrases)
    assert rep["n_hits"] == 1 and rep["verdict"] == "SUSPECT", rep
    assert rep["hits"][0]["canonical"] == "artificial neural network"
    print("[selftest] planted tortured phrase flagged PASS")

    # 3. Clean text yields no hits.
    clean = screen("We trained an artificial neural network on the data.",
                   phrases=phrases)
    assert clean["n_hits"] == 0 and clean["verdict"] == "CLEAN", clean
    print("[selftest] clean text -> no false positive PASS")

    # 4. Reference-list reach-back: hit attributed to 'reference' source.
    rep2 = screen("Clean draft body.",
                  refs_text="A study on bosom peril detection using deep learning.",
                  phrases=phrases)
    assert rep2["n_hits"] == 1 and rep2["hits"][0]["source"] == "reference", rep2
    print("[selftest] reference-list reach-back attribution PASS")

    # 5. Word-boundary: substring inside a larger word is not matched.
    nb = screen("The huge informationally rich corpus.", phrases=phrases)
    # 'huge information' should NOT match 'huge informationally'
    assert all(h["matched"] != "huge information" for h in nb["hits"]), nb
    print("[selftest] word-boundary guard (no spurious substring) PASS")

    # 6. Fallback path works without the JSON file.
    fb, src = load_dictionary("/nonexistent/path.json")
    assert src == "(inline fallback)" and "bosom peril" in fb
    print("[selftest] missing-file fallback PASS")

    print("[selftest] all assertions PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Tortured-phrase / paper-mill screener (stdlib)")
    ap.add_argument("path", nargs="?", help="draft text file to scan")
    ap.add_argument("--text", help="inline draft text instead of a file")
    ap.add_argument("--refs", help="file of reference titles/abstracts (one per line)")
    ap.add_argument("--dict", help="override path to tortured_phrases.json")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()

    phrases, _ = load_dictionary(args.dict)
    if args.text is not None:
        draft = args.text
    elif args.path:
        with open(args.path, encoding="utf-8", errors="replace") as f:
            draft = f.read()
    else:
        ap.error("provide a draft file path, --text, or --selftest")
    refs_text = None
    if args.refs:
        with open(args.refs, encoding="utf-8", errors="replace") as f:
            refs_text = f.read()
    report = screen(draft, refs_text=refs_text, phrases=phrases)
    _emit(report, args.json)
    return 0 if report["n_hits"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
