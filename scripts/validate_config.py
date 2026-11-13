#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.config import load_yaml, ModelSpec, SteeringSpec
errs = []
m = load_yaml(ROOT / "configs/models.yaml")
for key in ("primary", "comparator"):
    d = m[key]
    errs += ModelSpec(d["repo_id"], d["revision"], d["role"], d.get("dtype","bfloat16")).validate()
s = load_yaml(ROOT / "configs/steering.yaml")
errs += SteeringSpec(candidate_layers=[int(f*100) for f in s["candidate_layer_fracs"]],
                     alphas=s["alphas"], pool_method=s["pool_method"],
                     subspace_rank=s["subspace_rank"], norm_match=s["norm_match"],
                     seed=s["seed"], forms_in_pooled=tuple(s["forms_in_pooled"])).validate()
e = load_yaml(ROOT / "configs/evaluation.yaml")
assert e["unknown_is_never_safe"] is True, "unknown must never be treated as safe"
assert e["denominator_policy"] == "all_attempted_prompts"
if errs:
    print("CONFIG ERRORS:"); [print("  -", x) for x in errs]; raise SystemExit(1)
print("configs valid: models.yaml, steering.yaml, evaluation.yaml")
print("primary pooled forms:", s["forms_in_pooled"], "(cm/en correctly excluded)")
