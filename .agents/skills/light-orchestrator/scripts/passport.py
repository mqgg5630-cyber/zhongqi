#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""passport.py — 产物台账（.light/passport.yaml）的读写与校验工具。

把 passport 从"手填 YAML"变成"工具调用 + schema 校验"，堵两类机械错误：
必填字段缺失、stage 序号乱序、gate.result 枚举非法。schema 对齐
references/passport.md，并新增 per-stage `revision_rounds`（返修轮次计数，
跨会话续跑时从台账读已用轮次而非重置，防返修配额刷新，见 X-2）。

YAML 依赖策略：优先 stdlib。解析时先 try-import PyYAML；装了就用，没装
就退回内置最小块式 YAML 解析器（支持本工具自身 emit 的子集：标量、块
映射、块序列、行内 [..] / {..}）。写出始终用内置 emitter，输出确定、稳定。

诚实原则：脚本只校验结构（字段在不在、序号顺不顺、枚举合不合法），
不判断 input/output 文字内容是否属实——内容真实性仍靠 a08/a10 闸门与人工。

DAG 与幂等（修 pipelines.md 承诺并行、旧版 validate 却 FAIL 乱序的硬矛盾）：
stage 可选 `depends_on:[序号]` 声明依赖；validate 改为拓扑序合法校验（依赖必须
先于本阶段出现、无环、无重复），不再硬性要求 stage 序号严格升序——并行/乱序
执行只要满足拓扑序即合法。stage 可选 `inputs_fingerprint`（上游 artifact 的
路径+mtime+size 哈希），stale-check 子命令据此判定某阶段是否"已完成且仍有效"
（artifacts 存在且上游指纹未变=fresh，否则 stale），把 SKILL 反复说的"已提交
阶段默认不重做、只重验受影响最小范围"从人工判断升级为可计算标志。

v2 增量（批 0 总控·对话②，对齐 orchestrator-spec §3）：
  - stage 级显式 `status`（not_started/in_progress/delivered/gate_failed/needs_rework）：
    v1 靠 artifacts+gate 隐式推断，v2 落成显式字段；旧台账缺 status 时从 artifacts+gate
    **派生兜底**（只派生可派生三态），显式优先、与派生冲突仅 WARN（迁移容忍，不硬报错）。
  - **一等公民 `back_edges`**（{from,to,root_cause,evidence_ptr,round,by,at} 列表）：按根因
    定向回炉的 rework 记录，**记在回炉目标阶段上**（to==所在阶段）。它与 `depends_on` 分离，
    **不进拓扑/环检测**——这正是"回边不破坏拓扑序校验"的原因。
  - 顶层 `schema: light.passport.v2`（校验器认 v1→v2 迁移）、可选 `dag_template`；
    stage 可选 `node_kind`（默认 pipeline）。

诚实边界：脚本只产/校验"建议回边"的结构，**不替用户执行回炉**（回炉是决策点，见 reroute.py）。

子命令：
  init             新建台账（--project --pipeline [--created]，打 v2 schema）
  append-stage     追加一条阶段记录（字段见 --help；支持 --depends-on/--status/--node-kind）
  add-back-edge    在回炉目标阶段记一条回边，并置其 status=needs_rework（根因回炉落账）
  set-status       显式置某阶段 status（in_progress/delivered 等转移）
  get-current-stage 读 current_stage 并打印阶段摘要（含 status）
  validate         全量 schema 校验（拓扑序 + status 派生一致性 + 回边结构），FAIL 返回非零
  fingerprint      计算给定 artifact 集合的输入指纹（供 append/stale 用）
  stale-check      逐阶段判定 fresh/stale，输出最小重验范围（恢复时调用）
  --selftest       离线合成样例自测，自清理无残留

用法示例：
  python passport.py init --project demo --pipeline A --out .light/passport.yaml
  python passport.py append-stage --file .light/passport.yaml \\
      --stage 1 --skill m01 --input "数据集+目标" --output "文献12篇" \\
      --artifacts docs/lit.md --gate-type confirm --gate-result PASS
  python passport.py get-current-stage --file .light/passport.yaml
  python passport.py validate --file .light/passport.yaml
  python passport.py --selftest
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import sys
import tempfile

# Windows GBK 控制台下中文 CLI 输出不乱码（与 run_checkpoint/reroute/_shared 同款纪律）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ---- schema 常量（对齐 references/passport.md + orchestrator-spec §3）-------
GATE_TYPES = {"confirm", "decision"}
# 确认点结果枚举：PASS / FAIL / WARN / 以及 FAIL→PASS（返修后过）。
GATE_RESULTS = {"PASS", "FAIL", "WARN", "FAIL->PASS", "FAIL→PASS"}
TOP_REQUIRED = ["project", "pipeline", "created", "updated", "current_stage"]
STAGE_REQUIRED = ["stage", "skill", "input", "output"]
# 同一阶段最多 2 轮整体返修（见 references/checkpoints.md）。
MAX_REVISION_ROUNDS = 2

# v2 schema 版本：本工具 emit 一律打 v2；校验器认 v1→v2 迁移（缺 status 不硬报错）。
SCHEMA_PASSPORT = "light.passport.v3"
KNOWN_SCHEMAS = {"light.passport.v1", "light.passport.v2", "light.passport.v3"}
EVIDENCE_STATES = {"VERIFIED", "PLANNED", "UNKNOWN", "UNAVAILABLE", "FAILED"}
# stage 显式状态枚举（§3.2）。
VALID_STATUS = {"not_started", "in_progress", "delivered", "gate_failed", "needs_rework"}
# 可由 artifacts+gate **派生**的状态子集（迁移兜底用）；in_progress/needs_rework 是
# 显式意图态——前者无产物信号、后者由 add-back-edge 置位，故不从产物派生、也不参与冲突校验。
DERIVABLE_STATUS = {"not_started", "delivered", "gate_failed"}
# 节点种类（为将来 overlay 横切技能留；pipeline=DAG 主线节点）。
NODE_KINDS = {"pipeline"}
# 回边记录必填字段（一等公民 back_edges）。
BACK_EDGE_REQUIRED = [
    "from", "to", "root_cause", "evidence_ptr", "round", "by", "at",
    "authorization_id",
]


def now_minute() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M")


# ===========================================================================
# 最小 YAML 解析器（块式子集）+ try-import PyYAML 降级
# ===========================================================================
def parse_yaml(text: str) -> dict:
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _mini_parse(text)


def _scalar(tok: str):
    """把一个标量 token 解析成 Python 值。"""
    s = tok.strip()
    if s == "" or s == "~" or s == "null":
        return None
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _flow(tok: str):
    """解析行内 [..] 或 {..}；只支持一层（够本 schema 用）。"""
    s = tok.strip()
    if s.startswith("[") and s.endswith("]"):
        body = s[1:-1].strip()
        if not body:
            return []
        return [_scalar(x) for x in _split_top(body)]
    if s.startswith("{") and s.endswith("}"):
        body = s[1:-1].strip()
        out = {}
        if not body:
            return out
        for pair in _split_top(body):
            if ":" not in pair:
                continue
            k, v = pair.split(":", 1)
            out[k.strip()] = _scalar(v)
        return out
    return _scalar(s)


def _split_top(body: str) -> list:
    """按逗号切分，但跳过引号内与括号内的逗号。"""
    parts, depth, q, cur = [], 0, "", ""
    for ch in body:
        if q:
            cur += ch
            if ch == q:
                q = ""
            continue
        if ch in "\"'":
            q = ch
            cur += ch
        elif ch in "[{":
            depth += 1
            cur += ch
        elif ch in "]}":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts


def _mini_parse(text: str):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, raw.strip()))
    val, _ = _parse_block(lines, 0, 0)
    return val if isinstance(val, dict) else {}


def _parse_block(lines, idx, indent):
    """解析同一缩进层级的块；返回 (value, next_idx)。"""
    if idx >= len(lines):
        return None, idx
    if lines[idx][1].startswith("- "):
        return _parse_seq(lines, idx, indent)
    return _parse_map(lines, idx, indent)


def _parse_seq(lines, idx, indent):
    seq = []
    while idx < len(lines):
        ci, content = lines[idx]
        if ci < indent or not content.startswith("- "):
            break
        if ci > indent:
            break
        rest = content[2:].strip()
        # 把 "- " 之后内容当作该项首行，构造一个伪缩进块
        item_lines = [(indent + 2, rest)]
        j = idx + 1
        while j < len(lines) and lines[j][0] > indent:
            item_lines.append(lines[j])
            j += 1
        if ":" in rest and not rest.startswith(("[", "{")):
            val, _ = _parse_map(item_lines, 0, indent + 2)
        elif item_lines[0][1].startswith("- "):
            val, _ = _parse_seq(item_lines, 0, indent + 2)
        else:
            val = _flow(rest)
        seq.append(val)
        idx = j
    return seq, idx


def _parse_map(lines, idx, indent):
    mp = {}
    while idx < len(lines):
        ci, content = lines[idx]
        if ci != indent or content.startswith("- "):
            break
        if ":" not in content:
            break
        key, _, after = content.partition(":")
        key = key.strip()
        after = after.strip()
        if after:
            mp[key] = _flow(after)
            idx += 1
        else:
            # 嵌套块：下一更深缩进
            child = []
            j = idx + 1
            while j < len(lines) and lines[j][0] > indent:
                child.append(lines[j])
                j += 1
            if child:
                child_indent = child[0][0]
                val, _ = _parse_block(child, 0, child_indent)
                mp[key] = val
            else:
                mp[key] = None
            idx = j
    return mp, idx


