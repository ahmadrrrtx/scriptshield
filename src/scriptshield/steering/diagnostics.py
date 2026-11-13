"""Mechanism diagnostics on captured activations. Pure numpy (unit-tested locally,
re-runnable offline from the activation dump of a GPU run).

Inputs are FAMILY-ALIGNED arrays: ``acts[(form, label)]`` has shape [n_families, d]
and row i of every array belongs to the same intent family.

Estimator hazards handled here (both were seen on real data in the smoke test):

* In-sample alignment between the pooled harm vector and the script direction is
  noisy, and cos(v_ur - v_ro, d_script) is biased NEGATIVE by construction because
  the same benign activations enter both terms. So every directional claim is
  CROSS-FITTED: a family's own activations never help build the direction it is
  projected on (leave-one-family-out).
* A random isotropic direction is too easy a null in an anisotropic residual stream,
  so significance uses a within-family SIGN-FLIP test on cross-fitted projections.
"""
from __future__ import annotations

import numpy as np

FORMS = ("ur", "ro")


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    den = np.linalg.norm(a) * np.linalg.norm(b)
    return float(a @ b / den) if den > 0 else float("nan")


def sign_flip_test(x: np.ndarray, n_perm: int = 10000, seed: int = 0) -> dict:
    """Two-sided one-sample sign-flip test of mean(x) = 0 across families."""
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    obs = float(x.mean())
    rng = np.random.default_rng(seed)
    if n <= 16:                                   # exact enumeration
        signs = np.array(np.meshgrid(*[[-1.0, 1.0]] * n)).reshape(n, -1).T
    else:
        signs = rng.choice([-1.0, 1.0], size=(n_perm, n))
    null = (signs * x).mean(axis=1)
    p = float((np.sum(np.abs(null) >= abs(obs) - 1e-15) + (0 if n <= 16 else 1))
              / (null.size + (0 if n <= 16 else 1)))
    sd = float(x.std(ddof=1)) if n > 1 else float("nan")
    return {"n": int(n), "mean": obs, "sd": sd,
            "cohens_d": float(obs / sd) if sd and sd > 0 else float("nan"),
            "p_two_sided": p, "frac_positive": float((x > 0).mean())}


def bootstrap_ci(stat_fn, n: int, n_boot: int = 2000, seed: int = 0) -> list[float]:
    """Percentile 95 % CI of ``stat_fn(indices)`` under FAMILY resampling."""
    rng = np.random.default_rng(seed)
    vals = [stat_fn(rng.integers(0, n, size=n)) for _ in range(n_boot)]
    lo, hi = np.percentile(np.asarray(vals, dtype=np.float64), [2.5, 97.5])
    return [float(lo), float(hi)]


