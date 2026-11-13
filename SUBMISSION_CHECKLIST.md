# ScriptShield — submission checklist

How this project meets the requirements of the Lexsi AI Safety and Alignment Hackathon. Sources: the rules
and the "Submit" section of <https://hackathon.lexsi.ai/> and the submission checklist in the kickoff
slides, both read on 13 November 2026.

Solo team: Muhammad Ahmad ([@ahmadrrrtx](https://huggingface.co/ahmadrrrtx)). Track 2, AI Red Teaming,
Safety and Alignment: problem 8 (inference-time safety steering), with problem 4 (multilingual and
code-mixed safety).

## Rules

| Requirement | How it is met |
|---|---|
| Dense, open-weights Cohere Labs model from the permitted list | `CohereLabs/tiny-aya-fire` @ `73500c8…`; the weights used were hash-checked against the Hub's LFS objects |
| At least 2 repos of the track used together as a real pipeline (3 or more preferred) | CuratorKIT → SafeTune → AuditKIT, run end to end on the real model (`EXPERIMENT_LOG.md`; article section 2) |
| Developed during the hackathon | every commit is dated between 3 and 13 November 2026 (`docs/PROVENANCE.md`); the GPU runs are Kaggle kernel versions with server-side timestamps |
| All artifacts hosted on Hugging Face (models, adapters, logs, datasets) | the two collections below |
| Deployed publicly (demo or repository) | this repository and the [replay Space](https://huggingface.co/spaces/ahmadrrrtx/scriptshield-replay) |
| Before-and-after metrics, more than one | refusal per script, judged benign refusal, invalid output, utility, judge-flagged unsafe responses, and refusals on reading: article section 8, `docs/RESULTS.md` section 2 |
| Write-up: metrics and why, approach and rationale, how the result is better | [`docs/hf_article.md`](docs/hf_article.md) |
| Original work; libraries and datasets used where permitted | new dataset, no third-party prompts; licences in `LICENSE_LEDGER.md` |

## Submission form

| Item | Value |
|---|---|
| Abstract, under 500 words | [`docs/ABSTRACT.md`](docs/ABSTRACT.md) |
| Hugging Face model collection (public, un-gated) | <https://huggingface.co/collections/ahmadrrrtx/scriptshield-model-artifacts-6af6d396e9d50507cbd53417> |
| Hugging Face dataset collection (public, un-gated) | <https://huggingface.co/collections/ahmadrrrtx/scriptshield-data-artifacts-6af6d396c3a2600f7241d2d9> |
| Write-up or article | [`docs/hf_article.md`](docs/hf_article.md) in this repository |
| GitHub repository, README with reproducibility notes | <https://github.com/ahmadrrrtx/scriptshield>, README section "Reproduce" |
| Repos used | CuratorKIT, SafeTune, AuditKIT |
| Model used | `CohereLabs/tiny-aya-fire`; judges `Qwen/Qwen3Guard-Gen-4B` and `Qwen/Qwen2.5-7B-Instruct` (supplementary, as the rules allow) |
| Track and problem statements | Track 2: 2b problem 8, inference-time safety steering; 2a problem 4, multilingual and code-mixed safety |

## Article sections asked for at the kickoff

| # | Section | In the article |
|---|---|---|
| 1 | Problem statement and approach, in brief | section 1 |
| 2 | Hackathon repos used: which ones, for what, and which features | section 2 |
| 3 | Models used and their licences | section 3 |
| 4 | Datasets and benchmarks used and their licences | section 4 |
| 5 | Model artifacts public, as an HF collection | section 5 |
| 6 | Data artifacts public, as an HF collection | section 6 |
| 7 | Experiments run, findings and what else was tested | section 7 |
| 8 | With more credits: approach, before and after results | section 8 |
| 9 | Teammates tagged | section 9 (solo) |

## What was actually run

- Unit tests on CPU; dataset validator, config validator, secret scan and response-text scan clean.
- Real-model runs on free Kaggle T4s, $0: smoke test (8 of 8 steps), judge comparison, development grid
  (twice; the first was invalidated by a toolkit cache bug we found and fixed), frozen test (7 arms × 288
  prompts plus the utility probe), two judges on the test set, an exploratory development grid, and a
  release verification (144 of 144 logged responses reproduced from the published package alone).
- Pre-registered hypothesis 1 (the script gap) confirmed; the pre-registered gate for hypothesis 3
  (residualization helps) not met.
- The whole pre-registered analysis recomputed from the public logs (`scripts/recompute_from_public.py`).

## What is not done, and is not claimed anywhere

- Human review of the prompts and human annotation of the responses.
- Any second model, second seed, longer responses, adversarial or multi-turn prompts.
- A safety gain from steering.