# ===========================================================================
# YAML 输出（内置 emitter，输出稳定确定）
# ===========================================================================
def _emit_scalar(v) -> str:
    if v is None:
        return "~"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # 含特殊字符或可能被误解析时加引号
    # Commas must also be quoted because nested mappings are emitted in YAML
    # flow style. Without this, a value such as "gate-a,gate-b" is parsed back
    # as a second spurious mapping key and invalidates the canonical hash.
    if s == "" or any(c in s for c in ":#[]{},\n") or s.strip() != s:
        return '"' + s.replace('"', '\\"') + '"'
    return s


def _emit_flow_list(seq) -> str:
    return "[" + ", ".join(_emit_scalar(x) for x in seq) + "]"


def _emit_flow_map(mp) -> str:
    return "{" + ", ".join(f"{k}: {_emit_scalar(v)}" for k, v in mp.items()) + "}"


def emit_yaml(data: dict) -> str:
    """把 passport dict 写成稳定的块式 YAML。"""
    buf = io.StringIO()
    # v2：schema 置顶（emit 一律打 v2）；dag_template 紧随顶层元信息其后。
    buf.write(f"schema: {_emit_scalar(data.get('schema') or SCHEMA_PASSPORT)}\n")
    for key in ("project", "pipeline", "created", "updated", "current_stage",
                "state_revision", "state_hash", "evidence_state", "next_action",
                "delivery_status", "delivery_authorization_id"):
        if key in data:
            buf.write(f"{key}: {_emit_scalar(data[key])}\n")
    if data.get("dag_template"):
        buf.write(f"dag_template: {_emit_scalar(data['dag_template'])}\n")
    stages = data.get("stages") or []
    buf.write("stages:\n")
    for st in stages:
        buf.write(_emit_stage(st))
    kl = data.get("known_limitations")
    if kl:
        buf.write("known_limitations:\n")
        for item in kl:
            buf.write(f"  - {_emit_scalar(item)}\n")
    return buf.getvalue()


# stage 内字段输出顺序（缺失字段跳过）
_STAGE_ORDER = ["stage", "depends_on", "status", "node_kind", "evidence_state", "round",
                "revision_rounds", "skill", "input", "output", "artifacts",
                "inputs_fingerprint", "gate", "back_edges", "gaps"]


def _emit_stage(st: dict) -> str:
    buf = io.StringIO()
    first = True
    for k in _STAGE_ORDER:
        if k not in st:
            continue
        v = st[k]
        prefix = "  - " if first else "    "
        first = False
        if k in ("artifacts", "depends_on") and isinstance(v, list):
            # depends_on 也是 flow list；v1 漏了它→被 _emit_scalar 引成 "[5]" 字符串，
            # 存盘后 load 回来不再是 int 列表（v1 未在 selftest 里 save/load 带 depends_on
            # 的阶段，故潜伏未爆）。v2 回炉流程会往返 depends_on，必须修。
            buf.write(f"{prefix}{k}: {_emit_flow_list(v)}\n")
        elif k == "gate" and isinstance(v, dict):
            buf.write(f"{prefix}{k}: {_emit_flow_map(v)}\n")
        elif k == "back_edges" and isinstance(v, list):
            # 块序列，每项一个行内 flow map（两解析器皆可读：PyYAML 与内置 mini）。
            buf.write(f"{prefix}{k}:\n")
            item_indent = " " * (len(prefix) + 2)
            for be in v:
                cell = _emit_flow_map(be) if isinstance(be, dict) else _emit_scalar(be)
                buf.write(f"{item_indent}- {cell}\n")
        elif k == "gaps" and isinstance(v, list):
            buf.write(f"{prefix}{k}: {_emit_flow_list(v)}\n")
        else:
            buf.write(f"{prefix}{k}: {_emit_scalar(v)}\n")
    # 任何不在顺序表里的额外键也输出，保证读写往返不丢字段
    for k, v in st.items():
        if k in _STAGE_ORDER:
            continue
        prefix = "  - " if first else "    "
        first = False
        if isinstance(v, list):
            buf.write(f"{prefix}{k}: {_emit_flow_list(v)}\n")
        elif isinstance(v, dict):
            buf.write(f"{prefix}{k}: {_emit_flow_map(v)}\n")
        else:
            buf.write(f"{prefix}{k}: {_emit_scalar(v)}\n")
    return buf.getvalue()


# ===========================================================================
# 读写文件
# ===========================================================================
def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return parse_yaml(f.read())


