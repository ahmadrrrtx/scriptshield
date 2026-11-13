"""Real CuratorKIT integration: ingestion -> schema gate -> clean -> dedup -> export.

Design constraints from the approved directive:
* NO toxicity/quality gate. Our harmful items are intentional adversarial
  probes; a toxicity filter would delete exactly the signal we study.
* NFC-only unicode normalisation. No ASCII folding, no diacritic stripping,
  no lowercasing: those would erase the ur/ro script contrast.
* Exact dedup only. MinHash would collapse near-identical matched pairs across
  forms and silently break the paired design.
* Rejected records are RETAINED and counted, never silently dropped.
* Our research metadata rides through in DataSample.metadata so the pairing
  survives curation and can be verified on the way out.

Requires `curatorkit` to be installed. Raises a clear error if absent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_META_KEYS = ("family_id", "pair_id", "form", "safety_label", "split",
              "roman_style", "intended_meaning_en", "harm_category",
              "validation_status", "source", "created")


def to_curator_input(records: list[dict], path: str | Path) -> Path:
    """Write CuratorKIT-ingestible JSONL.

    CuratorKIT's canonical field is `instruction`; we map our `text` there.
    Research fields are written at TOP LEVEL, not nested under a "metadata"
    key: BaseConnector._collect_metadata promotes unmapped top-level columns
    into DataSample.metadata, so nesting would bury them one level too deep
    and silently destroy the pairing (F-006). `task_type=prompt_only` because
    these are evaluation prompts, not SFT targets.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for r in records:
            row = {
                "id": r["id"],
                "instruction": r["text"],
                "task_type": "prompt_only",
                "source_uri": f"scriptshield://authored/{r['family_id']}",
            }
            row.update({k: r[k] for k in _META_KEYS if k in r})
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return p


@dataclass
class CurationOutcome:
    passed: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    stage_counts: dict = field(default_factory=dict)
    output_dir: str = ""
    wall_clock_seconds: float = 0.0
    curatorkit_version: str = ""

    @property
    def n_passed(self) -> int:
        return len(self.passed)

    @property
    def n_rejected(self) -> int:
        return len(self.rejected)


def _require_curatorkit():
    try:
        import curatorkit
        from curatorkit import Curator, CuratorConfig
    except ImportError as e:
        raise ImportError(
            "CuratorKIT is not installed. Install the pinned commit:\n"
            "  pip install --no-deps 'git+https://github.com/Lexsi-Labs/CuratorKIT"
            "@dd9e835301fcddc74a37501d9e207a5a060d209f'\n"
            "Core deps: pydantic, typer, tqdm, pyyaml."
        ) from e
    return curatorkit, Curator, CuratorConfig


def curate_corpus(records: list[dict], output_dir: str | Path,
                  name: str = "scriptshield_pilot") -> CurationOutcome:
    """Run the real CuratorKIT pipeline over our corpus."""
    ck, Curator, CuratorConfig = _require_curatorkit()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    src = to_curator_input(records, out / "input.jsonl")

    cfg = CuratorConfig(
        dataset=str(src),
        # `format` selects the RECORD SCHEMA (DataFormat enum), not the file
        # type. Passing "jsonl" here rejects every row as
        # invalid_forced_format (F-005). File type comes from the extension.
        format="prompt_only",
        output_dir=str(out),
        name=name,
        # --- research-critical settings ---
        dedup="exact",              # never minhash: would collapse matched pairs
        clean=True,
        clean_transforms={
            "strip_html": True,
            "normalise_unicode": True,       # NFC only, script-preserving
            "fix_encoding_artifacts": True,
            "collapse_whitespace": True,
            "remove_control_chars": True,
        },
        clean_fields=["instruction"],
        # Urdu prompts are short; the default min_tokens=10 is tuned for SFT docs.
        min_tokens=3,
        max_tokens=512,
        schema_gate=True,
        # NO LLM, NO toxicity, NO reward/hallucination/diversity gates.
        llm_model=None,
        generation_task=None,
        hallucination_threshold=None,
        reward_threshold=None,
        diversity_threshold=None,
        embedding_dedup=False,
        write_hf_readme=False,
    )
    result = Curator(cfg).run()

    passed = []
    for s in result.passed:
        md = dict(s.metadata or {})
        rec = {k: md[k] for k in _META_KEYS if k in md}
        rec["id"] = s.id
        rec["text"] = s.instruction
        passed.append(rec)
    rejected = []
    for s in result.rejected:
        rejected.append({
            "id": s.id,
            "reason": getattr(s, "rejection_reason", "unknown"),
            "step": getattr(s, "rejecting_step", "unknown"),
            "metadata": dict(s.metadata or {}),
        })
    # Persist rejects: they are evidence, not garbage.
    (out / "rejected.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rejected),
        encoding="utf-8")
    return CurationOutcome(
        passed=passed, rejected=rejected,
        stage_counts=dict(result.stage_counts or {}),
        output_dir=str(result.output_dir),
        wall_clock_seconds=float(result.wall_clock_seconds),
        curatorkit_version=ck.__version__,
    )
