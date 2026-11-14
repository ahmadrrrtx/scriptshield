#!/usr/bin/env python3
"""Build a review revision of the corpus from the imported review.

    python3 scripts/build_dataset_revision.py                          # rebuild the current revision
    python3 scripts/build_dataset_revision.py --check                  # write nothing; exit 1 if anything would change
    python3 scripts/build_dataset_revision.py --new 0.3.0-draft.2 --date 2026-11-14
    python3 scripts/build_dataset_revision.py --mark-published all     # or one id

One revision per return. Every answer the reviewer sends (a batch, or corrected sentences that were still
missing) starts a new revision with --new. The revision before it is frozen from then on, published or not, so
an identifier that was once reported keeps meaning the same files. The current revision is rebuilt in place only
while the set of return files is the one it was built from.

Inputs, all tracked, so this runs in a fresh clone: the frozen corpus (checksum verified) and
data/reviewer_pack/review_status.json (written by scripts/import_review.py).

Outputs under data/revisions/:
    index.json                         every revision with the checksums of its files
    README.md                          what a revision is and what each one contains
    ../DATASET_CHANGELOG.md            the dataset changelog (versions and revisions; data/DATASET_CHANGELOG.md)
    ../reviewer_pack/REVIEW_LEDGER.md  the review ledger: every return, every correction, what is still open (no prompt text)
    v<id>/reviewed_records.jsonl       one row per reviewed prompt pair: original, revised, ratings, reviewer, reason
    v<id>/REVISION.json                counts, reviewer, versions, what was and was not evaluated
    v<id>/scriptshield_v<id>.jsonl     the full revised corpus; only written once no correction is pending

What this script never does:
  * touch the evaluated corpus (v0.2.0) or anything computed from it;
  * write a sentence the reviewer did not supply;
  * change a revision that has been published or that a later revision has superseded;
  * fold a new return into an existing revision: it refuses and asks for --new.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.artifacts.public_text import STATUS_WORDS  # noqa: E402
from scriptshield.data import revision as rv  # noqa: E402
from scriptshield.data.schema import load_corpus, validate_corpus  # noqa: E402

OUT = ROOT / "data" / "revisions"
CHANGELOG = ROOT / "data" / "DATASET_CHANGELOG.md"
STATUS = ROOT / "data" / "reviewer_pack" / "review_status.json"
SCHEMA = ROOT / "data" / "schemas" / "review_record.schema.json"
REVISED_SCHEMA = ROOT / "data" / "schemas" / "revised_prompt.schema.json"


def _pack_rows():
    spec = importlib.util.spec_from_file_location("build_review_pack", ROOT / "scripts" / "build_review_pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.pack_rows()[0]


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(revision_id: str, created: str, corpus: list[dict], spec: dict, status: dict, pack_rows: list[dict],
          previous: dict | None = None) -> dict[str, str]:
    """{file name: content} of one revision. ``previous`` is the manifest of the revision before it, if any."""
    rows = rv.review_records(pack_rows, corpus, status, revision_id)
    validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    for r in rows:
        errs = [f"{'.'.join(str(x) for x in e.absolute_path) or '<row>'}: {e.message}" for e in validator.iter_errors(r)]
        if errs:
            raise ValueError(f"{r['pair_id']}: {errs[:3]}")
        for key in (x.strip() for x in (r["correction_pending_fields"] or "").split(",") if x.strip()):
            field = {"ur": "ur_revised", "ro": "ro_revised", "en": "en_revised", "meaning": "intended_meaning_en_revised", "alt": "ro_alt_revised"}[key]
            if r[field] is not None:
                raise AssertionError(f"{r['pair_id']}: text was written for a correction that has not arrived ({key})")
    files = {"reviewed_records.jsonl": rv.dump_jsonl(rows)}
    summary = rv.summarize(rows, status)
    waiting = rv.pending_rows(rows)
    corpus_name = f"scriptshield_v{revision_id}.jsonl"
    if not waiting and summary["sentences_changed"]:
        revised = rv.revised_corpus(corpus, rows, status["reviewer"]["handle"])
        report = validate_corpus(revised, schema=json.loads(REVISED_SCHEMA.read_text(encoding="utf-8")))
        if not report.ok:
            raise ValueError(f"the revised corpus does not validate: {report.errors[:5]}")
        files[corpus_name] = rv.dump_jsonl(revised)
    state = f"draft. Review annotations for {summary['prompt_pairs_reviewed']} prompt pairs."
    if summary["sentences_changed"]:
        state += (f" {summary['sentences_changed']} sentence(s) of {summary['corrections']['applied']} prompt pair(s) were changed by the reviewer; "
                  "the changed sentences have not been evaluated.")
    if waiting:
        state += (f" {len(waiting)} correction(s) were announced by the reviewer without their text; for those the original sentence stands"
                  + ("." if summary["sentences_changed"] else " and no sentence has been changed."))
    if not summary["sentences_changed"] and not waiting:
        state += " No sentence has been changed."
    # what this revision adds to the one before it
    before = previous or {"review": {"batches": {}, "source_files": []}, "summary": {"prompt_pairs_reviewed": 0, "sentences_changed": 0,
                                                                                     "corrections": {"applied": 0}}}
    new_batches = sorted(set(status.get("batches", {})) - set(before["review"]["batches"]))
    new_rows = [r for r in rows if r["review_batch"] in new_batches]
    adds = {
        "previous_revision": previous["revision_id"] if previous else None,
        "review_batches": new_batches,
        "return_files": [x for x in status["sources"] if x not in before["review"]["source_files"]],
        "prompt_pairs_reviewed": len(new_rows),
        "families": sorted({r["family_id"] for r in new_rows}),
        "review_status": {k: sum(1 for r in new_rows if r["review_status"] == k) for k in sorted({r["review_status"] for r in new_rows})},
        "prompt_pairs_with_a_correction_applied": summary["corrections"]["applied"] - before["summary"]["corrections"]["applied"],
        "sentences_changed": summary["sentences_changed"] - before["summary"]["sentences_changed"],
        "pairings_judged_not_comparable": sorted({r["family_id"] for r in new_rows if r["pair_comparable"] == "no"}),
    }
    manifest = {
        "revision_id": revision_id, "created": created, "status": state,
        "previous_dataset_version": spec["dataset_version"], "previous_dataset_sha256": spec["sha256"],
        "previous_dataset_file": spec["corpus"],
        "what_this_is": ("A record of the author's review next to the frozen corpus. It is not a validated dataset: "
                         f"{summary['prompt_pairs_reviewed']} of {summary['prompt_pairs_total']} prompt pairs "
                         f"({summary['families_reviewed']} of {summary['families_total']} families) have been reviewed, by one person."),
        "review": {"reviewer": status["reviewer"], "batches": status.get("batches", {}), "source_files": status["sources"]},
        "adds_to_previous_revision": adds,
        "summary": summary,
        "corrections_waiting_for_text": [x for x in status.get("corrections", {}).get("text_pending", [])],
        "evaluation": {
            "evaluated": False,
            "results_belong_to_dataset_version": spec["dataset_version"],
            "note": ("Every result of this project was computed on the frozen corpus v0.2.0, with the original sentences. No model has been "
                     "run on a revised sentence. A revised sentence must not be paired with a logged reply or a reported number."),
            "families_to_leave_out_of_harmful_against_harmless_comparisons": summary["excluded_from_matched_pair_analysis"],
        },
        "revised_corpus": ({"file": corpus_name, "sha256": sha(files[corpus_name]), "records": len(corpus)} if corpus_name in files else
                           {"file": None, "reason": ("corrections are waiting for their text: a file called a revised corpus must not carry "
                                                     "sentences the reviewer wanted changed. The changed sentences are in reviewed_records.jsonl"
                                                     if waiting else "no sentence changed")}),
        "files": {name: {"sha256": sha(text), "rows": text.count("\n")} for name, text in sorted(files.items())},
        "generated_by": "scripts/build_dataset_revision.py",
    }
    files["REVISION.json"] = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    return files


def readme(index: dict, manifests: dict[str, dict]) -> str:
    L = ["# Review revisions of the ScriptShield corpus", "",
         "<!-- GENERATED by scripts/build_dataset_revision.py. Do not edit by hand. -->", "",
         f"The corpus that was evaluated is **v{index['evaluated_version']}** (sha256 `{index['evaluated_corpus_sha256']}`). It is frozen: no",
         "file of it is ever edited, and every reported number belongs to it.", "",
         "A **review revision** records what the reviewer said about prompt pairs of that corpus. Each revision is a",
         "folder here. It keeps, for every reviewed prompt pair, the original sample ids, the original sentences, the",
         "revised sentences, the original and the revised English meaning, the unchanged safety label, every rating,",
         "the reviewer, the review date, the reason and both version numbers.", "",
         "**Rules.**", "",
         "- The reviewer is one person: the project author, a native Urdu / Roman Urdu speaker. It is a participant",
         "  review. A revision is not an independent expert panel, not a professional translation certification and not",
         "  a consensus of several reviewers, and it covers only the prompt pairs listed in it.",
         "- A sentence the reviewer did not supply is never written. A correction that was announced without its text",
         "  is listed as waiting, and the original sentence stays.",
         "- No revised sentence has been run through a model. Revised sentences are exploratory until a new evaluation",
         "  is done, and they must not be paired with the logged replies or the reported numbers of v0.2.0.",
         "- A family whose harmful and harmless request the reviewer judged not comparable is left out of every",
         "  comparison between harmful and harmless requests on revised data.",
         "- Every answer the reviewer sends gets a new revision. A revision is not changed once a later one exists or",
         "  once it has been published.", "",
         "| Revision | Date | Review batches | Prompt pairs reviewed | Sentences changed | Corrections waiting for text | Left out of harmful/harmless comparisons | Published |",
         "|---|---|---|---:|---:|---:|---|---|"]
    for entry in index["revisions"]:
        m = manifests[entry["id"]]
        s = m["summary"]
        L.append(f"| [`v{entry['id']}`](v{entry['id']}/REVISION.json) | {entry['created']} | {', '.join(sorted(m['review']['batches'])) or 'none'} | "
                 f"{s['prompt_pairs_reviewed']} of {s['prompt_pairs_total']} | {s['sentences_changed']} | {s['corrections']['text_not_received']} | "
                 f"{', '.join('`' + f + '`' for f in s['excluded_from_matched_pair_analysis']) or 'none'} | {'yes' if entry['published'] else 'not yet'} |")
    L += ["", f"Current revision: `v{index['current']}`. Each revision holds the whole review up to its date, so the current one is",
          "the one to read. An earlier revision is kept unchanged as the record of the review at that point: every answer",
          "the reviewer sends starts a new revision, and the one before it is frozen from then on.", "",
          "Files of a revision: `reviewed_records.jsonl` (one row per reviewed prompt pair; its fields are described in",
          "[`review_record.schema.json`](../schemas/review_record.schema.json)), `REVISION.json` (counts, reviewer,",
          "versions) and, once no correction is waiting for its text, the full revised corpus.", "",
          "In a revised corpus, `validation_status` says what the review means for each record: `approved` (reviewed,",
          "unchanged), `corrected` (the text is the reviewer's), `unreviewed`, or `rejected`. The review covers the",
          "Urdu-script and the Roman-Urdu sentence. A code-mixed or English record is therefore `unreviewed` unless the",
          "reviewer supplied its text; and where he replaced a request, its old code-mixed record is kept with its old",
          "text, marked `rejected`, because no code-mixed sentence exists for the new request. Every record also says",
          "whether its text is the one that was evaluated (`text_unchanged_since_v0_2_0`).", "",
          "Rebuild and check: `python3 scripts/build_dataset_revision.py --check`.", ""]
    return "\n".join(L)


def ledger(index: dict, manifests: dict[str, dict], status: dict, rows: list[dict], pack_rows: list[dict]) -> str:
    """The review ledger: returns, corrections and open items. Ids and counts only, never a sentence."""
    cur = manifests[index["current"]]
    s, rv_who = cur["summary"], status["reviewer"]
    by_batch: dict = {}
    for r in pack_rows:
        b = by_batch.setdefault(f"{int(r['batch']):02d}", {"split": r["split"], "families": []})
        if r["family_id"] not in b["families"]:
            b["families"].append(r["family_id"])
    done = set(status.get("batches", {}))
    split_total = {sp: sum(len(b["families"]) for b in by_batch.values() if b["split"] == sp) for sp in ("test", "dev", "calibration")}
    first_in = {b: next(e["id"] for e in index["revisions"] if b in manifests[e["id"]]["review"]["batches"]) for b in done}
    L = ["# Review ledger", "",
         "<!-- GENERATED by scripts/build_dataset_revision.py. Do not edit by hand. -->", "",
         "What has been reviewed, by whom, when, and in which review revision it is recorded. This file holds ids and counts",
         "only. The sentences, original and revised, are in the review revisions (`revisions/`); the ratings of every prompt",
         "pair are also in section 9 of the dataset quality audit.", "",
         f"**Reviewer.** {rv_who['name']} (@{rv_who['handle']}), the project author. {rv_who['review_type'][0].upper() + rv_who['review_type'][1:]}: one",
         "reviewer, who took part in the project. Not an independent expert panel, not a professional translation",
         "certification, not a consensus of several reviewers.", "",
         f"**Status.** {s['prompt_pairs_reviewed']} of {s['prompt_pairs_total']} prompt pairs reviewed, in {s['families_reviewed']} of {s['families_total']} families: "
         + ", ".join(f"{sp} {s['reviewed_families_by_split'][sp]} of {split_total[sp]}" for sp in ("test", "dev", "calibration")) + ". "
         f"Current review revision: `v{index['current']}`. The evaluated data (v{index['evaluated_version']}) is unchanged, and no revised sentence has "
         "been run through a model.", "",
         "## Returns", "",
         "| Batch | Received | Families | Prompt pairs | Accepted as they are | Corrected | Correction waiting for its text | Other | Pairing not comparable | First recorded in | Return files |",
         "|---|---|---|---:|---:|---:|---:|---:|---|---|---|"]
    for b in sorted(done):
        info = status["batches"][b]
        mine = [r for r in rows if r["review_batch"] == b]
        n = lambda k: sum(1 for r in mine if r["review_status"] == k)  # noqa: E731
        no = sorted({r["family_id"] for r in mine if r["pair_comparable"] == "no"})
        L.append(f"| {b} | {info.get('received') or ''} | {', '.join('`' + f + '`' for f in info['families'])} | {len(mine)} | {n('accepted')} | {n('corrected')} | "
                 f"{n('correction_pending')} | {len(mine) - n('accepted') - n('corrected') - n('correction_pending')} | "
                 f"{', '.join('`' + f + '`' for f in no) or 'none'} | `v{first_in[b]}` | {', '.join('`' + x + '`' for x in info['source_files'])} |")
    L += ["", "\"Other\" counts prompt pairs that were rejected, left uncertain or not judged.", "",
          "## Corrections", ""]
    corr = [r for r in rows if r["correction_kind"]]
    if corr:
        L += ["| Prompt pair | Batch | Kind | What changes | State | Text written by | Date |", "|---|---|---|---|---|---|---|"]
        for r in corr:
            st = status["rows"][r["pair_id"]]
            if r["correction_pending_fields"]:
                what = rv._join([x.strip() for x in r["correction_pending_fields"].split(",")])
                who, date = "(waiting)", ""
            else:
                fields = [k for k, col in (("ur", "ur_changed"), ("ro", "ro_changed"), ("en", "en_changed"), ("meaning", "intended_meaning_en_changed")) if r[col]]
                fields += ["alt"] if st.get("corrected_alt") else []
                what = rv._join(fields) if fields else "nothing"
                drafted = st.get("maintainer_fields", [])
                who = "the reviewer" + (f"; {rv._join(drafted)} by the maintainer" if drafted else "")
                date = r["correction_date"] or ""
            L.append(f"| `{r['family_id']}` {'H' if r['safety_label'] == 'harmful' else 'B'} | {r['review_batch']} | {r['correction_kind']} | {what} | "
                     f"{r['correction_state']} | {who} | {date} |")
        L += ["", "A \"wording\" correction keeps the request and its intended meaning. A \"replacement\" puts another request in its place.",
              "Urdu-script and Roman-Urdu sentences are stored exactly as the reviewer wrote them."]
    else:
        L += ["No correction so far."]
    waiting = [r for r in corr if r["correction_pending_fields"]]
    left = s["excluded_from_matched_pair_analysis"]
    open_batches = [b for b in sorted(by_batch) if b not in done]
    L += ["", "## Open", "",
          "- **Corrections waiting for their text:** " + (", ".join(f"`{r['family_id']}` {'H' if r['safety_label'] == 'harmful' else 'B'}" for r in waiting)
                                                         + ". The original sentences stand until the text arrives; nothing is written in its place. "
                                                         "While one waits, no full revised corpus file is written." if waiting else "none."),
          "- **Families left out of comparisons between harmful and harmless requests** (pairing judged not comparable): "
          + (", ".join('`' + f + '`' for f in left) + ". They stay out, also after a replacement, until the replacement has been reviewed as a pair."
             if left else "none."),
          "- **Not yet reviewed:** " + ("; ".join(
              f"{sp} families: batch{'es' if len(bs) > 1 else ''} {', '.join(bs)} ({sum(len(by_batch[b]['families']) for b in bs)} families)"
              for sp in ("test", "dev", "calibration") for bs in [[b for b in open_batches if by_batch[b]["split"] == sp]] if bs) + "."
                                        if open_batches else "nothing."),
          "- **Evaluation of revised sentences:** none. Every reported number belongs to v" + index["evaluated_version"] + " and its original sentences.", "",
          "## Revisions", "",
          "| Revision | Date | Holds | Published |", "|---|---|---|---|"]
    for e in index["revisions"]:
        m = manifests[e["id"]]
        L.append(f"| `v{e['id']}` | {e['created']} | review batch{'es' if len(m['review']['batches']) > 1 else ''} {', '.join(sorted(m['review']['batches']))}: "
                 f"{m['summary']['prompt_pairs_reviewed']} prompt pairs, {m['summary']['sentences_changed']} sentences changed, "
                 f"{m['summary']['corrections']['text_not_received']} corrections waiting | {'yes' if e['published'] else 'not yet'} |")
    L += ["", "Every return starts a new revision; the one before it is kept unchanged.", ""]
    return "\n".join(L)


def changelog(index: dict, manifests: dict[str, dict]) -> str:
    """The dataset changelog. Versions of the evaluated data are fixed text; revisions come from their manifests."""
    L = ["# Dataset changelog", "",
         "<!-- GENERATED by scripts/build_dataset_revision.py. Do not edit by hand. -->", "",
         f"**Evaluated version: {index['evaluated_version']}.** Every reported number, every logged reply and the steering vectors belong to it. Its",
         "files are frozen and listed with their checksums in `data/manifests/frozen_public_release_v0.2.0.json` (code",
         "repository). Review revisions are separate files; none of them has been evaluated.", ""]
    for entry in reversed(index["revisions"]):
        m = manifests[entry["id"]]
        s = m["summary"]
        c = s["corrections"]
        batches = ", ".join(sorted(m["review"]["batches"])) or "none"
        adds = m.get("adds_to_previous_revision")
        later = [e["id"] for e in index["revisions"][index["revisions"].index(entry) + 1:]]
        L += [f"## Review revision {entry['id']} ({entry['created']}): not evaluated", ""]
        if adds and adds["previous_revision"]:
            L += [f"- **New since {adds['previous_revision']}.** "
                  + (f"Review batch {', '.join(adds['review_batches'])}: {adds['prompt_pairs_reviewed']} prompt pairs in {len(adds['families'])} families ("
                     + ", ".join(f"{n} {STATUS_WORDS[k]}" for k, n in adds["review_status"].items()) + "). " if adds["review_batches"] else
                     "No new batch; text or verdicts for prompt pairs reviewed earlier. ")
                  + f"Corrections applied: {adds['prompt_pairs_with_a_correction_applied']} prompt pairs, {adds['sentences_changed']} sentences."
                  + (" Pairing judged not comparable: " + ", ".join('`' + f + '`' for f in adds["pairings_judged_not_comparable"]) + "."
                     if adds["pairings_judged_not_comparable"] else "")]
        L += [
              f"- **What it is.** The author's review of {s['prompt_pairs_reviewed']} of {s['prompt_pairs_total']} prompt pairs "
              f"({s['families_reviewed']} of {s['families_total']} families; review batch{'es' if len(m['review']['batches']) > 1 else ''} {batches}), "
              "recorded next to the frozen corpus. One participant",
              "  reviewer, a native Urdu / Roman Urdu speaker; not an independent expert panel, not a professional translation",
              "  certification, not a consensus of several reviewers. The other prompt pairs are unreviewed.",
              "- **Verdicts.** " + ", ".join(f"{n} {STATUS_WORDS[k]}" for k, n in s["review_status"].items()) + ". "
              f"Same meaning in both scripts: {s['same_meaning_yes']} of {s['prompt_pairs_reviewed']}. Label right: {s['label_plausible_yes']} of "
              f"{s['prompt_pairs_reviewed']}. Naturalness (1 to 5): Urdu script {s['naturalness']['urdu_script']['mean']}, Roman Urdu "
              f"{s['naturalness']['roman_urdu']['mean']}. Second spelling natural: {s['alt_spelling_yes']} of {s['alt_spelling_judged']}.",
              f"- **Sentences changed: {s['sentences_changed']}.** Corrections announced for {c['prompt_pairs_with_a_correction']} prompt pairs"
              + (f" (of which {len(c['replacements'])} replace{'s' if len(c['replacements']) == 1 else ''} a request: "
                 + ", ".join('`' + x + '`' for x in c['replacements']) + ")" if c["replacements"] else "")
              + f"; applied {c['applied']}, waiting for their text {c['text_not_received']}, not applied {c['not_applied'] + c['not_approved']}."
              + (" A correction without its text changes nothing: the original sentence stays and no text was written for it." if c["text_not_received"] else "")
              + (" Every Urdu and Roman-Urdu sentence that changed is the reviewer's own, character for character."
                 if c["applied"] else "")
              + (" Written by the maintainer to go with a request the reviewer replaced, and marked so: "
                 + "; ".join(f"`{pair}`: {' and '.join(fields)}" for pair, fields in c["fields_written_by_maintainer"].items()) + "."
                 if c.get("fields_written_by_maintainer") else ""),
              "- **Harmful/harmless pairing.** " + (
                  "Judged not comparable by the reviewer: " + ", ".join('`' + f + '`' for f in s["excluded_from_matched_pair_analysis"])
                  + ". Left out of every comparison between harmful and harmless requests on revised data."
                  if s["excluded_from_matched_pair_analysis"] else "No family judged not comparable."),
              "- **Labels and ids.** No safety label and no sample id changed.",
              "- **Evaluation.** None. The results stay with v" + index["evaluated_version"] + " and its original sentences.",
              f"- **Files.** `revisions/v{entry['id']}/reviewed_records.jsonl` (sha256 `{m['files']['reviewed_records.jsonl']['sha256']}`), "
              f"`revisions/v{entry['id']}/REVISION.json`"
              + (f", `revisions/v{entry['id']}/{m['revised_corpus']['file']}` (sha256 `{m['revised_corpus']['sha256']}`)" if m["revised_corpus"]["file"] else
                 f". No revised corpus file: {m['revised_corpus']['reason']}") + ".",
              f"- **Published.** {'Yes' if entry['published'] else 'Not yet'}."
              + (f" Superseded by {later[-1]}; kept unchanged as the record of the review at that point." if later else ""), ""]
    L += ["## 0.2.0, documentation added (2026-11-13): no data file changed", "",
          "- Dataset card rewritten; figures, family-level quality audit, robustness checks and the review pack added.",
          "- The corpus, the splits and the evaluation logs are byte-identical to the first release.", "",
          "## 0.2.0 (2026-11-13): first public release, the evaluated version", "",
          f"- 72 intent families, 576 prompts (harmful and harmless, four written forms), split by family 24 / 12 / 36. Corpus sha256 `{index['evaluated_corpus_sha256']}`.",
          "- Evaluation logs of the frozen test run with the withholding rule of the dataset card.",
          "- Every record `unreviewed`: no human had reviewed the prompts when the experiments were run.", "",
          "## 0.1.1-pilot (2026-11-03): not published", "",
          "- 24 pilot families, used for pipeline tests only.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--new", metavar="ID", help="start a new revision, e.g. 0.3.0-draft.2")
    ap.add_argument("--date", help="creation date of the new revision, YYYY-MM-DD (required with --new)")
    ap.add_argument("--mark-published", metavar="ID", help="record that a revision has been uploaded: an id, or 'all'")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the committed files would change")
    a = ap.parse_args()

    corpus, spec = load_corpus(ROOT)                      # raises if the frozen corpus does not match its checksum
    spec = {**spec, "corpus": str(Path(spec["path"]).relative_to(ROOT))}
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    index_path = OUT / "index.json"
    index = (json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else
             {"evaluated_version": spec["dataset_version"], "evaluated_corpus_sha256": spec["sha256"], "current": None, "revisions": []})
    if index["evaluated_corpus_sha256"] != spec["sha256"]:
        print("REFUSING: the index was written for a different corpus")
        return 2
    if a.new:
        if a.check or not a.date or any(e["id"] == a.new for e in index["revisions"]):
            print("REFUSING: --new needs --date and an id that does not exist yet, and cannot be combined with --check")
            return 2
        # the revision before it is frozen from here on, published or not (its files are checked below)
        index["revisions"].append({"id": a.new, "created": a.date, "published": False, "files": {}})
        index["current"] = a.new
    if a.mark_published:
        hit = [e for e in index["revisions"] if a.mark_published in ("all", e["id"])]
        if not hit or a.check:
            print("REFUSING: unknown revision, or --check given")
            return 2
        for e in hit:
            e["published"] = True
    if not index["revisions"]:
        print("no revision yet: start one with --new <id> --date <YYYY-MM-DD>")
        return 0 if not a.check else 1

    pack_rows = _pack_rows()
    targets: dict[Path, str] = {}
    manifests: dict[str, dict] = {}
    previous: dict | None = None                          # manifest of the revision before the one being handled
    for entry in index["revisions"]:
        folder = OUT / f"v{entry['id']}"
        on_disk = {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*")) if p.is_file()} if folder.exists() else {}
        if entry["id"] != index["current"] or entry["published"]:
            # frozen: the files must still be the ones whose checksums were recorded
            got = {name: sha(text) for name, text in on_disk.items()}
            if got != entry["files"]:
                print(f"REFUSING: revision {entry['id']} is frozen and its files differ from the recorded checksums")
                return 3
            if entry["id"] == index["current"]:
                fresh = build(entry["id"], entry["created"], corpus, spec, status, pack_rows, previous)
                if {n: sha(t) for n, t in fresh.items()} != entry["files"]:
                    print(f"REFUSING: the review has changed since revision {entry['id']} was published. "
                          "Start a new revision: --new <id> --date <YYYY-MM-DD>")
                    return 3
            manifests[entry["id"]] = previous = json.loads(on_disk["REVISION.json"])
            continue
        if "REVISION.json" in on_disk:
            built_from = json.loads(on_disk["REVISION.json"])["review"]["source_files"]
            if built_from != status["sources"]:
                print(f"REFUSING: revision {entry['id']} was built from the returns {built_from}; the review now has {status['sources']}. "
                      "A new return starts a new revision: --new <id> --date <YYYY-MM-DD>")
                return 3
        files = build(entry["id"], entry["created"], corpus, spec, status, pack_rows, previous)
        entry["files"] = {name: sha(text) for name, text in sorted(files.items())}
        manifests[entry["id"]] = json.loads(files["REVISION.json"])
        for name, text in files.items():
            targets[folder / name] = text
        for stale in set(on_disk) - set(files):            # e.g. a revised corpus from before a correction was withdrawn
            targets[folder / stale] = ""
    targets[index_path] = json.dumps(index, indent=1, ensure_ascii=False) + "\n"
    targets[OUT / "README.md"] = readme(index, manifests)
    targets[CHANGELOG] = changelog(index, manifests)
    current_folder = OUT / f"v{index['current']}"
    current_rows = targets.get(current_folder / "reviewed_records.jsonl") or (current_folder / "reviewed_records.jsonl").read_text(encoding="utf-8")
    targets[STATUS.parent / "REVIEW_LEDGER.md"] = ledger(index, manifests, status, [json.loads(x) for x in current_rows.splitlines() if x.strip()], pack_rows)

    changed = [p for p, text in targets.items() if (p.read_text(encoding="utf-8") if p.exists() else "") != text]
    if a.check:
        print("stale: " + ", ".join(p.name if ROOT not in p.parents else str(p.relative_to(ROOT)) for p in changed)
              if changed else "revision files are up to date")
        return 1 if changed else 0
    for p, text in targets.items():
        if text == "" and p.exists() and p.name not in ("index.json", "README.md", "DATASET_CHANGELOG.md", "REVIEW_LEDGER.md"):
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    cur = manifests[index["current"]]["summary"]
    print(f"revision v{index['current']}: {cur['prompt_pairs_reviewed']} prompt pairs reviewed in {cur['families_reviewed']} families | "
          f"sentences changed {cur['sentences_changed']} | corrections waiting for text {cur['corrections']['text_not_received']} | "
          f"left out of harmful/harmless comparisons {cur['excluded_from_matched_pair_analysis']} | files rewritten {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
