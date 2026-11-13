#!/usr/bin/env python3
"""ScriptShield steering package - standalone loader (no ScriptShield code needed).

Applies a refusal-steering vector to CohereLabs/tiny-aya-fire at inference time through
Lexsi SafeTune's CAAModel:   h_L  <-  h_L + alpha * v     (output of decoder block L)

Requirements: numpy, torch, transformers, safetune (the pinned commit is in manifest.json).
The base model is NOT part of this package. You need your own access to it under the
Cohere Labs CC-BY-NC licence and Acceptable Use Policy.

  python apply_steering.py --model-dir /path/to/tiny-aya-fire --arm pooled --prompt "..."
  python apply_steering.py --model-dir /path/to/tiny-aya-fire --verify expected_outputs.jsonl

Four things this file gets right on purpose, because each one fails SILENTLY otherwise
(all four were found the hard way; see DECISIONS.md D-014, D-016, D-018, D-020):
  1. steering is live only through ``wrapper.generate`` - ``wrapper.model.generate`` is unsteered;
  2. the tokenizer pads on the LEFT, so the last position is always the last prompt token;
  3. a chat-templated prompt is tokenised with ``add_special_tokens=False`` (the template
     already starts with <BOS_TOKEN>; the default call would produce two);
  4. generation stops on the real end-of-turn tokens, not only on <EOS_TOKEN>.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
END_OF_TURN_TOKENS = ("<|END_RESPONSE|>", "<|END_OF_TURN_TOKEN|>", "<EOS_TOKEN>")
ORIENTATION = "harmful_minus_benign"


# --------------------------------------------------------------------------- package
def sha256_array(v: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(v, dtype=np.float64).tobytes()).hexdigest()


def load_package(pkg_dir: str | Path = HERE) -> tuple[dict[str, np.ndarray], dict]:
    """Returns ({arm name: vector}, manifest). Refuses a package whose checksums do not match."""
    pkg_dir = Path(pkg_dir)
    manifest = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("orientation") != ORIENTATION:
        raise ValueError(f"unexpected orientation {manifest.get('orientation')!r}: refusing to guess the sign")
    with np.load(pkg_dir / manifest["vector_file"]) as z:
        vectors = {k: z[k].astype(np.float64) for k in z.files}
    for name, meta in manifest["arms"].items():
        if name not in vectors:
            raise ValueError(f"vector {name!r} is listed in the manifest but missing from the file")
        if sha256_array(vectors[name]) != meta["sha256"]:
            raise ValueError(f"checksum mismatch for vector {name!r}")
        if vectors[name].shape != (manifest["hidden_dim"],):
            raise ValueError(f"vector {name!r} has shape {vectors[name].shape}")
    return vectors, manifest


# ----------------------------------------------------------------------------- model
def load_base(model_ref: str, dtype: str = "float16", device: int | None = 0, revision: str | None = None):
    """(tokenizer, model). ``model_ref`` is a local folder or a Hub id you have access to."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    local = Path(str(model_ref)).exists()
    kw = {} if (local or revision is None) else {"revision": revision}
    try:
        tok = AutoTokenizer.from_pretrained(str(model_ref), **kw)
    except Exception:                                  # tokenizer class renamed across versions
        from transformers import PreTrainedTokenizerFast
        tok = PreTrainedTokenizerFast.from_pretrained(str(model_ref), **kw)
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    mkw = {"low_cpu_mem_usage": True, **kw,
           "device_map": {"": device} if (device is not None and torch.cuda.is_available()) else None}
    td = getattr(torch, dtype)
    try:
        model = AutoModelForCausalLM.from_pretrained(str(model_ref), dtype=td, **mkw)
    except TypeError:                                  # older transformers spelling
        model = AutoModelForCausalLM.from_pretrained(str(model_ref), torch_dtype=td, **mkw)
    model.eval()
    return tok, model