def _json_default(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not canonical-state serializable")


def _canonical_clone(data: dict) -> dict:
    return json.loads(json.dumps(
        data, ensure_ascii=False, default=_json_default
    ))


def compute_state_hash(data: dict) -> str:
    """Hash canonical state content, excluding the hash field itself."""
    payload = _canonical_clone(data)
    payload.pop("state_hash", None)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def save(path: str, data: dict) -> None:
    if data.get("schema") == SCHEMA_PASSPORT:
        current = data.get("state_revision")
        data["state_revision"] = (current if isinstance(current, int) else 0) + 1
        data.setdefault("evidence_state", "UNKNOWN")
        data["state_hash"] = compute_state_hash(data)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(emit_yaml(data))


# ===========================================================================
# schema 校验
# ===========================================================================
def validate(data: dict, verify_hash: bool = True) -> dict:
    """全量校验，返回 {verdict, errors, warnings}。"""
    errors, warnings = [], []

    for k in TOP_REQUIRED:
        if k not in data or data[k] in (None, ""):
            errors.append(f"顶层缺必填字段：{k}")

    # schema 容忍 v1→v2 迁移：缺省静默按 v2 兜底（旧台账无 schema 不硬报错），
    # 仅当为"未知非空值"时 WARN（写错/打错才提示）。
    sch = data.get("schema")
    if sch is not None and sch not in KNOWN_SCHEMAS:
        warnings.append(f"未知 schema={sch!r}（已知 {sorted(KNOWN_SCHEMAS)}），按 v2 兜底校验")
    if sch == SCHEMA_PASSPORT:
        revision = data.get("state_revision")
        if not isinstance(revision, int) or revision < 1:
            errors.append("v3 state_revision 必须是 >=1 的整数")
        evidence_state = data.get("evidence_state")
        if evidence_state not in EVIDENCE_STATES:
            errors.append(f"v3 evidence_state 非法：{evidence_state!r}")
        delivery_status = data.get("delivery_status")
        if delivery_status not in {"IN_PROGRESS", "DELIVERED"}:
            errors.append(f"v3 delivery_status 非法：{delivery_status!r}")
        if delivery_status == "DELIVERED" and not data.get(
                "delivery_authorization_id"):
            errors.append("v3 最终交付必须记录 delivery_authorization_id")
        state_hash = data.get("state_hash")
        if not isinstance(state_hash, str) or not re.fullmatch(
                r"sha256:[0-9a-f]{64}", state_hash):
            errors.append("v3 state_hash 必须是 sha256:<64 hex>")
        elif verify_hash and state_hash != compute_state_hash(data):
            errors.append("v3 state_hash 与 canonical state 内容不一致")

    stages = data.get("stages")
    if not isinstance(stages, list):
        errors.append("stages 必须是序列")
        stages = []

    seen_nums = []
    deps_by_stage = {}
    be_refs = []  # v2：收集 (tag, idx, side, 引用序号) 待 seen_set 就绪后核验存在性
    for i, st in enumerate(stages):
        if not isinstance(st, dict):
            errors.append(f"stages[{i}] 不是映射")
            continue
        tag = f"stage[{st.get('stage', '?')}]"
        for k in STAGE_REQUIRED:
            if k not in st or st[k] in (None, ""):
                errors.append(f"{tag} 缺必填字段：{k}")
        num = st.get("stage")
        if isinstance(num, int):
            seen_nums.append(num)
        else:
            errors.append(f"{tag} 的 stage 必须是整数序号")
        # depends_on 校验（DAG 边）：必须是整数序号列表
        dep = st.get("depends_on")
        if dep is not None:
            if not isinstance(dep, list) or not all(isinstance(d, int) for d in dep):
                errors.append(f"{tag} depends_on 必须是整数序号列表")
            elif isinstance(num, int):
                deps_by_stage[num] = dep
        # gate 校验
        gate = st.get("gate")
        if isinstance(gate, dict):
            gt = gate.get("type")
            if gt not in GATE_TYPES:
                errors.append(f"{tag} gate.type 非法：{gt}（应为 {sorted(GATE_TYPES)}）")
            if gt == "confirm":
                res = gate.get("result")
                if res not in GATE_RESULTS:
                    errors.append(f"{tag} gate.result 非法：{res}"
                                  f"（应为 {sorted(GATE_RESULTS)}）")
                ev_state = gate.get("evidence_state")
                if sch == SCHEMA_PASSPORT and gate.get("evidence"):
                    if ev_state not in EVIDENCE_STATES:
                        errors.append(f"{tag} gate.evidence_state 非法或缺失：{ev_state!r}")
                    if gate.get("fresh") is not True:
                        errors.append(f"{tag} v3 confirm gate 必须 fresh=true；未盖时间戳不能交付")
                elif sch == SCHEMA_PASSPORT and res in GATE_RESULTS:
                    warnings.append(f"{tag} gate.result={res} 无 hash/timestamp，"
                                    "仅是 PLANNED 占位，不能证明 checkpoint 已运行")
            elif gt == "decision":
                if not gate.get("choice"):
                    errors.append(f"{tag} 决策点 gate 缺 choice")
                if gate.get("by") != "user":
                    warnings.append(f"{tag} 决策点 gate.by 建议为 user")
        elif gate is not None:
            errors.append(f"{tag} gate 必须是映射")
        # revision_rounds 校验（X-2）
        rr = st.get("revision_rounds")
        if rr is not None:
            if not isinstance(rr, int) or rr < 0:
                errors.append(f"{tag} revision_rounds 必须是非负整数")
            elif rr > MAX_REVISION_ROUNDS:
                warnings.append(f"{tag} revision_rounds={rr} 已超 {MAX_REVISION_ROUNDS} 轮"
                                f"返修上限，超出部分应转为 known_limitations 如实记录")
        # status 校验（v2 §3.2）：枚举合法性 + 与 artifacts/gate 派生的一致性。
        # 显式优先（采纳 spec §10 倾向）；仅当显式属"可派生子集"且与派生冲突时 WARN，
        # in_progress/needs_rework 为显式意图态，不做冲突校验。
        stt = st.get("status")
        if stt is not None:
            if stt not in VALID_STATUS:
                errors.append(f"{tag} status 非法：{stt}（应属 {sorted(VALID_STATUS)}）")
            elif stt in DERIVABLE_STATUS:
                drv = derive_status(st)
                if drv != stt:
                    warnings.append(f"{tag} status={stt} 与据 artifacts/gate 派生的 {drv} "
                                    f"不一致（显式优先，请核对是否漏更新）")
        stage_evidence = st.get("evidence_state")
        if stage_evidence is not None and stage_evidence not in EVIDENCE_STATES:
            errors.append(f"{tag} evidence_state 非法：{stage_evidence!r}")
        # node_kind 校验（v2）
        nk = st.get("node_kind")
        if nk is not None and nk not in NODE_KINDS:
            errors.append(f"{tag} node_kind 非法：{nk}（应属 {sorted(NODE_KINDS)}）")
        # back_edges 校验（v2 一等公民）：结构 + to 归属 + 收集 from/to 待存在性核验。
        # 注意：back_edges 不进 deps_by_stage，故**不参与拓扑序/环检测**——回边天然不破坏拓扑。
        be = st.get("back_edges")
        if be is not None:
            if not isinstance(be, list):
                errors.append(f"{tag} back_edges 必须是序列")
            else:
                for j, e in enumerate(be):
                    if not isinstance(e, dict):
                        errors.append(f"{tag} back_edges[{j}] 必须是映射")
                        continue
                    required_edge_fields = (
                        BACK_EDGE_REQUIRED if sch == SCHEMA_PASSPORT
                        else ["from", "to", "root_cause"]
                    )
                    for rk in required_edge_fields:
                        if rk not in e or e[rk] in (None, ""):
                            errors.append(f"{tag} back_edges[{j}] 缺必填字段：{rk}")
                    if sch != SCHEMA_PASSPORT and not e.get("authorization_id"):
                        warnings.append(f"{tag} back_edges[{j}] 是 legacy 回边，"
                                        "缺 authorization_id；迁移时只能标 UNKNOWN")
                    frm, to = e.get("from"), e.get("to")
                    if not isinstance(frm, int):
                        errors.append(f"{tag} back_edges[{j}].from 必须是 stage 整数序号")
                    if not isinstance(to, int):
                        errors.append(f"{tag} back_edges[{j}].to 必须是 stage 整数序号")
                    if isinstance(to, int) and isinstance(num, int) and to != num:
                        warnings.append(f"{tag} back_edges[{j}].to={to} 与所在阶段 {num} "
                                        f"不一致（回边应记在回炉目标阶段上）")
                    if isinstance(frm, int) and isinstance(to, int) and frm == to:
                        errors.append(f"{tag} back_edges[{j}] from==to={frm} 自指回边非法")
                    if isinstance(frm, int) and isinstance(to, int) and to > frm:
                        errors.append(f"{tag} back_edges[{j}] {frm}→{to} 是前向边，"
                                      "不能伪造成 back-edge")
                    if e.get("by") not in (None, "user"):
                        warnings.append(f"{tag} back_edges[{j}].by={e.get('by')!r} 建议为 user"
                                        f"（回炉是用户决策，不应自主）")
                    if isinstance(frm, int):
                        be_refs.append((tag, j, "from", frm))
                    if isinstance(to, int):
                        be_refs.append((tag, j, "to", to))

    # stage 序号不可重复
    if len(seen_nums) != len(set(seen_nums)):
        errors.append(f"stage 序号有重复：{seen_nums}")

    # 拓扑序校验：有 depends_on 时按 DAG 判定（修与并行文档的矛盾）；
    # 无任何 depends_on 时退回"建议升序"——乱序只 WARN 不 FAIL（线性链兜底）。
    seen_set = set(seen_nums)
    # v2：回边 from/to 必须指向存在的 stage（结构完整性；不影响拓扑，仅查引用）。
    for (tag, j, side, ref) in be_refs:
        if ref not in seen_set:
            errors.append(f"{tag} back_edges[{j}].{side}={ref} 指向不存在的 stage")
    if deps_by_stage:
        appeared = []
        for st in stages:
            if not isinstance(st, dict):
                continue
            num = st.get("stage")
            if not isinstance(num, int):
                continue
            for d in deps_by_stage.get(num, []):
                if d not in seen_set:
                    errors.append(f"stage[{num}] depends_on={d} 指向不存在的阶段")
                elif d == num:
                    errors.append(f"stage[{num}] depends_on 不能依赖自身（环）")
                elif d not in appeared:
                    errors.append(f"stage[{num}] 出现在其依赖 stage[{d}] 之前"
                                  f"（违反拓扑序）")
            appeared.append(num)
        # 环检测（DFS）
        cyc = _detect_cycle(deps_by_stage, seen_set)
        if cyc:
            errors.append(f"depends_on 存在环：{cyc}")
    else:
        if seen_nums != sorted(seen_nums):
            warnings.append(f"stage 序号未按升序排列：{seen_nums}"
                            f"（线性链建议升序；若为并行/乱序请用 depends_on 声明依赖）")

    # current_stage 应等于最后一条 stage
    cs = data.get("current_stage")
    if isinstance(cs, int) and seen_nums and cs != max(seen_nums):
        warnings.append(f"current_stage={cs} 与最大 stage 序号 {max(seen_nums)} 不一致")

    verdict = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"verdict": verdict, "errors": errors, "warnings": warnings}


def revision_rounds_used(data: dict, stage_num: int) -> int:
    """断点恢复后查某阶段已用返修轮次（X-2 防配额跨会话刷新）。"""
    for st in data.get("stages") or []:
        if isinstance(st, dict) and st.get("stage") == stage_num:
            rr = st.get("revision_rounds")
            return rr if isinstance(rr, int) else 0
    return 0


def derive_status(st: dict) -> str:
    """从 artifacts + gate 派生 stage 状态（迁移兜底：旧台账无显式 status 时用）。

    只产**可派生三态**（DERIVABLE_STATUS）：
      - gate.result == FAIL                              → gate_failed
      - 有 artifacts（PASS / WARN / FAIL→PASS 均算已交付）→ delivered
      - 否则                                              → not_started
    in_progress（无产物信号）与 needs_rework（由 add-back-edge 显式置位）**不从产物派生**。
    诚实说明：v1 旧台账无 back_edges 字段，迁移兜底无需考虑"未消解回边"；v2 运行期
    needs_rework 由显式 status 承载（add-back-edge 置位、重交付后翻 delivered）。
    """
    gate = st.get("gate")
    result = gate.get("result") if isinstance(gate, dict) else None
    if result == "FAIL":
        return "gate_failed"
    if st.get("artifacts"):
        return "delivered"
    return "not_started"


def effective_status(st: dict) -> str:
    """取某阶段的有效状态：显式 status 优先，缺则派生（迁移容忍）。"""
    stt = st.get("status")
    if stt in VALID_STATUS:
        return stt
    return derive_status(st)


