#!/usr/bin/env python3
"""ai_tell_lint.py — mechanically flag the "AI-generated" tells.

Scans HTML/JSX/CSS source text for the blacklisted patterns from the skill's
AI-tell section. Each finding reports file position + the offending snippet so
it can be verified and fixed. Pure stdlib. Self-tests under __main__.

Blacklist (all machine-detectable):
  T1 scroll cue        : "scroll down", "scroll to explore", a bouncing
                         chevron/mouse hint near the hero.
  T2 section-numbering : eyebrow text like "01 /", "02.", "(01)" used as a
                         decorative section counter.
  T3 version footer    : "v1.0.0", "Made with", "Powered by <generic>" style
                         filler footers. The bare vX.Y.Z form is only a tell in
                         a footer/page-footer context (a changelog/release-notes
                         body legitimately lists versions, so we don't flag those).
  T4 em-dash           : the literal em-dash character used as ENGLISH prose
                         punctuation (a notorious LLM tell). Only flagged inside
                         HTML text nodes (not CSS/JS/comments/strings) and not
                         when adjacent to CJK characters, because the Chinese
                         破折号 is legitimate prose. Suggests en-dash/comma/rewrite.

Usage:
  python ai_tell_lint.py <file>     # lint a real file, exit 1 if tells found
  python ai_tell_lint.py -          # read source from stdin
  python ai_tell_lint.py --selftest # synthetic DIRTY/CLEAN tests
  python ai_tell_lint.py            # (no args) == --selftest
"""
from __future__ import annotations
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass
class Finding:
    rule: str
    line: int
    snippet: str


# T1 scroll cues
_SCROLL = re.compile(
    r"(scroll\s*(down|to\s*explore|for\s*more)|scroll-(cue|hint|indicator)|"
    r"\bbounc\w*\s+(chevron|arrow|mouse))",
    re.I,
)
# T2 decorative section numbering used as eyebrow ("01 /", "02.", "(03)")
_SECNUM = re.compile(r"""(data-role=["']eyebrow["'][^>]*>\s*\(?0?\d{1,2}\s*[./)])""", re.I)
_SECNUM_TEXT = re.compile(r">\s*\(?0\d\s*[./)]\s*<")
# T3a "made with"/"powered by" filler — a tell anywhere it appears.
_MADEWITH = re.compile(r"(made\s+with\s+(love|❤|claude|ai|v0)|powered\s+by\s+\w+)", re.I)
# T3b bare semver — only a tell in a footer context (see _VersionScanner).
_VERSION = re.compile(r"v\d+\.\d+\.\d+", re.I)
# footer-context signal on a raw line (covers <footer>, data-role="footer", 页脚)
_FOOTER_HINT = re.compile(r"(<footer\b|data-role=[\"']?(footer|page-?footer)|页\s*脚)", re.I)
_EMDASH = "—"  # em-dash character

# ── 视觉 AI-slop 痕迹 T5-T8（头号卖点"反 AI-slop 禁令"的真实现，此前缺失）──
# T5 紫粉渐变（AI 生成站点最泛滥的视觉俗套）：linear/radial-gradient 同时含紫(#8b5cf6/
#    purple/violet/#a855f7 等)与粉(#ec4899/pink/#f472b6 等)色相。
_T5_GRADIENT = re.compile(
    r"(linear|radial|conic)-gradient\([^)]*\)", re.I)
_T5_PURPLE = re.compile(
    r"(#(8b5cf6|a855f7|9333ea|7c3aed|6d28d9|c084fc)|\bpurple\b|\bviolet\b|\bindigo\b|"
    r"rgba?\(\s*(1[0-4]\d|1[0-7]\d)\s*,\s*\d{1,2}\s*,\s*(2[0-4]\d|25[0-5])\b)", re.I)
_T5_PINK = re.compile(
    r"(#(ec4899|f472b6|db2777|f9a8d4|e879f9|d946ef)|\bpink\b|\bfuchsia\b|\bmagenta\b)", re.I)
# T6 emoji 当图标：HTML 元素内容/aria 里把 emoji 当 UI 图标（✨🚀💡🔥⚡🎯 等高频"AI味"emoji）
# emoji 字符类须排除 CJK(U+4E00-9FFF)：用 pictographs/dingbats/arrows 区段，不含汉字。
_EMOJI_CHARS = (r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF"
                r"\U00002B00-\U00002BFF\U00002190-\U000021FF\U0000FE0F\U00002B50]")
