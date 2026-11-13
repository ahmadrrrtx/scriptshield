#!/usr/bin/env python3
"""Agreement of each automatic refusal signal with reference labels (binary: refusal vs not).

Usage: judge_agreement.py <judged.jsonl> <reference.jsonl> [--arm unsteered]
The reference file says who labelled it. An LLM agent's adjudication is NOT human validation.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter


def kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("judged")
    ap.add_argument("reference")
    ap.add_argument("--arm", default="unsteered")
    ap.add_argument("--source", default=None, help="only rows whose source_file equals this name")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    ref = {}
    for line in open(a.reference, encoding="utf-8"):
        r = json.loads(line)
        ref[(r["id"], r.get("arm", "unsteered"))] = r
    rows = [json.loads(l) for l in open(a.judged, encoding="utf-8")]
    rows = [r for r in rows if (r["id"], r.get("arm", "unsteered")) in ref and r.get("arm", "unsteered") == a.arm
            and (a.source is None or r.get("source_file") == a.source)]
    seen = set()
    rows = [r for r in rows if not ((r["id"], r.get("arm")) in seen or seen.add((r["id"], r.get("arm"))))]
    if not rows:
        print("no overlap between judged rows and reference")
        return 1
    signals = {"guard": ("guard_refusal", "refusal"), "rubric": ("rubric_label", "refusal"),
               "keyword_proxy": ("proxy_label", "refusal")}
    truth = [ref[(r["id"], r.get("arm", "unsteered"))]["ref_label"] == "refusal" for r in rows]
    labeler = next(iter(ref.values())).get("labeler")
    out = {"n": len(rows), "reference_labeler": labeler, "reference_refusals": sum(truth), "signals": {}}
    print(f"n={len(rows)}  reference refusals={sum(truth)}  labeler={labeler}")
    for name, (key, pos) in signals.items():
        if key not in rows[0]:
            continue
        pred = [r[key] == pos for r in rows]
        tp = sum(p and t for p, t in zip(pred, truth)); fp = sum(p and not t for p, t in zip(pred, truth))
        fn = sum((not p) and t for p, t in zip(pred, truth)); tn = sum((not p) and (not t) for p, t in zip(pred, truth))
        by_form = {}
        for form in ("ur", "ro", "cm", "en"):
            ix = [i for i, r in enumerate(rows) if r["form"] == form]
            by_form[form] = sum(pred[i] == truth[i] for i in ix) / len(ix) if ix else None
        res = {"accuracy": (tp + tn) / len(rows), "kappa": kappa(pred, truth),
               "recall_refusal": tp / (tp + fn) if tp + fn else None,
               "precision_refusal": tp / (tp + fp) if tp + fp else None,
               "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}, "accuracy_by_form": by_form,
               "raw_label_counts": dict(Counter(r[key] for r in rows))}
        out["signals"][name] = res
        print(f"  {name:<14} acc={res['accuracy']:.3f} kappa={res['kappa']:.3f} recall={res['recall_refusal']} "
              f"precision={res['precision_refusal']} conf={res['confusion']} by_form={by_form}")
        for r, p, t in zip(rows, pred, truth):
            if p != t:
                print(f"      DISAGREE {r['id']}: {name}={r[key]} ref={'refusal' if t else 'not'} | {r['output'][:90]!r}")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
