# Changelog

Code versions of this repository. The data and steering vectors behind every reported number are tagged
`v0.2.0` on Hugging Face and have not changed since their first release. **No version listed here changes a
reported number**, and no experiment was rerun after the first release.

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
