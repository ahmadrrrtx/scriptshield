"""Sentences and tables that several public documents share (article, cards, Space).

Each function builds its text from the result files, so that a number appears in one place in the code
and the documents cannot drift apart.
"""
from __future__ import annotations

ARM_NAMES = {"unsteered": "no steering", "pooled": "pooled", "residualized": "residualized",
             "random_subspace": "pooled with a random direction removed", "orthogonal_null": "placebo",
             "ur_only": "Urdu-only", "ro_only": "Roman-only"}


def harmful_ro_refusals(analysis: dict) -> dict[str, int]:
    return {arm: v["cells"]["ro/harmful"]["refusal"] for arm, v in analysis["arms"].items()}


def benign_refusals(analysis: dict) -> dict[str, int]:
    return {arm: v["cells"]["ur/benign"]["refusal"] + v["cells"]["ro/benign"]["refusal"] for arm, v in analysis["arms"].items()}


def alt_gap(analysis: dict, reading_refusals: int) -> str:
    c = analysis["arms"]["unsteered"]["cells"]

    def of(form):
        return f"{c[form + '/harmful']['refusal']} of {c[form + '/harmful']['n']}"
    n = c["ro/harmful"]["n"]
    return (f"Bar chart. Share of {n} harmful requests refused by Tiny Aya Fire without steering: Urdu script {of('ur')}, "
            f"Roman Urdu {of('ro')} ({reading_refusals} of {n} after reading the replies), code-mixed {of('cm')}, English {of('en')}.")


def alt_arms(analysis: dict) -> str:
    ro, be = harmful_ro_refusals(analysis), benign_refusals(analysis)
    order = [k for k in ARM_NAMES if k in ro]
    return ("Two horizontal bar charts over seven arms. Left, harmful Roman-Urdu requests refused out of 36: "
            + ", ".join(f"{ARM_NAMES[k]} {ro[k]}" for k in order) + ". Right, harmless requests refused out of 72: "
            + ", ".join(f"{ARM_NAMES[k]} {be[k]}" for k in order) + ".")


def placebo_did_almost_as_well(analysis: dict) -> bool:
    """True while the sentence 'a placebo vector did almost as well as the real vectors' describes the data."""
    ro = harmful_ro_refusals(analysis)
    return abs(ro["pooled"] - ro["orthogonal_null"]) <= 2 and min(v - ro["unsteered"] for k, v in ro.items() if k != "unsteered") >= 1


def review_summary(status: dict) -> dict:
    """Counts and ready-made sentences about the human review, from review_status.json."""
    total, counts = status["n_rows_total"], status["counts"]
    done = total - counts["unreviewed"]
    who = "the project author (participant review, not independent expert validation)"
    parts = ", ".join(f"{counts[k]} {k.replace('_', ' ')}" for k in ("accepted", "corrected", "rejected", "uncertain", "unable_to_judge") if counts.get(k))
    if done == 0:
        line = f"a review by {who} has been prepared and no prompt pair has been reviewed yet."
    else:
        line = f"{done} of {total} prompt pairs have been reviewed by {who}: {parts}."
    block = (f"> **Human review status: {done} of {total} prompt pairs reviewed.** Every prompt was drafted with an LLM under the\n"
             f"> author's direction. Reviewer: {who}.\n"
             + (f"> Result so far: {parts}.\n" if done else "")
             + ("> Until a pair is reviewed, treat its naturalness and the exact equivalence of its two scripts as unverified.\n" if done < total else "")
             + "> The status of every pair is in `reviewer_pack/review_status.json`. Corrections never alter this version; they go\n"
               "> into a new one that keeps the original text.")
    banner = (f"drafted with an LLM; {done} of {total} prompt pairs reviewed so far by the project author "
              "(participant review, not independent expert validation)")
    return {"done": done, "total": total, "counts": counts, "line": line, "block": block, "banner": banner,
            "state": "pending" if done == 0 else ("complete" if done == total else "in progress")}
