#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在真实 Chromium 中做多视口、键盘与基础可访问性 QA。

输出 light.frontend.browser_qa.v1；它不是完整 WCAG 审计，也不替代 axe/Lighthouse
或人工视觉回看。需要 `pip install playwright` 与 `playwright install chromium`。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import tempfile
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCHEMA_ID = "light.frontend.browser_qa.v1"
_REPO_ROOT = pathlib.Path(__file__).resolve()
while _REPO_ROOT != _REPO_ROOT.parent and not (
    _REPO_ROOT / "_shared" / "__init__.py"
).exists():
    _REPO_ROOT = _REPO_ROOT.parent
VIEWPORTS = {
    "mobile": {"width": 375, "height": 812},
    "tablet": {"width": 768, "height": 1024},
    "desktop": {"width": 1440, "height": 900},
}


def _file_sha(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"

DOM_AUDIT = r"""
() => {
  const visible = (el) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.visibility !== "hidden" && s.display !== "none" && r.width > 0 && r.height > 0;
  };
  const locator = (el) => {
    if (el.id) return `#${el.id}`;
    const name = el.getAttribute("name");
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`;
    return el.tagName.toLowerCase();
  };
  const accessibleName = (el) => {
    const labelled = el.getAttribute("aria-labelledby");
    if (labelled) {
      const text = labelled.split(/\s+/).map(id => document.getElementById(id)?.textContent || "").join(" ").trim();
      if (text) return text;
    }
    const nativeLabels = el.labels ? [...el.labels].map(x => x.textContent || "").join(" ").trim() : "";
    if (nativeLabels) return nativeLabels;
    return (
      el.getAttribute("aria-label") ||
      el.getAttribute("alt") ||
      el.getAttribute("title") ||
      (el.tagName === "INPUT" ? el.getAttribute("value") : "") ||
      el.textContent || ""
    ).trim();
  };
  const interactive = [...document.querySelectorAll(
    'a[href],button,input:not([type="hidden"]),select,textarea,[tabindex]:not([tabindex="-1"])'
  )].filter(visible).filter(el => !el.disabled && el.getAttribute("aria-hidden") !== "true");
  const missingNames = interactive.filter(el => !accessibleName(el)).map(locator);
  const missingAlt = [...document.querySelectorAll("img")]
    .filter(visible).filter(el => !el.hasAttribute("alt")).map(locator);
  const vw = document.documentElement.clientWidth;
  const overflowElements = [...document.querySelectorAll("body *")].filter(visible)
    .filter(el => {
      const r = el.getBoundingClientRect();
      return r.right > vw + 1 || r.left < -1;
    }).slice(0, 20).map(locator);
  const smallTargets = interactive.filter(el => {
    const r = el.getBoundingClientRect();
    return r.width < 24 || r.height < 24;
  }).map(el => {
    const r = el.getBoundingClientRect();
    return {locator: locator(el), width: Math.round(r.width), height: Math.round(r.height)};
  });
  return {
    interactiveCount: interactive.length,
    missingNames,
    missingAlt,
    horizontalOverflow: document.documentElement.scrollWidth > vw + 1,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: vw,
    overflowElements,
    smallTargets
  };
}
"""


def _focus_probe(page: Any, count: int) -> dict[str, Any]:
    reached: list[str] = []
    no_indicator: list[str] = []
    for _ in range(min(count + 2, 80)):
        page.keyboard.press("Tab")
        data = page.evaluate(
            """() => {
              const el = document.activeElement;
              if (!el || el === document.body) return null;
              const s = getComputedStyle(el);
              const loc = el.id ? `#${el.id}` : el.tagName.toLowerCase();
              const indicator =
                (s.outlineStyle !== "none" && parseFloat(s.outlineWidth || "0") > 0) ||
                (s.boxShadow && s.boxShadow !== "none");
              return {loc, indicator};
            }"""
        )
        if data and data["loc"] not in reached:
            reached.append(data["loc"])
            if not data["indicator"]:
                no_indicator.append(data["loc"])
    return {
        "reached_unique": reached,
        "reached_count": len(reached),
        "focus_indicator_heuristic_missing": no_indicator,
    }


def _audit_loaded_page(page: Any, name: str, screenshot: pathlib.Path) -> dict[str, Any]:
    dom = page.evaluate(DOM_AUDIT)
    focus = _focus_probe(page, dom["interactiveCount"])
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot), full_page=True)
    screenshot_sha256 = _file_sha(screenshot)
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def add(target: list[dict[str, Any]], code: str, detail: Any) -> None:
        target.append({"code": code, "detail": detail})

    if dom["horizontalOverflow"]:
        add(failures, "HORIZONTAL_OVERFLOW", {
            "scroll_width": dom["scrollWidth"], "client_width": dom["clientWidth"],
            "elements": dom["overflowElements"],
        })
    if dom["missingNames"]:
        add(failures, "INTERACTIVE_NAME_MISSING", dom["missingNames"])
    if dom["missingAlt"]:
        add(failures, "IMAGE_ALT_MISSING", dom["missingAlt"])
    if focus["reached_count"] < dom["interactiveCount"]:
        add(failures, "KEYBOARD_UNREACHABLE", {
            "interactive": dom["interactiveCount"], "reached": focus["reached_count"],
        })
    if focus["focus_indicator_heuristic_missing"]:
        add(warnings, "FOCUS_INDICATOR_HEURISTIC", focus["focus_indicator_heuristic_missing"])
    if name == "mobile" and dom["smallTargets"]:
        add(warnings, "TARGET_BELOW_24_CSS_PX", dom["smallTargets"])
    return {
        "viewport": name,
        "size": page.viewport_size,
        "status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "dom": dom,
        "keyboard": focus,
        "failures": failures,
        "warnings": warnings,
        "screenshot": str(screenshot),
        "screenshot_sha256": screenshot_sha256,
    }


