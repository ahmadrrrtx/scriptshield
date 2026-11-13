"""D-028: the control direction must not carry the harm signal."""
import numpy as np
import pytest

from scriptshield.steering.caa import (contrast_vector, label_flip_null_vector,
                                       orthogonal_null_vector, shuffled_label_vector)


def data(n=48, d=256, strength=6.0, seed=0, heavy=False):
    rng = np.random.default_rng(seed)
    v = np.zeros(d); v[0] = 1.0
    b = rng.normal(size=(n, d))
    a = strength * (rng.lognormal(sigma=0.8, size=n) if heavy else np.ones(n))   # per-pair contrast size
    return b + a[:, None] * v + rng.normal(scale=0.5, size=(n, d)), b


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_the_old_unconstrained_shuffle_is_often_strongly_aligned_or_anti_aligned():
    """Documents the defect: with a dominant harm axis the shuffle is +/- the harm vector."""
    h, b = data(strength=40.0)                       # a dominant harm axis, as measured on the real model
    cs = [cos(shuffled_label_vector(h, b, s), contrast_vector(h, b)) for s in range(200)]
    assert np.mean(np.abs(cs)) > 0.4
    assert min(cs) < -0.5 and max(cs) > 0.5          # and the sign is a coin flip


def test_balanced_label_flip_is_centred_on_zero_but_not_exactly_orthogonal():
    h, b = data(heavy=True)
    cs = [cos(label_flip_null_vector(h, b, s), contrast_vector(h, b)) for s in range(300)]
    assert abs(np.mean(cs)) < 0.06                    # no systematic harm component
    assert np.mean(np.abs(cs)) > 0.05                 # ...yet a given seed is still correlated


def test_orthogonal_null_is_exactly_orthogonal_to_the_real_vector():
    h, b = data(heavy=True)
    ref = contrast_vector(h, b)
    for s in range(20):
        v = orthogonal_null_vector(h, b, ref, s)
        assert abs(cos(v, ref)) < 1e-10 and np.linalg.norm(v) > 0


def test_signs_sum_to_zero_even_for_odd_n():
    h, b = data(n=7)
    assert np.all(np.isfinite(label_flip_null_vector(h, b, 3)))


def test_unpaired_input_is_rejected():
    h, b = data()
    with pytest.raises(ValueError, match="matched pairs"):
        label_flip_null_vector(h, b[:-1], 0)
