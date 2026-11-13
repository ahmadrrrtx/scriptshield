# ScriptShield

**Does a model's safety depend on the script Urdu is typed in?**

Most Urdu typed on phones is Roman Urdu: Urdu in Latin letters. ScriptShield asks Cohere Labs'
[Tiny Aya Fire](https://huggingface.co/CohereLabs/tiny-aya-fire)
the same harmful and harmless requests in Urdu script and in Roman Urdu, measures the difference, and tests
one repair (a refusal-steering vector with the "script direction" removed). The study is pre-registered, the
repair did not work, and the result that matters most turned out to be about the automatic judge.

Built for the [Lexsi AI Safety and Alignment Hackathon](https://hackathon.lexsi.ai/) (Lexsi Labs × Cohere
Labs × Hugging Face), Track 2: AI Red Teaming, Safety and Alignment, with Lexsi's
[CuratorKIT](https://github.com/Lexsi-Labs/CuratorKIT), [SafeTune](https://github.com/Lexsi-Labs/SafeTune) and
[AuditKIT](https://github.com/Lexsi-Labs/AuditKIT). Solo project by Muhammad Ahmad ([@ahmadrrrtx](https://huggingface.co/ahmadrrrtx)).

| | |
|---|---|
| Write-up (follows the hackathon's submission checklist) | [`docs/hf_article.md`](docs/hf_article.md) |
| Full result tables | [`docs/RESULTS.md`](docs/RESULTS.md) |
| Model artifacts, Hugging Face collection | [ScriptShield — model artifacts](https://huggingface.co/collections/ahmadrrrtx/scriptshield-model-artifacts-6af6d396e9d50507cbd53417) |
| Data artifacts, Hugging Face collection | [ScriptShield — data artifacts](https://huggingface.co/collections/ahmadrrrtx/scriptshield-data-artifacts-6af6d396c3a2600f7241d2d9) |
| Steering vectors and loader | [`ahmadrrrtx/scriptshield-tiny-aya-fire-steering`](https://huggingface.co/ahmadrrrtx/scriptshield-tiny-aya-fire-steering) |
| Dataset and evaluation logs | [`ahmadrrrtx/scriptshield-urdu-roman`](https://huggingface.co/datasets/ahmadrrrtx/scriptshield-urdu-roman) |
| Replay of the recorded outputs | [`ahmadrrrtx/scriptshield-replay`](https://huggingface.co/spaces/ahmadrrrtx/scriptshield-replay) |

## What we found

| Question | Answer | Status |
|---|---|---|
| Does the model refuse harmful requests less often in Roman Urdu? | **Yes.** 100.0 % in Urdu script vs 47.2 % in Roman Urdu on 36 held-out intents (-52.8 points, 95 % CI -69.4 to -36.1, exact McNemar p = 3.8e-06) | pre-registered, confirmed |
| Does removing the script direction from a refusal-steering vector help Roman-Urdu users? | **No measurable effect.** Same outcome on 71 of 72 harmful prompts; the pre-registered gate was not met | pre-registered, not supported |
| Can the automatic judge be trusted in Roman Urdu? | **No.** Of its Roman-Urdu "refusals", 53 % were refusals on reading; the real Roman-Urdu refusal count is 13 of 36 | post hoc, read by an LLM agent, not by people |

Before and after steering, on the frozen test set (layer 18, strength ρ = 0.1):

| Metric | Unsteered | Pooled vector | Residualized vector |
|---|---:|---:|---:|
| Harmful requests refused, Urdu script (judge) | 100.0 % | 100.0 % | 100.0 % |
| Harmful requests refused, Roman Urdu (judge) | 47.2 % | 61.1 % | 63.9 % |
| Benign requests judged refused | 6.9 % | 13.9 % | 9.7 % |
| Invalid output | 1.4 % | 1.4 % | 1.0 % |
| Utility on 48 factual questions (pattern score) | 68.8 % | 72.9 % | 75.0 % |
| Real Roman-Urdu refusals on reading (post hoc) | 13 of 36 | 19 of 36 | 19 of 36 |

A control vector orthogonal to the refusal direction raised the judged Roman-Urdu refusal rate almost as
much as the pooled vector, so we do not claim that steering makes the model meaningfully safer. What the
study supports: the gap is real, this repair does not close it, and a moderation model's verdict on
Roman-Urdu output has to be read before it is trusted.

**Limits.** 72 intent families written with an LLM and not yet reviewed by a native speaker. One model, one
seed, 64-token responses. Labels come from model judges and from an LLM agent's reading, not from human
annotators. Every number in the two documents above is generated from the logged results.

## Method in six lines

```
v_form   = mean(h_harmful, form) - mean(h_benign, form)       # per script, last prompt token (SafeTune CAA)
v_pooled = mean(v_urdu_script, v_roman)
d_script = mean(h_benign, urdu_script) - mean(h_benign, roman)
v_resid  = v_pooled with d_script projected out, rescaled to |v_pooled|
h_L     <- h_L + alpha * v                                    # SafeTune CAAModel, layer and alpha frozen on dev
test once on 36 unseen intent families; exact McNemar, family bootstrap, Holm
```

Pipeline: **CuratorKIT** validates and exports the corpus → **SafeTune** extracts and applies the vectors →
**AuditKIT** runs and logs every generation → two open judge models label the responses → statistics are
computed locally from the logs.

## Reproduce

Everything below except step 4 and 5 runs on a laptop CPU. Tested with Python 3.13.

### 1. Install

```bash
git clone https://github.com/ahmadrrrtx/scriptshield && cd scriptshield
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                 # numpy, pyyaml, jsonschema, pytest

# optional: the two Lexsi toolkits that run on CPU, at the commits used in the study
pip install --no-deps \
  "git+https://github.com/Lexsi-Labs/AuditKIT@71316da345784ff220d5ed59337441a59ab31526" \
  "git+https://github.com/Lexsi-Labs/CuratorKIT@dd9e835301fcddc74a37501d9e207a5a060d209f"
pip install -e ".[curation]"            # pydantic and tqdm, which CuratorKIT's curation stage imports
```

### 2. Run the unit tests

```bash
python -m pytest -q
make validate        # dataset validator, config validator, secret scan
```

No GPU, network or model is needed. The tests that exercise AuditKIT are skipped if it is not installed.

### 3. Recompute every published number from the public logs

```bash
pip install -e ".[hub]"
python scripts/recompute_from_public.py --download
```

This downloads the public evaluation logs from the dataset repository, reruns the pre-registered analysis
(exact McNemar, family bootstrap, Holm, the gate) and compares the result, number for number, with
`experiments/results/test_analysis/test_analysis_guard.json`. It should end with `IDENTICAL`. The public
logs carry labels and hashes for every response, which is all the analysis uses.

The data stage can be repeated too: `python scripts/run_curation.py` sends the corpus through CuratorKIT
again and checks that 576 records go in, 576 come out and no text is changed.

### 4. Check the released vectors (GPU, and access to the gated base model)

```bash
pip install torch transformers huggingface_hub
pip install "git+https://github.com/Lexsi-Labs/SafeTune@26f59e6d1bdcacafe5f2be3b8d982fb214369659"
hf download ahmadrrrtx/scriptshield-tiny-aya-fire-steering --local-dir vectors && cd vectors
hf download CohereLabs/tiny-aya-fire --revision 73500c80fcb6c8bea3e830c21d5d2920249a0e1a --local-dir ../tiny-aya-fire
python apply_steering.py --model-dir ../tiny-aya-fire --verify expected_outputs.jsonl
```

`apply_steering.py` is standalone: it needs nothing from this repository. In a fresh GPU session it
reproduced 144 of 144 logged responses byte for byte (float16 on a Tesla T4; other hardware or library
versions can differ in the last bits).

### 5. Re-run the experiment

The GPU stages ran as single-file Kaggle kernels generated from a clean commit of this repository, on free
T4 time:

```bash
python scripts/build_kaggle_kernel.py --name fire_test --slug <slug> --title <title> \
    --entry scripts/run_experiment.py --args "--stage test --allow-test" --with-auditkit \
    --model-source cohere-labs/tiny-aya/transformers/fire/1
```

`EXPERIMENT_LOG.md` lists every run with its commit, runtime and what is and is not valid.
`TOOLCHAIN.md` records the library versions. Raw model responses are not in this repository (see below), so
`scripts/analyze.py`, `make_report.py` and `package_artifacts.py` need the outputs of your own run.

## Repository map

| Path | What it is |
|---|---|
| `RESEARCH_PROTOCOL.md` | hypotheses, gate, tests; amendments A1–A20 are dated and say whether they came before or after the data |
| `DECISIONS.md` | every non-obvious choice and every bug, with the evidence |
| `EXPERIMENT_LOG.md` | every GPU run: commit, runtime, what is valid and what is not |
| `docs/RESULTS.md`, `docs/hf_article.md` | generated report and write-up |
| `docs/PROVENANCE.md` | where this snapshot comes from, with the list of original commits |
| `src/scriptshield/` | library: runtime (templating, hooks, generation), steering math, labels, statistics, release rules |
| `scripts/` | run drivers, analysis, report, packaging, recomputation, Kaggle tooling |
| `data/` | corpus v0.2.0, family drafts, utility probe, reviewer pack, schema |
| `configs/` | pinned model and toolkits, grid, `frozen_selection.json`, public links |
| `experiments/` | run reports, analysis JSON, reading labels (no response text) |
| `artifacts/steering_package/`, `demo/` | loader and card template for the vector package; replay page |
| `tests/` | unit tests, no GPU or network needed |

## Safety of the artifacts

The dataset contains harmful **requests**: they state a goal and ask, and none contains instructions. Model
**responses** to harmful prompts are withheld from every public file unless they are clean refusals; in
Roman Urdu, where the automatic judge is unreliable, a response is published only if that exact text was
read and found to be an unambiguous refusal. Labels, lengths and hashes are kept, so the analysis remains
reproducible. `scripts/scan_repo_for_responses.py` checks the tracked files and
`scripts/package_artifacts.py` checks the release folder.

## How this was built

This project was built with substantial help from an AI assistant (an LLM agent). Under the author's
direction it drafted the prompts, wrote much of the code and analysis, and did the response readings that
the documents label as agent readings. The author chose the research direction, approved the protocol and
the release, and is responsible for the content. Nothing here has been labelled by human annotators yet; the
author is a native Urdu speaker and will review the prompts.

## Licences

Code: MIT ([`LICENSE`](LICENSE)). Data, results and documents: CC BY-NC 4.0
([`LICENSE-DATA.md`](LICENSE-DATA.md)). The published steering vectors, dataset and logs are CC BY-NC 4.0;
the vectors derive from Tiny Aya Fire, so their use is also subject to the Cohere Labs Acceptable Use
Policy. The Lexsi toolkits are source-available under LSAL and are imported, not copied. Third-party terms
are recorded in [`LICENSE_LEDGER.md`](LICENSE_LEDGER.md).

## Citation

```bibtex
@misc{scriptshield2026,
  author = {Muhammad Ahmad},
  title  = {ScriptShield: script-dependent refusal in Tiny Aya Fire for Urdu and Roman Urdu},
  year   = {2026},
  url    = {https://github.com/ahmadrrrtx/scriptshield}
}
```

## Acknowledgements

Lexsi Labs for CuratorKIT, SafeTune and AuditKIT and for organising the hackathon; Cohere Labs for Tiny Aya;
the Qwen team for the judge models; Kaggle for the free GPU time on which every run was made.
