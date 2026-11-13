"""Utility probe + response-script fidelity. Pure Python (unit-tested locally).

``utility`` is deliberately crude and objective: a factual question is answered
correctly iff a gold regex matches. It exists to detect a steering vector that has
broken ordinary question answering, not to benchmark capability.

``response_script`` reports which script the model actually answered in. The smoke
test showed Tiny Aya Fire sometimes answers a Roman Urdu prompt in DEVANAGARI
(treating it as Hindi), which a refusal metric alone would never reveal.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

UTILITY_PATH = Path("data") / "utility" / "utility_v0.1.yaml"


def load_utility(root: str | Path) -> list[dict]:
    """Flat records: one per (item, form). ``text`` is the prompt."""
    spec = yaml.safe_load((Path(root) / UTILITY_PATH).read_text(encoding="utf-8"))
    out = []
    for it in spec["items"]:
        for form in ("ur", "ro"):
            out.append({"id": f"{it['id']}-{form}", "item_id": it["id"], "family_id": it["id"],
                        "pair_id": it["id"], "form": form, "safety_label": "benign",
                        "split": "utility", "text": it[form], "answer": list(it["answer"])})
    ids = [r["id"] for r in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate utility ids")
    return out


def is_correct(output: str | None, patterns: list[str]) -> bool:
    if not output or not output.strip():
        return False                      # empty output is never 'correct'
    return any(re.search(p, output, flags=re.IGNORECASE) for p in patterns)


def response_script(text: str | None) -> str:
    """Dominant script of the LETTERS in a response:
    arabic | latin | devanagari | mixed | other | empty."""
    if not text or not text.strip():
        return "empty"
    counts = {"arabic": 0, "latin": 0, "devanagari": 0, "other": 0}
    for ch in text:
        o = ord(ch)
        if ch.isascii():
            if ch.isalpha():
                counts["latin"] += 1
        elif 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
            counts["arabic"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
        elif ch.isalpha():
            counts["other"] += 1
    total = sum(counts.values())
    if total == 0:
        return "other"
    top, n = max(counts.items(), key=lambda kv: kv[1])
    return top if n / total >= 0.7 else "mixed"


EXPECTED_SCRIPT = {"ur": {"arabic"}, "ro": {"latin"}, "en": {"latin"}, "cm": {"arabic", "latin", "mixed"}}


def script_matches_prompt(form: str, text: str | None) -> bool:
    return response_script(text) in EXPECTED_SCRIPT.get(form, set())


def apply_reading(pattern: dict[tuple[str, str], bool], disagreements: list[dict]) -> dict[tuple[str, str], bool]:
    """Correctness on reading = the pattern score with the recorded disagreements applied.

    ``pattern`` maps (arm, question id) to the pattern score. Each disagreement names a question
    id, the arms it applies to, what the pattern said and what the reader found. A disagreement is
    rejected unless the pattern outcome it records is the one actually computed and its two
    outcomes differ, so a stale or mistyped entry cannot silently change a count.
    """
    out = dict(pattern)
    seen: set[tuple[str, str]] = set()
    for d in disagreements:
        want = {"correct": True, "incorrect": False}
        if d["pattern"] not in want or d["reading"] not in want or d["pattern"] == d["reading"]:
            raise ValueError(f"{d['id']}: a disagreement needs two different outcomes")
        for arm in d["arms"]:
            key = (arm, d["id"])
            if key not in pattern:
                raise ValueError(f"{key}: no such utility answer")
            if key in seen:
                raise ValueError(f"{key}: listed twice")
            if pattern[key] is not want[d["pattern"]]:
                raise ValueError(f"{key}: recorded pattern score {d['pattern']!r} is not the computed one")
            seen.add(key)
            out[key] = want[d["reading"]]
    return out
