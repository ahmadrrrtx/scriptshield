#!/usr/bin/env python3
"""Push a built kernel, wait for it, and download its outputs. Token never printed.

  python3 scripts/kaggle_run.py push  remote/_build/smoke
  python3 scripts/kaggle_run.py wait  ahmadrrrtx/scriptshield-fire-smoke --timeout 1500
  python3 scripts/kaggle_run.py fetch ahmadrrrtx/scriptshield-fire-smoke experiments/results/fire_smoke_v1
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kaggle_cli import run  # noqa: E402

TERMINAL = ("COMPLETE", "ERROR", "CANCEL")


def status(kernel: str) -> str:
    rc, out = run(["kernels", "status", kernel], timeout=120)
    return out.strip().splitlines()[-1] if out.strip() else f"rc={rc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push"); p.add_argument("build_dir")
    w = sub.add_parser("wait"); w.add_argument("kernel"); w.add_argument("--timeout", type=int, default=1500)
    w.add_argument("--interval", type=int, default=30)
    f = sub.add_parser("fetch"); f.add_argument("kernel"); f.add_argument("dest")
    a = ap.parse_args()
    if a.cmd == "push":
        rc, out = run(["kernels", "push", "-p", a.build_dir], timeout=600)
        print(out.strip()[-600:])
        return rc
    if a.cmd == "wait":
        t0, last = time.time(), ""
        while time.time() - t0 < a.timeout:
            cur = status(a.kernel)
            if cur != last:
                print(f"[{time.time() - t0:5.0f}s] {cur[-110:]}", flush=True)
                last = cur
            if any(t in cur for t in TERMINAL):
                return 0 if "COMPLETE" in cur else 1
            time.sleep(a.interval)
        print(f"still running after {a.timeout}s: {last[-110:]}")
        return 124
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    rc, out = run(["kernels", "output", a.kernel, "-p", str(dest)], timeout=900)
    print(out.strip()[-500:])
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(dest)}  {p.stat().st_size} bytes")
    return rc


if __name__ == "__main__":
    sys.exit(main())
