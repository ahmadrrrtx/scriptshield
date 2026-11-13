#!/usr/bin/env python3
"""Local analysis of judged generations. No GPU, no model.

  analyze.py dev  --judged J.jsonl --margins M.jsonl --out DIR [--freeze]
  analyze.py test --judged J.jsonl --margins M.jsonl --out DIR

--freeze writes configs/frozen_selection.json (commit it BEFORE building the test kernel).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.evaluation.analysis import (analyze_test, cell_table, label_rows,  # noqa: E402
                                              select_dev_config)
from scriptshield.evaluation.utility import load_utility  # noqa: E402


def read(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["dev", "test"])
    ap.add_argument("--judged", required=True)
    ap.add_argument("--margins", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--judge", default="guard", choices=["guard", "rubric"])
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--echo-corrected", action="store_true",
                    help="POST HOC sensitivity (protocol A18): a prompt echo is labelled invalid. "
                         "Never combined with --freeze; output files get the suffix _echo")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = read(a.judged)
    margins = read(a.margins)
    if a.echo_corrected and a.freeze:
        print("REFUSING: the frozen selection uses the pre-registered labels only")
        return 2
    rows = label_rows(raw, a.judge, echo_invalid=a.echo_corrected)
    suffix = "_echo" if a.echo_corrected else ""
    sha = hashlib.sha256(Path(a.judged).read_bytes()).hexdigest()
    print(f"{len(rows)} judged rows | judge={a.judge} | "
          f"{'POST HOC echo-corrected labels (A18)' if a.echo_corrected else 'pre-registered labels'} | labels: "
          + str({k: sum(r['judge_label'] == k for r in rows) for k in ('refusal', 'compliance', 'invalid', 'unknown')}))

    if a.stage == "dev":
        base = [r for r in rows if r["arm"] == "unsteered" and r.get("set") == "baseline"]
        res = {"judge": a.judge, "judged_sha256": sha, "n_rows": len(rows),
               "unsteered_calibration_plus_dev": cell_table(base),
               "unsteered_dev_only": cell_table([r for r in base if r["split"] == "dev"])}
        print("\nUNSTEERED (calibration + dev, 36 families) - descriptive, NOT the frozen test:")
        for k, v in res["unsteered_calibration_plus_dev"].items():
            print(f"  {k:<11} n={v['n']:>2} refusal={v['refusal_rate']:.3f} unsafe={v['unsafe_rate']:.3f} "
                  f"invalid={v['invalid_rate']:.3f} in_prompt_script={v['answered_in_prompt_script']:.2f} {v['response_scripts']}")
        grid_rows = [r for r in rows if r.get("set") == "dev_grid"] + [r for r in base if r["split"] == "dev"]
        sel = select_dev_config(grid_rows, margins, arm="pooled")
        res["selection"] = sel
        print(f"\nDEV GRID, pooled arm (unsteered dev: harmful refusal {sel['unsteered_dev']['harmful_refusal']:.3f}, "
              f"benign refusal {sel['unsteered_dev']['benign_refusal']:.3f}):")
        print(f"  {'L':>3} {'rho':>5} {'harm_ref':>8} {'gain_pp':>8} {'ben_ref':>8} {'over_pp':>8} {'invalid':>8} {'dMargin':>8}  eligible")
        for t in sel["table"]:
            print(f"  {t['layer']:>3} {t['rho']:>5} {t['harmful_refusal']:>8.3f} {t['harmful_gain_pp']:>+8.1f} "
                  f"{t['benign_refusal']:>8.3f} {t['over_refusal_increase_pp']:>+8.1f} {t['invalid_rate']:>8.3f} "
                  f"{t['margin_gain_harmful']:>+8.3f}  {t['eligible']}")
        # the residualized arm on the same grid: reported, NEVER used for selection
        other = {}
        for arm in sorted({r["arm"] for r in grid_rows} - {"unsteered", "pooled"}):
            other[arm] = select_dev_config(grid_rows, margins, arm=arm)["table"]
        res["other_arms_same_grid_not_used_for_selection"] = other
        print(f"\nSELECTED (rule A5, pooled arm): layer={sel['layer']} rho={sel['rho']} "
              f"within_budget={sel['within_budget']} improves_on_unsteered={sel['improves_on_unsteered']}")
        res["labels"] = "post_hoc_echo_corrected_A18" if a.echo_corrected else "pre_registered"
        (out / f"dev_analysis{suffix}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        if a.freeze:
            frozen = {"layer": sel["layer"], "rho": sel["rho"], "selected_on_arm": "pooled",
                      "within_budget": sel["within_budget"], "improves_on_unsteered": sel["improves_on_unsteered"],
                      "primary_judge": "Qwen/Qwen3Guard-Gen-4B@6ec42827da0c1ff11e7a49dc269d2e810d27e108",
                      "rule": "RESEARCH_PROTOCOL.md §14 A5", "dev_judged_sha256": sha,
                      "selected_row": sel["selected_row"], "unsteered_dev": sel["unsteered_dev"]}
            (ROOT / "configs/frozen_selection.json").write_text(json.dumps(frozen, indent=1) + "\n", encoding="utf-8")
            print("FROZEN -> configs/frozen_selection.json (commit before building the test kernel)")
        return 0

    util = load_utility(ROOT)
    answers = {u["id"]: u["answer"] for u in util}
    test_rows = [r for r in rows if r.get("set") == "test"]
    util_rows = [r for r in raw if r.get("set") == "utility"]
    res = analyze_test(test_rows, margins, util_rows, answers)
    res["judge"], res["judged_sha256"] = a.judge, sha
    res["labels"] = "post_hoc_echo_corrected_A18" if a.echo_corrected else "pre_registered"
    (out / f"test_analysis_{a.judge}{suffix}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nTEST: {res['n_test_families']} families, {res['n_test_rows']} rows")
    print(f"  {'arm':<16} {'ur_H':>6} {'ro_H':>6} {'worst':>6} {'gap':>6} {'overRef':>8} {'invalid':>8} {'utility':>8}")
    for arm, v in res["arms"].items():
        c = v["cells"]
        print(f"  {arm:<16} {c['ur/harmful']['refusal_rate']:>6.3f} {c['ro/harmful']['refusal_rate']:>6.3f} "
              f"{v['worst_form_harmful_refusal']:>6.3f} {v['script_gap']:>6.3f} {v['over_refusal']:>8.3f} "
              f"{v['invalid_rate']:>8.3f} {str(round(v['utility_accuracy'], 3)) if v['utility_accuracy'] is not None else 'n/a':>8}")
    h1 = res["H1_unsteered_script_gap"]
    print(f"\nH1 unsteered: refusal ur={h1['refusal_ur']:.3f} ro={h1['refusal_ro']:.3f} "
          f"diff={h1['difference_ro_minus_ur_pp']:+.1f}pp CI[{h1['bootstrap']['ci_low']*100:+.1f},{h1['bootstrap']['ci_high']*100:+.1f}] "
          f"McNemar p={h1['mcnemar']['p_value']:.4g} | unsafe ur={h1['unsafe_response_ur']:.3f} ro={h1['unsafe_response_ro']:.3f}")
    if "H3_residualized_vs_pooled" in res:
        h3 = res["H3_residualized_vs_pooled"]
        print(f"H3 residualized vs pooled: worst-form gain {h3['worst_form_gain_bootstrap']['estimate']:+.1f}pp "
              f"CI[{h3['worst_form_gain_bootstrap']['ci_low']:+.1f},{h3['worst_form_gain_bootstrap']['ci_high']:+.1f}] | "
              f"gap reduction {h3['gap_reduction_bootstrap']['estimate']:+.1f}pp "
              f"CI[{h3['gap_reduction_bootstrap']['ci_low']:+.1f},{h3['gap_reduction_bootstrap']['ci_high']:+.1f}] | "
              f"identical outcomes {h3['identical_outcomes']}/{h3['n_paired_outcomes']}")
        print("   gate passed:", h3["gate"]["passed"], "|", "; ".join(h3["gate"]["reasons"]) or "all criteria met")
        print("   ->", h3["interpretation"])
        if "H3_continuous_margin" in res:
            cm = res["H3_continuous_margin"]
            print(f"   continuous margin: mean {cm['sign_flip']['mean']:+.4f} p={cm['sign_flip']['p_two_sided']:.4g} "
                  f"CI[{cm['bootstrap']['ci_low']:+.4f},{cm['bootstrap']['ci_high']:+.4f}]")
        print("   Holm:", dict(zip(res["holm"]["tests"], [round(x, 4) for x in res["holm"]["adjusted_p"]])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
