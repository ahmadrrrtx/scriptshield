import numpy as np
import pytest
from scriptshield.steering.residualize import (
    orthonormal_basis, project_out, residualize, match_norm,
    subspace_alignment, random_subspace, random_directions,
)


def test_orthonormal_basis_is_orthonormal():
    rng = np.random.default_rng(0)
    A = rng.standard_normal((3, 32))
    Q = orthonormal_basis(A)
    assert Q.shape == (32, 3)
    np.testing.assert_allclose(Q.T @ Q, np.eye(3), atol=1e-10)


def test_orthonormal_basis_drops_dependent_directions():
    # d2 - d3 == d1 by construction, exactly our script-contrast situation.
    d1 = np.array([1.0, 0.0, 0.0, 0.0])
    d2 = np.array([1.0, 1.0, 0.0, 0.0])
    d3 = d2 - d1
    Q = orthonormal_basis(np.stack([d1, d2, d3]))
    assert Q.shape == (4, 2), "rank must be 2, not 3"


def test_orthonormal_basis_zero_vector_gives_empty():
    Q = orthonormal_basis(np.zeros((2, 8)))
    assert Q.shape == (8, 0)


def test_project_out_removes_component():
    d = np.array([1.0, 0.0, 0.0])
    Q = orthonormal_basis(d)
    v = np.array([3.0, 4.0, 0.0])
    r = project_out(v, Q)
    np.testing.assert_allclose(r, [0.0, 4.0, 0.0], atol=1e-12)
    assert abs(float((Q.T @ r)[0])) < 1e-12


def test_project_out_empty_basis_is_identity():
    v = np.array([1.0, 2.0, 3.0])
    np.testing.assert_allclose(project_out(v, np.zeros((3, 0))), v)


def test_project_out_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        project_out(np.ones(4), np.ones((3, 1)))


def test_residualize_is_orthogonal_and_norm_matched():
    rng = np.random.default_rng(7)
    d = 64
    script = rng.standard_normal(d)
    v = rng.standard_normal(d)
    out = residualize(v, script, norm_match=True)
    assert out["rank"] == 1
    assert not out["degenerate"]
    np.testing.assert_allclose(out["norm_after"], out["norm_before"], rtol=1e-10)
    q = out["Q"][:, 0]
    assert abs(float(q @ out["vector"])) < 1e-9
    assert 0.0 <= out["alignment"] <= 1.0


def test_residualize_without_norm_match_shrinks():
    rng = np.random.default_rng(1)
    v = rng.standard_normal(32)
    s = rng.standard_normal(32)
    out = residualize(v, s, norm_match=False)
    assert out["norm_after"] <= out["norm_before"] + 1e-12


def test_residualize_flags_degenerate_when_fully_aligned():
    d = np.array([1.0, 0.0, 0.0, 0.0])
    out = residualize(d, d, norm_match=True)
    assert out["degenerate"] is True, "must not amplify numerical noise"


def test_match_norm_rejects_negative_target():
    with pytest.raises(ValueError):
        match_norm(np.ones(3), -1.0)


def test_nonfinite_input_rejected():
    with pytest.raises(ValueError):
        residualize(np.array([1.0, np.nan]), np.array([1.0, 0.0]))


def test_subspace_alignment_bounds_and_extremes():
    e1 = np.array([1.0, 0.0, 0.0])
    Q = orthonormal_basis(e1)
    assert subspace_alignment(e1, Q) == pytest.approx(1.0)
    assert subspace_alignment(np.array([0.0, 1.0, 0.0]), Q) == pytest.approx(0.0)


def test_random_subspace_reproducible_and_orthonormal():
    A = random_subspace(50, 3, seed=123)
    B = random_subspace(50, 3, seed=123)
    np.testing.assert_allclose(A, B)
    np.testing.assert_allclose(A.T @ A, np.eye(3), atol=1e-10)


def test_random_control_removes_less_than_true_subspace_on_planted_data():
    """Planted ground truth: script nuisance + harm signal.

    The true script basis should remove MORE of the nuisance than a random
    same-rank basis. This is the discriminating control for H2.
    """
    rng = np.random.default_rng(11)
    d = 128
    script = rng.standard_normal(d); script /= np.linalg.norm(script)
    harm = rng.standard_normal(d); harm -= (harm @ script) * script
    harm /= np.linalg.norm(harm)
    v_pooled = 1.0 * harm + 0.6 * script
    true = residualize(v_pooled, script, norm_match=False)
    rand = residualize(v_pooled, random_directions(d, 1, seed=5), norm_match=False)
    assert true["removed_frac"] > rand["removed_frac"]
    # Residualized vector should retain most of the harm component.
    assert float(true["vector"] @ harm) > 0.9


def test_residualize_rejects_basis_passed_as_directions():
    """Regression: a [d,r] basis must not be silently reinterpreted as [r,d]."""
    v = np.ones(128)
    basis = random_subspace(128, 1, seed=2)     # [128, 1]
    with pytest.raises(ValueError, match="stacked as ROWS"):
        residualize(v, basis)
    # The documented escape hatch works.
    out = residualize(v, basis.T, norm_match=True)
    assert out["rank"] == 1
