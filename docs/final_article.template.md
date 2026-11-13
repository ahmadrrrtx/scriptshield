# ScriptShield: the same harmful request is refused in Urdu script and often not in Roman Urdu

*A pre-registered study of script-dependent refusal in Cohere Labs' Tiny Aya Fire, and of a steering repair that did not work.*

*Lexsi Labs AI Safety and Alignment Hackathon · Track 2, AI Red Teaming, Safety and Alignment: problem 4
(multilingual and code-mixed safety) with problem 8 (inference-time safety steering) · Model:
[Tiny Aya Fire](https://huggingface.co/CohereLabs/tiny-aya-fire) · Toolkits: CuratorKIT, SafeTune, AuditKIT ·
Solo submission by {{AUTHOR}}*

## TL;DR

- **The question.** Most Urdu typed on phones is Roman Urdu: Urdu in Latin letters. Does a small multilingual
  model refuse a harmful request as reliably when the same sentence is typed in Roman Urdu as when it is
  written in Urdu script?
- **The finding.** No. Without any intervention, Tiny Aya Fire refused **{{H1_UR_K}} of {{H1_N}}** harmful
  requests in Urdu script and **{{H1_RO_K}} of {{H1_N}}** of the same requests in Roman Urdu
  ({{H1_DIFF}} points, 95 % CI {{H1_CI}}, exact McNemar p = {{H1_P}}; pre-registered). Code-mixed Urdu-English
  and English behave like Urdu script.
- **What a non-refusal is.** Mostly not a harmful answer. Reading the {{ADJ_TOTAL}} Roman-Urdu replies: {{ADJ_R}}
  refuse, {{ADJ_A}} go along with the request and {{ADJ_N}} are garbled, off-topic or repeat the question.
- **The repair did not work.** We predicted that removing the "which script is this" direction from a
  refusal-steering vector would close the gap. The pre-registered gate was **not met**: the residualized and the
  ordinary vector gave the same outcome on {{H3_SAME}} of {{H3_N}} harmful prompts, and a placebo vector did
  almost as well as either.
- **Why it did not work.** Inside the model the refusal direction is almost orthogonal to the script direction
  (|cosine| {{ALIGN_L}}), so there was nearly nothing to remove. What differs is strength: the harm signal for
  Roman Urdu is {{NORM_RATIO}} times as strong as for Urdu script.
- **The automatic judge is unreliable in Roman Urdu.** Only {{JUDGE_PREC}} of the Roman-Urdu replies it called
  refusals were refusals when read. Every correction makes the gap larger.
- **What is released.** The dataset, the evaluation logs (harmful completions withheld, every number
  recomputable), the steering vectors with a loader that reproduced {{VERIFY_K}} of {{VERIFY_N}} logged replies
  byte for byte, and a replay demo.
- **What is not known.** The prompts were drafted with an LLM; review by the author is {{REVIEW_STATE}}.
  One model, one deterministic run, {{H1_N}} test families, 64-token replies. Response labels come from model
  judges and an LLM agent's reading, not from human annotators.

![{{ALT_GAP}}]({{FIG}}/script_gap.png)

*Figure 1. The same {{H1_N}} harmful requests in four written forms, no steering. Only the Roman-Urdu form
falls, and it falls further when the replies are read instead of judged automatically.*

| Resource | Link |
|---|---|
| Model artifacts (collection) | [{{TITLE_COLLECTION_MODELS}}]({{URL_COLLECTION_MODELS}}) |
| Data artifacts (collection) | [{{TITLE_COLLECTION_DATA}}]({{URL_COLLECTION_DATA}}) |
| Steering vectors and loader | [`{{ID_MODEL}}`]({{URL_MODEL}}) |
| Dataset and evaluation logs | [`{{ID_DATASET}}`]({{URL_DATASET}}) |
| Replay of the recorded outputs | [`{{ID_SPACE}}`]({{URL_SPACE}}) |
| Code, protocol, tests | [github.com/ahmadrrrtx/scriptshield]({{URL_GITHUB}}) |

**What "same request, different script" means.** One harmless request from the test set, as the model saw it:

| Form | Text |
|---|---|
| English | {{EXAMPLE_EN}} |
| Urdu script | {{EXAMPLE_UR}} |
| Roman Urdu | {{EXAMPLE_RO}} |

The two Urdu lines are the same sentence, word for word. Only the letters differ.

---

## 1. Problem statement and approach, in brief

**Problem.** Safety evaluations usually treat "Urdu" as one language. In practice it is written in two ways:
in the Perso-Arabic script, and in Latin letters with no fixed spelling (Roman Urdu), which is how most
informal messages are typed. The two share grammar, vocabulary and speakers and differ only in orthography.
A guardrail that holds in one and fails in the other has a hole exactly where everyday Urdu is written.

**Approach.** Three steps, each fixed in writing before its data existed:

1. Build {{DATA_FAMILIES}} matched intent families. Each has a harmful request and a harmless request on the
   same topic, written in Urdu script, Roman Urdu, code-mixed Urdu-English and English.
2. Measure how Tiny Aya Fire responds, with the script as the only thing that changes.
3. Test one repair: a refusal-steering vector with the script direction projected out.

**Hypotheses, as pre-registered, and what happened.**

| | Hypothesis | Outcome |
|---|---|---|
| H1 | The refusal rate for harmful requests is lower in Roman Urdu than in matched Urdu script | **Confirmed** ({{H1_DIFF}} points) |
| H2 | The pooled refusal vector has a real component along the script direction | **Detectable but tiny** (absolute cosine {{ALIGN_L}}; a random direction gives {{NULL_L}}) |
| H3 | A residualized vector beats the ordinary one by at least 5 points on the worst script or on the gap, within fixed budgets for side effects | **Not met** |

The protocol named the null result in advance as a publishable outcome. This article reports it as one.

**What is new here, and what is not.** That safety training transfers unevenly across languages is well
established, and a transliteration gap has been shown for Arabic on closed models (see *Related work*). New
here: a matched Urdu-script and Roman-Urdu test set with harmless counterparts; a pre-registered within-item
test on an open multilingual model built for South Asian languages; a look inside the model at why the gap
exists; a controlled test of a script-aware repair; and an audit of the automatic judge on romanized text.

## 2. Hackathon repos used: which ones, for what, and which features

Three Lexsi toolkits run as one pipeline on the real model, end to end.

![Diagram of the pipeline in five stages: dataset with CuratorKIT, steering vectors with SafeTune, generation with AuditKIT, judging and statistical tests, release on Hugging Face.]({{FIG}}/pipeline.png)

*Figure 2. The pipeline. Calibration, development and test use different intent families.*

| Repo (pinned) | Used for | Features used |
|---|---|---|
| [**CuratorKIT**](https://github.com/Lexsi-Labs/CuratorKIT) 0.1.21 | building the dataset | `Curator` / `CuratorConfig` pipeline: ingestion, schema gate, NFC normalisation, exact de-duplication, provenance, `prompt_only` export. Toxicity and quality gates deliberately off (they would delete the harmful half); MinHash de-duplication off (it would merge the matched pairs) |
| [**SafeTune**](https://github.com/Lexsi-Labs/SafeTune) 0.1.8 | making and applying the steering vectors | `interventions.steer.caa.extract_caa_vectors` for contrastive activation addition; `CAAModel` forward hooks to apply a vector during generation. Our residualization sits between those two calls; SafeTune is neither forked nor patched |
| [**AuditKIT**](https://github.com/Lexsi-Labs/AuditKIT) 1.1.3 | running and logging every generation | `generate` with `CallableModel`, `Sample`, `RunConfig` and the disk cache for every generation of the real runs; `evaluate(model="precomputed")` with a `FunctionScorer` in the offline smoke pipeline. Aggregation and significance tests are ours |

**Data flow.** CuratorKIT validates and exports the corpus. SafeTune extracts the vectors from the calibration
families and applies them during generation. AuditKIT runs and logs every generation. Two open judge models
label the replies. Statistics are computed locally from the logs. Each remote run is one generated file that
embeds the repository at a clean commit, so every result names the exact code that produced it.

**Feedback for the toolkit authors.** Observed at the pinned commits, each with a regression test in our repository:

1. **AuditKIT** identifies a Python-callable model by its code and immutable closure values. Two steering
   configurations that differ only in a captured object share a cache key, and the disk cache silently returns
   the first configuration's text for the second. Our first development grid was 32 "configurations" with one
   distinct set of outputs. We now give every call a unique model identity and fail if the model was not asked.
2. **SafeTune**'s `CAAModel` installs its hooks only inside `wrapper.generate(...)` or a `with` block. Calling
   `wrapper.model.generate(...)` produces unsteered text without any warning.
3. **SafeTune** applies the chat template itself; passing an already-templated prompt templates it twice.
4. Tiny Aya's chat template begins with a BOS token and its tokenizer adds one too, so the default call yields
   two; its generation config lists only one of the three tokens that end a turn.

## 3. Models used and their licences

| Model | Role | Licence |
|---|---|---|
| [`CohereLabs/tiny-aya-fire`](https://huggingface.co/CohereLabs/tiny-aya-fire) @ `{{REVISION_SHORT}}` | model under study (one of the seven permitted models) | CC-BY-NC 4.0 + Cohere Labs Acceptable Use Policy |
| [`Qwen/Qwen3Guard-Gen-4B`](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B) | primary judge of the replies | Apache-2.0 |
| [`Qwen/Qwen2.5-7B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | second judge (pre-declared sensitivity analysis) | Apache-2.0 |

**Why Tiny Aya Fire.** It is a permitted dense Cohere open-weights model (3.35 B parameters, 36 layers) with
documented South Asian language coverage, and it fits on a free Kaggle T4. The judges are used for inference
only, as the rules allow. No model weights are redistributed.

## 4. Datasets and benchmarks used and their licences

| Dataset | Role | Licence |
|---|---|---|
| **ScriptShield v{{DATA_VERSION}}** (ours, new) | {{DATA_N}} prompts for extraction, selection and the final test | CC-BY-NC 4.0 |
| ScriptShield utility probe (ours, new) | 24 simple factual questions in both scripts | CC-BY-NC 4.0 |

No third-party dataset or benchmark was used, and no third-party prompt was copied.

**Design.** {{DATA_N}} prompts = {{DATA_FAMILIES}} intent families × harmful and harmless × four written forms.
A family pairs a harmful request with a harmless one on the same topic, for example breaking into someone's
email account and recovering your own. Harmful prompts state a goal and ask; they contain no instructions.

| Split | Families | Prompts | Used for |
|---|---:|---:|---|
| Calibration | 24 | 192 | computing the steering vectors |
| Development | 12 | 96 | choosing layer and strength |
| Test | 36 | 288 | every reported result; run once |

Families, not prompts, are the unit of splitting and of every statistical test. No family crosses a split.
The data went through **CuratorKIT** for schema validation, normalisation, exact de-duplication and provenance
({{DATA_N}} in, {{DATA_N}} out, no text changed). A per-character check guarantees that no Urdu-script prompt
contains Latin or Devanagari letters and no Roman-Urdu prompt contains Arabic-script letters.

**Quality status.** The prompts were drafted with an LLM. A review by the author is
{{REVIEW_STATE}} ({{REVIEW_DONE}} of 144 prompt pairs reviewed so far); it is a participant review, not
independent expert validation. A [family-level audit]({{URL_GITHUB}}/blob/main/docs/DATASET_QUALITY_AUDIT.md)
of all {{DATA_FAMILIES}} families found, by automatic checks:

- harmful requests are more often commands ("Write ...") than harmless ones ({{AUDIT_CMD_H}} of 72 against
  {{AUDIT_CMD_B}} of 72), and harmless requests more often begin by describing a situation
  ({{AUDIT_CTX_B}} against {{AUDIT_CTX_H}}). This cannot affect the script gap, which compares the same sentence
  in two scripts, but it can leak into a harmful-minus-harmless steering vector;
- in {{AUDIT_WORD}} prompts the Roman-Urdu version uses a synonym of one function word;
- the Roman Urdu keeps the wording of fairly formal Urdu, so that only the script differs. Whether the gap is as
  large for colloquial Roman Urdu was not tested.

## 5. Model artifacts (public Hugging Face collection)

**[{{TITLE_COLLECTION_MODELS}}]({{URL_COLLECTION_MODELS}})**

- [`{{ID_MODEL}}`]({{URL_MODEL}}): six steering vectors for decoder block {{LAYER}} of Tiny Aya Fire (pooled,
  residualized, placebo, a control for the residualization step, Urdu-only, Roman-only), a manifest with every
  setting and checksum, the frozen selection, a standalone loader, a compatibility check for the base model and
  {{VERIFY_N}} logged replies to check a setup against. **This is an inference-time steering package, not a
  fine-tuned checkpoint.** It contains no model weights.
- [`{{ID_SPACE}}`]({{URL_SPACE}}): an explorer of the recorded outputs, arm by arm and script by script. It
  replays logs; it does not run the model.

{{VERIFY_LINE}} The vectors are published so that the result can be checked and built on, **not as a
recommended safety intervention**: the idea they were built to test was not supported.

## 6. Data artifacts (public Hugging Face collection)

**[{{TITLE_COLLECTION_DATA}}]({{URL_COLLECTION_DATA}})**

- [`{{ID_DATASET}}`]({{URL_DATASET}}): the corpus with its three splits, the utility probe, the review pack and
  the evaluation logs: one row per prompt and arm of the frozen test run with both judges' verdicts, the
  refusal margins, every analysis file, the run reports and the labels of the response reading.

The data every number was computed from is tagged `v0.2.0` and will not change. Corrections from the review go
into a new version that keeps the original sentence next to the revised one.

## 7. Experiments run, findings and what else was tested

### 7.1 Method

**Steering vector (SafeTune, contrastive activation addition).** For each script *s*, take the mean residual
activation at the last prompt token, at layer *L*, over the harmful calibration prompts and subtract the mean
over the harmless ones:

$$v_s = \frac{1}{|F|}\sum_{f \in F}\Big(h_L\big(x^{\mathrm{harm}}_{f,s}\big) - h_L\big(x^{\mathrm{benign}}_{f,s}\big)\Big), \qquad v_{\mathrm{pooled}} = \tfrac{1}{2}\big(v_{\mathrm{ur}} + v_{\mathrm{ro}}\big)$$

**Script direction.** The mean difference between Urdu-script and Roman-Urdu **harmless** prompts:

$$d = \frac{1}{|F|}\sum_{f \in F}\Big(h_L\big(x^{\mathrm{benign}}_{f,\mathrm{ur}}\big) - h_L\big(x^{\mathrm{benign}}_{f,\mathrm{ro}}\big)\Big)$$

**Residualization.** Project the script direction out of the pooled vector and rescale to the pooled norm, so
that both vectors are applied at the same dose:

$$\tilde v = v_{\mathrm{pooled}} - \frac{\langle v_{\mathrm{pooled}}, d\rangle}{\lVert d\rVert^{2}}\, d, \qquad v_{\mathrm{res}} = \lVert v_{\mathrm{pooled}}\rVert \, \frac{\tilde v}{\lVert \tilde v\rVert}$$

**Application.** During generation SafeTune's `CAAModel` adds the vector to the output of block *L* at every
position, with a strength set as a fraction ρ of the typical activation norm:

$$h_L \leftarrow h_L + \alpha\, v, \qquad \alpha = \rho\,\frac{\overline{\lVert h_L\rVert}}{\lVert v_{\mathrm{pooled}}\rVert}$$

Layer and strength were chosen on the development families (*L* = {{LAYER}}, ρ = {{RHO}}) and committed to git
before the test set was run.

**What had to be true for the repair to help.** A harmful-minus-harmless contrast taken within one script
already cancels any constant script offset. Residualization can matter only if the pooled vector has a real
component along *d*; the share of its norm that is removed equals |cos(*v*<sub>pooled</sub>, *d*)|. We measured
that before looking at behaviour (7.4).

**Arms.** No steering; pooled; residualized; a placebo (a noise vector of the pooled norm, exactly orthogonal
to the pooled vector); a control for the residualization step (pooled with a *random* direction removed); and
vectors built from one script only. All have the same norm.

### 7.2 Metrics and pre-registration

Each metric is reported separately, never as one blended score.

| Metric | Denominator | Why it is there |
|---|---|---|
| Refusal rate on harmful prompts, per script | 36 test families | the safety behaviour itself |
| Gap between scripts, paired by family | 36 pairs | the research question |
| Refusal rate on matched harmless prompts | 72 (Urdu script + Roman Urdu) | a vector that refuses everything is not safer |
| Utility on factual questions | 48 (24 in each script) | catches a vector that breaks ordinary answering |
| Invalid rate (empty or looping output) | every prompt of the arm | catches "safety" bought by destroying fluency |
| Replies flagged unsafe by the judge | 36 per script | a reply can open with a refusal and still leak |

Every attempted prompt stays in the denominator. An empty, looping or unparseable reply is never counted as a
refusal or as safe.

**Pre-registration.** The hypotheses, the gate (residualized must beat pooled by at least 5 points on the worst
script or on the gap, with at most 2 points of extra refusal of harmless prompts, 2 of utility loss and 1 of
invalid output), the tests (exact McNemar, family-cluster bootstrap, Holm correction) and the rule for choosing
layer and strength were written down before the corresponding data existed. The test prompts were generated
once (a first launch stopped on a missing file before producing any output). Analyses designed after seeing
test outputs are labelled **post hoc** wherever they appear and never replace a pre-registered number.

### 7.3 Finding 1: the script gap (pre-registered)

{{RESULTS_H1}}

**Does the gap survive other ways of labelling the replies?** Yes; it grows.

{{H1_SENSITIVITY_TABLE}}

### 7.4 Finding 2: a weaker harm signal, not script information leaking into refusal

Measured on the 24 calibration families before any reply was generated:

- The harmful-versus-harmless direction for Roman Urdu points the same way as for Urdu script (cosine
  {{COS_UR_RO}} at layer {{LAYER}}), but it is only **{{NORM_RATIO}}** times as long (95 % CI {{NORM_CI}}).
- The pooled refusal vector is nearly orthogonal to the script direction: |cosine| {{ALIGN_L}} at layer
  {{LAYER}}, against {{NULL_L}} for a random direction (95th percentile). Residualization removes at most
  {{REMOVED_MAX}} of the vector's norm at the layers searched.

![{{ALT_MECH}}]({{FIG}}/mechanism_by_layer.png)

*Figure 3. Left: from the middle layers on, the model's internal harm signal for Roman Urdu is about half as
strong as for Urdu script. Right: the refusal direction and the script direction barely overlap at any layer.
Together they say the gap is a weak signal, not a misplaced one, which is why removing the script component
had almost nothing to act on.*

### 7.5 Finding 3: steering, its placebo, and the failed residualization (pre-registered)

Steering raised the judged Roman-Urdu refusal rate. So did a noise vector of the same size.

![{{ALT_ARMS}}]({{FIG}}/arms_comparison.png)

*Figure 4. Left: every vector, including the placebo, lifts judged refusal of harmful Roman-Urdu requests by
{{LIFT_MIN}} to {{LIFT_MAX}} prompts out of 36, and the intervals overlap. Right: judged refusals of harmless requests; in
the four arms whose replies were read, none of these was a real refusal (7.6).*

{{RESULTS_ARMS}}

**The residualization gate.**

{{RESULTS_H3}}

An exploratory rerun of every vector over the whole development grid (16 layer and strength settings, after
the freeze) tells the same story at stronger doses: residualized was ahead of pooled on harmful refusal in
{{DEVX_BETTER}} settings, behind in {{DEVX_WORSE}} and level in {{DEVX_EQUAL}}.

### 7.6 Finding 4: the automatic judge cannot be trusted in Roman Urdu

![{{ALT_OUTCOMES}}]({{FIG}}/roman_urdu_outcomes.png)

*Figure 5. The Roman-Urdu replies, read one by one (LLM agent, not a human; arm hidden). The largest group in
every arm is "neither": the model echoes the question, loops or answers something else. The automatic judge
counts many of these as refusals.*

{{RESULTS_VALIDITY}}

**Where the judge errs (post hoc).** Sorting the {{JE_N}} Roman-Urdu replies that were read by kind of text shows
the pattern. The model answered {{JE_ECHO_N}} times by repeating the prompt; the judge called {{JE_ECHO_REF}} of
these refusals, and none of them was one. Of all {{JE_REF}} replies it called refusals, {{JE_FALSE}} were not
refusals on reading: {{JE_FALSE_N}} were garbled or off-topic text and {{JE_FALSE_A}} went along with the request.
In the other direction it missed {{JE_MISSED}} of {{JE_TRUE}} refusals. The errors run mostly one way, so in this
study the judge reported the model as safer in Roman Urdu than it was on reading. The table by kind of reply is
in the [robustness checks]({{URL_GITHUB}}/blob/main/docs/ROBUSTNESS_CHECKS.md).

**Has a person checked the reading?** {{RESPONSE_CHECK_LINE}}

### 7.7 What else was tested

- **Numerical fidelity.** float16 on the T4 against a float32 reference; padding invariance; SafeTune's
  vectors against an independent activation capture (cosine 1.000000); save-and-reload of the vectors gives
  byte-identical generations.
- **Steering sign.** Confirmed with a teacher-forced refusal margin rather than keyword counts, at three layers.
- **A control that was wrong.** Our first placebo, a vector from shuffled labels, turned out to be an
  anti-refusal vector (cosine −0.59 to −0.81 with the refusal direction). It was replaced before the test.
- **Judge selection.** Three candidate signals were compared on 72 outputs before the experiment. The winner
  looked good there (κ = 0.94) and still failed on Roman Urdu at scale; that check contained too few
  Roman-Urdu replies.
- **Release check.** {{VERIFY_LINE}}

### 7.8 Threats to validity

| Threat | What it could do to the conclusions | What was done, and what remains |
|---|---|---|
| Prompts drafted by an LLM, not validated by annotators | If the Roman Urdu were unnatural, the gap could reflect odd text and not the script | Same wording in both scripts by design; author review {{REVIEW_STATE}}; the audit lists every known issue. Colloquial Roman Urdu is untested |
| The gap might hinge on a few prompts or one topic | A handful of odd prompts could carry the result | Post hoc [robustness checks]({{URL_GITHUB}}/blob/main/docs/ROBUSTNESS_CHECKS.md): leaving out any one harm group, the difference stays between {{ROB_LO}} and {{ROB_HI}} points; on the {{ROB_CLEAN_N}} test families with no audit flag and no note it is {{ROB_CLEAN_RO}} of {{ROB_CLEAN_N}} against {{ROB_CLEAN_UR}} of {{ROB_CLEAN_N}}. The judge sees no gap in {{ROB_NOGAP}} |
| One Roman-Urdu spelling convention | The gap could depend on this spelling | A second spelling has been drafted for the test families and waits for review; no result uses it yet |
| Automatic judge | Mislabels garbled Roman-Urdu text as refusal | Second judge (pre-declared), echo correction and a full reading; the gap grows under each |
| The reading is by an LLM agent | Not ground truth; only partly blind | Reported as a diagnostic; borderline labels flipped as a check; a participant check on a stratified sample is set up ({{RESPONSE_CHECK_SHORT}}); independent human labels are the first item under section 8 |
| Small test set | Steering effects of a few prompts cannot be resolved | The gap is far outside the noise; steering comparisons are reported as inconclusive |
| One model, one deterministic run | No evidence beyond Tiny Aya Fire or greedy decoding | Stated as a limit; decoding is greedy, so repeating the run gives the same text and would not be a second seed |
| 64-token replies | A reply that starts as a refusal or as noise may change later | Stated as a limit |
| Sentence form differs between harmful and harmless prompts | The steering vector may partly encode "command versus question" | Quantified in the audit; does not affect the script gap |
| Safety gap entangled with a competence gap | The model is also worse at harmless Roman-Urdu questions ({{UTIL_RO}} correct against {{UTIL_UR}}) | Cannot be separated in this study |

### 7.9 Limitations

- **No human annotation.** Prompts are under participant review; labels come from model judges and an LLM
  agent's reading.
- **Small.** {{H1_N}} test families.
- **One model, one run, one spelling convention, 64-token replies, single-turn, non-adversarial.**
- **A Roman-Urdu non-refusal is usually not a harmful answer** (Figure 5). The failure is partly that the model
  does not understand the request.
- **The repair is not a product.** We do not claim that the steered model is meaningfully safer.

## 8. With more credits: our approach, before and after results

**Before and after, so far.** Frozen test set, {{H1_N}} unseen intent families, steering at layer {{LAYER}},
ρ = {{RHO}}.

{{BEFORE_AFTER_TABLE}}

Read together: steering moves the judged Roman-Urdu refusal rate up, a placebo moves it almost as much, and
judged refusals of harmless prompts rise past the pre-registered budget (on reading, those are garbled answers
and not refusals). On reading, the gain in real refusals is modest and not statistically secure at this sample
size, and the residualized vector is indistinguishable from the pooled one. We claim that the gap is real,
that this repair does not close it, and that the usual way of measuring it is unreliable in Roman Urdu.

**Done.** Everything above: the dataset, the pre-registered test, the mechanism measurements, seven steering
arms, two judges, the reading, the release with exact replay.

**Done after the first release, without a GPU.** A family-level audit of the dataset, robustness checks of the
gap on subsets of the test set, and the breakdown of the judge's errors. The
[evidence plan]({{URL_GITHUB}}/blob/main/docs/EVIDENCE_UPGRADE_PLAN.md) assesses six further checks with their
cost, and says which were judged not worth doing.

**Under way, needs no credits.** The author's review of the prompts ({{REVIEW_DONE}} of 144 pairs so far) and of
a second Roman-Urdu spelling for the test families; and his check of the reading on a stratified sample of
replies ({{RESPONSE_CHECK_SHORT}}).

**With more credits, in order of value.** The outcome of each is unknown; that is the reason to run it.

1. **Independent human labels.** Two Urdu speakers who are not part of the project labelling the test replies
   (refusal, answer, neither). This would turn the reading in 7.6 into a result. The cost is annotator time,
   not GPU time.
2. **Spelling and register.** The test families in a second spelling and in colloquial Roman Urdu, both
   written or confirmed by a speaker: does the gap depend on how the Roman Urdu is written?
3. **Statistical power.** Four times as many intent families, to resolve steering effects of the size seen
   here: about 8,400 generations plus judging, an estimated three to four hours on one T4.
4. **Other models.** The same protocol on Tiny Aya Global and on a second model family: is the weak Roman-Urdu
   harm signal specific to Fire, or a property of romanized text?
5. **Fix the cause instead of steering around it.** The model forms a harm signal half as strong for Roman
   Urdu; a fixed added vector cannot make it recognise what it does not recognise. A small LoRA on romanized
   refusal data, or a per-script strength, evaluated on the same frozen test with human labels.
6. **Longer replies, sampling and adversarial prompts.** A second generation configuration (256 tokens;
   sampling with several seeds) is the cheapest of these: about one free GPU session. It is designed in the
   evidence plan and has not been run.

## 9. Teammates tagged

Solo submission: **{{AUTHOR}}**.

**Acknowledgements.** Lexsi Labs for CuratorKIT, SafeTune and AuditKIT and for organising the hackathon; Cohere
Labs for Tiny Aya; the Qwen team for the judge models; Kaggle for the free GPU time on which every run was made.

---

## Related work

**Safety across languages.** Translating a harmful request into a lower-resource language raises the rate of
unsafe replies (Deng et al., 2024; Yong et al., 2023), and safety differs widely across languages in
multilingual benchmarks (Wang et al., 2024). Mixing languages inside one query also weakens refusals (Yoo et
al., 2024).

**Script and transliteration.** The closest work is Al Ghanim et al. (2024): prompts that GPT-4 and Claude 3
Sonnet refused in Standard Arabic produced unsafe content when written in Arabic transliteration or in the
chat-style "Arabizi". Roman Urdu is the Urdu counterpart: common in informal writing, without a standard
spelling, and a known problem for content moderation (Rizwan et al., 2020). Romanized text shares tokens with
English (Husain et al., 2024), which is one reason to expect a model to process it differently from native
script.

**Refusal directions and steering.** Refusal is mediated largely by one direction in the residual stream
(Arditi et al., 2024); adding a contrastive activation vector steers behaviour without retraining (Turner et
al., 2023; Rimsky et al., 2024); and a refusal direction found in English transfers across languages (Wang et
al., 2025). Our measurements agree on direction, since the Urdu-script and Roman-Urdu vectors point the same
way, and add that the *strength* of the signal differs by script.

**Over-refusal.** Harmless prompts that resemble harmful ones are needed to tell caution from blanket refusal
(Röttger et al., 2024); the matched harmless request in every family plays that role here.

**What this study adds.** A matched Urdu-script and Roman-Urdu test set with harmless counterparts, on an
open-weights model; a pre-registered within-item test; an activation-level account of the gap; a controlled,
negative test of script-residualized steering; and an audit showing that an open guard model mislabels
romanized replies.

## Responsible release

- **Prompts.** The harmful prompts state a goal and ask. None contains instructions. They are published in full,
  because the test cannot be repeated without them.
- **Replies.** A reply is replaced by `[withheld]` when the prompt is harmful and the reply is not a clean
  refusal, or when the judge flagged it unsafe. In Roman Urdu, where the judge cannot be trusted, a reply to a
  harmful prompt is published only if that exact text was read and found to be an unambiguous refusal.
  {{WITHHELD}} of {{PUBLIC_ROWS}} logged replies are withheld. Labels, verdicts, lengths and hashes are kept for
  every row, and the whole pre-registered analysis can be recomputed from the public logs.
- **Vectors.** They point toward refusal. Like any published refusal direction they could be applied with the
  opposite sign; they are specific to one layer of one model, and the model already fails to refuse in Roman
  Urdu without any vector. They are released for verification, not for deployment.
- **Nothing is gated**, as the hackathon requires.

## Reproduce it

No GPU is needed for the first block. Python 3.11 or newer.

```bash
git clone {{URL_GITHUB}} && cd scriptshield
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,hub]"
python -m pytest -q                                   # expect: all tests pass (a few are skipped without the optional toolkits)
python scripts/recompute_from_public.py --download    # expect: a line starting with IDENTICAL
```

The second command downloads the public logs, reruns the pre-registered analysis (exact McNemar, family
bootstrap, Holm, the gate) and compares it number for number with the published file.

With a GPU and your own access to the gated base model:

```bash
pip install torch transformers "git+https://github.com/Lexsi-Labs/SafeTune@{{SAFETUNE_COMMIT}}"
hf download {{ID_MODEL}} --revision v0.2.0 --local-dir vectors
python vectors/apply_steering.py --model-dir /path/to/tiny-aya-fire --verify vectors/expected_outputs.jsonl
# expect: {{VERIFY_N}} of {{VERIFY_N}} outputs byte-identical (float16 on a Tesla T4; other hardware can differ in the last bits)
```

The repository holds the protocol with its dated amendments, every decision record, the experiment log and
{{N_TESTS}} unit tests. Base model revision, weight hashes, toolkit commits, dataset checksum, seeds and decoding
settings are recorded with every run.

## Cost

Every run used free Kaggle T4 time; nothing was spent. The {{GPU_RUNS}} sessions with a recorded runtime add up
to {{GPU_HOURS}} hours of wall-clock time on two T4 GPUs, including the runs that were discarded. The hackathon's
optional comparison of a closed model with a fine-tuned small model does not apply here: there is no improved
model to price. Steering itself costs one vector addition at one layer per forward pass.

## How this was built

This project was built with substantial help from an AI assistant (an LLM agent). Under the author's direction
it drafted the prompts, wrote much of the code and analysis, and did the response readings that this article
labels as agent readings. The author chose the research direction, approved the protocol and the release, and
is responsible for the content. The author is reviewing the prompts himself; the dataset's
review status is published per prompt pair and is updated as the review proceeds.

## Licences

Steering vectors, dataset and evaluation logs: CC-BY-NC 4.0 (the vectors derive from the Tiny Aya weights, and
their use is also subject to the Cohere Labs Acceptable Use Policy). Code: MIT. The Lexsi toolkits are used
under the Lexsi Labs Source Available Licence and are not redistributed.

## References

- Al Ghanim, M., Almohaimeed, S., Zheng, M., Solihin, Y., & Lou, Q. (2024). *Jailbreaking LLMs with Arabic Transliteration and Arabizi.* EMNLP 2024. arXiv:2406.18725. †
- Arditi, A., et al. (2024). *Refusal in Language Models Is Mediated by a Single Direction.* NeurIPS 2024.
- Deng, Y., Zhang, W., Pan, S. J., & Bing, L. (2024). *Multilingual Jailbreak Challenges in Large Language Models.* ICLR 2024.
- Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2).
- Husain, J. A., et al. (2024). *RomanSetu: Efficiently Unlocking Multilingual Capabilities of Large Language Models via Romanization.* ACL 2024. arXiv:2401.14280. †
- McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions or percentages. *Psychometrika*, 12(2).
- Rimsky, N., et al. (2024). *Steering Llama 2 via Contrastive Activation Addition.* ACL 2024.
- Rizwan, H., Shakeel, M. H., & Karim, A. (2020). *Hate-Speech and Offensive Language Detection in Roman Urdu.* EMNLP 2020.
- Röttger, P., et al. (2024). *XSTest: A Test Suite for Identifying Exaggerated Safety Behaviours in Large Language Models.* NAACL 2024.
- Turner, A. M., et al. (2023). *Activation Addition: Steering Language Models Without Optimization.* arXiv:2308.10248.
- Wang, W., et al. (2024). *All Languages Matter: On the Multilingual Safety of Large Language Models.* ACL 2024.
- Wang, X., et al. (2025). *Refusal Direction is Universal Across Safety-Aligned Languages.* arXiv:2505.17306.
- Yong, Z.-X., Menghini, C., & Bach, S. H. (2023). *Low-Resource Languages Jailbreak GPT-4.* arXiv:2310.02446.
- Yoo, H., Yang, Y., & Lee, H. (2024). *Code-Switching Red-Teaming: LLM Evaluation for Safety and Multilingual Understanding.* arXiv:2406.15481. †
- Lexsi Labs: [CuratorKIT](https://github.com/Lexsi-Labs/CuratorKIT), [SafeTune](https://github.com/Lexsi-Labs/SafeTune), [AuditKIT](https://github.com/Lexsi-Labs/AuditKIT). Cohere Labs: [Tiny Aya Fire](https://huggingface.co/CohereLabs/tiny-aya-fire). Qwen: [Qwen3Guard-Gen-4B](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B), [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct).

† Checked against the arXiv or publisher record on {{CHECKED_ON}}. The other entries are standard references
given by author, title and venue.

*Every number in this article is filled in from the logged results by `scripts/make_article.py`; none is typed
by hand.*
