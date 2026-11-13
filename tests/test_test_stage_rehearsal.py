"""End-to-end REHEARSAL of the test-stage file flow with a stub model and a stub judge.

Everything here is SYNTHETIC and lives in a temp dir. Its only purpose is to prove that
the files written by the GPU stage (schema of generations/margins), the judge output and
`analyze.py test` + `make_report.py` fit together BEFORE GPU time is spent on the real
frozen test set. No number produced here is a result.
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("auditkit")

from scriptshield.data.schema import load_corpus                                  # noqa: E402
from scriptshield.evaluation.auditkit_adapter import generate_outputs             # noqa: E402
from scriptshield.evaluation.utility import load_utility                          # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("unsteered", "pooled", "residualized", "random_subspace", "orthogonal_null", "ur_only", "ro_only")
PRIMARY = ("ur", "ro")


def stub_model(arm, rng):
    def fn(prompts):
        outs = []
        for p in prompts:
            x = rng.random()
            if x < 0.03:
                outs.append("")                                   # empty -> invalid
            elif x < 0.06:
                outs.append("ha " * 40)                           # repetition loop -> invalid
            elif x < (0.45 if arm == "unsteered" else 0.6):
                outs.append("معذرت، میں اس میں مدد نہیں کر سکتا۔")
            else:
                outs.append(f"SYNTHETIC answer from {arm}: Islamabad 1947 " + p[:20])
        return outs
    return fn


def stub_judge(row):
    out = row.get("output") or ""
    if not out.strip():
        return {"guard_refusal": "invalid", "guard_safety": "unknown", "is_empty": True}
    refused = "نہیں کر سکتا" in out or out.startswith("ha ")     # the real guard also calls loops refusals (D-026)
    return {"guard_refusal": "refusal" if refused else "no_refusal",
            "guard_safety": "safe" if refused or row["safety_label"] == "benign" else "unsafe",
            "rubric_label": "refusal" if refused else "compliance", "is_empty": False}


def test_test_stage_files_flow_into_analysis_and_report(tmp_path):
    rng = random.Random(7)
    recs, _ = load_corpus(ROOT)
    test = [r for r in recs if r["split"] == "test"]
    prim = [r for r in test if r["form"] in PRIMARY]
    util = load_utility(ROOT)
    assert len(test) == 288 and len({r["family_id"] for r in test}) == 36

    gens, margins = [], []
    for arm in ARMS:
        L, rho = (None, None) if arm == "unsteered" else (14, 0.4)
        plan = [(test, "test")] + ([(util, "utility")] if arm in ("unsteered", "pooled", "residualized") else [])
        for records, tag in plan:
            rows = generate_outputs(records, stub_model(arm, rng), run_tag=f"{tag}:{arm}")
            assert len(rows) == len(records)
            for r, src in zip(rows, records):
                r.update({"arm": arm, "layer": L, "rho": rho, "alpha": None if L is None else 1.8,
                          "set": tag, "harm_group": src.get("harm_group")})
                gens.append(r)
        for r in prim:
            margins.append({"arm": arm, "layer": L, "rho": rho, "id": r["id"], "family_id": r["family_id"],
                            "form": r["form"], "safety_label": r["safety_label"], "split": r["split"],
                            "refusal_lp": -1.0, "compliance_lp": -2.0, "margin": rng.gauss(1.0, 0.5)})
    assert len(gens) == 7 * 288 + 3 * len(util)

    # the judge must find a prompt for every generated row, utility included
    spec = __import__("importlib.util").util.spec_from_file_location("run_judge", ROOT / "scripts/run_judge.py")
    rj = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(rj)
    index, _ = rj.prompt_index(ROOT)
    assert all(g["id"] in index for g in gens)

    judged = [{**g, "prompt": index[g["id"]], **stub_judge(g)} for g in gens]
    jp, mp = tmp_path / "judged.jsonl", tmp_path / "margins.jsonl"
    jp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in judged) + "\n", encoding="utf-8")
    mp.write_text("\n".join(json.dumps(r) for r in margins) + "\n", encoding="utf-8")

    for judge in ("guard", "rubric"):
        run = subprocess.run([sys.executable, str(ROOT / "scripts/analyze.py"), "test", "--judged", str(jp),
                              "--margins", str(mp), "--out", str(tmp_path / "an"), "--judge", judge],
                             capture_output=True, text=True)
        assert run.returncode == 0, run.stdout[-1500:] + run.stderr[-3000:]
    res = json.loads((tmp_path / "an" / "test_analysis_guard.json").read_text(encoding="utf-8"))
    assert res["n_test_families"] == 36 and set(res["arms"]) == set(ARMS)
    for arm in ARMS:                                   # every attempted prompt stays in the denominator
        cells = res["arms"][arm]["cells"]
        assert all(cells[f"{f}/{lab}"]["n"] == 36 for f in PRIMARY for lab in ("harmful", "benign"))
        assert res["arms"][arm]["invalid_rate"] > 0     # empty + degenerate rows were NOT dropped or called refusals
    assert res["arms"]["pooled"]["utility_accuracy"] is not None
    assert "H1_unsteered_script_gap" in res and "H3_residualized_vs_pooled" in res
    assert len(res["holm"]["tests"]) == 3
    sec = res["secondary_each_arm_vs_unsteered_paired"]
    assert set(sec) == set(ARMS) - {"unsteered"}
    cell = sec["pooled"]["ro/harmful"]
    assert cell["n_families"] == 36 and cell["bootstrap"]["ci_low"] <= cell["diff_pp"] / 100 <= cell["bootstrap"]["ci_high"]

    out_md = tmp_path / "RESULTS.md"
    run = subprocess.run([sys.executable, str(ROOT / "scripts/make_report.py"),
                          "--test", str(tmp_path / "an" / "test_analysis_guard.json"),
                          "--test-rubric", str(tmp_path / "an" / "test_analysis_rubric.json"),
                          "--out", str(out_md)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr[-3000:]
    text = out_md.read_text(encoding="utf-8")
    assert "H3" in text and "Gate" in text and "nan" not in text.lower().replace("n/a", "")
