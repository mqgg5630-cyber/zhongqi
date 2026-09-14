#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_nature_skills.py - 按需下载 nature-skills（Apache-2.0）到 build/。

用途
----
[mqgg5630-cyber/nature-skills](https://github.com/mqgg5630-cyber/nature-skills) 里的
`skills/nature-paper2ppt` 是本项目 H 版 PPT 的方法来源（叙事弧、版式规则、自检脚本）。
仓库本体（约 78 MB）**不入库**，只在需要跑它的质量审计脚本时下载一次。

用法
----
    python code/fetch_nature_skills.py          # 下载到 build/nature-skills/
    python code/fetch_nature_skills.py --ref main
"""

from __future__ import annotations

import argparse
import io
import shutil
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "build" / "nature-skills"
URL = "https://codeload.github.com/mqgg5630-cyber/nature-skills/tar.gz/refs/heads/{ref}"

KEEP = ("skills/", "LICENSE", "README.md")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main")
    a = ap.parse_args(argv)
    url = URL.format(ref=a.ref)
    print(f"GET {url}")
    with urllib.request.urlopen(url, timeout=180) as r:
        data = r.read()
    print(f"  {len(data) / 1e6:.1f} MB")
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for m in tf.getmembers():
            parts = m.name.split("/", 1)
            if len(parts) < 2:
                continue
            rel = parts[1]
            if rel.startswith(KEEP):
                tf.extract(m, DEST)
    inner = next(p for p in DEST.iterdir() if p.is_dir())
    for name in ("skills", "LICENSE", "README.md"):
        src = inner / name
        if src.exists():
            shutil.move(str(src), str(DEST / name))
    shutil.rmtree(inner, ignore_errors=True)
    audit = DEST / "skills" / "nature-paper2ppt" / "scripts" / "audit_pptx_quality.py"
    print(f"audit script: {audit}  ({'ok' if audit.exists() else 'MISSING'})")
    print("接着运行：python code/make_ppt_nature.py --audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
