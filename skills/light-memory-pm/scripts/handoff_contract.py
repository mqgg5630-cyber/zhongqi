#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate that a handoff card is self-contained enough for the next session."""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys
import tempfile
import shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REQUIRED_SECTIONS = [
    "当前阶段",
    "已完成",
    "工作区状态",
    "待用户回答",
    "下一步",
    "阻塞/风险",
    "必读文件",
    "禁止",
]
PLACEHOLDER_RE = re.compile(r"<[^>\n]+>|\{\{[^}\n]+\}\}|\.\.\.|^\s*[-—_]*\s*$")
SESSION_RE = re.compile(r"^S\d{2,}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ACTION_RE = re.compile(
    r"(跑|读|改|写|补|验|提交|commit|test|run|verify|update|audit|check|review|生成|新建)"
)
STATUS_RE = re.compile(
    r"(clean|dirty|未提交|已提交|未推送|commit|sha|git status|CI|测试|工作树|工作区)",
    re.I,
)
QUESTION_ITEM_RE = re.compile(
    r"^\s*[-*]\s*decision_id=(?P<decision>[^|]+)\|\s*"
    r"question=(?P<question>[^|]+)\|\s*"
    r"option_a=(?P<option_a>[^|]+)\|\s*"
    r"option_b=(?P<option_b>.+?)\s*$",
    re.I,
)
NO_QUESTION_RE = re.compile(r"^\s*[-*]\s*none\s+[—-]\s*(?P<reason>.+?)\s*$", re.I)


def _repo_root() -> pathlib.Path:
    root = pathlib.Path(__file__).resolve()
    while root != root.parent and not (root / "_shared" / "__init__.py").exists():
        root = root.parent
    return root


def _issue(kind: str, severity: str, loc: str, detail: str, suggestion: str) -> dict[str, str]:
    return {
        "kind": kind,
        "severity": severity,
        "location": loc,
        "detail": detail,
        "suggestion": suggestion,
    }


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not match:
        return {}, text
    data: dict[str, str] = {}
    for raw in match.group(1).splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        data[key.strip()] = value.split("#", 1)[0].strip().strip('"')
    return data, text[match.end():]


def _sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            # Public template headings include explanatory suffixes such as
            # “已完成（产物 + 验证）”; normalize them to the contract key.
            current = re.sub(r"\s*[（(].*$", "", heading.group(1)).strip()
            sections[current] = []
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _real(text: str | None) -> bool:
    value = str(text or "").strip()
    return bool(value) and not PLACEHOLDER_RE.search(value) and value.casefold() not in {
        "unknown",
        "pending",
        "todo",
        "tbd",
        "n/a",
        "none",
        "无",
        "暂无",
    }


def _parse_date(text: str) -> dt.date | None:
    if not DATE_RE.fullmatch(text):
        return None
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def _valid_date(text: str) -> bool:
    return _parse_date(text) is not None


def _as_of_date(value: str | None = None) -> dt.date:
    if value is None or not str(value).strip():
        return dt.date.today()
    parsed = _parse_date(str(value).strip())
    if parsed is None:
        raise ValueError("--as-of must be YYYY-MM-DD")
    return parsed


def _bullets(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)
    ]


def extract_open_questions(text: str) -> list[dict[str, str]]:
    """Return machine-readable unresolved questions from one handoff card."""
    _fm, body = _frontmatter(text)
    section = _sections(body).get("待用户回答", "")
    questions: list[dict[str, str]] = []
    for line in section.splitlines():
        match = QUESTION_ITEM_RE.match(line)
        if match:
            item = {key: value.strip() for key, value in match.groupdict().items()}
            options_have_impact = all(
                re.search(
                    r"(后果|影响|代价|权衡|consequence|impact|tradeoff)",
                    item[name],
                    re.I,
                )
                for name in ("option_a", "option_b")
            )
            if (
                all(_real(value) for value in item.values())
                and re.search(r"[?？]$", item["question"])
                and options_have_impact
            ):
                questions.append(item)
    return questions


