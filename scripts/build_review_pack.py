#!/usr/bin/env python3
"""Build the review pack for the project author: one CSV and twelve small batch files.

    python3 scripts/build_review_pack.py            # refuses if the sheet already holds answers or edits
    python3 scripts/build_review_pack.py --force    # overwrite anyway (import the answers first!)

Reads the corpus and the audit (run scripts/audit_dataset.py first). Writes, under data/reviewer_pack/:
    AHMAD_REVIEW.csv                 144 rows (72 families x harmful / harmless), editable
    AHMAD_REVIEW_BATCH_01.md ... 12  six families each, with an answer block to fill in
The original pack (review_sheet.csv, review_template.jsonl, INSTRUCTIONS.md) is not touched.
The 36 test families come first, because the main result is measured on them.
A batch file whose families have all been answered is not rewritten: it is the record of what the reviewer saw.
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.roman_style import to_style_b  # noqa: E402
from scriptshield.data.schema import load_corpus  # noqa: E402

PACK = ROOT / "data" / "reviewer_pack"
BATCH_SIZE = 6
COLUMNS = ["batch", "row_id", "family_id", "split", "topic_group", "safety_label", "english_reference", "intended_meaning_en",
           "urdu_script", "roman_urdu", "roman_urdu_alt_candidate", "notes_for_reviewer",
           # ---- the reviewer fills in the columns below ----
           "ur_naturalness_1to5_or_U", "ro_naturalness_1to5_or_U", "same_meaning_yes_no_uncertain",
           "label_plausible_yes_no_uncertain", "alt_spelling_ok_yes_no_uncertain", "pair_comparable_yes_no_uncertain",
           "corrected_urdu", "corrected_roman_urdu", "corrected_alt_spelling", "comments", "reviewer"]
LABEL_NAME = {"harmful": "Harmful request", "benign": "Harmless request"}
REVIEW_COLUMNS = COLUMNS[COLUMNS.index("ur_naturalness_1to5_or_U"):]
TEXT_COLUMNS = ("urdu_script", "roman_urdu", "roman_urdu_alt_candidate")


def review_order(fam: dict) -> list[str]:
    """Test families first, then development, then calibration; within a split, topic groups take turns."""
    order: list[str] = []
    for split in ("test", "dev", "calibration"):
        groups: dict = collections.defaultdict(list)
        for f in sorted(fam):
            if fam[f][("harmful", "ur")]["split"] == split:
                groups[fam[f][("harmful", "ur")]["harm_group"]].append(f)
        queues = [groups[g] for g in sorted(groups)]
        while any(queues):
            for q in queues:
                if q:
                    order.append(q.pop(0))
    return order


def notes_for(audit: dict, label: str) -> list[str]:
    out = []
    for x in audit["automatic_flags"]:
        if x["label"] == label and x["type"] == "word_differs_between_scripts":
            if "'بغیر'" in x["detail"]:
                out.append("Automatic check: the Urdu script says بغیر (baghair) but the Roman Urdu says 'bina'. Same meaning, different word.")
            else:
                out.append("Automatic check: " + x["detail"] + " (a different word is used in the two scripts).")
    for n in audit["llm_notes"]:
        if n["label"] == label:
            out.append(f"LLM note ({n['type'].replace('_', ' ')}): {n['note']}")
    return out


def pair_notes(audit: dict) -> list[str]:
    out = []
    if audit["pair_form"] == "different":
        h, b = audit["speech_act"]["harmful"]["label"], audit["speech_act"]["benign"]["label"]
        out.append(f"Automatic check: the harmful request is a {h} and the harmless one is a {b}.")
    out += [f"LLM note ({n['type'].replace('_', ' ')}): {n['note']}" for n in audit["llm_notes"] if n["label"] == "pair"]
    return out


def sheet_edits(path: Path, rows: list[dict]) -> int:
    """How many cells of an existing sheet the reviewer has filled in or changed (0 for the untouched template)."""
    if not path.exists():
        return 0
    pristine = {r["row_id"]: r for r in rows}
    n = 0
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        n += sum(1 for c in REVIEW_COLUMNS if (r.get(c) or "").strip())
        o = pristine.get(r.get("row_id"))
        if o is not None:
            n += sum(1 for c in TEXT_COLUMNS if (r.get(c) or "").strip() != (o.get(c) or "").strip())
    return n


def pack_rows():
    """The untouched rows of the sheet, built from the corpus: (rows, batches, families, audit)."""
    recs, _ = load_corpus(ROOT)
    fam: dict = collections.defaultdict(dict)
    for r in recs:
        fam[r["family_id"]][(r["safety_label"], r["form"])] = r
    audit = json.loads((ROOT / "data/quality/family_audit_v0.2.0.json").read_text(encoding="utf-8"))["families"]
    order = review_order(fam)
    batches = [order[i:i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]

    rows = []
    for bi, batch in enumerate(batches, 1):
        for f in batch:
            for label in ("harmful", "benign"):
                g = fam[f]
                is_test = g[(label, "ur")]["split"] == "test"
                alt = to_style_b(g[(label, "ro")]["text"])[0] if is_test else ""
                rows.append({"batch": bi, "row_id": f"{f}-{label}", "family_id": f, "split": g[(label, "ur")]["split"],
                             "topic_group": g[(label, "ur")]["harm_group"], "safety_label": label,
                             "english_reference": g[(label, "en")]["text"], "intended_meaning_en": g[(label, "ur")]["intended_meaning_en"],
                             "urdu_script": g[(label, "ur")]["text"], "roman_urdu": g[(label, "ro")]["text"],
                             "roman_urdu_alt_candidate": alt,
                             "notes_for_reviewer": " | ".join(notes_for(audit[f], label) + (pair_notes(audit[f]) if label == "harmful" else []))})
    return rows, batches, fam, audit


def main() -> int:
    rows, batches, fam, audit = pack_rows()
    edits = sheet_edits(PACK / "AHMAD_REVIEW.csv", rows)
    if edits and "--force" not in sys.argv[1:]:
        print(f"REFUSING: AHMAD_REVIEW.csv holds {edits} cell(s) filled in or changed by the reviewer. Run scripts/import_review.py "
              "first (it keeps a copy under returns/), then pass --force if the sheet really should be rebuilt.")
        return 2
    with open(PACK / "AHMAD_REVIEW.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})

    status_path = PACK / "review_status.json"
    answered = set(json.loads(status_path.read_text(encoding="utf-8")).get("rows", {})) if status_path.exists() else set()
    kept = []
    for bi, batch in enumerate(batches, 1):
        target = PACK / f"AHMAD_REVIEW_BATCH_{bi:02d}.md"
        if target.exists() and all(f"{f}-{lab}" in answered for f in batch for lab in ("harmful", "benign")):
            kept.append(f"{bi:02d}")
            continue
        split = fam[batch[0]][("harmful", "ur")]["split"]
        L = [f"# Review batch {bi:02d} of {len(batches)}: {len(batch)} matched sets ({split} families)", "",
             "Please read [`AHMAD_REVIEW_GUIDE.md`](AHMAD_REVIEW_GUIDE.md) first (two minutes). Then, for each request below, judge the",
             "Urdu and the Roman Urdu and fill in the answer block at the end of this file.", "",
             "Each matched set has one harmful request and one harmless request about the same topic. The harmful ones only",
             "state what someone wants; they contain no instructions. Please do not make them more detailed.", ""]
        for i, f in enumerate(batch, 1):
            a = audit[f]
            L += [f"## {i}. `{f}`", "", f"Topic group: {a['harm_group']}. Split: {a['split']}.", ""]
            for label, tag in (("harmful", "H"), ("benign", "B")):
                g = fam[f]
                L += [f"**{tag} — {LABEL_NAME[label]}** (label: `{label}`)", "",
                      f"- English: {g[(label, 'en')]['text']}",
                      f"- Intended meaning: {g[(label, 'ur')]['intended_meaning_en']}",
                      f"- Urdu script: {g[(label, 'ur')]['text']}",
                      f"- Roman Urdu: {g[(label, 'ro')]['text']}"]
                if a["split"] == "test":
                    L.append(f"- Other spelling (candidate, drafted by rule): {to_style_b(g[(label, 'ro')]['text'])[0]}")
                for n in notes_for(a, label):
                    L.append(f"- _{n}_")
                L.append("")
            pn = pair_notes(a)
            if pn:
                L += ["Notes on the pair (not confirmed by a person):", ""] + [f"- _{n}_" for n in pn] + [""]
        L += ["---", "", "## Your answer", "",
              "Copy this block, fill in the blanks and send it back. `ur` and `ro` are 1 to 5 (5 = completely natural) or `U`",
              "(unable to judge). `same`, `label`, `alt` and `pair` are `y`, `n` or `?`.", "", "```"]
        for f in batch:
            alt = "  alt=" if audit[f]["split"] == "test" else ""
            L += [f"{f} H  ur=  ro=  same=  label={alt}", f"{f} B  ur=  ro=  same=  label={alt}", f"{f} pair="]
        L += ["```", "", "If a sentence should be changed, add a line for it **in the same message** (examples). Please write the",
              "sentence itself: a correction without its text cannot be applied, and nothing is ever written in its place.", "", "```",
              f"fix {batch[0]} H ro: <your Roman Urdu sentence>", f"fix {batch[0]} B ur: <your Urdu sentence>",
              f"fix {batch[0]} H alt: <your spelling>", f"note {batch[0]}: <anything you want to say about this set>", "```", "",
              "If the harmless request does not fit the harmful one (`pair=n`), you can propose another harmless request. Give it",
              "in English, Urdu and Roman Urdu. It is recorded as a replacement, and the set stays out of comparisons between",
              "harmful and harmless requests until the replacement has been reviewed on its own:", "", "```",
              f"fix {batch[0]} B en: <the new harmless request in English>", f"fix {batch[0]} B ur: <the same in Urdu>",
              f"fix {batch[0]} B ro: <the same in Roman Urdu>", "```", "",
              f"If a whole set is fine in every respect, you can write one line instead: `{batch[0]}: all good`.", ""]
        target.write_text("\n".join(L), encoding="utf-8")
    print(f"review pack: {len(rows)} rows, {len(batches)} batches of {BATCH_SIZE} families; "
          f"batch 01 = {', '.join(batches[0])}; test families are batches 01-{sum(1 for b in batches if audit[b[0]]['split'] == 'test'):02d}"
          + (f"; answered batches left as they are: {', '.join(kept)}" if kept else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
