---
license: cc-by-nc-4.0
base_model: CohereLabs/tiny-aya-fire
base_model_relation: adapter
datasets:
- {{ID_DATASET}}
language:
- ur
tags:
- steering-vector
- activation-steering
- contrastive-activation-addition
- refusal
- ai-safety
- urdu
- roman-urdu
- negative-result
- safetune
- lexsi
---

# ScriptShield steering vectors for Tiny Aya Fire

Six 2,048-dimensional steering vectors for decoder block {{LAYER}} of
[`CohereLabs/tiny-aya-fire`](https://huggingface.co/CohereLabs/tiny-aya-fire), with a manifest and a
standalone loader. No model weights are included.

> **This is an inference-time steering package, not a fine-tuned model checkpoint.** It holds six small
> vectors, a manifest and two Python files. It cannot be loaded with `from_pretrained`, and it does nothing
> without your own copy of the base model. A vector is added to the model's activations while it generates;
> the model's weights are never changed.

They were built to test one idea: a refusal-steering vector learned from Urdu-script **and** Roman-Urdu
prompts also carries "which script is this" information; if that component is projected out, the vector
might protect Roman-Urdu users better.

**The idea was not supported (pre-registered gate {{GATE}}).** These vectors are published so that the
result can be checked and built on, **not as a recommended safety intervention**.

| | |
|---|---|
| Dataset and evaluation logs | [`{{ID_DATASET}}`]({{URL_DATASET}}) |
| Code, protocol and reproduction notes | [{{URL_GITHUB}}]({{URL_GITHUB}}) |
| Write-up | [article]({{URL_ARTICLE}}) · [full result tables]({{URL_RESULTS}}) |
| Replay of the recorded outputs | [`{{ID_SPACE}}`]({{URL_SPACE}}) |
| Collections | [{{TITLE_COLLECTION_MODELS}}]({{URL_COLLECTION_MODELS}}) · [{{TITLE_COLLECTION_DATA}}]({{URL_COLLECTION_DATA}}) |

Author: {{AUTHOR}}. Built for the [Lexsi AI Safety and Alignment Hackathon]({{URL_HACKATHON}}), Track 2:
problem 4 (multilingual and code-mixed safety) with problem 8 (inference-time safety steering).

## Findings in brief

{{RESULTS_BRIEF}}

![{{ALT_ARMS}}]({{FIG}}/arms_comparison.png)

*Every vector, including the placebo (`orthogonal_null`), lifts the judged refusal of harmful Roman-Urdu
requests by a few prompts out of 36, with overlapping intervals. The residualized vector is not better than
the pooled one.*

## What is in the package

| File | Content |
|---|---|
| `steering_vectors.npz` | one float64 array of length 2,048 per arm (names below). Each is a direction in the residual stream at the output of decoder block {{LAYER}} (0-based) |
| `manifest.json` | layer, strength, per-vector checksums, base-model revision and weight hashes, extraction and inference settings, toolkit versions, code commit |
| `frozen_selection.json` | the layer and strength chosen on the development split before the test set was run |
| `apply_steering.py` | standalone loader (needs only `numpy`, `torch`, `transformers`, `safetune`) |
| `check_base_model.py` | checks that the package is intact and that a local base model is the one the vectors were made from (needs only `numpy`; does not load the model) |
| `expected_outputs.jsonl` | 144 logged responses (48 harmless factual questions in Urdu script and Roman Urdu × unsteered, pooled, residualized) with their sha256, to check that your setup reproduces ours |
| `SHA256SUMS` | checksums of every file |

| Arm | What it is | cos to `pooled` |
|---|---|---:|
{{ARM_TABLE}}

All arms are rescaled to the norm of `pooled`, so they are compared at the same dose. Orientation is
harmful − benign: a **positive** strength pushes toward refusal.

## Results on the frozen test set

{{N_TEST}} intent families the vectors never saw ({{N_CAL}} other families were used to extract them and
12 more to choose the layer and strength). One model, one seed, greedy decoding, 64 new tokens.

### The script gap in the unsteered model (pre-registered)

{{RESULTS_H1}}

### All arms (pre-registered labels)

{{RESULTS_ARMS}}

### Residualized vs pooled (pre-registered gate)

{{RESULTS_H3}}

### Each steered arm against the unsteered model

{{RESULTS_VS_UNSTEERED}}

## Can the automatic judge be trusted in Roman Urdu?

{{RESULTS_VALIDITY}}

## What can and cannot be claimed

{{RESULTS_CLAIMS}}

## Check what you downloaded

```bash
sha256sum -c SHA256SUMS                                             # every file of the package
python check_base_model.py                                          # manifest and vector file agree (no model needed)
python check_base_model.py --model-dir /path/to/tiny-aya-fire       # and the base model is the right one (hashes the weights)
```

Expected last line of the third command:
`OK: the package is intact and the model files are the ones the vectors were made from.`

The vectors can be inspected on a laptop, without a GPU or the base model:

```python
from apply_steering import load_package          # numpy only; every vector is checked against its checksum

vectors, manifest = load_package(".")
print(manifest["layer"], manifest["hidden_dim"], round(manifest["alpha"], 4), sorted(vectors))
```

Output, produced from the published files when this card was built:

```
{{INSPECT_OUTPUT}}
```

## How to use

```bash
pip install torch transformers numpy huggingface_hub
pip install "git+https://github.com/Lexsi-Labs/SafeTune@26f59e6d1bdcacafe5f2be3b8d982fb214369659"

# this package, and the base model (gated: accept its terms on the Hub first, then log in)
hf download {{ID_MODEL}} --local-dir scriptshield-vectors && cd scriptshield-vectors
hf download CohereLabs/tiny-aya-fire --revision {{REVISION}} --local-dir /path/to/tiny-aya-fire

# one prompt, unsteered vs steered
python apply_steering.py --model-dir /path/to/tiny-aya-fire --arm pooled --prompt "آپ کیسے ہیں؟"

# check that your environment reproduces the logged run exactly
python apply_steering.py --model-dir /path/to/tiny-aya-fire --verify expected_outputs.jsonl
```

```python
from apply_steering import load_package, load_base, make_wrapper, generate

vectors, manifest = load_package(".")                       # checksums are verified
tok, model = load_base("/path/to/tiny-aya-fire", manifest["inference"]["dtype"])
steered = make_wrapper(model, vectors["pooled"], manifest["layer"], manifest["alpha"])
print(generate(model, tok, ["..."], steered))               # steering is live only via wrapper.generate
```

Frozen setting: layer {{LAYER}}, ρ = {{RHO}} (α = {{ALPHA}}; ρ is the added vector's norm as a fraction of
the mean residual-stream norm at that layer). You need your own access to the base model.

## What the loader checks, and what it does not

| Situation | What happens |
|---|---|
| A vector was altered, or the file is damaged | `load_package` raises `checksum mismatch` |
| A vector has the wrong number of dimensions | `load_package` raises (shape is compared with `hidden_dim` in the manifest) |
| A vector named in the manifest is missing | `load_package` raises |
| The manifest states another sign convention | `load_package` raises instead of guessing the sign |
| The file holds a vector that the manifest does not list | **not caught by the loader**; `check_base_model.py` reports it |
| The base model has another hidden size or fewer blocks | **not caught before generation** by the loader (it fails later with a tensor error); `check_base_model.py --model-dir` reports it first |
| The base model has the same shape but other weights (another Tiny Aya variant, another revision) | **not caught by the loader**: it would steer silently. `check_base_model.py --model-dir` compares the sha256 of the weight files with the manifest and refuses |
| Steering hooks left installed after generation | `generate` raises |

`apply_steering.py` is byte-for-byte the file that was verified on a GPU, which is why the extra checks live
in a separate script. Run `check_base_model.py` once before you steer. The strongest check of all is
`--verify`: it regenerates {{N_EXPECTED}} logged replies and compares their hashes.

## How the vectors were made

1. **Data.** ScriptShield corpus v0.2.0: 72 intent families, each with a harmful and a matched benign
   request, written in Urdu script, Roman Urdu, code-mixed Urdu-English and English. Families are split
   24 calibration / 12 development / 36 test; no family crosses a split.
2. **Extraction.** Lexsi **SafeTune** contrastive activation addition at the last prompt token:
   mean(harmful) − mean(benign), separately for Urdu script and Roman Urdu on the calibration families;
   `pooled` is their equal-weight mean. Cross-checked against an independent activation capture.
3. **Script direction.** Mean activation difference between Urdu-script and Roman-Urdu **benign** prompts.
   `residualized` = `pooled` with that direction projected out, rescaled to the pooled norm.
4. **Selection.** Layer and strength were chosen on the development families by a rule written down
   beforehand (largest gain in harmful refusal with at most +2 points of benign refusal), on the `pooled`
   arm only, and committed before the test set was run.
5. **Evaluation.** Generation and logging through Lexsi **AuditKIT**; data validation and export through
   Lexsi **CuratorKIT**.

## Reproducibility

{{VERIFY_LINE}}

Test run produced at code commit `{{CODE_COMMIT}}`, base model revision `{{REVISION}}` (the sha256 of
both weight shards and of the tokenizer are in `manifest.json`), float16 on a Tesla T4.

## Versions

| Version | Date | What |
|---|---|---|
| tag `v0.2.0` | 2026-11-13 | first public release: vectors, manifest, loader and expected outputs exactly as verified on a GPU |
| current | {{BUILD_DATE}} | documentation rewritten; `check_base_model.py` added. The four verified files are unchanged |

sha256 of the four verified files (identical at `v0.2.0` and now):

{{CORE_SUMS}}

To get exactly the first release: `hf download {{ID_MODEL}} --revision v0.2.0 --local-dir vectors`.

## Limitations

- **Small, and not validated by annotators.** 36 test families. The prompts were drafted with an LLM;
  {{REVIEW_LINE}} Intervals are wide.
- **The judge is unreliable in Roman Urdu.** See the section above. The reading that corrects it was done
  by an LLM agent, not by people.
- **One model, one layer, one strength, one seed, 64-token responses.** Nothing here is known to transfer.
- **Steering has a cost.** On the development split, doubling the strength from ρ = 0.1 to 0.2 raised
  judged refusals of benign prompts by {{DOSE_COST}} points depending on the layer. At the frozen strength
  the judge-measured increase exceeded the pre-registered budget on the test set; on reading, those
  responses were garbled answers rather than refusals, which is a cost of a different kind.
- **Not a defence.** Anyone who controls the inference code can remove a steering vector.

## How this was built

This project was built with substantial help from an AI assistant (an LLM agent). Under the author's
direction it drafted the prompts, wrote much of the code and analysis, and did the response readings
labelled above as agent readings. The author chose the research direction, approved the protocol and the
release, and is responsible for the content. Responses were not labelled by human annotators; the author's
review of the prompts is recorded in the dataset repository.

## Licence and terms

The vectors are derived from the Tiny Aya weights and are released for **non-commercial research** under
CC-BY-NC 4.0; use is also subject to the Cohere Labs Acceptable Use Policy that governs the base model.
The base weights are not redistributed. `apply_steering.py` is also available under the MIT licence in the
code repository. SafeTune, AuditKIT and CuratorKIT are source-available under the Lexsi Labs licence (LSAL),
which has its own non-commercial terms.

## Citation

```bibtex
@misc{scriptshield2026,
  author = {{{AUTHOR_NAME}}},
  title  = {ScriptShield: script-dependent refusal in Tiny Aya Fire for Urdu and Roman Urdu},
  year   = {2026},
  url    = {{{URL_GITHUB}}}
}
```

## Acknowledgements

Built for the Lexsi hackathon with Lexsi Labs' CuratorKIT, SafeTune and AuditKIT. Base model by Cohere Labs.
Judge models by the Qwen team (Apache-2.0).
