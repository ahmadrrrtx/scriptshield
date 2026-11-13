"""Steering: CAA construction, script-subspace residualization, controls."""
from .residualize import (
    orthonormal_basis,
    project_out,
    residualize,
    match_norm,
    subspace_alignment,
    random_subspace, random_directions,
)
from .caa import contrast_vector, pooled_vector, script_contrast, shuffled_label_vector

__all__ = [
    "orthonormal_basis", "project_out", "residualize", "match_norm",
    "subspace_alignment", "random_subspace", "random_directions",
    "contrast_vector", "pooled_vector", "script_contrast", "shuffled_label_vector",
]
