#!/usr/bin/env python3
"""POST HOC (protocol A20): utility by pattern (pre-registered) next to utility on reading.

The reader's labels live in experiments/adjudication/utility_reading_check.json as a list of
disagreements with the pattern score. Everything else here is computed from the judged file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.evaluation.utility import apply_reading, is_correct, load_utility  # noqa: E402


def counts(scores: dict, arm: str) -> dict:
    by = {"ur": 0, "ro": 0}
    for (a, qid), ok in scores.items():
        if a == arm:
            by[qid[-2:]] += bool(ok)
    return {**by, "all": by["ur"] + by["ro"]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judged", default="experiments/results/judge_test_merged/judged.jsonl")
    ap.add_argument("--reading", default="experiments/adjudication/utility_reading_check.json")
    ap.add_argument("--out", default="experiments/results/test_analysis/utility_reading.json")
    a = ap.parse_args()
    raw = (ROOT / a.judged).read_bytes()
    gold = {u["id"]: u["answer"] for u in load_utility(ROOT)}
    pattern: dict[tuple[str, str], bool] = {}
    for line in raw.decode("utf-8").splitlines():
        r = json.loads(line)
        if r.get("set") == "utility":
            key = (r["arm"], r["id"])
            if key in pattern:
                raise SystemExit(f"duplicate utility row {key}")
            pattern[key] = is_correct(r["output"], gold[r["id"]])
    rec = json.loads((ROOT / a.reading).read_text(encoding="utf-8"))
    dis = rec["disagreements"]
    strict = apply_reading(pattern, dis)
    lenient = apply_reading(pattern, [d for d in dis if not d.get("borderline")])
    arms = sorted({k[0] for k in pattern}, key=["unsteered", "pooled", "residualized"].index)
    n_q = len({k[1] for k in pattern})

    def right(scores, arm):
        return {q for (x, q), ok in scores.items() if x == arm and ok}

    pairs = [("pooled", "unsteered"), ("residualized", "unsteered"), ("residualized", "pooled")]
    out = {
        "status": "POST HOC (protocol A20). Read by the LLM agent, not a human; arm labels visible.",
        "judged_sha256": hashlib.sha256(raw).hexdigest(),
        "n_answers": len(pattern), "n_questions_per_arm": n_q,
        "n_disagreements": sum(len(d["arms"]) for d in dis),
        "correct_but_not_matched": sum(len(d["arms"]) for d in dis if d["reading"] == "correct"),
        "matched_but_incorrect": sum(len(d["arms"]) for d in dis if d["reading"] == "incorrect"),
        "n_borderline": sum(len(d["arms"]) for d in dis if d.get("borderline")),
        "arms": {arm: {"n": n_q, "pattern": counts(pattern, arm), "reading": counts(strict, arm),
                       "reading_borderline_flipped": counts(lenient, arm),
                       "disagreements": sum(arm in d["arms"] for d in dis)} for arm in arms},
        "questions_answered_differently": {
            f"{x}_vs_{y}": {"pattern": sorted(right(pattern, x) ^ right(pattern, y)),
                            "reading": sorted(right(strict, x) ^ right(strict, y)),
                            "reading_borderline_flipped": sorted(right(lenient, x) ^ right(lenient, y))}
            for x, y in pairs if x in arms and y in arms},
        "utility_drop_pp_residualized_vs_pooled": {
            "pattern": 100 * (counts(pattern, "pooled")["all"] - counts(pattern, "residualized")["all"]) / n_q,
            "reading": 100 * (counts(strict, "pooled")["all"] - counts(strict, "residualized")["all"]) / n_q},
        "disagreements": dis,
    }
    (ROOT / a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for arm in arms:
        v = out["arms"][arm]
        print(f"{arm:13s} pattern {v['pattern']['all']}/{n_q} (ur {v['pattern']['ur']}, ro {v['pattern']['ro']})"
              f" | reading {v['reading']['all']}/{n_q} (ur {v['reading']['ur']}, ro {v['reading']['ro']})"
              f" | borderline flipped {v['reading_borderline_flipped']['all']}/{n_q}")
    print(f"{out['n_disagreements']} of {out['n_answers']} pattern scores disagree with the reading -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
