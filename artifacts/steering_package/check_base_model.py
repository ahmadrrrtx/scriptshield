#!/usr/bin/env python3
"""Check a download of this package and a local copy of the base model BEFORE steering anything.

    python check_base_model.py                                   # the package only
    python check_base_model.py --model-dir /path/to/tiny-aya-fire            # plus the base model (hashes the weights)
    python check_base_model.py --model-dir /path/to/tiny-aya-fire --quick    # plus the base model, configuration only

It needs numpy and the standard library and does not load the model.

Why it exists. `apply_steering.py` refuses a damaged package (checksum, shape, orientation). It does NOT check
which model it is given. A model with another hidden size fails later with a tensor error; a model with the
SAME size (the other Tiny Aya variants) would be steered silently with vectors that were never made for it.
This script closes that gap without touching the loader, whose exact bytes were verified on a GPU.

Exit code 0: everything checked is as expected. 1: a mismatch was found; do not steer. 2: a check could not run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HIDDEN_KEYS = ("hidden_size", "d_model", "n_embd")
LAYER_KEYS = ("num_hidden_layers", "n_layer", "num_layers")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_array(v: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(v, dtype=np.float64).tobytes()).hexdigest()


def package_problems(pkg_dir: Path) -> list[str]:
    """Manifest and vector file must agree in both directions; listed file checksums must match."""
    problems: list[str] = []
    manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    with np.load(pkg_dir / manifest["vector_file"]) as z:
        arrays = {k: z[k] for k in z.files}
    listed, present = set(manifest["arms"]), set(arrays)
    for name in sorted(listed - present):
        problems.append(f"vector '{name}' is in the manifest but not in {manifest['vector_file']}")
    for name in sorted(present - listed):
        problems.append(f"vector '{name}' is in {manifest['vector_file']} but not in the manifest (it has no checksum)")
    for name in sorted(listed & present):
        v, meta = arrays[name], manifest["arms"][name]
        if v.shape != (manifest["hidden_dim"],):
            problems.append(f"vector '{name}' has shape {v.shape}, expected ({manifest['hidden_dim']},)")
            continue
        if not np.all(np.isfinite(v)):
            problems.append(f"vector '{name}' contains NaN or infinite values")
        if sha256_array(v) != meta["sha256"]:
            problems.append(f"vector '{name}' does not match its checksum in the manifest")
        if abs(float(np.linalg.norm(v)) - meta["norm"]) > 1e-6 * max(1.0, meta["norm"]):
            problems.append(f"vector '{name}' has norm {float(np.linalg.norm(v)):.6f}, the manifest says {meta['norm']:.6f}")
    sums = pkg_dir / "SHA256SUMS"
    if sums.exists():
        for line in sums.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, name = line.split(maxsplit=1)
            f = pkg_dir / name.strip().lstrip("*")
            if not f.exists():
                problems.append(f"{name.strip()} is listed in SHA256SUMS but missing")
            elif sha256_file(f) != digest:
                problems.append(f"{name.strip()} does not match SHA256SUMS")
    return problems


def config_problems(config: dict, manifest: dict) -> list[str]:
    """Architecture of the model against what the vectors were made for. An unreadable value is a problem."""
    problems: list[str] = []
    hidden = next((config[k] for k in HIDDEN_KEYS if k in config), None)
    layers = next((config[k] for k in LAYER_KEYS if k in config), None)
    if hidden is None:
        problems.append("config.json does not state the hidden size; cannot confirm that the vectors fit")
    elif int(hidden) != int(manifest["hidden_dim"]):
        problems.append(f"hidden size is {hidden}; the vectors have {manifest['hidden_dim']} dimensions")
    if layers is None:
        problems.append("config.json does not state the number of layers; cannot confirm that the steered block exists")
    elif int(manifest["layer"]) >= int(layers):
        problems.append(f"the model has {layers} blocks; the vectors are for block {manifest['layer']} (0-based)")
    return problems


def weight_problems(model_dir: Path, manifest: dict) -> list[str]:
    """The weight shards and the tokenizer must be the files the vectors were extracted from."""
    problems: list[str] = []
    for name, digest in manifest["base_model"]["weights_sha256"].items():
        f = model_dir / name
        if not f.exists():
            problems.append(f"{name} is missing from the model folder")
        elif sha256_file(f) != digest:
            problems.append(f"{name} is not the file the vectors were made from (sha256 differs)")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", default=str(HERE))
    ap.add_argument("--model-dir", default=None, help="local folder of CohereLabs/tiny-aya-fire")
    ap.add_argument("--quick", action="store_true", help="check the model configuration only, do not hash the weights")
    a = ap.parse_args()
    pkg = Path(a.package)
    try:
        manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
        problems = package_problems(pkg)
    except (OSError, KeyError, ValueError) as e:
        print(f"COULD NOT CHECK the package: {e}")
        return 2
    print(f"package {manifest['package_version']}: {len(manifest['arms'])} vectors of {manifest['hidden_dim']} dimensions "
          f"for block {manifest['layer']} of {manifest['base_model']['hf_repo']} @ {manifest['base_model']['hf_revision'][:8]}")
    weights_checked = False
    if a.model_dir:
        model_dir = Path(a.model_dir)
        try:
            config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"COULD NOT CHECK the model: no readable config.json in {model_dir} ({e})")
            return 2
        problems += config_problems(config, manifest)
        if not a.quick:
            problems += weight_problems(model_dir, manifest)
            weights_checked = True
    for p in problems:
        print("MISMATCH:", p)
    if problems:
        print("Do not steer with this combination.")
        return 1
    if not a.model_dir:
        print("OK: the package is intact. The base model was not checked (pass --model-dir).")
    elif weights_checked:
        print("OK: the package is intact and the model files are the ones the vectors were made from.")
    else:
        print("OK: the package is intact and the model has the right shape. The weights were NOT compared (--quick): "
              "the other Tiny Aya variants have the same shape and would pass this check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
