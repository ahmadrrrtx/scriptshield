"""Real SafeTune integration. REMOTE ONLY (requires torch + transformers).

Uses the official public API for both extraction and application:
    safetune.interventions.steer.caa.extract_caa_vectors(...)
    safetune.interventions.steer.caa.CAAModel(model, vectors, strength)

ScriptShield's contribution sits strictly BETWEEN those two calls: we transform
the extracted vector dict. We do not fork or monkey-patch SafeTune.

Sign (verified in source at 26f59e6, DECISIONS D-006):
    extract_caa_vectors(positive=P, negative=N) -> mean(P) - mean(N)
    CAAModel applies h + strength * v
So positive=harmful, negative=benign, strength>0 increases refusal.
The empirical sign test in scripts/smoke_model.py MUST confirm this.
"""
from __future__ import annotations

from typing import Any


def _require_safetune():
    try:
        import safetune
        from safetune.interventions.steer.caa import CAAModel, extract_caa_vectors
    except ImportError as e:
        raise ImportError(
            "SafeTune is not installed (remote GPU env only). Install the pinned commit:\n"
            "  pip install 'git+https://github.com/Lexsi-Labs/SafeTune"
            "@26f59e6d1bdcacafe5f2be3b8d982fb214369659'\n"
            "Requires Python>=3.12, torch>=2.7, transformers>=5.15,<6."
        ) from e
    return safetune, CAAModel, extract_caa_vectors


def make_caa_config(layers: list[int], pool_method: str = "last_token",
                    normalize: bool = False) -> Any:
    """Official CAAConfig. Without this, SafeTune extracts at ALL decoder layers,
    which is far more compute than we want and not what the protocol specifies."""
    _require_safetune()
    from safetune.interventions.steer.caa import CAAConfig
    return CAAConfig(target_layers=list(layers), pool_method=pool_method,
                     normalize=normalize)


# Markers that only appear in ALREADY-RENDERED chat prompts.
_TEMPLATE_MARKERS = ("<|START_OF_TURN_TOKEN|>", "<BOS_TOKEN>", "<|USER_TOKEN|>", "<|CHATBOT_TOKEN|>",
                     "<|im_start|>", "<start_of_turn>", "[INST]", "<|start_header_id|>")


def assert_raw_prompts(prompts: list[str]) -> None:
    """Refuse pre-rendered prompts (D-021).

    SafeTune's extractor applies the chat template ITSELF. Handing it a string that
    was already rendered wraps a whole conversation, BOS token and system preamble
    included, inside a second user turn. Nothing raises; the vector is simply
    extracted from a different prompt than the one that is later steered.
    """
    for p in prompts:
        if not isinstance(p, str) or not p.strip():
            raise ValueError("prompts must be non-empty strings")
        hit = next((m for m in _TEMPLATE_MARKERS if m in p), None)
        if hit:
            raise ValueError(
                f"prompt already contains chat-template marker {hit!r}. Pass RAW user text: "
                "SafeTune applies the chat template itself (double templating, D-021).")


def extract_contrast(model: Any, tokenizer: Any, positive_prompts: list[str],
                     negative_prompts: list[str], layers: list[int],
                     config: Any = None, batch_size: int | None = None) -> dict[int, Any]:
    """Official SafeTune contrast extraction: {layer: mean(positive) - mean(negative)}.

    ``batch_size=None`` uses the public CAA entry point ``extract_caa_vectors``.
    An explicit ``batch_size`` uses SafeTune's ``SteeringVectorExtractor`` directly
    (the engine ``extract_caa_vectors`` itself wraps, whose CAAConfig exposes no
    batch size) so large prompt sets cannot exhaust GPU memory. Same maths, same
    hooks, same pooling.
    """
    assert_raw_prompts(positive_prompts)
    assert_raw_prompts(negative_prompts)
    _, _, extract_caa_vectors = _require_safetune()
    cfg = config if config is not None else make_caa_config(layers)
    if batch_size is None:
        vecs = extract_caa_vectors(model=model, tokenizer=tokenizer,
                                   positive_prompts=positive_prompts,
                                   negative_prompts=negative_prompts, config=cfg)
    else:
        from safetune.core.runtime.inference.vector_extraction import (
            SteeringVectorExtractor, VectorExtractionConfig)
        ve = VectorExtractionConfig(target_layers=list(cfg.target_layers), batch_size=int(batch_size),
                                    pool_method=cfg.pool_method, normalize=cfg.normalize)
        vecs = SteeringVectorExtractor(model, tokenizer, ve).extract(
            safe_prompts=positive_prompts, unsafe_prompts=negative_prompts)
    if not isinstance(vecs, dict) or not vecs:
        raise RuntimeError(f"SafeTune returned no vectors: {type(vecs)}")
    vecs = {int(k): v for k, v in vecs.items()}
    missing = sorted(set(int(l) for l in layers) - set(vecs))
    if missing:
        raise RuntimeError(f"SafeTune returned no vector for layers {missing}")
    for k, v in vecs.items():
        if getattr(v, "ndim", None) != 1:
            raise RuntimeError(f"layer {k}: expected 1-D vector, got shape {getattr(v, 'shape', None)}")
    return vecs


def extract_vectors(model: Any, tokenizer: Any,
                    harmful_prompts: list[str], benign_prompts: list[str],
                    layers: list[int], config: Any = None,
                    batch_size: int | None = None) -> dict[int, Any]:
    """Harm contrast with EXPLICIT naming: {layer: mean(harmful) - mean(benign)}."""
    return extract_contrast(model, tokenizer, harmful_prompts, benign_prompts, layers,
                            config=config, batch_size=batch_size)


def apply_vectors(model: Any, vectors: dict[int, Any], strength: float) -> Any:
    """Wrap a model with official SafeTune CAAModel.

    IMPORTANT (verified at 26f59e6): the constructor does NOT install hooks.
    Hooks are active only inside ``with wrapper:`` or during
    ``wrapper.generate(...)`` / ``wrapper(...)``. Calling ``wrapper.model.generate``
    directly produces UNSTEERED output. Always use ``wrapper.generate`` or the
    context manager, and verify with ``steering_is_active``.
    """
    _, CAAModel, _ = _require_safetune()
    return CAAModel(model=model, vectors=vectors, strength=strength)


def steering_is_active(wrapper: Any) -> bool:
    """True only if CAAModel currently has forward hooks installed."""
    return bool(getattr(wrapper, "_handles", []))


def transform_vector_dict(vectors: dict[int, Any],
                          script_by_layer: dict[int, Any],
                          norm_match: bool = True) -> tuple[dict[int, Any], dict]:
    """Residualize every layer's vector against that layer's script basis.

    Accepts and returns torch tensors (converted to numpy float64 internally for
    stable SVD, then cast back to the original dtype/device).
    """
    import numpy as np
    import torch

    from .residualize import residualize

    out, diag = {}, {}
    for layer, v in vectors.items():
        if layer not in script_by_layer:
            raise KeyError(f"no script basis for layer {layer}")
        dtype, device = v.dtype, v.device
        res = residualize(v.detach().to("cpu", torch.float64).numpy(),
                          np.asarray(script_by_layer[layer], dtype=np.float64),
                          norm_match=norm_match)
        out[layer] = torch.as_tensor(res["vector"], dtype=dtype, device=device)
        diag[layer] = {k: val for k, val in res.items() if k not in {"vector", "Q"}}
        diag[layer]["rank"] = int(res["rank"])
    return out, diag
