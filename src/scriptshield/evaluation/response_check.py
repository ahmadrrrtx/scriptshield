"""Human check of the response reading: sampling design, answer parsing and agreement statistics.

The reading of the Roman-Urdu test replies (refusal / goes along / neither) was done by an LLM agent. This module
supports a check of that reading by a person on a stratified sample. It holds no response text.
"""
from __future__ import annotations

import re
from collections import Counter

LABELS = ("R", "A", "N")
SEED = 20261113
# stratum = (prompt label, label of the LLM reading, automatic judge said "refusal" or something else) -> sample size
ALLOCATION = {
    ("harmful", "R", "refusal"): 8, ("harmful", "R", "other"): 4,
    ("harmful", "N", "refusal"): 6, ("harmful", "N", "other"): 6,
    ("harmful", "A", "refusal"): 3, ("harmful", "A", "other"): 5,
    ("benign", "N", "refusal"): 6, ("benign", "N", "other"): 3,
    ("benign", "A", "refusal"): 3, ("benign", "A", "other"): 4,
}
LINE = re.compile(r"^\s*(T\d{2})\s*[=:\-]?\s*([RANU])\b", re.I)
EMPTY = re.compile(r"^\s*T\d{2}\s*[=:\-]?\s*$", re.I)


def stratum_name(s) -> str:
    return "/".join(s)


def parse_answers(text: str) -> tuple[dict[str, str], list[str]]:
    """'T07 = N' lines -> {item: label}. Blank answers are skipped; anything else is reported, never guessed."""
    out, problems = {}, []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().strip("`")
        if not line or line.startswith("#") or EMPTY.match(line):
            continue
        m = LINE.match(line)
        if not m:
            if re.match(r"^\s*T\d{2}\b", line, re.I):
                problems.append(f"line {n}: not understood: {line[:60]}")
            continue
        out[m.group(1).upper()] = m.group(2).upper()
    return out, problems


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def weighted_rate(items: list[dict], sizes: dict[str, int], hit, strata=None) -> dict:
    """Stratum-weighted share of items for which hit(item) is true. Strata without a labelled item are left out
    and listed, so that the estimate says what it covers."""
    num = den = 0.0
    covered, missing = [], []
    for name, size in sizes.items():
        if strata is not None and name not in strata:
            continue
        sel = [it for it in items if it["stratum"] == name]
        if not sel:
            missing.append(name)
            continue
        covered.append(name)
        num += size * sum(bool(hit(it)) for it in sel) / len(sel)
        den += size
    return {"value": (num / den) if den else None, "population": int(den), "strata_without_labels": missing, "weighted_hits": num}


def summarise(items: list[dict], sizes: dict[str, int]) -> dict:
    """items: [{'item', 'stratum', 'llm', 'judge_refusal', 'human'}], human in R/A/N/U."""
    done = [it for it in items if it.get("human") in LABELS]
    unsure = [it for it in items if it.get("human") == "U"]
    conf = {x: {y: sum(it["llm"] == x and it["human"] == y for it in done) for y in LABELS} for x in LABELS}
    agree = sum(it["llm"] == it["human"] for it in done)
    res = {"n_sample": len(items), "n_labelled": len(done), "n_cannot_judge": len(unsure), "n_open": len(items) - len(done) - len(unsure),
           "agreement_raw": {"k": agree, "n": len(done)},
           "kappa_vs_llm_reading": cohen_kappa([it["llm"] for it in done], [it["human"] for it in done]),
           "confusion_llm_rows_human_cols": conf}
    if done:
        res["agreement_weighted"] = weighted_rate(done, sizes, lambda it: it["llm"] == it["human"])
        jr = {n for n in sizes if n.endswith("/refusal")}
        prec = weighted_rate(done, sizes, lambda it: it["human"] == "R", strata=jr)
        all_r = weighted_rate(done, sizes, lambda it: it["human"] == "R")
        res["judge_vs_human"] = {
            "precision_weighted": prec["value"],
            "recall_weighted": (prec["weighted_hits"] / all_r["weighted_hits"]) if all_r["weighted_hits"] else None,
            "sample_judge_refusal": {"n": sum(it["judge_refusal"] for it in done), "human_R": sum(it["judge_refusal"] and it["human"] == "R" for it in done)},
            "strata_without_labels": sorted(set(prec["strata_without_labels"]) | set(all_r["strata_without_labels"])),
        }
        llm_prec = sum(size for name, size in sizes.items() if name.endswith("/refusal") and name.split("/")[1] == "R") / sum(size for name, size in sizes.items() if name.endswith("/refusal"))
        llm_rec = sum(size for name, size in sizes.items() if name.endswith("/refusal") and name.split("/")[1] == "R") / sum(size for name, size in sizes.items() if name.split("/")[1] == "R")
        res["judge_vs_llm_reading_all_unique_replies"] = {"precision": llm_prec, "recall": llm_rec}
    return res
