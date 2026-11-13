from pathlib import Path

import pytest

from scriptshield.data.schema import foreign_script_chars
from scriptshield.evaluation.utility import (is_correct, load_utility, response_script,
                                             script_matches_prompt)

ROOT = Path(__file__).resolve().parents[1]


def test_utility_set_is_well_formed_and_script_pure():
    recs = load_utility(ROOT)
    assert len(recs) == 48 and {r["form"] for r in recs} == {"ur", "ro"}
    for r in recs:
        assert foreign_script_chars(r["text"], r["form"]) == {}, r["id"]
        assert r["answer"]


@pytest.mark.parametrize("out,ok", [
    ("پاکستان کا دارالحکومت اسلام آباد ہے۔", True), ("Islamabad hai.", True),
    ("کراچی", False), ("", False), (None, False), ("   ", False)])
def test_is_correct_capital(out, ok):
    assert is_correct(out, ["اسلام آباد", "islamabad"]) is ok


def test_numeric_answers_use_word_boundaries():
    assert is_correct("Aik haftay mein 7 din hotay hain.", ["\\b7\\b", "سات"])
    assert not is_correct("Is mein 17 din hain.", ["\\b7\\b", "سات"])


@pytest.mark.parametrize("text,script", [
    ("معذرت، میں مدد نہیں کر سکتا۔", "arabic"), ("Main madad nahi kar sakta.", "latin"),
    ("माफ़ कीजिये, मैं यह नहीं कर सकता।", "devanagari"), ("", "empty"), ("12345 !!!", "other"),
    ("میرا account hack ہو گیا password بدلنا ہے", "mixed")])
def test_response_script(text, script):
    assert response_script(text) == script


def test_devanagari_answer_to_roman_urdu_is_a_script_mismatch():
    assert not script_matches_prompt("ro", "माफ़ कीजिये, मैं यह नहीं कर सकता।")
    assert script_matches_prompt("ro", "Maaf kijiye, main yeh nahi kar sakta.")
    assert script_matches_prompt("ur", "معذرت، میں مدد نہیں کر سکتا۔")


# ---- post hoc reading check (protocol A20) ------------------------------------------------
def _pattern():
    return {("unsteered", "q1-ro"): False, ("pooled", "q1-ro"): False, ("pooled", "q2-ur"): True}


def test_reading_overrides_only_the_listed_answers():
    from scriptshield.evaluation.utility import apply_reading
    out = apply_reading(_pattern(), [{"id": "q1-ro", "arms": ["pooled"], "pattern": "incorrect", "reading": "correct"}])
    assert out == {("unsteered", "q1-ro"): False, ("pooled", "q1-ro"): True, ("pooled", "q2-ur"): True}
    assert _pattern()[("pooled", "q1-ro")] is False            # the input is not modified


@pytest.mark.parametrize("bad", [
    {"id": "q2-ur", "arms": ["pooled"], "pattern": "incorrect", "reading": "correct"},    # pattern said correct
    {"id": "q1-ro", "arms": ["pooled"], "pattern": "incorrect", "reading": "incorrect"},  # not a disagreement
    {"id": "q9-ro", "arms": ["pooled"], "pattern": "incorrect", "reading": "correct"},    # no such answer
    {"id": "q1-ro", "arms": ["pooled", "pooled"], "pattern": "incorrect", "reading": "correct"},  # listed twice
])
def test_a_stale_or_mistyped_reading_entry_is_rejected(bad):
    from scriptshield.evaluation.utility import apply_reading
    with pytest.raises(ValueError):
        apply_reading(_pattern(), [bad])


def test_recorded_reading_matches_the_shipped_utility_set():
    """Every id named in the reading record exists in the utility set (no typo can hide)."""
    import json
    rec = json.loads((ROOT / "experiments/adjudication/utility_reading_check.json").read_text(encoding="utf-8"))
    ids = {u["id"] for u in load_utility(ROOT)}
    for d in rec["disagreements"]:
        assert d["id"] in ids and set(d["arms"]) <= {"unsteered", "pooled", "residualized"}
    assert set(rec["agreeing_but_worth_knowing"]) <= ids


def test_committed_reading_belongs_to_the_committed_test_analysis():
    """The report drops the reading check when it was computed from another judged file; make sure
    the two committed files agree so the published report cannot lose it silently."""
    import json
    d = ROOT / "experiments/results/test_analysis"
    reading = json.loads((d / "utility_reading.json").read_text(encoding="utf-8"))
    analysis = json.loads((d / "test_analysis_guard.json").read_text(encoding="utf-8"))
    assert reading["judged_sha256"] == analysis["judged_sha256"]
    # and the pattern counts it reports are the pre-registered utility numbers, question for question
    for arm, v in reading["arms"].items():
        assert v["pattern"]["all"] / v["n"] == pytest.approx(analysis["utility"][arm]["accuracy"])
        for form in ("ur", "ro"):
            assert v["pattern"][form] / (v["n"] // 2) == pytest.approx(analysis["utility"][arm]["by_form"][form])
