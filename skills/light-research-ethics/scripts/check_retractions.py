#!/usr/bin/env python3
"""Batch retraction / correction check via Crossref (light-research-ethics asset).

For each DOI, query Crossref and inspect message.updated-by for entries whose
type is "retraction" / "correction" / "expression_of_concern". ``updated-by``
is the relation on the original work; ``update-to`` is the inverse relation on
the correction/retraction notice and must not make the notice itself look
retracted. A title prefix is retained as a legacy supplemental signal.

Endpoint (verified 2026-06, HTTP 200): https://api.crossref.org/works/{doi}
Since 2023 Crossref owns the Retraction Watch database and feeds it into production
relation metadata,
so coverage is materially better than a raw publisher feed — but RW's direct DB still
carries a few more, and not every retraction is exposed. Honest limits: treat a clean
result as "no retraction signal found in Crossref", not a guarantee.

礼貌池邮箱经环境变量 CROSSREF_MAILTO 或 --mailto 传入；不传则匿名查询（不伪造邮箱）。

Usage:
    python check_retractions.py 10.1126/science.aac4716 10.1038/nature12373
    python check_retractions.py --file dois.txt --mailto you@inst.edu
    CROSSREF_MAILTO=you@inst.edu python check_retractions.py --file dois.txt
"""
import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 礼貌池邮箱：优先环境变量 CROSSREF_MAILTO，其次 --mailto，都不传则匿名查询（不伪造邮箱）。
# Crossref polite pool 是可选的——带真实联系邮箱进 polite pool 限流更宽，不带仍可匿名查。
# 不再硬编码任何邮箱（旧版硬编码了一个私人邮箱，既泄露隐私又违反 polite pool 约定）。
DEFAULT_MAILTO = os.environ.get("CROSSREF_MAILTO", "").strip()
_MAILTO = DEFAULT_MAILTO

# 撤稿/更正标记类型：跨技能单一真相源 references/retraction_flag_types.json
# （light-citation/verify_refs.py 同源消费）。读取失败回退内联默认集，保证离线 selftest 不依赖文件。
_FLAG_FALLBACK = {"retraction_level": ["retraction", "withdrawal"],
                  "concern_level": ["correction", "expression_of_concern"]}


def _load_flag_types():
    """从共享 JSON 读 retraction/concern 两级类型；失败则用内联默认（含 stderr 提示）。"""
    path = os.path.join(os.path.dirname(__file__), "..", "references", "retraction_flag_types.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        ret = set(data["retraction_level"])
        con = set(data["concern_level"])
        if not ret or not con:
            raise ValueError("empty type set")
        return ret, con
    except Exception as exc:  # 文件缺失/损坏/字段异常 -> 内联回退，不让脚本崩
        print(f"[warn] 读取共享 retraction_flag_types.json 失败({exc})，用内联默认集", file=sys.stderr)
        return set(_FLAG_FALLBACK["retraction_level"]), set(_FLAG_FALLBACK["concern_level"])


RETRACTION_TYPES, CONCERN_TYPES = _load_flag_types()
FLAG_TYPES = RETRACTION_TYPES | CONCERN_TYPES   # 全集：四类标记统一进 flags


def _user_agent():
    if _MAILTO:
        return "light-research-ethics/1.0 (mailto:%s)" % _MAILTO
    return "light-research-ethics/1.0"


def query_crossref(doi, timeout=15):
    """Return (http_status, message_dict_or_None)."""
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
    if _MAILTO:
        url += "?mailto=" + urllib.parse.quote(_MAILTO, safe="")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _user_agent()},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return resp.status, data.get("message", {})
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # network / timeout / parse
        return None, {"_error": str(e)}