def audit_target(
    target: str,
    out_dir: pathlib.Path,
    timeout_ms: int = 30000,
    html: str | None = None,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {
            "schema": SCHEMA_ID, "status": "UNAVAILABLE",
            "reason": f"playwright Python package unavailable: {exc}",
            "install": "pip install playwright && playwright install chromium",
        }
    reports: list[dict[str, Any]] = []
    runtime_errors: list[dict[str, str]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            for name, viewport in VIEWPORTS.items():
                page = browser.new_page(viewport=viewport)
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on("console", lambda msg, bucket=console_errors: (
                    bucket.append(msg.text) if msg.type == "error" else None
                ))
                page.on("pageerror", lambda error, bucket=page_errors: bucket.append(str(error)))
                try:
                    if html is None:
                        page.goto(target, wait_until="networkidle", timeout=timeout_ms)
                    else:
                        page.set_content(html, wait_until="load", timeout=timeout_ms)
                    report = _audit_loaded_page(page, name, out_dir / f"{name}.png")
                    if console_errors:
                        report["failures"].append({"code": "CONSOLE_ERROR", "detail": console_errors})
                    if page_errors:
                        report["failures"].append({"code": "PAGE_ERROR", "detail": page_errors})
                    if report["failures"]:
                        report["status"] = "FAIL"
                    reports.append(report)
                except Exception as exc:  # noqa: BLE001
                    runtime_errors.append({"viewport": name, "error": str(exc)})
                finally:
                    page.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": SCHEMA_ID, "status": "UNAVAILABLE",
            "reason": f"Chromium launch failed: {exc}",
            "install": "playwright install chromium",
        }
    statuses = [x["status"] for x in reports]
    status = (
        "ERROR" if runtime_errors
        else "FAIL" if "FAIL" in statuses
        else "WARN" if "WARN" in statuses
        else "PASS"
    )
    return {
        "schema": SCHEMA_ID,
        "status": status,
        "target": target,
        "viewports": reports,
        "runtime_errors": runtime_errors,
        "coverage": {
            "real_chromium": True,
            "checks": [
                "console/page errors", "horizontal overflow", "interactive accessible names",
                "image alt presence", "keyboard reachability", "focus-indicator heuristic",
                "mobile 24 CSS px target advisory", "screenshots",
            ],
            "not_checked": [
                "full WCAG 2.2", "axe rules", "Lighthouse performance",
                "screen-reader behavior", "visual aesthetics",
            ],
        },
    }


def _selftest() -> int:
    clean = """<!doctype html><html><body>
    <main><h1>QA</h1><button id="go" style="outline:2px solid blue">Go</button>
    <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="dot"></main>
    </body></html>"""
    bad = """<!doctype html><html><body style="width:900px">
    <button></button><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">
    <script>console.error("selftest-error")</script></body></html>"""
    e2e_root = _REPO_ROOT / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser_qa_", dir=e2e_root) as td:
        root = pathlib.Path(td)
        good = audit_target("selftest:clean", root / "clean", html=clean)
        if good["status"] == "UNAVAILABLE":
            print(json.dumps(good, ensure_ascii=False, indent=2))
            return 2
        assert good["status"] in {"PASS", "WARN"}, good
        assert all(
            pathlib.Path(x["screenshot"]).exists()
            and str(x.get("screenshot_sha256") or "").startswith("sha256:")
            for x in good["viewports"]
        )
        failed = audit_target("selftest:bad", root / "bad", html=bad)
        assert failed["status"] == "FAIL", failed
        codes = {
            item["code"]
            for viewport in failed["viewports"]
            for item in viewport["failures"]
        }
        assert {"INTERACTIVE_NAME_MISSING", "IMAGE_ALT_MISSING", "CONSOLE_ERROR"} <= codes
    print("browser_qa selftest PASS: 真实 Chromium 三视口/键盘/截图/坏页负测")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=SCHEMA_ID)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--out", default="browser-qa")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if not args.url:
        parser.error("需要 --url 或 --selftest")
    report = audit_target(args.url, pathlib.Path(args.out), args.timeout_ms)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
