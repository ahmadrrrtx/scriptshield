#!/usr/bin/env python3
"""Phases 4-6 on the real model. REMOTE GPU.

  --stage dev   unsteered behaviour on calibration+dev, activation dump, SafeTune
                vectors, cross-fitted mechanism diagnostics, and the dev steering grid.
                The TEST split is never read in this stage.
  --stage test  REFUSES unless --allow-test is given AND configs/frozen_selection.json
                exists (written from dev results and committed BEFORE this run).
                Runs every arm at the frozen layer/strength on the test split.

Pipeline (each toolkit does real work, none is merely imported):
  CuratorKIT  curated the corpus this script loads (checksum-verified)
  SafeTune    extracts every contrast vector and applies every steering vector
  AuditKIT    drives every generation (ak.generate) with prompt identity verified
Judging runs afterwards in a separate kernel (scripts/run_judge.py) on the saved text.
Every attempted prompt stays in the output; nothing is filtered here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PRIMARY = ("ur", "ro")
TEST_ARMS = ("unsteered", "pooled", "residualized", "random_subspace", "orthogonal_null", "ur_only", "ro_only")


def jsonable(x):
    import numpy as np
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, Path):
        return str(x)
    return x


class Recorder:
    def __init__(self, out: Path, stage: str):
        self.out, self.t0 = out, time.time()
        out.mkdir(parents=True, exist_ok=True)
        self.report = {"kind": f"experiment_{stage}", "stage": stage, "completed": False,
                       "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sections": {}}

    def put(self, key, value):
        self.report["sections"][key] = value
        self.flush()
        print(f"[{time.time() - self.t0:6.0f}s] {key}", flush=True)

    def flush(self):
        self.report["elapsed_seconds"] = round(time.time() - self.t0, 1)
        (self.out / "run_report.json").write_text(
            json.dumps(jsonable(self.report), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["dev", "test"], required=True)
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--variant", default="fire")
    ap.add_argument("--dtype", default="float16", choices=["float16", "bfloat16", "float32"])
    ap.add_argument("--layers", default="10,14,18,22")
    ap.add_argument("--rhos", default="0.1,0.2,0.4,0.8", help="steering strength as a fraction of the "
                    "mean residual norm at the layer: alpha = rho * |h| / |v_pooled|")
    ap.add_argument("--dev-arms", default="pooled,residualized")
    ap.add_argument("--grid-only", action="store_true",
                    help="dev stage: skip the activation dump, diagnostics and unsteered baseline "
                         "(already produced by an earlier dev run) and only generate the steering grid")
    ap.add_argument("--max-new-tokens", type=int, default=64)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--skip-hash", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    rec = Recorder(out, a.stage)

    # ------------------------------------------------------------------ guards
    frozen = None
    if a.stage == "test":
        fpath = ROOT / "configs" / "frozen_selection.json"
        if not a.allow_test or not fpath.exists():
            print("REFUSING: the test stage needs --allow-test AND a committed configs/frozen_selection.json")
            return 2
        frozen = json.loads(fpath.read_text(encoding="utf-8"))

    import importlib.metadata as md

    import numpy as np
    import torch

    from scriptshield.artifacts.vector_io import save_vectors
    from scriptshield.config import load_yaml
    from scriptshield.data.schema import load_corpus
    from scriptshield.evaluation.auditkit_adapter import generate_outputs
    from scriptshield.evaluation.utility import load_utility
    from scriptshield.models import runtime as rt
    from scriptshield.steering.caa import contrast_vector, orthogonal_null_vector, script_contrast
    from scriptshield.steering.diagnostics import layer_diagnostics
    from scriptshield.steering.residualize import random_directions, residualize
    from scriptshield.steering.safetune_adapter import (
        apply_vectors, extract_contrast, extract_vectors, make_caa_config, steering_is_active)

    def ver(p):
        try:
            return md.version(p)
        except Exception:
            return None

    scfg = load_yaml(ROOT / "configs/steering.yaml")
    seed = int(scfg["seed"])
    mcfg = load_yaml(ROOT / "configs/models.yaml")["primary"]
    recs, corpus = load_corpus(ROOT)
    commit = (ROOT / "COMMIT.txt").read_text().strip() if (ROOT / "COMMIT.txt").exists() else None
    cal = [r for r in recs if r["split"] == "calibration"]
    dev = [r for r in recs if r["split"] == "dev"]
    fam_cal = sorted({r["family_id"] for r in cal})

    def pick(rs, form, label):
        """Family-ordered records for one (form, label) cell."""
        sel = {r["family_id"]: r for r in rs if r["form"] == form and r["safety_label"] == label}
        return [sel[f] for f in sorted(sel)]

    def T(rs, form, label):
        return [r["text"] for r in pick(rs, form, label)]

    # ------------------------------------------------------------------- load
    model_dir = Path(a.model_dir) if a.model_dir else rt.find_local_model_dir(variant=a.variant)
    if model_dir is None:
        print("no mounted model found under /kaggle/input")
        return 3
    integrity = None
    if not a.skip_hash:
        integrity = rt.verify_files(model_dir, mcfg["lfs_sha256"])
        if not integrity["all_match"]:
            print("REFUSING: mounted weights do not match the pinned Hugging Face LFS hashes")
            rec.put("integrity", integrity)
            return 4
    tok, tok_how = rt.load_tokenizer(model_dir)
    model = rt.load_model(model_dir, a.dtype, device_map={"": 0} if torch.cuda.is_available() else None)
    n_layers = len(rt.decoder_layers(model))
    layers = [int(x) for x in a.layers.split(",")] if a.stage == "dev" else [int(frozen["layer"])]
    rhos = [float(x) for x in a.rhos.split(",")] if a.stage == "dev" else [float(frozen["rho"])]
    rec.put("setup", {
        "code_commit": commit, "argv": sys.argv[1:], "torch": torch.__version__,
        "transformers": ver("transformers"), "safetune": ver("safetune"), "auditkit": ver("auditkit"),
        "gpus": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())],
        "model": {"hf_repo": mcfg["repo_id"], "hf_revision": mcfg["revision"],
                  "weights_source": mcfg.get("kaggle_source"), "model_dir": str(model_dir),
                  "weights_match_hf_lfs_sha256": None if integrity is None else integrity["all_match"],
                  "class": type(model).__name__, "n_layers": n_layers, "dtype": a.dtype,
                  "tokenizer_loader": tok_how},
        "corpus": {k: corpus[k] for k in ("dataset_version", "sha256", "n_records", "n_families")},
        "splits_read": ["calibration", "dev"] if a.stage == "dev" else ["calibration", "test"],
        "layers": layers, "rhos": rhos, "max_new_tokens": a.max_new_tokens, "seed": seed,
        "frozen_selection": frozen,
    })

    # ------------------------------------------------- vectors (official SafeTune)
    cfg = make_caa_config(layers, pool_method="last_token", normalize=False)
    v_form = {f: extract_vectors(model, tok, T(cal, f, "harmful"), T(cal, f, "benign"), layers,
                                 config=cfg, batch_size=a.batch_size) for f in PRIMARY}
    d_script = extract_contrast(model, tok, T(cal, "ur", "benign"), T(cal, "ro", "benign"), layers,
                                config=cfg, batch_size=a.batch_size)
    # independent capture of the same cells: cross-check + null-direction control + diagnostics
    cap = {(f, lab): rt.capture_last_token(model, tok, T(cal, f, lab), layers, batch_size=a.batch_size)
           for f in PRIMARY for lab in ("harmful", "benign")}

    def npv(t):
        return t.detach().to("cpu", torch.float64).numpy()

    cross, arms, geom = {}, {}, {}
    for L in layers:
        for f in PRIMARY:
            cross[f"harm_{f}@L{L}"] = rt.cosine(npv(v_form[f][L]),
                                                contrast_vector(cap[(f, "harmful")][L], cap[(f, "benign")][L]))
        cross[f"script@L{L}"] = rt.cosine(npv(d_script[L]), script_contrast(
            {"ur": cap[("ur", "benign")][L], "ro": cap[("ro", "benign")][L]}, "ur", "ro"))
        v_ur, v_ro, ds = npv(v_form["ur"][L]), npv(v_form["ro"][L]), npv(d_script[L])
        pooled = 0.5 * (v_ur + v_ro)                                   # equal weight per form (D-011)
        norm = float(np.linalg.norm(pooled))
        res = residualize(pooled, ds, norm_match=True)
        rnd = residualize(pooled, random_directions(pooled.shape[0], 1, seed=seed), norm_match=True)
        # D-028: control direction = the estimator's own noise, made EXACTLY orthogonal to pooled
        # (rows are family-aligned, so harmful[i] / benign[i] are matched pairs)
        null = orthogonal_null_vector(
            np.concatenate([cap[(f, "harmful")][L] for f in PRIMARY]),
            np.concatenate([cap[(f, "benign")][L] for f in PRIMARY]), pooled, seed=seed)

        def scaled(v):
            return v * (norm / max(float(np.linalg.norm(v)), 1e-12))  # dose parity with pooled

        arms[L] = {"pooled": pooled, "residualized": res["vector"], "random_subspace": rnd["vector"],
                   "orthogonal_null": scaled(null), "ur_only": scaled(v_ur), "ro_only": scaled(v_ro)}
        h_norm = float(np.mean([np.linalg.norm(cap[k][L], axis=1).mean() for k in cap]))
        geom[L] = {"norm_pooled": norm, "mean_activation_norm": h_norm,
                   "alpha_per_unit_rho": h_norm / norm,
                   "residualization": {k: res[k] for k in res if k not in ("vector", "Q")},
                   "random_subspace_removed_frac": rnd["removed_frac"],
                   "cos_to_pooled": {k: rt.cosine(v, pooled) for k, v in arms[L].items()}}
    min_cross = min(cross.values())
    rec.put("vectors", {"api": "safetune extract_caa_vectors engine (SteeringVectorExtractor), pinned 26f59e6",
                        "n_calibration_families": len(fam_cal),
                        "cross_check_vs_independent_capture": cross, "min_cosine": min_cross,
                        "geometry": geom, "arms_are_norm_matched_to_pooled": True})
    if min_cross < 0.99:
        print("ABORT: SafeTune vectors disagree with the independent capture")
        return 5
    save_vectors(out / "vectors" / f"arms_{a.stage}.npz",
                 {L * 100 + i: arms[L][name] for L in layers for i, name in enumerate(TEST_ARMS[1:])},
                 {"key_scheme": "layer*100 + arm_index", "arm_index": list(TEST_ARMS[1:]),
                  "base_model": mcfg["repo_id"], "base_model_revision": mcfg["revision"],
                  "dataset_version": corpus["dataset_version"], "dataset_sha256": corpus["sha256"],
                  "code_commit": commit, "inference_dtype": a.dtype, "stage": a.stage,
                  "geometry": jsonable(geom)})

    def alpha_for(L, rho):
        return rho * geom[L]["alpha_per_unit_rho"]

    # -------------------------------------------------------- generation / scoring
    seen_digests, identical = {}, {}
    gen_fh = (out / "generations.jsonl").open("w", encoding="utf-8")
    mar_fh = (out / "margins.jsonl").open("w", encoding="utf-8")
    timing = {}

    def wrapper_for(arm, L, rho):
        if arm == "unsteered":
            return None
        return apply_vectors(model, {L: torch.as_tensor(arms[L][arm], dtype=torch.float32)},
                             strength=alpha_for(L, rho))

    def generate(records, arm, L=None, rho=None, tag="main", max_new_tokens=None):
        """One arm through AuditKIT.generate; SafeTune steers inside the callable."""
        w = wrapper_for(arm, L, rho)
        t0 = time.time()
        rows = generate_outputs(records, lambda prompts: rt.generate_text(
            model, tok, prompts, wrapper=w, max_new_tokens=max_new_tokens or a.max_new_tokens,
            batch_size=a.batch_size), run_tag=f"{tag}:{arm}:L{L}:rho{rho}")
        # D-029 telemetry: which earlier call (if any) produced byte-identical text?
        digest = hashlib.sha256(json.dumps([[r["id"], r.get("output")] for r in rows],
                                           ensure_ascii=False).encode()).hexdigest()
        twin = seen_digests.get((tag, digest))
        seen_digests.setdefault((tag, digest), f"{arm}:L{L}:rho{rho}")
        if twin:
            identical[f"{tag}:{arm}:L{L}:rho{rho}"] = twin
            print(f"   NOTE identical text to {twin} (legitimate only for near-identical vectors)", flush=True)
        if w is not None and steering_is_active(w):
            raise RuntimeError("SafeTune hooks leaked after generation")
        for r, src in zip(rows, records):
            r.update({"arm": arm, "layer": L, "rho": rho, "alpha": None if L is None else alpha_for(L, rho),
                      "set": tag, "harm_group": src.get("harm_group")})
            gen_fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        gen_fh.flush()
        n_bad = sum(1 for r in rows if not (r.get("output") or "").strip())
        if rows and n_bad == len(rows):      # e.g. AuditKIT import failure: never "succeed" with no text
            raise RuntimeError(f"every generation failed for arm {arm}: {rows[0].get('error')}")
        timing[f"{tag}:{arm}:L{L}:rho{rho}"] = round(time.time() - t0, 1)
        print(f"   gen {tag} {arm} L={L} rho={rho}: n={len(rows)} empty/failed={n_bad} "
              f"({time.time() - t0:.0f}s)", flush=True)
        return rows

    def margins(records, arm, L=None, rho=None):
        """Teacher-forced refusal margin (continuous endpoint; no text generated)."""
        w = wrapper_for(arm, L, rho)
        m = rt.refusal_margin(w if w is not None else model, model, tok, [r["text"] for r in records])
        for i, r in enumerate(records):
            mar_fh.write(json.dumps({"arm": arm, "layer": L, "rho": rho, "id": r["id"],
                                     "family_id": r["family_id"], "form": r["form"],
                                     "safety_label": r["safety_label"], "split": r["split"],
                                     "refusal_lp": float(m["refusal_lp"][i]),
                                     "compliance_lp": float(m["compliance_lp"][i]),
                                     "margin": float(m["margin"][i])}) + "\n")
        mar_fh.flush()
        return m["margin"]

    # ===================================================================== DEV
    if a.stage == "dev":
        base_dev = [r for r in dev if r["form"] in PRIMARY]
        if not a.grid_only:
            # activation dump (calibration + dev, all four forms) for offline analysis
            scan = sorted(set(range(2, n_layers, 2)) | set(layers))
            cd = cal + dev
            acts = rt.capture_last_token(model, tok, [r["text"] for r in cd], scan, batch_size=a.batch_size)
            np.savez_compressed(out / "activations_cal_dev.npz", ids=np.array([r["id"] for r in cd]),
                                layers=np.array(scan), **{f"L{L}": acts[L].astype(np.float16) for L in scan})
            index = {r["id"]: i for i, r in enumerate(cd)}
            diag = {}
            for L in scan:
                cell = {(f, lab): acts[L][[index[r["id"]] for r in pick(cal, f, lab)]]
                        for f in PRIMARY for lab in ("harmful", "benign")}
                diag[L] = layer_diagnostics(cell, seed=seed, n_boot=1000, n_perm=5000)
            rec.put("mechanism_diagnostics", {
                "scope": "24 calibration families; cross-fitted (leave-one-family-out); not a behavioural result",
                "by_layer": diag})
            for L in scan:
                d_ = diag[L]
                print(f"   L{L:>2} |v|/|h|={d_['v_pooled_over_activation']:.3f} ro/ur={d_['norm_ratio_ro_over_ur']['value']:.2f} "
                      f"cos(ur,ro)={d_['cos_v_ur_v_ro']['value']:+.2f} align={d_['h2_script_alignment']['in_sample_abs_cosine']:.3f} "
                      f"cf={d_['h2_script_alignment']['cross_fitted_cosine']:+.3f} "
                      f"p={d_['h2_script_alignment']['cross_fitted_projection_test']['p_two_sided']:.3f}", flush=True)

            # unsteered behaviour, every form, calibration + dev
            generate(cd, "unsteered", tag="baseline")
            margins(cd, "unsteered")
            rec.put("baseline_done", {"n": len(cd), "timing": dict(timing)})

        # dev steering grid on the primary forms
        dev_arms = [x.strip() for x in a.dev_arms.split(",") if x.strip()]
        grid = []
        for L in layers:
            for rho in rhos:
                for arm in dev_arms:
                    generate(base_dev, arm, L, rho, tag="dev_grid")
                    m = margins(base_dev, arm, L, rho)
                    grid.append({"arm": arm, "layer": L, "rho": rho, "alpha": alpha_for(L, rho),
                                 "mean_margin": float(np.mean(m))})
                rec.put("dev_grid_progress", {"done": len(grid), "last": grid[-1], "timing": dict(timing)})
        rec.put("dev_grid", {"n_prompts_per_config": len(base_dev), "configs": grid,
                             "note": "selection is made AFTER judging, by the rule pre-declared in "
                                     "RESEARCH_PROTOCOL.md; this stage only generates"})

    # ==================================================================== TEST
    else:
        test = [r for r in recs if r["split"] == "test"]
        L, rho = layers[0], rhos[0]
        prim = [r for r in test if r["form"] in PRIMARY]
        util = load_utility(ROOT)
        for arm in TEST_ARMS:
            generate(test, arm, None if arm == "unsteered" else L, None if arm == "unsteered" else rho, tag="test")
            margins(prim, arm, None if arm == "unsteered" else L, None if arm == "unsteered" else rho)
            if arm in ("unsteered", "pooled", "residualized"):
                generate(util, arm, None if arm == "unsteered" else L, None if arm == "unsteered" else rho,
                         tag="utility", max_new_tokens=48)
            rec.put("test_progress", {"arms_done": TEST_ARMS[:TEST_ARMS.index(arm) + 1], "timing": dict(timing)})
        rec.put("test", {"n_test_prompts": len(test), "n_test_families": len({r["family_id"] for r in test}),
                         "arms": list(TEST_ARMS), "layer": L, "rho": rho, "alpha": alpha_for(L, rho),
                         "utility_prompts": len(util)})

    gen_fh.close()
    mar_fh.close()
    rec.report["completed"] = True
    rec.put("identical_text_between_calls", identical)
    rec.put("timing", timing)
    print("\nDONE. Text is unjudged; run scripts/run_judge.py on generations.jsonl.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
