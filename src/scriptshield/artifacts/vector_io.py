"""Vector serialization with a checksummed, self-describing manifest.

Uses .npz (numpy) so artifacts are inspectable without torch. A torch-backed
loader is provided for the remote env. Metadata records orientation, layers,
provenance SHAs and norm so a vector can never be applied with the wrong sign
or at the wrong layer by accident.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ORIENTATION = "harmful_minus_benign"


def vector_checksum(vectors: dict[int, np.ndarray]) -> str:
    h = hashlib.sha256()
    for layer in sorted(vectors):
        h.update(str(layer).encode())
        h.update(np.ascontiguousarray(vectors[layer], dtype=np.float64).tobytes())
    return h.hexdigest()


def save_vectors(path: str | Path, vectors: dict[int, np.ndarray],
                 metadata: dict) -> dict:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    arrs = {f"layer_{k}": np.asarray(v, dtype=np.float64) for k, v in vectors.items()}
    np.savez(p, **arrs)
    manifest = {
        "artifact_type": "scriptshield_steering_vector",
        "format": "npz",
        "orientation": ORIENTATION,
        "application": "h <- h + alpha * v  (SafeTune CAAModel semantics)",
        "layers": sorted(int(k) for k in vectors),
        "hidden_dim": int(next(iter(vectors.values())).shape[0]),
        "sha256_vectors": vector_checksum(vectors),
        "norms": {str(k): float(np.linalg.norm(v)) for k, v in vectors.items()},
        "license_note": ("Derived from Cohere Labs Tiny Aya weights: CC-BY-NC + AUP. "
                         "Non-commercial. Base weights are NOT included."),
        **metadata,
    }
    mpath = p.with_suffix(".manifest.json")
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def load_vectors(path: str | Path, verify: bool = True) -> tuple[dict[int, np.ndarray], dict]:
    p = Path(path)
    manifest = json.loads(p.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    with np.load(p) as z:
        vecs = {int(k.split("_")[1]): z[k].copy() for k in z.files}
    if verify:
        got = vector_checksum(vecs)
        if got != manifest["sha256_vectors"]:
            raise ValueError(f"vector checksum mismatch: expected "
                             f"{manifest['sha256_vectors']}, got {got}")
        if manifest.get("orientation") != ORIENTATION:
            raise ValueError(f"unexpected orientation {manifest.get('orientation')!r}; "
                             "refusing to apply a vector with unknown sign")
    return vecs, manifest