def migrate_data(data: dict) -> tuple[dict, list[str]]:
    """Explicitly migrate v1/v2 state to v3 without inventing authorization."""
    migrated = _canonical_clone(data)
    notes: list[str] = []
    old_schema = migrated.get("schema") or "light.passport.v1"
    if old_schema == SCHEMA_PASSPORT:
        return migrated, notes
    if old_schema not in KNOWN_SCHEMAS:
        raise ValueError(f"cannot migrate unknown schema {old_schema!r}")
    for st in migrated.get("stages") or []:
        if not isinstance(st, dict):
            continue
        st.setdefault("node_kind", "pipeline")
        st.setdefault("status", derive_status(st))
        gate = st.get("gate") if isinstance(st.get("gate"), dict) else {}
        result = gate.get("result")
        if result == "FAIL":
            st.setdefault("evidence_state", "FAILED")
        elif gate.get("evidence"):
            st.setdefault("evidence_state", "VERIFIED")
        else:
            st.setdefault("evidence_state", "UNKNOWN")
        if gate:
            gate.setdefault(
                "evidence_state",
                "FAILED" if result == "FAIL" else (
                    "VERIFIED" if gate.get("evidence") else "UNKNOWN"))
            gate.setdefault(
                "fresh",
                bool(gate.get("evidence") and "@" in str(gate.get("evidence"))
                     and not str(gate.get("evidence")).endswith("@unstamped")))
        for edge in st.get("back_edges") or []:
            if not isinstance(edge, dict):
                continue
            if not edge.get("authorization_id"):
                edge["authorization_id"] = "UNKNOWN"
                notes.append(
                    f"stage[{st.get('stage')}] legacy back-edge authorization is UNKNOWN")
            edge.setdefault("evidence_ptr", "UNKNOWN")
            edge.setdefault("round", st.get("revision_rounds") or 1)
            edge.setdefault("by", "user")
            edge.setdefault("at", migrated.get("updated") or "UNKNOWN")
    any_failed = any(
        isinstance(st, dict) and effective_status(st) == "gate_failed"
        for st in migrated.get("stages") or []
    )
    migrated["schema"] = SCHEMA_PASSPORT
    migrated["state_revision"] = 0
    migrated["state_hash"] = "sha256:" + ("0" * 64)
    migrated["evidence_state"] = "FAILED" if any_failed else "UNKNOWN"
    current = migrated.get("current_stage", 0)
    migrated["next_action"] = (
        f"inspect failed stage {current} and run reroute"
        if any_failed else f"resume from stage {current}")
    migrated["delivery_status"] = "IN_PROGRESS"
    migrated["delivery_authorization_id"] = None
    notes.append(f"schema {old_schema} -> {SCHEMA_PASSPORT}")
    return migrated, notes


def stage_back_edges(data: dict, stage_num: int) -> list:
    """取记在某阶段（作为回炉目标）上的回边列表。"""
    for st in data.get("stages") or []:
        if isinstance(st, dict) and st.get("stage") == stage_num:
            be = st.get("back_edges")
            return be if isinstance(be, list) else []
    return []


