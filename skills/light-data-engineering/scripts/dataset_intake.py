#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dataset_intake.py — 公开数据集发现 + 下载前元数据审计（warn-only）。

真实研究者不会看到标题就整库下载：先核任务匹配、许可、gating、版本、大小、split 与来源快照，
再抽样体检。本脚本把 Hugging Face 的公开 Hub API 接成一个轻量入口，产
`light.data_candidates.v1`；它不下载数据、不替用户选数据集，也不产 `light.findings.v1`。

为什么只做 advisory：
- 搜索热度不是科学适用性，downloads/likes 不能替代领域判断。
- license/tag/card 都可能缺失或写错；`unknown` 必须人工回官方卡片核，不可当允许使用。
- 公共元数据只能证明“页面怎么声明”，不能证明数据质量、无泄漏、无隐私问题。

用法：
  python dataset_intake.py --query "breast cancer" --limit 5 --report candidates.json
  python dataset_intake.py --inspect scikit-learn/breast-cancer-wisconsin
  python dataset_intake.py --selftest
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCHEMA = "light.data_candidates.v1"
HF_API = "https://huggingface.co/api/datasets"
USER_AGENT = "Light-Skills/data-engineering dataset-intake"
SORTS = ("downloads", "likes", "lastModified")
HF_REVISION_RE = re.compile(r"^[0-9a-f]{40}$", re.I)
SENSITIVE_TAG_NEEDLES = (
    "pii", "personal", "personally-identifiable", "privacy", "human", "patient",
    "medical", "clinical", "health", "biometric", "face", "voice", "audio",
    "children", "minor", "location", "geolocation",
)


