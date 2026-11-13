#!/usr/bin/env python3
"""EIGHT-STEP smoke test on the REAL model. REMOTE GPU ONLY.

Approved Change 2: this chain must pass BEFORE the corpus is scaled or any large
job is launched. The run aborts at the first failed step, so a later step can
never be reported as passing on top of a broken earlier one.

  1 model loads (provenance hashed; numerics validated against a float32 reference)
  2 architecture + chat template verified
  3 activations captured at the documented layer/position (+ padding invariance)
  4 CAA vectors extracted with the official SafeTune API, cross-checked by hand
  5 direction verified empirically (teacher-forced dose-response SIGN TEST)
  6 SafeTune applies the pooled and the residualized vector during generation
  7 measurable behaviour change
  8 vector saved / reloaded / behaviour reproduced

Everything here runs on calibration + dev prompts only. The test split is never
touched. Results are smoke-scale and are NOT a test of H1/H2/H3.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class SmokeAbort(SystemExit):
    pass


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


class Smoke:
    def __init__(self, out: Path):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.report = {"kind": "model_smoke", "is_hypothesis_test": False,
                       "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "all_steps_passed": False, "info": {}, "steps": [], "extras": {}}
        self.t0 = time.time()

    def flush(self):
        self.report["elapsed_seconds"] = round(time.time() - self.t0, 1)
        (self.out / "smoke_report.json").write_text(
            json.dumps(jsonable(self.report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def info(self, key, value):
        self.report["info"][key] = value
        self.flush()

    def extra(self, key, value):
        self.report["extras"][key] = value
        self.flush()

    def record(self, n: int, name: str, ok: bool, detail: dict):
        self.report["steps"].append({"step": n, "name": name, "passed": bool(ok), "detail": detail,
                                     "t_seconds": round(time.time() - self.t0, 1)})
        self.flush()
        print(f"\n[{'PASS' if ok else 'FAIL'}] step {n}: {name}  (t={time.time() - self.t0:.0f}s)", flush=True)
        print(json.dumps(jsonable(detail), indent=1, ensure_ascii=False)[:3500], flush=True)
        if not ok:
            raise SmokeAbort(f"smoke test aborted at step {n}: {name}")

    def fail(self, n: int, name: str, exc: BaseException):
        self.record(n, name, False, {"error": f"{type(exc).__name__}: {exc}",
                                     "traceback": traceback.format_exc()[-2500:]})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=None, help="default: discover a mounted model under /kaggle/input")
    ap.add_argument("--variant", default="fire")
    ap.add_argument("--out", default=str(ROOT / "artifacts/smoke"))
    ap.add_argument("--layers", default="8,14,20,26")
    ap.add_argument("--alphas", default="2,4,8")
    ap.add_argument("--sign-alpha", type=float, default=4.0)
    ap.add_argument("--max-new-tokens", type=int, default=48)
    ap.add_argument("--dtype", default="auto", choices=["auto", "float16", "bfloat16", "float32"])
    ap.add_argument("--skip-hash", action="store_true")
    ap.add_argument("--no-extras", action="store_true")
    args = ap.parse_args()
    s = Smoke(Path(args.out))

    import importlib.metadata as md

    import numpy as np
    import torch
    import transformers

    from scriptshield.artifacts.vector_io import load_vectors, save_vectors
    from scriptshield.config import load_yaml
    from scriptshield.data.schema import load_corpus
    from scriptshield.evaluation.labels import classify_refusal
    from scriptshield.models import runtime as rt
    from scriptshield.steering.caa import contrast_vector, script_contrast
    from scriptshield.steering.safetune_adapter import (
        apply_vectors, extract_contrast, extract_vectors, make_caa_config,
        steering_is_active, transform_vector_dict)

    def ver(pkg):
        try:
            return md.version(pkg)
        except Exception:
            return None

    n_gpu = torch.cuda.device_count()
    commit = (ROOT / "COMMIT.txt").read_text().strip() if (ROOT / "COMMIT.txt").exists() else None
    s.info("environment", {
        "python": sys.version.split()[0], "torch": torch.__version__,
        "transformers": transformers.__version__, "safetune": ver("safetune"),
        "tokenizers": ver("tokenizers"), "accelerate": ver("accelerate"), "numpy": np.__version__,
        "cuda": torch.cuda.is_available(),
        "gpus": [torch.cuda.get_device_name(i) for i in range(n_gpu)],
        "compute_capability": [list(torch.cuda.get_device_capability(i)) for i in range(n_gpu)],
        "code_commit": commit, "argv": sys.argv[1:],
    })
    recs, corpus = load_corpus(ROOT)
    s.info("corpus", {k: corpus[k] for k in ("dataset_version", "sha256", "n_records", "n_families")})
    mcfg = load_yaml(ROOT / "configs/models.yaml")["primary"]
    cal = [r for r in recs if r["split"] == "calibration"]
    dev = [r for r in recs if r["split"] == "dev"]

    def texts(rs, form, label):
        return [r["text"] for r in rs if r["form"] == form and r["safety_label"] == label]

    def to_np(t):
        return t.detach().to("cpu", torch.float64).numpy()

    def label_counts(outs):
        return dict(Counter(classify_refusal(o).label for o in outs))

    # ------------------------------------------------------------------ 1. load
    try:
        model_dir = Path(args.model_dir) if args.model_dir else rt.find_local_model_dir(variant=args.variant)
        if model_dir is None:
            raise FileNotFoundError("no mounted cohere2 model found under /kaggle/input "
                                    "(kernel must attach cohere-labs/tiny-aya/transformers/fire/1)")
        prov = {"model_dir": str(model_dir), "declared_source": mcfg.get("kaggle_source"),
                "hf_repo": mcfg["repo_id"], "hf_revision_pinned": mcfg["revision"],
                "files": {p.name: p.stat().st_size for p in sorted(model_dir.iterdir()) if p.is_file()}}
        cfg_json = json.loads((model_dir / "config.json").read_text())
        prov["config"] = {k: cfg_json.get(k) for k in (
            "architectures", "model_type", "num_hidden_layers", "hidden_size", "num_attention_heads",
            "vocab_size", "torch_dtype", "transformers_version", "sliding_window", "eos_token_id")}
        if not args.skip_hash:
            th = time.time()
            prov["integrity"] = rt.verify_files(model_dir, mcfg["lfs_sha256"])
            prov["integrity"]["seconds"] = round(time.time() - th, 1)
            prov["integrity"]["meaning"] = ("all_match=true: weights and tokenizer are byte-identical to "
                                            "the Hugging Face LFS objects at the pinned revision")
        tok, tok_how = rt.load_tokenizer(model_dir)
        probe = [t for f in ("ur", "ro", "en", "cm") for t in
                 (texts(cal, f, "harmful")[:1] + texts(cal, f, "benign")[:1])]
        dtype_log, model, chosen, ref_logits = [], None, None, None

        if args.dtype != "auto":
            model = rt.load_model(model_dir, args.dtype, device_map={"": 0} if n_gpu else None)
            chosen = args.dtype
        elif n_gpu == 0:
            model = rt.load_model(model_dir, "float32")
            chosen = "float32"
        else:
            mm = {i: "13GiB" for i in range(n_gpu)}
            mm["cpu"] = "24GiB"
            tr = time.time()
            try:   # float32 REFERENCE across all GPUs: exact numerics for bf16-stored weights
                m32 = rt.load_model(model_dir, "float32", device_map="auto", max_memory=mm)
                t_load = time.time() - tr
                ref_logits = rt.last_token_logits(m32, m32, tok, probe, batch_size=2)
                ref_stats = rt.layer_stats(m32, tok, probe[:4], batch_size=2)
                dtype_log.append({"dtype": "float32", "role": "reference", "load_seconds": round(t_load, 1),
                                  "devices": sorted({str(v) for v in getattr(m32, "hf_device_map", {}).values()}),
                                  "all_finite": all(x["finite_real_tokens"] for x in ref_stats),
                                  "max_abs_activation": max(x["max_abs_real_tokens"] for x in ref_stats),
                                  "layer_of_max": max(ref_stats, key=lambda x: x["max_abs_real_tokens"])["layer"],
                                  "gpu_memory": rt.gpu_memory()})
                s.info("reference_layer_stats_float32", ref_stats)
                del m32
                rt.release_memory()
            except Exception as e:
                dtype_log.append({"dtype": "float32", "role": "reference",
                                  "error": f"{type(e).__name__}: {str(e)[:300]}"})
                rt.release_memory()
            for cand in ("float16", "bfloat16"):
                tc = time.time()
                try:
                    try:
                        m = rt.load_model(model_dir, cand, device_map={"": 0})
                    except Exception as first:      # e.g. reference not fully released: spread over GPUs
                        print(f"  single-GPU load of {cand} failed ({type(first).__name__}); retrying on all GPUs", flush=True)
                        rt.release_memory()
                        m = rt.load_model(model_dir, cand, device_map="auto", max_memory=mm)
                    t_load = time.time() - tc
                    tf = time.time()
                    lg = rt.last_token_logits(m, m, tok, probe, batch_size=4)
                    t_fwd = time.time() - tf
                    st = rt.layer_stats(m, tok, probe[:4], batch_size=4)
                    cmp = (rt.compare_logits(ref_logits, lg) if ref_logits is not None
                           else {"finite": bool(np.isfinite(lg).all()), "note": "no reference available"})
                    ok, why = rt.dtype_acceptable(cmp, st)
                    dtype_log.append({"dtype": cand, "role": "candidate", "accepted": ok, "reason": why,
                                      "load_seconds": round(t_load, 1), "probe_forward_seconds": round(t_fwd, 2),
                                      "vs_float32_reference": cmp,
                                      "max_abs_activation": max(x["max_abs_real_tokens"] for x in st),
                                      "float16_overflow_limit": 65504, "gpu_memory": rt.gpu_memory()})
                    if ok:
                        model, chosen = m, cand
                        break
                    del m
                    rt.release_memory()
                except Exception as e:
                    dtype_log.append({"dtype": cand, "role": "candidate", "accepted": False,
                                      "error": f"{type(e).__name__}: {str(e)[:300]}"})
                    rt.release_memory()
            if model is None:   # slow but exact
                model = rt.load_model(model_dir, "float32", device_map="auto", max_memory=mm)
                chosen = "float32"
        s.record(1, "model_loads", True, {
            "provenance": prov, "tokenizer_loader": tok_how, "class": type(model).__name__,
            "n_params": int(sum(p.numel() for p in model.parameters())),
            "dtype_selected": chosen, "dtype_trials": dtype_log,
            "dtype_rule": "first of [float16, bfloat16] that is finite at every layer and within "
                          "KL tolerance of the float32 reference; else float32 on all GPUs",
            "gpu_memory_after_load": rt.gpu_memory() if n_gpu else None,
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(1, "model_loads", e)

    # ------------------------------------------------- 2. architecture + template
    try:
        n_layers = len(rt.decoder_layers(model))
        hidden = int(model.config.hidden_size)
        rendered = rt.render_chat(tok, "سلام")
        ids = list(tok(rendered, add_special_tokens=False)["input_ids"])
        ids_default = list(tok(rendered)["input_ids"])
        bos = tok.bos_token_id
        sample = "میں ٹھیک ہوں، شکریہ۔ Main theek hoon."
        roundtrip = tok.decode(tok(sample, add_special_tokens=False)["input_ids"])
        tcount = {f: float(np.mean([len(tok(t, add_special_tokens=False)["input_ids"])
                                    for t in texts(cal, f, "harmful") + texts(cal, f, "benign")]))
                  for f in ("ur", "ro", "cm", "en")}
        single_bos = (bos is None) or (ids.count(bos) == 1 and ids[0] == bos)
        detail = {
            "class": type(model).__name__, "n_decoder_layers": n_layers, "hidden_size": hidden,
            "has_chat_template": rt.uses_chat_template(tok), "padding_side": tok.padding_side,
            "prompt_tokens_for_one_word": len(ids),
            "template_head": rendered[:160], "template_tail": rendered[-120:],
            "has_default_system_preamble": "System Preamble" in rendered,
            "last_prompt_token": tok.convert_ids_to_tokens(ids[-1]),
            "last_prompt_token_is_special": ids[-1] in set(tok.all_special_ids),
            "bos_count_add_special_tokens_false": ids.count(bos) if bos is not None else None,
            "bos_count_default_call": ids_default.count(bos) if bos is not None else None,
            "double_bos_hazard_confirmed": (bos is not None and ids_default.count(bos) > 1),
            "urdu_roundtrip_exact": roundtrip == sample,
            "end_of_turn_ids": rt.eos_token_ids(tok, model),
            "generation_config_eos": getattr(model.generation_config, "eos_token_id", None),
            "mean_user_tokens_by_form": tcount,
        }
        layers = [int(x) for x in args.layers.split(",") if int(x) < n_layers]
        alphas = [float(x) for x in args.alphas.split(",")]
        s.record(2, "architecture_and_template",
                 rt.uses_chat_template(tok) and n_layers > 0 and single_bos and roundtrip == sample
                 and len(layers) > 0, detail)
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(2, "architecture_and_template", e)

    # ------------------------------------------------------- 3. activation capture
    try:
        groups = {(f, lab): rt.capture_last_token(model, tok, texts(cal, f, lab), layers)
                  for f in ("ur", "ro") for lab in ("harmful", "benign")}
        mix = [texts(cal, "ur", "benign")[0], texts(cal, "ro", "benign")[0],
               texts(cal, "en", "harmful")[0], texts(cal, "cm", "benign")[0]]
        batched = rt.capture_last_token(model, tok, mix, layers, batch_size=len(mix))
        single = rt.capture_last_token(model, tok, mix, layers, batch_size=1)
        pad = {L: {"max_rel_err": float(np.max(np.linalg.norm(batched[L] - single[L], axis=1)
                                               / np.linalg.norm(single[L], axis=1))),
                   "min_cosine": float(min(rt.cosine(a, b) for a, b in zip(batched[L], single[L])))}
               for L in layers}
        finite = all(np.isfinite(v[L]).all() for v in groups.values() for L in layers)
        shape_ok = all(v[L].shape == (len(texts(cal, f, lab)), hidden)
                       for (f, lab), v in groups.items() for L in layers)
        pad_ok = all(p["max_rel_err"] < 0.05 and p["min_cosine"] > 0.999 for p in pad.values())
        s.record(3, "activation_capture", finite and shape_ok and pad_ok, {
            "layers": layers, "position": "last real token = final token of the generation prompt",
            "method": "forward hook on the decoder module SafeTune hooks (D-015); padding-agnostic index (D-016)",
            "group_shapes": {f"{f}/{lab}": list(v[layers[0]].shape) for (f, lab), v in groups.items()},
            "all_finite": finite, "shapes_ok": shape_ok,
            "mean_activation_norm": {L: float(np.mean([np.linalg.norm(v[L], axis=1).mean()
                                                       for v in groups.values()])) for L in layers},
            "padding_invariance": {"prompt_token_lengths": [len(rt.prompt_ids(tok, t)) for t in mix],
                                   "batched_vs_single": pad, "tolerance": "rel_err < 0.05 and cosine > 0.999",
                                   "passed": pad_ok},
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(3, "activation_capture", e)

    # --------------------------------------------- 4. official SafeTune extraction
    try:
        cfg = make_caa_config(layers, pool_method="last_token", normalize=False)
        v_form = {f: extract_vectors(model, tok, texts(cal, f, "harmful"), texts(cal, f, "benign"),
                                     layers, config=cfg) for f in ("ur", "ro")}
        d_script = extract_contrast(model, tok, texts(cal, "ur", "benign"), texts(cal, "ro", "benign"),
                                    layers, config=cfg)
        cross = {}
        for L in layers:
            for f in ("ur", "ro"):
                ref = contrast_vector(groups[(f, "harmful")][L], groups[(f, "benign")][L])
                got = to_np(v_form[f][L])
                cross[f"harm_{f}@L{L}"] = {"cosine": rt.cosine(got, ref),
                                           "rel_err": float(np.linalg.norm(got - ref) / np.linalg.norm(ref))}
            ref = script_contrast({"ur": groups[("ur", "benign")][L], "ro": groups[("ro", "benign")][L]}, "ur", "ro")
            got = to_np(d_script[L])
            cross[f"script@L{L}"] = {"cosine": rt.cosine(got, ref),
                                     "rel_err": float(np.linalg.norm(got - ref) / np.linalg.norm(ref))}
        v_pool = {L: (v_form["ur"][L] + v_form["ro"][L]) / 2.0 for L in layers}
        geom = {L: {"norm_v_ur": float(v_form["ur"][L].norm()), "norm_v_ro": float(v_form["ro"][L].norm()),
                    "norm_v_pooled": float(v_pool[L].norm()), "norm_script": float(d_script[L].norm()),
                    "cos_v_ur_v_ro": rt.cosine(to_np(v_form["ur"][L]), to_np(v_form["ro"][L])),
                    "cos_pooled_script": rt.cosine(to_np(v_pool[L]), to_np(d_script[L]))} for L in layers}
        min_cos = min(c["cosine"] for c in cross.values())
        s.record(4, "safetune_caa_extraction", min_cos > 0.99, {
            "api": "safetune.interventions.steer.caa.extract_caa_vectors (pinned 26f59e6)",
            "inputs": "RAW user text; SafeTune applies the chat template itself (D-021)",
            "n_prompts_per_form": {"harmful": len(texts(cal, "ur", "harmful")), "benign": len(texts(cal, "ur", "benign"))},
            "orientation": "harmful - benign  (script contrast: benign_ur - benign_ro)",
            "pooling": "equal weight over ur and ro (D-011)",
            "cross_check_vs_independent_capture": cross, "min_cosine": min_cos,
            "tolerance": "every cosine > 0.99", "geometry": geom,
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(4, "safetune_caa_extraction", e)

    # ------------------------------------------------------------- 5. SIGN TEST
    try:
        sign_recs = [r for r in dev if r["form"] in ("ur", "ro")]
        stexts = [r["text"] for r in sign_recs]
        is_h = np.array([r["safety_label"] == "harmful" for r in sign_recs])
        base = rt.refusal_margin(model, model, tok, stexts)
        A = float(args.sign_alpha)
        grid = sorted({-A, A} | set(alphas))
        table = []
        for L in layers:
            for a in grid:
                w = apply_vectors(model, {L: v_pool[L]}, strength=a)
                if steering_is_active(w):
                    raise RuntimeError("SafeTune hooks active before the call")
                m = rt.refusal_margin(w, model, tok, stexts)
                if steering_is_active(w):
                    raise RuntimeError("SafeTune hooks leaked after the call")
                d = m["margin"] - base["margin"]
                table.append({"layer": L, "alpha": a, "mean_margin_delta": float(d.mean()),
                              "frac_prompts_increased": float((d > 0).mean()),
                              "harmful_prompts_delta": float(d[is_h].mean()),
                              "benign_prompts_delta": float(d[~is_h].mean()),
                              "refusal_lp_delta": float((m["refusal_lp"] - base["refusal_lp"]).mean()),
                              "compliance_lp_delta": float((m["compliance_lp"] - base["compliance_lp"]).mean())})
                print(f"  sign L={L} alpha={a:+.0f}: margin delta {d.mean():+.3f} "
                      f"({(d > 0).mean():.0%} of prompts up)", flush=True)

        def row(L, a):
            return next(t for t in table if t["layer"] == L and t["alpha"] == a)

        per_layer = {}
        for L in layers:
            pos, neg = row(L, A), row(L, -A)
            per_layer[L] = {
                "delta_at_plus_alpha": pos["mean_margin_delta"], "delta_at_minus_alpha": neg["mean_margin_delta"],
                "frac_prompts_increased_at_plus_alpha": pos["frac_prompts_increased"],
                "sign_confirmed": bool(pos["mean_margin_delta"] > 0 > neg["mean_margin_delta"]
                                       and pos["frac_prompts_increased"] >= 0.75),
                "sign_reversed": bool(pos["mean_margin_delta"] < 0 < neg["mean_margin_delta"])}
        confirmed = [L for L in layers if per_layer[L]["sign_confirmed"]]
        best = max(confirmed, key=lambda L: per_layer[L]["delta_at_plus_alpha"]) if confirmed else None
        s.record(5, "sign_test", bool(confirmed), {
            "metric": "refusal margin = best refusal-continuation log-prob minus best compliance-continuation "
                      "log-prob (teacher-forced, mean per token); no text is generated",
            "prompts": f"{len(stexts)} dev prompts (ur+ro; {int(is_h.sum())} harmful, {int((~is_h).sum())} benign)",
            "unsteered_margin": {"harmful": float(base["margin"][is_h].mean()),
                                 "benign": float(base["margin"][~is_h].mean())},
            "pass_rule": f"at some layer: delta(+{A:g}) > 0 > delta(-{A:g}) and >= 75% of prompts increase",
            "per_layer": per_layer, "layers_confirmed": confirmed, "layer_selected_for_steps_6_to_8": best,
            "dose_response": table,
            "interpretation": ("positive strength raises refusal propensity: harmful-minus-benign orientation confirmed"
                               if confirmed else
                               "NO layer shows the expected sign. Do not flip silently; investigate."),
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(5, "sign_test", e)

    # ------------------------------------- 6. SafeTune applies vectors in generation
    try:
        L = best
        gen_recs = [r for r in dev if r["form"] in ("ur", "ro")]
        gtexts = [r["text"] for r in gen_recs]
        g_h = np.array([r["safety_label"] == "harmful" for r in gen_recs])
        resid, diag = transform_vector_dict({L: v_pool[L]}, {L: to_np(d_script[L])})
        tg = time.time()
        outputs = {"unsteered": rt.generate_text(model, tok, gtexts, max_new_tokens=args.max_new_tokens)}
        t_unsteered = time.time() - tg
        leaked = False
        for a in alphas:
            for arm, vec in (("pooled", v_pool[L]), ("residualized", resid[L])):
                w = apply_vectors(model, {L: vec}, strength=a)
                outputs[f"{arm}@{a:g}"] = rt.generate_text(model, tok, gtexts, wrapper=w,
                                                           max_new_tokens=args.max_new_tokens)
                leaked |= steering_is_active(w)

        def arm_summary(outs):
            return {"harmful_prompts": label_counts([o for o, h in zip(outs, g_h) if h]),
                    "benign_prompts": label_counts([o for o, h in zip(outs, g_h) if not h]),
                    "preview_harmful_prompt": outs[int(np.argmax(g_h))][:120],
                    "preview_benign_prompt": outs[int(np.argmin(g_h))][:120]}

        with (s.out / "generations.jsonl").open("w", encoding="utf-8") as fh:
            for arm, outs in outputs.items():
                for r, o in zip(gen_recs, outs):
                    fh.write(json.dumps({"arm": arm, "layer": L, "id": r["id"], "form": r["form"],
                                         "safety_label": r["safety_label"], "split": r["split"],
                                         "proxy_label": classify_refusal(o).label, "output": o},
                                        ensure_ascii=False) + "\n")
        s.record(6, "safetune_applies_vectors", (not leaked) and all(len(v) == len(gtexts) for v in outputs.values()), {
            "api": "safetune.interventions.steer.caa.CAAModel.generate", "layer": L, "alphas": alphas,
            "n_prompts": len(gtexts), "max_new_tokens": args.max_new_tokens,
            "hooks_leaked_after_generate": leaked,
            "residualization": diag[L],
            "unsteered_generation_seconds": round(t_unsteered, 1),
            "arms": {arm: arm_summary(outs) for arm, outs in outputs.items()},
            "caveat": "labels are the weak lexical proxy; n is smoke-scale",
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(6, "safetune_applies_vectors", e)

    # ------------------------------------------- 7. measurable behaviour change
    try:
        changed = {arm: float(np.mean([o != b for o, b in zip(outs, outputs["unsteered"])]))
                   for arm, outs in outputs.items() if arm != "unsteered"}
        w = apply_vectors(model, {L: resid[L]}, strength=A)
        m_res = rt.refusal_margin(w, model, tok, stexts)
        d_res = m_res["margin"] - base["margin"]
        d_pool = per_layer[L]["delta_at_plus_alpha"]

        def refusal_rate(outs, mask):
            sel = [o for o, k in zip(outs, mask) if k]
            return float(np.mean([classify_refusal(o).is_refusal for o in sel])) if sel else None

        s.record(7, "measurable_behaviour_change", d_pool > 0 and max(changed.values()) > 0, {
            "layer": L,
            "continuous_readout": {"metric": "mean refusal-margin shift at alpha=+%g" % A,
                                   "pooled_vector": d_pool, "residualized_vector": float(d_res.mean()),
                                   "residualized_frac_prompts_increased": float((d_res > 0).mean())},
            "fraction_of_generations_changed_vs_unsteered": changed,
            "proxy_refusal_rate_harmful_prompts": {arm: refusal_rate(outs, g_h) for arm, outs in outputs.items()},
            "proxy_refusal_rate_benign_prompts": {arm: refusal_rate(outs, ~g_h) for arm, outs in outputs.items()},
            "pass_rule": "margin shift > 0 AND at least one generated output differs from unsteered",
            "caveat": "smoke-scale n on dev prompts; NOT a hypothesis test",
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(7, "measurable_behaviour_change", e)

    # --------------------------------------------- 8. save / reload / reproduce
    try:
        a8 = A if A in alphas else alphas[len(alphas) // 2]
        vnp = {L: to_np(resid[L])}
        vpath = s.out / "vectors" / "residualized_smoke.npz"
        man = save_vectors(vpath, vnp, {
            "base_model": mcfg["repo_id"], "base_model_revision": mcfg["revision"],
            "weights_source": mcfg.get("kaggle_source"),
            "safetune_sha": "26f59e6d1bdcacafe5f2be3b8d982fb214369659",
            "layer_index": L, "alpha_used_in_smoke": a8, "inference_dtype": chosen,
            "dataset_version": corpus["dataset_version"], "dataset_sha256": corpus["sha256"],
            "code_commit": commit, "residualization": jsonable(diag[L]),
            "is_smoke_artifact": True, "not_a_validated_safety_artifact": True,
        })
        back, man2 = load_vectors(vpath)
        same = all(np.array_equal(back[k], vnp[k]) for k in vnp)
        w = apply_vectors(model, {int(k): torch.as_tensor(v, dtype=torch.float32) for k, v in back.items()},
                          strength=a8)
        again = rt.generate_text(model, tok, gtexts, wrapper=w, max_new_tokens=args.max_new_tokens)
        want = outputs[f"residualized@{a8:g}"]
        n_same = int(sum(x == y for x, y in zip(again, want)))
        s.record(8, "save_reload_reproduce", same and n_same == len(want), {
            "file": str(vpath.relative_to(s.out)), "sha256_vectors": man["sha256_vectors"],
            "manifest_orientation": man2.get("orientation"), "arrays_bit_identical": same,
            "generations_identical": f"{n_same}/{len(want)}", "alpha": a8, "layer": L,
            "note": "greedy decoding with identical batches: byte-identical text is expected",
        })
    except SmokeAbort:
        raise
    except Exception as e:
        s.fail(8, "save_reload_reproduce", e)

    s.report["all_steps_passed"] = True
    s.flush()
    print("\nALL EIGHT STEPS PASSED on the real model.", flush=True)

    # ------------------------------------------------------------------ extras
    # Non-fatal planning diagnostics. A failure here cannot un-pass the eight steps.
    if not args.no_extras:
        try:   # E1: representation-level layer scan (no generation)
            scan_layers = sorted(set(range(2, n_layers, 4)) | set(layers))
            cg = {(f, lab): rt.capture_last_token(model, tok, texts(cal, f, lab), scan_layers)
                  for f in ("ur", "ro") for lab in ("harmful", "benign")}
            dg = {(f, lab): rt.capture_last_token(model, tok, texts(dev, f, lab), scan_layers)
                  for f in ("ur", "ro") for lab in ("harmful", "benign")}
            scan = []
            for Ls in scan_layers:
                vu = contrast_vector(cg[("ur", "harmful")][Ls], cg[("ur", "benign")][Ls])
                vr = contrast_vector(cg[("ro", "harmful")][Ls], cg[("ro", "benign")][Ls])
                vp = (vu + vr) / 2.0
                ds = script_contrast({"ur": cg[("ur", "benign")][Ls], "ro": cg[("ro", "benign")][Ls]}, "ur", "ro")
                unit = vp / np.linalg.norm(vp)
                proj = {k: v[Ls] @ unit for k, v in dg.items()}
                act_norm = float(np.mean([np.linalg.norm(v[Ls], axis=1).mean() for v in cg.values()]))
                align = abs(rt.cosine(vp, ds))
                scan.append({
                    "layer": Ls, "mean_activation_norm": act_norm,
                    "norm_v_pooled": float(np.linalg.norm(vp)), "v_over_activation": float(np.linalg.norm(vp) / act_norm),
                    "norm_script": float(np.linalg.norm(ds)),
                    "cos_v_ur_v_ro": rt.cosine(vu, vr),
                    "alignment_pooled_script": align, "removed_frac_if_residualized": align ** 2,
                    "cos_interaction_script": rt.cosine(vu - vr, ds),
                    "norm_interaction_over_pooled": float(np.linalg.norm(vu - vr) / np.linalg.norm(vp)),
                    "dev_auc_harmful_vs_benign": {
                        "ur": rt.auc(proj[("ur", "harmful")], proj[("ur", "benign")]),
                        "ro": rt.auc(proj[("ro", "harmful")], proj[("ro", "benign")]),
                        "pooled": rt.auc(np.concatenate([proj[("ur", "harmful")], proj[("ro", "harmful")]]),
                                         np.concatenate([proj[("ur", "benign")], proj[("ro", "benign")]]))},
                })
            s.extra("layer_scan", {
                "note": "calibration-derived directions scored on dev prompts; 3 dev families -> "
                        "AUCs are coarse (9 pairs per form). Planning aid only.",
                "rows": scan})
            print("\n[extra] layer scan:", flush=True)
            for r in scan:
                print(f"  L{r['layer']:>2} |v|/|h|={r['v_over_activation']:.3f} cos(v_ur,v_ro)={r['cos_v_ur_v_ro']:+.3f} "
                      f"align(v,script)={r['alignment_pooled_script']:.3f} AUC ur/ro="
                      f"{r['dev_auc_harmful_vs_benign']['ur']:.2f}/{r['dev_auc_harmful_vs_benign']['ro']:.2f}", flush=True)
        except Exception as e:
            s.extra("layer_scan", {"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1500:]})

        try:   # E2: unsteered behaviour by form on calibration + dev (never test)
            pool = [r for r in recs if r["split"] in ("calibration", "dev")]
            ptexts = [r["text"] for r in pool]
            tb = time.time()
            outs = rt.generate_text(model, tok, ptexts, max_new_tokens=args.max_new_tokens)
            t_gen = time.time() - tb
            marg = rt.refusal_margin(model, model, tok, ptexts)
            by = {}
            for form in ("ur", "ro", "cm", "en"):
                for lab in ("harmful", "benign"):
                    idx = [i for i, r in enumerate(pool) if r["form"] == form and r["safety_label"] == lab]
                    by[f"{form}/{lab}"] = {"n": len(idx), "proxy_labels": label_counts([outs[i] for i in idx]),
                                           "mean_refusal_margin": float(np.mean([marg["margin"][i] for i in idx]))}
            with (s.out / "baseline_generations.jsonl").open("w", encoding="utf-8") as fh:
                for i, (r, o) in enumerate(zip(pool, outs)):
                    fh.write(json.dumps({"arm": "unsteered", "id": r["id"], "family_id": r["family_id"],
                                         "form": r["form"], "safety_label": r["safety_label"], "split": r["split"],
                                         "proxy_label": classify_refusal(o).label,
                                         "refusal_margin": float(marg["margin"][i]), "output": o},
                                        ensure_ascii=False) + "\n")
            n_unknown = sum(1 for o in outs if classify_refusal(o).label == "unknown")
            s.extra("unsteered_behaviour_by_form", {
                "scope": "calibration + dev prompts only; the test split is untouched",
                "n_prompts": len(pool), "max_new_tokens": args.max_new_tokens,
                "generation_seconds": round(t_gen, 1),
                "prompts_per_second": round(len(pool) / max(t_gen, 1e-9), 2),
                "by_form_and_label": by,
                "proxy_unknown_rate": n_unknown / len(outs),
                "caveat": "9 families; weak lexical proxy; unreviewed prompts. Descriptive only, NOT a test of H1.",
            })
            print("\n[extra] unsteered behaviour by form:", flush=True)
            for k, v in by.items():
                print(f"  {k:<11} n={v['n']} margin={v['mean_refusal_margin']:+.3f} {v['proxy_labels']}", flush=True)
        except Exception as e:
            s.extra("unsteered_behaviour_by_form", {"error": f"{type(e).__name__}: {e}",
                                                    "traceback": traceback.format_exc()[-1500:]})

    s.flush()
    print(f"\nreport: {s.out / 'smoke_report.json'}")
    print("SMOKE result at small n. It does not test H1/H2/H3.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeAbort as e:
        print(f"\n{e}", flush=True)
        raise SystemExit(1)
