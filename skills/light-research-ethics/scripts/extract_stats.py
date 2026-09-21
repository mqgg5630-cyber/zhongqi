#!/usr/bin/env python3
"""statcheck-style full-text NHST extractor + batch consistency recompute
(light-research-ethics asset, stdlib only).

Closes the single biggest depth gap vs the field benchmark statcheck: instead of
hand-typing each --t/--df, this scans a whole manuscript (or its results section)
for reported test statistics and recomputes every one through
stat_consistency.pcheck, producing a "reported p vs recomputed p" table with
GROSS mismatches flagged.

Covers the statistics statcheck covers, all five:
    t(df) = val, p = val
    F(df1, df2) = val, p = val
    r(df) = val, p = val
    chi2 / χ²(df[, N=..]) = val, p = val
    Z = val, p = val

Comparison operators on p (<, >, =, <=, >=) are parsed; for "p < .05" the check
asks whether the recomputed p is consistent with the stated bound (an inequality
is flagged only when the recomputed p clearly violates it, e.g. recomputed .20
reported "p < .05").

HONEST LIMITS:
- Regex extraction over prose is best-effort: APA-ish "stat(df)=v, p=v" forms are
  caught; non-standard typography, stats split across lines, or values in tables
  may be missed. A miss is silent (not "clean") — always eyeball the source too.
- The recompute is a MAGNITUDE sanity check (same engine/limits as
  stat_consistency.pcheck), never a misconduct verdict. Rounding of the reported
  statistic is expected; only GROSS discrepancies are flagged.
- One-tailed tests reported as such will look "off by ~2x" — this is expected and
  is surfaced as a soft note, not a hard GROSS flag, when the only issue is a ~2x
  ratio with no significance-threshold crossing.

Usage:
    python extract_stats.py paper.txt
    python extract_stats.py paper.txt --json
    python extract_stats.py --text "We found t(48) = 2.10, p = .04 ..."
    python extract_stats.py --selftest
"""
import sys
import os
import re
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Reuse the recompute engine (same dir).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stat_consistency as sc  # noqa: E402


# --------------------------------------------------------------------------
# Regex grammar for reported NHST statistics (APA-ish).
# Numbers may be ".045", "0.045", "2.10", "1,024" (we strip thousands commas
# only inside N=). p may carry a comparison operator.
# --------------------------------------------------------------------------
_NUM = r"[-+]?\d*\.?\d+"
_P = r"(?P<pop>[<>=]=?|=)\s*(?P<pval>\d*\.?\d+)"

# t(df) = v, p ... ; allow "t (48)" spacing
_RE_T = re.compile(
    r"\bt\s*\(\s*(?P<df>%s)\s*\)\s*=\s*(?P<val>%s)\s*,?\s*p\s*%s"
    % (_NUM, _NUM, _P), re.IGNORECASE)
# F(df1, df2) = v, p ...
_RE_F = re.compile(
    r"\bF\s*\(\s*(?P<df1>%s)\s*,\s*(?P<df2>%s)\s*\)\s*=\s*(?P<val>%s)\s*,?\s*p\s*%s"
    % (_NUM, _NUM, _NUM, _P), re.IGNORECASE)
# r(df) = v, p ...
_RE_R = re.compile(
    r"\br\s*\(\s*(?P<df>%s)\s*\)\s*=\s*(?P<val>%s)\s*,?\s*p\s*%s"
    % (_NUM, _NUM, _P), re.IGNORECASE)
# chi2 / χ2(df[, N = ...]) = v, p ...  (accept chi2, χ2, χ²)
_RE_CHI = re.compile(
    r"(?:χ\s*[²³]?|chi\s*[²]?2?|\\chi\^?2?)\s*"
    r"\(\s*(?P<df>%s)\s*(?:,\s*N\s*=\s*(?P<N>[\d,]+)\s*)?\)\s*=\s*"
    r"(?P<val>%s)\s*,?\s*p\s*%s" % (_NUM, _NUM, _P), re.IGNORECASE)
