# Changelog

Code versions of this repository. The data and steering vectors behind every reported number are tagged
`v0.2.0` on Hugging Face and have not changed since their first release. **No version listed here changes a
reported number**, and no experiment was rerun after the first release.

## 0.2.3 (2026-11-14)

The first two review batches (twelve test families) were imported. Dataset changes are in
[`data/DATASET_CHANGELOG.md`](data/DATASET_CHANGELOG.md); this entry lists the code.

- `scripts/import_review.py`: a return can state its batch, the day it arrived and the owner's word that its
  corrections are to be applied; corrections of the English sentence and of the intended meaning (a
  replacement of a request); a correction that was announced without its text (`correction_pending`); one
  pairing verdict per family and the list of families to leave out of harmful-against-harmless comparisons.
- `scripts/build_dataset_revision.py`, `src/scriptshield/data/revision.py`: review revisions under
  `data/revisions/` and the dataset changelog. A sentence the reviewer did not supply is never written; a
  published revision cannot be changed.
- Who wrote what: Urdu and Roman Urdu enter a revision only as the reviewer wrote them. English that the
  maintainer writes to go with a request the reviewer replaced (`drafted` lines) is marked as the maintainer's
  in the revision row, in the reason, in the changelog and in the revised corpus, where it stays `unreviewed`.
- A replaced request keeps its old code-mixed record with the old text and the old meaning, marked `rejected`:
  no code-mixed sentence exists for the new request.
- One revision per return: every answer of the reviewer starts a new review revision and freezes the one before
  it, published or not. The builder refuses to fold a new return into an existing revision. Each revision's
  manifest says what it adds to the one before.
- `scripts/import_review.py`: `kind` lines (what the reviewer called a correction: a changed English sentence
  with an unchanged meaning can be a wording correction if he says so) and `note overall:` (a remark about a
  whole batch).
- `data/reviewer_pack/REVIEW_LEDGER.md` (generated): every return, every correction and what is still open.
- Explorer: a prompt pair the reviewer corrected says so, and that his text has not been run.
- `docs/ABSTRACT.md`: states the review status in numbers and the steering result per arm; a test ties both to
  the data. `docs/EVIDENCE_UPGRADE_PLAN.md`: the optional GPU session was not run before the submission.
- `data/schemas/review_record.schema.json`, `data/schemas/revised_prompt.schema.json`.
- `data/manifests/frozen_public_release_v0.2.0.json`: checksums of the data files of the first public release.
  `scripts/package_artifacts.py` refuses to build a dataset folder in which one of them differs.
- `scripts/robustness_checks.py`: the gap without families whose pairing the reviewer rejected, and refused
  harmless requests with and without them (protocol amendment A23).
- `scripts/audit_dataset.py`: section 9, human review so far.
- Explorer: for each prompt pair, what the author's review says; where a change was asked for, a line that the
  request shown and the replies are the original.
- `scripts/build_review_pack.py`: a batch that has been answered is no longer rewritten; the open batches ask
  for the corrected sentence in the same message.
- The documents describe the review as the owner specified: one participant-provided review by a native Urdu /
  Roman Urdu speaker; not an independent expert panel, not a professional translation certification, not a
  consensus of several reviewers.

## 0.2.2 (2026-11-13)

Faults found by checking the published pages: the live explorer, the article text and the cards.

- Explorer: a cell could show "judge: refusal" and "read as: refusal" and still be withheld as "not a clean
  refusal". The data was right (the reading was borderline, so the text stays withheld), but the page did not
  say so. Borderline readings are now marked, and every withheld cell names its reason, taken from
  `withheld_reason` in the published log.
- Article: it quoted an exact number of unit tests that was already out of date. The sentence is now a floor
  that the generator keeps true. `scripts/make_article.py --check` compares the committed article with what
  the generator produces, and the snapshot script refuses to export stale generated documents.
- Article: its title is the one used on the explorer page; the finding is the first bold line. The text
  contains no HTML tags.

## 0.2.1 (2026-11-13)

Faults found by checking a fresh clone of tag `v0.2.0` and the published dataset repository.

- `scripts/audit_dataset.py` added one table only when a local release folder existed, so the committed audit
  could not be reproduced from a clone. The audit now uses no model output. The numbers of that table are in
  `docs/ROBUSTNESS_CHECKS.md`, which is computed from the public logs. New: `audit_dataset.py --check` and
  `make docs-check`.
- The copy of the audit in the dataset repository had two dead relative links. The links are rewritten for
  that repository's layout. Packaging and the snapshot script now refuse dead relative links
  (`src/scriptshield/artifacts/linkcheck.py`).
- `scriptshield.__version__` said 0.0.1 while the package metadata said 0.2.0. One version everywhere, with a
  test.
- The description of the explorer in the Space README matches its layout (one row per written form).

## 0.2.0 (2026-11-13)

Revision of the write-up and the supporting material.

- `docs/FINAL_HF_ARTICLE.md`: the write-up, in the nine sections of the hackathon checklist, generated from
  the result files, with six figures.
- `docs/DATASET_QUALITY_AUDIT.md`: family-level audit of the corpus. Automatic checks, LLM notes and human
  review are kept apart.
- `docs/ROBUSTNESS_CHECKS.md`: post hoc; the script gap on subsets of the test set and the errors of the
  automatic judge by kind of reply (protocol amendment A21).
- `docs/HUMAN_RESPONSE_CHECK.md`: design of a person's check of the LLM reading on a stratified sample
  (protocol amendment A22). The document states how many replies are labelled.
- `docs/EVIDENCE_UPGRADE_PLAN.md`: six further checks assessed, with cost and decision.
- `data/reviewer_pack/`: guide, batches and sheet for the author's review of the prompts, and the review
  status of every prompt pair.
- `artifacts/steering_package/check_base_model.py`: integrity and base-model check that leaves the
  GPU-verified loader untouched.
- README, model card, dataset card, abstract and the explorer page were rewritten.
- `docs/baselines/`: checksums of everything that was public at `v0.1.0`.

## 0.1.0 (2026-11-13)

First public state: code, protocol, decisions, experiment log, result tables, first write-up, steering
package, dataset and replay page.
