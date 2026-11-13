"""The hand-written public documents must agree with the computed results and with each other."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = json.loads((ROOT / "experiments/results/test_analysis/test_analysis_guard.json").read_text(encoding="utf-8"))
ADJ = json.loads((ROOT / "experiments/adjudication/test_ro_adjudication.json").read_text(encoding="utf-8"))
LINKS = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))


def pct(x):
    return f"{100 * x:.1f} %"


def _recompute_module():
    spec = importlib.util.spec_from_file_location("recompute_from_public", ROOT / "scripts/recompute_from_public.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def headline_strings():
    h1, h3 = ANALYSIS["H1_unsteered_script_gap"], ANALYSIS["H3_residualized_vs_pooled"]
    u = ADJ["arms"]["unsteered"]["harmful"]
    return [pct(h1["refusal_ur"]), pct(h1["refusal_ro"]), f"{h1['difference_ro_minus_ur_pp']:+.1f} points",
            f"{100 * h1['bootstrap']['ci_low']:+.1f} to {100 * h1['bootstrap']['ci_high']:+.1f}",
            f"p = {h1['mcnemar']['p_value']:.2g}", f"{h3['identical_outcomes']} of {h3['n_paired_outcomes']}",
            f"{100 * ADJ['judge_vs_adjudication']['guard_pre_registered']['precision']:.0f} %"], u


@pytest.mark.parametrize("doc", ["README.md", "docs/ABSTRACT.md"])
def test_headline_numbers_in_hand_written_documents_are_the_computed_ones(doc):
    text = re.sub(r"\s+", " ", (ROOT / doc).read_text(encoding="utf-8"))
    strings, u = headline_strings()
    for s in strings:
        assert s in text, f"{doc} does not contain the computed value {s!r}"
    assert not ANALYSIS["H3_residualized_vs_pooled"]["gate"]["passed"]       # both documents say the gate was not met
    assert "gate was not met" in text
    if doc == "README.md":
        assert f"{u['R']} of {u['n']}" in text


def test_readme_before_after_table_is_the_computed_one():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    arms = ANALYSIS["arms"]
    cols = ("unsteered", "pooled", "residualized")

    def row(name, values):
        return f"| {name} | " + " | ".join(values) + " |"
    for line in (
        row("Harmful requests refused, Urdu script (judge)", [pct(arms[c]["cells"]["ur/harmful"]["refusal_rate"]) for c in cols]),
        row("Harmful requests refused, Roman Urdu (judge)", [pct(arms[c]["cells"]["ro/harmful"]["refusal_rate"]) for c in cols]),
        row("Benign requests judged refused", [pct(arms[c]["over_refusal"]) for c in cols]),
        row("Invalid output", [pct(arms[c]["invalid_rate"]) for c in cols]),
        row("Utility on 48 factual questions (pattern score)", [pct(arms[c]["utility_accuracy"]) for c in cols]),
        row("Real Roman-Urdu refusals on reading (post hoc)",
            [f"{ADJ['arms'][c]['harmful']['R']} of {ADJ['arms'][c]['harmful']['n']}" for c in cols]),
    ):
        assert line in text, f"README table row is stale: expected {line!r}"


def test_public_links_are_used_consistently():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    checklist = (ROOT / "SUBMISSION_CHECKLIST.md").read_text(encoding="utf-8")
    for key in ("hf_model", "hf_dataset", "hf_space", "hf_collection_models", "hf_collection_data"):
        assert LINKS[key]["url"] in readme, f"README is missing the link {key}"
    for key in ("hf_collection_models", "hf_collection_data"):
        assert LINKS[key]["url"] in checklist
        assert LINKS[key]["url"].endswith(LINKS[key]["slug"])
    assert LINKS["github_repo"] in readme and LINKS["github_repo"] in checklist
    for key in ("hf_model", "hf_dataset", "hf_space"):
        assert LINKS[key]["url"].endswith(LINKS[key]["repo_id"])
        assert LINKS[key]["repo_id"].split("/")[0] == LINKS["author"]["hf"]


def test_abstract_is_under_500_words():
    body = (ROOT / "docs/ABSTRACT.md").read_text(encoding="utf-8").split("\n", 2)[2]
    assert len(body.split()) < 500


def test_differences_names_the_path_and_ignores_float_noise():
    d = _recompute_module().differences
    assert d({"a": 1.0, "b": [1, 2]}, {"a": 1.0 + 1e-15, "b": [1, 2]}) == []
    assert d({"a": {"x": 0.5}}, {"a": {"x": 0.6}}) == ["/a/x: 0.5 != 0.6"]
    assert d({"a": 1}, {"a": 1, "b": 2}) == ["/b: only in the published analysis"]
    assert d({"a": True}, {"a": 1.0}) != []                       # a flag is not a number
    assert d({"a": [1, 2]}, {"a": [1, 2, 3]}) != []


def test_public_logs_reproduce_the_published_analysis_when_a_release_is_built():
    """Needs release/ (not in git). Skipped in a fresh clone; `recompute_from_public.py --download` does the same."""
    logs = ROOT / "release/hf_dataset/eval_logs"
    if not (logs / "test_judged_public.jsonl").exists():
        pytest.skip("no local release folder")
    m = _recompute_module()
    from scriptshield.evaluation.utility import load_utility
    res = m.recompute(m.read_jsonl(logs / "test_judged_public.jsonl"), m.read_jsonl(logs / "test_margins.jsonl"),
                      {u["id"]: u["answer"] for u in load_utility(ROOT)})
    assert m.differences(res, {k: v for k, v in ANALYSIS.items() if k not in m.WRAPPER_KEYS}) == []
