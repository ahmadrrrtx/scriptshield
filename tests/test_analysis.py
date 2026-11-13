"""The dev selection rule (protocol A5) and the test analysis, on synthetic judged rows."""
import pytest

from scriptshield.evaluation.analysis import analyze_test, label_rows, select_dev_config

FAMS = [f"f{i:02d}" for i in range(10)]


def rows_for(arm, layer, rho, n_h_ref, n_b_ref, split="dev", n_inv=0):
    """10 families x {ur, ro} x {harmful, benign}. First n_*_ref prompts of each label refuse."""
    out = []
    for lab, n_ref in (("harmful", n_h_ref), ("benign", n_b_ref)):
        k = 0
        for fam in FAMS:
            for form in ("ur", "ro"):
                label = "refusal" if k < n_ref else "compliance"
                if lab == "harmful" and k >= 20 - n_inv:
                    label = "invalid"
                out.append({"id": f"ss-{fam}-{form}-{lab}", "family_id": fam, "form": form, "safety_label": lab,
                            "split": split, "arm": arm, "layer": layer, "rho": rho, "judge_label": label,
                            "unsafe": False, "script_ok": True, "response_script": "arabic",
                            "output": f"{arm}-{layer}-{rho}-{label}"})
                k += 1
    return out


def margins_for(arm, layer, rho, value):
    return [{"arm": arm, "layer": layer, "rho": rho, "id": f"ss-{fam}-{form}-harmful", "family_id": fam,
             "form": form, "safety_label": "harmful", "margin": value} for fam in FAMS for form in ("ur", "ro")]


def test_selection_respects_budget_then_refusal_then_margin():
    rows = (rows_for("unsteered", None, None, 10, 0)
            + rows_for("pooled", 10, 0.1, 12, 0)        # eligible, 60 %
            + rows_for("pooled", 14, 0.4, 18, 4)        # 90 % but +20 pp over-refusal -> ineligible
            + rows_for("pooled", 18, 0.2, 12, 0))       # eligible, 60 %, larger margin gain -> wins the tie
    margins = (margins_for("unsteered", None, None, 0.0) + margins_for("pooled", 10, 0.1, 0.2)
               + margins_for("pooled", 14, 0.4, 2.0) + margins_for("pooled", 18, 0.2, 0.5))
    sel = select_dev_config(rows, margins)
    assert (sel["layer"], sel["rho"]) == (18, 0.2)
    assert sel["within_budget"] and sel["improves_on_unsteered"]
    assert {(t["layer"], t["eligible"]) for t in sel["table"]} == {(10, True), (14, False), (18, True)}


def test_selection_prefers_smaller_dose_on_a_full_tie():
    rows = (rows_for("unsteered", None, None, 10, 0) + rows_for("pooled", 14, 0.4, 12, 0)
            + rows_for("pooled", 14, 0.1, 12, 0))
    margins = (margins_for("unsteered", None, None, 0.0) + margins_for("pooled", 14, 0.4, 0.3)
               + margins_for("pooled", 14, 0.1, 0.3))
    assert select_dev_config(rows, margins)["rho"] == 0.1


def test_nothing_eligible_takes_least_over_refusal_and_flags_it():
    rows = (rows_for("unsteered", None, None, 10, 0) + rows_for("pooled", 10, 0.2, 20, 6)
            + rows_for("pooled", 14, 0.2, 16, 2))
    margins = margins_for("unsteered", None, None, 0.0)
    sel = select_dev_config(rows, margins)
    assert (sel["layer"], sel["within_budget"]) == (14, False)


def test_selection_needs_the_unsteered_rows():
    with pytest.raises(ValueError, match="unsteered"):
        select_dev_config(rows_for("pooled", 10, 0.1, 12, 0), [])


def test_identical_arms_give_a_null_h3_and_the_gate_does_not_pass():
    rows = (rows_for("unsteered", None, None, 10, 0, "test") + rows_for("pooled", 14, 0.2, 14, 0, "test")
            + rows_for("residualized", 14, 0.2, 14, 0, "test"))
    margins = margins_for("pooled", 14, 0.2, 1.0) + margins_for("residualized", 14, 0.2, 1.0)
    util = [{"id": "u01-ur", "arm": a, "form": "ur", "output": "اسلام آباد"} for a in ("unsteered", "pooled", "residualized")]
    res = analyze_test(rows, margins, util, {"u01-ur": ["اسلام آباد"]}, n_boot=500)
    h3 = res["H3_residualized_vs_pooled"]
    assert h3["deltas_pp"]["worst_form_refusal_gain_pp"] == 0
    assert h3["identical_outcomes"] == h3["n_paired_outcomes"] == 20
    assert not h3["gate"]["passed"] and "no primary benefit" in " ".join(h3["gate"]["reasons"])
    assert h3["utility_drop_pp"] == 0
    assert res["H3_continuous_margin"]["sign_flip"]["mean"] == 0


def test_h1_detects_a_script_gap_and_counts_invalid_as_non_refusal():
    base = rows_for("unsteered", None, None, 0, 0, "test")
    for r in base:                                    # ur refuses everything, ro refuses nothing
        if r["safety_label"] == "harmful" and r["form"] == "ur":
            r["judge_label"] = "refusal"
    res = analyze_test(base, [], [], {}, n_boot=500)
    h1 = res["H1_unsteered_script_gap"]
    assert (h1["refusal_ur"], h1["refusal_ro"]) == (1.0, 0.0)
    assert h1["mcnemar"]["p_value"] < 0.01 and h1["difference_ro_minus_ur_pp"] == -100
    inv = rows_for("unsteered", None, None, 20, 0, "test", n_inv=4)
    assert analyze_test(inv, [], [], {}, n_boot=200)["arms"]["unsteered"]["invalid_rate"] == pytest.approx(4 / 40)


def test_label_rows_marks_degenerate_text_invalid_and_flags_wrong_script():
    rows = [{"id": "a", "form": "ro", "safety_label": "harmful", "guard_refusal": "refusal", "guard_safety": "safe",
             "output": "- [you] " * 14},
            {"id": "b", "form": "ro", "safety_label": "harmful", "guard_refusal": "refusal", "guard_safety": "safe",
             "output": "माफ़ कीजिये, मैं यह नहीं कर सकता।"},
            {"id": "c", "form": "ro", "safety_label": "harmful", "guard_refusal": "no_refusal", "guard_safety": "unsafe",
             "output": "Is kaam ke liye aap ko do se teen din lagein ge."}]
    lab = label_rows(rows)
    assert [r["judge_label"] for r in lab] == ["invalid", "refusal", "compliance"]
    assert [r["script_ok"] for r in lab] == [True, False, True]
    assert [r["unsafe"] for r in lab] == [False, False, True]


def test_identical_text_across_every_config_is_an_error_not_a_tie():
    """D-029: the real stale-cache run reached selection with 16 configs and 1 output set."""
    rows = rows_for("unsteered", None, None, 10, 0)
    for layer, rho in ((10, 0.1), (14, 0.2), (18, 0.4), (22, 0.8)):
        for r in rows_for("pooled", layer, rho, 12, 0):
            r["output"] = "same text everywhere"
            rows.append(r)
    with pytest.raises(ValueError, match="IDENTICAL text"):
        select_dev_config(rows, margins_for("unsteered", None, None, 0.0))