def _as_relation_list(value):
    """Crossref returns a relation as either one object or an object array."""
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def extract_flags(msg):
    """Extract status-changing relations that apply *to this work*."""
    flags = []
    for relation in _as_relation_list(msg.get("updated-by")):
        utype = (relation.get("type") or "").lower().replace("-", "_")
        if utype in FLAG_TYPES:
            flags.append({
                "type": utype,
                "label": relation.get("label"),
                "doi": relation.get("DOI"),
                "source": relation.get("source"),
                "relation": "updated-by",
            })
    title = str((msg.get("title") or [""])[0] or "").strip()
    if title.upper().startswith(("RETRACTED:", "RETRACTED ")):
        flags.append({
            "type": "retraction",
            "label": "title prefix",
            "doi": None,
            "source": "crossref-title",
            "relation": "title",
        })
    return flags


def check_doi(doi):
    status, msg = query_crossref(doi)
    if status != 200 or not msg:
        return {"doi": doi, "status": status, "verdict": "UNRESOLVED",
                "flags": [], "note": "Crossref did not return a record"}
    flags = extract_flags(msg)
    if any(f["type"] in {"retraction", "withdrawal"} for f in flags):
        verdict = "RETRACTED"
    elif flags:
        verdict = "FLAGGED"  # correction / expression of concern
    else:
        verdict = "CLEAN"
    return {"doi": doi, "status": status, "verdict": verdict,
            "title": (msg.get("title") or [None])[0], "flags": flags}


def main():
    ap = argparse.ArgumentParser(description="Batch retraction check via Crossref")
    ap.add_argument("dois", nargs="*", help="DOIs to check")
    ap.add_argument("--file", help="text file with one DOI per line")
    ap.add_argument("--mailto", default="",
                    help="Crossref polite-pool 邮箱（也可设环境变量 CROSSREF_MAILTO）；不传则匿名查")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    ap.add_argument("--selftest", action="store_true", help="offline logic self-test")
    args = ap.parse_args()

    global _MAILTO
    if args.mailto:
        _MAILTO = args.mailto.strip()

    if args.selftest:
        return _selftest()

    dois = list(args.dois)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            dois += [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    dois = list(dict.fromkeys(dois))  # dedup, keep order
    if not dois:
        ap.error("provide DOIs or --file (or --selftest)")

    results = []
    for d in dois:
        results.append(check_doi(d))
        time.sleep(0.3)  # be polite to Crossref

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    bad = [r for r in results if r["verdict"] in ("RETRACTED", "FLAGGED")]
    print("# Retraction check — %d DOI(s)\n" % len(results))
    print("| DOI | verdict | title |")
    print("|---|---|---|")
    for r in results:
        mark = {"RETRACTED": "🛑", "FLAGGED": "⚠️", "CLEAN": "✅",
                "UNRESOLVED": "❔"}.get(r["verdict"], "?")
        title = (r.get("title") or "")[:60].replace("|", "/")
        print("| %s | %s %s | %s |" % (r["doi"], mark, r["verdict"], title))
    print("\n**%d flagged** (retracted/correction/EoC). Verify each before citing." % len(bad))
    print("\n> Honest limit: a CLEAN result means no `updated-by`/title retraction signal in "
          "Crossref (which since 2023 includes the Retraction Watch DB) — not all retractions "
          "are exposed there. Cross-check Retraction Watch's direct DB for high-stakes refs.")
    return 0


def _selftest():
    """Offline test of the verdict logic (no network)."""
    sample = {"updated-by": {"type": "retraction", "label": "Retraction",
                              "DOI": "10.x/retr", "source": "retraction-watch"},
              "title": ["A retracted study"]}
    flags = extract_flags(sample)
    assert any(f["type"] == "retraction" for f in flags), "should detect retraction"
    correction = {
        "updated-by": [{"type": "correction", "DOI": "10.x/corr"}],
        "title": ["Original article"],
    }
    assert extract_flags(correction)[0]["type"] == "correction"
    notice = {
        "update-to": {"type": "retraction", "DOI": "10.x/original"},
        "title": ["Retraction of an article"],
    }
    assert not extract_flags(notice), "inverse update-to must not retract the notice itself"
    legacy = {"title": ["RETRACTED: old record"]}
    assert extract_flags(legacy)[0]["source"] == "crossref-title"
    empty = {"title": ["fine"]}
    assert not extract_flags(empty), "clean record has no applicable relation"
    print("[selftest] updated-by object/list + inverse update-to + title fallback PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
