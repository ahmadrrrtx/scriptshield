"""Review revisions: what the reviewer said about each prompt pair, kept next to the frozen text.

The evaluated corpus (v0.2.0) is never edited, and every reported result belongs to it. A review revision is a
separate, versioned file with one row per reviewed prompt pair (one request in Urdu script and in Roman Urdu).
Each row holds the original text, the revised text, the ratings, the reviewer, the date and the reason, so that
a revised sentence can always be traced to the record it came from.

Three rules are enforced here and tested:

* text that the reviewer did not supply is never written: a correction that was announced without its text
  leaves the revised field empty and is reported as pending;
* a safety label is never changed by a revision;
* no revised text is described as evaluated. A full revised corpus is only built once no correction is pending.
"""
from __future__ import annotations

import hashlib
import json

from .schema import foreign_script_chars, script_of

PREVIOUS_VERSION = "0.2.0"
MAX_LEN, MIN_LEN = 600, 5
# how much longer (in words) a corrected harmful request may be before a person has to look at it
LENGTH_RATIO_FLAG = 1.5

FIELD_OF = {"ur": "corrected_ur", "ro": "corrected_ro", "alt": "corrected_alt", "en": "corrected_en", "meaning": "corrected_meaning"}
FIELD_NAME = {"ur": "Urdu script", "ro": "Roman Urdu", "alt": "second Roman-Urdu spelling", "en": "English sentence", "meaning": "intended meaning"}
EXCLUDED = "excluded: the reviewer judged the harmful and the harmless request of this family not comparable (pair = no)"


def current_revision(root) -> dict | None:
    """The manifest (REVISION.json) of the current review revision, or None if there is none."""
    from pathlib import Path
    folder = Path(root) / "data" / "revisions"
    if not (folder / "index.json").exists():
        return None
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    if not index.get("current"):
        return None
    return json.loads((folder / f"v{index['current']}" / "REVISION.json").read_text(encoding="utf-8"))


def all_revisions(root) -> list[dict]:
    """The manifests of every review revision, oldest first."""
    from pathlib import Path
    folder = Path(root) / "data" / "revisions"
    if not (folder / "index.json").exists():
        return []
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    return [json.loads((folder / f"v{e['id']}" / "REVISION.json").read_text(encoding="utf-8")) for e in index["revisions"]]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def text_problems(form: str, text: str) -> list[str]:
    """Why a corrected sentence cannot enter a dataset whose independent variable is the script."""
    out = []
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        out.append(f"length {len(text)} outside {MIN_LEN} to {MAX_LEN} characters")
    bad = foreign_script_chars(text, form)
    if bad:
        out.append(f"characters of another script: {''.join(bad)!r}")
    want = {"ur": "arabic", "ro": "latin", "en": "latin"}.get(form)
    if want and not bad and script_of(text) != want:
        out.append(f"script is {script_of(text)}, expected {want}")
    return out


def _join(fields: list[str]) -> str:
    names = [FIELD_NAME[f] for f in fields]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _score(v) -> tuple[int | None, str | None]:
    """A rating as (number, note): 1 to 5 is a number; 'ok' (set accepted as a whole) and 'unable' are notes."""
    if isinstance(v, int):
        return v, None
    return None, (None if v is None else str(v))


