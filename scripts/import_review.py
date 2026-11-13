#!/usr/bin/env python3
"""Import the reviewer's answers and record the review status of every prompt pair.

    python3 scripts/import_review.py

Reads everything under data/reviewer_pack/returns/:
    *.txt   answer blocks pasted from the batch files (saved exactly as received)
    *.csv   a filled-in copy of AHMAD_REVIEW.csv
Later files override earlier ones row by row (files are read in name order).

If AHMAD_REVIEW.csv itself was filled in or edited in place, a copy of it is first saved as
returns/AHMAD_REVIEW_edited_in_place.csv and read like any other return. A sentence that was changed
directly in its cell counts as a proposed correction; the original always comes from the corpus.

Writes data/reviewer_pack/review_status.json (one entry per reviewed row) and
data/reviewer_pack/proposed_revisions.jsonl (one line per suggested correction).

Rules that keep the record honest:
  * a row with no answer stays "unreviewed"; nothing is accepted by default;
  * a correction is only a PROPOSAL here; it enters a new dataset version after it has been checked
    against the intended meaning and approved by the project owner;
  * "label = no" always sends the row to separate adjudication;
  * the reviewer is recorded as a participant (the project author), not as an independent expert.
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
            "role": "project author; participant review, not independent expert validation"}
STATUSES = ("accepted", "corrected", "rejected", "uncertain", "unable_to_judge")
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


def parse_text(text: str, known_families: set[str]) -> tuple[dict, list[str]]:
    """{row_id: fields} from an answer block. Unknown or malformed lines are returned as problems, never guessed."""
    rows: dict = {}
    problems: list[str] = []

    def row(fam: str, label: str) -> dict:
        return rows.setdefault(f"{fam}-{label}", {})

    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().strip("`")
        if not line or line.startswith("#"):
            continue
        try:
            m = re.match(r"^fix\s+(\w+)\s+(\w+)\s+(ur|ro|alt)\s*:\s*(.+)$", line, re.I)
            if m:
                fam, tag, form, new = m.group(1), m.group(2).lower(), m.group(3).lower(), m.group(4).strip()
                if fam not in known_families or tag not in TAG or new.startswith("<"):
                    raise ValueError("unknown family or label, or the example text was left in")
                row(fam, TAG[tag])[{"ur": "corrected_ur", "ro": "corrected_ro", "alt": "corrected_alt"}[form]] = new
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
    judged = [f.get(k) for k in ("ur", "ro", "same", "label") if k in f]
    if not judged and not any(k in f for k in ("corrected_ur", "corrected_ro")):
        return "unreviewed", False
    if f.get("label") == NO:
        return "rejected", True
    if f.get("corrected_ur") or f.get("corrected_ro"):
        return "corrected", False
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
    sources = sorted(p for p in (PACK / "returns").glob("*") if p.suffix in {".txt", ".csv"})
    for p in sources:
        if p.suffix == ".txt":
            got, prob = parse_text(p.read_text(encoding="utf-8"), families)
            problems += [f"{p.name}: {x}" for x in prob]
        else:
            got = parse_csv(p, originals)
        for rid, f in got.items():
            if rid not in originals:
                problems.append(f"{p.name}: unknown row {rid}")
                continue
            merged.setdefault(rid, {}).update(f)
            merged[rid]["source_file"] = p.name
    rows, revisions = {}, []
    for rid, f in sorted(merged.items()):
        status, adjudicate = status_of(f)
        if status == "unreviewed":
            continue
        rows[rid] = {**f, "status": status, "needs_adjudication": adjudicate}
        o = originals[rid]
        for key, form, col in (("corrected_ur", "ur", "urdu_script"), ("corrected_ro", "ro", "roman_urdu"),
                               ("corrected_alt", "ro_alt", "roman_urdu_alt_candidate")):
            if f.get(key):
                revisions.append({"row_id": rid, "family_id": o["family_id"], "safety_label": o["safety_label"], "split": o["split"],
                                  "form": form, "original": o[col], "proposed": f[key], "reason": f.get("comments", ""),
                                  "proposed_by": REVIEWER["name"], "state": "proposed, not yet approved for a dataset version"})
    counts = {s: sum(1 for r in rows.values() if r["status"] == s) for s in STATUSES}
    counts["unreviewed"] = len(originals) - len(rows)
    fam_done = sorted(f for f in families if all(f"{f}-{lab}" in rows for lab in ("harmful", "benign")))
    doc = {"reviewer": REVIEWER, "sources": [p.name for p in sources], "n_rows_total": len(originals), "counts": counts,
           "families_fully_reviewed": fam_done, "problems": problems, "rows": rows}
    (PACK / "review_status.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (PACK / "proposed_revisions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in revisions), encoding="utf-8")
    print(f"review status: {counts} | families fully reviewed: {len(fam_done)} | proposed corrections: {len(revisions)} | "
          f"rows needing adjudication: {sum(r['needs_adjudication'] for r in rows.values())} | lines not understood: {len(problems)}")
    for x in problems[:20]:
        print("  NOT UNDERSTOOD:", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
