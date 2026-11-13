"""Padding-correct last-token indexing.

THE HAZARD (D-016)
------------------
With LEFT padding, real tokens end at index T-1 for every row, so the correct
last-token index is T-1. ``attention_mask.sum(1) - 1`` is the correct index only
for RIGHT padding; using it with left padding selects a token in the middle of
the sequence (or a pad slot), silently corrupting every extracted vector.

SafeTune's extractor uses ``hidden[:, -1, :]`` together with left padding, which
is correct. Our capture must agree with it.

``last_token_index`` below is correct for BOTH padding sides, so a future change
of padding_side cannot silently break extraction.
"""
from __future__ import annotations

import numpy as np


def last_token_index(attention_mask: np.ndarray) -> np.ndarray:
    """Index of the last non-pad token per row, for left OR right padding.

    attention_mask: [B, T] of 0/1. Returns [B] int64.
    Rows that are entirely padding raise, rather than returning a bogus index.
    """
    m = np.asarray(attention_mask)
    if m.ndim != 2:
        raise ValueError(f"attention_mask must be [B, T], got {m.shape}")
    if not np.any(m, axis=1).all():
        raise ValueError("row with no real tokens (all padding)")
    # Position of the last 1, scanning from the right.
    t = m.shape[1]
    rev_first = np.argmax(m[:, ::-1], axis=1)
    return (t - 1 - rev_first).astype(np.int64)
