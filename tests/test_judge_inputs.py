"""The judge must be able to resolve a prompt for every row the experiment generates,
including the utility probe (its ids are not corpus ids)."""
import importlib.util
from pathlib import Path

from scriptshield.data.schema import load_corpus
from scriptshield.evaluation.utility import load_utility

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_prompt_index_covers_corpus_and_utility():
    rj = _load_script("run_judge")
    index, corpus = rj.prompt_index(ROOT)
    recs, _ = load_corpus(ROOT)
    util = load_utility(ROOT)
    assert all(index[r["id"]] == r["text"] for r in recs)
    assert all(index[u["id"]] == u["text"] for u in util)
    assert len(index) == len(recs) + len(util)
    assert corpus["dataset_version"]


def test_guard_parser_never_invents_a_verdict():
    rj = _load_script("run_judge")
    assert rj.parse_guard("Safety: Unsafe\nCategories: Violent\nRefusal: No")["guard_refusal"] == "no_refusal"
    assert rj.parse_guard("Safety: Safe\nCategories: None\nRefusal: Yes")["guard_refusal"] == "refusal"
    bad = rj.parse_guard("I think this is fine")
    assert bad["guard_refusal"] == "unknown" and bad["guard_safety"] == "unknown"
    assert rj.parse_rubric("maybe?")["rubric_label"] == "unknown"
