"""Real AuditKIT integration: generate -> score -> retain every row.

AuditKIT owns generation and scoring. We own aggregation and significance
(DECISIONS D-009) because upstream 1.1.3 can drop failed samples from headline
means and its paired-bootstrap p-value is not a valid null test.

Guarantees enforced here:
* one output row per input row, positionally verified
* a generation exception becomes INVALID, never a dropped row
* scorer output is parsed strictly; unrecognised -> UNKNOWN
* AuditKIT's disk cache can NEVER replay another arm's text (D-029): every call gets
  a unique model identity, and we count the prompts the model really received
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Sequence

from .labels import INVALID, classify_refusal


def _require_auditkit():
    try:
        import auditkit
        from auditkit import Sample, evaluate, generate
    except ImportError as e:
        raise ImportError(
            "AuditKIT is not installed. Install the pinned commit:\n"
            "  pip install --no-deps 'git+https://github.com/Lexsi-Labs/AuditKIT"
            "@71316da345784ff220d5ed59337441a59ab31526'"
        ) from e
    return auditkit, Sample, evaluate, generate


def records_to_samples(records: Sequence[dict]):
    """Build AuditKIT Samples carrying our research metadata."""
    _, Sample, _, _ = _require_auditkit()
    out = []
    for r in records:
        out.append(Sample(
            input=r["text"],
            id=r["id"],
            task="safety_refusal",
            metadata={k: r[k] for k in ("family_id", "pair_id", "form", "safety_label",
                                        "split", "harm_category") if k in r},
        ))
    return out


def generate_outputs(records: Sequence[dict], model: Any, batch_size: int = 64,
                     run_tag: str = "run") -> list[dict]:
    """Run AuditKIT.generate and return one row per input, failures included.

    ``model`` is a list[str]->list[str] callable (for steered arms: a closure over
    SafeTune's CAAModel), an AuditKIT Model, or a model spec string.

    D-029 - STALE CACHE. ``Runner.run`` returns a cached RunResult whenever the run
    fingerprint matches, and the fingerprint identifies a callable only by its code
    and IMMUTABLE closure values. Two steering arms differ only in a captured CAAModel
    object, so they collide: in our first dev run AuditKIT generated one arm and then
    replayed its text for the other 31 (0.0 s each, 32 "arms" with 1 distinct output
    set). Defences, all three always on:
      1. the callable is wrapped in a CallableModel with a unique name per call, so no
         two calls can share a fingerprint;
      2. we count the prompts the callable actually received and raise StaleCacheError
         unless it equals the number of records;
      3. prompt identity is verified (PromptAltered) and output order is checked by id.
    """
    ak, Sample, _, generate = _require_auditkit()
    from auditkit import RunConfig
    samples = records_to_samples(records)
    rows: list[dict] = []
    seen = {"prompts": 0}
    is_callable = callable(model) and not isinstance(model, str) and not hasattr(model, "generate")
    if is_callable:
        from auditkit.model import CallableModel
        expected = {r["text"] for r in records}
        inner = model

        def checked(prompts: list[str]) -> list[str]:
            alien = [p for p in prompts if p not in expected]
            if alien:
                raise PromptAltered(f"AuditKIT passed {len(alien)} prompt(s) that are not in the "
                                    f"dataset, e.g. {alien[0][:80]!r}")
            outs = inner(list(prompts))
            if len(outs) != len(prompts):
                raise RuntimeError(f"model returned {len(outs)} outputs for {len(prompts)} prompts")
            seen["prompts"] += len(prompts)
            return outs

        model = CallableModel(checked, name=f"scriptshield::{run_tag}::{uuid.uuid4().hex}")
    try:
        produced = generate(samples, model=model, config=RunConfig(batch_size=batch_size, max_retries=0))
    except PromptAltered:
        raise
    except Exception as exc:                      # generation-level failure
        for r in records:
            rows.append({**_row_base(r), "output": None,
                         "error": f"generate_failed:{type(exc).__name__}:{exc}",
                         "judge_label": INVALID})
        return rows
    if is_callable and seen["prompts"] != len(records):
        raise StaleCacheError(
            f"AuditKIT returned {len(produced)} outputs but the model was only asked for "
            f"{seen['prompts']} of {len(records)} prompts: text was replayed from a cache")
    if len(produced) != len(records):
        # Never silently zip a short list: pad with INVALID so denominators hold.
        for i, r in enumerate(records):
            if i < len(produced):
                rows.append({**_row_base(r), "output": produced[i].actual_output})
            else:
                rows.append({**_row_base(r), "output": None,
                             "error": "missing_output", "judge_label": INVALID})
        return rows
    for r, s in zip(records, produced):
        if s.id != r["id"]:
            raise RuntimeError(f"AuditKIT returned samples out of order: {s.id} != {r['id']}")
        rows.append({**_row_base(r), "output": s.actual_output})
    return rows


class StaleCacheError(RuntimeError):
    """AuditKIT served text from its disk cache instead of calling the model."""


class PromptAltered(RuntimeError):
    """AuditKIT handed the model a string that is not one of our prompts."""


def _row_base(r: dict) -> dict:
    return {k: r[k] for k in ("id", "family_id", "pair_id", "form", "safety_label", "split")
            if k in r}


def score_with_auditkit(rows: list[dict], scorer_fn: Callable | None = None) -> dict:
    """Score precomputed outputs through AuditKIT.evaluate(model="precomputed").

    Returns {"auditkit_result": RunResult, "rows": rows with proxy labels}.
    The AuditKIT result is retained as the audit trail; our own aggregation is
    what gets reported.
    """
    ak, Sample, evaluate, _ = _require_auditkit()
    from auditkit.scorers import FunctionScorer
    try:
        from auditkit.types import Direction
    except ImportError:
        from auditkit.metrics.base import Direction  # older layout

    fn = scorer_fn or (lambda sample, output: float(classify_refusal(output).is_refusal))
    scorer = FunctionScorer(fn, Direction.MAXIMIZE, name=f"refusal_proxy::{uuid.uuid4().hex}")  # D-029
    samples = [Sample(input=r.get("output") or "", id=r["id"],
                      actual_output=r.get("output"), task="safety_refusal",
                      metadata={"form": r["form"], "safety_label": r["safety_label"]})
               for r in rows]
    result = evaluate(samples, model="precomputed", scorers=[scorer])
    for r in rows:
        if "judge_label" not in r:
            r["proxy_label"] = classify_refusal(r.get("output")).label
    return {"auditkit_result": result, "rows": rows, "auditkit_version": ak.__version__}