# Z = v, p ...  (capital/lower z, but avoid matching inside words via \b)
_RE_Z = re.compile(
    r"\bZ\s*=\s*(?P<val>%s)\s*,?\s*p\s*%s" % (_NUM, _P))


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def _parse_p(m):
    op = m.group("pop")
    op = "=" if op == "==" else op
    return op, float(m.group("pval"))


def _check_one(kind, params, op, reported_p, gross_ratio=3.0):
    """Run pcheck for one extracted stat; fold the comparison operator in."""
    res = sc.pcheck(reported_p, gross_ratio=gross_ratio, **params)
    computed = res["computed_p"]
    note = ""
    consistent = res["consistent"]
    if op in ("<", "<="):
        # reported bound says p below threshold; violated only if computed clearly above
        consistent = computed <= reported_p * 1.0 + 1e-9 or computed <= reported_p
        if computed > reported_p and computed / max(reported_p, 1e-12) > gross_ratio:
            consistent = False
            note = "recomputed p=%.4g exceeds the reported upper bound p%s%g" % (
                computed, op, reported_p)
        else:
            consistent = True
    elif op in (">", ">="):
        if computed < reported_p and reported_p / max(computed, 1e-12) > gross_ratio:
            consistent = False
            note = "recomputed p=%.4g falls below the reported lower bound p%s%g" % (
                computed, op, reported_p)
        else:
            consistent = True
    return {
        "kind": kind,
        "params": params,
        "reported_p_op": op,
        "reported_p": reported_p,
        "computed_p": computed,
        "ratio": res["ratio"],
        "significance_crosses": res["significance_crosses"],
        "consistent": consistent,
        "status": "CONSISTENT" if consistent else "GROSS",
        "note": note or (res["status"] if not consistent else ""),
    }


def extract(text, gross_ratio=3.0):
    """Scan text for reported NHST stats and recompute each. Returns a report."""
    rows = []

    for m in _RE_T.finditer(text):
        op, p = _parse_p(m)
        df = float(m.group("df"))
        t = float(m.group("val"))
        row = _check_one("t", {"t": t, "df": df}, op, p, gross_ratio)
        row.update({"raw": m.group(0).strip(), "line": _line_of(text, m.start())})
        rows.append(row)

    for m in _RE_F.finditer(text):
        op, p = _parse_p(m)
        row = _check_one("F", {"F": float(m.group("val")),
                               "df1": float(m.group("df1")),
                               "df2": float(m.group("df2"))}, op, p, gross_ratio)
        row.update({"raw": m.group(0).strip(), "line": _line_of(text, m.start())})
        rows.append(row)

    for m in _RE_CHI.finditer(text):
        op, p = _parse_p(m)
        row = _check_one("chi2", {"chi2": float(m.group("val")),
                                  "df": float(m.group("df"))}, op, p, gross_ratio)
        row.update({"raw": m.group(0).strip(), "line": _line_of(text, m.start())})
        rows.append(row)

    # r and Z after chi2/F so we don't double-match the leading letters.
    for m in _RE_R.finditer(text):
        op, p = _parse_p(m)
        row = _check_one("r", {"r": float(m.group("val")),
                               "df": float(m.group("df"))}, op, p, gross_ratio)
        row.update({"raw": m.group(0).strip(), "line": _line_of(text, m.start())})
        rows.append(row)

    for m in _RE_Z.finditer(text):
        op, p = _parse_p(m)
        row = _check_one("Z", {"z": float(m.group("val"))}, op, p, gross_ratio)
        row.update({"raw": m.group(0).strip(), "line": _line_of(text, m.start())})
        rows.append(row)

    rows.sort(key=lambda r: r["line"])
    n_gross = sum(1 for r in rows if r["status"] == "GROSS")
    return {
        "tool": "extract_stats",
        "n_extracted": len(rows),
        "n_gross": n_gross,
        "verdict": "GROSS_FOUND" if n_gross else ("CLEAN" if rows else "NONE_FOUND"),
        "rows": rows,
        "honest_note": ("Regex extraction is best-effort; a miss is silent, not "
                        "'clean'. Recompute is a magnitude sanity check, not a "
                        "misconduct verdict."),
    }


