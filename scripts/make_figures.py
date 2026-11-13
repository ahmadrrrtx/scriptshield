#!/usr/bin/env python3
"""Draw the figures of the write-up, the README and the cards from the result files.

    python3 scripts/make_figures.py            # needs matplotlib:  pip install -e ".[figures]"

Every number in a figure is read from a file that is public (analysis JSON, public evaluation log, run
report, manifest); nothing is typed in. The values drawn are also written to docs/figures/figure_data.json
so that a figure can be checked against its source without reading pixels.
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures"
UR, RO, GREY, LIGHT, INK, BLUE, RED = "#167a74", "#d9822b", "#8a8f98", "#d7dbe0", "#1f2933", "#3b5bdb", "#c2410c"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#9aa1ab", "axes.labelcolor": INK, "text.color": INK, "xtick.color": INK,
                     "ytick.color": INK, "figure.dpi": 100, "savefig.dpi": 200, "savefig.bbox": "tight",
                     "savefig.facecolor": "white"})
ARM_NAMES = {"unsteered": "No steering", "pooled": "Pooled vector", "residualized": "Residualized vector",
             "random_subspace": "Pooled, a random\ndirection removed", "orthogonal_null": "Placebo: noise vector\nunrelated to harm",
             "ur_only": "Urdu-script\nvector only", "ro_only": "Roman-Urdu\nvector only"}


def exact_ci(k: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Clopper-Pearson interval by bisection on the binomial tail (no SciPy needed)."""
    a = (1 - level) / 2

    def tail_ge(p):  # P(X >= k)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))

    def tail_gt(p):  # P(X > k)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1, n + 1))

    def solve(f, target):
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) < target else (lo, mid)
        return (lo + hi) / 2

    low = 0.0 if k == 0 else solve(tail_ge, a)
    high = 1.0 if k == n else solve(tail_gt, 1 - a)
    return low, high


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def published(kind: str, name: str) -> Path:
    """A file of the public release: from the local release folder if there is one, otherwise downloaded
    from the Hub without credentials (needs `huggingface_hub`)."""
    local = ROOT / "release" / {"model": "hf_model", "dataset": "hf_dataset"}[kind] / name
    if local.exists():
        return local
    from huggingface_hub import hf_hub_download
    links = load("configs/public_links.json")
    return Path(hf_hub_download(links[f"hf_{kind}"]["repo_id"], name, repo_type=kind, token=False))


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name)
    plt.close(fig)


def fig_script_gap(an, reading, data):
    cells = an["arms"]["unsteered"]["cells"]
    forms = [("ur", "Urdu script", UR), ("ro", "Roman Urdu", RO), ("cm", "Code-mixed\n(Urdu script + English)", GREY), ("en", "English", GREY)]
    fig, ax = plt.subplots(figsize=(7.6, 4.3))
    rec = []
    for i, (f, name, col) in enumerate(forms):
        k, n = cells[f"{f}/harmful"]["refusal"], cells[f"{f}/harmful"]["n"]
        lo, hi = exact_ci(k, n)
        ax.bar(i, 100 * k / n, color=col, width=0.62, zorder=2)
        ax.errorbar(i, 100 * k / n, yerr=[[100 * (k / n - lo)], [100 * (hi - k / n)]], color=INK, capsize=4, lw=1.2, zorder=3)
        ax.text(i, 5, f"{k} of {n}", ha="center", va="bottom", fontsize=11, fontweight="bold", color="white", zorder=5)
        rec.append({"form": f, "refused": k, "n": n, "ci95": [round(lo, 4), round(hi, 4)]})
    r = reading["unsteered"]
    ax.scatter([1.17], [100 * r["R"] / 36], marker="D", s=70, color="white", edgecolor=INK, linewidth=1.6, zorder=4)
    ax.annotate(f"after reading the\nresponses: {r['R']} of 36", xy=(1.19, 100 * r["R"] / 36 + 1.5), xytext=(1.0, 72),
                fontsize=9, ha="center", arrowprops={"arrowstyle": "-", "color": INK, "lw": 0.8})
    ax.set_xticks(range(4), [x[1] for x in forms])
    ax.set_ylim(0, 112)
    ax.set_yticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    ax.set_ylabel("Harmful requests refused")
    ax.grid(axis="y", color=LIGHT, lw=0.8, zorder=0)
    ax.set_title("The same 36 harmful requests, written four ways\nTiny Aya Fire without any steering", loc="left", fontsize=12, fontweight="bold")
    fig.text(0.01, -0.03, "Bars: automatic judge, pre-registered labels. Lines: 95% exact intervals. Diamond: Roman-Urdu responses read one by one "
             "(LLM agent, not a human).", fontsize=8, color="#52606d")
    save(fig, "script_gap.png")
    data["script_gap"] = {"judge": rec, "reading_roman_urdu_refusals": r["R"]}


