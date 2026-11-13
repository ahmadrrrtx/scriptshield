"""Paired, family-clustered inference with explicit denominators.

Design rules:
* Every function reports the denominator it used.
* Nothing is silently dropped. Invalid/unknown outcomes are passed in as a
  third state and stay out of the numerator but IN the denominator.
* Resampling is by INTENT FAMILY, never by row: forms of the same family are
  correlated and treating them as independent inflates significance.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass
class Proportion:
    numerator: int
    denominator: int
    value: float
    unknown: int = 0
    invalid: int = 0


def proportion(flags: Sequence[int], unknown: Sequence[int] | None = None,
               invalid: Sequence[int] | None = None) -> Proportion:
    """Rate with explicit denominator. ``flags`` are 0/1 for valid judged rows.

    Unknown/invalid rows are NOT removed from the denominator; they simply do
    not contribute to the numerator. This is the 'missing output is never safe'
    rule expressed arithmetically: it can only ever *lower* a refusal rate.
    """
    f = np.asarray(flags, dtype=np.int64)
    n = int(f.size)
    num = int(np.sum(f == 1))
    u = 0 if unknown is None else int(np.sum(np.asarray(unknown, dtype=bool)))
    iv = 0 if invalid is None else int(np.sum(np.asarray(invalid, dtype=bool)))
    return Proportion(num, n, (num / n if n else float("nan")), u, iv)


def exact_mcnemar(a: Sequence[int], b: Sequence[int]) -> dict:
    """Exact two-sided McNemar on paired binary outcomes.

    ``a`` = baseline, ``b`` = treatment. Only discordant pairs carry evidence.
    p = 2 * sum_{k<=min(b01,b10)} C(n,k) 0.5^n, capped at 1.
    """
    aa, bb = np.asarray(a, dtype=np.int64), np.asarray(b, dtype=np.int64)
    if aa.shape != bb.shape:
        raise ValueError("paired arrays must have equal length")
    if not (np.isin(aa, [0, 1]).all() and np.isin(bb, [0, 1]).all()):
        raise ValueError("McNemar requires binary 0/1 outcomes; map unknowns explicitly first")
    b01 = int(np.sum((aa == 0) & (bb == 1)))   # baseline fail -> treatment success
    b10 = int(np.sum((aa == 1) & (bb == 0)))   # baseline success -> treatment fail
    n = b01 + b10
    if n == 0:
        p = 1.0
    else:
        k = min(b01, b10)
        tail = sum(math.comb(n, i) for i in range(k + 1))
        p = min(1.0, 2.0 * tail / (2.0 ** n))
    return {"b01": b01, "b10": b10, "discordant": n, "p_value": p,
            "n_pairs": int(aa.size), "method": "exact_mcnemar_two_sided"}


def paired_rate_diff(a: Sequence[int], b: Sequence[int]) -> float:
    """mean(b) - mean(a) in proportion units."""
    aa, bb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if aa.shape != bb.shape:
        raise ValueError("paired arrays must have equal length")
    if aa.size == 0:
        return float("nan")
    return float(bb.mean() - aa.mean())


def cluster_bootstrap_diff(a: Sequence[int], b: Sequence[int],
                           families: Sequence, n_boot: int = 10000,
                           seed: int = 20261103) -> np.ndarray:
    """Bootstrap distribution of mean(b)-mean(a), resampling FAMILIES with replacement.

    Returns the replicate array so callers can compute CIs and p-values.
    """
    aa, bb = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    fam = np.asarray(families)
    if not (aa.shape == bb.shape == fam.shape):
        raise ValueError("a, b, families must have equal length")
    if aa.size == 0:
        raise ValueError("no observations")
    uniq, inv = np.unique(fam, return_inverse=True)
    # Sum contributions per family so resampling a family moves all its forms.
    sums = np.zeros((uniq.size, 2), dtype=np.float64)
    counts = np.zeros(uniq.size, dtype=np.float64)
    np.add.at(sums[:, 0], inv, bb - aa)
    np.add.at(counts, inv, 1.0)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, uniq.size, size=(n_boot, uniq.size))
    num = sums[idx, 0].sum(axis=1)
    den = counts[idx].sum(axis=1)
    return num / den


def cluster_bootstrap_ci(a, b, families, n_boot: int = 10000,
                         seed: int = 20261103, alpha: float = 0.05) -> dict:
    reps = cluster_bootstrap_diff(a, b, families, n_boot=n_boot, seed=seed)
    lo, hi = np.quantile(reps, [alpha / 2, 1 - alpha / 2])
    point = paired_rate_diff(a, b)
    # Two-sided bootstrap p: 2*min(P(rep<=0), P(rep>=0)), floored at 1/n_boot.
    p = 2.0 * min(float(np.mean(reps <= 0)), float(np.mean(reps >= 0)))
    return {"estimate": point, "ci_low": float(lo), "ci_high": float(hi),
            "p_value": min(1.0, max(p, 1.0 / n_boot)),
            "n_boot": n_boot, "n_families": int(np.unique(np.asarray(families)).size),
            "seed": seed, "method": "family_cluster_bootstrap"}


def holm_correction(p_values: Sequence[float], alpha: float = 0.05) -> dict:
    """Holm-Bonferroni step-down. Returns adjusted p-values and rejections."""
    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1 or p.size == 0:
        raise ValueError("p_values must be a non-empty 1-D sequence")
    if not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must be finite and in [0,1]")
    m = p.size
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        val = (m - rank) * p[i]
        running = max(running, val)
        adj[i] = min(1.0, running)
    return {"adjusted_p": adj.tolist(), "reject": (adj <= alpha).tolist(),
            "alpha": alpha, "n_tests": m, "method": "holm"}
