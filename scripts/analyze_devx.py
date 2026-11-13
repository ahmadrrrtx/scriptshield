#!/usr/bin/env python3
"""EXPLORATORY: every vector over the development grid (run after the freeze; never used for selection).

Combines the pooled grid (dev v2) with the residualized / Roman-only / Urdu-only grid (devx).
Labels are the pre-registered ones (primary judge + repetition rule); an echo-corrected copy is
reported next to them. 24 harmful and 24 benign prompts per cell (12 development families).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.evaluation.analysis import label_rows  # noqa: E402

ARMS = ("pooled", "residualized", "ro_only", "ur_only")


def read(p):
    return [json.loads(l) for l in open(ROOT / p, encoding="utf-8") if l.strip()]


def table(rows):
    out = {}
    for r in rows:
        if r.get("set") != "dev_grid" or r["arm"] not in ARMS:
            continue
        c = out.setdefault((r["layer"], r["rho"]), {}).setdefault(r["arm"], {"harmful": [0, 0], "benign": [0, 0], "invalid": 0,
                                                                              "harmful_ro": [0, 0], "harmful_ur": [0, 0]})
        c[r["safety_label"]][0] += r["judge_label"] == "refusal"
        c[r["safety_label"]][1] += 1
        c["invalid"] += r["judge_label"] == "invalid"
        if r["safety_label"] == "harmful":
            c[f"harmful_{r['form']}"][0] += r["judge_label"] == "refusal"
            c[f"harmful_{r['form']}"][1] += 1
    return out


def summarise(tab):
    rows, dh, db = [], [], []
    for (layer, rho) in sorted(tab):
        cell = tab[(layer, rho)]
        if not all(a in cell for a in ARMS):
            raise ValueError(f"missing arm at layer {layer} rho {rho}: {sorted(cell)}")
        row = {"layer": layer, "rho": rho}
        for a in ARMS:
            c = cell[a]
            row[a] = {"harmful_refusal": c["harmful"][0] / c["harmful"][1], "benign_refusal": c["benign"][0] / c["benign"][1],
                      "harmful_refusal_ro": c["harmful_ro"][0] / c["harmful_ro"][1],
                      "harmful_refusal_ur": c["harmful_ur"][0] / c["harmful_ur"][1],
                      "n_harmful": c["harmful"][1], "n_benign": c["benign"][1],
                      "invalid_rate": c["invalid"] / (c["harmful"][1] + c["benign"][1])}
        dh.append(100 * (row["residualized"]["harmful_refusal"] - row["pooled"]["harmful_refusal"]))
        db.append(100 * (row["residualized"]["benign_refusal"] - row["pooled"]["benign_refusal"]))
        rows.append(row)
    return rows, {"n_configs": len(rows), "mean_harmful_diff_pp": float(np.mean(dh)), "min_harmful_diff_pp": float(min(dh)),
                  "max_harmful_diff_pp": float(max(dh)), "mean_benign_diff_pp": float(np.mean(db)),
                  "n_resid_better": int(sum(x > 1e-9 for x in dh)), "n_resid_worse": int(sum(x < -1e-9 for x in dh)),
                  "n_equal": int(sum(abs(x) <= 1e-9 for x in dh)),
                  "definition": "residualized minus pooled, percentage points, per (layer, rho)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pooled", default="experiments/results/judge_dev_v2/judge_dev/judged.jsonl")
    ap.add_argument("--others", default="experiments/results/judge_devx_v1/judge_devx/judged.jsonl")
    ap.add_argument("--out", default="experiments/results/devx_analysis")
    a = ap.parse_args()
    raw = read(a.pooled) + read(a.others)
    res = {"status": "EXPLORATORY: run after the freeze, never used for selection or for a hypothesis test",
           "labels": "pre_registered"}
    res["rows"], res["summary"] = summarise(table(label_rows(raw, "guard")))
    rows_e, sum_e = summarise(table(label_rows(raw, "guard", echo_invalid=True)))
    res["echo_corrected"] = {"rows": rows_e, "summary": sum_e}
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "devx_analysis.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    print(f"{'L':>3} {'rho':>4} | harmful refusal: pooled resid ro_only ur_only | benign refusal: pooled resid ro_only ur_only | invalid pooled resid")
    for r in res["rows"]:
        print(f"{r['layer']:>3} {r['rho']:>4} | " + " ".join(f"{r[x]['harmful_refusal']:>7.3f}" for x in ARMS) + "   | "
              + " ".join(f"{r[x]['benign_refusal']:>7.3f}" for x in ARMS)
              + f" | {r['pooled']['invalid_rate']:.3f} {r['residualized']['invalid_rate']:.3f}")
    print("summary (pre-registered labels):", json.dumps(res["summary"]))
    print("summary (echo-corrected):       ", json.dumps(sum_e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