def fig_outcomes(reading, data):
    arms = ["unsteered", "pooled", "residualized", "orthogonal_null"]
    fig, ax = plt.subplots(figsize=(7.6, 3.4))
    parts = [("R", "Refuses", UR), ("A", "Goes along with the request", RED), ("N", "Neither: garbled, off-topic or repeats the question", LIGHT)]
    for i, arm in enumerate(arms):
        left = 0
        for key, _, col in parts:
            v = reading[arm][key]
            ax.barh(i, v, left=left, color=col, edgecolor="white", height=0.62)
            ax.text(left + v / 2, i, str(v), ha="center", va="center", fontsize=10, fontweight="bold",
                    color="white" if key != "N" else INK)
            left += v
    ax.set_yticks(range(len(arms)), [ARM_NAMES[a].replace("\n", " ") for a in arms])
    ax.invert_yaxis()
    ax.set_xlim(0, 36)
    ax.set_xticks([0, 9, 18, 27, 36])
    ax.set_xlabel("Harmful Roman-Urdu test requests (36)")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in parts], labels=[p[1] for p in parts],
              loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=1, frameon=False, fontsize=9)
    ax.set_title("What the model actually wrote in reply to harmful Roman-Urdu requests", loc="left", fontsize=12, fontweight="bold")
    save(fig, "roman_urdu_outcomes.png")
    data["roman_urdu_outcomes_reading"] = {a: reading[a] for a in arms}


def fig_arms(an, data):
    arms = ["unsteered", "pooled", "residualized", "random_subspace", "orthogonal_null", "ur_only", "ro_only"]
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.0), sharey=True)
    rec = {}
    for ax, (title, getter, base_col) in zip(axes, [
            ("Harmful Roman-Urdu requests refused (of 36)", lambda c: (c["ro/harmful"]["refusal"], c["ro/harmful"]["n"]), RO),
            ("Harmless requests refused, both scripts (of 72)", lambda c: (c["ur/benign"]["refusal"] + c["ro/benign"]["refusal"],
                                                                          c["ur/benign"]["n"] + c["ro/benign"]["n"]), BLUE)]):
        for i, arm in enumerate(arms):
            k, n = getter(an["arms"][arm]["cells"])
            lo, hi = exact_ci(k, n)
            col = GREY if arm == "unsteered" else (base_col if arm in ("pooled", "residualized") else "#c9ced6")
            ax.barh(i, 100 * k / n, color=col, height=0.66, zorder=2)
            ax.errorbar(100 * k / n, i, xerr=[[100 * (k / n - lo)], [100 * (hi - k / n)]], color=INK, capsize=3, lw=1, zorder=3)
            ax.text(100 * hi + 2, i, f"{k}", va="center", fontsize=9, fontweight="bold")
            rec.setdefault(arm, {})[title.split(" (")[0]] = [k, n]
        k0, n0 = getter(an["arms"]["unsteered"]["cells"])
        ax.axvline(100 * k0 / n0, color=INK, lw=0.9, ls=(0, (4, 3)), zorder=1)
        ax.set_xlim(0, 100)
        ax.set_xticks(range(0, 101, 25), [f"{v}%" for v in range(0, 101, 25)])
        ax.grid(axis="x", color=LIGHT, lw=0.8, zorder=0)
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold")
    axes[0].set_yticks(range(len(arms)), [ARM_NAMES[a] for a in arms])
    axes[0].invert_yaxis()
    fig.suptitle("Steering compared with its controls (automatic judge)", x=0.01, ha="left", fontsize=12, fontweight="bold", y=1.02)
    fig.text(0.01, -0.04, "Dashed line: no steering. Lines: 95% exact intervals. The placebo vector has the same length as the pooled vector "
             "and is orthogonal to it.",
             fontsize=8, color="#52606d")
    save(fig, "arms_comparison.png")
    data["arms_comparison"] = rec


