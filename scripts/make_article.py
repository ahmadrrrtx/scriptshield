#!/usr/bin/env python3
"""Render docs/hf_article.md from docs/hf_article.template.md. No number is typed by hand."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


def pct(x, d=1):
    return f"{100 * x:.{d}f} %"


def section(md: str, start: str) -> str:
    out, on = [], False
    for ln in md.splitlines():
        if ln.startswith(start):
            on = True
            continue
        if on and ln.startswith("## "):
            break
        if on:
            out.append(ln)
    return "\n".join(out).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default=None, help="byline; default: name and Hugging Face handle from configs/public_links.json")
    ap.add_argument("--verify-report", default="experiments/results/verify_release_v1/verify_release/verify_report.json")
    ap.add_argument("--out", default="docs/hf_article.md")
    a = ap.parse_args()
    t = load("experiments/results/test_analysis/test_analysis_guard.json")
    rub = load("experiments/results/test_analysis/test_analysis_rubric.json")
    echo = load("experiments/results/test_analysis/test_analysis_guard_echo.json")
    adj = load("experiments/adjudication/test_ro_adjudication.json")
    devx = load("experiments/results/devx_analysis/devx_analysis.json")
    D = load("experiments/results/fire_dev_v2/fire_dev/run_report.json")["sections"]["mechanism_diagnostics"]["by_layer"]
    frozen = load("configs/frozen_selection.json")
    man = load("data/manifests/scriptshield_0.2.0.json")
    results = (ROOT / "docs/RESULTS.md").read_text(encoding="utf-8")
    import yaml
    rev = yaml.safe_load((ROOT / "configs/models.yaml").read_text(encoding="utf-8"))["primary"]["revision"]

    links = load("configs/public_links.json")
    ur_read = load("experiments/results/test_analysis/utility_reading.json")
    author = a.author or f"{links['author']['name']} (@{links['author']['hf']})"

    h1, h3 = t["H1_unsteered_script_gap"], t["H3_residualized_vs_pooled"]
    u = adj["arms"]["unsteered"]["harmful"]
    j1 = adj["judge_vs_adjudication"]["guard_pre_registered"]
    ro = {"pre": h1["refusal_ro"], "rubric": rub["H1_unsteered_script_gap"]["refusal_ro"],
          "echo": echo["H1_unsteered_script_gap"]["refusal_ro"], "reading": u["R"] / u["n"]}
    if not all(v <= ro["pre"] for v in ro.values()):
        print("REFUSING: the template says every correction widens the gap, which is no longer true:", ro)
        return 2
    if h3["gate"]["passed"]:
        print("REFUSING: the template describes a gate that was not met")
        return 2
    L = str(frozen["layer"])
    grid = [k for k in ("10", "14", "18", "22") if k in D]
    vp = ROOT / a.verify_report
    if vp.exists():
        v = json.loads(vp.read_text(encoding="utf-8"))
        arms = v["verify"]["arms"]
        if not v.get("passed"):
            print("REFUSING: the release verification did not pass")
            return 2
        verify_line = (f"In a fresh GPU session the released package alone (vectors, manifest and loader, with none of "
                       f"this project's code importable) reproduced {sum(x['identical'] for x in arms.values())} of "
                       f"{sum(x['n'] for x in arms.values())} logged responses byte for byte.")
    else:
        verify_line = "Verification of the released package in a clean environment has not been run yet."
    n_tests = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip().splitlines()[-1].split()[0]
    cells = t["arms"]["unsteered"]["cells"]

    # before / after table: unsteered vs the two steered arms the gate compares, plus the control
    cols = [c for c in ("unsteered", "pooled", "residualized", "orthogonal_null") if c in t["arms"]]
    head = {"unsteered": "Before (unsteered)", "pooled": "After: pooled vector", "residualized": "After: residualized vector",
            "orthogonal_null": "Control vector"}

    def row(name, fn):
        return f"| {name} | " + " | ".join(fn(c) for c in cols) + " |"

    def frac_of(d, k):
        return f"{d[k]} of {d['n']}"
    ba = ["| Metric | " + " | ".join(head[c] for c in cols) + " |", "|---|" + "---:|" * len(cols),
          row("Harmful requests refused, Urdu script (judge)", lambda c: pct(t["arms"][c]["cells"]["ur/harmful"]["refusal_rate"])),
          row("Harmful requests refused, Roman Urdu (judge)", lambda c: pct(t["arms"][c]["cells"]["ro/harmful"]["refusal_rate"])),
          row("Roman-Urdu responses flagged unsafe (judge)", lambda c: pct(t["arms"][c]["cells"]["ro/harmful"]["unsafe_rate"])),
          row("Benign requests judged refused (lower is better)", lambda c: pct(t["arms"][c]["over_refusal"])),
          row("Invalid output (empty or looping)", lambda c: pct(t["arms"][c]["invalid_rate"])),
          row("Utility, 48 factual questions (pattern score)",
              lambda c: pct(t["arms"][c]["utility_accuracy"]) if t["arms"][c]["utility_accuracy"] is not None else "not measured"),
          row("Utility on reading (post hoc)",
              lambda c: f"{ur_read['arms'][c]['reading']['all']} of {ur_read['arms'][c]['n']}" if c in ur_read["arms"] else "not measured"),
          row("Real refusals, Roman Urdu, on reading (post hoc)", lambda c: frac_of(adj["arms"][c]["harmful"], "R")),
          row("Answers toward the harmful request, Roman Urdu, on reading (post hoc)", lambda c: frac_of(adj["arms"][c]["harmful"], "A"))]
    before_after = "\n".join(ba)
    rep = {
        "URL_GITHUB": links["github_repo"], "URL_MODEL": links["hf_model"]["url"], "URL_DATASET": links["hf_dataset"]["url"],
        "URL_SPACE": links["hf_space"]["url"], "URL_COLLECTION_MODELS": links["hf_collection_models"]["url"],
        "URL_COLLECTION_DATA": links["hf_collection_data"]["url"],
        "TITLE_COLLECTION_MODELS": links["hf_collection_models"]["title"],
        "TITLE_COLLECTION_DATA": links["hf_collection_data"]["title"],
        "ID_MODEL": links["hf_model"]["repo_id"], "ID_DATASET": links["hf_dataset"]["repo_id"],
        "ID_SPACE": links["hf_space"]["repo_id"], "BEFORE_AFTER_TABLE": before_after,
        "AUTHOR": author, "H1_N": str(h1["n_families"]), "H1_UR": pct(h1["refusal_ur"]), "H1_RO": pct(h1["refusal_ro"]),
        "H1_DIFF": f"{h1['difference_ro_minus_ur_pp']:+.1f}",
        "H1_CI": f"{100 * h1['bootstrap']['ci_low']:+.1f} to {100 * h1['bootstrap']['ci_high']:+.1f}",
        "H1_P": f"{h1['mcnemar']['p_value']:.2g}", "CM_RATE": pct(cells["cm/harmful"]["refusal_rate"]),
        "EN_RATE": pct(cells["en/harmful"]["refusal_rate"]),
        "H3_SAME": str(h3["identical_outcomes"]), "H3_N": str(h3["n_paired_outcomes"]),
        "JUDGE_PREC": pct(j1["precision"], 0),
        "DATA_VERSION": man["dataset_version"], "DATA_N": str(man["n_records"]), "DATA_FAMILIES": str(man["n_families"]),
        "LAYER": L, "RHO": str(frozen["rho"]),
        "NORM_RATIO": f"{D[L]['norm_ratio_ro_over_ur']['value']:.2f}",
        "NORM_CI": f"{D[L]['norm_ratio_ro_over_ur']['ci95'][0]:.2f} to {D[L]['norm_ratio_ro_over_ur']['ci95'][1]:.2f}",
        "ALIGN_MAX": f"{max(abs(D[k]['h2_script_alignment']['cross_fitted_cosine']) for k in grid):.3f}",
        "REMOVED_MAX": pct(max(D[k]["h2_script_alignment"]["removed_norm_fraction_if_residualized"] for k in grid)),
        "RESULTS_H1": section(results, "## 1. "), "RESULTS_ARMS": section(results, "## 2. "),
        "RESULTS_H3": section(results, "## 3. "),
        # the report numbers its sub-sections 5.1-5.3; inside the article they sit under 7.5
        "RESULTS_VALIDITY": re.sub(r"(?m)^### 5\.\d+ ", "#### ", section(results, "## 5. ")),
        "DEVX_BETTER": str(devx["summary"]["n_resid_better"]), "DEVX_WORSE": str(devx["summary"]["n_resid_worse"]),
        "DEVX_EQUAL": str(devx["summary"]["n_equal"]),
        "VERIFY_LINE": verify_line, "ADJ_TOTAL": str(u["n"]), "ADJ_R": str(u["R"]), "ADJ_A": str(u["A"]), "ADJ_N": str(u["N"]),
        "UTIL_UR": pct(t["utility"]["unsteered"]["by_form"]["ur"]), "UTIL_RO": pct(t["utility"]["unsteered"]["by_form"]["ro"]),
        "N_TESTS": n_tests, "REVISION_SHORT": rev[:8],
    }
    text = (ROOT / "docs/hf_article.template.md").read_text(encoding="utf-8")
    for k, v in rep.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        print("REFUSING: unfilled placeholders:", sorted(set(left)))
        return 2
    (ROOT / a.out).write_text(text, encoding="utf-8")
    print(f"wrote {a.out}: {len(text.split())} words, {n_tests} tests collected, verification: {'included' if vp.exists() else 'pending'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
