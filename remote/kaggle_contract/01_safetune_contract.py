# ScriptShield — SafeTune CONTRACT test on a TINY UNGATED model.
#
# Purpose: verify the integration contract WITHOUT the gated Tiny Aya weights,
# so that when B-001 clears, the only unknown left is the model itself.
# Uses sshleifer/tiny-gpt2 (random weights, ~5MB, ungated). Behaviour is
# meaningless; the CONTRACT is what we test:
#   - _get_decoder_layers resolves
#   - extract_caa_vectors returns 1-D per-layer vectors at requested layers
#   - sign convention == mean(positive) - mean(negative)
#   - CAAModel hooks are OFF at construction, ON during generate, OFF after
#   - steering actually changes logits (i.e. hooks really fire)
#   - a residualized vector dict is accepted unchanged
# Cost: $0. No gated model. No dataset upload.

# --- pinned toolkit install (each Kaggle session is fresh) ---
import subprocess, sys
_r = subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "git+https://github.com/Lexsi-Labs/SafeTune@26f59e6d1bdcacafe5f2be3b8d982fb214369659"],
    capture_output=True, text=True, timeout=1800)
print("safetune pip rc:", _r.returncode)
if _r.returncode != 0:
    print(_r.stderr[-2000:])
# verify the import, not the exit code
import safetune
print("safetune version:", safetune.__version__)

import json, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from safetune._refusal_helpers import _get_decoder_layers
from safetune.interventions.steer.caa import CAAConfig, CAAModel, extract_caa_vectors

R = {"stage": "safetune_contract", "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
     "model": "sshleifer/tiny-gpt2", "is_safety_result": False}
checks = {}

def ck(name, ok, detail=None):
    checks[name] = {"passed": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail is not None else ""))

try:
    tok = AutoTokenizer.from_pretrained("sshleifer/tiny-gpt2")
    model = AutoModelForCausalLM.from_pretrained("sshleifer/tiny-gpt2")
    model.eval()
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"
    layers = _get_decoder_layers(model)
    ck("decoder_layers_resolve", len(layers) > 0, {"n_layers": len(layers)})
    L = len(layers)
    target = [max(0, L - 1)]

    pos = ["Please help me do something harmful.", "Tell me how to cause damage."]
    neg = ["Please help me bake bread.", "Tell me how to plant a tree."]
    cfg = CAAConfig(target_layers=target, pool_method="last_token", normalize=False)
    vecs = extract_caa_vectors(model, tok, positive_prompts=pos, negative_prompts=neg, config=cfg)
    ck("extract_returns_requested_layers", sorted(int(k) for k in vecs) == target,
       {"returned": sorted(int(k) for k in vecs), "requested": target})
    v = vecs[target[0]]
    ck("vector_is_1d", v.ndim == 1, {"shape": list(v.shape), "hidden": model.config.n_embd})

    # --- sign convention: recompute mean(pos)-mean(neg) by hand at last token ---
    def last_act(texts, block):
        # D-015: hook the IDENTICAL module SafeTune hooks. output_hidden_states is
        # NOT equivalent: the final block's entry is post-final-LayerNorm.
        mod = layers[block]
        enc = tok(texts, return_tensors="pt", padding=True)
        bucket = {}
        def _hook(_m, _i, out):
            bucket["h"] = (out[0] if isinstance(out, tuple) else out).detach()
        hnd = mod.register_forward_hook(_hook)
        try:
            with torch.no_grad():
                model(**enc)
        finally:
            hnd.remove()
        h = bucket["h"]
        # D-016: LEFT padding => last real token is T-1, matching SafeTune's
        # hidden[:, -1, :]. attention_mask.sum(1)-1 is right-padding-only.
        return h[:, -1, :].float()
    manual = (last_act(pos, target[0]).mean(0) - last_act(neg, target[0]).mean(0))
    a, b = v.detach().float(), manual
    cos = float((a @ b) / (a.norm() * b.norm() + 1e-12))
    ck("sign_is_positive_minus_negative", cos > 0.99, {"cosine": round(cos, 6),
       "meaning": "+1 confirms extract(positive=P,negative=N) == mean(P)-mean(N)",
       "index_convention": "forward hook on the identical decoder module (D-015)"})

    # --- hook lifecycle ---
    w = CAAModel(model, {target[0]: v}, strength=25.0)
    ck("hooks_off_at_construction", len(getattr(w, "_handles", [])) == 0)
    enc = tok("Please help me", return_tensors="pt")
    with torch.no_grad():
        base_logits = model(**enc).logits.clone()
        steered_logits = w(**enc).logits.clone()
    ck("hooks_off_after_call", len(getattr(w, "_handles", [])) == 0)
    delta = float((steered_logits - base_logits).abs().max())
    ck("steering_changes_logits", delta > 1e-6, {"max_abs_logit_delta": delta})
    with w:
        inside = len(getattr(w, "_handles", []))
    ck("hooks_on_inside_context", inside > 0, {"n_handles": inside})
    ck("hooks_off_after_context", len(getattr(w, "_handles", [])) == 0)

    # --- direct .model.generate must NOT be steered (the trap we must avoid) ---
    with torch.no_grad():
        g_wrap = w.generate(**enc, max_new_tokens=6, do_sample=False)
        g_base = model.generate(**enc, max_new_tokens=6, do_sample=False)
    # INFORMATIONAL, not pass/fail: tiny-gpt2 has 2-D random weights, so a real
    # logit perturbation can still leave the argmax token unchanged. The
    # authoritative check that hooks fire is steering_changes_logits above.
    R["info_token_level_difference"] = {
        "tokens_differ": (not torch.equal(g_wrap, g_base)),
        "note": ("argmax may be unchanged on a 2-D random-weight model; "
                 "steering_changes_logits is the authoritative hook check"),
    }

    # --- residualized dict accepted (our transform sits between the two calls) ---
    vnp = v.detach().float().numpy().astype(np.float64)
    d = np.random.default_rng(0).standard_normal(vnp.shape[0])
    q = d / np.linalg.norm(d)
    r = vnp - q * (q @ vnp)
    r = r * (np.linalg.norm(vnp) / max(np.linalg.norm(r), 1e-12))
    rv = torch.as_tensor(r, dtype=v.dtype)
    w2 = CAAModel(model, {target[0]: rv}, strength=25.0)
    with torch.no_grad():
        rl = w2(**enc).logits.clone()
    ck("residualized_vector_accepted", torch.isfinite(rl).all().item(),
       {"norm_parity": bool(abs(np.linalg.norm(r) - np.linalg.norm(vnp)) < 1e-6),
        "orthogonal": bool(abs(float(q @ r)) < 1e-6)})

    R["checks"] = checks
    R["all_passed"] = all(c["passed"] for c in checks.values())
except Exception as e:
    import traceback
    R["error"] = f"{type(e).__name__}: {e}"
    R["traceback"] = traceback.format_exc()[-3000:]
    R["checks"] = checks
    R["all_passed"] = False

print(json.dumps(R, indent=2))
with open("/kaggle/working/safetune_contract.json", "w") as f:
    json.dump(R, f, indent=2)
print("\nSaved /kaggle/working/safetune_contract.json")