def layer_diagnostics(acts: dict, seed: int = 20261112, n_boot: int = 2000, n_perm: int = 10000) -> dict:
    """All mechanism diagnostics for ONE layer.

    acts: {(form, label): [n_families, d]} for form in ur/ro and label in harmful/benign.
    """
    A = {k: np.asarray(v, dtype=np.float64) for k, v in acts.items()}
    n, d = A[("ur", "harmful")].shape
    for k, v in A.items():
        if v.shape != (n, d):
            raise ValueError(f"{k}: expected {(n, d)}, got {v.shape}; arrays must be family-aligned")
    c = {f: A[(f, "harmful")] - A[(f, "benign")] for f in FORMS}      # per-family harm contrast [n, d]
    s = A[("ur", "benign")] - A[("ro", "benign")]                      # per-family script diff   [n, d]
    v = {f: c[f].mean(axis=0) for f in FORMS}
    v_pool = 0.5 * (v["ur"] + v["ro"])
    d_script = s.mean(axis=0)
    act_norm = float(np.mean([np.linalg.norm(a, axis=1).mean() for a in A.values()]))

    def lofo(mat: np.ndarray, i: int) -> np.ndarray:                  # mean without family i
        return (mat.sum(axis=0) - mat[i]) / (n - 1)

    # --- H2: is the pooled harm vector aligned with the benign script direction? (cross-fitted)
    # projection of family i's script difference on the unit pooled vector built WITHOUT family i
    p_script = np.array([s[i] @ _unit(0.5 * (lofo(c["ur"], i) + lofo(c["ro"], i))) for i in range(n)])
    h2 = sign_flip_test(p_script, n_perm, seed)
    cf_alignment = float(p_script.mean() / np.linalg.norm(d_script)) if np.linalg.norm(d_script) > 0 else float("nan")

    # --- representation-level H1: is the harm signal weaker in Roman Urdu along the shared direction?
    proj = {f: np.array([c[f][i] @ _unit(0.5 * (lofo(c["ur"], i) + lofo(c["ro"], i))) for i in range(n)])
            for f in FORMS}
    h1_repr = sign_flip_test(proj["ur"] - proj["ro"], n_perm, seed + 1)

    in_sample = abs(_cos(v_pool, d_script))
    rng = np.random.default_rng(seed + 2)
    rand = rng.standard_normal((2000, d))
    rand_cos = np.abs(rand @ _unit(v_pool)) / np.linalg.norm(rand, axis=1)

    return {
        "n_families": int(n), "hidden": int(d), "mean_activation_norm": act_norm,
        "norm_v_ur": float(np.linalg.norm(v["ur"])), "norm_v_ro": float(np.linalg.norm(v["ro"])),
        "norm_v_pooled": float(np.linalg.norm(v_pool)), "norm_script": float(np.linalg.norm(d_script)),
        "v_pooled_over_activation": float(np.linalg.norm(v_pool) / act_norm),
        "norm_ratio_ro_over_ur": {
            "value": float(np.linalg.norm(v["ro"]) / np.linalg.norm(v["ur"])),
            "ci95": bootstrap_ci(lambda ix: np.linalg.norm(c["ro"][ix].mean(0)) / np.linalg.norm(c["ur"][ix].mean(0)),
                                 n, n_boot, seed + 3)},
        "cos_v_ur_v_ro": {
            "value": _cos(v["ur"], v["ro"]),
            "ci95": bootstrap_ci(lambda ix: _cos(c["ur"][ix].mean(0), c["ro"][ix].mean(0)), n, n_boot, seed + 4),
            "note": "in-sample cosines of noisy means are biased toward 0; see split-half below"},
        "cos_v_ur_v_ro_split_half": _split_half_cos(c, seed + 5),
        "h2_script_alignment": {
            "in_sample_abs_cosine": in_sample,
            "removed_norm_fraction_if_residualized": in_sample,
            "removed_variance_fraction_if_residualized": in_sample ** 2,
            "cross_fitted_cosine": cf_alignment,
            "cross_fitted_projection_test": h2,
            "isotropic_random_null_abs_cosine": {"mean": float(rand_cos.mean()),
                                                 "p95": float(np.percentile(rand_cos, 95))},
            "reading": "cross_fitted_projection_test asks whether families' benign script differences "
                       "point consistently along (or against) the harm direction built from OTHER families"},
        "h1_representation": {
            "mean_projection_ur": float(proj["ur"].mean()), "mean_projection_ro": float(proj["ro"].mean()),
            "ratio_ro_over_ur": float(proj["ro"].mean() / proj["ur"].mean()) if proj["ur"].mean() else float("nan"),
            "paired_difference_test_ur_minus_ro": h1_repr,
            "reading": "projection of each family's harmful-minus-benign contrast on the shared harm "
                       "direction (leave-one-family-out); ur > ro means harm is under-represented in Roman Urdu"},
    }


def _split_half_cos(c: dict, seed: int, n_splits: int = 200) -> dict:
    """cos(v_ur from half A, v_ro from half B): no shared noise between the two vectors."""
    n = c["ur"].shape[0]
    rng = np.random.default_rng(seed)
    vals, same = [], []
    for _ in range(n_splits):
        perm = rng.permutation(n)
        a, b = perm[: n // 2], perm[n // 2:]
        vals.append(_cos(c["ur"][a].mean(0), c["ro"][b].mean(0)))
        same.append(_cos(c["ur"][a].mean(0), c["ur"][b].mean(0)))       # reliability ceiling
    return {"cross_script": float(np.mean(vals)), "within_script_ceiling_ur": float(np.mean(same)),
            "disattenuated": float(np.mean(vals) / np.mean(same)) if np.mean(same) > 0 else float("nan"),
            "note": "cross_script / ceiling ~ 1 means the two scripts share one harm direction up to noise"}
