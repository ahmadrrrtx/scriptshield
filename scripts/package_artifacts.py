#!/usr/bin/env python3
"""Assemble the public release from real run outputs. Local, no GPU, no network.

  release/hf_model/     steering-vector package  (Hugging Face model repo)
  release/hf_dataset/   corpus + reviewer pack + redacted evaluation logs  (dataset repo)
  release/demo/         replay data for the demo (recorded outputs, no live model)
  release/verify/       expected-output file used by the release verification kernel

Nothing is uploaded here. Every number in the cards is read from the analysis JSON.
Response text that must not be public is withheld (D-030) and the folder is scanned.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.artifacts.linkcheck import unresolved_relative_links  # noqa: E402
from scriptshield.artifacts.release import (ARM_DESCRIPTIONS, WITHHELD, assert_nothing_leaks, attach_reading,  # noqa: E402
                                            public_row, repack_vectors, save_npz_deterministic, sha256_array,
                                            sha256_file, sha256_text, write_jsonl, write_sums)
from scriptshield.artifacts.public_text import alt_arms, alt_gap, placebo_did_almost_as_well, review_summary  # noqa: E402
from scriptshield.config import load_yaml  # noqa: E402
from scriptshield.data.schema import load_corpus  # noqa: E402
from scriptshield.evaluation.analysis import label_rows  # noqa: E402
from scriptshield.evaluation.utility import load_utility  # noqa: E402

ARMS = ("pooled", "residualized", "random_subspace", "orthogonal_null", "ur_only", "ro_only")
VERIFY_ARMS = ("unsteered", "pooled", "residualized")
# Verification set = the utility probe: 48 harmless factual questions, logged for these three arms in the
# frozen test run (same order, batches of 8, 48 new tokens). Harmless on both sides, so the public model
# repository carries no harmful prompt and every expected response can be shown in full.
VERIFY_SET, VERIFY_MAX_NEW_TOKENS = "utility", 48
PACKAGE_VERSION = "0.2.0"


def read_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def git_head() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def section(md: str, start: str, stop_prefix: str = "## ") -> str:
    """Body of the markdown section whose heading starts with ``start`` (heading excluded)."""
    lines, out, on = md.splitlines(), [], False
    for ln in lines:
        if ln.startswith(start):
            on = True
            continue
        if on and ln.startswith(stop_prefix):
            break
        if on:
            out.append(ln)
    return "\n".join(out).strip()


def leak_scan(out: Path, labelled: list[dict], prompts: list[str], width: int = 40, step: int = 20) -> dict:
    """Search every text file of the release for windows of text that occur only in withheld responses."""
    released = "\n".join(prompts + [r.get("output") or "" for r in labelled if not public_row(r)["withheld"]])
    withheld = sorted({r.get("output") or "" for r in labelled if public_row(r)["withheld"]})
    windows = {}
    for text in withheld:
        for i in range(0, max(1, len(text) - width + 1), step):
            w = text[i:i + width]
            if len(w.strip()) >= 30 and w not in released:
                windows.setdefault(w, text)
    files = [f for f in sorted(out.rglob("*")) if f.is_file() and f.suffix in (".json", ".jsonl", ".md", ".html", ".txt", ".yaml", ".csv")]
    blobs = {}
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        blobs[str(f.relative_to(out))] = raw + "\n" + raw.replace("\\n", "\n").replace('\\"', '"').replace("<\\/", "</")
    everything = "\n".join(blobs.values())
    leaks = []
    for w in windows:
        if w in everything:
            leaks += [(name, w[:24] + "...") for name, blob in blobs.items() if w in blob]
    return {"files_scanned": len(files), "withheld_texts": len(withheld),
            "withheld_texts_with_unique_content": len(set(windows.values())), "unique_windows_checked": len(windows),
            "window_chars": width, "leaks": leaks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-run", required=True, help="folder with run_report.json, generations/margins, vectors/")
    ap.add_argument("--judged", required=True, help="judged.jsonl of the test stage")
    ap.add_argument("--analysis-dir", default="experiments/results/test_analysis")
    ap.add_argument("--dev-analysis", default="experiments/results/dev_analysis/dev_analysis.json")
    ap.add_argument("--results-md", default="docs/RESULTS.md")
    ap.add_argument("--verify-report", default=None, help="report.json written by the release verification kernel")
    ap.add_argument("--out", default="release")
    a = ap.parse_args()
    out = ROOT / a.out
    run = ROOT / a.test_run
    for sub in ("hf_model", "hf_dataset", "hf_space", "demo", "verify"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
        (out / sub).mkdir(parents=True)

    report = json.loads((run / "run_report.json").read_text(encoding="utf-8"))
    S = report["sections"]
    if not report.get("completed"):
        print("REFUSING: the test run did not complete")
        return 2
    frozen = json.loads((ROOT / "configs/frozen_selection.json").read_text(encoding="utf-8"))
    L = int(frozen["layer"])
    if S["test"]["layer"] != L or abs(S["test"]["rho"] - frozen["rho"]) > 1e-12:
        print("REFUSING: the test run did not use the frozen selection")
        return 2
    mcfg = load_yaml(ROOT / "configs/models.yaml")["primary"]
    recs, corpus = load_corpus(ROOT)
    by_id = {r["id"]: r for r in recs}
    n_utility = len(load_utility(ROOT))
    analysis = json.loads((ROOT / a.analysis_dir / "test_analysis_guard.json").read_text(encoding="utf-8"))
    results_md = (ROOT / a.results_md).read_text(encoding="utf-8")
    verify = json.loads((ROOT / a.verify_report).read_text(encoding="utf-8")) if a.verify_report else None
    head = git_head()
    links = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))
    author = f"{links['author']['name']} ([@{links['author']['hf']}](https://huggingface.co/{links['author']['hf']}))"
    link_fields = {"{{URL_GITHUB}}": links["github_repo"], "{{URL_ARTICLE}}": links["article_in_repo"],
                   "{{URL_RESULTS}}": links["results_in_repo"], "{{URL_HACKATHON}}": links["hackathon"],
                   "{{URL_MODEL}}": links["hf_model"]["url"], "{{ID_MODEL}}": links["hf_model"]["repo_id"],
                   "{{URL_DATASET}}": links["hf_dataset"]["url"], "{{ID_DATASET}}": links["hf_dataset"]["repo_id"],
                   "{{URL_SPACE}}": links["hf_space"]["url"], "{{ID_SPACE}}": links["hf_space"]["repo_id"],
                   "{{URL_COLLECTION_MODELS}}": links["hf_collection_models"]["url"],
                   "{{TITLE_COLLECTION_MODELS}}": links["hf_collection_models"]["title"],
                   "{{URL_COLLECTION_DATA}}": links["hf_collection_data"]["url"],
                   "{{TITLE_COLLECTION_DATA}}": links["hf_collection_data"]["title"],
                   "{{AUTHOR}}": author, "{{AUTHOR_NAME}}": links["author"]["name"]}
    # the report numbers the judge sub-sections 5.1-5.3; inside a card they are plain sub-headings
    validity = re.sub(r"(?m)^### 5\.\d+ ", "### ", section(results_md, "## 5. "))

    # ------------------------------------------------------------ labelled + public rows
    raw = read_jsonl(ROOT / a.judged)
    labelled = label_rows(raw, "guard")
    adj_path = ROOT / "experiments/adjudication/test_ro_rows.jsonl"
    # attach the reading (R/A/N) where one exists (Roman Urdu, 4 arms) and, for every harmful Roman-Urdu
    # row, whether its exact text was read as an unambiguous refusal (the only case in which it is public)
    n_adjudicated = attach_reading(labelled, read_jsonl(adj_path) if adj_path.exists() else [])
    pub = [public_row(r) for r in labelled]
    assert_nothing_leaks(pub)
    order = [r["id"] for r in raw if r.get("set") == "test" and r["arm"] == "unsteered"]   # generation order
    if len(order) != S["test"]["n_test_prompts"]:
        print("REFUSING: judged file does not contain the full unsteered test call")
        return 2

    # --------------------------------------------------------------------- hf_model
    m = out / "hf_model"
    run_manifest = json.loads((run / "vectors/arms_test.manifest.json").read_text(encoding="utf-8"))
    vectors = repack_vectors(run / "vectors/arms_test.npz", run_manifest, L, list(ARMS))
    save_npz_deterministic(m / "steering_vectors.npz", vectors)
    geom = S["vectors"]["geometry"][str(L)]
    manifest = {
        "artifact_type": "scriptshield_steering_vectors", "package_version": PACKAGE_VERSION,
        "vector_file": "steering_vectors.npz", "format": "npz, one float64 array per arm",
        "orientation": "harmful_minus_benign",
        "application": "h_L <- h_L + alpha * v, added to the OUTPUT of decoder block `layer` (0-based) at every "
                       "token position, through SafeTune CAAModel forward hooks",
        "layer": L, "rho": frozen["rho"], "alpha": S["test"]["alpha"],
        "alpha_definition": "alpha = rho * mean_activation_norm / norm_pooled  (dose as a fraction of the "
                            "residual-stream norm at this layer)",
        "hidden_dim": int(next(iter(vectors.values())).shape[0]),
        "mean_activation_norm": geom["mean_activation_norm"], "norm_pooled": geom["norm_pooled"],
        "arms": {name: {"description": ARM_DESCRIPTIONS[name], "sha256": sha256_array(v),
                        "norm": float(np.linalg.norm(v)), "cos_to_pooled": geom["cos_to_pooled"][name]}
                 for name, v in vectors.items()},
        "residualization": geom["residualization"],
        "base_model": {"hf_repo": mcfg["repo_id"], "hf_revision": mcfg["revision"],
                       "weights_source_used": mcfg.get("kaggle_source"),
                       "weights_sha256": mcfg["lfs_sha256"], "included_in_package": False},
        "extraction": {"method": "contrastive activation addition: mean(harmful) - mean(benign) at the last prompt "
                                 "token, per form; pooled = equal-weight mean of the Urdu-script and Roman-Urdu vectors",
                       "engine": S["vectors"]["api"], "n_calibration_families": S["vectors"]["n_calibration_families"],
                       "forms": ["ur", "ro"], "min_cosine_vs_independent_capture": S["vectors"]["min_cosine"]},
        "selection": {"rule": frozen["rule"], "selected_on_arm": frozen["selected_on_arm"],
                      "dev_families": 12, "dev_judged_sha256": frozen["dev_judged_sha256"],
                      "selected_row": frozen["selected_row"], "unsteered_dev": frozen["unsteered_dev"]},
        "inference": {"dtype": S["setup"]["model"]["dtype"], "decoding": "greedy", "batch_size": 8,
                      "max_new_tokens": S["setup"]["max_new_tokens"], "padding_side": "left",
                      "chat_template": "model default (one user turn; the template injects its own preamble)",
                      "tokenise_rendered_prompt_with_add_special_tokens": False},
        "dataset": S["setup"]["corpus"],
        "toolkits": {"safetune": S["setup"]["safetune"], "auditkit": S["setup"]["auditkit"],
                     "safetune_commit": "26f59e6d1bdcacafe5f2be3b8d982fb214369659",
                     "torch": S["setup"]["torch"], "transformers": S["setup"]["transformers"]},
        "produced_by": {"code_commit_of_test_run": S["setup"]["code_commit"], "hardware": S["setup"]["gpus"]},
        "license_note": "Derived from Cohere Labs Tiny Aya weights (CC-BY-NC 4.0 + Cohere Labs Acceptable Use "
                        "Policy). Non-commercial research use. Base weights are not included.",
    }
    (m / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "configs/frozen_selection.json", m / "frozen_selection.json")
    shutil.copyfile(ROOT / "artifacts/steering_package/apply_steering.py", m / "apply_steering.py")
    shutil.copyfile(ROOT / "artifacts/steering_package/check_base_model.py", m / "check_base_model.py")

    # expected outputs: the utility probe of the logged run, per arm, in generation order
    pub_key = {(r["set"], r["arm"], r["id"]): r for r in pub}
    util_text = {u["id"]: u["text"] for u in load_utility(ROOT)}
    v_order = [r["id"] for r in raw if r.get("set") == VERIFY_SET and r["arm"] == "unsteered"]
    if v_order != list(util_text):
        print("REFUSING: the logged utility call is not in the order of the utility file")
        return 2
    expected = []
    for arm in VERIFY_ARMS:
        for i, rid in enumerate(v_order):
            pr = pub_key[(VERIFY_SET, arm, rid)]
            if pr["withheld"]:
                print(f"REFUSING: a verification response would be withheld ({arm}, {rid})")
                return 2
            expected.append({"index": i, "id": rid, "arm": arm, "prompt": util_text[rid],
                             "max_new_tokens": VERIFY_MAX_NEW_TOKENS, "output_sha256": pr["output_sha256"],
                             "output_chars": pr["output_chars"], "output": pr["output"]})
    write_jsonl(m / "expected_outputs.jsonl", expected)
    write_jsonl(out / "verify" / "expected_outputs.jsonl", expected)

    # --------------------------------------------------------------------- hf_dataset
    d = out / "hf_dataset"
    (d / "data").mkdir()
    shutil.copyfile(ROOT / corpus["path"], d / "data" / Path(corpus["path"]).name)
    for split in ("calibration", "dev", "test"):
        write_jsonl(d / "data" / f"{split}.jsonl", [r for r in recs if r["split"] == split])
    shutil.copyfile(ROOT / "data/utility/utility_v0.1.yaml", d / "data" / "utility_v0.1.yaml")
    shutil.copyfile(ROOT / f"data/manifests/scriptshield_{corpus['dataset_version']}.json", d / "manifest.json")
    # Working files of the review stay in the code repository: the reviewer's raw messages, the sheet and batches
    # (they carry unreviewed spelling candidates) and proposed corrections. Unapproved text does not enter the dataset.
    shutil.copytree(ROOT / "data/reviewer_pack", d / "reviewer_pack", ignore=shutil.ignore_patterns(
        "returns", "AHMAD_REVIEW.csv", "AHMAD_REVIEW_BATCH_*.md", "proposed_revisions.jsonl"))
    (d / "figures").mkdir()
    for f in sorted((ROOT / "docs/figures").glob("*")):
        shutil.copyfile(f, d / "figures" / f.name)
    (d / "quality").mkdir()
    for f in sorted((ROOT / "data/quality").glob("*.json")):
        shutil.copyfile(f, d / "quality" / f.name)
    # The two documents are written for the code repository. In the dataset repository the folders are laid out
    # differently, so their relative links are rewritten and a line says where the named scripts and paths live.
    ds_url = links["hf_dataset"]["url"]
    relink = {"](../data/quality/": f"]({ds_url}/blob/main/quality/",
              "](../data/reviewer_pack/)": f"]({ds_url}/tree/main/reviewer_pack)",
              "](../data/reviewer_pack/": f"]({ds_url}/blob/main/reviewer_pack/"}
    for name in ("DATASET_QUALITY_AUDIT.md", "ROBUSTNESS_CHECKS.md"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        for old, new in relink.items():
            text = text.replace(old, new)
        title, rest = text.split("\n", 1)
        note = (f"\n> Copy of [`docs/{name}`]({links['github_repo']}/blob/main/docs/{name}) from the code repository. "
                f"Scripts and file paths named in the text (`scripts/...`, `data/...`, `docs/...`) are in that repository; "
                f"in this dataset repository the audit data is under `quality/` and the review pack under `reviewer_pack/`.\n")
        (d / "quality" / name).write_text(title + "\n" + note + rest, encoding="utf-8")
    logs = d / "eval_logs"
    logs.mkdir()
    write_jsonl(logs / "test_judged_public.jsonl", [r for r in pub if r.get("set") in ("test", "utility")])
    shutil.copyfile(run / "margins.jsonl", logs / "test_margins.jsonl")
    for f in sorted((ROOT / a.analysis_dir).glob("test_analysis_*.json")) + [ROOT / a.analysis_dir / "utility_reading.json"]:
        if f.exists():
            shutil.copyfile(f, logs / f.name)
    if (ROOT / a.dev_analysis).exists():
        shutil.copyfile(ROOT / a.dev_analysis, logs / "dev_analysis.json")
    (logs / "test_run_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    adj_dir = logs / "adjudication"
    adj_dir.mkdir()
    for f in ("RUBRIC.md", "test_ro_labels.json", "test_ro_borderline.json", "test_ro_adjudication.json",
              "test_ro_rows.jsonl", "ur_harmful_unsteered_check.json", "utility_reading_check.json"):
        if (ROOT / "experiments/adjudication" / f).exists():
            shutil.copyfile(ROOT / "experiments/adjudication" / f, adj_dir / f)
    for f in sorted((ROOT / "experiments/results/devx_analysis").glob("*.json")):
        shutil.copyfile(f, logs / f.name)
    for extra in ("experiments/results/fire_dev_v2/fire_dev/run_report.json",
                  "experiments/results/fire_smoke_v1/fire_smoke/smoke_report.json",
                  "experiments/judge_validation/agreement_smoke_baseline.json"):
        if (ROOT / extra).exists():
            name = {"run_report.json": "dev_run_report.json"}.get(Path(extra).name, Path(extra).name)
            shutil.copyfile(ROOT / extra, logs / name)

    # --------------------------------------------------------------------- demo data
    fams = sorted({by_id[i]["family_id"] for i in order})
    demo = {"note": "Recorded outputs of the frozen test run. No model runs in this demo. Response text is withheld "
                    "where the prompt is harmful and the response is not a clean refusal; for Roman-Urdu prompts it is "
                    "shown only where that response was read and found to be a refusal.",
            "links": [["Research article", links.get("hf_article") or links["article_in_repo"], "the full write-up, with figures and limitations"],
                      ["GitHub repository", links["github_repo"], "code, protocol, decision records, tests"],
                      ["Dataset and evaluation logs", links["hf_dataset"]["url"], "prompts, logs, quality audit, review status"],
                      ["Steering vectors (model artifact)", links["hf_model"]["url"], "vectors, manifest, loader; not a fine-tuned model"],
                      ["Collection: model artifacts", links["hf_collection_models"]["url"], "steering vectors and this explorer"],
                      ["Collection: data artifacts", links["hf_collection_data"]["url"], "dataset with evaluation logs"],
                      ["Full result tables", links["results_in_repo"], "every table, generated from the logs"],
                      ["Dataset quality audit", links["audit_in_repo"], "family-level findings and review status"],
                      ["Robustness checks", links["github_repo"] + "/blob/main/docs/ROBUSTNESS_CHECKS.md", "the gap on subsets of the test set; where the judge errs"]],
            "footer": (f"{links['author']['name']} (@{links['author']['hf']}), solo submission to the Lexsi AI Safety and Alignment Hackathon. "
                       "Built with substantial help from an AI assistant. Labels come from a model judge and from an LLM agent's reading, "
                       "not from human annotators. Recorded outputs: CC BY-NC 4.0; Tiny Aya Fire is subject to the Cohere Labs Acceptable Use Policy."),
            "layer": L, "rho": frozen["rho"], "arms": ["unsteered", *ARMS], "arm_descriptions": ARM_DESCRIPTIONS,
            "reading": (json.loads((ROOT / "experiments/adjudication/test_ro_adjudication.json").read_text(encoding="utf-8"))["arms"]
                        if (ROOT / "experiments/adjudication/test_ro_adjudication.json").exists() else None),
            "summary": {arm: {"cells": {k: {x: v[x] for x in ("n", "refusal_rate", "unsafe_rate", "invalid_rate")}
                                        for k, v in analysis["arms"][arm]["cells"].items()},
                              "utility_accuracy": analysis["arms"][arm]["utility_accuracy"]}
                        for arm in analysis["arms"]},
            "families": []}
    h1s, h3s = analysis["H1_unsteered_script_gap"], analysis["H3_residualized_vs_pooled"]
    adj_doc = json.loads((ROOT / "experiments/adjudication/test_ro_adjudication.json").read_text(encoding="utf-8"))
    mech = json.loads((ROOT / "experiments/results/fire_dev_v2/fire_dev/run_report.json").read_text(encoding="utf-8"))[
        "sections"]["mechanism_diagnostics"]["by_layer"][str(L)]
    review = review_summary(json.loads((ROOT / "data/reviewer_pack/review_status.json").read_text(encoding="utf-8")))
    va_ = (verify or {}).get("verify", {}).get("arms", {})
    gaps = {arm: v["cells"]["ur/harmful"]["refusal"] - v["cells"]["ro/harmful"]["refusal"] for arm, v in analysis["arms"].items()}
    ru = adj_doc["arms"]["unsteered"]["harmful"]
    if h3s["gate"]["passed"] or not placebo_did_almost_as_well(analysis) or min(gaps.values()) < 0.5 * gaps["unsteered"] \
            or ru["N"] <= ru["A"] or any(v["benign"]["R"] for v in adj_doc["arms"].values()):
        print("REFUSING: fixed sentences of the explorer (gate failed, placebo, gap not closed, non-refusals mostly garbled, no real "
              "refusal of harmless prompts) no longer describe the data")
        return 2
    demo["stats"] = {
        "h1": {"n": h1s["n_families"], "ur_k": round(h1s["refusal_ur"] * h1s["n_families"]), "ro_k": round(h1s["refusal_ro"] * h1s["n_families"]),
               "diff_pp": round(h1s["difference_ro_minus_ur_pp"], 1), "ci_low_pp": round(100 * h1s["bootstrap"]["ci_low"], 1),
               "ci_high_pp": round(100 * h1s["bootstrap"]["ci_high"], 1), "p": f"{h1s['mcnemar']['p_value']:.2g}"},
        "h3": {"same": h3s["identical_outcomes"], "n": h3s["n_paired_outcomes"], "gate_passed": bool(h3s["gate"]["passed"])},
        "judge": {"precision": adj_doc["judge_vs_adjudication"]["guard_pre_registered"]["precision"]},
        "mechanism": {"norm_ratio": mech["norm_ratio_ro_over_ur"]["value"], "abs_cos": mech["h2_script_alignment"]["in_sample_abs_cosine"]},
        "rows": len(pub), "withheld": int(sum(r["withheld"] for r in pub)),
        "review": {"reviewed": review["done"], "total": review["total"]},
        "verify": {"k": sum(v["identical"] for v in va_.values()), "n": sum(v["n"] for v in va_.values())},
        "corpus": {"families": len({r["family_id"] for r in recs}), "records": len(recs),
                   "split": " / ".join(str(len({r["family_id"] for r in recs if r["split"] == sp})) for sp in ("calibration", "dev", "test"))},
    }
    for fam in fams:
        entry = {"family_id": fam, "harm_group": None, "prompts": {}, "meaning": {}, "responses": {}}
        for r in recs:
            if r["family_id"] != fam:
                continue
            entry["harm_group"] = r.get("harm_group")
            entry["prompts"].setdefault(r["safety_label"], {})[r["form"]] = r["text"]
            entry["meaning"][r["safety_label"]] = r.get("intended_meaning_en")
            for arm in demo["arms"]:
                p = pub_key.get(("test", arm, r["id"]))
                if p:
                    entry["responses"].setdefault(arm, {}).setdefault(r["safety_label"], {})[r["form"]] = {
                        "label": p["judge_label"], "unsafe": bool(p.get("unsafe")), "script": p.get("response_script"),
                        "read_as": p.get("adjudicated"), "echo": bool(p.get("is_echo")),
                        "text": p["output"], "chars": p["output_chars"], "withheld": p["withheld"]}
        demo["families"].append(entry)
    (out / "demo" / "replay_data.json").write_text(json.dumps(demo, ensure_ascii=False) + "\n", encoding="utf-8")
    tpl = (ROOT / "demo/template.html").read_text(encoding="utf-8")
    if "/*__DATA__*/" not in tpl:
        print("REFUSING: demo/template.html has no data placeholder")
        return 2
    (out / "demo" / "index.html").write_text(
        tpl.replace("/*__DATA__*/", json.dumps(demo, ensure_ascii=False).replace("</", "<\\/")), encoding="utf-8")

    # --------------------------------------------------------------- hf_space (static: no runtime to break)
    sp = out / "hf_space"
    shutil.copyfile(out / "demo" / "index.html", sp / "index.html")
    (sp / "README.md").write_text(
        "---\ntitle: ScriptShield Recorded Experiment Explorer\nemoji: 🛡️\ncolorFrom: blue\ncolorTo: gray\nsdk: static\n"
        "app_file: index.html\npinned: false\nlicense: cc-by-nc-4.0\n"
        "short_description: Urdu vs Roman Urdu safety in Tiny Aya Fire (replay)\n"
        f"datasets:\n- {links['hf_dataset']['repo_id']}\nmodels:\n- {links['hf_model']['repo_id']}\n---\n\n"
        "# ScriptShield: recorded experiment explorer\n\n"
        "**Evaluating Urdu and Roman Urdu safety behaviour in Cohere Tiny Aya Fire.** The page shows the research overview, "
        "the measured results as charts, and the recorded replies of the frozen test run: for each request, one row per "
        "written form (Urdu script, Roman Urdu, English, code-mixed) with the unsteered model and each steering vector "
        "side by side.\n\n"
        "**No model runs here.** This is a replay of logged outputs: live inference would need a GPU and access to a gated "
        "model. Every number on the page is computed from the embedded logs. Reply text is withheld wherever a harmful "
        "prompt received anything other than a clean refusal.\n\n"
        "Labels come from a model judge and from an LLM agent's reading, not from human annotators. The steering "
        "intervention did not pass its pre-registered gate; the page says so.\n\n"
        f"- Research article: {links.get('hf_article') or links['article_in_repo']}\n"
        f"- Collections: [model artifacts]({links['hf_collection_models']['url']}) · [data artifacts]({links['hf_collection_data']['url']})\n"
        f"- Dataset and evaluation logs: [`{links['hf_dataset']['repo_id']}`]({links['hf_dataset']['url']})\n"
        f"- Steering vectors: [`{links['hf_model']['repo_id']}`]({links['hf_model']['url']})\n"
        f"- Code, protocol and write-up: [{links['github_repo']}]({links['github_repo']})\n\n"
        f"Author: {author}. Built for the [Lexsi AI Safety and Alignment Hackathon]({links['hackathon']}).\n",
        encoding="utf-8")

    # ------------------------------------------------------------------------- cards
    h1, h3 = analysis["H1_unsteered_script_gap"], analysis.get("H3_residualized_vs_pooled")
    n_withheld = sum(r["withheld"] for r in pub if r.get("set") == "test")
    if verify:
        core = ("steering_vectors.npz", "manifest.json", "apply_steering.py", "expected_outputs.jsonl")
        stale = [f for f in core if verify.get("package_files", {}).get(f) != sha256_file(m / f)]
        if stale or not verify.get("passed"):
            print(f"REFUSING: the verification report is not a pass for this exact package (differs: {stale}, "
                  f"passed={verify.get('passed')})")
            return 2
        va = verify["verify"]["arms"]
        per_arm = ", ".join(f"{k} {v['identical']}/{v['n']}" for k, v in va.items())
        ver_line = (f"Verified in a fresh GPU session ({verify.get('hardware', 'GPU')}): this package alone (loader + "
                    f"vectors, no ScriptShield code importable) reproduced **{sum(v['identical'] for v in va.values())}"
                    f"/{sum(v['n'] for v in va.values())}** logged outputs byte-for-byte ({per_arm}).")
    else:
        ver_line = "**Not yet verified in a clean environment.**"
    gate = "PASSED" if (h3 and h3["gate"]["passed"]) else "NOT MET"
    dev_an = json.loads((ROOT / a.dev_analysis).read_text(encoding="utf-8"))
    by = {(t["layer"], t["rho"]): t["benign_refusal"] for t in dev_an["selection"]["table"]}
    steps = [100 * (by[(layer, 0.2)] - by[(layer, 0.1)]) for layer in sorted({k[0] for k in by})
             if (layer, 0.1) in by and (layer, 0.2) in by]
    dose_cost = f"{min(steps):.0f} to {max(steps):.0f}"
    audit = json.loads((ROOT / "data/quality/family_audit_v0.2.0.json").read_text(encoding="utf-8"))["summary"]
    build_date = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--date=short", "--format=%ad"], capture_output=True, text=True).stdout.strip()
    core_files = ("steering_vectors.npz", "manifest.json", "apply_steering.py", "expected_outputs.jsonl")
    inspect_out = f"{manifest['layer']} {manifest['hidden_dim']} {round(manifest['alpha'], 4)} {sorted(manifest['arms'])}"
    by_split = {sp: [r for r in recs if r["split"] == sp] for sp in ("calibration", "dev", "test")}
    split_table = "\n".join(["| Split | Families | Prompts | Harmful | Harmless | Role |", "|---|---:|---:|---:|---:|---|"] + [
        f"| `{sp}` | {len({r['family_id'] for r in rows_})} | {len(rows_)} | {sum(r['safety_label'] == 'harmful' for r in rows_)} | "
        f"{sum(r['safety_label'] == 'benign' for r in rows_)} | {role} |"
        for (sp, rows_), role in zip(by_split.items(), ("computing steering vectors", "choosing layer and strength", "the final measurement, run once"))])
    form_table = "\n".join(["| Written form | Code | Prompts | Harmful | Harmless |", "|---|---|---:|---:|---:|"] + [
        f"| {name} | `{code}` | {sum(r['form'] == code for r in recs)} | {sum(r['form'] == code and r['safety_label'] == 'harmful' for r in recs)} | "
        f"{sum(r['form'] == code and r['safety_label'] == 'benign' for r in recs)} |"
        for code, name in (("ur", "Urdu, Perso-Arabic script"), ("ro", "Roman Urdu"), ("cm", "Code-mixed Urdu-English"), ("en", "English (reference)"))])
    by_rob = {r["key"]: r for r in json.loads((ROOT / "data/quality/robustness_checks_v0.2.0.json").read_text(encoding="utf-8"))["subsets"]}
    wo = [r["diff_pp"] for k, r in by_rob.items() if k.startswith("without:")]
    rob = {"ROB_LO": f"{max(wo):+.1f}", "ROB_HI": f"{min(wo):+.1f}", "ROB_CLEAN_N": str(by_rob["audit:clean"]["n"]),
           "ROB_CLEAN_RO": str(by_rob["audit:clean"]["ro"]), "ROB_CLEAN_UR": str(by_rob["audit:clean"]["ur"])}
    extra_fields = {
        "{{FIG}}": links["figures_base"], "{{URL_AUDIT}}": links["audit_in_repo"], "{{BUILD_DATE}}": build_date,
        "{{ALT_GAP}}": alt_gap(analysis, ru["R"]), "{{ALT_ARMS}}": alt_arms(analysis),
        "{{REVIEW_BLOCK}}": review["block"], "{{REVIEW_LINE}}": review["line"],
        "{{AUDIT_CMD_H}}": str(audit["speech_act_counts"]["harmful"].get("command", 0)),
        "{{AUDIT_CMD_B}}": str(audit["speech_act_counts"]["benign"].get("command", 0)),
        "{{AUDIT_CTX_H}}": str(audit["context_sentence_counts"]["harmful"]), "{{AUDIT_CTX_B}}": str(audit["context_sentence_counts"]["benign"]),
        "{{AUDIT_WORD}}": str(audit["n_word_differs_between_scripts"]), "{{AUDIT_SPELL}}": str(len(audit["roman_spelling_variants"])),
        "{{AUDIT_DUP}}": str(audit["exact_duplicate_texts"]), "{{AUDIT_REGISTER}}": str(audit["llm_note_counts"].get("register", 0)),
        "{{SPLIT_TABLE}}": split_table, "{{FORM_TABLE}}": form_table,
        "{{ROB_LO}}": rob["ROB_LO"], "{{ROB_HI}}": rob["ROB_HI"], "{{ROB_CLEAN_N}}": rob["ROB_CLEAN_N"],
        "{{ROB_CLEAN_RO}}": rob["ROB_CLEAN_RO"], "{{ROB_CLEAN_UR}}": rob["ROB_CLEAN_UR"],
        "{{EXAMPLE_HARMFUL_EN}}": next(r["text"] for r in recs if r["id"] == "ss-exam_cheat-en-harmful"),
        "{{INSPECT_OUTPUT}}": inspect_out, "{{N_EXPECTED}}": str(len(expected)),
        "{{CORE_SUMS}}": "\n".join(["| File | sha256 |", "|---|---|"] + [f"| `{f}` | `{sha256_file(m / f)}` |" for f in core_files]),
    }
    link_fields.update(extra_fields)
    card = (ROOT / "artifacts/steering_package/MODEL_CARD.template.md").read_text(encoding="utf-8")
    card = (card.replace("{{LAYER}}", str(L)).replace("{{RHO}}", str(frozen["rho"]))
            .replace("{{ALPHA}}", f"{S['test']['alpha']:.4f}").replace("{{REVISION}}", mcfg["revision"])
            .replace("{{N_CAL}}", str(S["vectors"]["n_calibration_families"]))
            .replace("{{N_TEST}}", str(analysis["n_test_families"])).replace("{{GATE}}", gate)
            .replace("{{DOSE_COST}}", dose_cost)
            .replace("{{H3_INTERPRETATION}}", h3["interpretation"] if h3 else "n/a")
            .replace("{{VERIFY_LINE}}", ver_line).replace("{{CODE_COMMIT}}", S["setup"]["code_commit"])
            .replace("{{RESULTS_BRIEF}}", section(results_md, "## Findings in brief"))
            .replace("{{RESULTS_VALIDITY}}", validity)
            .replace("{{RESULTS_CLAIMS}}", section(results_md, "## 10. "))
            .replace("{{RESULTS_H1}}", section(results_md, "## 1. "))
            .replace("{{RESULTS_ARMS}}", section(results_md, "## 2. "))
            .replace("{{RESULTS_H3}}", section(results_md, "## 3. "))
            .replace("{{RESULTS_VS_UNSTEERED}}", section(results_md, "## 4. "))
            .replace("{{ARM_TABLE}}", "\n".join(
                f"| `{k}` | {v['description']} | {v['cos_to_pooled']:+.4f} |" for k, v in manifest["arms"].items())))
    for k, v in link_fields.items():
        card = card.replace(k, v)
    (m / "README.md").write_text(card, encoding="utf-8")
    dcard = (ROOT / "data/DATASET_CARD.template.md").read_text(encoding="utf-8")
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    dcard = (dcard.replace("{{VERSION}}", corpus["dataset_version"]).replace("{{SHA256}}", corpus["sha256"])
             .replace("{{N_RECORDS}}", str(man["n_records"])).replace("{{N_FAMILIES}}", str(man["n_families"]))
             .replace("{{HARM_GROUPS}}", ", ".join(f"{k} {v}" for k, v in sorted(man["by_harm_group"].items())))
             .replace("{{H1_UR}}", f"{100 * h1['refusal_ur']:.1f}").replace("{{H1_RO}}", f"{100 * h1['refusal_ro']:.1f}")
             .replace("{{H1_N}}", str(h1["n_families"])).replace("{{H1_P}}", f"{h1['mcnemar']['p_value']:.2g}")
             .replace("{{N_WITHHELD}}", str(n_withheld))
             .replace("{{N_TEST_ROWS}}", str(sum(1 for r in pub if r.get("set") == "test")))
             .replace("{{RESULTS_H1}}", section(results_md, "## 1. "))
             .replace("{{RESULTS_VALIDITY}}", validity.replace("\n### ", "\n#### "))
             .replace("{{N_ADJ}}", str(n_adjudicated)))
    for k, v in link_fields.items():
        dcard = dcard.replace(k, v)
    (d / "README.md").write_text(dcard, encoding="utf-8")
    for f in (m / "README.md", d / "README.md"):
        left = re.findall(r"\{\{[A-Z0-9_]+\}\}", f.read_text(encoding="utf-8"))
        if left:
            print(f"REFUSING: unfilled placeholders in {f}: {left[:5]}")
            return 2

    # ----------------------------------------------------------- relative links resolve inside each release folder
    for sub in ("hf_model", "hf_dataset", "hf_space"):
        dead = unresolved_relative_links(out / sub)
        if dead:
            print(f"REFUSING: relative links in release/{sub} point at nothing: {dead[:6]}")
            return 4

    # ----------------------------------------------------------- leak scan + checksums
    # Rule: text that exists ONLY in withheld responses must not appear anywhere in the release.
    # (Released text - prompts, refusals, benign answers - is public by definition, and a withheld
    # response often shares its opening with a released one, e.g. an echo of the prompt.)
    scan = leak_scan(out, labelled, [r["text"] for r in recs] + [u["text"] for u in load_utility(ROOT)])
    if scan["leaks"]:
        print("REFUSING: text unique to withheld responses found in the release:", scan["leaks"][:5])
        return 3
    sums = {sub: write_sums(out / sub) for sub in ("hf_model", "hf_dataset", "hf_space", "demo")}
    summary = {"packaged_at_commit": head, "test_run_commit": S["setup"]["code_commit"], "layer": L, "rho": frozen["rho"],
               "adjudicated_rows_attached": n_adjudicated,
               "files": {k: len(v) for k, v in sums.items()},
               "public_rows": len(pub), "withheld_rows": int(sum(r["withheld"] for r in pub)),
               "utility_prompts": n_utility,
               "leak_scan": {k: v for k, v in scan.items() if k != "leaks"} | {"leaks": 0},
               "vector_sha256": {k: v["sha256"] for k, v in manifest["arms"].items()},
               "verify_report_included": bool(verify), "expected_outputs": len(expected),
               "dataset_sha256": sha256_file(d / "data" / Path(corpus["path"]).name),
               "withheld_marker": WITHHELD, "empty_text_sha256": sha256_text("")}
    (out / "RELEASE_SUMMARY.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
