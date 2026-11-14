#!/usr/bin/env python3
"""Render docs/FINAL_HF_ARTICLE.md from docs/final_article.template.md. No number is typed by hand.

Figures are referenced by URL (configs/public_links.json, "figures_base"), so that the same text renders on
GitHub and as a Hugging Face Article. Run scripts/make_figures.py and scripts/audit_dataset.py first.
"""
from __future__ import annotations

import argparse
import json
import re
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


def response_check_fields(links: dict) -> dict:
    """State of the human check of the reading (docs/HUMAN_RESPONSE_CHECK.md). Says exactly what exists, no more."""
    design = json.loads((ROOT / "data/response_check/sample_design.json").read_text(encoding="utf-8"))
    s = json.loads((ROOT / "data/response_check/human_labels.json").read_text(encoding="utf-8"))["summary"]
    url = links["github_repo"] + "/blob/main/docs/HUMAN_RESPONSE_CHECK.md"
    n, pop, done = design["n_sample"], design["population"]["n"], s["n_labelled"] + s["n_cannot_judge"]
    setup = (f"A stratified random sample of {n} of the {pop} distinct replies was drawn with a fixed seed, to be labelled by the "
             "author with the steering arm, the judge's label and the LLM's label hidden. This is a participant check, not independent annotation.")
    if s["n_labelled"] == 0:
        line = f"Not yet. {setup} No label had been returned when this text was generated; [the report]({url}) shows the current state."
        short = f"0 of {n} replies labelled so far"
    else:
        a = s["agreement_raw"]
        k = s["kappa_vs_llm_reading"]
        part = "" if s["n_open"] == 0 else f" ({s['n_open']} of {n} still open)"
        line = (f"On a sample. {setup} So far {done} of {n} are labelled{part}: the author and the LLM gave the same label on {a['k']} of {a['n']}"
                + (f" (Cohen's kappa {k:.2f})" if k is not None else "") + f". Details, including disagreements: [the report]({url}).")
        short = f"{done} of {n} replies labelled; same label as the LLM on {a['k']} of {a['n']}"
    return {"RESPONSE_CHECK_LINE": line, "RESPONSE_CHECK_SHORT": short}


def robustness_fields() -> dict:
    """Numbers of docs/ROBUSTNESS_CHECKS.md (post hoc sensitivity analysis) quoted in the threats table."""
    by = {r["key"]: r for r in json.loads((ROOT / "data/quality/robustness_checks_v0.2.0.json").read_text(encoding="utf-8"))["subsets"]}
    without = [r for k, r in by.items() if k.startswith("without:")]
    groups = [r for k, r in by.items() if k.startswith("group:")]
    nogap = [r["title"].split(": ")[1] for r in groups if r["ro"] >= r["ur"]]
    words = {0: "none", 1: "one", 2: "two", 3: "three", 4: "four"}
    clean = by["audit:clean"]
    doc = json.loads((ROOT / "data/quality/robustness_checks_v0.2.0.json").read_text(encoding="utf-8"))
    je = {e["key"]: e for e in doc["judge_errors"]}
    tot, echo = je["all"], je["echo"]
    if echo["true_refusal"] != 0 or tot["false_refusal_nonresponsive"] <= tot["false_refusal_answer"] or tot["missed_refusal"] * 2 >= tot["judge_refusal"] - tot["true_refusal"]:
        raise SystemExit("REFUSING: the template says that no repeated prompt was a refusal and that the judge's errors run mostly one way")
    return {
        "JE_N": str(tot["n"]), "JE_ECHO_N": str(echo["n"]), "JE_ECHO_REF": str(echo["judge_refusal"]), "JE_REF": str(tot["judge_refusal"]),
        "JE_FALSE": str(tot["judge_refusal"] - tot["true_refusal"]), "JE_FALSE_N": str(tot["false_refusal_nonresponsive"]),
        "JE_FALSE_A": str(tot["false_refusal_answer"]), "JE_MISSED": str(tot["missed_refusal"]), "JE_TRUE": str(tot["refusal_on_reading"]),
        "ROB_LO": f"{max(r['diff_pp'] for r in without):+.1f}", "ROB_HI": f"{min(r['diff_pp'] for r in without):+.1f}",
        "ROB_CLEAN_N": str(clean["n"]), "ROB_CLEAN_RO": str(clean["ro"]), "ROB_CLEAN_UR": str(clean["ur"]),
        "ROB_NOGAP": (f"{words.get(len(nogap), len(nogap))} of the {len(groups)} harm groups ({', '.join(nogap)}; "
                      f"{sum(r['n'] for r in groups if r['ro'] >= r['ur'])} families)") if nogap else "none of the harm groups",
    }


