import numpy as np
import pytest
from scriptshield.statistics.inference import (
    exact_mcnemar, cluster_bootstrap_ci, holm_correction, proportion, paired_rate_diff,
)


def test_mcnemar_no_discordant_pairs_gives_p_one():
    r = exact_mcnemar([0, 1, 1], [0, 1, 1])
    assert r["discordant"] == 0 and r["p_value"] == 1.0


def test_mcnemar_all_discordant_one_direction():
    r = exact_mcnemar([0] * 10, [1] * 10)
    assert r["b01"] == 10 and r["b10"] == 0
    assert r["p_value"] == pytest.approx(2 / 1024)


def test_mcnemar_known_small_case():
    # 5 one way, 1 the other: p = 2*(C(6,0)+C(6,1))/2^6 = 14/64
    r = exact_mcnemar([0,0,0,0,0,1], [1,1,1,1,1,0])
    assert r["p_value"] == pytest.approx(14/64)


def test_mcnemar_rejects_non_binary():
    with pytest.raises(ValueError):
        exact_mcnemar([0, 2], [1, 1])


def test_mcnemar_rejects_length_mismatch():
    with pytest.raises(ValueError):
        exact_mcnemar([0, 1], [1])


def test_proportion_keeps_unknown_in_denominator():
    p = proportion([1, 1, 0, 0], unknown=[0, 0, 1, 1])
    assert p.denominator == 4
    assert p.value == pytest.approx(0.5)
    assert p.unknown == 2


def test_proportion_empty_is_nan_not_zero():
    assert np.isnan(proportion([]).value)


def test_paired_rate_diff():
    assert paired_rate_diff([0,0,1,1], [1,1,1,1]) == pytest.approx(0.5)


def test_cluster_bootstrap_detects_consistent_improvement():
    fam = np.repeat(np.arange(20), 4)
    a = np.tile([0,0,0,1], 20)
    b = np.tile([1,1,0,1], 20)
    r = cluster_bootstrap_ci(a, b, fam, n_boot=2000, seed=7)
    assert r["estimate"] == pytest.approx(0.5)
    assert r["ci_low"] > 0
    assert r["n_families"] == 20


def test_cluster_bootstrap_null_brackets_zero():
    rng = np.random.default_rng(0)
    fam = np.repeat(np.arange(60), 4)
    a = rng.integers(0, 2, 240)
    b = a.copy()
    r = cluster_bootstrap_ci(a, b, fam, n_boot=2000, seed=7)
    assert r["ci_low"] <= 0 <= r["ci_high"]
    assert r["estimate"] == 0.0


def test_cluster_bootstrap_resamples_families_not_rows():
    # Perfectly correlated within family: row bootstrap would understate variance.
    fam = np.repeat(np.arange(10), 8)
    a = np.zeros(80, dtype=int)
    b = np.concatenate([np.ones(40, dtype=int), np.zeros(40, dtype=int)])
    r = cluster_bootstrap_ci(a, b, fam, n_boot=4000, seed=3)
    assert r["n_families"] == 10
    assert (r["ci_high"] - r["ci_low"]) > 0.5, "cluster CI must be wide"


def test_holm_known_values():
    r = holm_correction([0.01, 0.04, 0.03])
    np.testing.assert_allclose(r["adjusted_p"], [0.03, 0.06, 0.06], atol=1e-12)
    assert r["reject"] == [True, False, False]


def test_holm_monotone_and_capped():
    r = holm_correction([0.5, 0.6, 0.9])
    assert all(p <= 1.0 for p in r["adjusted_p"])
    assert r["reject"] == [False, False, False]


def test_holm_rejects_invalid_p():
    with pytest.raises(ValueError):
        holm_correction([0.1, 1.5])
