"""The post hoc robustness checks: the committed report matches its JSON, and the subset logic is right."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("robustness_checks", ROOT / "scripts/robustness_checks.py")
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)

DOC = json.loads((ROOT / "data/quality/robustness_checks_v0.2.0.json").read_text(encoding="utf-8"))


def test_report_is_rendered_from_the_committed_json():
    md = rc.render(DOC["subsets"], DOC["review_rows_done"], DOC["review_rows_total"], DOC["judge_errors"])
    assert md == (ROOT / "docs/ROBUSTNESS_CHECKS.md").read_text(encoding="utf-8")


def test_full_set_is_the_preregistered_comparison():
    full = DOC["subsets"][0]
    assert full["key"] == "all" and (full["n"], full["ur"], full["ro"]) == (36, 36, 17)
    assert abs(full["p"] - 3.8e-06) < 1e-07
    assert full["arms_ro"] == {"unsteered": 17, "pooled": 22, "residualized": 23, "orthogonal_null": 21}


def test_groups_partition_the_test_set():
    groups = [s for s in DOC["subsets"] if s["key"].startswith("group:")]
    fams = [f for s in groups for f in s["families"]]
    assert len(fams) == len(set(fams)) == 36
    assert sum(s["ro"] for s in groups) == 17 and sum(s["ur"] for s in groups) == 36
    for s in (x for x in DOC["subsets"] if x["key"].startswith("without:")):
        g = next(x for x in groups if x["key"] == "group:" + s["key"].split(":")[1])
        assert s["n"] + g["n"] == 36 and s["ro"] + g["ro"] == 17


def test_judge_error_table_matches_the_published_precision_and_recall():
    tot = DOC["judge_errors"][-1]
    assert tot["n"] == 288 and tot["judge_refusal"] == 108 and tot["true_refusal"] == 57
    assert tot["false_refusal_nonresponsive"] + tot["false_refusal_answer"] == 51
    assert round(tot["true_refusal"] / tot["judge_refusal"], 2) == 0.53
    assert round((tot["refusal_on_reading"] - tot["missed_refusal"]) / tot["refusal_on_reading"], 2) == 0.86
    parts = DOC["judge_errors"][:-1]
    for k in ("n", "judge_refusal", "true_refusal", "missed_refusal"):
        assert sum(p[k] for p in parts) == tot[k]


def _toy():
    def fam(group, command=False, notes=(), flags=()):
        return {"split": "test", "harm_group": group, "speech_act": {"harmful": {"is_command": command}},
                "llm_notes": [{"label": "harmful", "type": t} for t in notes],
                "automatic_flags": [{"label": "harmful", "type": t} for t in flags]}
    audit = {"families": {"a": fam("x"), "b": fam("x", command=True, notes=("register",)), "c": fam("y", flags=("word_differs_between_scripts",))}}

    def cells(ur, ro, read):
        return {arm: {"ur": {"judge": ur, "read": None}, "ro": {"judge": ro, "read": read}} for arm in rc.ARMS}
    tab = {"a": cells(1, 0, 0), "b": cells(1, 1, 0), "c": cells(1, 0, 0)}
    return audit, tab


def test_subsets_follow_flags_notes_and_review():
    audit, tab = _toy()
    review = {"rows": {"a-harmful": {"status": "accepted"}, "b-harmful": {"status": "corrected"}, "a-benign": {"status": "accepted"}}}
    subs = {key: fams for key, _, fams in rc.subsets(audit, review, ["a", "b", "c"])}
    assert subs["all"] == ["a", "b", "c"]
    assert subs["form:command"] == ["b"] and subs["form:question"] == ["a", "c"]
    assert subs["audit:no_register"] == ["a", "c"] and subs["audit:no_word_flag"] == ["a", "b"] and subs["audit:clean"] == ["a"]
    assert subs["review:accepted"] == ["a"] and subs["review:reviewed"] == ["a", "b"]
    g = rc.gap(tab, subs["all"])
    assert (g["n"], g["ur"], g["ro"], g["ro_read"]) == (3, 3, 1, 0) and g["diff_pp"] == -66.7
    assert rc.gap(tab, [])["n"] == 0


def test_script_states_that_it_is_post_hoc():
    md = (ROOT / "docs/ROBUSTNESS_CHECKS.md").read_text(encoding="utf-8")
    assert "post hoc sensitivity analysis" in md and "not a human" in md and "no subset is a second chance" in md
