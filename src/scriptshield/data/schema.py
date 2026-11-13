"""Corpus validation: JSON-Schema + research-integrity checks.

The schema catches shape errors. The corpus checks catch the errors that would
silently invalidate the experiment: family leakage across splits, missing forms
in a matched pair, wrong script for a declared form, and duplicate text.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from ..config import ALL_FORMS, SAFETY_LABELS

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "schemas" / "prompt.schema.json"

_ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN = re.compile(r"[A-Za-z]")


def _schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_records(path: str | Path) -> list[dict]:
    p = Path(path)
    out = []
    with p.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{i}: invalid JSON: {e}") from e
    return out


def corpus_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_corpus(root: str | Path) -> tuple[list[dict], dict]:
    """Load THE corpus named in configs/data.yaml and verify its checksum.

    Every script goes through this, so no script can silently run on a different
    or edited corpus: a checksum mismatch raises instead of producing results
    that cannot be tied to a dataset version.
    """
    from ..config import load_yaml
    root = Path(root)
    spec = load_yaml(root / "configs" / "data.yaml")
    path = root / spec["corpus"]
    got = corpus_sha256(path)
    if got != spec["sha256"]:
        raise ValueError(f"corpus checksum mismatch for {path}: configs/data.yaml says "
                         f"{spec['sha256']}, file is {got}. Rebuild with scripts/build_dataset.py")
    return load_records(path), {**spec, "path": str(path)}


def validate_record(rec: dict) -> list[str]:
    v = jsonschema.Draft202012Validator(_schema())
    return [f"{'.'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message}"
            for e in v.iter_errors(rec)]


def script_of(text: str) -> str:
    has_a, has_l = bool(_ARABIC.search(text)), bool(_LATIN.search(text))
    if has_a and has_l:
        return "mixed"
    if has_a:
        return "arabic"
    if has_l:
        return "latin"
    return "other"


def _char_script(ch: str) -> str:
    """Classify ONE character: arabic | latin | common | foreign:<UNICODE NAME PREFIX>."""
    o = ord(ch)
    if ch.isascii():
        return "latin" if ch.isalpha() else "common"
    if (0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F
            or 0xFB50 <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF):
        return "arabic"
    cat = unicodedata.category(ch)
    if cat[0] in "PZS" or ch in "\u200c\u200d\u200e\u200f":
        return "common"                       # punctuation, spaces, symbols, ZWNJ/ZWJ, bidi marks
    try:
        name = unicodedata.name(ch).split()[0]
    except ValueError:
        name = f"U+{o:04X}"
    return f"foreign:{name}"


def foreign_script_chars(text: str, form: str) -> dict[str, str]:
    """Characters that do not belong in ``form``. Returns {char: script}.

    D-019: the v0.1.0 pilot shipped one code-mixed record with three Devanagari
    characters inside an Urdu word. A whole-string "has Arabic / has Latin" test
    cannot see that. For a study whose independent variable IS the script, a
    single foreign-script character contaminates the contrast, so the check is
    per character:  ur -> Arabic only;  ro/en -> ASCII Latin only;
    cm -> Arabic + ASCII Latin;  no other script is ever allowed.
    """
    allowed = {"ur": {"arabic", "common"}, "ro": {"latin", "common"},
               "en": {"latin", "common"}, "cm": {"arabic", "latin", "common"}}.get(form)
    if allowed is None:
        return {}
    return {ch: sc for ch in dict.fromkeys(text) if (sc := _char_script(ch)) not in allowed}


def check_script_consistency(rec: dict) -> list[str]:
    """A form label that disagrees with the actual script invalidates the contrast."""
    form, text = rec.get("form"), rec.get("text", "")
    s = script_of(text)
    errs = []
    bad = foreign_script_chars(text, form)
    if bad:
        errs.append(f"{rec.get('id')}: form={form} contains out-of-script characters "
                    f"{sorted(set(bad.values()))}: {''.join(bad)!r}")
    if form == "ur" and s != "arabic":
        errs.append(f"{rec.get('id')}: form=ur but script={s} (expected pure Perso-Arabic)")
    if form == "ro" and s != "latin":
        errs.append(f"{rec.get('id')}: form=ro but script={s} (expected Latin-only Roman Urdu)")
    if form == "en" and s != "latin":
        errs.append(f"{rec.get('id')}: form=en but script={s}")
    if form == "cm" and s not in {"mixed", "latin"}:
        errs.append(f"{rec.get('id')}: form=cm but script={s}")
    return errs


@dataclass
class CorpusReport:
    n_records: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    by_split: dict = field(default_factory=dict)
    by_form_label: dict = field(default_factory=dict)
    n_families: int = 0
    validation_status_counts: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        lines = [
            f"records      : {self.n_records}",
            f"families     : {self.n_families}",
            f"by split     : {self.by_split}",
            f"by form/label: {self.by_form_label}",
            f"validation   : {self.validation_status_counts}",
            f"errors       : {len(self.errors)}",
            f"warnings     : {len(self.warnings)}",
        ]
        lines += [f"  ERROR {e}" for e in self.errors[:20]]
        lines += [f"  WARN  {w}" for w in self.warnings[:10]]
        return "\n".join(lines)


def validate_corpus(records: list[dict], strict_pairs: bool = True) -> CorpusReport:
    rep = CorpusReport(n_records=len(records))
    seen_ids: set[str] = set()
    fam_splits: dict[str, set[str]] = defaultdict(set)
    pair_forms: dict[str, set[str]] = defaultdict(set)
    text_index: dict[str, list[str]] = defaultdict(list)

    for rec in records:
        errs = validate_record(rec)
        rep.errors.extend(errs)
        if errs:
            continue
        rep.errors.extend(check_script_consistency(rec))
        rid = rec["id"]
        if rid in seen_ids:
            rep.errors.append(f"duplicate id: {rid}")
        seen_ids.add(rid)
        expected_id = f"ss-{rec['family_id']}-{rec['form']}-{rec['safety_label']}"
        if rid != expected_id:
            rep.errors.append(f"{rid}: id does not match family/form/label ({expected_id})")
        fam_splits[rec["family_id"]].add(rec["split"])
        pair_forms[rec["pair_id"]].add(rec["form"])
        norm = " ".join(rec["text"].split()).casefold()
        text_index[norm].append(rid)

    # Family-level leakage: the single most damaging possible bug here.
    for fam, splits in fam_splits.items():
        if len(splits) > 1:
            rep.errors.append(f"family leakage: {fam} appears in splits {sorted(splits)}")

    if strict_pairs:
        for pair, forms in pair_forms.items():
            missing = set(ALL_FORMS) - forms
            if missing:
                rep.errors.append(f"incomplete matched set {pair}: missing forms {sorted(missing)}")

    for norm, ids in text_index.items():
        if len(ids) > 1:
            rep.errors.append(f"duplicate text across records: {ids}")

    rep.by_split = dict(Counter(r.get("split") for r in records))
    rep.by_form_label = {f"{f}/{l}": sum(1 for r in records
                                        if r.get("form") == f and r.get("safety_label") == l)
                         for f in ALL_FORMS for l in SAFETY_LABELS}
    rep.n_families = len(fam_splits)
    rep.validation_status_counts = dict(Counter(r.get("validation_status") for r in records))

    # Honest reporting: unreviewed content is a WARNING, never silently 'validated'.
    n_unrev = rep.validation_status_counts.get("unreviewed", 0)
    if n_unrev:
        rep.warnings.append(
            f"{n_unrev}/{len(records)} records are UNREVIEWED. "
            "No human language-quality validation may be claimed."
        )
    for bad in ("reviewer_id",):
        for r in records:
            if r.get("validation_status") == "unreviewed" and r.get(bad):
                rep.errors.append(f"{r.get('id')}: unreviewed record carries {bad}")
    return rep
