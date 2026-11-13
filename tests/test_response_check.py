"""Human check of the response reading: parsing, statistics, design, and privacy of the pack."""
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from scriptshield.evaluation.response_check import ALLOCATION, cohen_kappa, parse_answers, stratum_name, summarise, weighted_rate

ROOT = Path(__file__).resolve().parents[1]
DESIGN = json.loads((ROOT / "data/response_check/sample_design.json").read_text(encoding="utf-8"))
MAPPING = ROOT / "experiments/adjudication/human_pack/mapping_PRIVATE.json"
PACK = ROOT / "experiments/adjudication/human_pack/RESPONSE_LABEL_PACK.md"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parse_answers_accepts_only_clear_lines():
    got, problems = parse_answers("T01 = R\nt02: a\nT03 n\nT04 =\nT05 = maybe\n# note\nhello\n`T06 = U`\nT07 = R (sure)\n")
    assert got == {"T01": "R", "T02": "A", "T03": "N", "T06": "U", "T07": "R"}
    assert len(problems) == 1 and "T05" in problems[0]          # reported, never guessed
    assert parse_answers("")[0] == {}


def test_blank_answers_are_never_counted():
    block = "\n".join(f"T{i:02d} = " for i in range(1, 49))
    assert parse_answers(block) == ({}, [])


def test_cohen_kappa_known_values():
    assert cohen_kappa(["R", "A", "N", "R"], ["R", "A", "N", "R"]) == 1.0
    assert abs(cohen_kappa(["R", "R", "A", "A"], ["R", "A", "R", "A"])) < 1e-12        # chance level
    assert cohen_kappa([], []) is None and cohen_kappa(["R", "R"], ["R", "R"]) is None  # undefined, not 1


def test_weighted_rate_uses_stratum_sizes_and_reports_gaps():
    items = [{"stratum": "a", "ok": True}, {"stratum": "a", "ok": False}, {"stratum": "b", "ok": True}]
    r = weighted_rate(items, {"a": 10, "b": 90, "c": 50}, lambda it: it["ok"])
    assert abs(r["value"] - (10 * 0.5 + 90 * 1.0) / 100) < 1e-12
    assert r["population"] == 100 and r["strata_without_labels"] == ["c"]


def test_summarise_counts_and_judge_precision():
    sizes = {"harmful/R/refusal": 40, "harmful/N/refusal": 10, "harmful/R/other": 10, "harmful/N/other": 40}
    def it(stratum, human):
        return {"item": "x", "stratum": stratum, "llm": stratum.split("/")[1], "judge_refusal": stratum.endswith("/refusal"), "human": human}
    items = [it("harmful/R/refusal", "R"), it("harmful/R/refusal", "R"), it("harmful/N/refusal", "N"), it("harmful/N/refusal", "R"),
             it("harmful/R/other", "R"), it("harmful/N/other", "N"), it("harmful/N/other", "U"), it("harmful/N/other", None)]
    s = summarise(items, sizes)
    assert (s["n_labelled"], s["n_cannot_judge"], s["n_open"]) == (6, 1, 1)
    assert s["agreement_raw"] == {"k": 5, "n": 6}
    # judge said refusal: 40 replies all R by the human, 10 replies half R -> (40 + 5) / 50
    assert abs(s["judge_vs_human"]["precision_weighted"] - 0.9) < 1e-12
    # human R in the population: 40 + 5 + 10 + 0 = 55, of which the judge caught 45
    assert abs(s["judge_vs_human"]["recall_weighted"] - 45 / 55) < 1e-12
    assert s["judge_vs_llm_reading_all_unique_replies"] == {"precision": 0.8, "recall": 0.8}
    empty = summarise([it("harmful/R/refusal", None)], sizes)
    assert empty["n_labelled"] == 0 and "judge_vs_human" not in empty and empty["kappa_vs_llm_reading"] is None


def test_design_matches_the_allocation_and_hides_the_labels():
    assert DESIGN["n_sample"] == sum(ALLOCATION.values()) == 48
    assert DESIGN["population"]["n"] == sum(x["population"] for x in DESIGN["strata"]) == 214
    assert {x["stratum"]: x["sampled"] for x in DESIGN["strata"]} == {stratum_name(k): v for k, v in ALLOCATION.items()}
    assert all(x["sampled"] <= x["population"] for x in DESIGN["strata"])
    assert set(DESIGN["hidden_from_the_labeller"]) == {"steering arm", "automatic judge label", "LLM reading label"}
    assert "participant" in DESIGN["labeller"]["role"] and "not independent" in DESIGN["labeller"]["role"]
    assert "items" not in DESIGN and "key" not in json.dumps(DESIGN["strata"])     # no item-level mapping in the public design


def test_report_is_rendered_from_the_committed_labels_and_claims_nothing_early():
    doc = json.loads((ROOT / "data/response_check/human_labels.json").read_text(encoding="utf-8"))
    md = load("import_response_labels").render(DESIGN, doc)
    assert md == (ROOT / "docs/HUMAN_RESPONSE_CHECK.md").read_text(encoding="utf-8")
    assert "participant check, not independent annotation" in md
    n = doc["summary"]["n_labelled"]
    assert len([i for i in doc["items"] if i["human"] in ("R", "A", "N")]) == n
    if n == 0:
        assert "No label has been returned yet" in md and "Cohen" not in md and doc["items"] == []
    for item in doc["items"]:                                       # labels and hashes only, never reply text
        assert set(item) == {"item", "stratum", "safety_label", "llm", "judge_refusal", "output_sha256", "human"}


def test_private_pack_is_ignored_by_git_and_never_tracked():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "experiments/adjudication/human_pack"], capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    assert out.stdout.strip() == ""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "experiments/adjudication/human_pack/" in text


@pytest.mark.skipif(not MAPPING.exists(), reason="the private pack is not part of the public repository")
def test_private_pack_matches_the_commitment_and_is_blind():
    text = MAPPING.read_text(encoding="utf-8")
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == DESIGN["mapping_sha256"]
    mapping = json.loads(text)
    assert len(mapping) == 48 and len({m["key"] for m in mapping}) == 48
    from collections import Counter
    assert Counter(m["stratum"] for m in mapping) == Counter({stratum_name(k): v for k, v in ALLOCATION.items()})
    pack = PACK.read_text(encoding="utf-8")
    items = pack.split("\n---\n")[1]                                 # the item blocks, between the guide and the answer block
    assert items.count("\n## T") + items.startswith("## T") + items.lstrip().startswith("## T") >= 48
    for word in ("pooled", "residualized", "orthogonal", "unsteered", "judge", "LLM", "stratum"):
        assert word not in items, word                               # nothing that reveals arm or labels
    assert pack.count(" = \n") >= 48                                 # an empty answer line per item


@pytest.mark.skipif(not MAPPING.exists(), reason="the private pack is not part of the public repository")
def test_sample_is_reproducible_from_the_seed(tmp_path, monkeypatch):
    mod = load("build_response_label_pack")
    monkeypatch.setattr(mod, "PACK", tmp_path / "pack")
    monkeypatch.setattr(mod, "PUBLIC", tmp_path / "public")
    assert mod.main() == 0
    assert (tmp_path / "pack/mapping_PRIVATE.json").read_text(encoding="utf-8") == MAPPING.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "public/sample_design.json").read_text(encoding="utf-8")) == DESIGN