_T6_EMOJI_ICON = re.compile(
    r"(class=[\"'][^\"']*\b(icon|feature|card|badge)\b[^\"']*[\"'][^>]*>\s*"
    + _EMOJI_CHARS + r")|("
    + _EMOJI_CHARS + r"\s*</(span|div|i|li|h[1-6])>)")
# T7 gradient-orb / 模糊光斑装饰（blur + 绝对定位的圆形渐变球，纯装饰噪声）
_T7_ORB = re.compile(
    r"(class=[\"'][^\"']*\b(orb|blob|glow|gradient-(orb|ball|blur)|aurora)\b)|"
    r"(border-radius:\s*50%[^;}]*;[^}]*filter:\s*blur)", re.I)
# T8 CSS 剪影/光泽冒充产品图（box-shadow 多层 + 伪 3D，或 backdrop-filter 玻璃拟态堆砌）
_T8_FAUX = re.compile(
    r"(backdrop-filter:\s*blur[^;}]*;[^}]*background:\s*rgba\(\s*255\s*,\s*255\s*,\s*255)|"
    r"(class=[\"'][^\"']*\b(glassmorphism|glass-card|neumorphism|faux-3d)\b)", re.I)


def _visual_slop_findings(line: str, line_no: int):
    """T5-T8 视觉 slop 检测（单行）。返回 Finding 列表。"""
    out = []
    for grad in _T5_GRADIENT.finditer(line):
        seg = grad.group(0)
        if _T5_PURPLE.search(seg) and _T5_PINK.search(seg):
            out.append(Finding("T5 紫粉渐变(AI-slop视觉俗套)", line_no, seg[:80]))
    if _T6_EMOJI_ICON.search(line):
        out.append(Finding("T6 emoji当UI图标", line_no, line.strip()[:80]))
    if _T7_ORB.search(line):
        out.append(Finding("T7 gradient-orb/模糊光斑装饰", line_no, line.strip()[:80]))
    if _T8_FAUX.search(line):
        out.append(Finding("T8 玻璃/拟物冒充产品图", line_no, line.strip()[:80]))
    return out


# Unicode ranges that count as CJK (Chinese 破折号 context is legitimate prose).
_CJK = re.compile(
    r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]"
)


def _is_cjk(ch: str) -> bool:
    return bool(ch) and bool(_CJK.match(ch))


class _ProseScanner(HTMLParser):
    """Walks HTML and flags em-dash only inside real text nodes (skipping
    <script>/<style>/comments) and only when it is NOT adjacent to a CJK
    character — i.e. English em-dash usage, the LLM tell."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.findings: list[Finding] = []
        self._skip_depth = 0  # inside <script>/<style>

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth:
            return
        if _EMDASH not in data:
            return
        line = self.getpos()[0]
        for i, ch in enumerate(data):
            if ch != _EMDASH:
                continue
            prev_ch = data[i - 1] if i > 0 else ""
            next_ch = data[i + 1] if i + 1 < len(data) else ""
            # legitimate Chinese 破折号: adjacent to CJK on either side → skip
            if _is_cjk(prev_ch) or _is_cjk(next_ch):
                continue
            snip = data.strip()[:80] or "—"
            self.findings.append(Finding("T4 em-dash", line, snip))
            break  # one finding per text node is enough


def lint(text: str) -> list[Finding]:
    findings: list[Finding] = []
    # Line-based rules: T1, T2, T3a (made-with), T3b (version in footer line).
    for i, line in enumerate(text.splitlines(), 1):
        for rule, rx in (
            ("T1 scroll-cue", _SCROLL),
            ("T2 section-numbering eyebrow", _SECNUM),
            ("T2 section-numbering eyebrow", _SECNUM_TEXT),
            ("T3 version/made-with footer", _MADEWITH),
        ):
            m = rx.search(line)
            if m:
                findings.append(Finding(rule, i, line.strip()[:80]))
        # bare semver only counts as a tell when the line is footer context
        if _VERSION.search(line) and _FOOTER_HINT.search(line):
            findings.append(
                Finding("T3 version/made-with footer", i, line.strip()[:80])
            )
        # T5-T8 视觉 AI-slop 痕迹（头号卖点的真实现）
        findings.extend(_visual_slop_findings(line, i))

    # Parser-based rule: T4 em-dash in English prose text nodes only.
    scanner = _ProseScanner()
    try:
        scanner.feed(text)
        scanner.close()
    except Exception:
        pass  # malformed markup: skip the prose pass rather than crash the lint
    findings.extend(scanner.findings)
    findings.sort(key=lambda f: (f.line, f.rule))
    return findings


def render(findings: list[Finding]) -> str:
    if not findings:
        return "CLEAN: no AI-tells found."
    return "\n".join(f"L{f.line} [{f.rule}] {f.snippet}" for f in findings)


_DIRTY = """
<section data-layout="hero">
  <span data-role="eyebrow">01 / Intro</span>
  <h1>Hi</h1>
  <a class="scroll-cue">Scroll down to explore</a>
