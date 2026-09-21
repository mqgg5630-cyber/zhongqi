#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contrast_lint.py — design-token / CSS 配色的 WCAG 对比度门（**复用 _shared/visual_qa,不重造数学**）。

为什么是「复用」而非「重写」（v1 债的偿还）
------------------------------------------------
v1 的 contrast_lint 自己实现了一遍 WCAG 相对亮度/对比度公式 + 阈值表——而批 0
`_shared/visual_qa.py` 已把这套 WCAG 2.x 数学落成可机检的门（`check_contrast` /
`detect_contrast_issues` / `qa_report`，AA 4.5/3.0、AAA 7.0/4.5）。同一份 WCAG 数学
在两处各写一遍 = 维护分叉 + 口径漂移风险。本脚本照 **figure_visual_qa 复用 visual_qa**
的同一先例,**删掉本地 WCAG 数学,只保留 frontend 真正的增量 = 配色「抽取」**:

  从 design-token JSON（DTCG `$value` 树 / flat map / 显式 `pairs` 列表）或 CSS/`@theme`
  块里**抽出**所有十六进制配色与（可能的）前景/背景配对——这是 visual_qa 不做、也不该做
  的 frontend 特化脏活。抽出后,**判定全部委托** `_shared/visual_qa.check_contrast`。

role → visual_qa 档映射（WCAG 2.2 一手核 2026-06-22）
----------------------------------------------------
  body  正文（<18pt / <14pt 粗）         → check_contrast(large=False) → 需 4.5:1  (SC 1.4.3)
  large 大字（>=18pt/24px 或 14pt 粗）    → check_contrast(large=True)  → 需 3:1    (SC 1.4.3)
  ui    UI 组件/图标/边框/焦点指示         → check_contrast(large=True)  → 需 3:1    (SC 1.4.11 非文本)

诚实边界
--------
- WCAG 数学的**单一真相源 = `_shared/visual_qa`**;本脚本不再持有一份。`_shared` 不可达 →
  **诚实硬报错退出**(exit 2),**绝不偷偷退回本地实现**(那会把刚还掉的债又借回来)。
- 对比度门是**确定性硬错**抓取(配色对不对)。它**不**替代 render-then-look:像素级的层次/
  审美/真实可读性须把页面截图喂回多模态模型(见 SKILL 的回看协议),本脚本只判可计算的配色。
- frontend-design **非 DAG 节点**:本门是技能**自查**(供自身 fix-loop),**不产 light.findings.v1、
  不被 run_checkpoint 聚合**;`--qa-report` 出的是 `light.visual_qa.v1`(同 figure 内部用的 schema)。

用法（纯 stdlib + _shared,无第三方依赖）:
  python contrast_lint.py <tokens.json|styles.css>   # 任一 FAIL → exit 1
  python contrast_lint.py - --css                    # stdin 作 CSS
  python contrast_lint.py - --json                   # stdin 作 JSON
  python contrast_lint.py <file> --qa-report out.json  # 额外写 light.visual_qa.v1
  python contrast_lint.py --selftest                 # 离线合成自测(真 import visual_qa)
  python contrast_lint.py                            # (无参) == --selftest
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from dataclasses import dataclass

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ── 规范 bootstrap(_shared/README.md):向上走目录树找含 _shared 包的仓库根 ──
# 治 v1 硬编码 `../../_shared`/`parents[N]` 之脆(v2 _shared 在仓库根、嵌套深度已变)。
# 本脚本是 _shared/visual_qa 的正当消费者:抽配色喂其 WCAG 引擎,**不重造数学**。
_ROOT = pathlib.Path(__file__).resolve()
while _ROOT != _ROOT.parent and not (_ROOT / "_shared" / "__init__.py").exists():
    _ROOT = _ROOT.parent
sys.path.insert(0, str(_ROOT))
try:
    from _shared.visual_qa import (check_contrast, contrast_ratio,  # noqa: E402
                                   detect_contrast_issues, qa_report)
    _HAS_VQA = True
except ImportError:
    _HAS_VQA = False


# ── 配色抽取(frontend 的真增量;visual_qa 不做) ─────────────────────────
_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")
# 捕获 `--token-name: #hex` 或 `prop: #hex`(带前置标识符)
_NAMED_HEX_RE = re.compile(
    r"(--[\w-]+|[\w-]+)\s*:\s*(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}))\b"
)
# role → visual_qa 的 large 档:body=正文(False), large/ui=大字/非文本(True, 3:1)
_LARGE_ROLE = {"body": False, "large": True, "ui": True}


def _expand_hex(h: str) -> str:
    """规范化 #rgb / #rrggbb(带不带 # 皆可)为 6 位小写十六进制。"""
    h = h.lstrip("#").lower()
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6 or any(c not in "0123456789abcdef" for c in h):
        raise ValueError(f"not a hex color: {h!r}")
    return h


