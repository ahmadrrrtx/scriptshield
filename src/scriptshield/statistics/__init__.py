"""Independent statistics. AuditKIT's paired-bootstrap significance is NOT used
(DECISIONS D-009): we compute exact McNemar, family-cluster bootstrap and Holm."""
from .inference import (
    exact_mcnemar, cluster_bootstrap_diff, cluster_bootstrap_ci, holm_correction,
    proportion, paired_rate_diff,
)
__all__ = ["exact_mcnemar", "cluster_bootstrap_diff", "cluster_bootstrap_ci",
           "holm_correction", "proportion", "paired_rate_diff"]