def latest_open_questions(handoff_dir: pathlib.Path) -> dict[str, object]:
    """Read the highest-numbered handoff card and return its open questions."""
    candidates: list[tuple[int, pathlib.Path]] = []
    if handoff_dir.is_dir():
        for card in handoff_dir.glob("S*-*.md"):
            match = re.match(r"^S(\d+)-", card.name)
            if match:
                candidates.append((int(match.group(1)), card))
    if not candidates:
        return {"card": None, "questions": []}
    _number, latest = max(candidates, key=lambda item: (item[0], item[1].name))
    text = latest.read_text(encoding="utf-8-sig")
    return {"card": str(latest), "questions": extract_open_questions(text)}


def audit_text(text: str, *, name: str = "handoff", as_of: str | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    today = _as_of_date(as_of)
    fm, body = _frontmatter(text)
    sections = _sections(body)
    contract_version = str(fm.get("contract_version") or "1").strip()
    if contract_version not in {"1", "2"}:
        issues.append(
            _issue(
                "HANDOFF_CONTRACT_VERSION",
                "error",
                f"{name}:frontmatter.contract_version",
                "contract_version must be 1 or 2",
                "Use contract_version: 2 for cards created from the current template.",
            )
        )

    for field in ("session_no", "suggested_title", "parent_session", "project", "date"):
        if not _real(fm.get(field)):
            issues.append(
                _issue(
                    "HANDOFF_FRONTMATTER",
                    "error",
                    f"{name}:frontmatter.{field}",
                    f"frontmatter field {field} is missing or placeholder",
                    "Fill concrete session metadata before handing off.",
                )
            )
    session_no = fm.get("session_no", "")
    if session_no and not SESSION_RE.fullmatch(session_no):
        issues.append(
            _issue(
                "HANDOFF_FRONTMATTER",
                "error",
                f"{name}:frontmatter.session_no",
                "session_no must look like S03",
                "Use S<NN> with at least two digits.",
            )
        )
    parent = str(fm.get("parent_session") or "").strip()
    if parent and parent.casefold() != "none" and not SESSION_RE.fullmatch(parent):
        issues.append(
            _issue(
                "HANDOFF_FRONTMATTER",
                "error",
                f"{name}:frontmatter.parent_session",
                "parent_session must be none or an existing S<NN>",
                "Use none for the first card or the previous session id.",
            )
        )
    date_value = fm.get("date", "")
    if date_value and not _valid_date(date_value):
        issues.append(
            _issue(
                "HANDOFF_FRONTMATTER",
                "error",
                f"{name}:frontmatter.date",
                "date must be an absolute YYYY-MM-DD date",
                "Convert relative dates such as today/yesterday to absolute dates.",
            )
        )
    elif date_value and _parse_date(date_value) > today:
        issues.append(
            _issue(
                "HANDOFF_FRONTMATTER",
                "error",
                f"{name}:frontmatter.date",
                f"date {date_value} is later than as_of {today.isoformat()}",
                "Do not pre-fill future handoff dates; write the actual card creation date.",
            )
        )

    for section in REQUIRED_SECTIONS:
        if section not in sections:
            if section == "待用户回答" and contract_version == "1":
                issues.append(
                    _issue(
                        "HANDOFF_OPEN_QUESTION_LEGACY_GAP",
                        "warn",
                        f"{name}:## {section}",
                        "legacy handoff does not record unresolved user-facing questions",
                        "Upgrade the next card to contract_version: 2 and record the exact question/options or an explicit none reason.",
                    )
                )
                continue
            issues.append(
                _issue(
                    "HANDOFF_SECTION_MISSING",
                    "error",
                    f"{name}:## {section}",
                    f"required section ## {section} is missing",
                    "Use the memory-pm handoff card template and fill it concretely.",
                )
            )
            continue
        if not _real(sections[section]):
            issues.append(
                _issue(
                    "HANDOFF_SECTION_EMPTY",
                    "error",
                    f"{name}:## {section}",
                    f"section ## {section} is empty or placeholder",
                    "Write concrete status; if truly none, explain why in a sentence.",
                )
            )

    open_question_section = sections.get("待用户回答", "")
    if open_question_section:
        lines = [
            line.strip()
            for line in open_question_section.splitlines()
            if line.strip().startswith(("-", "*"))
        ]
        explicit_none = [line for line in lines if NO_QUESTION_RE.match(line)]
        question_lines = [line for line in lines if QUESTION_ITEM_RE.match(line)]
        if explicit_none and question_lines:
            issues.append(
                _issue(
                    "HANDOFF_OPEN_QUESTION_CONFLICT",
                    "error",
                    f"{name}:## 待用户回答",
                    "section records both none and unresolved questions",
                    "Use either one explained none line or one/more decision question lines.",
                )
            )
        elif explicit_none:
            match = NO_QUESTION_RE.match(explicit_none[0])
            if len(lines) != 1 or match is None or not _real(match.group("reason")):
                issues.append(
                    _issue(
                        "HANDOFF_OPEN_QUESTION_NONE_INVALID",
                        "error",
                        f"{name}:## 待用户回答",
                        "none must be the only bullet and include a concrete reason",
                        "Write '- none — 当前没有待用户回答的问题；下一步可直接执行。'.",
                    )
                )
        elif not question_lines or len(question_lines) != len(lines):
            issues.append(
                _issue(
                    "HANDOFF_OPEN_QUESTION_FORMAT",
                    "error",
                    f"{name}:## 待用户回答",
                    "unresolved question does not use the machine-readable four-field format",
                    "Use '- decision_id=... | question=...? | option_a=label + consequence | option_b=label + consequence'.",
                )
            )
        else:
            seen: set[str] = set()
            for line in question_lines:
                match = QUESTION_ITEM_RE.match(line)
                assert match is not None
                item = {key: value.strip() for key, value in match.groupdict().items()}
                if (
                    not all(_real(value) for value in item.values())
                    or item["decision"] in seen
                    or not re.search(r"[?？]$", item["question"])
                ):
                    issues.append(
                        _issue(
                            "HANDOFF_OPEN_QUESTION_INVALID",
                            "error",
                            f"{name}:## 待用户回答",
                            "decision id/options must be concrete and unique; question must end in ? or ？",
                            "Record the exact user-facing question and two consequence-bearing options.",
                        )
                    )
                seen.add(item["decision"])
                for option_name in ("option_a", "option_b"):
                    if not re.search(
                        r"(后果|影响|代价|权衡|consequence|impact|tradeoff)",
                        item[option_name],
                        re.I,
                    ):
                        issues.append(
                            _issue(
                                "HANDOFF_OPEN_QUESTION_OPTION_GAP",
                                "error",
                                f"{name}:## 待用户回答",
                                f"{option_name} does not state a consequence/impact/tradeoff",
                                "Include both the option label and what choosing it changes.",
                            )
                        )

    done = sections.get("已完成", "")
    done_items = _bullets(done)
    if not done_items:
        issues.append(
            _issue(
                "HANDOFF_DONE_EVIDENCE_GAP",
                "error",
                f"{name}:## 已完成",
                "completed section needs at least one bullet with artifact path and verification",
                "Write '- path — verified by command/output' for each completed item.",
            )
        )
    for item in done_items:
        if "—" not in item and " - " not in item:
            issues.append(
                _issue(
                    "HANDOFF_DONE_EVIDENCE_GAP",
                    "error",
                    f"{name}:## 已完成",
                    "completed bullet lacks artifact/evidence separator",
                    "Use 'artifact/path — verification summary'.",
                )
            )
        else:
            artifact = re.split(r"\s+—\s+|\s+-\s+", item, maxsplit=1)[0]
            artifact = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", artifact).strip()
            if not _real(artifact):
                issues.append(
                    _issue(
                        "HANDOFF_DONE_ARTIFACT_GAP",
                        "error",
                        f"{name}:## 已完成",
                        "completed bullet artifact side is missing or still a placeholder",
                        "Use 'artifact/path — verification summary' with a concrete artifact, commit, or decision locator.",
                    )
                )
        if not re.search(r"(exit\s*0|PASS|通过|验证|selftest|ruff|commit|hash|人工确认)", item, re.I):
            issues.append(
                _issue(
                    "HANDOFF_DONE_VERIFICATION_GAP",
                    "error",
                    f"{name}:## 已完成",
                    "completed bullet lacks verification evidence",
                    "Mention exact command result, hash, commit, or human confirmation.",
                )
            )

    status = sections.get("工作区状态", "")
    if status and not STATUS_RE.search(status):
        issues.append(
            _issue(
                "HANDOFF_WORKTREE_STATUS_GAP",
                "error",
                f"{name}:## 工作区状态",
                "worktree status does not mention clean/dirty/commit/unpushed/CI evidence",
                "Record git status/log reality; the next session must refresh it before work.",
            )
        )

    next_steps = _bullets(sections.get("下一步", ""))
    if not next_steps:
        issues.append(
            _issue(
                "HANDOFF_NEXT_STEP_GAP",
                "error",
                f"{name}:## 下一步",
                "next step section needs 1-3 actionable bullets",
                "Write the smallest next actions, not a vague goal.",
            )
        )
    if len(next_steps) > 3:
        issues.append(
            _issue(
                "HANDOFF_NEXT_STEP_TOO_MANY",
                "warn",
                f"{name}:## 下一步",
                f"next step section has {len(next_steps)} bullets; expected <=3",
                "Keep only the smallest immediate actions; move backlog elsewhere.",
            )
        )
    for item in next_steps:
        if not ACTION_RE.search(item):
            issues.append(
                _issue(
                    "HANDOFF_NEXT_STEP_NOT_ACTIONABLE",
                    "error",
                    f"{name}:## 下一步",
                    "next step bullet is not action-oriented",
                    "Start with a concrete verb and name the artifact/command.",
                )
            )

    must_read = sections.get("必读文件", "")
    for required in (".light/passport.yaml", ".light/project_card.md"):
        if required not in must_read:
            issues.append(
                _issue(
                    "HANDOFF_MUST_READ_GAP",
                    "error",
                    f"{name}:## 必读文件",
                    f"must-read list omits {required}",
                    "The next session must read passport and project_card after the handoff card.",
                )
            )
    if "handoff" not in must_read.casefold() and "本卡" not in must_read:
        issues.append(
            _issue(
                "HANDOFF_MUST_READ_GAP",
                "error",
                f"{name}:## 必读文件",
                "must-read list does not name the handoff card itself",
                "Put the latest handoff card first.",
            )
        )

    forbidden = sections.get("禁止", "")
    if "git status" not in forbidden or not re.search(r"当前事实|现实|凭记忆", forbidden):
        issues.append(
            _issue(
                "HANDOFF_FORBIDDEN_REFRESH_GAP",
                "error",
                f"{name}:## 禁止",
                "forbidden section must tell the next session to refresh current reality and not trust memory",
                "Include 'do not treat this card as current fact; run git status/log first'.",
            )
        )
    return issues


def audit_path(path: pathlib.Path, *, as_of: str | None = None) -> list[dict[str, str]]:
    return audit_text(path.read_text(encoding="utf-8-sig"), name=str(path), as_of=as_of)


def audit_dir(path: pathlib.Path, *, as_of: str | None = None) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for card in sorted(path.glob("S*-*.md")):
        issues.extend(audit_path(card, as_of=as_of))
    return issues


def render(issues: list[dict[str, str]]) -> str:
    if not issues:
        return "handoff contract PASS"
    lines = ["handoff contract FAIL" if any(i["severity"] == "error" for i in issues) else "handoff contract WARN"]
    for issue in issues:
        lines.append(
            f"[{issue['severity'].upper()}] {issue['kind']} @ {issue['location']}: {issue['detail']}"
        )
        lines.append(f"  fix: {issue['suggestion']}")
    return "\n".join(lines)


def _selftest() -> int:
    e2e_root = _repo_root() / ".upgrade" / "_e2e"
    e2e_root.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(tempfile.mkdtemp(prefix="handoff_contract_", dir=e2e_root))
    try:
        good = root / "S03-good.md"
        good.write_text(
            """---
session_no: S03
contract_version: 2
suggested_title: "[demo] S04 Finish audit"
parent_session: S02
project: demo
date: 2026-07-05
---
## 当前阶段
Round 3 A38, tightening memory handoff.

## 已完成
- skills/light-memory-pm/scripts/handoff_contract.py — selftest exit 0 and ruff PASS

## 工作区状态
git status clean after commit d25b89f; no CI pending.

## 待用户回答
- decision_id=delivery-1 | question=是否接受当前交付并进入下一阶段？ | option_a=接受；影响：冻结当前交付哈希 | option_b=暂缓；影响：继续修订且不推进

## 下一步
1. 跑 pm.py audit 验证 handoff_contract 接入。
2. 提交 A38 commit。

## 阻塞/风险
无；接手后仍先刷新 git status。

## 必读文件
1. 本卡 → 2. .light/passport.yaml → 3. .light/project_card.md → 4. skills/light-memory-pm/SKILL.md

## 禁止
- 别把本卡当作当前事实；先运行 git status / git log 刷新现实，别凭记忆补写未验证结论。
""",
            encoding="utf-8",
        )
        assert not audit_path(good, as_of="2026-07-05"), render(audit_path(good, as_of="2026-07-05"))
        open_items = extract_open_questions(good.read_text(encoding="utf-8"))
        assert open_items and open_items[0]["decision"] == "delivery-1", open_items
        latest = latest_open_questions(root)
        assert latest["card"] == str(good) and latest["questions"] == open_items, latest

        bad = root / "S04-bad.md"
        bad.write_text(
            """---
session_no: 4
contract_version: 2
suggested_title: <title>
parent_session: yesterday
project: <project>
date: today
---
## 当前阶段
<stage>

## 已完成
- did stuff

## 工作区状态
looks okay

## 待用户回答
- decision_id=bad | question=continue | option_a=yes | option_b=no

## 下一步
1. continue
2. think more
3. do things
4. extra backlog

## 必读文件
1. notes.md

## 禁止
- be careful
""",
            encoding="utf-8",
        )
        issues = audit_path(bad, as_of="2026-07-05")
        codes = {issue["kind"] for issue in issues}
        expected = {
            "HANDOFF_FRONTMATTER",
            "HANDOFF_SECTION_MISSING",
            "HANDOFF_SECTION_EMPTY",
            "HANDOFF_DONE_EVIDENCE_GAP",
            "HANDOFF_DONE_VERIFICATION_GAP",
            "HANDOFF_WORKTREE_STATUS_GAP",
            "HANDOFF_NEXT_STEP_TOO_MANY",
            "HANDOFF_NEXT_STEP_NOT_ACTIONABLE",
            "HANDOFF_MUST_READ_GAP",
            "HANDOFF_FORBIDDEN_REFRESH_GAP",
        }
        assert expected <= codes, (expected, codes, render(issues))
        future = root / "S05-future.md"
        future.write_text(good.read_text(encoding="utf-8").replace("date: 2026-07-05", "date: 2999-01-01"), encoding="utf-8")
        future_issues = audit_path(future, as_of="2026-07-05")
        assert any(
            issue["kind"] == "HANDOFF_FRONTMATTER" and "later than as_of" in issue["detail"]
            for issue in future_issues
        ), render(future_issues)

        placeholder_artifact = root / "S06-placeholder-artifact.md"
        placeholder_artifact.write_text(
            good.read_text(encoding="utf-8").replace(
                "- skills/light-memory-pm/scripts/handoff_contract.py — selftest exit 0 and ruff PASS",
                "- <artifact-path> — selftest exit 0 and ruff PASS",
            ),
            encoding="utf-8",
        )
        artifact_issues = audit_path(placeholder_artifact, as_of="2026-07-05")
        assert any(issue["kind"] == "HANDOFF_DONE_ARTIFACT_GAP" for issue in artifact_issues), render(artifact_issues)
        template = _repo_root() / "skills" / "light-memory-pm" / "assets" / "handoff_card.template.md"
        if template.exists():
            assert audit_path(template, as_of="2026-07-05"), "placeholder template should fail closed"
        print("handoff_contract selftest PASS: frontmatter/sections/evidence/actions/refresh/future-date")
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="light.memory_pm.handoff_contract")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--card")
    parser.add_argument("--dir")
    parser.add_argument("--as-of", help="YYYY-MM-DD; defaults to today and blocks future handoff dates")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    if args.card:
        issues = audit_path(pathlib.Path(args.card), as_of=args.as_of)
    elif args.dir:
        issues = audit_dir(pathlib.Path(args.dir), as_of=args.as_of)
    else:
        parser.error("need --card, --dir, or --selftest")
    print(render(issues))
    return 1 if any(issue["severity"] == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