def review_record(pack_row: dict, ids: dict, cm_text: str, harm_category: str, status: dict, reviewer: dict,
                  revision_id: str, pair_verdict: str | None) -> dict:
    """One row of a revision. ``pack_row`` is the untouched row the reviewer saw; ``status`` his answers for it."""
    f = status
    kind, pending = f.get("correction_kind"), list(f.get("pending_fields", []))
    approved = bool(f.get("correction_approved")) if kind else None
    orig = {"ur": pack_row["urdu_script"], "ro": pack_row["roman_urdu"], "en": pack_row["english_reference"],
            "meaning": pack_row["intended_meaning_en"], "alt": pack_row["roman_urdu_alt_candidate"] or None}
    revised, changed, flags = {}, {}, []
    for key in ("ur", "ro", "en", "meaning", "alt"):
        new = f.get(FIELD_OF[key])
        if key in pending:                       # announced, text not received: nothing is written in its place
            revised[key], changed[key] = None, None
        elif new and approved:
            probs = text_problems(key, new) if key in ("ur", "ro", "en") else []
            if probs:                            # cannot be applied; the original stays, the reason is recorded
                flags.append(f"{FIELD_NAME[key]} not applied ({'; '.join(probs)})")
                revised[key], changed[key] = orig[key], False
            else:
                revised[key], changed[key] = new, new != orig[key]
        else:
            revised[key], changed[key] = orig[key], False
    if "ro" in pending and "alt" not in pending:
        # the second spelling that was judged belongs to the original sentence, and that sentence is being corrected
        revised["alt"], changed["alt"] = None, None
    if new_ro := f.get("corrected_ro"):
        if "alt" not in pending and not f.get("corrected_alt") and changed["ro"]:
            # the confirmed second spelling belonged to the original sentence; none exists for the corrected one
            revised["alt"], changed["alt"] = None, None
        if pack_row["safety_label"] == "harmful" and len(new_ro.split()) > LENGTH_RATIO_FLAG * len(orig["ro"].split()):
            flags.append("corrected harmful request is more than half longer than the original: check that no detail was added")

    if not kind:
        state, reason = None, {"accepted": "No change. The reviewer accepted both scripts as they are."}.get(
            f["status"], f"No change. Review status: {f['status'].replace('_', ' ')}.")
    elif pending:
        state = "text not received"
        what = "a replacement of this request" if kind == "replacement" else "a correction of the wording"
        reason = (f"The reviewer announced {what} ({_join(pending)}). The text has not been received. "
                  "The original is kept and nothing was written in its place.")
    elif not approved:
        state = "proposed, not approved by the project owner"
        reason = "The reviewer proposed a correction. It is not applied until the project owner approves it."
    else:
        applied = [k for k in ("ur", "ro", "en", "meaning", "alt") if changed.get(k)]
        state = "applied" if applied and not any("not applied" in x for x in flags) else ("applied in part" if applied else "not applied")
        reason = (("Request replaced by the reviewer" if kind == "replacement" else "Wording corrected by the reviewer")
                  + (f" ({_join(applied)})." if applied else "."))
    drafted = [k for k in ("en", "meaning") if k in f.get("maintainer_fields", []) and changed.get(k)]
    if drafted:
        reason += (f" {_join(drafted)[:1].upper() + _join(drafted)[1:]}: written by the maintainer to match the reviewer's sentences, "
                   "not the reviewer's wording.")
    if pair_verdict == "no":
        reason += (" The reviewer judged the original harmful and harmless request of this family not comparable (pair = no); the family is "
                   "left out of comparisons between harmful and harmless requests until a replacement has been reviewed as a pair.")
    written_by = lambda key: None if not changed.get(key) else ("maintainer" if key in drafted else "reviewer")  # noqa: E731

    text_final = not pending and state not in ("proposed, not approved by the project owner",)
    differs = None if not text_final else bool(changed["ur"] or changed["ro"])
    ur_n, ur_note = _score(f.get("ur"))
    ro_n, ro_note = _score(f.get("ro"))
    note = "; ".join(f"{k}: {v}" for k, v in (("Urdu script", ur_note), ("Roman Urdu", ro_note)) if v) or None
    return {
        "pair_id": pack_row["row_id"], "family_id": pack_row["family_id"], "safety_label": pack_row["safety_label"],
        "split": pack_row["split"], "harm_group": pack_row["topic_group"], "harm_category": harm_category,
        "id_ur": ids["ur"], "id_ro": ids["ro"], "id_en": ids["en"], "id_cm": ids["cm"],
        "ur_original": orig["ur"], "ur_revised": revised["ur"], "ur_changed": changed["ur"],
        "ro_original": orig["ro"], "ro_revised": revised["ro"], "ro_changed": changed["ro"],
        "en_original": orig["en"], "en_revised": revised["en"], "en_changed": changed["en"],
        "en_revised_written_by": written_by("en"),
        "intended_meaning_en_original": orig["meaning"], "intended_meaning_en_revised": revised["meaning"],
        "intended_meaning_en_changed": changed["meaning"],
        "intended_meaning_en_revised_written_by": written_by("meaning"),
        "ro_alt_candidate": orig["alt"], "ro_alt_revised": revised["alt"],
        "cm_original": cm_text,
        "cm_status": ("not reviewed" if not kind else
                      "not reviewed; may no longer match the corrected Urdu and Roman Urdu" if kind == "wording" else
                      "not reviewed; it is the code-mixed form of a request that is to be replaced" if pending else
                      "not reviewed; it is the code-mixed form of the request that was replaced, and none exists for the new request"),
        "review_status": f["status"],
        "ur_naturalness": ur_n, "ro_naturalness": ro_n, "naturalness_note": note,
        "same_meaning": f.get("same"), "label_plausible": f.get("label"), "alt_spelling_ok": f.get("alt"),
        "pair_comparable": pair_verdict,
        "matched_pair_analysis": EXCLUDED if pair_verdict == "no" else ("included" if pair_verdict == "yes" else "not settled"),
        "comments": f.get("comments") or None,
        "correction_kind": kind, "correction_state": state,
        "correction_pending_fields": ", ".join(pending) or None,
        "correction_approved_by_owner": approved, "correction_date": f.get("correction_date") if kind else None,
        "correction_flags": "; ".join(flags) or None,
        "revision_reason": reason,
        "reviewer_name": reviewer["name"], "reviewer_handle": reviewer["handle"], "reviewer_role": reviewer["role"],
        "review_type": reviewer["review_type"], "review_date": f.get("review_date"), "review_batch": f.get("review_batch"),
        "review_source_file": f.get("review_source_file") or f.get("source_file"),
        "previous_dataset_version": PREVIOUS_VERSION, "updated_dataset_version": revision_id,
        "original_text_used_in_v0_2_0_as": {"test": "frozen test set", "dev": "development set (selection of layer and strength)",
                                             "calibration": "calibration set (steering vectors)"}[pack_row["split"]],
        "revised_text_differs_from_original": differs,
        "revised_text_used_in_any_result": False,
    }


