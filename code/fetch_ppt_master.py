#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_ppt_master.py - 按需下载 ppt-master（54k★，MIT），解包到 build/。

为什么按需下载
--------------
ppt-master 解包后约 150 MB，远超仓库体积上限，所以**不入库**；只在真正要用它的
原生导出通路（`code/make_ppt_svg.py`）时下载一次，放在 gitignore 的 build/ 下。

用法
----
    python code/fetch_ppt_master.py              # 下载 main 分支 tarball 并解包
    python code/fetch_ppt_master.py --ref v6.4.0 # 指定 tag / 分支
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "build" / "ppt-master"
URL = "https://codeload.github.com/hugohe3/ppt-master/tar.gz/refs/heads/{ref}"
URL_TAG = "https://codeload.github.com/hugohe3/ppt-master/tar.gz/refs/tags/{ref}"


def download(ref: str) -> bytes:
    for url in (URL.format(ref=ref), URL_TAG.format(ref=ref)):
        try:
            print(f"GET {url}")
            with urllib.request.urlopen(url, timeout=180) as r:
                data = r.read()
            print(f"  {len(data) / 1e6:.1f} MB")
            return data
        except Exception as e:                        # noqa: BLE001
            print(f"  failed: {e}")
    raise SystemExit("下载失败：网络不可达或 ref 不存在")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="main")
    a = ap.parse_args(argv)
    data = download(a.ref)
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        members = [m for m in tf.getmembers()
                   if "/skills/ppt-master/" in m.name or m.isdir()]
        tf.extractall(DEST, members=members)
    inner = next(p for p in DEST.iterdir() if p.is_dir() and p.name.startswith("ppt-master"))
    for name in ("skills", "requirements.txt", "LICENSE", "README.md"):
        src = inner / name
        if src.exists():
            shutil.move(str(src), str(DEST / name))
    shutil.rmtree(inner, ignore_errors=True)
    skill = DEST / "skills" / "ppt-master"
    print(f"skill 目录：{skill}")
    print(f"导出入库脚本：{skill / 'scripts' / 'svg_to_pptx.py'}")
    print("接着运行：python code/make_ppt_svg.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
