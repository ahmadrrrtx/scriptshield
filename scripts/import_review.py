#!/usr/bin/env python3
"""Import the reviewer's answers and record the review status of every prompt pair.

    python3 scripts/import_review.py

Reads everything under data/reviewer_pack/returns/:
    *.txt   answer blocks pasted from the batch files (saved exactly as received, or transcribed line by line
            from a message that is kept next to it as *.md)
    *.csv   a filled-in copy of AHMAD_REVIEW.csv
Later files override earlier ones row by row (files are read in name order). Files with other endings are
kept for the record and not parsed.

Lines of a *.txt file, besides the answer block of a batch:
    batch: 01                       which batch the file answers
    received: 2026-11-13            the day the answers arrived; recorded as the review date of its rows
    apply: yes                      the project owner said that the corrections of this file are to be applied
    fix <family> <H|B> <field>: <text>      field is ur, ro, alt, en or meaning
    announced <family> <H|B>: <fields>      the reviewer said these fields are to be corrected, text to follow
    drafted <family> <H|B> <en|meaning>: <text>     the English sentence or the intended meaning that the maintainer
                                            wrote to match a request the reviewer replaced in Urdu and Roman Urdu.
                                            Recorded as the maintainer's, never as the reviewer's. Urdu and Roman
                                            Urdu can not be drafted: they come from the reviewer or not at all.
    kind <family> <H|B>: wording|replacement      what the reviewer called his correction. Without this line a
                                            correction that changes the English sentence counts as a replacement.
    note <family> [H|B]: <text>
    note overall: <text>            a remark about the whole batch; kept with the batch, not with a prompt pair

If AHMAD_REVIEW.csv itself was filled in or edited in place, a copy of it is first saved as
returns/AHMAD_REVIEW_edited_in_place.csv and read like any other return. A sentence that was changed
directly in its cell counts as a proposed correction; the original always comes from the corpus.

Writes data/reviewer_pack/review_status.json (one entry per reviewed row) and
data/reviewer_pack/proposed_revisions.jsonl (one line per suggested correction).

Rules that keep the record honest:
  * a row with no answer stays "unreviewed"; nothing is accepted by default;
  * a correction is a PROPOSAL until the project owner says it is to be applied ("apply: yes"); it then enters a
    review revision (scripts/build_dataset_revision.py), never the evaluated corpus;
  * a correction that was announced without its text is "correction_pending"; no text is ever written for it;
  * the reviewer's sentences are stored character for character; English written by the maintainer to go with a
    replaced request is marked as such in every file that carries it;
  * a correction that changes the intended meaning is a REPLACEMENT of the request, not a wording fix, and is
    recorded as such. One that changes the English sentence is a replacement too, unless the reviewer said that
    he only improved the wording ("kind ... : wording"); the intended meaning must then be unchanged;
  * "label = no" always sends the row to separate adjudication;
  * "pair = no" puts the family on the list of families to leave out of harmful-against-harmless comparisons;
  * the reviewer is recorded as one participant (the project author), not as an independent expert.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data" / "reviewer_pack"
IN_PLACE_COPY = "AHMAD_REVIEW_edited_in_place.csv"


def _builder():
    spec = importlib.util.spec_from_file_location("build_review_pack", ROOT / "scripts" / "build_review_pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
REVIEWER = {"name": "Muhammad Ahmad", "handle": "ahmadrrrtx",
            "role": "project author; participant review, not independent expert validation",
            "review_type": "participant-provided native Urdu / Roman Urdu linguistic review",
            "language_background": "native Urdu / Roman Urdu speaker (as stated by the reviewer)",
            "n_reviewers": 1, "independent": False, "professional_translation_certification": False,
            "multi_reviewer_consensus": False}
STATUSES = ("accepted", "corrected", "correction_pending", "rejected", "uncertain", "unable_to_judge")
RATING_KEYS = ("ur", "ro", "same", "label")
FIX_KEYS = {"ur": "corrected_ur", "ro": "corrected_ro", "alt": "corrected_alt", "en": "corrected_en", "meaning": "corrected_meaning"}
DRAFTABLE = ("en", "meaning")       # what the maintainer may write to go with a request the reviewer replaced
# what a correction field is called in the proposals file, and the column of the pack that holds the original
FIX_FORMS = (("corrected_ur", "ur", "urdu_script"), ("corrected_ro", "ro", "roman_urdu"), ("corrected_alt", "ro_alt", "roman_urdu_alt_candidate"),
             ("corrected_en", "en", "english_reference"), ("corrected_meaning", "intended_meaning_en", "intended_meaning_en"))
YES, NO, UNSURE, UNABLE = "yes", "no", "uncertain", "unable"
_YN = {"y": YES, "yes": YES, "haan": YES, "han": YES, "ok": YES, "n": NO, "no": NO, "nahi": NO, "nahin": NO,
       "?": UNSURE, "uncertain": UNSURE, "unsure": UNSURE, "maybe": UNSURE, "u": UNABLE, "unable": UNABLE}
TAG = {"h": "harmful", "b": "benign", "harmful": "harmful", "benign": "benign", "harmless": "benign"}


def norm_score(v: str):
    v = v.strip().lower().rstrip(",;")
    if v in {"1", "2", "3", "4", "5"}:
        return int(v)
    if v in {"u", "unable"}:
        return UNABLE
    if v in {"ok", "good"}:
        return "ok"
    raise ValueError(f"naturalness must be 1-5 or U, got {v!r}")


def norm_yn(v: str) -> str:
    v = v.strip().lower().rstrip(",;")
    if v not in _YN:
        raise ValueError(f"expected y, n or ?, got {v!r}")
    return _YN[v]


_DIRECTIVE = re.compile(r"^(batch|received|apply|note\s+overall)\s*:\s*(.+)$", re.I)
KINDS = ("wording", "replacement")


def file_meta(text: str) -> dict:
    """The file-level lines of a return: {'batch': '01', 'received': '2026-11-13', 'apply': True, 'note': '...'}."""
    meta: dict = {}
    for raw in text.splitlines():
        m = _DIRECTIVE.match(raw.strip().strip("`"))
        if not m:
            continue
        key, val = " ".join(m.group(1).lower().split()), m.group(2).strip()
        if key == "note overall":
            meta["note"] = (meta.get("note", "") + " " + val).strip()
        elif key == "apply":
            meta["apply"] = val.lower() in {"yes", "y", "true"}
        elif key == "received":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                raise ValueError(f"received: expected YYYY-MM-DD, got {val!r}")
            meta["received"] = val
        else:
            meta["batch"] = val
    return meta


def pending_fields(f: dict) -> list[str]:
    """Fields the reviewer said he corrected and for which no corrected text has arrived."""
    return [k for k in f.get("announced", []) if not f.get(FIX_KEYS[k])]


def correction_kind(f: dict) -> str | None:
    """'replacement' if the English sentence or the intended meaning changes, 'wording' for any other correction."""
    touched = set(f.get("announced", [])) | {k for k, col in FIX_KEYS.items() if f.get(col)}
    if touched and f.get("kind_stated") in KINDS and not (f["kind_stated"] == "wording" and "meaning" in touched):
        return f["kind_stated"]                 # the reviewer's own word for it
    if not touched:
        return None
    return "replacement" if touched & {"en", "meaning"} else "wording"


def parse_text(text: str, known_families: set[str]) -> tuple[dict, list[str]]:
    """{row_id: fields} from an answer block. Unknown or malformed lines are returned as problems, never guessed."""
    rows: dict = {}
    problems: list[str] = []

    def row(fam: str, label: str) -> dict:
        return rows.setdefault(f"{fam}-{label}", {})

    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().strip("`")
        if not line or line.startswith("#") or _DIRECTIVE.match(line):
            continue
        try:
            m = re.match(r"^fix\s+(\w+)\s+(\w+)\s+(ur|ro|alt|en|meaning)\s*:\s*(.+)$", line, re.I)
            if m:
                fam, tag, form, new = m.group(1), m.group(2).lower(), m.group(3).lower(), m.group(4).strip()
                if fam not in known_families or tag not in TAG or new.startswith("<"):
                    raise ValueError("unknown family or label, or the example text was left in")
                r = row(fam, TAG[tag])
                r[FIX_KEYS[form]] = new
                if form in r.get("maintainer_fields", []):         # the reviewer's own text replaces a draft
                    r["maintainer_fields"].remove(form)
                continue
            m = re.match(r"^drafted\s+(\w+)\s+(\w+)\s+(\w+)\s*:\s*(.+)$", line, re.I)
            if m:
                fam, tag, form, new = m.group(1), m.group(2).lower(), m.group(3).lower(), m.group(4).strip()
                if form not in DRAFTABLE:
                    raise ValueError("only the English sentence and the intended meaning can be drafted by the maintainer; "
                                     "Urdu and Roman Urdu come from the reviewer")
                if fam not in known_families or tag not in TAG or new.startswith("<"):
                    raise ValueError("unknown family or label, or the example text was left in")
                r = row(fam, TAG[tag])
                r[FIX_KEYS[form]] = new
                r["maintainer_fields"] = [k for k in DRAFTABLE if k in set(r.get("maintainer_fields", [])) | {form}]
                r["maintainer_fields_in_this_file"] = list(r["maintainer_fields"])
                continue
            m = re.match(r"^kind\s+(\w+)\s+(\w+)\s*:\s*(\w+)\s*$", line, re.I)
            if m:
                fam, tag, kind = m.group(1), m.group(2).lower(), m.group(3).lower()
                if fam not in known_families or tag not in TAG or kind not in KINDS:
                    raise ValueError("unknown family or label, or a kind that is neither 'wording' nor 'replacement'")
                row(fam, TAG[tag])["kind_stated"] = kind
                continue
            m = re.match(r"^announced\s+(\w+)\s+(\w+)\s*:\s*(.+)$", line, re.I)
            if m:
                fam, tag, fields = m.group(1), m.group(2).lower(), re.split(r"[\s,]+", m.group(3).strip().lower())
                if fam not in known_families or tag not in TAG or not fields or any(x not in FIX_KEYS for x in fields):
                    raise ValueError("unknown family, label or field in an 'announced' line")
                r = row(fam, TAG[tag])
                r["announced"] = [k for k in FIX_KEYS if k in set(fields) | set(r.get("announced", []))]
                continue
            m = re.match(r"^note\s+(\w+)(?:\s+(H|B))?\s*:\s*(.+)$", line, re.I)
            if m:
                fam, tag, txt = m.group(1), (m.group(2) or "").lower(), m.group(3).strip()
                if fam not in known_families or txt.startswith("<"):
                    raise ValueError("unknown family, or the example text was left in")
                for label in ([TAG[tag]] if tag else ["harmful", "benign"]):
                    r = row(fam, label)
                    r["comments"] = (r.get("comments", "") + " " + txt).strip()
                continue
            m = re.match(r"^(\w+)\s*:\s*all\s+good\.?$", line, re.I)
            if m:
                if m.group(1) not in known_families:
                    raise ValueError("unknown family")
                for label in ("harmful", "benign"):
                    row(m.group(1), label).update({"ur": "ok", "ro": "ok", "same": YES, "label": YES, "pair": YES})
                continue
            m = re.match(r"^(\w+)\s+pair\s*=\s*(\S*)$", line, re.I)
            if m:
                if m.group(1) not in known_families:
                    raise ValueError("unknown family")
                if m.group(2):
                    for label in ("harmful", "benign"):
                        row(m.group(1), label)["pair"] = norm_yn(m.group(2))
                continue
            m = re.match(r"^(\w+)\s+(H|B)\b(.*)$", line, re.I)
            if m:
                if m.group(1) not in known_families:
                    raise ValueError("unknown family")
                r = {}
                keys = r"(?:ur|ro|same|label|alt)"
                for key, val in re.findall(rf"\b({keys})\s*=\s*(.*?)(?=\s*(?:\b{keys}\s*=|$))", m.group(3), re.I):
                    val = val.strip().strip(",;|")
                    if val:
                        r[key.lower()] = norm_score(val) if key.lower() in ("ur", "ro") else norm_yn(val)
                if r:
                    row(m.group(1), TAG[m.group(2).lower()]).update(r)
                continue
            raise ValueError("line not understood")
        except ValueError as e:
            problems.append(f"line {n}: {e}: {raw.strip()[:80]}")
    return {k: v for k, v in rows.items() if v}, problems


def parse_csv(path: Path, originals: dict | None = None) -> dict:
    rows = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        f = {}
        o = (originals or {}).get(r.get("row_id"))
        if o is not None:        # a sentence changed directly in its cell is a proposed correction
            for col, key in (("urdu_script", "corrected_ur"), ("roman_urdu", "corrected_ro"), ("roman_urdu_alt_candidate", "corrected_alt")):
                cell = (r.get(col) or "").strip()
                if cell and cell != (o.get(col) or "").strip():
                    f[key] = cell
        for col, key, fn in (("ur_naturalness_1to5_or_U", "ur", norm_score), ("ro_naturalness_1to5_or_U", "ro", norm_score),
                             ("same_meaning_yes_no_uncertain", "same", norm_yn), ("label_plausible_yes_no_uncertain", "label", norm_yn),
                             ("alt_spelling_ok_yes_no_uncertain", "alt", norm_yn), ("pair_comparable_yes_no_uncertain", "pair", norm_yn)):
            if (r.get(col) or "").strip():
                f[key] = fn(r[col])
        for col, key in (("corrected_urdu", "corrected_ur"), ("corrected_roman_urdu", "corrected_ro"),
                         ("corrected_alt_spelling", "corrected_alt"), ("comments", "comments")):
            if (r.get(col) or "").strip():
                f[key] = r[col].strip()
        if f:
            rows[r["row_id"]] = f
    return rows


def status_of(f: dict) -> tuple[str, bool]:
    """(status, needs separate adjudication). See the module docstring for the rules."""
    judged = [f.get(k) for k in RATING_KEYS if k in f]
    fixed = any(f.get(k) for k in ("corrected_ur", "corrected_ro", "corrected_en", "corrected_meaning"))
    pending = pending_fields(f)
    if not judged and not fixed and not pending:
        return "unreviewed", False
    if f.get("label") == NO:
        return "rejected", True
    # a replacement changes what is asked: it needs the owner's word before it is more than a proposal
    adjudicate = correction_kind(f) == "replacement" and not f.get("correction_approved")
    if pending:
        return "correction_pending", adjudicate
    if fixed:
        return "corrected", adjudicate
    if f.get("same") == NO:
        return "rejected", False
    if judged and all(v == UNABLE for v in judged):
        return "unable_to_judge", False
    scores = [f.get("ur"), f.get("ro")]
    complete = all(k in f for k in ("ur", "ro", "same", "label"))
    if UNSURE in judged or UNABLE in judged or any(isinstance(s, int) and s <= 3 for s in scores) or not complete:
        return "uncertain", False
    return "accepted", False


def main() -> int:
    builder = _builder()
    pristine = builder.pack_rows()[0]
    originals = {r["row_id"]: r for r in pristine}          # the corpus text, never the possibly edited sheet
    families = {r["family_id"] for r in originals.values()}
    (PACK / "returns").mkdir(exist_ok=True)
    if builder.sheet_edits(PACK / "AHMAD_REVIEW.csv", pristine):
        shutil.copyfile(PACK / "AHMAD_REVIEW.csv", PACK / "returns" / IN_PLACE_COPY)
    merged: dict = {}
    problems: list[str] = []
    batches: dict = {}
    sources = sorted(p for p in (PACK / "returns").glob("*") if p.suffix in {".txt", ".csv"})
    for p in sources:
        meta: dict = {}
        if p.suffix == ".txt":
            text = p.read_text(encoding="utf-8")
            try:
                meta = file_meta(text)
            except ValueError as e:
                problems.append(f"{p.name}: {e}")
            got, prob = parse_text(text, families)
            problems += [f"{p.name}: {x}" for x in prob]
        else:
            got = parse_csv(p, originals)
        for rid, f in got.items():
            if rid not in originals:
                problems.append(f"{p.name}: unknown row {rid}")
                continue
            m = merged.setdefault(rid, {})
            if "announced" in f:                                    # what was announced earlier stays announced
                f = {**f, "announced": [k for k in FIX_KEYS if k in set(f["announced"]) | set(m.get("announced", []))]}
            if "maintainer_fields" in f or "maintainer_fields" in m:
                # a field stays "written by the maintainer" until the reviewer sends his own text for it
                own = {k for k, col in FIX_KEYS.items() if f.get(col)} - set(f.get("maintainer_fields", []))
                keep = (set(m.get("maintainer_fields", [])) - own) | set(f.get("maintainer_fields", []))
                f = {**f, "maintainer_fields": [k for k in DRAFTABLE if k in keep]}
            m.update(f)
            m["source_file"] = p.name
            if any(k in f for k in RATING_KEYS):                    # the file that carries the ratings dates the review
                m["review_source_file"] = p.name
                for key, name in (("received", "review_date"), ("batch", "review_batch")):
                    if meta.get(key):
                        m[name] = meta[key]
            own = {k for k, col in FIX_KEYS.items() if f.get(col)} - set(f.get("maintainer_fields_in_this_file", []))
            if own or "announced" in f:
                m["correction_source_file"] = p.name
                m["correction_approved"] = bool(meta.get("apply"))
                if meta.get("received"):
                    m["correction_date"] = meta["received"]
            if f.get("maintainer_fields_in_this_file"):
                m["maintainer_source_file"] = p.name
            m.pop("maintainer_fields_in_this_file", None)
        if meta.get("batch"):
            b = batches.setdefault(meta["batch"], {"received": meta.get("received"), "source_files": [], "families": []})
            b["source_files"].append(p.name)
            if meta.get("note"):
                b["reviewer_note"] = (b.get("reviewer_note", "") + " " + meta["note"]).strip()
            b["families"] = sorted(set(b["families"]) | {originals[r]["family_id"] for r in got if r in originals})
    rows, revisions = {}, []
    for rid, f in sorted(merged.items()):
        status, adjudicate = status_of(f)
        if status == "unreviewed":
            continue
        rows[rid] = {**f, "status": status, "needs_adjudication": adjudicate}
        if not f.get("maintainer_fields"):
            rows[rid].pop("maintainer_fields", None)
        elif not (f.get("corrected_ur") and f.get("corrected_ro")):
            # English must follow the reviewer's sentences, never lead them
            problems.append(f"{rid}: English drafted by the maintainer, but the reviewer's Urdu and Roman Urdu sentence are not both there")
        kind, pending = correction_kind(f), pending_fields(f)
        if f.get("kind_stated") and kind and kind != f["kind_stated"]:
            problems.append(f"{rid}: called a wording correction, but the intended meaning changes; recorded as a replacement")
        if f.get("kind_stated") and not kind:
            problems.append(f"{rid}: a kind is stated but there is no correction")
        if kind:
            rows[rid]["correction_kind"] = kind
        if pending:
            rows[rid]["pending_fields"] = pending
        o = originals[rid]
        for key, form, col in FIX_FORMS:
            if f.get(key):
                state = (f"approved by the project owner ({f.get('correction_date', 'date not recorded')}); applied in a review revision if it passes the checks"
                         if f.get("correction_approved") else "proposed, not yet approved for a dataset version")
                revisions.append({"row_id": rid, "family_id": o["family_id"], "safety_label": o["safety_label"], "split": o["split"],
                                  "form": form, "kind": kind, "original": o[col], "proposed": f[key], "reason": f.get("comments", ""),
                                  "proposed_by": ("maintainer (written to match the reviewer's replacement; not the reviewer's wording)"
                                                  if {"en": "en", "intended_meaning_en": "meaning"}.get(form) in f.get("maintainer_fields", [])
                                                  else REVIEWER["name"]), "state": state})
    counts = {s: sum(1 for r in rows.values() if r["status"] == s) for s in STATUSES}
    counts["unreviewed"] = len(originals) - len(rows)
    fam_done = sorted(f for f in families if all(f"{f}-{lab}" in rows for lab in ("harmful", "benign")))
    # one verdict per family on whether its harmful and its harmless request fit together
    pair_verdicts = {}
    for f in sorted(families):
        got = {rows[f"{f}-{lab}"]["pair"] for lab in ("harmful", "benign") if f"{f}-{lab}" in rows and "pair" in rows[f"{f}-{lab}"]}
        if len(got) > 1:
            problems.append(f"{f}: the two rows carry different pair verdicts {sorted(got)}")
        if got:
            pair_verdicts[f] = NO if NO in got else sorted(got)[0]
    with_correction = {rid: r for rid, r in rows.items() if r.get("correction_kind")}
    corrections = {"rows_with_a_correction": len(with_correction),
                   "text_received": sum(1 for r in with_correction.values() if not r.get("pending_fields")),
                   "text_pending": [{"row_id": rid, "fields": r["pending_fields"]} for rid, r in with_correction.items() if r.get("pending_fields")],
                   "approved_by_owner": sum(1 for r in with_correction.values() if r.get("correction_approved")),
                   "replacements": sorted(rid for rid, r in with_correction.items() if r["correction_kind"] == "replacement")}
    doc = {"reviewer": REVIEWER, "sources": [p.name for p in sources], "n_rows_total": len(originals), "counts": counts,
           "families_fully_reviewed": fam_done, "batches": batches, "pair_verdicts": pair_verdicts,
           "excluded_from_matched_pair_analysis": sorted(f for f, v in pair_verdicts.items() if v == NO),
           "corrections": corrections, "problems": problems, "rows": rows}
    (PACK / "review_status.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (PACK / "proposed_revisions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in revisions), encoding="utf-8")
    print(f"review status: {counts} | families fully reviewed: {len(fam_done)} | corrections with text: {len(revisions)} | "
          f"corrections announced without text: {len(corrections['text_pending'])} | pair = no: {doc['excluded_from_matched_pair_analysis']} | "
          f"rows needing adjudication: {sum(r['needs_adjudication'] for r in rows.values())} | lines not understood: {len(problems)}")
    for x in problems[:20]:
        print("  NOT UNDERSTOOD:", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
