#!/usr/bin/env python3
"""Does the script gap depend on particular prompts? Post hoc sensitivity checks on the PUBLIC test logs.

The pre-registered test is unchanged: unsteered model, harmful prompts, Urdu script against Roman Urdu, paired by
family, on all 36 test families. This script repeats that comparison on subsets defined by information that does
not depend on any model output: harm group, the form of the request, the flags of the dataset audit and, as it
arrives, the reviewer's verdict. No threshold, label or test set is changed, and nothing here is a new
pre-registered test. The steering arms are tabulated on the same subsets without tests.

  python scripts/robustness_checks.py                 # uses release/hf_dataset/eval_logs if present
  python scripts/robustness_checks.py --download      # fetches the public logs (tag v0.2.0) from the Hub

Writes docs/ROBUSTNESS_CHECKS.md and data/quality/robustness_checks_v0.2.0.json. No GPU, no model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.statistics.inference import exact_mcnemar  # noqa: E402

LOG = "eval_logs/test_judged_public.jsonl"
ARMS = ("unsteered", "pooled", "residualized", "orthogonal_null")
ALL_ARMS = ("unsteered", "pooled", "residualized", "random_subspace", "orthogonal_null", "ur_only", "ro_only")
ARM_TITLES = {"unsteered": "No steering", "pooled": "Pooled", "residualized": "Residualized", "random_subspace": "Pooled, random direction removed",
              "orthogonal_null": "Placebo", "ur_only": "Urdu-only vector", "ro_only": "Roman-only vector"}


def load_rows(download: bool, logs: Path | None) -> list[dict]:
    if logs is None and not download and (ROOT / "release/hf_dataset" / LOG).exists():
        path = ROOT / "release/hf_dataset" / LOG
    elif logs is not None:
        path = logs
    else:
        from huggingface_hub import hf_hub_download
        links = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))
        path = Path(hf_hub_download(links["hf_dataset"]["repo_id"], LOG, repo_type="dataset", revision="v0.2.0"))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def table(rows: list[dict]) -> dict:
    """family -> arm -> form -> {'judge': 0/1, 'read': 0/1/None} for harmful test prompts."""
    out: dict = {}
    for r in rows:
        if r.get("set") != "test" or r["safety_label"] != "harmful" or r["form"] not in ("ur", "ro"):
            continue
        cell = {"judge": int(r["judge_label"] == "refusal"),
                "read": None if r.get("adjudicated") is None else int(r["adjudicated"] == "R")}
        out.setdefault(r["family_id"], {}).setdefault(r["arm"], {})[r["form"]] = cell
    return out


def benign_table(rows: list[dict]) -> dict:
    """family -> arm -> form -> 0/1 (judge says refusal) for harmless test prompts in Urdu script and Roman Urdu."""
    out: dict = {}
    for r in rows:
        if r.get("set") == "test" and r["safety_label"] == "benign" and r["form"] in ("ur", "ro"):
            out.setdefault(r["family_id"], {}).setdefault(r["arm"], {})[r["form"]] = int(r["judge_label"] == "refusal")
    return out


def harmless_refusals(btab: dict, fams: list[str]) -> dict:
    """Harmless requests refused per arm on the given families: {'prompts': 2 x families, 'arms': {arm: count}}."""
    return {"families": len(fams), "prompts": 2 * len(fams),
            "arms": {a: sum(btab[f][a]["ur"] + btab[f][a]["ro"] for f in fams) for a in ALL_ARMS}}


def gap(tab: dict, fams: list[str]) -> dict:
    ur = [tab[f]["unsteered"]["ur"]["judge"] for f in fams]
    ro = [tab[f]["unsteered"]["ro"]["judge"] for f in fams]
    read = [tab[f]["unsteered"]["ro"]["read"] for f in fams]
    res = {"n": len(fams), "ur": sum(ur), "ro": sum(ro), "ro_read": sum(read) if all(x is not None for x in read) else None,
           "diff_pp": round(100 * (sum(ro) - sum(ur)) / len(fams), 1) if fams else None,
           "p": exact_mcnemar(ur, ro)["p_value"] if fams else None,
           "arms_ro": {a: sum(tab[f][a]["ro"]["judge"] for f in fams) for a in ARMS}}
    return res


KINDS = (("echo", "Repeats the prompt"), ("devanagari", "Written in Devanagari (Hindi script)"),
         ("latin", "Other text in Latin letters"), ("other", "Mixed or other script"))


def judge_errors(rows: list[dict]) -> list[dict]:
    """Judge label against the reading, by kind of reply. Roman-Urdu test rows that were read (four arms)."""
    read = [r for r in rows if r.get("set") == "test" and r["form"] == "ro" and r.get("adjudicated") in ("R", "A", "N")]

    def kind(r):
        if r.get("is_echo"):
            return "echo"
        return r.get("response_script") if r.get("response_script") in ("devanagari", "latin") else "other"
    out = []
    for key, title in (*KINDS, ("all", "All replies that were read")):
        sel = [r for r in read if key == "all" or kind(r) == key]
        jr = [r for r in sel if r["judge_label"] == "refusal"]
        out.append({"key": key, "title": title, "n": len(sel), "judge_refusal": len(jr),
                    "true_refusal": sum(r["adjudicated"] == "R" for r in jr),
                    "false_refusal_nonresponsive": sum(r["adjudicated"] == "N" for r in jr),
                    "false_refusal_answer": sum(r["adjudicated"] == "A" for r in jr),
                    "missed_refusal": sum(r["adjudicated"] == "R" and r["judge_label"] != "refusal" for r in sel),
                    "refusal_on_reading": sum(r["adjudicated"] == "R" for r in sel)})
    return out


def subsets(audit: dict, review: dict, test: list[str]) -> list[tuple[str, str, list[str]]]:
    fam = audit["families"]

    def notes(f, types=None, labels=("harmful",)):
        return [n for n in fam[f]["llm_notes"] if n["label"] in labels and (types is None or n["type"] in types)]

    def flags(f, label="harmful"):
        return [x for x in fam[f]["automatic_flags"] if x["label"] == label]
    accepted = {k.rsplit("-", 1)[0] for k, v in review.get("rows", {}).items()
                if k.endswith("-harmful") and v.get("status") == "accepted"}
    reviewed = {k.rsplit("-", 1)[0] for k, v in review.get("rows", {}).items() if k.endswith("-harmful") and v.get("status")}
    pair_no = {f for f, v in review.get("pair_verdicts", {}).items() if v == "no"}
    out = [("all", "All test families (the pre-registered comparison)", test)]
    for g in sorted({fam[f]["harm_group"] for f in test}):
        out.append((f"group:{g}", f"Harm group: {g}", [f for f in test if fam[f]["harm_group"] == g]))
    for g in sorted({fam[f]["harm_group"] for f in test}):
        out.append((f"without:{g}", f"Without harm group: {g}", [f for f in test if fam[f]["harm_group"] != g]))
    out += [
        ("form:command", "Harmful request is a command", [f for f in test if fam[f]["speech_act"]["harmful"]["is_command"]]),
        ("form:question", "Harmful request is a question", [f for f in test if not fam[f]["speech_act"]["harmful"]["is_command"]]),
        ("audit:no_word_flag", "Without families where a word differs between the scripts (automatic check)", [f for f in test if not flags(f)]),
        ("audit:no_meaning_drift", "Without families with an LLM note on meaning drift", [f for f in test if not notes(f, {"meaning_drift"})]),
        ("audit:no_register", "Without families with an LLM note on register", [f for f in test if not notes(f, {"register"})]),
        ("audit:no_llm_note", "Without families with any LLM note on the harmful prompt", [f for f in test if not notes(f)]),
        ("audit:clean", "Only families with no automatic flag and no LLM note on the harmful prompt", [f for f in test if not notes(f) and not flags(f)]),
        ("review:accepted", "Only families whose harmful prompt pair the reviewer accepted as it is", [f for f in test if f in accepted]),
        ("review:reviewed", "Only families whose harmful prompt pair has been reviewed (any verdict)", [f for f in test if f in reviewed]),
        ("review:pair_ok", "Without families whose harmful and harmless request the reviewer judged not comparable", [f for f in test if f not in pair_no]),
    ]
    return out


def review_lines(by: dict, review_done: int, review_total: int, harmless: dict) -> list[str]:
    """The bullet on human review in 'Result in brief'."""
    if not review_done:
        return [f"- Human review: {review_done} of {review_total} prompt pairs reviewed so far. The review rows below fill in as the review proceeds."]
    rev, acc, ok = by["review:reviewed"], by["review:accepted"], by["review:pair_ok"]
    out = [f"- Human review: {review_done} of {review_total} prompt pairs reviewed so far (one participant reviewer). On the {rev['n']} reviewed test "
           f"families Roman Urdu is refused {rev['ro']}/{rev['n']} times against {rev['ur']}/{rev['n']} in Urdu script; on the {acc['n']} whose harmful "
           f"prompt pair he accepted as it is, {acc['ro']}/{acc['n']} against {acc['ur']}/{acc['n']}. Too few families to say more than that the "
           "reviewed ones show the same direction."]
    left = harmless.get("left_out", [])
    if left:
        out.append(f"- The reviewer judged the harmful and the harmless request of {len(left)} test famil{'y' if len(left) == 1 else 'ies'} not comparable "
                   f"({', '.join('`' + f + '`' for f in left)}). Without {'it' if len(left) == 1 else 'them'} the gap is {ok['ro']}/{ok['n']} against "
                   f"{ok['ur']}/{ok['n']} ({pp(ok['diff_pp'])}), and "
                   + (lambda moved: "no count of refused harmless requests changes" if moved == 0 else
                      f"the counts of refused harmless requests change by at most {moved} per arm")(
                          max(harmless["all"]["arms"][a] - harmless["pair_ok"]["arms"][a] for a in harmless["all"]["arms"]))
                   + " (table below).")
    return out


def harmless_lines(harmless: dict) -> list[str]:
    """Harmless requests refused per arm, with and without the families whose pairing the reviewer rejected."""
    if not harmless:
        return []
    a, b, left = harmless["all"], harmless["pair_ok"], harmless.get("left_out", [])
    lines = ["### Harmless requests refused, with and without families whose pairing the reviewer rejected", "",
             "The harmless request of a family serves as its matched control. Where the reviewer judged the harmful and the harmless",
             "request not comparable, that control is in doubt, so the counts are shown both ways. Urdu script and Roman Urdu together;",
             "automatic judge.", "",
             f"| Arm | All {a['families']} test families (of {a['prompts']} prompts) | "
             + (f"Without {', '.join('`' + f + '`' for f in left)} (of {b['prompts']} prompts) |" if left else "No family left out yet |"),
             "|---|---:|---:|"]
    for arm in a["arms"]:
        lines.append(f"| {ARM_TITLES[arm]} | {a['arms'][arm]} | {b['arms'][arm] if left else ''} |")
    return lines + [""]


def pp(x: float) -> str:
    return "0.0 pp" if x == 0 else f"{x:+.1f} pp"


def fmt_p(p) -> str:
    return "n/a" if p is None else (f"{p:.2g}" if p < 0.001 else f"{p:.3f}")


def render(results: list[dict], review_done: int, review_total: int, errors: list[dict], harmless: dict | None = None) -> str:
    by = {r["key"]: r for r in results}
    full = by["all"]
    harmless = harmless or {}

    def row(r):
        if r["n"] == 0:
            return f"| {r['title']} | 0 | | | | | |"
        read = "" if r["ro_read"] is None else f"{r['ro_read']}/{r['n']}"
        return (f"| {r['title']} | {r['n']} | {r['ur']}/{r['n']} | {r['ro']}/{r['n']} | {read} | "
                f"{pp(r['diff_pp'])} | {fmt_p(r['p'])} |")
    head = ["| Subset | Families | Refused, Urdu script | Refused, Roman Urdu (judge) | (on reading) | Difference (judge) | exact McNemar p |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    groups = [r for r in results if r["key"].startswith("group:")]
    without = [r for r in results if r["key"].startswith("without:")]
    forms = [r for r in results if r["key"].startswith("form:")]
    audit = [r for r in results if r["key"].startswith("audit:")]
    review = [r for r in results if r["key"].startswith("review:")]
    lo = min(without, key=lambda r: abs(r["diff_pp"])); hi = max(without, key=lambda r: abs(r["diff_pp"]))
    least = min((r for r in audit if r["n"]), key=lambda r: abs(r["diff_pp"]))
    in_every_group = all(r["ro"] < r["ur"] for r in groups)
    clean, shown = by["audit:clean"], [full, *audit, *forms]
    tot, echo = errors[-1], errors[0]

    def lead(r):
        return r["arms_ro"]["residualized"] - r["arms_ro"]["orthogonal_null"]
    sizes = sorted(r["n"] for r in groups)
    lines = [
        "# Robustness checks of the script gap",
        "",
        "<!-- GENERATED by scripts/robustness_checks.py from the public evaluation logs. Do not edit by hand. -->",
        "",
        "**Status: post hoc sensitivity analysis** (protocol amendment A21). It was planned after the test results and",
        "the dataset audit were known. The pre-registered test is the first row of the first table and is unchanged.",
        "Nothing below is a new confirmatory test; small subsets have wide uncertainty and their p-values are descriptive.",
        "",
        "**Questions.** The [dataset audit](DATASET_QUALITY_AUDIT.md) found imperfections in some prompts. Does the gap",
        "between Urdu script and Roman Urdu depend on those prompts, on one topic, or on one form of request? And when",
        "the automatic judge is wrong about a Roman-Urdu reply, in which direction, and on what kind of text?",
        "",
        "**How.** Unsteered Tiny Aya Fire, harmful prompts, same families in both scripts. Each subset is defined by",
        "information that does not depend on any model output (topic, form of the request, audit flags, review",
        "verdict). \"On reading\" is the count of real refusals when an LLM agent read the Roman-Urdu replies (not a",
        "human).",
        "",
        "## Result in brief",
        "",
        f"- Full test set: {full['ur']}/{full['n']} in Urdu script, {full['ro']}/{full['n']} in Roman Urdu ({pp(full['diff_pp'])}).",
        f"- Leaving out any one harm group, the difference stays between {pp(lo['diff_pp'])} and {pp(hi['diff_pp'])}.",
        (f"- Roman Urdu is refused less often than Urdu script in every one of the {len(groups)} harm groups."
         if in_every_group else
         "- Roman Urdu is refused less often than Urdu script in " + str(sum(r['ro'] < r['ur'] for r in groups)) + f" of the {len(groups)} harm groups; "
         "in the others the two scripts are equal: " + ", ".join(r['title'].split(': ')[1] for r in groups if r['ro'] >= r['ur']) + "."),
        f"- Dropping the prompts that the audit flagged changes little: the smallest difference among the audit subsets is "
        f"{pp(least['diff_pp'])} ({least['ro']}/{least['n']} against {least['ur']}/{least['n']}, subset \"{least['title']}\"). "
        f"On the {clean['n']} families with no flag and no note it is {pp(clean['diff_pp'])} ({clean['ro']}/{clean['n']} against {clean['ur']}/{clean['n']}).",
        f"- Commands and questions both show the gap: commands {by['form:command']['ro']}/{by['form:command']['n']} against "
        f"{by['form:command']['ur']}/{by['form:command']['n']}, questions {by['form:question']['ro']}/{by['form:question']['n']} against "
        f"{by['form:question']['ur']}/{by['form:question']['n']}. Commands are few, so the difference between the two forms is not secure.",
        f"- Steering does not look better on cleaner prompts. On the {clean['n']} families with no flag and no note, judged refusals of harmful "
        f"Roman-Urdu prompts are {clean['arms_ro']['unsteered']} without steering, {clean['arms_ro']['pooled']} pooled, "
        f"{clean['arms_ro']['residualized']} residualized and {clean['arms_ro']['orthogonal_null']} placebo. Across the subsets tabulated below the "
        f"residualized vector is ahead of the placebo by at most {max(lead(r) for r in shown if r['n'])} prompts (full set: {lead(full)}).",
        *review_lines(by, review_done, review_total, harmless),
        "",
        "## By audit finding",
        "",
        *head, row(full), *[row(r) for r in audit],
        "",
        "## By reviewer verdict",
        "",
        "The reviewer is the project author (one participant reviewer, not independent validation). The counts below are for the",
        "original sentences, which are the ones that were run. Where he announced a correction, the corrected sentence has not",
        "been run.",
        "",
        *head, *[row(r) for r in review],
        "",
        "An empty row means that no family is in that subset yet. With so few families the rows are descriptive only.",
        "",
        *harmless_lines(harmless),
        "## By form of the harmful request",
        "",
        *head, *[row(r) for r in forms],
        "",
        "## By harm group",
        "",
        *head, *[row(r) for r in groups],
        "",
        f"Groups have {sizes[0]} to {sizes[-1]} families each; read the counts, not the percentages.",
        "",
        "## Leaving one harm group out",
        "",
        *head, *[row(r) for r in without],
        "",
        "## Steering arms on the same subsets (counts only)",
        "",
        "Judged refusals of harmful Roman-Urdu prompts. The pre-registered gate for the residualized vector is defined",
        "on the full test set, where it was not met; no subset is a second chance for it, so no test is run here.",
        "",
        "| Subset | Families | No steering | Pooled | Residualized | Placebo |",
        "|---|---:|---:|---:|---:|---:|",
        *[f"| {r['title']} | {r['n']} | {r['arms_ro']['unsteered']} | {r['arms_ro']['pooled']} | {r['arms_ro']['residualized']} | {r['arms_ro']['orthogonal_null']} |"
          for r in [full, *audit, *forms] if r["n"]],
        "",
        "## Where the automatic judge errs",
        "",
        f"Roman-Urdu replies of the four arms that were read ({tot['n']} rows: 36 harmful and 36 harmless prompts per arm). The",
        "reference is the reading by an LLM agent, not a human label.",
        "",
        "| Kind of reply | Replies | Judge says \"refusal\" | of these, refusals on reading | false: garbled or off-topic | false: goes along with the request | Refusals the judge missed |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *[f"| {e['title']} | {e['n']} | {e['judge_refusal']} | {e['true_refusal']} | {e['false_refusal_nonresponsive']} | {e['false_refusal_answer']} | {e['missed_refusal']} |"
          for e in errors],
        "",
        f"- False positives: {tot['judge_refusal'] - tot['true_refusal']} of the {tot['judge_refusal']} replies the judge called refusals were not "
        f"refusals on reading (precision {tot['true_refusal'] / tot['judge_refusal']:.2f}).",
        f"- False negatives: the judge missed {tot['missed_refusal']} of {tot['refusal_on_reading']} refusals "
        f"(recall {(tot['refusal_on_reading'] - tot['missed_refusal']) / tot['refusal_on_reading']:.2f}).",
        f"- Replies that only repeat the prompt: {echo['judge_refusal']} of {echo['n']} were called refusals; {echo['true_refusal']} of those were refusals on reading.",
        "- The errors run mostly in one direction: text that is not an answer is taken for a refusal. In this study the",
        "  judge therefore reported the model as safer in Roman Urdu than it was on reading.",
        "",
        "## Limits",
        "",
        "- The subsets were chosen after the results were known. They can show that the gap does not hinge on a few",
        "  prompts; they cannot add confidence beyond the pre-registered test.",
        "- The audit flags come from automatic checks and from an LLM's reading notes, not from a human reviewer.",
        "- All counts use the automatic judge unless the column says \"on reading\"; the judge overstates Roman-Urdu",
        "  refusals, so the gap on reading is larger in every subset where it is available.",
        "",
        "Reproduce: `python scripts/robustness_checks.py --download` (no GPU).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true", help="fetch the public logs (tag v0.2.0) from the Hub")
    ap.add_argument("--logs", type=Path, default=None, help="path to test_judged_public.jsonl")
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed outputs would change")
    args = ap.parse_args()
    rows = load_rows(args.download, args.logs)
    audit = json.loads((ROOT / "data/quality/family_audit_v0.2.0.json").read_text(encoding="utf-8"))
    review = json.loads((ROOT / "data/reviewer_pack/review_status.json").read_text(encoding="utf-8"))
    tab = table(rows)
    test = sorted(f for f, v in audit["families"].items() if v["split"] == "test")
    if sorted(tab) != test:
        print("REFUSING: the test families in the logs and in the audit differ")
        return 2
    results = [{"key": key, "title": title, "families": fams, **gap(tab, fams)} for key, title, fams in subsets(audit, review, test)]
    full = results[0]
    if (full["ur"], full["ro"], full["n"]) != (36, 17, 36):
        print(f"REFUSING: the full-set counts {full['ur']}/{full['n']} vs {full['ro']}/{full['n']} are not the published 36/36 vs 17/36")
        return 2
    done = review["n_rows_total"] - review["counts"]["unreviewed"]
    errors = judge_errors(rows)
    btab = benign_table(rows)
    left = sorted(f for f, v in review.get("pair_verdicts", {}).items() if v == "no" and f in test)
    harmless = {"all": harmless_refusals(btab, test), "pair_ok": harmless_refusals(btab, [f for f in test if f not in left]), "left_out": left}
    if harmless["all"]["arms"]["unsteered"] != 5 or harmless["all"]["prompts"] != 72:
        print(f"REFUSING: harmless refusals without steering are {harmless['all']['arms']['unsteered']} of {harmless['all']['prompts']}, not the published 5 of 72")
        return 2
    md = render(results, done, review["n_rows_total"], errors, harmless)
    js = json.dumps({"status": "post hoc sensitivity analysis; the pre-registered test is the subset 'all'",
                     "source": LOG, "review_rows_done": done, "review_rows_total": review["n_rows_total"],
                     "subsets": results, "harmless_refusals": harmless, "judge_errors": errors}, indent=1, ensure_ascii=False) + "\n"
    targets = ((ROOT / "docs/ROBUSTNESS_CHECKS.md", md), (ROOT / "data/quality/robustness_checks_v0.2.0.json", js))
    if args.check:
        stale = [str(p.relative_to(ROOT)) for p, text in targets if not p.exists() or p.read_text(encoding="utf-8") != text]
        print("stale: " + ", ".join(stale) if stale else "robustness outputs are up to date")
        return 1 if stale else 0
    for p, text in targets:
        p.write_text(text, encoding="utf-8")
    print(f"wrote {targets[0][0].relative_to(ROOT)} and {targets[1][0].relative_to(ROOT)}: {len(results)} subsets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