def render(tok, text: str) -> str:
    """One user turn + generation prompt. The model's own template adds its default preamble."""
    if getattr(tok, "chat_template", None) is None:
        return text
    return tok.apply_chat_template([{"role": "user", "content": text}], tokenize=False,
                                   add_generation_prompt=True)


def eos_token_ids(tok, model) -> list[int]:
    ids: list[int] = []
    unk = getattr(tok, "unk_token_id", None)
    for cand in (getattr(tok, "eos_token_id", None), getattr(model.config, "eos_token_id", None)):
        for c in (cand if isinstance(cand, (list, tuple)) else [cand]):
            if c is not None:
                ids.append(int(c))
    vocab = tok.get_vocab()
    for name in END_OF_TURN_TOKENS:
        if name in vocab and vocab[name] != unk:
            ids.append(int(vocab[name]))
    return sorted(set(ids))


def make_wrapper(model, vector: np.ndarray, layer: int, alpha: float):
    """SafeTune CAAModel adding ``alpha * vector`` to the output of decoder block ``layer``."""
    import torch
    from safetune.interventions.steer.caa import CAAModel
    return CAAModel(model=model, vectors={int(layer): torch.as_tensor(vector, dtype=torch.float32)},
                    strength=float(alpha))


def generate(model, tok, prompts: list[str], wrapper=None, max_new_tokens: int = 64,
             batch_size: int = 8) -> list[str]:
    """Greedy decoding. Pass ``wrapper`` to steer; omit it for the unsteered model."""
    import torch
    target = wrapper.generate if wrapper is not None else model.generate      # (1) never wrapper.model.generate
    if tok.padding_side != "left":                                             # (2)
        raise RuntimeError("tokenizer.padding_side must be 'left'")
    eos = eos_token_ids(tok, model)                                            # (4)
    device = model.get_input_embeddings().weight.device
    templated = getattr(tok, "chat_template", None) is not None
    outs: list[str] = []
    for i in range(0, len(prompts), batch_size):
        kw = {"return_tensors": "pt", "padding": True}
        if templated:
            kw["add_special_tokens"] = False                                   # (3)
        enc = tok([render(tok, p) for p in prompts[i:i + batch_size]], **kw)
        enc = {k: enc[k].to(device) for k in ("input_ids", "attention_mask")}
        with torch.no_grad():
            gen = target(**enc, max_new_tokens=max_new_tokens, do_sample=False,
                         pad_token_id=tok.pad_token_id, eos_token_id=eos)
        outs.extend(t.strip() for t in tok.batch_decode(gen[:, enc["input_ids"].shape[1]:],
                                                        skip_special_tokens=True))
    if wrapper is not None and getattr(wrapper, "_handles", []):
        raise RuntimeError("steering hooks are still installed after generation")
    return outs


def describe_layer(model, layer: int) -> dict:
    """Module tree of the steered block (which sub-modules exist, which have a bias)."""
    from safetune._refusal_helpers import _get_decoder_layers
    block = _get_decoder_layers(model)[layer]
    mods = []
    for name, m in block.named_modules():
        if name and not list(m.children()):
            bias = getattr(m, "bias", None)
            mods.append({"name": name, "type": type(m).__name__,
                         "has_bias": bias is not None,
                         "weight_shape": list(m.weight.shape) if getattr(m, "weight", None) is not None else None})
    return {"block_type": type(block).__name__, "leaf_modules": mods,
            "any_bias_in_block": any(m["has_bias"] for m in mods)}


