#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""get_cjk_font.py - extract a Simplified-Chinese CJK font so matplotlib / the
preview renderer can draw Chinese text.

The font comes from the PyPI package ``noto-cjk-sans-otc`` (NotoSansCJK-Regular.ttc).
A .ttc is a collection; matplotlib cannot use it directly, so we pull the SC
(Simplified Chinese) member out and save it as a standalone .otf.

The font file is *not* stored in the repository - it is rebuilt on demand:

    pip install --break-system-packages noto-cjk-sans-otc fonttools
    python code/get_cjk_font.py

prints the path of the extracted font.
"""

from __future__ import annotations

import argparse
import glob
import os
import site
import sys
from pathlib import Path

DEFAULT_OUT = "/tmp/fonts/NotoSansCJKsc-Regular.otf"


def find_ttc() -> Path | None:
    paths = []
    for p in site.getsitepackages() + [site.getusersitepackages()]:
        paths += glob.glob(os.path.join(p, "**", "*.ttc"), recursive=True)
    for p in sorted(set(paths)):
        if "CJK" in os.path.basename(p):
            return Path(p)
    return None


def extract(out_path: Path, which: str = "SC") -> Path:
    from fontTools.ttLib import TTCollection

    ttc = find_ttc()
    if ttc is None:
        raise SystemExit("NotoSansCJK-Regular.ttc not found - "
                         "run: pip install --break-system-packages noto-cjk-sans-otc")

    coll = TTCollection(str(ttc))
    chosen = None
    names = []
    for f in coll.fonts:
        ps = f["name"].getDebugName(6) or ""          # PostScript name
        fam = f["name"].getDebugName(1) or ""
        names.append(f"{ps} / {fam}")
        import re as _re
        if _re.search(f"[Cc][Jj][Kk]{which}-", ps) or _re.search(f"Sans CJK {which}$", fam):
            chosen = f
            break
    if chosen is None:
        print("available faces:")
        for n in names:
            print("   ", n)
        raise SystemExit(f"no face matching {which!r} in {ttc}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    chosen.save(str(out_path))
    print(f"{chosen['name'].getDebugName(4)}  ->  {out_path} "
          f"({os.path.getsize(out_path) / 1e6:.1f} MB)")
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--which", default="SC", help="SC / TC / JP / KR")
    args = ap.parse_args(argv)
    p = extract(Path(args.out), args.which)
    print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