def _emit(report, as_json):
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print("extract_stats: %d statistic(s) extracted, %d GROSS"
          % (report["n_extracted"], report["n_gross"]))
    if not report["rows"]:
        print("  (no APA-style reported statistics matched — check source manually)")
    for r in report["rows"]:
        icon = "🛑" if r["status"] == "GROSS" else "✅"
        print("  %s L%d  %s" % (icon, r["line"], r["raw"]))
        print("       reported p %s %g   recomputed p = %.4g   ratio=%.3g"
              % (r["reported_p_op"], r["reported_p"], r["computed_p"], r["ratio"]))
        if r["note"]:
            print("       -> %s" % r["note"])
    print("  " + report["honest_note"])


def _selftest():
    # 1. Extract all five kinds from a synthetic results paragraph.
    txt = (
        "In Study 1, the effect was reliable, t(48) = 2.10, p = .04. "
        "An ANOVA showed F(2, 40) = 4.50, p = .017. "
        "The correlation was significant, r(98) = .30, p = .003. "
        "A chi-square test, χ²(2, N = 200) = 6.0, p = .05, held. "
        "The z-test gave Z = 2.58, p = .0099."
    )
    rep = extract(txt)
    kinds = sorted(r["kind"] for r in rep["rows"])
    assert kinds == ["F", "Z", "chi2", "r", "t"], "all 5 kinds extracted: %r" % kinds
    assert rep["n_gross"] == 0, "clean paragraph should be GROSS-free: %r" % rep
    print("[selftest] extract all 5 stat kinds, clean paragraph PASS")

    # 2. A planted GROSS error: t(25)=2.10 cannot give p=.0001.
    bad = "We report t(25) = 2.10, p = .0001 here."
    rb = extract(bad)
    assert rb["n_gross"] == 1 and rb["rows"][0]["kind"] == "t", rb
    print("[selftest] planted t/p gross mismatch flagged PASS")

    # 3. A threshold crossing: true p>.05 reported as p < .05.
    cross = "The difference, t(20) = 1.50, p = .04, was significant."
    rc = extract(cross)
    assert rc["n_gross"] == 1, "t=1.50 df=20 (~.149) vs p=.04 should flag: %r" % rc
    print("[selftest] significance-threshold crossing flagged PASS")

    # 4. chi2 gross: chi2(1)=0.5 cannot give p<.001.
    chi_bad = "Association held, chi2(1) = 0.5, p < .001."
    rch = extract(chi_bad)
    assert rch["n_gross"] == 1, "chi2 bound violation should flag: %r" % rch
    print("[selftest] chi2 upper-bound violation flagged PASS")

    # 5. Inequality that is fine: t(48)=2.10, p < .05 (true ~.04) -> consistent.
    okbound = "Result was t(48) = 2.10, p < .05."
    rok = extract(okbound)
    assert rok["n_gross"] == 0, "valid p<.05 bound should be clean: %r" % rok
    print("[selftest] valid inequality bound stays clean PASS")

    # 6. No stats -> NONE_FOUND, not crash.
    assert extract("This paragraph has no statistics.")["verdict"] == "NONE_FOUND"
    print("[selftest] empty input -> NONE_FOUND PASS")

    print("[selftest] all assertions PASS")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="statcheck-style NHST extractor + batch recompute (stdlib)")
    ap.add_argument("path", nargs="?", help="manuscript text file to scan")
    ap.add_argument("--text", help="inline text instead of a file")
    ap.add_argument("--gross-ratio", type=float, default=3.0)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return _selftest()
    if args.text is not None:
        text = args.text
    elif args.path:
        with open(args.path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    else:
        ap.error("provide a text file path, --text, or --selftest")
    report = extract(text, gross_ratio=args.gross_ratio)
    _emit(report, args.json)
    return 0 if report["n_gross"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
