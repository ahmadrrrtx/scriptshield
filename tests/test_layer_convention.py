"""D-015 / D-016 regression: ONE capture implementation, and it is the right one.

Two wrong approaches were tried and rejected on real GPU:
  hidden_states[idx]      -> the block's INPUT                       (cosine 0.78)
  hidden_states[idx + 1]  -> post-final-LayerNorm for the last block (cosine 0.33)
The correct approach is a forward hook on the decoder module SafeTune itself hooks.

Since the runtime refactor that logic lives ONLY in scriptshield/models/runtime.py.
The drivers must not re-implement capture, templating or tokenisation: a second
copy is exactly how the two drivers drifted apart before.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "src/scriptshield/models/runtime.py").read_text(encoding="utf-8")
DRIVERS = ["scripts/smoke_model.py", "scripts/run_experiment.py"]


def _code(src: str) -> str:
    """Source with comments and docstrings blanked, so prose may mention forbidden names."""
    import io
    import tokenize
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_runtime_hooks_the_decoder_module_safetune_hooks():
    code = _code(RUNTIME)
    assert "_get_decoder_layers" in code, "must resolve layers with SafeTune's own resolver"
    assert "register_forward_hook" in code


def test_runtime_never_reads_output_hidden_states():
    assert "output_hidden_states" not in _code(RUNTIME), (
        "output_hidden_states is post-final-norm for the last block and does not "
        "match SafeTune's hook capture (D-015)")


def test_every_hook_registration_is_removed_in_a_finally_block():
    """A leaked hook would steer or record during every later arm, 'unsteered' included."""
    n_reg = RUNTIME.count("register_forward_hook(")
    assert n_reg >= 2
    for chunk in RUNTIME.split("register_forward_hook(")[1:]:
        window = chunk[:600]
        assert "finally:" in window and "handle.remove()" in window


def test_runtime_uses_padding_agnostic_last_token_index():
    code = _code(RUNTIME)
    assert "last_token_index (" in code or "last_token_index(" in code
    assert ". sum ( 1 )" not in code and ".sum(1)" not in RUNTIME.replace(" ", "")


@pytest.mark.parametrize("script", DRIVERS)
def test_drivers_do_not_reimplement_capture_or_templating(script):
    code = _code((ROOT / script).read_text(encoding="utf-8"))
    for forbidden in ("register_forward_hook", "output_hidden_states", "apply_chat_template",
                      "AutoModelForCausalLM", "AutoTokenizer", "attention_mask"):
        assert forbidden not in code, f"{script} must go through scriptshield.models.runtime, found {forbidden}"
    assert "runtime" in code, f"{script} must import scriptshield.models.runtime"
