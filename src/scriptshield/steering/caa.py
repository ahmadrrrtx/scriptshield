"""Contrastive Activation Addition construction, independent of SafeTune.

This module is the *reference implementation* used to cross-check SafeTune's
``extract_caa_vectors`` on the real model. Sign convention is explicit and
matches the verified SafeTune behaviour (DECISIONS D-006):

    v = mean(harmful) - mean(benign)      ->  points toward refusal
    CAAModel applies  h + strength * v    ->  positive strength increases refusal

Never infer the sign from a parameter name; the sign test is mandatory.
"""
from __future__ import annotations

import numpy as np


def _stack(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim != 2:
        raise ValueError(f"expected [n_samples, dim], got {a.shape}")
    if a.shape[0] == 0:
        raise ValueError("empty activation group")
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite activations")
    return a


def contrast_vector(harmful: np.ndarray, benign: np.ndarray) -> np.ndarray:
    """mean(harmful) - mean(benign). Refusal-pointing by construction."""
    h, b = _stack(harmful), _stack(benign)
    if h.shape[1] != b.shape[1]:
        raise ValueError(f"hidden dim mismatch: {h.shape[1]} vs {b.shape[1]}")
    return h.mean(axis=0) - b.mean(axis=0)


def pooled_vector(per_form: dict[str, np.ndarray], forms: tuple[str, ...]) -> np.ndarray:
    """Equal-weight mean over the requested forms.

    Equal weighting per FORM (not per sample) is intentional: it prevents a
    form with more prompts from dominating the pooled direction.
    """
    missing = [f for f in forms if f not in per_form]
    if missing:
        raise KeyError(f"missing forms for pooling: {missing}")
    vecs = [np.asarray(per_form[f], dtype=np.float64) for f in forms]
    d = vecs[0].shape[0]
    if any(v.shape != (d,) for v in vecs):
        raise ValueError("all per-form vectors must be 1-D of equal length")
    return np.mean(np.stack(vecs, axis=0), axis=0)


def script_contrast(benign_by_form: dict[str, np.ndarray],
                    form_a: str, form_b: str) -> np.ndarray:
    """Benign-derived script nuisance direction: mean(benign_a) - mean(benign_b).

    Uses BENIGN prompts only, so the subspace cannot be a relabelled harm axis.
    """
    a, b = _stack(benign_by_form[form_a]), _stack(benign_by_form[form_b])
    if a.shape[1] != b.shape[1]:
        raise ValueError("hidden dim mismatch between forms")
    return a.mean(axis=0) - b.mean(axis=0)


def shuffled_label_vector(harmful: np.ndarray, benign: np.ndarray,
                          seed: int) -> np.ndarray:
    """Control: shuffle harmful/benign labels, then recompute the contrast.

    Under the null (no label signal) this has similar norm but random direction.
    """
    h, b = _stack(harmful), _stack(benign)
    pooled = np.concatenate([h, b], axis=0)
    n_h = h.shape[0]
    rng = np.random.default_rng(seed)
    idx = rng.permutation(pooled.shape[0])
    return pooled[idx[:n_h]].mean(axis=0) - pooled[idx[n_h:]].mean(axis=0)


def label_flip_null_vector(harmful: np.ndarray, benign: np.ndarray, seed: int) -> np.ndarray:
    """Control direction with NO harm signal in expectation and the estimator's own noise.

    ``harmful[i]`` and ``benign[i]`` must be a matched pair. Exactly half of the pairs
    have their labels swapped, so the true harm component cancels:

        v_null = mean_i( s_i * (harmful_i - benign_i) ),   s_i = +/-1,  sum(s_i) = 0

    WHY this replaced ``shuffled_label_vector`` (D-028, found on real data before any
    test run): an unconstrained label shuffle leaves a chance imbalance of true labels
    between the two groups, and because the harm axis is by far the strongest direction
    in the pooled set, that imbalance dominates. On Tiny Aya Fire the "shuffled" vector
    had cosine -0.59 ... -0.81 with the real refusal vector; norm-matched, it would
    have been an ANTI-refusal steering arm, not a neutral control.
    """
    h, b = _stack(harmful), _stack(benign)
    if h.shape != b.shape:
        raise ValueError("label_flip_null_vector needs matched pairs: equal shapes required")
    n = h.shape[0]
    if n < 2:
        raise ValueError("need at least two pairs")
    signs = np.ones(n)
    signs[: n // 2] = -1.0
    if n % 2:
        signs[-1] = 0.0                      # odd n: drop one pair so the signs sum to zero
    np.random.default_rng(seed).shuffle(signs)
    return ((h - b) * signs[:, None]).sum(axis=0) / max(float(np.abs(signs).sum()), 1.0)


def orthogonal_null_vector(harmful: np.ndarray, benign: np.ndarray, reference: np.ndarray,
                           seed: int) -> np.ndarray:
    """Control direction EXACTLY orthogonal to ``reference`` (the real steering vector).

    Start from the balanced label-flip vector (the estimator's own noise) and remove
    its component along the reference. Measured on Tiny Aya Fire: even the balanced
    label flip keeps |cos| ~ 0.2-0.3 with the refusal vector for a given seed, because
    per-pair contrasts vary a lot in size along the harm axis. A control that is "a
    little anti-refusal by chance" cannot answer the question it exists for:
    *is the effect due to the DIRECTION, or to adding any vector of this norm?*
    """
    v = label_flip_null_vector(harmful, benign, seed)
    ref = np.asarray(reference, dtype=np.float64)
    n = float(ref @ ref)
    if n <= 0:
        raise ValueError("reference vector has zero norm")
    out = v - (v @ ref) / n * ref
    if float(np.linalg.norm(out)) < 1e-9:
        raise ValueError("null vector is degenerate after orthogonalisation")
    return out
