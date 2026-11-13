#!/usr/bin/env python3
"""Validate the pilot corpus (schema + research integrity)."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import load_records, validate_corpus
from scriptshield.config import load_yaml
p = ROOT / load_yaml(ROOT / "configs/data.yaml")["corpus"]
if not p.exists():
    print(f"missing {p}; run scripts/build_pilot_dataset.py first"); raise SystemExit(2)
rep = validate_corpus(load_records(p))
print(rep.summary())
raise SystemExit(0 if rep.ok else 1)
