"""Contracts of the shared model runtime that can be checked WITHOUT torch.

D-018 double BOS, D-020 end-of-turn ids, D-021 double templating, plus the pure
numpy helpers used by the dtype-fidelity check and the layer scan.
"""
from pathlib import Path

import numpy as np
import pytest

from scriptshield.models import runtime as rt
from scriptshield.steering.safetune_adapter import assert_raw_prompts

ROOT = Path(__file__).resolve().parents[1]
BOS, PAD = 2, 0


class FakeTok:
    """Reproduces the Tiny Aya hazard: the chat template emits <BOS_TOKEN> AND the
    tokenizer prepends BOS again unless add_special_tokens=False."""
    chat_template = "{{ bos_token }}..."
    padding_side = "left"
    pad_token_id = PAD
    eos_token_id = 6
    unk_token_id = 4

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        assert tokenize is False and add_generation_prompt is True
        assert len(messages) == 1 and messages[0]["role"] == "user"
        return "<BOS_TOKEN><U>" + messages[0]["content"] + "<A>"

    def __call__(self, text, add_special_tokens=True, **_):
        body = [BOS] if text.startswith("<BOS_TOKEN>") else []
        body += [10 + (ord(c) % 50) for c in text.replace("<BOS_TOKEN>", "")]
        return {"input_ids": ([BOS] if add_special_tokens else []) + body}

    def get_vocab(self):
        return {"<|END_RESPONSE|>": 261001, "<|END_OF_TURN_TOKEN|>": 6, "<EOS_TOKEN>": 3, "<UNK>": 4}


class NoTemplateTok(FakeTok):
    chat_template = None


class FakeModel:
    class config:
        eos_token_id = 3


def test_prompt_ids_has_exactly_one_bos_d018():
    ids = rt.prompt_ids(FakeTok(), "salam")
    assert ids.count(BOS) == 1 and ids[0] == BOS
    assert FakeTok()("<BOS_TOKEN><U>salam<A>")["input_ids"].count(BOS) == 2, "the hazard itself"


def test_render_chat_is_one_user_turn_with_generation_prompt():
    assert rt.render_chat(FakeTok(), "x") == "<BOS_TOKEN><U>x<A>"
    assert rt.render_chat(NoTemplateTok(), "x") == "x"


def test_models_without_a_template_keep_default_special_tokens():
    assert rt.prompt_ids(NoTemplateTok(), "x")[0] == BOS


def test_end_of_turn_ids_cover_every_way_a_turn_can_end_d020():
    assert rt.eos_token_ids(FakeTok(), FakeModel()) == [3, 6, 261001]


def test_end_of_turn_ids_skip_tokens_missing_from_the_vocab():
    class Tok(FakeTok):
        def get_vocab(self):
            return {"<EOS_TOKEN>": 3}
    assert rt.eos_token_ids(Tok(), FakeModel()) == [3, 6]


def test_encode_refuses_right_padding():
    class Right(FakeTok):
        padding_side = "right"
    with pytest.raises(RuntimeError, match="left"):
        rt.encode(Right(), ["x"], device=None)


def test_runtime_source_tokenises_templated_text_without_special_tokens():
    src = (ROOT / "src/scriptshield/models/runtime.py").read_text(encoding="utf-8")
    assert src.count('"add_special_tokens": False') + src.count('["add_special_tokens"] = False') >= 2
    assert "truncation" not in src.split('"""', 2)[2].replace("No truncation", ""), (
        "truncating a rendered prompt would cut off its generation prompt")


@pytest.mark.parametrize("bad", [
    "<BOS_TOKEN><|START_OF_TURN_TOKEN|><|USER_TOKEN|>salam",
    "<|im_start|>user\nhi<|im_end|>", "[INST] hi [/INST]", "<start_of_turn>user hi",
])
def test_pre_rendered_prompts_are_refused_d021(bad):
    with pytest.raises(ValueError, match="RAW user text"):
        assert_raw_prompts([bad])


def test_raw_prompts_pass_and_empty_ones_do_not():
    assert_raw_prompts(["Main apna password bhool gaya hoon", "میں ٹھیک ہوں"])
    with pytest.raises(ValueError):
        assert_raw_prompts(["   "])


def test_compare_logits_identical_and_perturbed():
    rng = np.random.default_rng(0)
    ref = rng.normal(size=(6, 50))
    same = rt.compare_logits(ref, ref.copy())
    assert same["finite"] and same["top1_agreement"] == 1.0 and same["kl_max"] < 1e-12
    off = rt.compare_logits(ref, ref + rng.normal(scale=2.0, size=ref.shape))
    assert off["kl_mean"] > 0.1 and off["top1_agreement"] < 1.0


def test_compare_logits_flags_nonfinite_candidate():
    ref = np.zeros((2, 5))
    bad = ref.copy(); bad[1, 2] = np.nan
    out = rt.compare_logits(ref, bad)
    assert out["finite"] is False and out["n_nonfinite_rows"] == 1


def test_dtype_acceptable_rules():
    ok_stats = [{"layer": 0, "finite_real_tokens": True}]
    good = {"finite": True, "kl_mean": 1e-4, "kl_max": 1e-3}
    assert rt.dtype_acceptable(good, ok_stats)[0]
    assert not rt.dtype_acceptable({"finite": True, "kl_mean": 0.5, "kl_max": 0.9}, ok_stats)[0]
    assert not rt.dtype_acceptable({"finite": False}, ok_stats)[0]
    assert not rt.dtype_acceptable(good, [{"layer": 7, "finite_real_tokens": False}])[0]


def test_auc_and_cosine():
    assert rt.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0
    assert rt.auc(np.array([1.0]), np.array([1.0])) == 0.5
    assert rt.auc(np.array([0.0]), np.array([1.0])) == 0.0
    assert rt.cosine([1, 0], [0, 1]) == 0.0
    assert rt.cosine([1, 2], [2, 4]) == pytest.approx(1.0)


def test_importing_the_runtime_does_not_import_torch():
    import sys
    assert "torch" not in sys.modules, "runtime must stay importable on the 2 GB local box"
