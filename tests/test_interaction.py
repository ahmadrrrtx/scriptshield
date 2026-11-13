"""D-011: residualization helps only under script x harm interaction.

These are the mechanism tests. They encode WHY the method can work, and the
condition under which it must be reported as a null.
"""
import numpy as np
import pytest
from scriptshield.steering.caa import contrast_vector, pooled_vector, script_contrast
from scriptshield.steering.residualize import residualize, random_directions

D, N = 64, 2000


def _axes(seed=1):
    rng = np.random.default_rng(seed)
    s = rng.standard_normal(D); s /= np.linalg.norm(s)
    h = rng.standard_normal(D); h -= (h @ s) * s; h /= np.linalg.norm(h)
    return rng, s, h


def _build(interaction: bool, contaminate_benign: bool = False,
           antisymmetric: bool = False):
    """Generative model.

    benign : c_f + s_f                      (no harm response)
    harmful: c_f + s_f + a_f*h + b_f*s      (b_f = script x harm interaction)

    Interaction magnitudes are ASYMMETRIC (b_ur=0.6, b_ro=0.2) so a component
    survives equal-weight pooling. With ``antisymmetric=True`` (b_ur=+0.4,
    b_ro=-0.4) the script components cancel in the pooled vector: pooling is
    itself a partial defence, and residualization then has nothing to remove.

    ``contaminate_benign`` deliberately gives benign prompts a form-dependent
    harm-axis component. That is the failure mode where the "script" basis is
    no longer pure script, and residualizing it deletes real harm signal.
    """
    rng, s, h = _axes()
    acts = {}
    for form, sc, amp in (("ur", 0.8, 1.0), ("ro", -0.8, 0.35 if interaction else 1.0)):
        for label in ("harmful", "benign"):
            base = rng.standard_normal((N, D)) * 0.3 + sc * s
            if label == "harmful":
                if not interaction:
                    b = 0.0
                elif antisymmetric:
                    b = 0.5 * sc
                else:
                    b = 0.6 if form == "ur" else 0.2
                base = base + amp * h + b * s
            elif contaminate_benign:
                base = base - amp * h
            acts[(form, label)] = base
    v = pooled_vector({f: contrast_vector(acts[(f, "harmful")], acts[(f, "benign")])
                       for f in ("ur", "ro")}, ("ur", "ro"))
    dscript = script_contrast({f: acts[(f, "benign")] for f in ("ur", "ro")}, "ur", "ro")
    return v, dscript


def test_additive_script_offset_cancels_in_contrast_vector():
    """CAA is already invariant to additive script offsets: alignment ~ 0."""
    v, dscript = _build(interaction=False)
    out = residualize(v, dscript)
    assert out["alignment"] < 0.05, (
        "additive script offset must cancel in a within-form contrast; "
        f"got alignment={out['alignment']:.4f}")


def test_interaction_produces_script_aligned_pooled_vector():
    v, dscript = _build(interaction=True)
    out = residualize(v, dscript)
    assert out["alignment"] > 0.4, f"expected strong alignment, got {out['alignment']:.4f}"


def test_true_subspace_beats_random_control_only_under_interaction():
    v, dscript = _build(interaction=True)
    true = residualize(v, dscript, norm_match=False)
    ctrl = residualize(v, random_directions(D, 1, seed=99), norm_match=False)
    assert true["removed_frac"] > 5 * ctrl["removed_frac"]


def test_residualization_preserves_norm_and_orthogonality_under_interaction():
    v, dscript = _build(interaction=True)
    out = residualize(v, dscript, norm_match=True)
    assert out["norm_after"] == pytest.approx(out["norm_before"], rel=1e-9)
    assert abs(float(out["Q"][:, 0] @ out["vector"])) < 1e-9


def test_residualized_vector_retains_harm_signal():
    """Removing script must not remove harm: dose parity + retained projection."""
    _, s, h = _axes()
    v, dscript = _build(interaction=True)
    out = residualize(v, dscript, norm_match=True)
    before = float(v @ h) / np.linalg.norm(v)
    after = float(out["vector"] @ h) / np.linalg.norm(out["vector"])
    assert after > before, "residualization should increase harm-direction purity"


def test_contaminated_benign_basis_deletes_harm_signal():
    """Threat to validity: if benign forms differ along the harm axis, the
    script basis is not pure script and residualization removes harm signal.

    This is why the real pipeline must verify that the benign-derived script
    direction is not harm-aligned BEFORE trusting a residualized arm.
    """
    v, dscript = _build(interaction=True, contaminate_benign=True)
    out = residualize(v, dscript, norm_match=True)
    _, _, h = _axes()
    purity_before = float(v @ h) / np.linalg.norm(v)
    purity_after = float(out["vector"] @ h) / np.linalg.norm(out["vector"])
    assert purity_after < purity_before, (
        "contaminated basis should measurably reduce harm purity; "
        "the diagnostic must be able to detect this")


def test_antisymmetric_interaction_cancels_under_pooling():
    """Equal-weight form pooling already removes sign-symmetric script leakage."""
    v, dscript = _build(interaction=True, antisymmetric=True)
    out = residualize(v, dscript)
    assert out["alignment"] < 0.05, (
        f"antisymmetric interaction must cancel in the pool, got {out['alignment']:.4f}")