</section>
<p>We move fast — then we ship.</p>
<footer>Made with love · v1.2.3 · Powered by Acme</footer>
"""

_CLEAN = """
<section data-layout="hero">
  <span data-role="eyebrow">New release</span>
  <h1>Hi</h1>
</section>
<p>We move fast, then we ship.</p>
<footer>(c) 2026 Acme. All rights reserved.</footer>
"""

# These previously caused FALSE POSITIVES and must now stay CLEAN:
#  - Chinese 破折号 in legitimate prose (T4 must not fire on CJK-adjacent em-dash)
#  - em-dash inside a CSS/JS comment or string (T4 only scans HTML text nodes)
#  - a bare vX.Y.Z in a changelog/release-notes body, NOT a footer (T3 needs
#    footer context for the bare semver form)
_CLEAN_TRICKY = """
<section data-layout="content">
  <p data-role="body">奶山羊发情行为识别——一个跨学科的研究课题，需要细致标注。</p>
  <h2>更新日志</h2>
  <ul><li>v2.1.0 新增夜间识别</li><li>v2.0.3 修复漏检</li></ul>
</section>
<style>/* layout — keep the grid tidy */ .x{gap:8px}</style>
<script>const label = "range a—b means inclusive"; // note — keep simple</script>
"""

def _selftest() -> None:
    print("=== DIRTY (expect findings T1-T4) ===")
    d = lint(_DIRTY)
    print(render(d))
    rules = {f.rule[:2] for f in d}
    for needle in ("T1", "T2", "T3", "T4"):
        assert needle in rules, f"{needle} should be flagged in DIRTY"

    print("\n=== CLEAN (expect none) ===")
    c = lint(_CLEAN)
    print(render(c))
    assert not c, "CLEAN doc should have zero findings"

    print("\n=== CLEAN_TRICKY (no false positives) ===")
    t = lint(_CLEAN_TRICKY)
    print(render(t))
    assert not t, (
        "CLEAN_TRICKY must stay clean: CJK 破折号, comment/string em-dash, and "
        "changelog semver are all legitimate, not AI-tells"
    )

    # ── 视觉 AI-slop T5-T8（头号卖点真实现）──
    print("\n=== VISUAL SLOP (expect T5-T8) ===")
    slop = """
<div style="background: linear-gradient(135deg, #8b5cf6, #ec4899);">x</div>
<span class="feature-icon">🚀</span>
<div class="gradient-orb"></div>
<div class="glass-card" style="backdrop-filter: blur(12px); background: rgba(255,255,255,0.1)">x</div>
"""
    sv = lint(slop)
    print(render(sv))
    svr = {f.rule[:2] for f in sv}
    for needle in ("T5", "T6", "T7", "T8"):
        assert needle in svr, f"{needle} 视觉 slop 应被标记: got {svr}"

    # 视觉 slop 假阳防护：单色渐变/正经图标类/合理阴影不应误报
    print("\n=== VISUAL CLEAN (no false positives) ===")
    vclean = """
<div style="background: linear-gradient(90deg, #1e293b, #334155);">monochrome</div>
<svg class="icon"><use href="#arrow"/></svg>
<div class="card" style="box-shadow: 0 1px 3px rgba(0,0,0,0.1)">subtle</div>
<div style="background: linear-gradient(135deg, #8b5cf6, #6d28d9);">purple-only</div>
"""
    vc = lint(vclean)
    print(render(vc))
    assert not vc, f"单色渐变/SVG图标/克制阴影不应误报: {[(f.rule,f.snippet) for f in vc]}"

    print("\nself-test OK")


def _run_file(path: str) -> int:
    """Lint a real file (or '-' for stdin). Exit 1 if any AI-tell is found."""
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    findings = lint(text)
    print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--selftest":
        _selftest()
    else:
        raise SystemExit(_run_file(args[0]))