def _detect_cycle(deps_by_stage: dict, nodes: set):
    """DFS 检测 depends_on 图中的环；返回环上的节点列表或 None。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    stack_path = []

    def visit(u):
        color[u] = GRAY
        stack_path.append(u)
        for v in deps_by_stage.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                return stack_path[stack_path.index(v):] + [v]
            if color[v] == WHITE:
                r = visit(v)
                if r:
                    return r
        color[u] = BLACK
        stack_path.pop()
        return None

    for n in nodes:
        if color[n] == WHITE:
            r = visit(n)
            if r:
                return r
    return None


# ===========================================================================
# 输入指纹 + stale 判定（DAG/幂等：把"已完成阶段是否仍有效"从判断变计算）
# ===========================================================================
def compute_fingerprint(paths, root: str = ".") -> str:
    """Hash artifact paths and bytes; mtime alone is never freshness evidence."""
    h = hashlib.sha256()
    for p in sorted(paths or []):
        ap = os.path.join(root, p) if not os.path.isabs(p) else p
        h.update(p.encode("utf-8"))
        if os.path.exists(ap):
            h.update(b"|")
            with open(ap, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
        else:
            h.update(b"|MISSING")
        h.update(b";")
    return "sha256:" + h.hexdigest()


def _upstream_artifacts(data: dict, stage_num: int) -> list:
    """收集某阶段所有 depends_on 上游阶段的 artifacts 路径并集。"""
    by_num = {st.get("stage"): st for st in (data.get("stages") or [])
              if isinstance(st, dict)}
    st = by_num.get(stage_num)
    if not st:
        return []
    out = []
    for d in st.get("depends_on") or []:
        up = by_num.get(d)
        if up and isinstance(up.get("artifacts"), list):
            out.extend(up["artifacts"])
    return out


def stage_status(data: dict, stage_num: int, root: str = ".") -> dict:
    """判定某阶段当前状态：fresh / stale / incomplete / no_fingerprint。

    - incomplete：本阶段无 artifacts 或文件不存在 → 未真正完成。
    - no_fingerprint：未记录 inputs_fingerprint，无法计算（退回人工判断）。
    - stale：上游 artifacts 指纹与记录不符 → 上游变了，需重验本阶段。
    - fresh：本阶段产物在 + 上游指纹未变 → 已完成且仍有效，可不重跑。
    """
    by_num = {st.get("stage"): st for st in (data.get("stages") or [])
              if isinstance(st, dict)}
    st = by_num.get(stage_num)
    if not st:
        return {"stage": stage_num, "state": "missing", "reason": "无此阶段记录"}
    arts = st.get("artifacts") or []
    missing = [a for a in arts
               if not os.path.exists(os.path.join(root, a)
                                     if not os.path.isabs(a) else a)]
    if not arts or missing:
        return {"stage": stage_num, "state": "incomplete",
                "reason": f"产物缺失：{missing or '未登记任何 artifact'}"}
    recorded = st.get("inputs_fingerprint")
    if not recorded:
        return {"stage": stage_num, "state": "no_fingerprint",
                "reason": "未记录 inputs_fingerprint，无法计算 stale，退回人工判断"}
    up = _upstream_artifacts(data, stage_num)
    current = compute_fingerprint(up, root)
    if current == recorded:
        return {"stage": stage_num, "state": "fresh",
                "reason": "产物在且上游指纹未变", "fingerprint": current}
    return {"stage": stage_num, "state": "stale",
            "reason": "上游 artifacts 指纹已变，需重验本阶段",
            "recorded": recorded, "current": current,
            "upstream": up}


def stale_check(data: dict, root: str = ".") -> dict:
    """逐阶段判定 fresh/stale，给出最小重验范围（断点恢复时调用）。"""
    results = []
    for st in data.get("stages") or []:
        if isinstance(st, dict) and isinstance(st.get("stage"), int):
            results.append(stage_status(data, st["stage"], root))
    need_reverify = [r["stage"] for r in results
                     if r["state"] in ("stale", "incomplete")]
    return {"stages": results, "need_reverify": need_reverify}


# ===========================================================================
# 子命令实现
# ===========================================================================
def cmd_init(args) -> int:
    if os.path.exists(args.out) and not args.force:
        print(f"[init] 已存在：{args.out}（续跑场景，勿覆盖；要重建加 --force）",
              file=sys.stderr)
        return 1
    created = args.created or now_minute()
    data = {
        "schema": SCHEMA_PASSPORT,
        "project": args.project,
        "pipeline": args.pipeline,
        "created": created,
        "updated": created,
        "current_stage": 0,
        "state_revision": 0,
        "state_hash": "sha256:" + ("0" * 64),
        "evidence_state": "PLANNED",
        "next_action": "confirm project scope and append the first selected pipeline stage",
        "delivery_status": "IN_PROGRESS",
        "delivery_authorization_id": None,
        "stages": [],
    }
    if getattr(args, "dag_template", None):
        data["dag_template"] = args.dag_template
    save(args.out, data)
    print(f"[init] 已建台账：{args.out}（schema={SCHEMA_PASSPORT} "
          f"project={args.project} pipeline={args.pipeline}）")
    return 0


def _kv_list(pairs):
    """把 ['k=v', ...] 解析成有序 dict。"""
    out = {}
    for p in pairs or []:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip()] = _scalar(v)
    return out


def cmd_append_stage(args) -> int:
    data = load(args.file)
    stage = {
        "stage": args.stage,
        "skill": args.skill,
        "input": args.input,
        "output": args.output,
        "node_kind": "pipeline",
        "evidence_state": "PLANNED",
    }
    if args.round is not None:
        stage["round"] = args.round
    if args.revision_rounds is not None:
        stage["revision_rounds"] = args.revision_rounds
    if getattr(args, "depends_on", None):
        stage["depends_on"] = list(args.depends_on)
    # v2：显式 status / node_kind（不给 status 则留空，validate 时按 artifacts+gate 派生）。
    if getattr(args, "status", None):
        stage["status"] = args.status
    if getattr(args, "node_kind", None):
        stage["node_kind"] = args.node_kind
    if args.artifacts:
        stage["artifacts"] = list(args.artifacts)
    # 自动算输入指纹：未显式给 --inputs-fingerprint 时，按 depends_on 上游产物算
    if getattr(args, "inputs_fingerprint", None):
        stage["inputs_fingerprint"] = args.inputs_fingerprint
    elif getattr(args, "auto_fingerprint", False) and stage.get("depends_on"):
        # 需要先把 stage 临时并入 data 才能解析上游
        tmp = dict(data)
        tmp_stages = list(data.get("stages") or []) + [stage]
        tmp["stages"] = tmp_stages
        up = _upstream_artifacts(tmp, args.stage)
        if up:
            stage["inputs_fingerprint"] = compute_fingerprint(
                up, getattr(args, "root", ".") or ".")
    gate = {}
    if args.gate_type:
        gate["type"] = args.gate_type
        if args.gate_type == "confirm" and args.gate_result:
            gate["result"] = args.gate_result
        if args.gate_type == "decision":
            if args.gate_choice:
                gate["choice"] = args.gate_choice
            gate["by"] = "user"
        if args.gate_notes:
            gate["notes"] = args.gate_notes
    extra = _kv_list(args.gate_kv)
    gate.update(extra)
    if gate:
        gate.setdefault("evidence_state", "PLANNED")
        gate.setdefault("fresh", False)
        stage["gate"] = gate
    if args.gaps:
        stage["gaps"] = list(args.gaps)

    if not isinstance(data.get("stages"), list):
        data["stages"] = []
    data["stages"].append(stage)
    data["current_stage"] = args.stage
    data["updated"] = now_minute()
    data["evidence_state"] = "PLANNED"
    data["next_action"] = f"run or resume stage {args.stage} ({args.skill})"

    rep = validate(data, verify_hash=False)
    if rep["verdict"] == "FAIL":
        for e in rep["errors"]:
            print(f"  [ERR] {e}", file=sys.stderr)
        print("[append-stage] 校验未过，未写入。", file=sys.stderr)
        return 1
    save(args.file, data)
    for w in rep["warnings"]:
        print(f"  [WARN] {w}", file=sys.stderr)
    print(f"[append-stage] 已追加 stage={args.stage} skill={args.skill}，"
          f"current_stage→{args.stage}")
    return 0


def cmd_get_current_stage(args) -> int:
    data = load(args.file)
    cs = data.get("current_stage")
    print(f"current_stage: {cs}")
    stages = data.get("stages") or []
    cur = None
    for st in stages:
        if isinstance(st, dict) and st.get("stage") == cs:
            cur = st
    if cur:
        print(f"  skill : {cur.get('skill')}")
        print(f"  status: {effective_status(cur)}"
              + ("" if cur.get("status") else "（派生：未显式登记 status）"))
        print(f"  output: {cur.get('output')}")
        gate = cur.get("gate") or {}
        print(f"  gate  : {gate}")
        rr = cur.get("revision_rounds")
        if rr is not None:
            print(f"  revision_rounds: {rr}/{MAX_REVISION_ROUNDS}（续跑时从此读，勿重置）")
        be = cur.get("back_edges") or []
        if be:
            print(f"  back_edges: {len(be)} 条回炉记录（本阶段为回炉目标）")
    else:
        print("  （无匹配阶段记录，可能尚未追加任何 stage）")
    return 0


def cmd_add_back_edge(args) -> int:
    """在回炉目标阶段（--to）记一条回边，并置其 status=needs_rework。

    这是"根因回炉"落账的唯一入口：reroute.py 只产**建议**，用户拍板后由本命令写台账
    （回炉是决策点，绝不自主——见 orchestrator-spec §2.2/§5）。回边记在回炉目标上。
    """
    data = load(args.file)
    by_num = {st.get("stage"): st for st in (data.get("stages") or [])
              if isinstance(st, dict)}
    if args.to not in by_num:
        print(f"[add-back-edge] 回炉目标 stage={args.to} 不存在", file=sys.stderr)
        return 1
    if args.from_stage not in by_num:
        print(f"[add-back-edge] 触发源 stage={args.from_stage} 不存在", file=sys.stderr)
        return 1
    if args.to >= args.from_stage:
        print(f"[add-back-edge] 非法回边 {args.from_stage}→{args.to}："
              "to 必须严格小于 from；2⊣3 属 admission hold，不能落 back-edge",
              file=sys.stderr)
        return 1
    if not getattr(args, "authorization_id", None):
        print("[add-back-edge] 缺 --authorization-id；reroute 只建议，"
              "必须绑定用户明确授权后才能落账", file=sys.stderr)
        return 1
    target = by_num[args.to]
    rec = {"from": args.from_stage, "to": args.to, "root_cause": args.root_cause}
    if args.evidence_ptr:
        rec["evidence_ptr"] = args.evidence_ptr
    rec["round"] = (args.round if args.round is not None
                    else revision_rounds_used(data, args.to) + 1)
    rec["by"] = args.by or "user"
    rec["at"] = args.at or now_minute()
    rec["authorization_id"] = args.authorization_id
    if rec["round"] > MAX_REVISION_ROUNDS:
        print(f"[add-back-edge] stage[{args.to}] 返修将达 {rec['round']} 轮，"
              f"超过上限 {MAX_REVISION_ROUNDS}；应请求用户转 known limitation",
              file=sys.stderr)
        return 1
    target.setdefault("back_edges", []).append(rec)
    # 回炉目标置为待返修（显式意图态）；重交付后由 run_checkpoint / set-status 翻 delivered。
    target["status"] = "needs_rework"
    target["revision_rounds"] = rec["round"]
    target["evidence_state"] = "PLANNED"
    data["updated"] = now_minute()
    data["evidence_state"] = "PLANNED"
    data["next_action"] = (
        f"repair stage {args.to} for authorized root cause: {args.root_cause}")
    rep = validate(data, verify_hash=False)
    if rep["verdict"] == "FAIL":
        for e in rep["errors"]:
            print(f"  [ERR] {e}", file=sys.stderr)
        print("[add-back-edge] 校验未过，未写入。", file=sys.stderr)
        return 1
    save(args.file, data)
    for w in rep["warnings"]:
        print(f"  [WARN] {w}", file=sys.stderr)
    print(f"[add-back-edge] stage[{args.to}] ← 回边 from stage[{args.from_stage}]"
          f"（根因：{args.root_cause}，round={rec['round']}），status→needs_rework")
    return 0


def cmd_set_status(args) -> int:
    """显式置某阶段 status（in_progress/delivered 等转移）。"""
    data = load(args.file)
    if args.status not in VALID_STATUS:
        print(f"[set-status] 非法 status={args.status}（应属 {sorted(VALID_STATUS)}）",
              file=sys.stderr)
        return 1
    hit = None
    for st in data.get("stages") or []:
        if isinstance(st, dict) and st.get("stage") == args.stage:
            hit = st
            break
    if hit is None:
        print(f"[set-status] 无 stage={args.stage}", file=sys.stderr)
        return 1
    old = hit.get("status")
    hit["status"] = args.status
    hit["evidence_state"] = "FAILED" if args.status == "gate_failed" else "PLANNED"
    data["updated"] = now_minute()
    data["evidence_state"] = hit["evidence_state"]
    data["next_action"] = f"continue stage {args.stage} from status {args.status}"
    rep = validate(data, verify_hash=False)
    if rep["verdict"] == "FAIL":
        for e in rep["errors"]:
            print(f"  [ERR] {e}", file=sys.stderr)
        print("[set-status] 校验未过，未写入。", file=sys.stderr)
        return 1
    save(args.file, data)
    for w in rep["warnings"]:
        print(f"  [WARN] {w}", file=sys.stderr)
    print(f"[set-status] stage[{args.stage}] status: {old} → {args.status}")
    return 0


def cmd_validate(args) -> int:
    data = load(args.file)
    rep = validate(data)
    for e in rep["errors"]:
        print(f"  [ERR]  {e}")
    for w in rep["warnings"]:
        print(f"  [WARN] {w}")
    print(f"[validate] verdict={rep['verdict']}")
    return 1 if rep["verdict"] == "FAIL" else 0


def cmd_migrate(args) -> int:
    data = load(args.file)
    try:
        migrated, notes = migrate_data(data)
    except ValueError as exc:
        print(f"[migrate] {exc}", file=sys.stderr)
        return 1
    if data.get("schema") == SCHEMA_PASSPORT:
        print("[migrate] already light.passport.v3; no change")
        return 0
    if args.write:
        save(args.file, migrated)
        checked = validate(load(args.file))
        if checked["verdict"] == "FAIL":
            print(f"[migrate] post-write validation failed: {checked['errors']}",
                  file=sys.stderr)
            return 1
        print(f"[migrate] wrote {args.file}; state_hash={load(args.file).get('state_hash')}")
    else:
        preview = json.loads(json.dumps(migrated, ensure_ascii=False))
        preview["state_revision"] = 1
        preview["state_hash"] = compute_state_hash(preview)
        print(emit_yaml(preview))
        print("[migrate] dry-run only; add --write after user authorization",
              file=sys.stderr)
    for note in notes:
        print(f"  [NOTE] {note}", file=sys.stderr)
    return 0


def cmd_authorize_delivery(args) -> int:
    """Record an explicit final-delivery decision after freshness checks."""
    data = load(args.file)
    if not args.authorization_id:
        print("[authorize-delivery] 缺用户 authorization_id", file=sys.stderr)
        return 1
    checked = validate(data)
    if checked["verdict"] == "FAIL":
        print(f"[authorize-delivery] passport invalid: {checked['errors']}",
              file=sys.stderr)
        return 1
    stages = [st for st in data.get("stages") or [] if isinstance(st, dict)]
    blockers = []
    if not stages:
        blockers.append("没有已选择的 pipeline stage")
    for st in stages:
        number = st.get("stage")
        if effective_status(st) != "delivered":
            blockers.append(f"stage[{number}] status={effective_status(st)}")
        if st.get("evidence_state") != "VERIFIED":
            blockers.append(
                f"stage[{number}] evidence_state={st.get('evidence_state')}"
            )
        gate = st.get("gate")
        if isinstance(gate, dict) and gate.get("type") == "confirm":
            if gate.get("fresh") is not True:
                blockers.append(f"stage[{number}] confirm gate is not fresh")
    stale = stale_check(data, args.root)
    if stale["need_reverify"]:
        blockers.append(f"need_reverify={stale['need_reverify']}")
    if blockers:
        print("[authorize-delivery] BLOCKED: " + "; ".join(blockers),
              file=sys.stderr)
        return 1
    limitations = data.setdefault("known_limitations", [])
    for item in args.known_limitation or []:
        if item not in limitations:
            limitations.append(item)
    data["delivery_status"] = "DELIVERED"
    data["delivery_authorization_id"] = args.authorization_id
    data["updated"] = args.at or now_minute()
    data["evidence_state"] = "VERIFIED"
    data["next_action"] = (
        "delivery authorized and recorded; preserve the hash-bound handoff "
        "and reopen only through a new intake"
    )
    save(args.file, data)
    final = validate(load(args.file))
    if final["verdict"] == "FAIL":
        print(f"[authorize-delivery] post-write invalid: {final['errors']}",
              file=sys.stderr)
        return 1
    print(f"[authorize-delivery] DELIVERED authorization={args.authorization_id} "
          f"known_limitations={len(limitations)}")
    return 0


def cmd_fingerprint(args) -> int:
    fp = compute_fingerprint(args.paths, args.root or ".")
    print(fp)
    return 0


def cmd_stale_check(args) -> int:
    data = load(args.file)
    rep = stale_check(data, args.root or ".")
    for r in rep["stages"]:
        print(f"  stage[{r['stage']}] {r['state']:14s} {r['reason']}")
    nr = rep["need_reverify"]
    if nr:
        print(f"[stale-check] 需重验的最小范围（stale/incomplete）：{nr}")
    else:
        print("[stale-check] 全部 fresh / no_fingerprint，无 stale 阶段")
    # 有 stale/incomplete 不算硬失败，返回 0；供编排器读列表做决定
    return 0


# ===========================================================================
# 离线自测（合成样例，自清理无残留）
# ===========================================================================
class _NS:
    """轻量 argparse.Namespace 替身，供 selftest 直接调子命令。"""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _mk_append(path, **kw):
    return _NS(
        file=path,
        stage=kw["stage"], skill=kw["skill"],
        input=kw.get("input", "in"), output=kw.get("output", "out"),
        round=kw.get("round"), revision_rounds=kw.get("revision_rounds"),
        depends_on=kw.get("depends_on"),
        status=kw.get("status"), node_kind=kw.get("node_kind"),
        inputs_fingerprint=kw.get("inputs_fingerprint"),
        auto_fingerprint=kw.get("auto_fingerprint", False),
        root=kw.get("root", "."),
        artifacts=kw.get("artifacts"),
        gate_type=kw.get("gate_type"), gate_result=kw.get("gate_result"),
        gate_choice=kw.get("gate_choice"), gate_notes=kw.get("gate_notes"),
        gate_kv=kw.get("gate_kv"), gaps=kw.get("gaps"),
    )


def selftest() -> int:
    ok = True
    tmp = tempfile.mkdtemp(prefix="passport_selftest_")
    path = os.path.join(tmp, "passport.yaml")
    try:
        # 1. init
        rc = cmd_init(_NS(out=path, force=False, project="demo",
                          pipeline="A", created="2026-06-08T09:00"))
        ok &= (rc == 0 and os.path.exists(path))
        print(f"  [{'OK' if rc == 0 else 'FAIL'}] init")

        # 2. 合法 confirm 阶段
        rc = cmd_append_stage(_mk_append(path, stage=1, skill="m01",
                              artifacts=["docs/lit.md"],
                              gate_type="confirm", gate_result="PASS"))
        ok &= (rc == 0)
        print(f"  [{'OK' if rc == 0 else 'FAIL'}] append confirm/PASS")

        # 3. 决策点 + 返修轮次
        rc = cmd_append_stage(_mk_append(path, stage=4, skill="m04", round=2,
                              revision_rounds=1, gate_type="decision",
                              gate_choice="微调放行"))
        ok &= (rc == 0)
        print(f"  [{'OK' if rc == 0 else 'FAIL'}] append decision + revision_rounds")

        # 4. FAIL->PASS 诚信门 + GAP
        rc = cmd_append_stage(_mk_append(path, stage=8, skill="m07",
                              revision_rounds=1, gate_type="confirm",
                              gate_result="FAIL->PASS",
                              gate_notes="2 处幻觉引用已删",
                              gaps=["[RESULT GAP] 待补敏感性分析"]))
        ok &= (rc == 0)
        print(f"  [{'OK' if rc == 0 else 'FAIL'}] append FAIL->PASS + gaps")

        # 5. 读写往返一致：重新 load 再 validate
        data = load(path)
        rep = validate(data)
        good = rep["verdict"] in ("PASS", "WARN")
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] round-trip validate "
              f"verdict={rep['verdict']}")

        # 6. revision_rounds_used 读取（X-2 防刷新核心 API）
        used = revision_rounds_used(data, 8)
        ok &= (used == 1)
        print(f"  [{'OK' if used == 1 else 'FAIL'}] revision_rounds_used(8)={used}")

        # 7. 非法 gate.result 枚举被拦
        bad = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
               "current_stage": 1,
               "stages": [{"stage": 1, "skill": "m1", "input": "i", "output": "o",
                           "gate": {"type": "confirm", "result": "GREAT"}}]}
        rep = validate(bad)
        hit = any("gate.result" in e for e in rep["errors"])
        good = rep["verdict"] == "FAIL" and hit
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] reject illegal gate.result")

        # 8. stage 乱序（无 depends_on）：降级为 WARN 而非 FAIL
        #    （修与并行文档矛盾：乱序合法，只提示用 depends_on 声明依赖）
        bad2 = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
                "current_stage": 3,
                "stages": [{"stage": 3, "skill": "m1", "input": "i", "output": "o"},
                           {"stage": 2, "skill": "m2", "input": "i", "output": "o"}]}
        rep = validate(bad2)
        hit = any("升序" in w for w in rep["warnings"])
        good = rep["verdict"] == "WARN" and hit
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] out-of-order→WARN (not hard FAIL)")

        # 9. 缺必填字段被拦
        bad3 = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
                "current_stage": 1,
                "stages": [{"stage": 1, "skill": "m1", "output": "o"}]}
        rep = validate(bad3)
        hit = any("input" in e for e in rep["errors"])
        good = rep["verdict"] == "FAIL" and hit
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] reject missing required field")

        # 10. DAG：合法并行（10∥11，乱序但满足拓扑序）应 PASS（修并行矛盾）
        par = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
               "current_stage": 11,
               "stages": [
                   {"stage": 9, "skill": "m06", "input": "i", "output": "o"},
                   {"stage": 11, "skill": "m10", "input": "i", "output": "o",
                    "depends_on": [9]},
                   {"stage": 10, "skill": "m11", "input": "i", "output": "o",
                    "depends_on": [9]}]}
        rep = validate(par)
        good = rep["verdict"] in ("PASS", "WARN")
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] accept parallel DAG (10∥11) "
              f"verdict={rep['verdict']}")

        # 11. DAG：依赖出现在被依赖之前 → 违反拓扑序，FAIL
        topo = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
                "current_stage": 2,
                "stages": [
                    {"stage": 2, "skill": "m2", "input": "i", "output": "o",
                     "depends_on": [3]},
                    {"stage": 3, "skill": "m3", "input": "i", "output": "o"}]}
        rep = validate(topo)
        hit = any("拓扑序" in e for e in rep["errors"])
        good = rep["verdict"] == "FAIL" and hit
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] reject topo-order violation")

        # 12. DAG：环被拦
        cyc = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
               "current_stage": 2,
               "stages": [
                   {"stage": 1, "skill": "m1", "input": "i", "output": "o",
                    "depends_on": [2]},
                   {"stage": 2, "skill": "m2", "input": "i", "output": "o",
                    "depends_on": [1]}]}
        rep = validate(cyc)
        hit = any("环" in e for e in rep["errors"])
        ok &= (rep["verdict"] == "FAIL" and hit)
        print(f"  [{'OK' if rep['verdict'] == 'FAIL' and hit else 'FAIL'}] "
              f"reject dependency cycle")

        # 13. 指纹 + stale 判定：建上游产物→算指纹→改产物→判 stale
        up_art = os.path.join(tmp, "up.txt")
        with open(up_art, "w", encoding="utf-8") as fh:
            fh.write("v1")
        fp1 = compute_fingerprint([up_art])
        fdata = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
                 "current_stage": 2,
                 "stages": [
                     {"stage": 1, "skill": "m1", "input": "i", "output": "o",
                      "artifacts": [up_art]},
                     {"stage": 2, "skill": "m2", "input": "i", "output": "o",
                      "depends_on": [1], "artifacts": [up_art],
                      "inputs_fingerprint": fp1}]}
        s = stage_status(fdata, 2)
        good = s["state"] == "fresh"
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] stage_status fresh when unchanged")

        # 改上游产物（确保 mtime/size 变），重判应 stale
        import time as _t
        _t.sleep(0.01)
        with open(up_art, "w", encoding="utf-8") as fh:
            fh.write("v2-changed-content")
        s2 = stage_status(fdata, 2)
        good = s2["state"] == "stale"
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] stage_status stale when changed")

        # 14. stale-check 汇总：need_reverify 含 stage 2
        rep = stale_check(fdata)
        good = 2 in rep["need_reverify"]
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] stale_check flags need_reverify={rep['need_reverify']}")

        # ============== v2 新增（status / 一等回边 / 迁移容忍 / 降级）==============
        import copy as _copy
        # 15. 含一等回边的 DAG：拓扑/状态校验通过，且**回边不破坏拓扑**（核心演示）。
        v2dag = {
            "schema": "light.passport.v2", "project": "p", "pipeline": "A",
            "created": "x", "updated": "x", "current_stage": 7,
            "stages": [
                {"stage": 3, "skill": "idea-generation", "input": "i", "output": "o",
                 "status": "delivered", "artifacts": ["idea.md"]},
                {"stage": 4, "skill": "idea-critique", "input": "i", "output": "o",
                 "depends_on": [3], "status": "delivered", "artifacts": ["crit.md"]},
                {"stage": 5, "skill": "research-plan", "input": "i", "output": "o",
                 "depends_on": [4], "status": "needs_rework", "artifacts": ["plan.md"],
                 "back_edges": [{"from": 7, "to": 5, "root_cause": "结果不支撑假设",
                                 "evidence_ptr": "sha:ab12@2026-06-16T10:00",
                                 "round": 1, "by": "user", "at": "2026-06-16T10:00"}]},
                {"stage": 6, "skill": "experiment-coding", "input": "i", "output": "o",
                 "depends_on": [5], "status": "delivered", "artifacts": ["run.py"]},
                {"stage": 7, "skill": "result-analysis", "input": "i", "output": "o",
                 "depends_on": [6], "status": "gate_failed", "artifacts": ["res.md"],
                 "gate": {"type": "confirm", "result": "FAIL"}}]}
        rep = validate(v2dag)
        no_topo_err = not any(("拓扑序" in e or "环" in e) for e in rep["errors"])
        good = rep["verdict"] in ("PASS", "WARN") and no_topo_err
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] v2 含回边 DAG 校验通过 verdict={rep['verdict']}"
              f"，无拓扑/环错误={no_topo_err}")
        # 回边是拓扑惰性的：删掉所有 back_edges，verdict 不变
        nobe = _copy.deepcopy(v2dag)
        for s in nobe["stages"]:
            s.pop("back_edges", None)
        nobe_rep = validate(nobe)
        good = not any(("拓扑序" in e or "环" in e) for e in nobe_rep["errors"])
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] 回边拓扑惰性：有无回边均不改变 forward DAG 合法性")

        # 16. status 显式与派生冲突 → WARN（显式优先 + 提示，spec §10 倾向）
        conf = {"schema": "light.passport.v2", "project": "p", "pipeline": "A",
                "created": "x", "updated": "x", "current_stage": 1,
                "stages": [{"stage": 1, "skill": "s", "input": "i", "output": "o",
                            "status": "delivered"}]}  # 无 artifacts/gate → 派生 not_started
        rep = validate(conf)
        hit = any("不一致" in w for w in rep["warnings"])
        good = rep["verdict"] == "WARN" and hit
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] status 冲突→WARN（显式 delivered vs 派生 not_started）")

        # 17. v1→v2 迁移容忍：无 schema、无 status 的旧台账 validate 不报错 + 可派生
        v1old = {"project": "p", "pipeline": "A", "created": "x", "updated": "x",
                 "current_stage": 2,
                 "stages": [
                     {"stage": 1, "skill": "m01", "input": "i", "output": "o",
                      "artifacts": ["lit.md"], "gate": {"type": "confirm", "result": "PASS"}},
                     {"stage": 2, "skill": "m02", "input": "i", "output": "o",
                      "depends_on": [1], "gate": {"type": "confirm", "result": "FAIL"}}]}
        rep = validate(v1old)
        es1 = effective_status(v1old["stages"][0])  # 有产物+PASS → delivered
        es2 = effective_status(v1old["stages"][1])  # 无产物+FAIL → gate_failed
        good = (rep["verdict"] in ("PASS", "WARN")
                and es1 == "delivered" and es2 == "gate_failed")
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] v1→v2 迁移容忍：verdict={rep['verdict']} "
              f"派生 status=({es1},{es2})")

        # 18. mini-YAML 降级：**强制内置解析器**往返 v2 schema（PyYAML 装了也走 _mini_parse，
        #     确保降级路径真的覆盖 v2 新字段 back_edges/status/schema/dag_template）。
        rich = {"schema": "light.passport.v2", "project": "p", "pipeline": "A",
                "created": "x", "updated": "x", "current_stage": 7,
                "dag_template": "core-13",
                "stages": [
                    {"stage": 5, "skill": "research-plan", "status": "needs_rework",
                     "node_kind": "pipeline", "input": "i", "output": "o",
                     "artifacts": ["plan.md"], "revision_rounds": 1,
                     "gate": {"type": "confirm", "result": "FAIL->PASS"},
                     "back_edges": [{"from": 7, "to": 5, "root_cause": "结果不支撑假设",
                                     "evidence_ptr": "sha:ab12@2026-06-16T10:00",
                                     "round": 1, "by": "user", "at": "2026-06-16T10:00"}]},
                    {"stage": 7, "skill": "result-analysis", "input": "i", "output": "o",
                     "depends_on": [5], "status": "gate_failed", "artifacts": ["res.md"],
                     "gate": {"type": "confirm", "result": "FAIL"}}]}
        text = emit_yaml(rich)
        parsed = _mini_parse(text)
        st = parsed["stages"][0]
        be = (st.get("back_edges") or [{}])[0]
        good = (parsed.get("schema") == "light.passport.v2"
                and parsed.get("dag_template") == "core-13"
                and st.get("status") == "needs_rework"
                and st.get("node_kind") == "pipeline"
                and be.get("from") == 7 and be.get("to") == 5
                and be.get("root_cause") == "结果不支撑假设"
                and be.get("evidence_ptr") == "sha:ab12@2026-06-16T10:00"
                and be.get("by") == "user")
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] mini-YAML 强制降级往返 v2（回边/状态/schema 保真）")
        if not good:
            print("    parsed=", parsed)

        # 19. 真实 save→load 往返（本机装了 PyYAML，走 PyYAML 路径）v2 字段保真 + 校验通过
        rpath = os.path.join(tmp, "v2.yaml")
        save(rpath, rich)
        reloaded = load(rpath)
        st = reloaded["stages"][0]
        be = (st.get("back_edges") or [{}])[0]
        good = (reloaded.get("schema") == "light.passport.v2"
                and st.get("status") == "needs_rework"
                and be.get("from") == 7 and be.get("to") == 5
                and be.get("root_cause") == "结果不支撑假设"
                and validate(reloaded)["verdict"] in ("PASS", "WARN"))
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] save→load 往返 v2（PyYAML 路径）+ 校验通过")

        # 20. add-back-edge 命令：置回炉目标 needs_rework + 追加回边，拓扑仍有效
        apath = os.path.join(tmp, "abe.yaml")
        cmd_init(_NS(out=apath, force=False, project="d", pipeline="A",
                     created="2026-06-16T09:00", dag_template=None))
        cmd_append_stage(_mk_append(apath, stage=5, skill="research-plan",
                                    artifacts=["plan.md"], gate_type="confirm",
                                    gate_result="PASS"))
        cmd_append_stage(_mk_append(apath, stage=7, skill="result-analysis",
                                    depends_on=[5], artifacts=["res.md"],
                                    gate_type="confirm", gate_result="FAIL"))
        rc = cmd_add_back_edge(_NS(file=apath, to=5, from_stage=7,
                                   root_cause="结果不支撑假设",
                                   evidence_ptr="sha:cd34@2026-06-16T11:00",
                                   round=None, by="user", at="2026-06-16T11:00",
                                   authorization_id="user-msg:test-20"))
        reloaded = load(apath)
        st5 = [s for s in reloaded["stages"] if s.get("stage") == 5][0]
        good = (rc == 0 and st5.get("status") == "needs_rework"
                and len(st5.get("back_edges") or []) == 1
                and st5["back_edges"][0]["from"] == 7
                and st5.get("revision_rounds") == 1
                and st5["back_edges"][0]["authorization_id"] == "user-msg:test-20"
                and validate(reloaded)["verdict"] in ("PASS", "WARN"))
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] add-back-edge→needs_rework+回边落账，校验通过")

        # 21. admission hold / 自指 / 无授权不能伪造成 back-edge
        before = emit_yaml(reloaded)
        rc_forward = cmd_add_back_edge(_NS(
            file=apath, to=7, from_stage=5, root_cause="invalid forward",
            evidence_ptr="x", round=None, by="user", at="x",
            authorization_id="user-msg:x"))
        rc_noauth = cmd_add_back_edge(_NS(
            file=apath, to=5, from_stage=7, root_cause="missing auth",
            evidence_ptr="x", round=None, by="user", at="x",
            authorization_id=None))
        good = rc_forward == 1 and rc_noauth == 1 and emit_yaml(load(apath)) == before
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] reject forward/self/unauthorized back-edge")

        # 22. explicit v2→v3 migration preserves unknown authorization honestly.
        legacy = {
            "schema": "light.passport.v2", "project": "legacy", "pipeline": "A",
            "created": "x", "updated": "x", "current_stage": 7,
            "stages": [
                {"stage": 5, "skill": "research-plan", "input": "i", "output": "o",
                 "status": "needs_rework",
                 "back_edges": [{"from": 7, "to": 5, "root_cause": "x"}]},
                {"stage": 7, "skill": "result-analysis", "input": "i", "output": "o",
                 "depends_on": [5], "status": "gate_failed",
                 "gate": {"type": "confirm", "result": "FAIL"}}],
        }
        migrated, migration_notes = migrate_data(legacy)
        mpath = os.path.join(tmp, "migrated.yaml")
        save(mpath, migrated)
        checked = load(mpath)
        edge = checked["stages"][0]["back_edges"][0]
        good = (checked["schema"] == SCHEMA_PASSPORT
                and edge["authorization_id"] == "UNKNOWN"
                and checked["state_hash"] == compute_state_hash(checked)
                and validate(checked)["verdict"] in ("PASS", "WARN")
                and any("authorization is UNKNOWN" in n for n in migration_notes))
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] explicit v2→v3 migration + hash + UNKNOWN auth")

        # 23. PyYAML may materialize an unquoted YYYY-MM-DD as datetime.date.
        dated = load(apath)
        dated["updated"] = datetime.date(2026, 7, 4)
        save(apath, dated)
        checked = load(apath)
        good = (
            checked["state_hash"] == compute_state_hash(checked)
            and validate(checked)["verdict"] in ("PASS", "WARN")
        )
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] date-valued YAML state hashes canonically")

        # 24. final delivery requires explicit authorization, verified stages,
        # fresh artifacts and a recorded limitation.
        dpath = os.path.join(tmp, "delivery.yaml")
        artifact = os.path.join(tmp, "delivery.txt")
        with open(artifact, "w", encoding="utf-8") as fh:
            fh.write("verified delivery")
        cmd_init(_NS(out=dpath, force=False, project="delivery", pipeline="crop",
                     created="2026-07-04", dag_template=None))
        cmd_append_stage(_mk_append(
            dpath, stage=1, skill="m01", artifacts=["delivery.txt"],
            status="delivered"
        ))
        delivery_data = load(dpath)
        delivery_data["stages"][0]["evidence_state"] = "VERIFIED"
        delivery_data["evidence_state"] = "VERIFIED"
        save(dpath, delivery_data)
        denied = cmd_authorize_delivery(_NS(
            file=dpath, root=tmp, authorization_id="",
            known_limitation=[], at="2026-07-04"))
        accepted = cmd_authorize_delivery(_NS(
            file=dpath, root=tmp, authorization_id="user-msg:delivery",
            known_limitation=["synthetic fixture"], at="2026-07-04"))
        delivered = load(dpath)
        good = (
            denied == 1 and accepted == 0
            and delivered["delivery_status"] == "DELIVERED"
            and delivered["delivery_authorization_id"] == "user-msg:delivery"
            and delivered["known_limitations"] == ["synthetic fixture"]
            and validate(delivered)["verdict"] in ("PASS", "WARN")
        )
        ok &= good
        print(f"  [{'OK' if good else 'FAIL'}] delivery authorization is explicit "
              "and freshness-gated")
    finally:
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        os.rmdir(tmp)
        print(f"  [cleanup] removed {tmp} exists={os.path.exists(tmp)}")

    print("[selftest]", "ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="产物台账 passport.yaml 读写与校验")
    ap.add_argument("--selftest", action="store_true", help="离线合成样例自测")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="新建台账")
    p.add_argument("--project", required=True)
    p.add_argument("--pipeline", required=True)
    p.add_argument("--created", help="首次启动时间，默认当前分钟")
    p.add_argument("--dag-template", dest="dag_template",
                   help="本项目裁的链 id（可选，便于汇报）")
    p.add_argument("--out", default=".light/passport.yaml")
    p.add_argument("--force", action="store_true", help="允许覆盖已存在台账")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("append-stage", help="追加一条阶段记录")
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--stage", type=int, required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--round", type=int, help="回环阶段第几轮（m03⇄m04）")
    p.add_argument("--revision-rounds", type=int, dest="revision_rounds",
                   help="本阶段已用整体返修轮次（X-2，续跑勿重置）")
    p.add_argument("--depends-on", nargs="*", type=int, dest="depends_on",
                   help="DAG 依赖的上游 stage 序号（声明后按拓扑序校验，支持并行）")
    p.add_argument("--status", choices=sorted(VALID_STATUS),
                   help="显式 stage 状态（不给则 validate 时按 artifacts+gate 派生）")
    p.add_argument("--node-kind", dest="node_kind", choices=sorted(NODE_KINDS),
                   help="节点种类（默认 pipeline）")
    p.add_argument("--inputs-fingerprint", dest="inputs_fingerprint",
                   help="显式输入指纹；不给且加 --auto-fingerprint 则按上游产物自动算")
    p.add_argument("--auto-fingerprint", action="store_true",
                   help="按 depends_on 上游 artifacts 自动算 inputs_fingerprint")
    p.add_argument("--root", default=".", help="算指纹时的项目根（默认当前目录）")
    p.add_argument("--artifacts", nargs="*", help="产物路径，相对项目根")
    p.add_argument("--gate-type", choices=sorted(GATE_TYPES))
    p.add_argument("--gate-result", help="confirm 结果：PASS/FAIL/WARN/FAIL->PASS")
    p.add_argument("--gate-choice", help="decision 用户所选分支")
    p.add_argument("--gate-notes", help="闸门备注，FAIL->PASS 须写原因")
    p.add_argument("--gate-kv", nargs="*", help="额外 gate 字段 k=v")
    p.add_argument("--gaps", nargs="*", help="本阶段 GAP 留痕")
    p.set_defaults(func=cmd_append_stage)

    p = sub.add_parser("get-current-stage", help="读 current_stage 摘要")
    p.add_argument("--file", default=".light/passport.yaml")
    p.set_defaults(func=cmd_get_current_stage)

    p = sub.add_parser("add-back-edge",
                       help="在回炉目标阶段记一条回边并置 needs_rework（根因回炉落账）")
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--to", type=int, required=True, help="回炉目标=根因阶段序号")
    p.add_argument("--from", type=int, required=True, dest="from_stage",
                   help="触发源阶段序号（门 fail 处）")
    p.add_argument("--root-cause", required=True, dest="root_cause",
                   help="根因/类别（如 'claim 无证据'、'结果不支撑假设'）")
    p.add_argument("--evidence-ptr", dest="evidence_ptr",
                   help="证据指针（sha@ts 或 finding 定位）")
    p.add_argument("--round", type=int, help="本回边触发的返修轮次（默认已用+1）")
    p.add_argument("--by", default="user", help="回炉决策人（默认 user）")
    p.add_argument("--at", help="时间戳（默认当前分钟）")
    p.add_argument("--authorization-id", required=True,
                   help="用户明确回炉授权记录 ID/消息指针；缺失拒绝落账")
    p.set_defaults(func=cmd_add_back_edge)

    p = sub.add_parser("set-status", help="显式置某阶段 status")
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--stage", type=int, required=True)
    p.add_argument("--status", required=True, choices=sorted(VALID_STATUS))
    p.set_defaults(func=cmd_set_status)

    p = sub.add_parser("validate", help="全量 schema 校验")
    p.add_argument("--file", default=".light/passport.yaml")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("migrate", help="显式迁移 v1/v2 passport 到 v3（默认 dry-run）")
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--write", action="store_true",
                   help="真正写回；默认只预览，须先获得用户台账迁移授权")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser(
        "authorize-delivery",
        help="用户明确授权后，把已验证且 fresh 的 pipeline 标为最终交付",
    )
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--root", default=".", help="项目根，用于 freshness 检查")
    p.add_argument("--authorization-id", required=True,
                   help="用户最终交付授权消息/记录 ID")
    p.add_argument("--known-limitation", action="append", default=[],
                   help="随交付保留的已知限制；可重复")
    p.add_argument("--at", help="授权时间，默认当前分钟")
    p.set_defaults(func=cmd_authorize_delivery)

    p = sub.add_parser("fingerprint", help="计算一组 artifact 的输入指纹")
    p.add_argument("paths", nargs="*", help="artifact 路径")
    p.add_argument("--root", default=".", help="项目根（默认当前目录）")
    p.set_defaults(func=cmd_fingerprint)

    p = sub.add_parser("stale-check", help="逐阶段判定 fresh/stale，出最小重验范围")
    p.add_argument("--file", default=".light/passport.yaml")
    p.add_argument("--root", default=".", help="项目根（默认当前目录）")
    p.set_defaults(func=cmd_stale_check)

    args = ap.parse_args()
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.error("需要子命令（init/append-stage/add-back-edge/set-status/"
                 "get-current-stage/validate/migrate/authorize-delivery/"
                 "fingerprint/stale-check）或 --selftest")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
