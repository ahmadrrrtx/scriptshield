#!/usr/bin/env python3
"""Write a redacted environment report. No credentials are read or printed."""
from __future__ import annotations
import importlib.metadata as md, json, os, platform, shutil, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def ver(p):
    try: return md.version(p)
    except md.PackageNotFoundError: return None

def sh(c):
    try: return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: return None

rep = {
    "python": sys.version.split()[0], "platform": platform.platform(),
    "cpu_count": os.cpu_count(),
    "disk_free_gb": round(shutil.disk_usage("/").free/1e9, 2),
    "meminfo_mb": sh("free -m | awk '/Mem:/{print $2\" total, \"$7\" available\"}'"),
    "git": sh("git --version"),
    "gpu": sh("nvidia-smi --query-gpu=name --format=csv,noheader") or "none",
    "packages": {p: ver(p) for p in
                 ["numpy","scipy","pandas","pyyaml","jsonschema","pytest","requests",
                  "curatorkit","auditkit","safetune","torch","transformers","kaggle"]},
    "credentials_present_not_shown": {
        "hf_read": (Path.home() / ".cache/scriptshield-secrets/hf_read.token").exists(),
        "kaggle": (Path.home() / ".cache/scriptshield-secrets/kaggle_api.token").exists(),
    },
    "spend_usd_authorized": 0.0, "spend_usd_to_date": 0.0,
}
out = ROOT / "experiments/manifests/environment.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
print(json.dumps(rep, indent=2))
print(f"\nwrote {out.relative_to(ROOT)}")
