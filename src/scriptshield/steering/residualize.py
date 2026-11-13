"""Script-subspace residualization — the core ScriptShield intervention.

Pure numpy. No torch, no model, no network. This is deliberately testable on the
2 GB local box so the mathematics is proven correct BEFORE any GPU time is spent.

Mathematics (RESEARCH_PROTOCOL.md §6-7), per layer l:

    d_script = mean(h_benign,ur) - mean(h_benign,ro)
    Q        = orth(d_script)                     # QR, SVD fallback
    v_resid  = (I - Q Q^T) v_pooled
    v_resid <- v_resid * (||v_pooled|| / ||v_resid||)   # dose parity

Everything is float64 internally for numerical stability; callers may cast back.
"""
from __future__ import annotations

import numpy as np

RANK_TOL = 1e-8
DEGENERATE_TOL = 1e-10


def _as_f64(x: np.ndarray) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite values in input array")
    return a


def orthonormal_basis(vectors: np.ndarray, tol: float = RANK_TOL) -> np.ndarray:
    """Orthonormal basis for the span of ``vectors`` (shape [k, d] or [d]).

    Uses SVD so that rank-deficient / duplicated script contrasts are handled
    gracefully instead of producing a bogus full-rank Q. Returns [d, r] with
    r <= k. Returns [d, 0] when every direction is numerically zero.

    SVD is chosen over classical QR because our rank-1 and rank-3 script bases
    are frequently near-degenerate (d1, d2, d3 are linearly dependent by
    construction: d2 - d3 = d1), and QR would silently keep a noise direction.
    """
    a = _as_f64(vectors)
    if a.ndim == 1:
        a = a[None, :]
    if a.ndim != 2:
        raise ValueError(f"expected 1-D or 2-D array, got shape {a.shape}")
    if a.shape[1] == 0:
        return np.zeros((0, 0), dtype=np.float64)
    # Rows are directions; SVD of A^T gives left singular vectors in feature space.
    _, s, vt = np.linalg.svd(a, full_matrices=False)
    if s.size == 0:
        return np.zeros((a.shape[1], 0), dtype=np.float64)
    thresh = tol * max(a.shape) * (s[0] if s[0] > 0 else 1.0)
    rank = int(np.sum(s > thresh))
    return vt[:rank].T.copy()          # [d, r]


def project_out(v: np.ndarray, Q: np.ndarray) -> np.ndarray:
    """(I - Q Q^T) v. Q is [d, r]; r == 0 is a no-op."""
    vv = _as_f64(v)
    if vv.ndim != 1:
        raise ValueError(f"v must be 1-D, got {vv.shape}")
    q = _as_f64(Q)
    if q.ndim != 2:
        raise ValueError(f"Q must be 2-D [d, r], got {q.shape}")
    if q.shape[0] != vv.shape[0]:
        raise ValueError(f"dimension mismatch: v has {vv.shape[0]}, Q has {q.shape[0]} rows")
    if q.shape[1] == 0:
        return vv.copy()
    return vv - q @ (q.T @ vv)


def match_norm(v: np.ndarray, target_norm: float,
               tol: float = DEGENERATE_TOL) -> tuple[np.ndarray, bool]:
    """Scale ``v`` to ``target_norm``.

    Returns (scaled, degenerate). ``degenerate=True`` means the residual was too
    small to rescale safely; the caller MUST report this rather than amplifying
    numerical noise into a huge steering vector.
    """
    vv = _as_f64(v)
    n = float(np.linalg.norm(vv))
    if not np.isfinite(target_norm) or target_norm < 0:
        raise ValueError(f"invalid target_norm {target_norm}")
    if n < tol:
        return vv.copy(), True
    return vv * (target_norm / n), False


def residualize(v_pooled: np.ndarray, script_vectors: np.ndarray,
                norm_match: bool = True,
                tol: float = RANK_TOL) -> dict:
    """Full intervention with diagnostics.

    Returns dict with:
      vector        residualized (and optionally norm-matched) vector
      Q             orthonormal script basis [d, r]
      rank          effective subspace rank
      removed_frac  fraction of ||v_pooled|| removed by projection
      alignment     cosine between v_pooled and its projection onto span(Q)
      degenerate    True if residual too small to rescale
      norm_before / norm_after
    """
    v = _as_f64(v_pooled)
    sv = _as_f64(script_vectors)
    if sv.ndim == 2 and sv.shape[1] != v.shape[0]:
        raise ValueError(
            f"script_vectors must be directions stacked as ROWS [k, d] (or 1-D [d]); "
            f"got {sv.shape} for hidden dim {v.shape[0]}. "
            f"If you already hold an orthonormal basis [d, r], pass basis.T"
        )
    Q = orthonormal_basis(sv, tol=tol)
    resid = project_out(v, Q)
    n_before = float(np.linalg.norm(v))
    n_resid = float(np.linalg.norm(resid))
    removed = 0.0 if n_before == 0 else float(np.sqrt(max(n_before**2 - n_resid**2, 0.0)) / n_before)
    alignment = 0.0 if n_before == 0 else float(np.sqrt(max(1.0 - (n_resid / n_before) ** 2, 0.0)))
    degenerate = False
    out = resid
    if norm_match:
        out, degenerate = match_norm(resid, n_before)
    return {
        "vector": out,
        "Q": Q,
        "rank": int(Q.shape[1]),
        "removed_frac": removed,
        "alignment": alignment,
        "degenerate": bool(degenerate),
        "norm_before": n_before,
        "norm_after": float(np.linalg.norm(out)),
    }


def subspace_alignment(v: np.ndarray, Q: np.ndarray) -> float:
    """Cosine-style alignment in [0,1]: ||Q^T v|| / ||v||. 0 = orthogonal."""
    vv = _as_f64(v)
    n = float(np.linalg.norm(vv))
    if n == 0 or Q.shape[1] == 0:
        return 0.0
    return float(np.linalg.norm(Q.T @ vv) / n)


def random_subspace(dim: int, rank: int, seed: int) -> np.ndarray:
    """Seeded random orthonormal [dim, rank] control, matched to the real rank."""
    if rank <= 0:
        return np.zeros((dim, 0), dtype=np.float64)
    rng = np.random.default_rng(seed)
    return orthonormal_basis(rng.standard_normal((rank, dim)))


def random_directions(dim: int, rank: int, seed: int) -> np.ndarray:
    """Seeded random control DIRECTIONS as [rank, dim].

    Prefer this over feeding ``random_subspace`` output back into ``residualize``:
    the latter returns a basis [dim, rank], whose rows would be misread as
    directions. This helper keeps the control on the same footing as the real
    script contrasts (raw, unnormalized directions).
    """
    if rank <= 0:
        return np.zeros((0, dim), dtype=np.float64)
    rng = np.random.default_rng(seed)
    return rng.standard_normal((rank, dim))