def review_fields(links: dict) -> dict:
    """Sentences about the author's review, from the review status, the review revision and the robustness checks."""
    sys.path.insert(0, str(ROOT / "src"))
    from scriptshield.artifacts.public_text import review_summary
    from scriptshield.data.revision import current_revision
    status = load("data/reviewer_pack/review_status.json")
    revision = current_revision(ROOT)
    rs = review_summary(status, revision)
    rob = load("data/quality/robustness_checks_v0.2.0.json")
    by = {r["key"]: r for r in rob["subsets"]}
    rev, ok, acc = by["review:reviewed"], by["review:pair_ok"], by["review:accepted"]
    harmless = rob["harmless_refusals"]
    left = harmless["left_out"]
    moved = max(harmless["all"]["arms"][a] - harmless["pair_ok"]["arms"][a] for a in harmless["all"]["arms"])
    rows = status.get("rows", {})
    same = sum(1 for r in rows.values() if r.get("same") == "yes")
    n_corr = sum(1 for r in rows.values() if r.get("correction_kind"))
    s = revision["summary"] if revision else None
    gh = links["github_repo"]
    if not rs["done"]:
        para = "No prompt pair has been reviewed yet."
        threat = "author review pending"
        pair_note = "Not reviewed yet"
        alt_note = "A second spelling has been drafted for the test families and waits for review; no result uses it yet"
    else:
        para = (f"**What the review has found so far.** {rs['findings']} "
                + (f"On the {rev['n']} reviewed test families the model refuses {rev['ro']} of {rev['n']} harmful requests in Roman Urdu and "
                   f"{rev['ur']} of {rev['n']} in Urdu script"
                   + (f"; on the {acc['n']} whose harmful request he accepted as it is, {acc['ro']} of {acc['n']} and {acc['ur']} of {acc['n']}"
                      if acc["n"] and acc["n"] != rev["n"] else "")
                   + ". These counts are for the original sentences; no corrected sentence has been run, and subsets this small only show "
                     "that the reviewed families point the same way. "
                   if rev["n"] else "")
                + f"The review is recorded per prompt pair in the review revision `v{rs['revision_id']}` of the dataset repository "
                  f"(original and revised sentence, ratings, reviewer, date, reason) and in section 9 of the "
                  f"[audit]({gh}/blob/main/docs/DATASET_QUALITY_AUDIT.md).")
        threat = (f"author review in progress: in the prompt pairs reviewed so far the two scripts mean the same in {same} of {rs['done']}"
                  + ("" if not n_corr else f"; he asked for changes to {n_corr} of them, "
                     + ("their corrected text has not been received, and every result is for the original sentences"
                        if s and s["sentences_changed"] == 0 else "and the changed sentences have not been run")))
        pairs = status.get("pair_verdicts", {})
        pair_note = (f"The reviewer rejected the pairing in {len(rs['pairs_not_comparable'])} of {len(pairs)} reviewed families"
                     + (f". Without {'it' if len(left) == 1 else 'them'} the gap is {ok['ro']} of {ok['n']} against {ok['ur']} of {ok['n']}, and "
                        + ("no count of refused harmless requests changes" if moved == 0 else f"the counts of refused harmless requests change by at most {moved}")
                        + f" ([robustness checks]({gh}/blob/main/docs/ROBUSTNESS_CHECKS.md))" if left else "")
                     + ". The calibration families, from which the vectors are computed, are not reviewed yet")
        alt_note = (f"A second spelling has been drafted for the test families; the reviewer has judged {s['alt_spelling_judged']} of them and found "
                    f"{s['alt_spelling_yes']} natural. No result uses it yet")
    return {"REVIEW_DONE": str(rs["done"]), "REVIEW_STATE": rs["state"], "REVIEW_FAMILIES": str(rs["families_done"]),
            "REVIEW_PARAGRAPH": para, "REVIEW_THREAT": threat, "PAIR_NOTE": pair_note, "ALT_NOTE": alt_note,
            "REVISION_ID": rs["revision_id"] or "none yet"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--author", default=None, help="byline; default: name and Hugging Face handle from configs/public_links.json")
    ap.add_argument("--verify-report", default="experiments/results/verify_release_v1/verify_release/verify_report.json")
    ap.add_argument("--template", default="docs/final_article.template.md")
    ap.add_argument("--out", default="docs/FINAL_HF_ARTICLE.md")
    ap.add_argument("--check", action="store_true", help="write nothing; exit code 1 if the committed article is stale")
    ap.add_argument("--checked-on", default="13 November 2026", help="date on which the marked references were checked")
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
    # The text says "more than 200 unit tests". An exact count would make the published article stale with every
    # test that is added, so the sentence is a floor and this line keeps it true.
    n_tests = sum(len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.M)) for f in sorted((ROOT / "tests").glob("test_*.py")))
    if n_tests <= 200:
        print(f"REFUSING: the article says 'more than 200 unit tests' but only {n_tests} test functions were found")
        return 2
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
        "REVISION_SHORT": rev[:8],
    }
    # ---------------------------------------------------------------- additions for the final article
    audit = load("data/quality/family_audit_v0.2.0.json")["summary"]
    fig = load("docs/figures/figure_data.json")
    ur_check = load("experiments/adjudication/ur_harmful_unsteered_check.json")
    corpus = {r["id"]: r["text"] for r in (json.loads(x) for x in (ROOT / man["path"]).read_text(encoding="utf-8").splitlines() if x.strip())}
    ro_k = {arm: t["arms"][arm]["cells"]["ro/harmful"]["refusal"] for arm in t["arms"]}
    be_k = {arm: t["arms"][arm]["cells"]["ur/benign"]["refusal"] + t["arms"][arm]["cells"]["ro/benign"]["refusal"] for arm in t["arms"]}
    lifts = [ro_k[a_] - ro_k["unsteered"] for a_ in ro_k if a_ != "unsteered"]
    align = D[L]["h2_script_alignment"]["in_sample_abs_cosine"]
    null95 = D[L]["h2_script_alignment"]["isotropic_random_null_abs_cosine"]["p95"]
    ratio_l = D[L]["norm_ratio_ro_over_ur"]["value"]
    if abs(ro_k["pooled"] - ro_k["orthogonal_null"]) > 2 or min(lifts) < 1:
        print("REFUSING: the template says the placebo did almost as well as the real vectors; no longer true:", ro_k)
        return 2
    if not (null95 < align < 0.2 and 0.4 <= ratio_l <= 0.6):
        print("REFUSING: the template describes a small but detectable script alignment and a harm signal about half as strong")
        return 2
    if any(adj["arms"][c]["benign"]["R"] for c in adj["arms"]):
        print("REFUSING: the template says no harmless prompt was really refused in the arms that were read")
        return 2
    runtimes = [int(x.replace(",", "")) for x in re.findall(r"\*\*Runtime:\*\*\s*~?([\d,]+)\s*s", (ROOT / "EXPERIMENT_LOG.md").read_text(encoding="utf-8"))]
    names = {"unsteered": "no steering", "pooled": "pooled", "residualized": "residualized", "random_subspace": "pooled with a random direction removed",
             "orthogonal_null": "placebo", "ur_only": "Urdu-only", "ro_only": "Roman-only"}
    order = [k for k in names if k in ro_k]
    layers = sorted(int(k) for k in D)

    def k_of(d):
        return f"{d['refusal_ur'] * h1['n_families']:.0f} of {h1['n_families']}", f"{d['refusal_ro'] * h1['n_families']:.0f} of {h1['n_families']}"
    sens = ["| Labels from | Decided | Urdu script | Roman Urdu | Difference |", "|---|---|---:|---:|---:|"]
    for label, when, d in (("Primary judge (Qwen3Guard)", "pre-registered", h1), ("Second judge (Qwen2.5-7B with a fixed rubric)", "pre-declared", rub["H1_unsteered_script_gap"]),
                           ("Primary judge, replies that repeat the prompt counted as invalid", "post hoc", echo["H1_unsteered_script_gap"])):
        a_ur, a_ro = k_of(d)
        sens.append(f"| {label} | {when} | {a_ur} ({pct(d['refusal_ur'])}) | {a_ro} ({pct(d['refusal_ro'])}) | {d['difference_ro_minus_ur_pp']:+.1f} points |")
    sens.append(f"| Replies read one by one (LLM agent, not a human) | post hoc | {ur_check['explicit_refusal']} of {ur_check['n']} "
                f"({pct(ur_check['explicit_refusal'] / ur_check['n'])}) | {u['R']} of {u['n']} ({pct(u['R'] / u['n'])}) | "
                f"{100 * (u['R'] / u['n'] - ur_check['explicit_refusal'] / ur_check['n']):+.1f} points |")
    gap = {x["form"]: x for x in fig["script_gap"]["judge"]}
    rd = fig["roman_urdu_outcomes_reading"]
    verify = json.loads(vp.read_text(encoding="utf-8"))["verify"]["arms"] if vp.exists() else {}
    log_rows = [json.loads(x) for x in (ROOT / "release/hf_dataset/eval_logs/test_judged_public.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (ROOT / "release/hf_dataset/eval_logs/test_judged_public.jsonl").exists() else []
    rep.update({
        "FIG": links["figures_base"], "CHECKED_ON": a.checked_on,
        "H1_UR_K": f"{h1['refusal_ur'] * h1['n_families']:.0f}", "H1_RO_K": f"{h1['refusal_ro'] * h1['n_families']:.0f}",
        "ALIGN_L": f"{align:.2f}", "NULL_L": f"{null95:.2f}", "COS_UR_RO": f"{D[L]['cos_v_ur_v_ro']['value']:.2f}",
        "VERIFY_K": str(sum(x["identical"] for x in verify.values())), "VERIFY_N": str(sum(x["n"] for x in verify.values())),
        **robustness_fields(), **response_check_fields(links),
        **review_fields(links),
        "EXAMPLE_EN": corpus["ss-wifi_crack-en-benign"], "EXAMPLE_UR": corpus["ss-wifi_crack-ur-benign"], "EXAMPLE_RO": corpus["ss-wifi_crack-ro-benign"],
        "AUDIT_CMD_H": str(audit["speech_act_counts"]["harmful"].get("command", 0)), "AUDIT_CMD_B": str(audit["speech_act_counts"]["benign"].get("command", 0)),
        "AUDIT_CTX_H": str(audit["context_sentence_counts"]["harmful"]), "AUDIT_CTX_B": str(audit["context_sentence_counts"]["benign"]),
        "AUDIT_WORD": str(audit["n_word_differs_between_scripts"]), "H1_SENSITIVITY_TABLE": "\n".join(sens),
        "LIFT_MIN": str(min(lifts)), "LIFT_MAX": str(max(lifts)),
        "WITHHELD": f"{sum(bool(r['withheld']) for r in log_rows):,}", "PUBLIC_ROWS": f"{len(log_rows):,}",
        "SAFETUNE_COMMIT": load("release/hf_model/manifest.json")["toolkits"]["safetune_commit"],
        "GPU_RUNS": str(len(runtimes)), "GPU_HOURS": f"{sum(runtimes) / 3600:.1f}",
        "ALT_GAP": ("Bar chart. Share of " + str(h1["n_families"]) + " harmful requests refused by Tiny Aya Fire without steering: Urdu script "
                    f"{gap['ur']['refused']} of {gap['ur']['n']}, Roman Urdu {gap['ro']['refused']} of {gap['ro']['n']} "
                    f"({fig['script_gap']['reading_roman_urdu_refusals']} of {gap['ro']['n']} after reading the replies), code-mixed "
                    f"{gap['cm']['refused']} of {gap['cm']['n']}, English {gap['en']['refused']} of {gap['en']['n']}."),
        "ALT_MECH": (f"Two line charts across layers {layers[0]} to {layers[-1]}. Left: the ratio of the Roman-Urdu to the Urdu-script harm signal is "
                     f"{D[str(layers[0])]['norm_ratio_ro_over_ur']['value']:.2f} at layer {layers[0]} and {ratio_l:.2f} at layer {L}. Right: the absolute cosine "
                     f"between the refusal direction and the script direction is at most "
                     f"{max(D[str(k)]['h2_script_alignment']['in_sample_abs_cosine'] for k in layers):.2f} at any layer."),
        "ALT_ARMS": ("Two horizontal bar charts over seven arms. Left, harmful Roman-Urdu requests refused out of 36: "
                     + ", ".join(f"{names[k]} {ro_k[k]}" for k in order) + ". Right, harmless requests refused out of 72: "
                     + ", ".join(f"{names[k]} {be_k[k]}" for k in order) + "."),
        "ALT_OUTCOMES": ("Stacked bars for four arms showing what the model wrote in reply to 36 harmful Roman-Urdu requests, as refuse / go along / neither: "
                         + "; ".join(f"{names[k]} {rd[k]['R']} / {rd[k]['A']} / {rd[k]['N']}" for k in rd) + "."),
    })
    if not log_rows or not verify:
        print("REFUSING: the final article needs the local release folder and the verification report")
        return 2
    text = (ROOT / a.template).read_text(encoding="utf-8")
    for k, v in rep.items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{\w+\}\}", text)
    if left:
        print("REFUSING: unfilled placeholders:", sorted(set(left)))
        return 2
    if a.check:
        current = (ROOT / a.out).read_text(encoding="utf-8") if (ROOT / a.out).exists() else ""
        if current != text:
            print(f"stale: {a.out} is not what this script produces from the template and the result files; run `make article`")
            return 1
        print(f"{a.out} is up to date")
        return 0
    (ROOT / a.out).write_text(text, encoding="utf-8")
    print(f"wrote {a.out}: {len(text.split())} words, {n_tests} test functions, verification: {'included' if vp.exists() else 'pending'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
