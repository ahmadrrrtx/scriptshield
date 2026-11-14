"""Review revisions: the evaluated corpus stays frozen, a revision can be traced to it, and nothing is invented.

Three kinds of test:
* the frozen data (checksums that must never change);
* the committed revision (it is what the builder produces, it validates, every row traces back to the corpus);
* the rules, on made-up answers (a correction without text writes nothing, an unapproved correction is not applied,
  a replacement is not a wording fix, a published revision cannot be changed).
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from scriptshield.data import revision as rv
from scriptshield.data.schema import load_corpus, validate_corpus

ROOT = Path(__file__).resolve().parents[1]
REV = ROOT / "data" / "revisions"
INDEX = json.loads((REV / "index.json").read_text(encoding="utf-8"))
STATUS = json.loads((ROOT / "data/reviewer_pack/review_status.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "data/schemas/review_record.schema.json").read_text(encoding="utf-8"))
REVISED_SCHEMA = json.loads((ROOT / "data/schemas/revised_prompt.schema.json").read_text(encoding="utf-8"))
CORPUS, SPEC = load_corpus(ROOT)
BY_ID = {r["id"]: r for r in CORPUS}
# The corpus every reported number was computed on. Typed here on purpose: changing the corpus and every file that
# quotes its checksum together must still fail a test.
EVALUATED_SHA256 = "fd7a5b7b4aa6eb03a889fbbe68117af63ac8652e667aa48ac5c245d4a3df8763"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


builder = _load("build_dataset_revision")
PACK_ROWS = {r["row_id"]: r for r in builder._pack_rows()}


def _rows(revision_id=None):
    rid = revision_id or INDEX["current"]
    return [json.loads(x) for x in (REV / f"v{rid}" / "reviewed_records.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


# ------------------------------------------------------------------ the evaluated data is frozen
def test_evaluated_corpus_has_the_checksum_every_result_was_computed_on():
    assert hashlib.sha256(Path(SPEC["path"]).read_bytes()).hexdigest() == EVALUATED_SHA256
    assert SPEC["sha256"] == EVALUATED_SHA256 and SPEC["dataset_version"] == "0.2.0"
    assert INDEX["evaluated_corpus_sha256"] == EVALUATED_SHA256 and INDEX["evaluated_version"] == "0.2.0"
    assert json.loads((ROOT / "data/manifests/scriptshield_0.2.0.json").read_text(encoding="utf-8"))["sha256"] == EVALUATED_SHA256


def test_every_record_of_the_evaluated_corpus_is_still_unreviewed_in_place():
    """Review results never go into the frozen file: its records keep the status they had when the experiments ran."""
    assert {r["validation_status"] for r in CORPUS} == {"unreviewed"}
    assert not any(r.get("reviewer_id") for r in CORPUS)


def test_frozen_release_manifest_lists_the_data_files_of_the_first_public_release():
    frozen = json.loads((ROOT / "data/manifests/frozen_public_release_v0.2.0.json").read_text(encoding="utf-8"))["files"]
    base = json.loads((ROOT / "docs/baselines/BASELINE_2026-11-13.json").read_text(encoding="utf-8"))["dataset"]["files"]
    want = {n: (v if isinstance(v, str) else v["sha256"]) for n, v in base.items() if n not in ("README.md", "SHA256SUMS", ".gitattributes")}
    assert frozen == want and len(frozen) == 29
    assert frozen["data/scriptshield_v0.2.0.jsonl"] == EVALUATED_SHA256
    assert sum(n.startswith(("data/", "eval_logs/")) for n in frozen) == 25


def test_packaged_dataset_keeps_every_frozen_file_when_a_release_is_built():
    folder = ROOT / "release" / "hf_dataset"
    if not (folder / "data").is_dir():
        pytest.skip("no local release folder")
    frozen = json.loads((ROOT / "data/manifests/frozen_public_release_v0.2.0.json").read_text(encoding="utf-8"))["files"]
    changed = [n for n, want in frozen.items() if not (folder / n).is_file() or hashlib.sha256((folder / n).read_bytes()).hexdigest() != want]
    assert changed == []


def test_results_carry_the_evaluated_version_and_no_revision():
    """The logged test run names the corpus it used, by version and checksum; no result file names a revision."""
    report = json.loads((ROOT / "experiments/results/fire_test_v2/fire_test/run_report.json").read_text(encoding="utf-8"))
    used = report["sections"]["setup"]["corpus"]
    assert (used["dataset_version"], used["sha256"]) == ("0.2.0", EVALUATED_SHA256)
    for f in sorted((ROOT / "experiments/results/test_analysis").glob("*.json")) + [ROOT / "experiments/results/fire_test_v2/fire_test/run_report.json"]:
        assert "0.3.0" not in f.read_text(encoding="utf-8"), f"{f.name} mentions a revision"
    frozen = json.loads((ROOT / "data/manifests/frozen_public_release_v0.2.0.json").read_text(encoding="utf-8"))["files"]
    for name in ("eval_logs/test_run_report.json", "eval_logs/test_judged_public.jsonl", "eval_logs/test_analysis_guard.json"):
        assert name in frozen, f"{name} must be among the frozen files"


# ------------------------------------------------------------------ the committed revision
def test_committed_revision_is_what_the_builder_produces():
    out = subprocess.run([sys.executable, str(ROOT / "scripts/build_dataset_revision.py"), "--check"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout[-400:] + out.stderr[-400:]


def test_recorded_checksums_match_the_files_of_every_revision():
    for entry in INDEX["revisions"]:
        folder = REV / f"v{entry['id']}"
        got = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*")) if p.is_file()}
        assert got == entry["files"], entry["id"]
        manifest = json.loads((folder / "REVISION.json").read_text(encoding="utf-8"))
        for name, meta in manifest["files"].items():
            assert got[name] == meta["sha256"]
        assert manifest["evaluation"]["evaluated"] is False and manifest["evaluation"]["results_belong_to_dataset_version"] == "0.2.0"
        assert manifest["previous_dataset_sha256"] == EVALUATED_SHA256
        assert "not a validated dataset" in manifest["what_this_is"]


def test_rows_validate_and_trace_back_to_the_frozen_records():
    validator = jsonschema.Draft202012Validator(SCHEMA)
    rows = _rows()
    assert len(rows) == len(STATUS["rows"]) > 0, "one row per reviewed prompt pair, and no row for an unreviewed one"
    for r in rows:
        assert not list(validator.iter_errors(r)), r["pair_id"]
        for form in ("ur", "ro", "en", "cm"):
            rec = BY_ID[r[f"id_{form}"]]
            assert rec["family_id"] == r["family_id"] and rec["safety_label"] == r["safety_label"], "ids and labels come from the corpus"
            assert rec["text"] == r[f"{form}_original"], f"{r['pair_id']}: the original {form} sentence is not the corpus text"
        assert BY_ID[r["id_ur"]]["intended_meaning_en"] == r["intended_meaning_en_original"]
        assert r["previous_dataset_version"] == "0.2.0" and r["updated_dataset_version"] == INDEX["current"]
        assert r["revised_text_used_in_any_result"] is False
        assert r["reviewer_name"] == "Muhammad Ahmad" and r["review_date"] and r["review_batch"]
        st = STATUS["rows"][r["pair_id"]]
        assert (r["ur_naturalness"], r["ro_naturalness"]) == tuple(v if isinstance(v, int) else None for v in (st.get("ur"), st.get("ro")))
        assert (r["same_meaning"], r["label_plausible"], r["alt_spelling_ok"]) == (st.get("same"), st.get("label"), st.get("alt"))


def test_no_text_is_written_for_a_correction_that_has_not_arrived():
    field = {"ur": "ur_revised", "ro": "ro_revised", "en": "en_revised", "meaning": "intended_meaning_en_revised", "alt": "ro_alt_revised"}
    waiting = 0
    for r in _rows():
        pending = [x.strip() for x in (r["correction_pending_fields"] or "").split(",") if x.strip()]
        for key in pending:
            assert r[field[key]] is None, f"{r['pair_id']}: text was written for a correction without text ({key})"
        if pending:
            waiting += 1
            assert r["review_status"] == "correction_pending" and r["correction_state"] == "text not received"
            assert r["revised_text_differs_from_original"] is None
            if "ro" in pending:
                assert r["ro_alt_revised"] is None, "a second spelling of a sentence that is being corrected is not carried over"
        else:
            for form in ("ur", "ro", "en"):                       # unchanged unless a correction with text was applied
                assert r[f"{form}_changed"] is not None
                assert (r[f"{form}_revised"] == r[f"{form}_original"]) == (not r[f"{form}_changed"])
    manifest = json.loads((REV / f"v{INDEX['current']}" / "REVISION.json").read_text(encoding="utf-8"))
    assert manifest["summary"]["corrections"]["text_not_received"] == waiting == len(STATUS["corrections"]["text_pending"])
    if waiting:
        assert manifest["revised_corpus"]["file"] is None, "no revised corpus while a correction waits for its text"
        assert not list((REV / f"v{INDEX['current']}").glob("scriptshield_v*.jsonl"))


def test_family_with_rejected_pairing_is_marked_on_both_rows_and_in_the_manifest():
    left = STATUS["excluded_from_matched_pair_analysis"]
    manifest = json.loads((REV / f"v{INDEX['current']}" / "REVISION.json").read_text(encoding="utf-8"))
    assert manifest["evaluation"]["families_to_leave_out_of_harmful_against_harmless_comparisons"] == left
    for r in _rows():
        assert r["matched_pair_analysis"].startswith("excluded") == (r["family_id"] in left)
        assert (r["pair_comparable"] == "no") == (r["family_id"] in left)


def test_documents_do_not_claim_more_review_than_happened():
    """Counts in the generated documents equal the status file; nothing calls the dataset validated."""
    n, total = len(STATUS["rows"]), STATUS["n_rows_total"]
    assert n < total, "this test describes a partial review"
    for rel in ("data/DATASET_CHANGELOG.md", "data/revisions/README.md", "docs/DATASET_QUALITY_AUDIT.md"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert f"{n} of {total}" in text, rel
        low = text.lower()
        for claim in ("human-validated dataset", "fully reviewed", "expert-validated", "validated by experts", "certified translation"):
            assert claim not in low, f"{rel}: {claim}"
    changelog = (ROOT / "data/DATASET_CHANGELOG.md").read_text(encoding="utf-8")
    assert "not evaluated" in changelog and EVALUATED_SHA256 in changelog
    assert "not an independent expert panel" in changelog and "not a professional translation" in changelog


# ------------------------------------------------------------------ the rules, on made-up answers
REVIEWER = {"name": "Reviewer", "handle": "rev", "role": "participant", "review_type": "participant-provided review"}
IDS = {"ur": "ss-x-ur-harmful", "ro": "ss-x-ro-harmful", "en": "ss-x-en-harmful", "cm": "ss-x-cm-harmful"}


def _pack_row(label="harmful"):
    return {"row_id": f"x-{label}", "family_id": "x", "safety_label": label, "split": "test", "topic_group": "fraud",
            "urdu_script": "میں یہ کام کیسے کروں؟", "roman_urdu": "Main yeh kaam kaise karoon?", "english_reference": "How do I do this?",
            "intended_meaning_en": "Ask how to do the thing.", "roman_urdu_alt_candidate": "Mein ye kaam kese karun?"}


def _record(status, label="harmful", pair="yes"):
    base = {"status": "accepted", "ur": 5, "ro": 5, "same": "yes", "label": "yes", "review_date": "2026-11-13", "review_batch": "01"}
    return rv.review_record(_pack_row(label), IDS, "میں یہ task کیسے کروں؟", "cat", {**base, **status}, REVIEWER, "0.3.0-draft.9", pair)


def test_accepted_pair_is_copied_unchanged():
    r = _record({})
    assert (r["ur_revised"], r["ro_revised"], r["ro_alt_revised"]) == (r["ur_original"], r["ro_original"], r["ro_alt_candidate"])
    assert not any(r[k] for k in ("ur_changed", "ro_changed", "en_changed", "intended_meaning_en_changed"))
    assert r["correction_kind"] is None and r["revised_text_differs_from_original"] is False


def test_approved_wording_correction_is_applied_and_keeps_the_original():
    new_ur, new_ro = "میں یہ کام کس طرح کروں؟", "Main yeh kaam kis tarah karoon?"
    r = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": True, "correction_date": "2026-11-14",
                 "corrected_ur": new_ur, "corrected_ro": new_ro})
    assert (r["ur_revised"], r["ro_revised"]) == (new_ur, new_ro) and r["ur_changed"] and r["ro_changed"]
    assert r["ur_original"] == _pack_row()["urdu_script"] and r["safety_label"] == "harmful"
    assert r["correction_state"] == "applied" and r["revised_text_differs_from_original"] is True
    assert r["ro_alt_revised"] is None, "the judged second spelling belonged to the original sentence"
    assert r["revised_text_used_in_any_result"] is False


def test_correction_without_the_owners_word_is_not_applied():
    r = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": False, "corrected_ro": "Main yeh kaam kis tarah karoon?"})
    assert r["ro_revised"] == r["ro_original"] and r["ro_changed"] is False
    assert r["correction_state"] == "proposed, not approved by the project owner" and r["revised_text_differs_from_original"] is None


def test_corrected_urdu_with_latin_letters_is_not_applied():
    r = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": True, "corrected_ur": "میں یہ task کیسے کروں؟"})
    assert r["ur_revised"] == r["ur_original"] and r["ur_changed"] is False
    assert "not applied" in r["correction_flags"] and r["correction_state"] == "not applied"


def test_much_longer_harmful_correction_is_flagged_for_a_person():
    long_ro = "Main yeh kaam kaise karoon aur is ke liye mujhe kya kya cheezen chahiye hon gi aur kahan se milein gi?"
    r = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": True, "corrected_ro": long_ro})
    assert "no detail was added" in r["correction_flags"]
    harmless = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": True, "corrected_ro": long_ro}, label="benign")
    assert harmless["correction_flags"] is None, "the length rule is about harmful requests"


def test_replacement_changes_english_and_meaning_and_keeps_the_family_out():
    r = _record({"status": "corrected", "correction_kind": "replacement", "correction_approved": True, "corrected_en": "How do I do that instead?",
                 "corrected_meaning": "Ask how to do the other thing.", "corrected_ur": "میں وہ کام کیسے کروں؟", "corrected_ro": "Main woh kaam kaise karoon?"},
                label="benign", pair="no")
    assert r["en_changed"] and r["intended_meaning_en_changed"] and r["correction_kind"] == "replacement"
    assert r["revision_reason"].startswith("Request replaced by the reviewer")
    assert r["matched_pair_analysis"].startswith("excluded"), "a replacement does not make the pair comparable by itself"
    assert r["safety_label"] == "benign"


def test_announced_correction_leaves_every_pending_field_empty():
    r = _record({"status": "correction_pending", "correction_kind": "wording", "correction_approved": True, "pending_fields": ["ur", "ro"]})
    assert r["ur_revised"] is None and r["ro_revised"] is None and r["ro_alt_revised"] is None
    assert r["en_revised"] == r["en_original"] and r["correction_state"] == "text not received"
    assert "nothing was written in its place" in r["revision_reason"]


def _toy_corpus():
    out = []
    for label in ("harmful", "benign"):
        p = _pack_row(label)
        for form, text in (("ur", p["urdu_script"]), ("ro", p["roman_urdu"]), ("en", p["english_reference"]), ("cm", "میں یہ task کیسے کروں؟")):
            text = text if label == "harmful" else text.replace("کام", "چیز").replace("kaam", "cheez").replace("this", "that").replace("task", "thing")
            out.append({"id": f"ss-x-{form}-{label}", "family_id": "x", "pair_id": f"x-{label}", "form": form, "safety_label": label, "text": text,
                        "intended_meaning_en": p["intended_meaning_en"], "harm_category": "cat", "harm_group": "fraud", "split": "test",
                        "validation_status": "unreviewed", "source": "authored", "created": "2026-11-12",
                        **({"roman_style": "A"} if form == "ro" else {})})
    return out


def test_revised_corpus_refuses_while_a_correction_waits_and_keeps_ids_and_labels_otherwise():
    corpus = _toy_corpus()
    waiting = _record({"status": "correction_pending", "correction_kind": "wording", "correction_approved": True, "pending_fields": ["ro"]})
    with pytest.raises(ValueError, match="announced without text"):
        rv.revised_corpus(corpus, [waiting], "rev")
    new_ro = "Main yeh kaam kis tarah karoon?"
    done = _record({"status": "corrected", "correction_kind": "wording", "correction_approved": True, "corrected_ro": new_ro, "ur": 4})
    out = rv.revised_corpus(corpus, [done], "rev")
    assert [r["id"] for r in out] == [r["id"] for r in corpus] and [r["safety_label"] for r in out] == [r["safety_label"] for r in corpus]
    by = {r["id"]: r for r in out}
    assert by["ss-x-ro-harmful"]["text"] == new_ro and by["ss-x-ro-harmful"]["validation_status"] == "corrected"
    assert by["ss-x-ur-harmful"]["validation_status"] == "approved" and by["ss-x-ur-harmful"]["naturalness"] == 4
    assert "naturalness" not in by["ss-x-ro-harmful"], "a rating of the original sentence does not carry over to a corrected one"
    assert "same_meaning" not in by["ss-x-ur-harmful"], "'same meaning' was judged for the pair as it was, and one half has changed"
    assert "may no longer match" in by["ss-x-cm-harmful"]["notes"]
    assert by["ss-x-ro-harmful"]["text_unchanged_since_v0_2_0"] is False
    assert by["ss-x-ro-harmful"]["text_v0_2_0"] == _pack_row()["roman_urdu"], "the original stays next to the corrected text"
    for form in ("ur", "ro", "en", "cm"):                             # an unreviewed request is copied; only the flag is added
        before = next(r for r in corpus if r["id"] == f"ss-x-{form}-benign")
        assert by[f"ss-x-{form}-benign"] == {**before, "text_unchanged_since_v0_2_0": True}
    report = validate_corpus(out, schema=REVISED_SCHEMA)
    assert report.ok, report.errors[:3]
    assert not validate_corpus(out).ok, "a revised corpus is not a file of the frozen format, and cannot pass for one"
    assert corpus == _toy_corpus(), "the input corpus is never modified"


def test_replaced_request_marks_its_english_as_supplied_and_its_code_mixed_form_as_unusable():
    corpus = _toy_corpus()
    row = _record({"status": "corrected", "correction_kind": "replacement", "correction_approved": True, "corrected_en": "How do I do that instead?",
                   "corrected_meaning": "Ask how to do the other thing.", "corrected_ur": "میں وہ دوسرا کام کیسے کروں؟",
                   "corrected_ro": "Main woh doosra kaam kaise karoon?"}, label="benign", pair="no")
    harmful = _record({}, label="harmful", pair="no")               # the family's other pair: accepted as it is
    by = {r["id"]: r for r in rv.revised_corpus(corpus, [harmful, row], "rev")}
    en, cm, ur = by["ss-x-en-benign"], by["ss-x-cm-benign"], by["ss-x-ur-benign"]
    assert en["text"] == "How do I do that instead?" and en["validation_status"] == "corrected" and en["text_unchanged_since_v0_2_0"] is False
    assert ur["intended_meaning_en"] == "Ask how to do the other thing."
    before = next(r for r in corpus if r["id"] == "ss-x-cm-benign")
    assert cm["text"] == before["text"] and cm["intended_meaning_en"] == before["intended_meaning_en"], "the old code-mixed record is kept as it was"
    assert cm["validation_status"] == "rejected" and "replaced" in cm["notes"]
    assert all(by[f"ss-x-{form}-harmful"]["text"] == next(r for r in corpus if r["id"] == f"ss-x-{form}-harmful")["text"] for form in ("ur", "ro", "en", "cm"))
    assert "left out of harmful-against-harmless comparisons" in by["ss-x-ur-harmful"]["notes"]
    assert validate_corpus(list(by.values()), schema=REVISED_SCHEMA).ok


def test_english_written_by_the_maintainer_is_marked_in_the_record_and_stays_unreviewed_in_the_corpus():
    corpus = _toy_corpus()
    fields = {"status": "corrected", "correction_kind": "replacement", "correction_approved": True, "corrected_en": "How do I do that instead?",
              "corrected_meaning": "Ask how to do the other thing.", "corrected_ur": "میں وہ دوسرا کام کیسے کروں؟",
              "corrected_ro": "Main woh doosra kaam kaise karoon?"}
    own = _record(fields, label="benign", pair="no")
    assert (own["en_revised_written_by"], own["intended_meaning_en_revised_written_by"]) == ("reviewer", "reviewer")
    assert "maintainer" not in own["revision_reason"]
    row = _record({**fields, "maintainer_fields": ["en", "meaning"]}, label="benign", pair="no")
    assert (row["en_revised_written_by"], row["intended_meaning_en_revised_written_by"]) == ("maintainer", "maintainer")
    assert "written by the maintainer" in row["revision_reason"] and "not the reviewer's wording" in row["revision_reason"]
    assert row["ur_revised"] == fields["corrected_ur"] and row["ro_revised"] == fields["corrected_ro"], "his sentences, character for character"
    untouched = _record({})
    assert untouched["en_revised_written_by"] is None and untouched["intended_meaning_en_revised_written_by"] is None
    by = {r["id"]: r for r in rv.revised_corpus(corpus, [_record({}, pair="no"), row], "rev")}
    en, ur = by["ss-x-en-benign"], by["ss-x-ur-benign"]
    assert en["text"] == fields["corrected_en"] and en["validation_status"] == "unreviewed" and not en.get("reviewer_id")
    assert "written by the maintainer" in en["notes"] and "written by the maintainer" in ur["notes"]
    assert ur["validation_status"] == "corrected" and ur["reviewer_id"] == "rev"
    assert validate_corpus(list(by.values()), schema=REVISED_SCHEMA).ok
    status = {"n_rows_total": 2, "families_fully_reviewed": ["x"], "pair_verdicts": {"x": "no"}, "excluded_from_matched_pair_analysis": ["x"]}
    assert rv.summarize([own], status)["corrections"]["english_written_by_maintainer"] == []
    assert rv.summarize([row], status)["corrections"]["english_written_by_maintainer"] == ["x-benign"]


def test_revised_schema_is_the_frozen_schema_with_the_documented_differences():
    base = json.loads((ROOT / "data/schemas/prompt.schema.json").read_text(encoding="utf-8"))
    assert set(REVISED_SCHEMA["properties"]) - set(base["properties"]) == {"same_meaning", "text_unchanged_since_v0_2_0", "text_v0_2_0"}
    for name, spec in base["properties"].items():
        assert REVISED_SCHEMA["properties"][name] == spec, name
    assert REVISED_SCHEMA["required"] == base["required"] + ["text_unchanged_since_v0_2_0"]
    assert REVISED_SCHEMA["allOf"][0] == base["allOf"][0] and REVISED_SCHEMA["additionalProperties"] is False
    # the frozen corpus itself still validates against its own, unchanged schema
    assert validate_corpus(CORPUS).ok


def _status_of_batches(batches: set[str]) -> dict:
    """The committed review status cut back to the given batches, as the importer would have written it then."""
    st = json.loads(json.dumps(STATUS))
    st["rows"] = {k: v for k, v in st["rows"].items() if v["review_batch"] in batches}
    st["batches"] = {k: v for k, v in st["batches"].items() if k in batches}
    st["sources"] = [f for b in sorted(st["batches"]) for f in st["batches"][b]["source_files"]]
    fams = {k.rsplit("-", 1)[0] for k in st["rows"]}
    st["families_fully_reviewed"] = [f for f in st["families_fully_reviewed"] if f in fams]
    st["pair_verdicts"] = {f: v for f, v in st["pair_verdicts"].items() if f in fams}
    st["excluded_from_matched_pair_analysis"] = [f for f in st["excluded_from_matched_pair_analysis"] if f in fams]
    st["corrections"]["text_pending"] = [x for x in st["corrections"]["text_pending"] if x["row_id"] in st["rows"]]
    return st


def test_a_new_return_starts_a_new_revision_and_the_one_before_it_is_frozen(tmp_path, monkeypatch, capsys):
    """One revision per return: the builder will not fold a new batch into an existing revision, published or not."""
    if len(STATUS["batches"]) < 2:
        pytest.skip("needs two imported batches")
    out = tmp_path / "revisions"
    status_path = tmp_path / "review_status.json"
    monkeypatch.setattr(builder, "OUT", out)
    monkeypatch.setattr(builder, "STATUS", status_path)
    monkeypatch.setattr(builder, "CHANGELOG", tmp_path / "DATASET_CHANGELOG.md")

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["build_dataset_revision.py", *args])
        return builder.main()
    status_path.write_text(json.dumps(_status_of_batches({"01"})), encoding="utf-8")
    assert run("--new", "0.3.0-draft.1", "--date", "2026-11-13") == 0
    first = {p.name: p.read_bytes() for p in (out / "v0.3.0-draft.1").iterdir()}
    assert run() == 0, "the same returns: the unpublished revision is rebuilt in place, to the same bytes"
    assert {p.name: p.read_bytes() for p in (out / "v0.3.0-draft.1").iterdir()} == first
    status_path.write_text(json.dumps(_status_of_batches({"01", "02"})), encoding="utf-8")
    assert run() == 3 and "A new return starts a new revision" in capsys.readouterr().out
    assert run("--check") == 3
    assert {p.name: p.read_bytes() for p in (out / "v0.3.0-draft.1").iterdir()} == first, "nothing was folded into the first revision"
    assert run("--new", "0.3.0-draft.2", "--date", "2026-11-13") == 0
    assert {p.name: p.read_bytes() for p in (out / "v0.3.0-draft.1").iterdir()} == first, "frozen although it was never published"
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert index["current"] == "0.3.0-draft.2" and [e["published"] for e in index["revisions"]] == [False, False]
    second = json.loads((out / "v0.3.0-draft.2" / "REVISION.json").read_text(encoding="utf-8"))
    adds = second["adds_to_previous_revision"]
    assert adds["previous_revision"] == "0.3.0-draft.1" and adds["review_batches"] == ["02"]
    assert adds["prompt_pairs_reviewed"] == sum(1 for r in STATUS["rows"].values() if r["review_batch"] == "02")
    assert second["summary"]["prompt_pairs_reviewed"] == len(STATUS["rows"]), "a revision holds the whole review up to its date"
    changelog = (tmp_path / "DATASET_CHANGELOG.md").read_text(encoding="utf-8")
    assert "New since 0.3.0-draft.1" in changelog and "Superseded by 0.3.0-draft.2" in changelog
    (out / "v0.3.0-draft.1" / "reviewed_records.jsonl").write_text("tampered\n", encoding="utf-8")
    assert run() == 3 and "frozen" in capsys.readouterr().out
    assert run("--mark-published", "nonsense") == 2


def test_committed_first_revision_is_still_the_one_that_was_reported():
    """0.3.0-draft.1 was reported to the owner with this checksum before batch 02 arrived. It must not change."""
    first = next(e for e in INDEX["revisions"] if e["id"] == "0.3.0-draft.1")
    assert first["files"]["reviewed_records.jsonl"] == "2af06034774eeecc7e79c72cb2c2930bf69641714b251e02ac13a1b84450c41a"
    rows = _rows("0.3.0-draft.1")
    assert len(rows) == 12 and {r["review_batch"] for r in rows} == {"01"} and {r["updated_dataset_version"] for r in rows} == {"0.3.0-draft.1"}


def test_published_revision_cannot_be_changed(tmp_path, monkeypatch, capsys):
    """After publication the builder refuses to rewrite a revision when the review has moved on."""
    out = tmp_path / "revisions"
    status_path = tmp_path / "review_status.json"
    status_path.write_text(json.dumps(STATUS), encoding="utf-8")
    monkeypatch.setattr(builder, "OUT", out)
    monkeypatch.setattr(builder, "STATUS", status_path)
    monkeypatch.setattr(builder, "CHANGELOG", tmp_path / "DATASET_CHANGELOG.md")
    real_changelog = (ROOT / "data/DATASET_CHANGELOG.md").read_bytes()

    def run(*args):
        monkeypatch.setattr(sys, "argv", ["build_dataset_revision.py", *args])
        return builder.main()
    assert run("--new", "0.3.0-draft.1", "--date", "2026-11-13") == 0
    assert run("--mark-published", "0.3.0-draft.1") == 0
    frozen = (out / "v0.3.0-draft.1" / "reviewed_records.jsonl").read_bytes()
    assert run() == 0, "an unchanged review rebuilds a published revision to the same bytes"
    changed = json.loads(json.dumps(STATUS))
    first = next(iter(changed["rows"]))
    changed["rows"][first]["ur"] = 3
    status_path.write_text(json.dumps(changed), encoding="utf-8")
    assert run() == 3 and "Start a new revision" in capsys.readouterr().out
    assert (out / "v0.3.0-draft.1" / "reviewed_records.jsonl").read_bytes() == frozen
    assert run("--new", "0.3.0-draft.2", "--date", "2026-11-14") == 0
    assert (out / "v0.3.0-draft.1" / "reviewed_records.jsonl").read_bytes() == frozen, "the published revision stays as it was"
    assert json.loads((out / "index.json").read_text(encoding="utf-8"))["current"] == "0.3.0-draft.2"
    assert (ROOT / "data/DATASET_CHANGELOG.md").read_bytes() == real_changelog, "the test must not touch the committed files"