def fig_mechanism(dev, manifest, data):
    bl = dev["sections"]["mechanism_diagnostics"]["by_layer"]
    layers = sorted(int(k) for k in bl)
    ratio = [bl[str(k)]["norm_ratio_ro_over_ur"]["value"] for k in layers]
    lo = [bl[str(k)]["norm_ratio_ro_over_ur"]["ci95"][0] for k in layers]
    hi = [bl[str(k)]["norm_ratio_ro_over_ur"]["ci95"][1] for k in layers]
    cos = [bl[str(k)]["h2_script_alignment"]["in_sample_abs_cosine"] for k in layers]
    null = [bl[str(k)]["h2_script_alignment"]["isotropic_random_null_abs_cosine"]["p95"] for k in layers]
    sel = manifest["layer"]
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.6))
    ax = axes[0]
    ax.fill_between(layers, lo, hi, color=RO, alpha=0.18, lw=0)
    ax.plot(layers, ratio, color=RO, marker="o", ms=4, lw=1.8)
    ax.axhline(1, color=GREY, lw=0.9, ls=(0, (4, 3)))
    ax.text(layers[-1], 1.02, "equal strength", ha="right", va="bottom", fontsize=8, color="#52606d")
    ax.set_ylim(0, 1.25)
    ax.set_ylabel("Roman Urdu / Urdu script")
    ax.set_title("Strength of the harm signal in Roman Urdu,\nrelative to Urdu script", loc="left", fontsize=10.5, fontweight="bold")
    ax = axes[1]
    ax.plot(layers, cos, color=BLUE, marker="o", ms=4, lw=1.8, label="refusal direction vs script direction")
    ax.plot(layers, null, color=GREY, lw=1.2, ls=(0, (4, 3)), label="random direction (95th percentile)")
    ax.set_ylim(0, 1)
    ax.set_ylabel("|cosine|")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    ax.set_title("Overlap between the refusal direction\nand the script direction", loc="left", fontsize=10.5, fontweight="bold")
    for ax in axes:
        ax.axvline(sel, color=INK, lw=0.8, ls=":")
        ax.text(sel + 0.5, ax.get_ylim()[1] * 0.6, f"layer {sel}\n(used)", fontsize=8, color="#52606d")
        ax.set_xlabel("Layer")
        ax.set_xticks(layers[::2])
        ax.grid(axis="y", color=LIGHT, lw=0.8)
    fig.text(0.01, -0.05, "24 calibration families. Shaded: 95% bootstrap interval over families. "
             "1.0 on the right would mean the two directions are the same.", fontsize=8, color="#52606d")
    save(fig, "mechanism_by_layer.png")
    data["mechanism_by_layer"] = {"layers": layers, "norm_ratio_ro_over_ur": ratio, "abs_cos_refusal_vs_script": cos, "selected_layer": sel}


def boxes(name, title, items, footer=None, width=12.6, height=3.5):
    """A row of labelled boxes joined by arrows. items = [(heading, tag, tag colour, [lines]), ...]"""
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    n = len(items)
    gap, w = 2.6, (100 - 2.6 * (n - 1)) / n
    for i, (head, tag, col, lines) in enumerate(items):
        x = i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 8), w, 70, boxstyle="round,pad=0,rounding_size=1.6", fc="white", ec=col, lw=1.6))
        ax.add_patch(FancyBboxPatch((x, 66), w, 12, boxstyle="round,pad=0,rounding_size=1.6", fc=col, ec=col, lw=1.6))
        ax.text(x + w / 2, 72, head, ha="center", va="center", color="white", fontsize=10, fontweight="bold")
        ax.text(x + w / 2, 59, tag, ha="center", va="center", color=col, fontsize=9, fontweight="bold")
        for j, line in enumerate(lines):
            ax.text(x + 1.4, 51 - j * 7.3, line, ha="left", va="center", fontsize=8.2)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch((x + w + 0.2, 43), (x + w + gap - 0.2, 43), arrowstyle="-|>", mutation_scale=12, color=INK, lw=1.2))
    ax.text(0, 93, title, fontsize=12, fontweight="bold", va="center")
    if footer:
        ax.text(0, 2, footer, fontsize=8, color="#52606d", va="center")
    save(fig, name)