def review_records(pack_rows: list[dict], corpus: list[dict], status: dict, revision_id: str) -> list[dict]:
    """All reviewed prompt pairs as revision rows, in the order of the review pack."""
    by = {(r["family_id"], r["safety_label"], r["form"]): r for r in corpus}
    out = []
    for p in pack_rows:
        f = status["rows"].get(p["row_id"])
        if not f:
            continue
        fam, lab = p["family_id"], p["safety_label"]
        for form, col in (("ur", "urdu_script"), ("ro", "roman_urdu"), ("en", "english_reference")):
            if by[(fam, lab, form)]["text"] != p[col]:
                raise ValueError(f"{p['row_id']}: the pack row is not the corpus text ({form})")
        ids = {form: by[(fam, lab, form)]["id"] for form in ("ur", "ro", "en", "cm")}
        out.append(review_record(p, ids, by[(fam, lab, "cm")]["text"], by[(fam, lab, "ur")]["harm_category"], f,
                                 status["reviewer"], revision_id, status.get("pair_verdicts", {}).get(fam)))
    return out


def pending_rows(rows: list[dict]) -> list[str]:
    return [r["pair_id"] for r in rows if r["correction_pending_fields"]]


def revised_corpus(corpus: list[dict], rows: list[dict], reviewer_id: str) -> list[dict]:
    """The corpus with every applied correction, in the record format of data/schemas/revised_prompt.schema.json.

    Refuses while a correction is pending: a file called a revised corpus must not carry sentences the reviewer
    wanted changed. Unreviewed records are copied and stay ``unreviewed``. Every record says whether its text is
    the one that was evaluated in v0.2.0; a changed record carries the original text next to the new one.
    """
    waiting = pending_rows(rows)
    if waiting:
        raise ValueError(f"corrections announced without text: {waiting}; a revised corpus is built once they have arrived")
    by = {r["pair_id"]: r for r in rows}
    out = []
    for rec in corpus:
        new = dict(rec)
        row = by.get(f"{rec['family_id']}-{rec['safety_label']}")
        if row:
            form = rec["form"]
            replaced = row["correction_kind"] == "replacement" and bool(row["en_changed"] or row["intended_meaning_en_changed"])
            if form in ("ur", "ro", "en") and row[f"{form}_changed"]:
                new["text"] = row[f"{form}_revised"]
            if row["intended_meaning_en_changed"] and not (form == "cm" and replaced):
                new["intended_meaning_en"] = row["intended_meaning_en_revised"]
            touched = any(row[k] for k in ("ur_changed", "ro_changed", "en_changed", "intended_meaning_en_changed"))
            if form in ("ur", "ro"):                                  # the two forms the reviewer judged
                ok = row["review_status"] in ("accepted", "corrected")
                changed = bool(row[f"{form}_changed"])
                new["validation_status"] = "corrected" if changed else ("approved" if ok else "unreviewed")
                if ok:
                    new["reviewer_id"] = reviewer_id
                    if not touched and row["same_meaning"]:           # judged for the two sentences as they still are
                        new["same_meaning"] = row["same_meaning"]
                    if not changed and row[f"{form}_naturalness"] is not None:
                        new["naturalness"] = row[f"{form}_naturalness"]   # the rating was given for exactly this text
            note = []
            if form == "en" and row["en_changed"]:
                if row["en_revised_written_by"] == "reviewer":        # an English sentence supplied by the reviewer
                    new["validation_status"], new["reviewer_id"] = "corrected", reviewer_id
                else:                                                 # stays unreviewed: nobody but its writer has read it
                    note.append("English sentence written by the maintainer to match the reviewer's replacement; not reviewed")
            if form != "cm" and row["intended_meaning_en_revised_written_by"] == "maintainer":
                note.append("intended meaning written by the maintainer to match the reviewer's replacement")
            if form == "cm" and replaced:
                # the request was replaced and no code-mixed sentence was supplied for the new one: this record still
                # holds the old request, with its old meaning, and must not be used
                new["validation_status"], new["reviewer_id"] = "rejected", reviewer_id
                note.append("belongs to the request that the reviewer replaced; no code-mixed form exists for the new request")
            elif form == "cm" and touched:
                note.append("code-mixed form not revised; it may no longer match the corrected Urdu and Roman Urdu")
            if row["pair_comparable"] == "no":
                note.append("family left out of harmful-against-harmless comparisons (reviewer: pair = no)")
            if note:
                new["notes"] = "; ".join(note)
        new["text_unchanged_since_v0_2_0"] = new["text"] == rec["text"]
        if not new["text_unchanged_since_v0_2_0"]:
            new["text_v0_2_0"] = rec["text"]
        out.append(new)
    if [r["safety_label"] for r in out] != [r["safety_label"] for r in corpus] or [r["id"] for r in out] != [r["id"] for r in corpus]:
        raise AssertionError("a revision must keep every id and every safety label")
    return out


