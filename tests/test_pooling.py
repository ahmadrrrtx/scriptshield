"""D-016: last-token indexing must be correct under LEFT padding."""
import numpy as np
import pytest
from scriptshield.steering.pooling import last_token_index


def test_left_padding_last_token_is_final_position():
    mask = np.array([[0, 0, 1, 1, 1], [1, 1, 1, 1, 1]])
    np.testing.assert_array_equal(last_token_index(mask), [4, 4])
    # The buggy right-padding formula would give [2, 4] — wrong for row 0.
    assert not np.array_equal(mask.sum(1) - 1, last_token_index(mask))


def test_right_padding_matches_sum_minus_one():
    mask = np.array([[1, 1, 1, 0, 0], [1, 1, 1, 1, 1]])
    np.testing.assert_array_equal(last_token_index(mask), mask.sum(1) - 1)


def test_mixed_lengths_left_padded():
    mask = np.array([[0, 0, 0, 1], [0, 1, 1, 1], [1, 1, 1, 1]])
    np.testing.assert_array_equal(last_token_index(mask), [3, 3, 3])


def test_single_token_row():
    np.testing.assert_array_equal(last_token_index(np.array([[0, 0, 1]])), [2])


def test_all_padding_row_raises():
    with pytest.raises(ValueError, match="no real tokens"):
        last_token_index(np.array([[0, 0, 0]]))


def test_wrong_shape_raises():
    with pytest.raises(ValueError):
        last_token_index(np.ones(5))


def test_the_single_capture_implementation_uses_the_safe_helper():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src/scriptshield/models/runtime.py").read_text()
    assert "last_token_index(" in src, "runtime capture must use the padding-agnostic helper"
    assert '["attention_mask"].sum' not in src, (
        "attention_mask.sum(1)-1 is wrong under left padding (D-016)")