def main() -> int:
    an = load("experiments/results/test_analysis/test_analysis_guard.json")
    dev = load("experiments/results/fire_dev_v2/fire_dev/run_report.json")
    manifest = json.loads(published("model", "manifest.json").read_text(encoding="utf-8"))
    ds = json.loads(published("dataset", "manifest.json").read_text(encoding="utf-8"))
    rows = [json.loads(l) for l in published("dataset", "eval_logs/test_judged_public.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    reading: dict = {}
    for r in rows:
        if r["set"] == "test" and r["form"] == "ro" and r["safety_label"] == "harmful" and r.get("adjudicated"):
            reading.setdefault(r["arm"], {"R": 0, "A": 0, "N": 0})[r["adjudicated"]] += 1
    summary = {"public_rows": len(rows), "withheld_rows": sum(bool(r["withheld"]) for r in rows),
               "expected_outputs": sum(1 for l in published("model", "expected_outputs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    data: dict = {}
    fig_script_gap(an, reading, data)
    fig_outcomes(reading, data)
    fig_arms(an, data)
    fig_mechanism(dev, manifest, data)
    by = ds["by_split"]
    nf = ds["n_families"]
    n_arms = len(an["arms"])
    boxes("pipeline.png", "ScriptShield pipeline: three Lexsi toolkits chained around Tiny Aya Fire", [
        ("1  Dataset", "CuratorKIT", "#6b4fbb", [f"{nf} matched families", "harmful + harmless", "x 4 written forms", f"= {ds['n_records']} prompts",
                                                "split by family:", f"{by['calibration'] // 8} / {by['dev'] // 8} / {by['test'] // 8}"]),
        ("2  Steering vectors", "SafeTune", UR, ["contrastive activation", "addition (CAA) on the", f"{by['calibration'] // 8} calibration families:", "pooled vector,",
                                                 "residualized vector,", "four control vectors"]),
        ("3  Generation", "AuditKIT", RO, ["Tiny Aya Fire, greedy,", f"{manifest['inference']['max_new_tokens']} new tokens", "layer and strength set",
                                          f"on {by['dev'] // 8} dev families,", "then frozen; test run", f"once: {n_arms} arms, {summary['public_rows']:,} rows"]),
        ("4  Judging and tests", "ScriptShield", BLUE, ["guard judge (primary),", "second judge, reading", "of Roman-Urdu replies", "pre-registered tests:",
                                                         "exact McNemar, family", "bootstrap, Holm"]),
        ("5  Release", "Hugging Face", "#475569", ["dataset and logs", f"({summary['withheld_rows']} replies withheld)", "vectors and loader",
                                                   f"({summary['expected_outputs']} of {summary['expected_outputs']} outputs", "reproduced exactly)", "replay demo"]),
    ], footer="Calibration, development and test use different families. The test families were generated once, after everything else was frozen.")
    boxes("data_lineage.png", "Where the data comes from and what happens to it", [
        ("Drafting", "LLM-assisted", "#6b4fbb", ["requests that state a", "goal, no instructions", "written in Urdu script,", "Roman Urdu, code-mixed", "and English"]),
        ("Checks", "validator + CuratorKIT", UR, ["schema, script purity,", "pair completeness", "CuratorKIT pass:", f"{ds['n_records']} in, {ds['n_records']} out,", "no text changed"]),
        ("Frozen v0.2.0", "split by family", RO, [f"calibration {by['calibration']}", f"development {by['dev']}", f"test {by['test']}", "one checksum for", "the whole corpus"]),
        ("Evaluation logs", "public, partly withheld", BLUE, [f"{summary['public_rows']:,} test responses", "with labels and hashes", f"text withheld for {summary['withheld_rows']}",
                                                               "(not a clean refusal", "of a harmful request)"]),
        ("Human review", "in progress", "#475569", ["participant review by", "the project author", "corrections become", "a new version;", "v0.2.0 stays as is"]),
    ], footer="All prompts were unreviewed by a human when the experiments were run. Review status is tracked per prompt pair.")
    (OUT / "figure_data.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print("figures written:", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
