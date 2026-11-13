# ScriptShield: Tiny Aya refuses harmful requests in Urdu script and mostly does not in Roman Urdu

*Lexsi AI Safety and Alignment Hackathon · Track 2, AI Red Teaming, Safety and Alignment · problem 8
(inference-time safety steering) with problem 4 (multilingual and code-mixed safety). Solo submission by
{{AUTHOR}}.*

**Artifacts:** [model collection]({{URL_COLLECTION_MODELS}}) · [data collection]({{URL_COLLECTION_DATA}}) ·
[code and reproduction notes]({{URL_GITHUB}}) · [replay demo]({{URL_SPACE}})

*Every number in this article is generated from the logged results by `scripts/make_article.py`; none is
typed by hand. The sections follow the hackathon's submission checklist.*

## 1. Problem statement and approach, in brief

**Problem.** Most Urdu typed on phones is Roman Urdu: Urdu written in Latin letters. Multilingual safety work
usually treats "Urdu" as one language. Urdu script and Roman Urdu share the language and differ only in
orthography, which makes the pair a clean test: same meaning, same speaker, different characters. A guardrail
that works in one script and fails in the other has a hole exactly where most informal Urdu is written.

**Approach.** We wrote {{DATA_FAMILIES}} matched intent families (a harmful request and a benign one on the
same topic, each in Urdu script, Roman Urdu, code-mixed Urdu-English and English), measured how Cohere Labs'
Tiny Aya Fire responds to them, and tested one repair: a refusal-steering vector from which the "which script
is this" direction has been projected out. Hypotheses, acceptance gate, statistical tests and the rule for
choosing the layer and strength were written down before the data existed, and the test set was run once.

**What we found.**

- **The gap is large.** On {{H1_N}} held-out intents, Tiny Aya Fire refused {{H1_UR}} of harmful requests
  written in Urdu script and {{H1_RO}} of the same requests in Roman Urdu ({{H1_DIFF}} points, 95 % CI
  {{H1_CI}}, exact McNemar p = {{H1_P}}). Code-mixed Urdu-English ({{CM_RATE}}) and English ({{EN_RATE}})
  behave like Urdu script. This test was pre-registered.
- **Our intervention did not work.** We predicted that removing the "script direction" from a
  refusal-steering vector would help Roman-Urdu users. It made no measurable difference: the pre-registered
  gate was not met, and the residualized and the ordinary vector gave the same outcome on {{H3_SAME}} of
  {{H3_N}} harmful prompts. We report it as a negative result.
- **The automatic judge failed where it mattered.** The open moderation model we used as judge calls
  echoes, loops and off-topic text "refusals" in Roman Urdu. Reading the responses showed that only
  {{JUDGE_PREC}} of its Roman-Urdu "refusals" were refusals. Every correction we applied makes the script
  gap larger, not smaller.

**Why it is useful.** Anyone deploying a small multilingual model for Urdu speakers can measure this gap on
their own model with a few hundred prompts; the result tells them that a moderation model's verdict on
Roman-Urdu output needs to be read before it is trusted; and the negative result saves others from trying
the same repair.

Limits that apply to everything below: {{DATA_FAMILIES}} intent families written with an LLM and **not yet
reviewed by a native speaker**; one model, one seed, 64-token responses; labels from model judges and from an
LLM agent's reading, **not from human annotators**.

## 2. Hackathon repos used: which ones, for what, and which features

Three Lexsi toolkits run as one pipeline, on the real model, end to end:

