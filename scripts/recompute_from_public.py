#!/usr/bin/env python3
"""Recompute the pre-registered test analysis from the PUBLIC evaluation logs and compare it,
number for number, with the published analysis file. No GPU, no model, no private data.

The public log replaces some response texts by "[withheld]" but keeps every label, verdict and
the sha256 of every text. That is all the analysis needs: it uses labels, and compares texts
only for identity.

  python scripts/recompute_from_public.py --download            # fetch the logs from the Hub
  python scripts/recompute_from_public.py --logs path/to/eval_logs

Exit code 0 = every number of the published analysis was reproduced.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.evaluation.analysis import analyze_test  # noqa: E402
from scriptshield.evaluation.utility import load_utility  # noqa: E402

WRAPPER_KEYS = ("judge", "judged_sha256", "labels")       # added by scripts/analyze.py around the analysis


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def differences(a, b, path: str = "") -> list[str]:
    """Paths at which two JSON values differ (floats compared to 1e-12)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in the {'published' if k in b else 'recomputed'} analysis")
            else:
                out += differences(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in differences(x, y, f"{path}[{i}]")]
    if isinstance(a, bool) or isinstance(b, bool):                 # a flag never equals a number
        same = isinstance(a, bool) and isinstance(b, bool) and a == b
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        same = abs(a - b) <= 1e-12
    else:
        same = a == b
    return [] if same else [f"{path}: {str(a)[:60]} != {str(b)[:60]}"]


def recompute(public_rows: list[dict], margins: list[dict], answers: dict) -> dict:
    """The analysis of scripts/analyze.py, fed with public rows. A text is represented by its hash."""
    test_rows = [{**r, "output": r["output_sha256"]} for r in public_rows if r.get("set") == "test"]
    utility_rows = [r for r in public_rows if r.get("set") == "utility"]
    if any(r.get("withheld") for r in utility_rows):
        raise ValueError("a utility answer is withheld; utility cannot be recomputed")
    return analyze_test(test_rows, margins, utility_rows, answers)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--logs", default=None, help="folder holding test_judged_public.jsonl and test_margins.jsonl")
    ap.add_argument("--download", action="store_true", help="fetch eval_logs/ from the public dataset on the Hub")
    ap.add_argument("--published", default="experiments/results/test_analysis/test_analysis_guard.json")
    a = ap.parse_args()
    if a.download:
        from huggingface_hub import snapshot_download
        repo = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))["hf_dataset"]["repo_id"]
        logs = Path(snapshot_download(repo, repo_type="dataset", allow_patterns=["eval_logs/test_*.jsonl"])) / "eval_logs"
        print(f"downloaded the public logs of {repo}")
    elif a.logs:
        logs = Path(a.logs)
    else:
        ap.error("give --logs DIR or --download")
    public_rows = read_jsonl(logs / "test_judged_public.jsonl")
    margins = read_jsonl(logs / "test_margins.jsonl")
    answers = {u["id"]: u["answer"] for u in load_utility(ROOT)}
    res = recompute(public_rows, margins, answers)
    published = json.loads((ROOT / a.published).read_text(encoding="utf-8"))
    diff = differences(res, {k: v for k, v in published.items() if k not in WRAPPER_KEYS})

    withheld = sum(bool(r.get("withheld")) for r in public_rows)
    h1 = res["H1_unsteered_script_gap"]
    h3 = res["H3_residualized_vs_pooled"]
    print(f"{len(public_rows)} public rows ({withheld} with the response text withheld), {res['n_test_families']} test families")
    print(f"H1  unsteered refusal of harmful requests: Urdu script {100 * h1['refusal_ur']:.1f} %, "
          f"Roman Urdu {100 * h1['refusal_ro']:.1f} % ({h1['difference_ro_minus_ur_pp']:+.1f} pp, "
          f"exact McNemar p = {h1['mcnemar']['p_value']:.2g})")
    print(f"H3  residualized vs pooled: gate {'PASSED' if h3['gate']['passed'] else 'NOT MET'}; "
          f"same outcome on {h3['identical_outcomes']} of {h3['n_paired_outcomes']} harmful prompts")
    for arm, v in res["arms"].items():
        c = v["cells"]
        print(f"    {arm:<16} harmful ur {c['ur/harmful']['refusal_rate']:.3f}  ro {c['ro/harmful']['refusal_rate']:.3f}"
              f"  benign refusal {v['over_refusal']:.3f}  invalid {v['invalid_rate']:.3f}")
    if diff:
        print(f"\nDIFFERENT from {a.published} in {len(diff)} places:")
        for d in diff[:20]:
            print("  " + d)
        return 1
    print(f"\nIDENTICAL to {a.published}: every number of the pre-registered analysis was reproduced from the public logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