def summarize(rows: list[dict], status: dict) -> dict:
    """Counts for the revision manifest and for the documents."""
    fams = sorted({r["family_id"] for r in rows})
    num = lambda key: [r[key] for r in rows if r[key] is not None]  # noqa: E731
    yes = lambda key: sum(1 for r in rows if r[key] == "yes")  # noqa: E731
    with_corr = [r for r in rows if r["correction_kind"]]
    return {
        "prompt_pairs_reviewed": len(rows), "prompt_pairs_total": status["n_rows_total"],
        "families_reviewed": len(status["families_fully_reviewed"]), "families_with_any_review": len(fams), "families_total": status["n_rows_total"] // 2,
        "reviewed_families_by_split": {s: sum(1 for f in fams if next(r for r in rows if r["family_id"] == f)["split"] == s)
                                       for s in ("test", "dev", "calibration")},
        "review_status": {s: sum(1 for r in rows if r["review_status"] == s) for s in sorted({r["review_status"] for r in rows})},
        "naturalness": {"urdu_script": {"rated": len(num("ur_naturalness")), "min": min(num("ur_naturalness"), default=None),
                                        "mean": round(sum(num("ur_naturalness")) / len(num("ur_naturalness")), 2) if num("ur_naturalness") else None},
                        "roman_urdu": {"rated": len(num("ro_naturalness")), "min": min(num("ro_naturalness"), default=None),
                                       "mean": round(sum(num("ro_naturalness")) / len(num("ro_naturalness")), 2) if num("ro_naturalness") else None}},
        "same_meaning_yes": yes("same_meaning"), "label_plausible_yes": yes("label_plausible"),
        "alt_spelling_judged": sum(1 for r in rows if r["alt_spelling_ok"] is not None), "alt_spelling_yes": yes("alt_spelling_ok"),
        "pair_verdicts": {v: sum(1 for x in status.get("pair_verdicts", {}).values() if x == v)
                          for v in sorted(set(status.get("pair_verdicts", {}).values()))},
        "excluded_from_matched_pair_analysis": list(status.get("excluded_from_matched_pair_analysis", [])),
        "corrections": {
            "prompt_pairs_with_a_correction": len(with_corr),
            "applied": sum(1 for r in with_corr if r["correction_state"] in ("applied", "applied in part")),
            "text_not_received": sum(1 for r in with_corr if r["correction_state"] == "text not received"),
            "not_approved": sum(1 for r in with_corr if r["correction_state"] == "proposed, not approved by the project owner"),
            "english_written_by_maintainer": [r["pair_id"] for r in with_corr
                                              if "maintainer" in (r["en_revised_written_by"], r["intended_meaning_en_revised_written_by"])],
            "fields_written_by_maintainer": {r["pair_id"]: [name for name, col in (("English sentence", "en_revised_written_by"),
                                                                                     ("intended meaning", "intended_meaning_en_revised_written_by"))
                                                             if r[col] == "maintainer"]
                                             for r in with_corr if "maintainer" in (r["en_revised_written_by"], r["intended_meaning_en_revised_written_by"])},
            "not_applied": sum(1 for r in with_corr if r["correction_state"] == "not applied"),
            "replacements": sorted(r["pair_id"] for r in with_corr if r["correction_kind"] == "replacement"),
            "flagged": sorted(r["pair_id"] for r in with_corr if r["correction_flags"]),
        },
        "sentences_changed": sum(1 for r in rows for k in ("ur_changed", "ro_changed", "en_changed") if r[k]),
    }
