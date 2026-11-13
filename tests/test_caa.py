import numpy as np
import pytest
from scriptshield.steering.caa import (
    contrast_vector, pooled_vector, script_contrast, shuffled_label_vector,
)


def test_contrast_sign_is_harmful_minus_benign():
    h = np.array([[2.0, 0.0], [4.0, 0.0]])
    b = np.array([[0.0, 1.0], [0.0, 3.0]])
    np.testing.assert_allclose(contrast_vector(h, b), [3.0, -2.0])


def test_contrast_rejects_empty_group():
    with pytest.raises(ValueError):
        contrast_vector(np.zeros((0, 4)), np.zeros((2, 4)))


def test_contrast_rejects_dim_mismatch():
    with pytest.raises(ValueError):
        contrast_vector(np.zeros((2, 4)), np.zeros((2, 5)))


def test_pooled_weights_forms_equally_not_samples():
    per_form = {"ur": np.array([1.0, 0.0]), "ro": np.array([3.0, 0.0])}
    np.testing.assert_allclose(pooled_vector(per_form, ("ur", "ro")), [2.0, 0.0])


def test_pooled_missing_form_raises():
    with pytest.raises(KeyError):
        pooled_vector({"ur": np.ones(3)}, ("ur", "ro"))


def test_script_contrast_uses_benign_only_by_signature():
    benign = {"ur": np.array([[1.0, 0.0]]), "ro": np.array([[0.0, 1.0]])}
    np.testing.assert_allclose(script_contrast(benign, "ur", "ro"), [1.0, -1.0])


def test_shuffled_label_vector_is_reproducible():
    rng = np.random.default_rng(0)
    h, b = rng.standard_normal((10, 8)), rng.standard_normal((10, 8))
    a = shuffled_label_vector(h, b, seed=42)
    c = shuffled_label_vector(h, b, seed=42)
    np.testing.assert_allclose(a, c)


def test_shuffled_control_has_smaller_signal_than_true_on_planted_data():
    rng = np.random.default_rng(3)
    d, n = 64, 200
    signal = rng.standard_normal(d); signal /= np.linalg.norm(signal)
    h = rng.standard_normal((n, d)) * 0.1 + signal
    b = rng.standard_normal((n, d)) * 0.1 - signal
    true_norm = np.linalg.norm(contrast_vector(h, b))
    null_norm = np.linalg.norm(shuffled_label_vector(h, b, seed=1))
    assert true_norm > 5 * null_norm