@dataclass
class Pair:
    fg: str
    bg: str
    role: str = "body"  # body | large | ui
    fg_name: str = ""
    bg_name: str = ""


@dataclass
class Result:
    pair: Pair
    ratio: float
    threshold: float
    passed: bool

    def line(self) -> str:
        tag = "PASS" if self.passed else "FAIL"
        a = self.pair.fg_name or f"#{self.pair.fg}"
        b = self.pair.bg_name or f"#{self.pair.bg}"
        return (f"[{tag}] {self.pair.role:5s} {a} on {b}: "
                f"{self.ratio:.2f}:1 (need {self.threshold}:1)")


def check_pairs(pairs: list[Pair], level: str = "AA") -> list[Result]:
    """**判定委托 _shared/visual_qa.check_contrast**,本函数只做 role→large 映射 + 装配。"""
    if not _HAS_VQA:
        raise RuntimeError(
            "无法 import _shared.visual_qa —— WCAG 数学的单一真相源不可达。"
            "请确保脚本在 Light-Skills 树内(向上可找到 _shared/__init__.py)。"
            "本脚本绝不退回本地 WCAG 实现(那会复活已偿还的重复债)。")
    out: list[Result] = []
    for p in pairs:
        large = _LARGE_ROLE.get(p.role, False)
        res = check_contrast(f"#{p.fg}", f"#{p.bg}", large=large, level=level)
        out.append(Result(p, res["ratio"], res["required"], res["pass"]))
    return out


def render(results: list[Result]) -> str:
    if not results:
        return "no color pairs to check"
    lines = [r.line() for r in results]
    n_pass = sum(1 for r in results if r.passed)
    lines.append(f"--- {n_pass}/{len(results)} pairs pass WCAG ---")
    return "\n".join(lines)


def build_qa_report(pairs: list[Pair], level: str = "AA") -> dict:
    """用 visual_qa.detect_contrast_issues + qa_report 出 light.visual_qa.v1。

    再次**全程复用** visual_qa:既不重造检测,也不重造报告 schema。"""
    vqa_pairs = [{"fg": f"#{p.fg}", "bg": f"#{p.bg}",
                  "where": (p.fg_name or f"#{p.fg}") + " on " + (p.bg_name or f"#{p.bg}"),
                  "large": _LARGE_ROLE.get(p.role, False)} for p in pairs]
    cissues = detect_contrast_issues(vqa_pairs, level=level)
    # contrast 门是确定性配色检测,无几何、未做像素回看(vlm_findings=None) → 如实标注
    return qa_report([], vlm_findings=None, contrast_issues=cissues)


# ── 抽取实现 ───────────────────────────────────────────────────────────
def _walk_json_colors(obj, prefix: str, acc: dict) -> None:
    """从 flat map 或 DTCG($value) token 树收集 {name: hex}。"""
    if isinstance(obj, dict):
        val = obj.get("$value")
        if isinstance(val, str) and _HEX_RE.fullmatch(val.strip()):
            acc[prefix or "color"] = _expand_hex(val.strip())
            return
        for k, v in obj.items():
            if k.startswith("$"):
                continue
            child = f"{prefix}.{k}" if prefix else k
            if isinstance(v, str) and _HEX_RE.fullmatch(v.strip()):
                acc[child] = _expand_hex(v.strip())
            else:
                _walk_json_colors(v, child, acc)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk_json_colors(v, f"{prefix}[{i}]", acc)


def pairs_from_json(text: str) -> list[Pair]:
    data = json.loads(text)
    # 显式配对优先(可标 role)
    if isinstance(data, dict) and isinstance(data.get("pairs"), list):
        pairs: list[Pair] = []
        for item in data["pairs"]:
            pairs.append(Pair(
                fg=_expand_hex(item["fg"]), bg=_expand_hex(item["bg"]),
                role=item.get("role", "body"),
                fg_name=item.get("fg_name", item["fg"]),
                bg_name=item.get("bg_name", item["bg"])))
        return pairs
    colors: dict = {}
    _walk_json_colors(data, "", colors)
    return _all_combinations(colors)


def pairs_from_css(text: str) -> list[Pair]:
    colors: dict = {}
    for name, hexv in _NAMED_HEX_RE.findall(text):
        try:
            colors[name] = _expand_hex(hexv)
        except ValueError:
            continue
    if not colors:  # 退回任意裸 hex 出现
        for m in _HEX_RE.finditer(text):
            h = _expand_hex(m.group(0))
            colors.setdefault(f"#{h}", h)
    return _all_combinations(colors)


def _all_combinations(colors: dict) -> list[Pair]:
    items = list(colors.items())
    pairs: list[Pair] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            n1, h1 = items[i]
            n2, h2 = items[j]
            if h1 == h2:
                continue
            pairs.append(Pair(fg=h1, bg=h2, role="body", fg_name=n1, bg_name=n2))
    return pairs