# ---------------------------------------------------------------------------- verify
def verify(model, tok, vectors: dict, manifest: dict, expected_path: str | Path) -> dict:
    """Re-generate logged outputs and compare sha256(text). Exact reproduction is the criterion."""
    rows = [json.loads(l) for l in Path(expected_path).read_text(encoding="utf-8").splitlines() if l.strip()]
    report: dict = {"n": len(rows), "arms": {}, "mismatches": []}
    inf = manifest["inference"]
    produced: dict = {}
    for arm in sorted({r["arm"] for r in rows}, key=lambda a: (a != "unsteered", a)):
        sel = sorted((r for r in rows if r["arm"] == arm), key=lambda r: r["index"])
        wrapper = None if arm == "unsteered" else make_wrapper(model, vectors[arm], manifest["layer"],
                                                               manifest["alpha"])
        limits = {r.get("max_new_tokens", inf["max_new_tokens"]) for r in sel}
        if len(limits) != 1:
            raise ValueError("rows of one arm must share max_new_tokens")
        outs = generate(model, tok, [r["prompt"] for r in sel], wrapper,
                        max_new_tokens=limits.pop(), batch_size=inf["batch_size"])
        produced[arm] = outs
        same = 0
        for r, o in zip(sel, outs):
            ok = hashlib.sha256(o.encode("utf-8")).hexdigest() == r["output_sha256"]
            same += ok
            if not ok:
                report["mismatches"].append({"arm": arm, "id": r["id"], "n_chars_got": len(o),
                                             "n_chars_expected": r.get("output_chars")})
        report["arms"][arm] = {"n": len(sel), "identical": int(same)}
        print(f"verify {arm:<14} {same}/{len(sel)} outputs byte-identical to the logged run", flush=True)
    report["all_identical"] = all(v["identical"] == v["n"] for v in report["arms"].values())
    # evidence that steering was really applied: steered text must differ from unsteered text somewhere
    if "unsteered" in produced:
        report["steered_differs_from_unsteered"] = {
            arm: int(sum(a != b for a, b in zip(outs, produced["unsteered"])))
            for arm, outs in produced.items() if arm != "unsteered" and len(outs) == len(produced["unsteered"])}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model-dir", required=True, help="local folder or Hub id of CohereLabs/tiny-aya-fire")
    ap.add_argument("--package", default=str(HERE))
    ap.add_argument("--arm", default="pooled")
    ap.add_argument("--prompt", action="append", default=[])
    ap.add_argument("--alpha", type=float, default=None, help="override the frozen strength (research only)")
    ap.add_argument("--dtype", default=None)
    ap.add_argument("--verify", default=None, help="expected_outputs.jsonl to reproduce")
    ap.add_argument("--describe-layer", action="store_true")
    ap.add_argument("--report", default=None, help="write a JSON report here")
    a = ap.parse_args()

    vectors, manifest = load_package(a.package)
    if a.arm != "unsteered" and a.arm not in vectors:
        print(f"unknown arm {a.arm!r}; available: {sorted(vectors)}")
        return 2
    tok, model = load_base(a.model_dir, a.dtype or manifest["inference"]["dtype"])
    report: dict = {"package": manifest["package_version"], "layer": manifest["layer"], "alpha": manifest["alpha"],
                    "scriptshield_imported": any(m.split(".")[0] == "scriptshield" for m in sys.modules)}
    if a.describe_layer:
        report["layer_modules"] = describe_layer(model, manifest["layer"])
        print(json.dumps(report["layer_modules"], indent=1))
    if a.verify:
        report["verify"] = verify(model, tok, vectors, manifest, a.verify)
    if a.prompt:
        alpha = manifest["alpha"] if a.alpha is None else a.alpha
        base = generate(model, tok, a.prompt, None, manifest["inference"]["max_new_tokens"])
        if a.arm == "unsteered":
            steered = base
        else:
            steered = generate(model, tok, a.prompt, make_wrapper(model, vectors[a.arm], manifest["layer"], alpha),
                               manifest["inference"]["max_new_tokens"])
        report["generations"] = [{"prompt": p, "unsteered": b, a.arm: s} for p, b, s in zip(a.prompt, base, steered)]
        for g in report["generations"]:
            print("\nPROMPT   :", g["prompt"], "\nUNSTEERED:", g["unsteered"], f"\n{a.arm.upper():<9}:", g[a.arm])
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if (not a.verify or report["verify"]["all_identical"]) else 1


if __name__ == "__main__":
    sys.exit(main())
