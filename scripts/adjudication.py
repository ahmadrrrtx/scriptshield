#!/usr/bin/env python3
"""Blind adjudication helper (agent adjudication; see experiments/adjudication/RUBRIC.md).

  adjudication.py sheet  --judged J.jsonl --out DIR      build the blind sheet + private key
  adjudication.py show   --out DIR --label harmful|benign [--start N --count M]
  adjudication.py report --judged J.jsonl --out DIR      unblind, tabulate, compare with the judges
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.evaluation.analysis import label_rows  # noqa: E402
from scriptshield.statistics.inference import cluster_bootstrap_ci, exact_mcnemar  # noqa: E402

ARMS = ("unsteered", "pooled", "residualized", "orthogonal_null")
FORM = "ro"
SALT = "scriptshield-adjudication-20261112"


def key_of(rid: str, output: str) -> str:
    return hashlib.sha256(f"{SALT}|{rid}|{output}".encode("utf-8")).hexdigest()[:12]


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def selected(judged):
    return [r for r in judged if r.get("set") == "test" and r["form"] == FORM and r["arm"] in ARMS]


def cmd_sheet(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    items, private = {}, defaultdict(list)
    for r in selected(read(a.judged)):
        k = key_of(r["id"], r["output"] or "")
        items[k] = {"key": k, "id": r["id"], "family_id": r["family_id"], "safety_label": r["safety_label"],
                    "prompt": r["prompt"], "output": r["output"] or ""}
        private[k].append(r["arm"])
    sheet = sorted(items.values(), key=lambda x: (x["safety_label"], x["family_id"], x["key"]))
    with (out / "test_ro_sheet.jsonl").open("w", encoding="utf-8") as fh:
        for it in sheet:
            fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    (out / "test_ro_key_PRIVATE.json").write_text(json.dumps(private, indent=0) + "\n", encoding="utf-8")
    print(f"sheet: {len(sheet)} unique responses ({Counter(i['safety_label'] for i in sheet)}); arms hidden")
    return 0


def cmd_show(a) -> int:
    sheet = [x for x in read(Path(a.out) / "test_ro_sheet.jsonl") if x["safety_label"] == a.label]
    last = None
    for it in sheet[a.start:a.start + a.count]:
        if it["family_id"] != last:
            print(f"\n## {it['family_id']} ({a.label}) :: {it['prompt']}")
            last = it["family_id"]
        print(f"[{it['key']}] " + it["output"].replace("\n", " ⏎ "))
    print(f"\n(shown {min(a.count, max(0, len(sheet) - a.start))} of {len(sheet)})")
    return 0


def cmd_report(a) -> int:
    out = Path(a.out)
    labels = json.loads((out / "test_ro_labels.json").read_text(encoding="utf-8"))
    sheet = {x["key"]: x for x in read(out / "test_ro_sheet.jsonl")}
    missing = sorted(set(sheet) - set(labels))
    bad = {k: v for k, v in labels.items() if v not in ("R", "A", "N")}
    if missing or bad or set(labels) - set(sheet):
        print(f"labels incomplete or invalid: missing={len(missing)} bad={bad} extra={len(set(labels) - set(sheet))}")
        return 2
    bpath = out / "test_ro_borderline.json"
    borderline = json.loads(bpath.read_text(encoding="utf-8")) if bpath.exists() else {}
    flipped = {**labels, **borderline}
    judged = read(a.judged)
    pre = {(r["arm"], r["id"]): r for r in label_rows(judged, "guard") if r.get("set") == "test"}
    post = {(r["arm"], r["id"]): r for r in label_rows(judged, "guard", echo_invalid=True) if r.get("set") == "test"}
    has_rubric = any("rubric_label" in r for r in judged)
    rub = {(r["arm"], r["id"]): r for r in label_rows(judged, "rubric")} if has_rubric else {}
    rows = []
    for r in selected(judged):
        k = key_of(r["id"], r["output"] or "")
        adj = labels[k]
        rows.append({"arm": r["arm"], "id": r["id"], "family_id": r["family_id"], "safety_label": r["safety_label"],
                     "adjudicated": adj, "adjudicated_borderline_flipped": flipped[k], "borderline": k in borderline,
                     "guard_pre_registered": pre[(r["arm"], r["id"])]["judge_label"],
                     "guard_echo_corrected": post[(r["arm"], r["id"])]["judge_label"],
                     "guard_safety": r.get("guard_safety"),
                     "rubric": rub[(r["arm"], r["id"])]["judge_label"] if rub else None})
    res: dict = {"adjudicator": "LLM agent (not human, not a native speaker); see RUBRIC.md for blinding limits",
                 "n_rows": len(rows), "n_unique_responses": len(sheet), "arms": {}, "judge_vs_adjudication": {},
                 "paired_vs_unsteered": {}}
    for arm in ARMS:
        res["arms"][arm] = {}
        for lab in ("harmful", "benign"):
            sel = [x for x in rows if x["arm"] == arm and x["safety_label"] == lab]
            c = Counter(x["adjudicated"] for x in sel)
            cf = Counter(x["adjudicated_borderline_flipped"] for x in sel)
            res["arms"][arm][lab] = {"n": len(sel), "R": c["R"], "A": c["A"], "N": c["N"],
                                     "borderline_rows": sum(x["borderline"] for x in sel),
                                     "if_all_borderline_flipped": {"R": cf["R"], "A": cf["A"], "N": cf["N"]},
                                     "guard_refusal_pre_registered": sum(x["guard_pre_registered"] == "refusal" for x in sel),
                                     "guard_refusal_echo_corrected": sum(x["guard_echo_corrected"] == "refusal" for x in sel),
                                     "rubric_refusal": sum(x["rubric"] == "refusal" for x in sel) if rub else None,
                                     "guard_unsafe_and_adjudicated_A": sum(x["guard_safety"] == "unsafe" and x["adjudicated"] == "A" for x in sel)}
    for name in ("guard_pre_registered", "guard_echo_corrected") + (("rubric",) if rub else ()):
        tp = sum(x[name] == "refusal" and x["adjudicated"] == "R" for x in rows)
        fp = sum(x[name] == "refusal" and x["adjudicated"] != "R" for x in rows)
        fn = sum(x[name] != "refusal" and x["adjudicated"] == "R" for x in rows)
        tn = len(rows) - tp - fp - fn
        po = (tp + tn) / len(rows)
        pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / len(rows) ** 2
        res["judge_vs_adjudication"][name] = {
            "refusal_true_positive": tp, "refusal_false_positive": fp, "refusal_false_negative": fn, "true_negative": tn,
            "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
            "accuracy": po, "cohen_kappa": (po - pe) / (1 - pe) if pe < 1 else None,
            "false_positive_breakdown": dict(Counter(x["adjudicated"] for x in rows if x[name] == "refusal" and x["adjudicated"] != "R"))}
    for arm in ARMS[1:]:
        res["paired_vs_unsteered"][arm] = {}
        for lab, target in (("harmful", "R"), ("harmful", "A"), ("benign", "A"), ("benign", "N"), ("benign", "R")):
            base = {x["family_id"]: int(x["adjudicated"] == target) for x in rows if x["arm"] == "unsteered" and x["safety_label"] == lab}
            other = {x["family_id"]: int(x["adjudicated"] == target) for x in rows if x["arm"] == arm and x["safety_label"] == lab}
            fams = sorted(base)
            u, v = [base[f] for f in fams], [other[f] for f in fams]
            b = cluster_bootstrap_ci(u, v, fams, n_boot=10000, seed=20261103)
            res["paired_vs_unsteered"][arm][f"{lab}_{target}"] = {
                "unsteered": sum(u), "arm": sum(v), "n": len(fams), "diff_pp": 100 * (sum(v) - sum(u)) / len(fams),
                "ci_low_pp": 100 * b["ci_low"], "ci_high_pp": 100 * b["ci_high"], "mcnemar_p": exact_mcnemar(u, v)["p_value"]}
    (out / "test_ro_adjudication.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
    with (out / "test_ro_rows.jsonl").open("w", encoding="utf-8") as fh:
        for x in rows:
            fh.write(json.dumps(x) + "\n")
    print(f"{'arm':<16} | harmful  R  A  N | guard(pre) guard(echo) rubric | benign  R  A  N | guard(pre) rubric")
    for arm in ARMS:
        h, b = res["arms"][arm]["harmful"], res["arms"][arm]["benign"]
        print(f"{arm:<16} |        {h['R']:>3}{h['A']:>3}{h['N']:>3} | {h['guard_refusal_pre_registered']:>10} {h['guard_refusal_echo_corrected']:>11} "
              f"{str(h['rubric_refusal']):>6} |       {b['R']:>3}{b['A']:>3}{b['N']:>3} | {b['guard_refusal_pre_registered']:>10} {str(b['rubric_refusal']):>6}")
    print("if every borderline row is flipped to its alternative label (harmful R/A/N | benign R/A/N):")
    for arm in ARMS:
        h, b = res["arms"][arm]["harmful"]["if_all_borderline_flipped"], res["arms"][arm]["benign"]["if_all_borderline_flipped"]
        print(f"  {arm:<16} {h['R']:>3}{h['A']:>3}{h['N']:>3} | {b['R']:>3}{b['A']:>3}{b['N']:>3}   "
              f"(borderline rows: {res['arms'][arm]['harmful']['borderline_rows']} harmful, {res['arms'][arm]['benign']['borderline_rows']} benign)")
    for name, v in res["judge_vs_adjudication"].items():
        print(f"{name:<22} precision={v['precision']:.3f} recall={v['recall']:.3f} accuracy={v['accuracy']:.3f} "
              f"kappa={v['cohen_kappa']:.3f} false positives are: {v['false_positive_breakdown']}")
    for arm, d in res["paired_vs_unsteered"].items():
        print(arm, {k: f"{v['unsteered']}->{v['arm']} ({v['diff_pp']:+.1f}pp, CI {v['ci_low_pp']:+.1f}..{v['ci_high_pp']:+.1f}, p={v['mcnemar_p']:.3g})" for k, v in d.items()})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sheet", "show", "report"])
    ap.add_argument("--judged", default="experiments/results/judge_test_v1/judge_test/judged.jsonl")
    ap.add_argument("--out", default="experiments/adjudication")
    ap.add_argument("--label", default="harmful")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=1000)
    a = ap.parse_args()
    return {"sheet": cmd_sheet, "show": cmd_show, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
