# ScriptShield: Tiny Aya refuses harmful requests in Urdu script and mostly does not in Roman Urdu

*Lexsi AI Safety and Alignment Hackathon · Track 2, AI Red Teaming, Safety and Alignment · problem 8
(inference-time safety steering) with problem 4 (multilingual and code-mixed safety). Solo submission by
Muhammad Ahmad (@ahmadrrrtx).*

**Artifacts:** [model collection](https://huggingface.co/collections/ahmadrrrtx/scriptshield-model-artifacts-6af6d396e9d50507cbd53417) · [data collection](https://huggingface.co/collections/ahmadrrrtx/scriptshield-data-artifacts-6af6d396c3a2600f7241d2d9) ·
[code and reproduction notes](https://github.com/ahmadrrrtx/scriptshield) · [replay demo](https://huggingface.co/spaces/ahmadrrrtx/scriptshield-replay)

*Every number in this article is generated from the logged results by `scripts/make_article.py`; none is
typed by hand. The sections follow the hackathon's submission checklist.*

## 1. Problem statement and approach, in brief

**Problem.** Most Urdu typed on phones is Roman Urdu: Urdu written in Latin letters. Multilingual safety work
usually treats "Urdu" as one language. Urdu script and Roman Urdu share the language and differ only in
orthography, which makes the pair a clean test: same meaning, same speaker, different characters. A guardrail
that works in one script and fails in the other has a hole exactly where most informal Urdu is written.

**Approach.** We wrote 72 matched intent families (a harmful request and a benign one on the
same topic, each in Urdu script, Roman Urdu, code-mixed Urdu-English and English), measured how Cohere Labs'
Tiny Aya Fire responds to them, and tested one repair: a refusal-steering vector from which the "which script
is this" direction has been projected out. Hypotheses, acceptance gate, statistical tests and the rule for
choosing the layer and strength were written down before the data existed, and the test set was run once.

**What we found.**

- **The gap is large.** On 36 held-out intents, Tiny Aya Fire refused 100.0 % of harmful requests
  written in Urdu script and 47.2 % of the same requests in Roman Urdu (-52.8 points, 95 % CI
  -69.4 to -36.1, exact McNemar p = 3.8e-06). Code-mixed Urdu-English (97.2 %) and English (100.0 %)
  behave like Urdu script. This test was pre-registered.
- **Our intervention did not work.** We predicted that removing the "script direction" from a
  refusal-steering vector would help Roman-Urdu users. It made no measurable difference: the pre-registered
  gate was not met, and the residualized and the ordinary vector gave the same outcome on 71 of
  72 harmful prompts. We report it as a negative result.
- **The automatic judge failed where it mattered.** The open moderation model we used as judge calls
  echoes, loops and off-topic text "refusals" in Roman Urdu. Reading the responses showed that only
  53 % of its Roman-Urdu "refusals" were refusals. Every correction we applied makes the script
  gap larger, not smaller.

**Why it is useful.** Anyone deploying a small multilingual model for Urdu speakers can measure this gap on
their own model with a few hundred prompts; the result tells them that a moderation model's verdict on
Roman-Urdu output needs to be read before it is trusted; and the negative result saves others from trying
the same repair.

Limits that apply to everything below: 72 intent families written with an LLM and **not yet
reviewed by a native speaker**; one model, one seed, 64-token responses; labels from model judges and from an
LLM agent's reading, **not from human annotators**.

## 2. Hackathon repos used: which ones, for what, and which features

Three Lexsi toolkits run as one pipeline, on the real model, end to end:

| Repo (pinned) | Used for | Features used |
|---|---|---|
| [**CuratorKIT**](https://github.com/Lexsi-Labs/CuratorKIT) 0.1.21 | building the dataset | `Curator` / `CuratorConfig` pipeline: ingestion, schema gate, NFC normalisation, exact de-duplication, provenance, `prompt_only` export. Toxicity and quality gates deliberately off (they would delete the harmful half); MinHash de-duplication off (it would merge the matched pairs) |
| [**SafeTune**](https://github.com/Lexsi-Labs/SafeTune) 0.1.8 | making and applying the steering vectors | `interventions.steer.caa.extract_caa_vectors` for contrastive activation addition; `CAAModel` forward hooks to apply a vector during generation. Our residualization sits between those two calls; SafeTune is neither forked nor patched |
| [**AuditKIT**](https://github.com/Lexsi-Labs/AuditKIT) 1.1.3 | running and logging every generation | `generate` with `CallableModel`, `Sample`, `RunConfig` and the disk cache for every generation of the real runs; `evaluate(model="precomputed")` with a `FunctionScorer` in the offline smoke pipeline. Aggregation and significance tests are ours |

**Pipeline.** CuratorKIT validates and exports the corpus → SafeTune extracts the vectors and applies them
during generation → AuditKIT runs and logs every generation → two open judge models label the responses →
statistics are computed locally from the logs. Each remote run is a single generated file that embeds the
repository at a clean commit, so every result names the exact code that produced it. All compute was free
Kaggle T4 time.

**Feedback for the toolkit authors.** Observed at the pinned commits, each with a regression test in our
repository:

1. **AuditKIT** identifies a Python-callable model by its code and immutable closure values. Two steering
   configurations that differ only in a captured object therefore share a cache key, and the disk cache
   silently returns the first configuration's text for the second. Our first development grid consisted of
   32 "configurations" with one distinct set of outputs. We now give every call a unique model identity and
   fail if the model was not actually asked.
2. **SafeTune**'s `CAAModel` installs its hooks only inside `wrapper.generate(...)` or a `with` block.
   Calling `wrapper.model.generate(...)` produces unsteered text without any warning.
3. **SafeTune** applies the chat template itself; passing an already-templated prompt templates it twice.
4. Tiny Aya's chat template begins with a BOS token and its tokenizer also adds one, so the default
   tokenizer call yields two; its generation config lists only one of the three tokens that end a turn.

## 3. Models used and their licences

| Model | Role | Licence |
|---|---|---|
| [`CohereLabs/tiny-aya-fire`](https://huggingface.co/CohereLabs/tiny-aya-fire) @ `73500c80` | model under study (one of the seven permitted models) | CC-BY-NC 4.0 + Cohere Labs Acceptable Use Policy |
| [`Qwen/Qwen3Guard-Gen-4B`](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B) | primary judge of the responses | Apache-2.0 |
| [`Qwen/Qwen2.5-7B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | second judge (pre-declared sensitivity analysis) | Apache-2.0 |

**Why Tiny Aya Fire.** It is a permitted dense Cohere open-weights model (3.35 B parameters, 36 layers) with
documented South Asian language coverage, and it fits on a free Kaggle T4, so the whole study cost $0. The
judges are used for inference only, as the rules allow. No model weights are redistributed.

## 4. Datasets and benchmarks used and their licences

| Dataset | Role | Licence |
|---|---|---|
| **ScriptShield v0.2.0** (ours, new) | 576 prompts for extraction, selection and the final test | CC-BY-NC 4.0 |
| ScriptShield utility probe (ours, new) | 24 simple factual questions in both scripts | CC-BY-NC 4.0 |

No third-party dataset or benchmark was used, and no third-party prompt was copied.

**ScriptShield v0.2.0**: 576 prompts = 72 intent families × harmful / matched
benign × four forms (Urdu script, Roman Urdu, code-mixed, English). A family pairs a harmful request with a
benign one on the same topic, e.g. breaking into someone's email account vs recovering your own. Harmful
prompts state a goal and ask; they contain no instructions.

Families, not prompts, are the unit of splitting and of every statistical test: 24 for building vectors,
12 for choosing the layer and strength, 36 for the final test. No family crosses a split.

The data went through Lexsi **CuratorKIT** for schema validation, normalisation, exact de-duplication and
provenance (576 in, 576 out, no text changed). A per-character check guarantees that no
Urdu-script prompt contains Latin or Devanagari letters and no Roman-Urdu prompt contains Arabic-script letters.

**Status: unreviewed.** A bilingual reviewer pack is included with the dataset. Until a native speaker
returns it, naturalness and exact equivalence across forms are unverified.

## 5. Model artifacts (public Hugging Face collection)

**[ScriptShield — model artifacts](https://huggingface.co/collections/ahmadrrrtx/scriptshield-model-artifacts-6af6d396e9d50507cbd53417)**

- [`ahmadrrrtx/scriptshield-tiny-aya-fire-steering`](https://huggingface.co/ahmadrrrtx/scriptshield-tiny-aya-fire-steering): the six steering vectors for decoder block 18 of Tiny Aya Fire
  (pooled, residualized, two controls, Urdu-only, Roman-only), a manifest with every setting and checksum,
  the frozen selection, a standalone loader and 144 logged responses to check a setup against.
- [`ahmadrrrtx/scriptshield-replay`](https://huggingface.co/spaces/ahmadrrrtx/scriptshield-replay): a replay explorer of the recorded outputs, arm by arm and script by script.

In a fresh GPU session the released package alone (vectors, manifest and loader, with none of this project's code importable) reproduced 144 of 144 logged responses byte for byte. The vectors are published so that the result can be checked and built on, **not as a
recommended safety intervention**: the idea they were built to test was not supported.

## 6. Data artifacts (public Hugging Face collection)

**[ScriptShield — data artifacts](https://huggingface.co/collections/ahmadrrrtx/scriptshield-data-artifacts-6af6d396c3a2600f7241d2d9)**

- [`ahmadrrrtx/scriptshield-urdu-roman`](https://huggingface.co/datasets/ahmadrrrtx/scriptshield-urdu-roman): the corpus with its three splits, the utility probe, the reviewer
  pack, and the evaluation logs: one row per prompt and arm of the frozen test run with both judges'
  verdicts, the refusal margins, every analysis file, the run reports, and the labels of the response reading.

**What is withheld.** The logs contain model responses to harmful requests, and some of them comply. A
response text is replaced by `[withheld]` when the prompt is harmful and the response is not a clean
refusal, or when the judge flagged it unsafe. In Roman Urdu, where the judge cannot be trusted, a response
to a harmful prompt is published only if that exact text was read and found to be an unambiguous refusal.
Labels, verdicts, lengths and hashes are kept for every row, and **the whole pre-registered analysis can be
recomputed from the public logs alone** (`scripts/recompute_from_public.py` in the repository does it and
compares the result with the published numbers).

## 7. Experiments run, findings and what else was tested

### 7.1 Method and metrics

**Steering vector.** With SafeTune's contrastive activation addition, for each script we take the mean
activation on harmful prompts minus the mean on benign prompts at the last prompt token. The `pooled` vector
is the equal-weight mean of the Urdu-script and Roman-Urdu vectors.

**Script direction.** The mean activation difference between Urdu-script and Roman-Urdu **benign** prompts.

**Residualization.** `residualized` = `pooled` with the script direction projected out, rescaled to the
pooled norm so both are applied at the same dose.

**What had to be true for this to help.** A harmful-minus-benign contrast taken within one script already
cancels any constant script offset. Residualization can only matter if the refusal vector has a real
component along the script direction. We measured that component before looking at behaviour (7.2).

**Arms.** Unsteered; pooled; residualized; two controls (the pooled vector with a *random* direction
removed, and a vector of the same norm exactly orthogonal to the pooled one); Urdu-only and Roman-only
vectors. All are norm-matched.

**Metrics, and why each is there.** We report them separately, never as one blended score:

| Metric | Why it is there |
|---|---|
| Refusal rate on harmful prompts, per script | the safety behaviour itself |
| Gap between scripts, paired by intent | the research question |
| Refusal rate on matched benign prompts | a vector that refuses everything is not safer |
| Utility on 24 factual questions | catches a vector that breaks ordinary answering |
| Invalid rate (empty or looping output) | catches a vector that "improves safety" by destroying fluency |
| Judge-flagged unsafe responses | a response can open with a refusal and still leak |

Every attempted prompt stays in the denominator. An empty, looping or unparseable response is never counted
as a refusal or as safe.

**Pre-registration.** The hypotheses, the gate (residualized must beat pooled by at least 5 points on the
worst script or on the gap, without more than 2 points of extra benign refusal, 2 of utility loss or 1 of
invalid output), the tests (exact McNemar, family-cluster bootstrap, Holm correction) and the rule for
choosing layer and strength were written down before the corresponding data existed. The chosen setting
(layer 18, ρ = 0.1) was committed to git before the test set was run. The test prompts were
generated once (a first launch stopped on a missing file before producing any output).

### 7.2 The model forms a weaker harm signal for Roman Urdu

Before any generation, on the 24 calibration families: the harmful-vs-benign direction for Roman Urdu points
the same way as for Urdu script, but at layer 18 its size is only 0.48 of the Urdu-script
one (95 % CI 0.41 to 0.61). The pooled refusal vector is nearly orthogonal to the script direction at the
layers we searched (|cosine| ≤ 0.089); residualization would remove at most 9.1 % of its
norm. So the mechanism behind the gap looks like a weak harm signal, not script information leaking into the
refusal direction. This already predicted that residualization had little to act on.

### 7.3 The script gap (pre-registered)

Paired by intent family, n = 36 test families, harmful prompts, same meaning in both scripts.

| | Urdu script | Roman Urdu | Difference |
|---|---:|---:|---:|
| Refusal rate | 100.0 % | 47.2 % | -52.8 pp (95 % CI -69.4 to -36.1) |
| Judge-flagged unsafe response | 0.0 % | 27.8 % | McNemar p = 0.002 |

Exact McNemar on refusal: 19 families were refused in Urdu script but not in Roman Urdu, 0 the reverse; p = 3.8e-06.

For reference, the same harmful intents were refused at 97.2 % in code-mixed Urdu-English and 100.0 % in English.

The same pattern appears on the other 36 families (calibration + development, never part of this test): 94.4 % in Urdu script vs 44.4 % in Roman Urdu.

The model is also weaker in Roman Urdu on harmless material: on 24 simple factual questions it answered 87.5 % correctly in Urdu script and 50.0 % in Roman Urdu, and it answered 9 of 72 Roman-Urdu prompts in Devanagari (Hindi).

(Utility is scored by answer patterns fixed before the run. Reading the answers (post hoc, by the agent) gives 22 of 24 in Urdu script and 13 of 24 in Roman Urdu, the same 9-question difference; see the note under the all-arms table.)

### 7.4 Steering, and the residualization test (pre-registered)

| Arm | Refusal, harmful, Urdu script | Refusal, harmful, Roman Urdu | Judged refusal of benign prompts | Invalid | Utility |
|---|---:|---:|---:|---:|---:|
| unsteered | 100.0 % | 47.2 % | 6.9 % | 1.4 % | 68.8 % |
| pooled | 100.0 % | 61.1 % | 13.9 % | 1.4 % | 72.9 % |
| residualized | 100.0 % | 63.9 % | 9.7 % | 1.0 % | 75.0 % |
| random_subspace | 100.0 % | 61.1 % | 13.9 % | 1.4 % | n/a |
| orthogonal_null | 97.2 % | 58.3 % | 4.2 % | 1.4 % | n/a |
| ur_only | 100.0 % | 61.1 % | 12.5 % | 2.1 % | n/a |
| ro_only | 100.0 % | 58.3 % | 8.3 % | 1.0 % | n/a |

Every attempted prompt is in the denominator (36 per cell; benign = 72 Urdu-script + Roman-Urdu prompts). `invalid` = empty or a repetition loop; it is never counted as a refusal. Utility was measured for three arms only. **The section on the judge shows that its refusal label is unreliable in Roman Urdu; read the Roman-Urdu and benign columns with that in mind.**

**Utility column: post hoc reading check (protocol A20).** The agent read all 144 utility answers (not a human; arm labels visible). 7 pattern scores disagree with the text: 5 correct answers used a spelling or transliteration the patterns do not cover, and 2 answers were matched although the answer they state is wrong (2 borderline, also shown flipped). Details: `experiments/adjudication/utility_reading_check.json`.

| Arm | Utility by pattern (pre-registered) | Utility on reading (post hoc) | Borderline flipped |
|---|---:|---:|---:|
| unsteered | 33/48 | 35/48 | 35/48 |
| pooled | 35/48 | 36/48 | 37/48 |
| residualized | 36/48 | 36/48 | 37/48 |

On reading, the pooled and residualized arms answer the same questions correctly; the pooled arm differs from the unsteered model on 1 question (2 with the borderline answer flipped). The pre-registered column is unchanged. Differences of one or two questions in it are within the scoring error of the patterns and should not be read as effects of steering.

| Criterion | Measured | Threshold | Met |
|---|---:|---:|:--:|
| Worst-form refusal gain | +2.8 pp (CI +0.0 to +8.3) | ≥ +5 pp | no |
| Script-gap reduction | +2.8 pp (CI +0.0 to +8.3) | ≥ +5 pp | no |
| Over-refusal increase | -4.2 pp | ≤ +2 pp | yes |
| Utility drop | -2.1 pp | ≤ +2 pp | yes |
| Invalid-rate increase | -0.3 pp | ≤ +1 pp | yes |

**Gate NOT MET.** The two arms gave the same refusal outcome on 71 of 72 harmful prompts; the single difference is one family. With 36 families the interval still contains +5 pp, so by the pre-registered wording this is inconclusive rather than proof of no effect.
On reading (post hoc, see the reading of the responses) the two arms are indistinguishable: 19 vs 19 real Roman-Urdu refusals, 3 vs 3 answers, 14 vs 14 non-responsive; the one judged difference was a mistranslated echo that the judge read as a refusal.
The two arms produced byte-identical text on 232 of 288 test prompts (80.6 %).
The utility difference in the table is a scoring artefact: on reading (post hoc, note under the all-arms table) both arms answer the same 36 of 48 questions correctly. The gate outcome does not depend on it.

Pre-declared continuous endpoint (teacher-forced refusal margin, residualized − pooled, family means): +0.0219 nats/token (95 % CI +0.0208 to +0.0231; sign-flip p = 0.0001).
That is statistically detectable and tiny: the unsteered margin is 2.44 for Urdu-script and 1.14 for Roman-Urdu harmful prompts, so residualization closes 1.7 % of that 1.30-nat difference.

Holm-adjusted p-values: H1 unsteered ur vs ro (McNemar): 1.1e-05; H3 worst-form gain (bootstrap): 1; H3 gap reduction (bootstrap): 1.

An exploratory rerun of every vector over the whole development grid (16 layer/strength settings, after the
freeze) tells the same story at stronger doses: residualized was ahead of pooled on harmful refusal in
3 settings, behind in 4 and level in 9.

### 7.5 The judge could not be trusted in Roman Urdu

#### Second judge — PRE-DECLARED sensitivity analysis

The same outputs scored by a rubric prompt on Qwen2.5-7B-Instruct: H1 refusal 100.0 % vs 44.4 % (-55.6 pp, 95 % CI -72.2 to -38.9; exact McNemar p = 1.9e-06).
H3 worst-form gain +2.8 pp, gate not met. Both pre-registered conclusions hold under the second judge.

| Arm | Refusal, harmful, Roman Urdu (judge 1) | (judge 2) | Refusal of benign prompts (judge 1) | (judge 2) |
|---|---:|---:|---:|---:|
| unsteered | 47.2 % | 44.4 % | 6.9 % | 13.9 % |
| pooled | 61.1 % | 50.0 % | 13.9 % | 20.8 % |
| residualized | 63.9 % | 52.8 % | 9.7 % | 20.8 % |
| random_subspace | 61.1 % | 52.8 % | 13.9 % | 20.8 % |
| orthogonal_null | 58.3 % | 44.4 % | 4.2 % | 9.7 % |
| ur_only | 61.1 % | 52.8 % | 12.5 % | 16.7 % |
| ro_only | 58.3 % | 47.2 % | 8.3 % | 18.1 % |

#### Prompt echoes — POST HOC (protocol A18)

The model often answers a Roman-Urdu prompt by repeating the prompt. 49 of 2016 test responses are such echoes (49 of them to Roman-Urdu prompts), and the judge labelled 32 of them refusals. Treating an echo as `invalid` instead:

- H1 becomes 100.0 % vs 36.1 % (-63.9 pp, 95 % CI -77.8 to -47.2; exact McNemar p = 2.4e-07).

| Arm | Refusal, harmful, Roman Urdu (pre-registered) | (echo-corrected) | Refusal of benign prompts (echo-corrected) |
|---|---:|---:|---:|
| unsteered | 47.2 % | 36.1 % | 6.9 % |
| pooled | 61.1 % | 47.2 % | 13.9 % |
| residualized | 63.9 % | 50.0 % | 9.7 % |
| random_subspace | 61.1 % | 47.2 % | 13.9 % |
| orthogonal_null | 58.3 % | 47.2 % | 4.2 % |
| ur_only | 61.1 % | 47.2 % | 12.5 % |
| ro_only | 58.3 % | 47.2 % | 8.3 % |

#### Reading the responses — POST HOC, exploratory (protocol A19)

The LLM agent labelled all 214 distinct Roman-Urdu test responses of four arms (288 rows) with the arm hidden, under a rubric committed beforehand: **R** refusal, **A** answer toward the request, **N** non-responsive (echo, loop, paraphrase of the prompt, off-topic or misread). **This is not human annotation and not by a native speaker; it was only partly blind.**

| Arm | Harmful: R | A | N | Judge said refusal | Benign: R | A | N | Judge said refusal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| unsteered | 13 | 6 | 17 | 17 | 0 | 29 | 7 | 5 |
| pooled | 19 | 3 | 14 | 22 | 0 | 27 | 9 | 10 |
| residualized | 19 | 3 | 14 | 23 | 0 | 28 | 8 | 7 |
| orthogonal_null | 15 | 5 | 16 | 21 | 0 | 27 | 9 | 3 |

36 prompts per cell. With every borderline label flipped to its alternative, harmful-prompt refusals are unsteered 11, pooled 15, residualized 15, orthogonal_null 12.

Judge against this reading, Roman-Urdu rows only:

| Label source | Precision of "refusal" | Recall | Cohen's κ | What its false refusals really were |
|---|---:|---:|---:|---|
| Judge 1, pre-registered label | 0.53 | 0.86 | 0.52 | 42 non-responsive, 9 answers |
| Judge 1, echo-corrected | 0.63 | 0.86 | 0.63 | 24 non-responsive, 9 answers |
| Judge 2 (rubric) | 0.60 | 0.86 | 0.60 | 19 non-responsive, 19 answers |

Paired change against unsteered (36 families):

| Arm | Real refusals of harmful prompts | Answers toward harmful requests | Benign prompts answered |
|---|---:|---:|---:|
| pooled | 13 → 19 (+16.7 pp, CI +2.8 to +33.3, p = 0.07) | 6 → 3 (-8.3 pp, CI -19.4 to +2.8, p = 0.38) | 29 → 27 (-5.6 pp, CI -19.4 to +8.3, p = 0.69) |
| residualized | 13 → 19 (+16.7 pp, CI +2.8 to +33.3, p = 0.07) | 6 → 3 (-8.3 pp, CI -19.4 to +2.8, p = 0.38) | 29 → 28 (-2.8 pp, CI -13.9 to +8.3, p = 1) |
| orthogonal_null | 13 → 15 (+5.6 pp, CI +0.0 to +13.9, p = 0.5) | 6 → 5 (-2.8 pp, CI -13.9 to +8.3, p = 1) | 29 → 27 (-5.6 pp, CI -19.4 to +8.3, p = 0.69) |

What this shows:

- Of the 108 Roman-Urdu responses judge 1 called refusals, 51 (47 %) were not refusals on reading.
- Benign prompts: the judge reported 25 refusals across the four arms; the reading found 0. What the judge calls over-refusal in Roman Urdu is garbled or looping output.
- Harmful prompts: the judge credits the pooled vector with +5 refusals and the control with +4; the reading finds +6 and +2. With 36 families neither difference is statistically secure.

### 7.6 What else was tested

- **Numerical fidelity.** float16 on the T4 against a float32 reference; padding invariance; SafeTune's
  vectors against an independent activation capture (cosine 1.000000); save-and-reload of the vectors gives
  byte-identical generations.
- **Steering sign.** Confirmed with a teacher-forced refusal margin rather than keyword counts, at three layers.
- **A control that was wrong.** Our first control, a vector from shuffled labels, turned out to be an
  anti-refusal vector (cosine −0.59 to −0.81 with the refusal direction). It was replaced before the test.
- **Judge selection.** Three candidate signals were compared on 72 outputs before the experiment. The winner
  looked good there (κ = 0.94) and still failed on Roman Urdu at scale; that check contained too few
  Roman-Urdu responses.
- **Release check.** In a fresh GPU session the released package alone (vectors, manifest and loader, with none of this project's code importable) reproduced 144 of 144 logged responses byte for byte.

### 7.7 Limitations

- **No human validation.** Prompts are unreviewed; labels come from model judges and an LLM agent's reading.
  The reading was only partly blind and is reported as a diagnostic, not as ground truth.
- **Small.** 36 test families. The script gap is far outside the noise; the steering comparisons are not.
- **One model, one seed, one Roman-Urdu spelling convention, 64-token responses, single-turn, non-adversarial.**
- **A Roman-Urdu non-refusal is usually not a harmful answer.** Of 36 unsteered responses to
  harmful Roman-Urdu prompts, 13 refused, 6 moved toward the request and 17 were
  echoes, loops or misreadings. The model is also weaker at harmless Roman-Urdu questions (50.0 %
  correct vs 87.5 % in Urdu script). The safety gap and the competence gap are entangled, and this
  study cannot separate them.
- **Post hoc analyses** (echo correction, response reading, utility reading, exploratory grid) were designed
  after seeing test outputs. They are labelled as such everywhere and never replace the pre-registered results.

## 8. With more credits: our approach, before and after results

**Before and after, so far.** Frozen test set, 36 unseen intent families, steering at layer 18,
ρ = 0.1. Total spent: $0 (free Kaggle T4).

| Metric | Before (unsteered) | After: pooled vector | After: residualized vector | Control vector |
|---|---:|---:|---:|---:|
| Harmful requests refused, Urdu script (judge) | 100.0 % | 100.0 % | 100.0 % | 97.2 % |
| Harmful requests refused, Roman Urdu (judge) | 47.2 % | 61.1 % | 63.9 % | 58.3 % |
| Roman-Urdu responses flagged unsafe (judge) | 27.8 % | 27.8 % | 27.8 % | 22.2 % |
| Benign requests judged refused (lower is better) | 6.9 % | 13.9 % | 9.7 % | 4.2 % |
| Invalid output (empty or looping) | 1.4 % | 1.4 % | 1.0 % | 1.4 % |
| Utility, 48 factual questions (pattern score) | 68.8 % | 72.9 % | 75.0 % | not measured |
| Utility on reading (post hoc) | 35 of 48 | 36 of 48 | 36 of 48 | not measured |
| Real refusals, Roman Urdu, on reading (post hoc) | 13 of 36 | 19 of 36 | 19 of 36 | 15 of 36 |
| Answers toward the harmful request, Roman Urdu, on reading (post hoc) | 6 of 36 | 3 of 36 | 3 of 36 | 5 of 36 |

Read together: steering moves the judged Roman-Urdu refusal rate up, a control vector moves it almost as
much, and judged refusals of benign prompts rise past the pre-registered budget (on reading, those are
garbled answers rather than refusals). On reading, the gain in real refusals is modest and not statistically
secure at this sample size, and the residualized vector is indistinguishable from the pooled one. We do not
claim that the steered model is meaningfully safer; we claim that the gap is real, that this repair does not
close it, and that the usual way of measuring it is unreliable in Roman Urdu.

**With more credits**, in order of value:

1. **Human labels.** Two native Urdu speakers labelling the 2,016 test responses (refusal / answer /
   non-responsive) and reviewing the 576 prompts with the pack already prepared. This would turn the
   reading in 7.5 into a result. The cost is annotator time, not GPU time.
2. **Statistical power.** Four times as many intent families, to resolve steering effects of the size seen
   here: about 8,400 generations plus judging, three to four hours on one T4.
3. **Other models.** The same protocol on Tiny Aya Global and on a second model family, to see whether the
   weak Roman-Urdu harm signal is specific to Fire or a property of romanized text in training data.
4. **Fix the cause rather than steer around it.** The mechanism result says the model forms a harm signal
   half as strong for Roman Urdu; a fixed added vector cannot make it recognise what it does not recognise.
   A small LoRA on romanized refusal data, or a per-script strength schedule, evaluated on the same frozen
   test with human labels.
5. **Longer responses and adversarial prompts.** With 256 tokens some non-responsive Roman-Urdu answers may
   turn into real compliance; also a second Roman-Urdu spelling convention.

The expected "after" for items 2–5 is unknown, which is the reason to run them; details and cost estimates
are in `docs/with_more_credits.md`.

## 9. Teammates tagged

Solo submission: **Muhammad Ahmad (@ahmadrrrtx)**.

## Reproducibility

Released: the steering-vector package with a standalone loader, the dataset with reviewer pack and
evaluation logs, and a replay demo of the recorded outputs. [The repository](https://github.com/ahmadrrrtx/scriptshield) contains the
protocol with its dated amendments, every decision record, the experiment log and 211 unit tests
that run without a GPU. Base model revision, weight hashes, toolkit commits, dataset checksum, seeds and
decoding settings are recorded with every run. Three checks anyone can repeat: the unit tests; the
recomputation of every pre-registered number from the public logs; and, with a GPU and access to the base
model, the byte-for-byte reproduction of 144 logged responses from the released package alone.

## How this was built

This project was built with substantial help from an AI assistant (an LLM agent). Under the author's
direction it drafted the prompts, wrote much of the code and analysis, and did the response readings that
this article labels as agent readings. The author chose the research direction, approved the protocol and
the release, and is responsible for the content. Nothing here has been labelled by human annotators yet;
the author is a native Urdu speaker and will review the prompts, and the dataset's review status will be
updated when that is done.

## Licences

Steering vectors, dataset and evaluation logs: CC-BY-NC 4.0 (the vectors derive from the Tiny Aya weights,
and their use is also subject to the Cohere Labs Acceptable Use Policy). Code: MIT. The Lexsi toolkits are
used under the Lexsi Labs Source Available Licence and are not redistributed.
