"""Configuration loading and validation (no heavy deps)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PRIMARY_FORMS = ("ur", "ro")      # approved Change 1: primary contrast
SECONDARY_FORMS = ("cm",)          # code-mixed: secondary, never pooled into primary
REFERENCE_FORMS = ("en",)          # English: reference only
ALL_FORMS = PRIMARY_FORMS + SECONDARY_FORMS + REFERENCE_FORMS
SAFETY_LABELS = ("harmful", "benign")
SPLITS = ("calibration", "dev", "test")


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected a mapping at top level")
    return data


@dataclass
class ModelSpec:
    repo_id: str
    revision: str
    role: str
    dtype: str = "bfloat16"

    def validate(self) -> list[str]:
        errs = []
        if not self.repo_id.startswith("CohereLabs/"):
            errs.append(f"{self.repo_id}: hackathon requires a Cohere Labs model")
        if len(self.revision) != 40:
            errs.append(f"{self.repo_id}: revision must be a full 40-char SHA, got {self.revision!r}")
        return errs


@dataclass
class SteeringSpec:
    candidate_layers: list[int]
    alphas: list[float]
    pool_method: str = "last_token"
    subspace_rank: int = 1
    norm_match: bool = True
    seed: int = 20261103
    forms_in_pooled: tuple[str, ...] = PRIMARY_FORMS

    def validate(self) -> list[str]:
        errs = []
        if self.pool_method not in {"last_token", "mean"}:
            errs.append(f"pool_method must be last_token|mean, got {self.pool_method}")
        if self.subspace_rank < 1:
            errs.append("subspace_rank must be >= 1")
        if any(f not in ALL_FORMS for f in self.forms_in_pooled):
            errs.append(f"unknown form in forms_in_pooled: {self.forms_in_pooled}")
        # Approved Change 1: English/code-mixed must not silently enter the primary vector.
        if set(self.forms_in_pooled) & (set(SECONDARY_FORMS) | set(REFERENCE_FORMS)):
            errs.append("primary pooled vector must not include code-mixed or English forms")
        if any(a <= 0 for a in self.alphas):
            errs.append("alphas must be positive; sign is handled explicitly, not via negative alpha")
        return errs