def _json_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _fetch_json(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Hugging Face API unavailable: {type(exc).__name__}: {exc}") from exc


def _tag_values(tags: list[str], prefix: str) -> list[str]:
    needle = prefix + ":"
    return [t[len(needle):] for t in tags if isinstance(t, str) and t.startswith(needle)]


def _dataset_info_blocks(card: dict[str, Any]) -> list[dict[str, Any]]:
    raw = card.get("dataset_info")
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _license_info(card: dict[str, Any], tags: list[str]) -> tuple[str, str]:
    value = card.get("license")
    if isinstance(value, str) and value.strip():
        return value.strip(), "cardData.license"
    if isinstance(value, list):
        vals = [str(x).strip() for x in value if str(x).strip()]
        if vals:
            return ",".join(vals), "cardData.license"
    tagged = _tag_values(tags, "license")
    return (tagged[0], "tag:license") if tagged else ("unknown", "unknown")


def _size_and_splits(item: dict[str, Any]) -> tuple[int | None, list[dict[str, Any]]]:
    card = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    sizes: list[int] = []
    splits: list[dict[str, Any]] = []
    for block in _dataset_info_blocks(card):
        for key in ("dataset_size", "download_size"):
            value = block.get(key)
            if isinstance(value, (int, float)) and value > 0:
                sizes.append(int(value))
        raw_splits = block.get("splits")
        if isinstance(raw_splits, list):
            for split in raw_splits:
                if isinstance(split, dict):
                    splits.append({
                        "name": split.get("name", "unknown"),
                        "num_examples": split.get("num_examples"),
                        "num_bytes": split.get("num_bytes"),
                    })
    used = item.get("usedStorage")
    if isinstance(used, (int, float)) and used > 0:
        sizes.append(int(used))
    return (max(sizes) if sizes else None), splits


def normalize_hf(item: dict[str, Any]) -> dict[str, Any]:
    """把 HF 搜索/详情响应归一成下载前候选卡；缺字段显式 unknown。"""
    tags = item.get("tags") if isinstance(item.get("tags"), list) else []
    tags = [str(x) for x in tags]
    card = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    dataset_id = str(item.get("id") or "unknown")
    url = f"https://huggingface.co/datasets/{dataset_id}"
    gated = item.get("gated", False)
    private = bool(item.get("private", False))
    access = "private" if private else ("gated" if gated not in (False, None, "false") else "public")
    size_bytes, splits = _size_and_splits(item)
    siblings = item.get("siblings") if isinstance(item.get("siblings"), list) else []
    files = [x.get("rfilename") for x in siblings
             if isinstance(x, dict) and isinstance(x.get("rfilename"), str)]
    license_name, license_source = _license_info(card, tags)
    sensitive = sorted({
        tag for tag in tags
        if any(needle in tag.casefold() for needle in SENSITIVE_TAG_NEEDLES)
    })

    candidate = {
        "provider": "huggingface",
        "id": dataset_id,
        "url": url,
        "revision": item.get("sha") or "unknown",
        "last_modified": item.get("lastModified") or "unknown",
        "access": access,
        "gated": gated,
        "license": license_name,
        "license_status": "declared" if license_name != "unknown" else "unknown",
        "license_source": license_source,
        "license_locator": f"{url}#license" if license_name != "unknown" else "unknown",
        "size_bytes": size_bytes,
        "size_categories": _tag_values(tags, "size_categories"),
        "formats": _tag_values(tags, "format"),
        "modalities": _tag_values(tags, "modality"),
        "tasks": _tag_values(tags, "task_categories"),
        "sensitive_signals": sensitive,
        "splits": splits,
        "files": files,
        "downloads": item.get("downloads"),
        "likes": item.get("likes"),
        "description_present": bool(item.get("description")),
        "dataset_card_present": bool(card),
    }
    candidate["review_reasons"] = audit_candidate(candidate)
    candidate["readiness"] = "review" if candidate["review_reasons"] else "metadata-ready"
    return candidate


def audit_candidate(c: dict[str, Any]) -> list[str]:
    """只做下载前元数据完整性 advisory；不把缺失字段变成科学结论。"""
    reasons = []
    if c.get("access") != "public":
        reasons.append(f"access={c.get('access', 'unknown')}：下载前核 gating/登录/条款")
    if c.get("license") in (None, "", "unknown"):
        reasons.append("license=unknown：不得推定可研究/可再分发")
    elif c.get("license_source") == "tag:license":
        reasons.append("license=tag-only：须回 dataset card/原始发布者条款核 locator")
    if c.get("license") not in (None, "", "unknown") and c.get("license_locator") in (None, "", "unknown"):
        reasons.append("license_locator=unknown：许可声明缺可复核位置")
    if c.get("revision") in (None, "", "unknown"):
        reasons.append("revision=unknown：无法锁定可复现实验版本")
    elif not HF_REVISION_RE.match(str(c.get("revision"))):
        reasons.append("revision_format=unexpected：HF revision 应为 40 位 commit SHA")
    if c.get("last_modified") in (None, "", "unknown"):
        reasons.append("last_modified=unknown：无法判断元数据新鲜度")
    if not c.get("size_bytes") and not c.get("size_categories"):
        reasons.append("size=unknown：下载前无法核磁盘/带宽预算")
    if not c.get("splits"):
        reasons.append("splits=unknown：须核官方 split 或自行按 group/time 设计")
    if not c.get("files"):
        reasons.append("files=unknown：下载前无法抽样核 schema/格式/大小")
    if not c.get("dataset_card_present"):
        reasons.append("dataset_card=missing：动机、采集、偏差与用途边界不可核")
    if c.get("sensitive_signals"):
        reasons.append(
            "sensitive_signals="
            + ",".join(c["sensitive_signals"][:5])
            + "：涉人/隐私/医疗等信号需 research-ethics/privacy 复核"
        )
    return reasons


def search_hf(query: str, limit: int = 10, sort: str = "downloads",
              timeout: float = 20.0) -> tuple[list[dict[str, Any]], str, str]:
    if sort not in SORTS:
        raise ValueError(f"sort 须为 {SORTS}")
    params = urllib.parse.urlencode({
        "search": query,
        "limit": max(1, min(int(limit), 50)),
        "full": "true",
        "sort": sort,
        "direction": "-1",
    })
    endpoint = f"{HF_API}?{params}"
    payload = _fetch_json(endpoint, timeout=timeout)
    if not isinstance(payload, list):
        raise RuntimeError("Hugging Face API returned non-list payload")
    return [normalize_hf(x) for x in payload if isinstance(x, dict)], endpoint, _json_sha256(payload)


def inspect_hf(dataset_id: str, timeout: float = 20.0) -> tuple[list[dict[str, Any]], str, str]:
    safe_id = "/".join(urllib.parse.quote(part, safe="") for part in dataset_id.split("/"))
    endpoint = f"{HF_API}/{safe_id}"
    payload = _fetch_json(endpoint, timeout=timeout)
    if not isinstance(payload, dict):
        raise RuntimeError("Hugging Face API returned non-object detail payload")
    return [normalize_hf(payload)], endpoint, _json_sha256(payload)


def build_report(candidates: list[dict[str, Any]], *, mode: str, query: str,
                 endpoint: str, checked_at: str | None = None,
                 raw_response_sha256: str | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "provider": "huggingface",
        "mode": mode,
        "query": query,
        "checked_at": checked_at or _utc_now(),
        "endpoint": endpoint,
        "raw_response_sha256": raw_response_sha256 or "unknown",
        "candidate_manifest_sha256": _json_sha256(candidates),
        "access_note": "公开元数据端点免 key；gated/private 数据下载仍需登录、接受条款或授权。",
        "ranking_note": "排序只用于发现；downloads/likes/更新时间不等于科学适用性或数据质量。",
        "candidates": candidates,
        "summary": {
            "total": len(candidates),
            "metadata_ready": sum(c["readiness"] == "metadata-ready" for c in candidates),
            "needs_review": sum(c["readiness"] == "review" for c in candidates),
            "unknown_license": sum(c["license"] == "unknown" for c in candidates),
            "gated_or_private": sum(c["access"] != "public" for c in candidates),
            "sensitive_review": sum(bool(c.get("sensitive_signals")) for c in candidates),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# 数据候选下载前审计（Hugging Face）",
        "",
        f"- query: `{report['query']}`",
        f"- checked_at: `{report['checked_at']}`",
        f"- raw_response_sha256: `{report['raw_response_sha256']}`",
        f"- candidate_manifest_sha256: `{report['candidate_manifest_sha256']}`",
        f"- candidates: {s['total']} · metadata-ready={s['metadata_ready']} · "
        f"needs-review={s['needs_review']}",
        "- **注意**：metadata-ready 只表示下载前字段较齐，不表示数据适用、无泄漏或合规。",
        "",
        "| candidate | access | license | size | revision | readiness |",
        "|---|---|---|---:|---|---|",
    ]
    for c in report["candidates"]:
        size = str(c["size_bytes"]) if c["size_bytes"] else (
            ",".join(c["size_categories"]) if c["size_categories"] else "unknown")
        revision = str(c["revision"])
        if revision != "unknown":
            revision = revision[:12]
        lines.append(
            f"| [{c['id']}]({c['url']}) | {c['access']} | {c['license']} | "
            f"{size} | {revision} | {c['readiness']} |"
        )
        for reason in c["review_reasons"]:
            lines.append(f"| ↳ review |  |  |  |  | {reason} |")
    lines += [
        "",
        "下一步：只对 shortlist 候选抽样下载；记录 revision/URL/SHA256，再依次跑 "
        "`data_doctor` → `split_leakage` → `data_feasibility_gate`。"
    ]
    return "\n".join(lines)


def _selftest() -> int:
    good = {
        "id": "org/good",
        "sha": "a" * 40,
        "lastModified": "2026-07-02T00:00:00Z",
        "private": False,
        "gated": False,
        "tags": ["license:cc-by-4.0", "size_categories:1K<n<10K", "format:csv",
                 "modality:tabular", "task_categories:tabular-classification"],
        "description": "documented",
        "cardData": {"license": "cc-by-4.0", "dataset_info": {
            "dataset_size": 12345,
            "splits": [{"name": "train", "num_examples": 900, "num_bytes": 10000},
                       {"name": "test", "num_examples": 100, "num_bytes": 2345}],
        }},
        "siblings": [{"rfilename": "README.md"}, {"rfilename": "data.csv"}],
    }
    bad = {
        "id": "org/unknown",
        "private": False,
        "gated": "manual",
        "tags": ["medical", "license:cc-by-4.0"],
        "cardData": {},
    }
    c1, c2 = normalize_hf(good), normalize_hf(bad)
    assert c1["readiness"] == "metadata-ready" and not c1["review_reasons"], c1
    assert c1["size_bytes"] == 12345 and len(c1["splits"]) == 2, c1
    assert c1["revision"] == "a" * 40 and c1["license"] == "cc-by-4.0", c1
    assert c2["readiness"] == "review" and c2["license"] == "cc-by-4.0", c2
    blob = " ".join(c2["review_reasons"])
    assert "license=tag-only" in blob and "revision=unknown" in blob and "gating" in blob, blob
    assert "sensitive_signals" in blob and "files=unknown" in blob and "last_modified=unknown" in blob, blob
    rep = build_report([c1, c2], mode="search", query="fixture",
                       endpoint="https://example.test", checked_at="2026-07-02T00:00:00+00:00",
                       raw_response_sha256="sha256:" + "b" * 64)
    assert rep["schema"] == SCHEMA and rep["summary"] == {
        "total": 2, "metadata_ready": 1, "needs_review": 1,
        "unknown_license": 0, "gated_or_private": 1, "sensitive_review": 1,
    }, rep["summary"]
    assert rep["raw_response_sha256"].startswith("sha256:")
    assert rep["candidate_manifest_sha256"].startswith("sha256:")
    md = render_markdown(rep)
    assert "metadata-ready" in md and "license=tag-only" in md and "不表示数据适用" in md, md
    print("[SELFTEST][dataset_intake] OK：公开/受限、许可/版本/大小/split/card 缺口均按 "
          "metadata-ready|review 诚实分流；不产 critical。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="公开数据集发现 + 下载前元数据审计（warn-only）")
    mx = ap.add_mutually_exclusive_group()
    mx.add_argument("--query", help="Hugging Face 数据集搜索词")
    mx.add_argument("--inspect", help="Hugging Face dataset id（owner/name）")
    mx.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int, default=10, help="搜索返回数，1–50（默认 10）")
    ap.add_argument("--sort", choices=SORTS, default="downloads")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--report", help="写出 light.data_candidates.v1 JSON")
    args = ap.parse_args()

    if args.selftest or not (args.query or args.inspect):
        return _selftest()
    try:
        if args.query:
            candidates, endpoint, raw_sha = search_hf(args.query, args.limit, args.sort, args.timeout)
            report = build_report(
                candidates, mode="search", query=args.query, endpoint=endpoint,
                raw_response_sha256=raw_sha,
            )
        else:
            candidates, endpoint, raw_sha = inspect_hf(args.inspect, args.timeout)
            report = build_report(
                candidates, mode="inspect", query=args.inspect, endpoint=endpoint,
                raw_response_sha256=raw_sha,
            )
    except (RuntimeError, ValueError) as exc:
        print(f"[UNAVAILABLE] {exc}", file=sys.stderr)
        return 2

    if args.report:
        pathlib.Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[REPORT] {SCHEMA} → {args.report}", file=sys.stderr)
    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
