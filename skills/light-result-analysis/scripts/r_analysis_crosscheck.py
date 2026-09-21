#!/usr/bin/env python3
"""Locate Rscript honestly and run the base-R result cross-check."""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


HERE = pathlib.Path(__file__).resolve().parent
R_SCRIPT = HERE / "r_analysis_crosscheck.R"


def find_rscript() -> str | None:
    explicit = os.environ.get("RSCRIPT")
    if explicit and pathlib.Path(explicit).is_file():
        return explicit
    found = shutil.which("Rscript")
    if found:
        return found
    if os.name == "nt":
        root = pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "R"
        candidates = sorted(root.glob("R-*/bin/Rscript.exe"), reverse=True)
        if candidates:
            return str(candidates[0])
    return None


def run_crosscheck(input_path: str, group: str, metric: str, out: str,
                   paired_by: str | None = None) -> subprocess.CompletedProcess:
    rscript = find_rscript()
    if not rscript:
        raise RuntimeError(
            "Rscript not found in PATH, RSCRIPT, or Windows Program Files; R cross-check not run")
    cmd = [rscript, str(R_SCRIPT), "--input", input_path, "--group", group,
           "--metric", metric, "--out", out]
    if paired_by:
        cmd += ["--paired-by", paired_by]
    return subprocess.run(cmd, check=False, text=True, capture_output=True, encoding="utf-8")


def _selftest() -> int:
    rscript = find_rscript()
    if not rscript:
        print("[selftest] SKIP r_analysis_crosscheck: Rscript unavailable (honest degradation)")
        return 0
    direct = subprocess.run(
        [rscript, str(R_SCRIPT), "--selftest"],
        check=False, text=True, capture_output=True, encoding="utf-8")
    if direct.returncode:
        print(direct.stdout)
        print(direct.stderr, file=sys.stderr)
        return direct.returncode

    with tempfile.TemporaryDirectory() as td:
        inp = pathlib.Path(td) / "results.csv"
        out = pathlib.Path(td) / "r.csv"
        with inp.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["method", "seed", "score"])
            a_values = (.80, .82, .81, .83, .84, .85)
            differences = (.04, .05, .06, .045, .055, .05)
            for seed, value in enumerate(a_values, 1):
                writer.writerow(["a", seed, value])
            for seed, (value, diff) in enumerate(zip(a_values, differences), 1):
                writer.writerow(["b", seed, value - diff])
        proc = run_crosscheck(str(inp), "method", "score", str(out), "seed")
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)
            return proc.returncode
        with out.open(encoding="utf-8") as fh:
            row = next(csv.DictReader(fh))
        assert row["design"] == "paired" and int(row["n"]) == 6
        assert abs(float(row["mean_diff"]) - .05) < 1e-10
    print(f"[selftest] PASS r_analysis_crosscheck via {rscript}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a base-R two-group cross-check")
    ap.add_argument("--input")
    ap.add_argument("--group")
    ap.add_argument("--metric")
    ap.add_argument("--paired-by")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    required = (args.input, args.group, args.metric, args.out)
    if not all(required):
        ap.error("--input --group --metric --out are required")
    try:
        proc = run_crosscheck(args.input, args.group, args.metric, args.out, args.paired_by)
    except RuntimeError as exc:
        print(f"[R unavailable] {exc}", file=sys.stderr)
        return 2
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
