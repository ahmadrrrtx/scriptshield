"""D-029 regression: AuditKIT's disk cache must never replay one arm's text for another.

Reproduces the real failure: two 'arms' are closures that differ ONLY in a captured
mutable object (as two SafeTune CAAModel wrappers do), run over the SAME prompts.
"""
from pathlib import Path

import pytest

auditkit = pytest.importorskip("auditkit")

from scriptshield.data.schema import load_corpus                                   # noqa: E402
from scriptshield.evaluation.auditkit_adapter import StaleCacheError, generate_outputs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


class Wrapper:                       # stands in for a CAAModel: mutable, not hashable into a fingerprint
    def __init__(self, tag):
        self.tag = tag


def make_arm(w):
    return lambda prompts: [f"{w.tag}:{len(p)}" for p in prompts]


@pytest.fixture
def records():
    recs, _ = load_corpus(ROOT)
    return [r for r in recs if r["split"] == "dev"][:12]


def test_two_arms_on_the_same_prompts_get_their_own_text(records):
    a = generate_outputs(records, make_arm(Wrapper("A")), run_tag="arm_a")
    b = generate_outputs(records, make_arm(Wrapper("B")), run_tag="arm_b")
    assert all(r["output"].startswith("A:") for r in a)
    assert all(r["output"].startswith("B:") for r in b), "arm B was served arm A's cached text"


def test_the_same_arm_twice_is_generated_twice(records):
    calls = []

    def arm(prompts):
        calls.append(len(prompts))
        return ["x"] * len(prompts)

    generate_outputs(records, arm)
    generate_outputs(records, arm)
    assert sum(calls) == 2 * len(records)


def test_raw_auditkit_really_has_this_hazard(records):
    """If this ever starts failing, upstream fixed the collision; the guards stay anyway."""
    import auditkit as ak
    from scriptshield.evaluation.auditkit_adapter import records_to_samples
    samples = records_to_samples(records)
    first = ak.generate(samples, model=make_arm(Wrapper("A")))
    second = ak.generate(samples, model=make_arm(Wrapper("B")))
    replayed = all(s.actual_output.startswith("A:") for s in second)
    assert first[0].actual_output.startswith("A:")
    assert replayed, "expected upstream AuditKIT 1.1.3 to replay arm A for arm B"


def test_guard_raises_if_the_model_was_not_called(records, monkeypatch):
    """Simulate a cache hit: AuditKIT returns outputs without invoking the callable."""
    import dataclasses

    import auditkit as ak

    def fake_generate(samples, model, config=None, **_):
        return [dataclasses.replace(s, actual_output="stale") for s in samples]

    monkeypatch.setattr(ak, "generate", fake_generate)
    with pytest.raises(StaleCacheError, match="replayed from a cache"):
        generate_outputs(records, lambda prompts: ["fresh"] * len(prompts))
