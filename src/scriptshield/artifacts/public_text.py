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


REVIEWER_WORDS = "the project author, a native Urdu / Roman Urdu speaker (one participant reviewer; not independent expert validation)"
REVIEW_IS_NOT = ("It is one participant-provided review: not an independent expert panel, not a professional translation "
                 "certification and not a consensus of several reviewers.")
STATUS_WORDS = {"accepted": "accepted as they are", "corrected": "corrected",
                "correction_pending": "to be corrected (the corrected text has not been received)",
                "rejected": "rejected", "uncertain": "uncertain", "unable_to_judge": "not judged"}


def _mean(xs: list[int]) -> str:
    return f"{sum(xs) / len(xs):.1f}" if xs else "n/a"


def review_findings(status: dict) -> str:
    """What the reviewer found in the pairs reviewed so far, as plain sentences. Empty if nothing is reviewed."""
    rows = status.get("rows", {})
    if not rows:
        return ""
    n = len(rows)
    ur = [r["ur"] for r in rows.values() if isinstance(r.get("ur"), int)]
    ro = [r["ro"] for r in rows.values() if isinstance(r.get("ro"), int)]
    same = sum(1 for r in rows.values() if r.get("same") == "yes")
    label = sum(1 for r in rows.values() if r.get("label") == "yes")
    alt = [r["alt"] for r in rows.values() if "alt" in r]
    out = [f"In the prompt pairs reviewed so far, the reviewer judged the Urdu-script and the Roman-Urdu sentence to mean the same in "
           f"{same} of {n} and the label to be right in {label} of {n}."]
    if ur and ro:
        out.append(f"Naturalness on a scale of 1 to 5: Urdu script {_mean(ur)} on average (lowest {min(ur)}), Roman Urdu {_mean(ro)} "
                   f"(lowest {min(ro)}).")
    if alt:
        out.append(f"The second Roman-Urdu spelling was judged natural in {sum(1 for a in alt if a == 'yes')} of {len(alt)}.")
    corr = [r for r in rows.values() if r.get("correction_kind")]
    if corr:
        repl = sum(1 for r in corr if r["correction_kind"] == "replacement")
        waiting = sum(1 for r in corr if r.get("pending_fields"))
        kinds = f"{len(corr) - repl} of wording" + (f", {repl} that replace{'s' if repl == 1 else ''} a request" if repl else "")
        got = len(corr) - waiting
        if waiting == len(corr):
            out.append(f"He announced corrections to {len(corr)} prompt pairs ({kinds}); the corrected text has not been received for any "
                       "of them, so no sentence has been changed.")
        else:
            out.append(f"He asked for changes to {len(corr)} prompt pairs ({kinds}). For {got} of them he supplied the corrected sentences; "
                       "they are recorded in the review revision next to the originals and have not been run through a model."
                       + (f" The other {waiting} wait{'s' if waiting == 1 else ''} for {'its' if waiting == 1 else 'their'} text, and until "
                          f"then the original sentence{'' if waiting == 1 else 's'} stand{'s' if waiting == 1 else ''}." if waiting else ""))
    pairs = status.get("pair_verdicts", {})
    no = sorted(f for f, v in pairs.items() if v == "no")
    if pairs:
        out.append(f"He judged the harmful and the harmless request to fit together as a pair in {sum(1 for v in pairs.values() if v == 'yes')} of "
                   f"{len(pairs)} families" + (f"; not in {len(no)} (`{'`, `'.join(no)}`), which {'is' if len(no) == 1 else 'are'} left out of "
                                               "comparisons between harmful and harmless requests on revised data." if no else "."))
    return " ".join(out)


def review_summary(status: dict, revision: dict | None = None) -> dict:
    """Counts and ready-made sentences about the human review, from review_status.json.

    ``revision`` is the manifest of the current review revision (data/revisions/v<id>/REVISION.json), if there is one.
    """
    total, counts = status["n_rows_total"], status["counts"]
    done = total - counts["unreviewed"]
    fam_done, fam_total = len(status.get("families_fully_reviewed", [])), total // 2
    who = REVIEWER_WORDS
    parts = ", ".join(f"{counts[k]} {STATUS_WORDS[k]}" for k in STATUS_WORDS if counts.get(k))
    findings = review_findings(status)
    rev_id = revision["revision_id"] if revision else None
    if done == 0:
        line = f"a review by {who} has been prepared and no prompt pair has been reviewed yet."
    else:
        line = f"{done} of {total} prompt pairs ({fam_done} of {fam_total} families) have been reviewed by {who}: {parts}."
    wrap = lambda text: "".join(f"> {x}\n" for x in _wrap(text, 112))  # noqa: E731
    block = (f"> **Human review status: {done} of {total} prompt pairs reviewed ({fam_done} of {fam_total} families).**\n"
             + wrap(f"Every prompt was drafted with an LLM under the author's direction. Reviewer: {who}.")
             + (wrap(REVIEW_IS_NOT) if done else "")
             + (">\n" + wrap(f"Result so far: {parts}. {findings}") if done else "")
             + (">\n" if done else "")
             + ("> Until a pair is reviewed, treat its naturalness and the exact equivalence of its two scripts as unverified.\n" if done < total else "")
             + "> The status of every pair is in `reviewer_pack/review_status.json`. The evaluated data (v0.2.0) is never edited:\n"
             + ("> review results and corrected sentences are published next to it as a review revision "
                f"(`revisions/v{rev_id}/`),\n> and no result has been computed on a corrected sentence."
                if rev_id else "> corrections go into a separate revision that keeps the original text."))
    banner = (f"drafted with an LLM; {done} of {total} prompt pairs reviewed so far by the project author "
              "(one participant reviewer, a native Urdu / Roman Urdu speaker; not independent expert validation)")
    state = "pending" if done == 0 else ("complete" if done == total else "in progress")
    return {"done": done, "total": total, "families_done": fam_done, "families_total": fam_total, "counts": counts, "line": line,
            "block": block, "banner": banner, "findings": findings, "parts": parts, "who": who, "revision_id": rev_id, "state": state,
            "pairs_not_comparable": sorted(f for f, v in status.get("pair_verdicts", {}).items() if v == "no")}


def _wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + ([cur] if cur else [])