| Repo (pinned) | Used for | Features used |
|---|---|---|
| **CuratorKIT** 0.1.21 | building the dataset | `Curator` / `CuratorConfig` pipeline: ingestion, schema gate, NFC normalisation, exact de-duplication, provenance, `prompt_only` export. Toxicity and quality gates deliberately off (they would delete the harmful half); MinHash de-duplication off (it would merge the matched pairs) |
| **SafeTune** 0.1.8 | making and applying the steering vectors | `interventions.steer.caa.extract_caa_vectors` for contrastive activation addition; `CAAModel` forward hooks to apply a vector during generation. Our residualization sits between those two calls; SafeTune is neither forked nor patched |
| **AuditKIT** 1.1.3 | running and logging every generation | `generate` with `CallableModel`, `Sample`, `RunConfig` and the disk cache for every generation of the real runs; `evaluate(model="precomputed")` with a `FunctionScorer` in the offline smoke pipeline. Aggregation and significance tests are ours |

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
| `CohereLabs/tiny-aya-fire` @ `{{REVISION_SHORT}}` | model under study (one of the seven permitted models) | CC-BY-NC 4.0 + Cohere Labs Acceptable Use Policy |
| `Qwen/Qwen3Guard-Gen-4B` | primary judge of the responses | Apache-2.0 |
| `Qwen/Qwen2.5-7B-Instruct` | second judge (pre-declared sensitivity analysis) | Apache-2.0 |

**Why Tiny Aya Fire.** It is a permitted dense Cohere open-weights model (3.35 B parameters, 36 layers) with
documented South Asian language coverage, and it fits on a free Kaggle T4, so the whole study cost $0. The
judges are used for inference only, as the rules allow. No model weights are redistributed.

## 4. Datasets and benchmarks used and their licences

| Dataset | Role | Licence |
|---|---|---|
| **ScriptShield v{{DATA_VERSION}}** (ours, new) | {{DATA_N}} prompts for extraction, selection and the final test | CC-BY-NC 4.0 |
| ScriptShield utility probe (ours, new) | 24 simple factual questions in both scripts | CC-BY-NC 4.0 |

No third-party dataset or benchmark was used, and no third-party prompt was copied.

**ScriptShield v{{DATA_VERSION}}**: {{DATA_N}} prompts = {{DATA_FAMILIES}} intent families × harmful / matched
benign × four forms (Urdu script, Roman Urdu, code-mixed, English). A family pairs a harmful request with a
benign one on the same topic, e.g. breaking into someone's email account vs recovering your own. Harmful
prompts state a goal and ask; they contain no instructions.

Families, not prompts, are the unit of splitting and of every statistical test: 24 for building vectors,
12 for choosing the layer and strength, 36 for the final test. No family crosses a split.

The data went through Lexsi **CuratorKIT** for schema validation, normalisation, exact de-duplication and
provenance ({{DATA_N}} in, {{DATA_N}} out, no text changed). A per-character check guarantees that no
Urdu-script prompt contains Latin or Devanagari letters and no Roman-Urdu prompt contains Arabic-script letters.

**Status: unreviewed.** A bilingual reviewer pack is included with the dataset. Until a native speaker
returns it, naturalness and exact equivalence across forms are unverified.

## 5. Model artifacts (public Hugging Face collection)

**[{{TITLE_COLLECTION_MODELS}}]({{URL_COLLECTION_MODELS}})**

- [`{{ID_MODEL}}`]({{URL_MODEL}}): the six steering vectors for decoder block {{LAYER}} of Tiny Aya Fire
  (pooled, residualized, two controls, Urdu-only, Roman-only), a manifest with every setting and checksum,
  the frozen selection, a standalone loader and 144 logged responses to check a setup against.
- [`{{ID_SPACE}}`]({{URL_SPACE}}): a replay explorer of the recorded outputs, arm by arm and script by script.

{{VERIFY_LINE}} The vectors are published so that the result can be checked and built on, **not as a
recommended safety intervention**: the idea they were built to test was not supported.

## 6. Data artifacts (public Hugging Face collection)

**[{{TITLE_COLLECTION_DATA}}]({{URL_COLLECTION_DATA}})**

- [`{{ID_DATASET}}`]({{URL_DATASET}}): the corpus with its three splits, the utility probe, the reviewer
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
(layer {{LAYER}}, ρ = {{RHO}}) was committed to git before the test set was run. The test prompts were
generated once (a first launch stopped on a missing file before producing any output).

