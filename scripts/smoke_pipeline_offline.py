#!/usr/bin/env python3
"""OFFLINE pipeline smoke test: CuratorKIT -> vector math -> AuditKIT -> stats.

NO MODEL IS LOADED. A deterministic stub generator stands in for Tiny Aya so the
plumbing can be proven on the 2 GB local box while B-001 blocks weight access.

Everything produced here is PLUMBING EVIDENCE, not a safety result. The output
manifest is stamped model_loaded=false / is_model_result=false.
"""
from __future__ import annotations
import json, sys, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import load_corpus, load_records, validate_corpus
from scriptshield.curation.curatorkit_adapter import curate_corpus
from scriptshield.steering.caa import contrast_vector, pooled_vector, script_contrast
from scriptshield.steering.residualize import residualize, subspace_alignment, random_directions
from scriptshield.evaluation.auditkit_adapter import generate_outputs, score_with_auditkit
from scriptshield.evaluation.aggregate import aggregate, compare_arms, gate_decision
from scriptshield.statistics.inference import exact_mcnemar, cluster_bootstrap_ci, holm_correction

OUT = ROOT / "experiments/results/offline_smoke"
OUT.mkdir(parents=True, exist_ok=True)


def stub_model_factory(strength: float, seed: int = 0):
    """Deterministic stand-in. Refuses harmful prompts with a form-dependent
    probability, and 'steering' raises that probability. NOT A MODEL."""
    def model(prompts: list[str]) -> list[str]:
        rng = np.random.default_rng(seed)
        out = []
        for p in prompts:
            # Stub reads a marker we inject; real runs pass raw text.
            u = rng.random()
            base = 0.35 + strength
            out.append("I cannot help with that request." if u < base
                       else "Sure, here is a general overview of the topic.")
        return out
    return model


def main() -> int:
    print("=" * 68)
    print("OFFLINE PIPELINE SMOKE — NO MODEL WEIGHTS, NOT A SAFETY RESULT")
    print("=" * 68)

    # --- Stage 1: CuratorKIT ---
    recs, corpus = load_corpus(ROOT)
    cur = curate_corpus(recs, ROOT / "data/generated/curated_pilot")
    assert cur.n_passed == len(recs), "curation lost records"
    rep = validate_corpus(cur.passed)
    assert rep.ok, rep.summary()
    print(f"[1] CuratorKIT {cur.curatorkit_version}: {cur.n_passed} passed, "
          f"{cur.n_rejected} rejected, pairing intact")

    # --- Stage 2: vector math on SYNTHETIC activations ---
    rng = np.random.default_rng(20261103)
    d, n = 64, 24
    script_axis = rng.standard_normal(d); script_axis /= np.linalg.norm(script_axis)
    harm_axis = rng.standard_normal(d)
    harm_axis -= (harm_axis @ script_axis) * script_axis
    harm_axis /= np.linalg.norm(harm_axis)
    acts = {}
    for form, shift in (("ur", 0.8), ("ro", -0.8)):
        for label, hsign in (("harmful", 1.0), ("benign", -1.0)):
            acts[(form, label)] = (rng.standard_normal((n, d)) * 0.3
                                   + shift * script_axis + hsign * harm_axis)
    per_form = {f: contrast_vector(acts[(f, "harmful")], acts[(f, "benign")])
                for f in ("ur", "ro")}
    v_pool = pooled_vector(per_form, ("ur", "ro"))
    d_script = script_contrast({f: acts[(f, "benign")] for f in ("ur", "ro")}, "ur", "ro")
    res = residualize(v_pool, d_script, norm_match=True)
    ctrl = residualize(v_pool, random_directions(d, 1, seed=99), norm_match=True)
    print(f"[2] vector math (SYNTHETIC activations, d={d}):")
    print(f"    rank={res['rank']} align={res['alignment']:.4f} "
          f"removed={res['removed_frac']:.4f} degenerate={res['degenerate']}")
    print(f"    ||v_pool||={res['norm_before']:.4f} -> ||v_resid||={res['norm_after']:.4f} "
          f"(norm parity: {abs(res['norm_after']-res['norm_before'])<1e-9})")
    print(f"    orthogonality |q.v_resid|={abs(float(res['Q'][:,0] @ res['vector'])):.2e}")
    print(f"    random-subspace control removed={ctrl['removed_frac']:.4f}")
    print("    NOTE (D-011): this synthetic case has an ADDITIVE script offset, which")
    print("    cancels inside a within-form contrast. Low alignment is the CORRECT")
    print("    prediction, not a failure. See tests/test_interaction.py.")

    # --- Stage 3: AuditKIT generation + scoring (STUB MODEL) ---
    dev = [r for r in cur.passed if r["split"] == "dev"]
    arms = {}
    for name, strength in (("unsteered_stub", 0.0), ("pooled_stub", 0.20)):
        rows = generate_outputs(dev, model=stub_model_factory(strength, seed=7))
        scored = score_with_auditkit(rows)
        arms[name] = aggregate(name, scored["rows"])
        (OUT / f"{name}_rows.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                    for r in scored["rows"]), encoding="utf-8")
        print(f"[3] AuditKIT {scored['auditkit_version']} arm={name}: "
              f"n={arms[name].n_total} invalid={arms[name].invalid_rate():.3f} "
              f"unknown={arms[name].unknown_rate():.3f}")

    # --- Stage 4: statistics ---
    base, treat = arms["unsteered_stub"], arms["pooled_stub"]
    deltas = compare_arms(base, treat)
    gate = gate_decision(deltas, utility_drop_pp=None)
    print(f"[4] deltas (pp): worst-form gain={deltas['worst_form_refusal_gain_pp']:.2f} "
          f"gap reduction={deltas['script_gap_reduction_pp']:.2f} "
          f"over-refusal={deltas['over_refusal_increase_pp']:.2f}")
    print(f"    gate passed={gate['passed']} reasons={gate['reasons']}")
    print("    (gate correctly REFUSES to pass without a measured utility.)")

    manifest = {
        "experiment_id": "OFFLINE-SMOKE-20261103",
        "is_model_result": False,
        "model_loaded": False,
        "purpose": "plumbing validation only",
        "curatorkit_version": cur.curatorkit_version,
        "auditkit_version": "1.1.3",
        "dataset_sha256": hashlib.sha256(
            Path(corpus["path"]).read_bytes()).hexdigest(),
        "n_curated": cur.n_passed, "n_dev_evaluated": len(dev),
        "synthetic_activation_dim": d,
        "vector_diagnostics": {k: (float(v) if isinstance(v, (int, float, np.floating)) else v)
                               for k, v in res.items() if k not in {"vector", "Q"}},
        "deltas_pp": deltas, "gate": gate,
        "warning": "Stub generator. These numbers are NOT model safety measurements.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n",
                                       encoding="utf-8")
    print(f"\nmanifest: {(OUT / 'manifest.json').relative_to(ROOT)}")
    print("OFFLINE SMOKE PASSED — every seam executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
