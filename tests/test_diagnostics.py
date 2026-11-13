"""Synthetic ground-truth tests for the cross-fitted mechanism diagnostics."""
import numpy as np
import pytest

from scriptshield.steering.diagnostics import layer_diagnostics, sign_flip_test


def make(n=40, d=96, a_ur=3.0, a_ro=3.0, leak=0.0, noise=1.0, seed=0):
    """harm direction h, script direction s (orthogonal). harmful = benign + a_f*h (+ leak*s for ur)."""
    rng = np.random.default_rng(seed)
    h = np.zeros(d); h[0] = 1.0
    s = np.zeros(d); s[1] = 1.0
    base = rng.normal(scale=noise, size=(n, d))                       # family-specific content
    out = {}
    for form, off, a, lk in (("ur", +2.0, a_ur, leak), ("ro", -2.0, a_ro, 0.0)):
        ben = base + off * s + rng.normal(scale=noise * 0.5, size=(n, d))
        out[(form, "benign")] = ben
        out[(form, "harmful")] = ben + a * h + lk * s + rng.normal(scale=noise * 0.5, size=(n, d))
    return out


def test_no_leak_gives_no_script_alignment():
    r = layer_diagnostics(make(leak=0.0), n_boot=200, n_perm=2000)
    h2 = r["h2_script_alignment"]
    assert abs(h2["cross_fitted_cosine"]) < 0.1
    assert h2["cross_fitted_projection_test"]["p_two_sided"] > 0.05


def test_asymmetric_leak_is_detected_and_signed():
    r = layer_diagnostics(make(leak=3.0), n_boot=200, n_perm=2000)
    h2 = r["h2_script_alignment"]
    assert h2["cross_fitted_cosine"] > 0.3
    assert h2["cross_fitted_projection_test"]["p_two_sided"] < 0.01
    assert h2["in_sample_abs_cosine"] > 0.3


def test_weaker_roman_harm_signal_is_detected():
    r = layer_diagnostics(make(a_ur=3.0, a_ro=1.5), n_boot=200, n_perm=2000)
    assert 0.35 < r["norm_ratio_ro_over_ur"]["value"] < 0.75
    h1 = r["h1_representation"]
    assert 0.3 < h1["ratio_ro_over_ur"] < 0.7
    assert h1["paired_difference_test_ur_minus_ro"]["p_two_sided"] < 0.01
    assert h1["paired_difference_test_ur_minus_ro"]["mean"] > 0


def test_equal_harm_signal_is_not_flagged():
    r = layer_diagnostics(make(a_ur=3.0, a_ro=3.0, seed=3), n_boot=200, n_perm=2000)
    assert r["h1_representation"]["paired_difference_test_ur_minus_ro"]["p_two_sided"] > 0.05


def test_shared_direction_split_half_is_near_ceiling():
    r = layer_diagnostics(make(), n_boot=100, n_perm=500)
    assert r["cos_v_ur_v_ro_split_half"]["disattenuated"] > 0.85


def test_sign_flip_exact_small_n():
    assert sign_flip_test(np.ones(6))["p_two_sided"] == pytest.approx(2 / 64)
    assert sign_flip_test(np.array([1.0, -1.0, 1.0, -1.0]))["p_two_sided"] == 1.0


def test_misaligned_arrays_are_rejected():
    bad = make()
    bad[("ro", "benign")] = bad[("ro", "benign")][:-1]
    with pytest.raises(ValueError, match="family-aligned"):
        layer_diagnostics(bad)