### 7.2 The model forms a weaker harm signal for Roman Urdu

Before any generation, on the 24 calibration families: the harmful-vs-benign direction for Roman Urdu points
the same way as for Urdu script, but at layer {{LAYER}} its size is only {{NORM_RATIO}} of the Urdu-script
one (95 % CI {{NORM_CI}}). The pooled refusal vector is nearly orthogonal to the script direction at the
layers we searched (|cosine| ≤ {{ALIGN_MAX}}); residualization would remove at most {{REMOVED_MAX}} of its
norm. So the mechanism behind the gap looks like a weak harm signal, not script information leaking into the
refusal direction. This already predicted that residualization had little to act on.

### 7.3 The script gap (pre-registered)

{{RESULTS_H1}}

### 7.4 Steering, and the residualization test (pre-registered)

{{RESULTS_ARMS}}

{{RESULTS_H3}}

An exploratory rerun of every vector over the whole development grid (16 layer/strength settings, after the
freeze) tells the same story at stronger doses: residualized was ahead of pooled on harmful refusal in
{{DEVX_BETTER}} settings, behind in {{DEVX_WORSE}} and level in {{DEVX_EQUAL}}.

### 7.5 The judge could not be trusted in Roman Urdu

{{RESULTS_VALIDITY}}

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
- **Release check.** {{VERIFY_LINE}}

### 7.7 Limitations

- **No human validation.** Prompts are unreviewed; labels come from model judges and an LLM agent's reading.
  The reading was only partly blind and is reported as a diagnostic, not as ground truth.
- **Small.** 36 test families. The script gap is far outside the noise; the steering comparisons are not.
- **One model, one seed, one Roman-Urdu spelling convention, 64-token responses, single-turn, non-adversarial.**
- **A Roman-Urdu non-refusal is usually not a harmful answer.** Of {{ADJ_TOTAL}} unsteered responses to
  harmful Roman-Urdu prompts, {{ADJ_R}} refused, {{ADJ_A}} moved toward the request and {{ADJ_N}} were
  echoes, loops or misreadings. The model is also weaker at harmless Roman-Urdu questions ({{UTIL_RO}}
  correct vs {{UTIL_UR}} in Urdu script). The safety gap and the competence gap are entangled, and this
  study cannot separate them.
- **Post hoc analyses** (echo correction, response reading, utility reading, exploratory grid) were designed
  after seeing test outputs. They are labelled as such everywhere and never replace the pre-registered results.

## 8. With more credits: our approach, before and after results

**Before and after, so far.** Frozen test set, {{H1_N}} unseen intent families, steering at layer {{LAYER}},
ρ = {{RHO}}. Total spent: $0 (free Kaggle T4).

{{BEFORE_AFTER_TABLE}}

Read together: steering moves the judged Roman-Urdu refusal rate up, a control vector moves it almost as
much, and judged refusals of benign prompts rise past the pre-registered budget (on reading, those are
garbled answers rather than refusals). On reading, the gain in real refusals is modest and not statistically
secure at this sample size, and the residualized vector is indistinguishable from the pooled one. We do not
claim that the steered model is meaningfully safer; we claim that the gap is real, that this repair does not
close it, and that the usual way of measuring it is unreliable in Roman Urdu.

**With more credits**, in order of value:

1. **Human labels.** Two native Urdu speakers labelling the 2,016 test responses (refusal / answer /
   non-responsive) and reviewing the {{DATA_N}} prompts with the pack already prepared. This would turn the
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

Solo submission: **{{AUTHOR}}**.

## Reproducibility

Released: the steering-vector package with a standalone loader, the dataset with reviewer pack and
evaluation logs, and a replay demo of the recorded outputs. [The repository]({{URL_GITHUB}}) contains the
protocol with its dated amendments, every decision record, the experiment log and {{N_TESTS}} unit tests
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