# ── selftest(离线,但**真 import visual_qa** 以证复用) ───────────────────
def _selftest() -> None:
    assert _HAS_VQA, ("selftest 必须能 import _shared.visual_qa —— 本脚本的全部 WCAG "
                      "判定都委托它;import 不到说明 bootstrap 或仓库结构坏了。")

    # 1. 复用证据:本脚本的对比度数值 == visual_qa.contrast_ratio(同一真相源)
    assert abs(contrast_ratio("#000000", "#ffffff") - 21.0) < 0.2, "黑白≈21:1(来自 visual_qa)"
    assert abs(contrast_ratio("#ffffff", "#ffffff") - 1.0) < 1e-6, "同色=1:1"

    print("=== JSON tokens(DTCG $value 树,混合过/不过)===")
    tok = json.dumps({"color": {
        "ink": {"$value": "#1a1a1a"},
        "bg": {"$value": "#ffffff"},
        "muted": {"$value": "#cfcfcf"},  # 对白底低对比
    }})
    res = check_pairs(pairs_from_json(tok))
    print(render(res))
    assert any(r.passed for r in res), "至少一对强对比通过"
    assert any(not r.passed for r in res), "muted/bg 必须 fail"

    print("\n=== 显式 pairs + role 映射(body vs large/ui 档)===")
    pj = json.dumps({"pairs": [
        {"fg": "#1a1a1a", "bg": "#ffffff", "role": "body"},   # 强 → PASS
        {"fg": "#949494", "bg": "#ffffff", "role": "body"},   # ~3.0 → FAIL body(需4.5)
        {"fg": "#949494", "bg": "#ffffff", "role": "large"},  # ~3.0 → PASS large(需3)
        {"fg": "#949494", "bg": "#ffffff", "role": "ui"},     # ~3.0 → PASS ui(非文本需3)
    ]})
    rp = check_pairs(pairs_from_json(pj))
    print(render(rp))
    assert rp[0].passed, "深墨/白底过 body"
    assert not rp[1].passed, "中灰过不了 body 4.5:1"
    assert rp[2].passed, "同中灰过 large 3:1(role 映射生效)"
    assert rp[3].passed and rp[3].threshold == 3.0, "ui 档=3:1(WCAG 1.4.11 非文本)"

    print("\n=== CSS 变量抽取 ===")
    css = ":root{--fg:#222;--bg:#fff;--faint:#ddd;}\n.btn{color:#222;background:#fff}"
    rc = check_pairs(pairs_from_css(css))
    print(render(rc))
    assert any(not r.passed for r in rc), "faint/浅 对必 fail"

    print("\n=== build_qa_report → light.visual_qa.v1(复用 visual_qa.qa_report)===")
    rep = build_qa_report(pairs_from_json(pj))
    print(json.dumps({"schema": rep["schema"], "verdict": rep["verdict"],
                      "counts": rep["counts"],
                      "pixel_review_done": rep["pixel_review_done"]},
                     ensure_ascii=False))
    assert rep["schema"] == "light.visual_qa.v1", "出 visual_qa 的统一 schema"
    assert rep["counts"]["total"] >= 1, "应抓到 body 档 fail"
    assert rep["pixel_review_done"] is False, "对比度门未做像素回看,如实标注"

    print("\nself-test OK")


def _run_file(path: str, mode, qa_report_path) -> int:
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    if mode == "css" or (mode is None and path.lower().endswith(".css")):
        pairs = pairs_from_css(text)
    elif mode == "json" or (mode is None and path.lower().endswith(".json")):
        pairs = pairs_from_json(text)
    else:  # 嗅探:能 JSON 解析就 JSON,否则 CSS
        try:
            pairs = pairs_from_json(text)
        except Exception:
            pairs = pairs_from_css(text)
    results = check_pairs(pairs)
    print(render(results))
    if qa_report_path:
        rep = build_qa_report(pairs)
        pathlib.Path(qa_report_path).write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[qa-report] light.visual_qa.v1 → {qa_report_path} (verdict={rep['verdict']})")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--selftest":
        if not _HAS_VQA:
            print("FATAL: 无法 import _shared.visual_qa(WCAG 真相源不可达)", file=sys.stderr)
            raise SystemExit(2)
        _selftest()
    else:
        mode = "css" if "--css" in args else ("json" if "--json" in args else None)
        qa_report_path = None
        if "--qa-report" in args:
            i = args.index("--qa-report")
            if i + 1 < len(args):
                qa_report_path = args[i + 1]
        path = next((a for a in args
                     if not a.startswith("--") and a != qa_report_path), "-")
        if not _HAS_VQA:
            print("FATAL: 无法 import _shared.visual_qa(WCAG 真相源不可达)", file=sys.stderr)
            raise SystemExit(2)
        raise SystemExit(_run_file(path, mode, qa_report_path))
