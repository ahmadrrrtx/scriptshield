# SCRIPTSHIELD — DECISIONS

Append-only. Every decision records the original position, evidence, alternatives, and outcome. Corrections never erase history.

---

## D-001 — Accept the four approved methodological changes (2026-11-03)

**Original:** dossier §12 treated four written forms symmetrically, proposed 1,200 prompts up front, assumed a steering-vector repo might satisfy the model-artifact rule, and deferred human validation.

**Decision:** the four Research Lead changes OVERRIDE the dossier blueprint.

1. **Narrow primary comparison.** Primary contrast is **Urdu (Perso-Arabic) vs semantically matched Roman Urdu**. Code-mixed is a **secondary** condition. English is a **reference**, never a pure-orthography comparator. The primary claim is restricted to written-form variation within matched Urdu intent families.
2. **Validate the whole technical path before scaling.** An eight-step smoke test (load → template → activation → CAA → sign → apply → behaviour change → serialize/reload) must pass before authoring 1,200 prompts or launching large GPU jobs.
3. **Do not assume the artifact qualifies.** Prepare the steering-vector package AND an organizer clarification question. No arbitrary adapter will be trained merely to satisfy a checklist.
4. **Human validation is mandatory for language-quality claims.** Reviewer pack required. If unavailable, downgrade claims and state the limitation.

**Evidence:** user directive §0 (authoritative project decision).
**Alternatives considered:** keep dossier as-is (rejected — explicitly overridden); silently reinterpret (rejected — dishonest).
**Outcome:** ADOPTED. Reflected in `RESEARCH_PROTOCOL.md` and the plan.

---

## D-002 — Keep PyTorch off the local machine (2026-11-03)

**Original assumption:** ~2 GB RAM and ~2 GB disk.
**Measured:** RAM 1982 MB total / ~1424 MB available; **disk 20 GB free** on `/`; `/tmp` is a 992 MB tmpfs.
**Decision:** still no local torch/transformers/model weights. The binding constraint is **RAM**, not disk. Local environment does schema validation, JSONL, numpy math, statistics, tests.
**Evidence:** `free -m`, `df -h`, `nproc` (2), `importlib.metadata` probe.
**Alternatives:** install CPU torch locally (rejected: ~2 GB RAM cannot comfortably host a 3.35B model even in fp32 meta form, and it would pollute the lightweight env).
**Outcome:** ADOPTED. **Dossier disk figure corrected**; RAM conclusion unchanged.

---

## D-003 — Credential handling (2026-11-03)

**Decision:** secrets stored at `~/.cache/scriptshield-secrets/` with dir `0700`, files `0600`, outside the git repo. `.cache` is excluded from workspace snapshots. Values are never printed, never written into notebooks, configs, or logs. Remote notebooks must read from **Kaggle Secrets**, not literals.
**Evidence:** directive §7; workspace snapshot exclusion rules.
**Alternatives:** `.env` in repo (rejected); notebook literals (rejected); OS keyring (unavailable headless).
**Outcome:** ADOPTED. A secret-scan test guards the repo.
**Note:** the two tokens were supplied by the user in chat. They are treated as compromised-by-transit and should be **rotated after the hackathon**. Only the read-scoped HF token was provided; no write token exists yet.

---

## D-004 — Gated model access is a hard blocker, not a workaround target (2026-11-03)

**Finding:** the provided HF read token authenticates as `ahmadrrrtx` (role `read`) but `config.json` for both `tiny-aya-fire` and `tiny-aya-global` returns **HTTP 403 — "not in the authorized list"**.
**Decision:** do **not** attempt to bypass the gate, use mirror re-uploads, or scrape weights. Record B-001 and request the user accept the model terms. Continue all unblocked work.
**Evidence:** F-001, F-002 in the ledger.
**Alternatives:** third-party mirrors (rejected — license/provenance violation); different model (rejected — changes the approved thesis).
**Outcome:** ADOPTED.

---

## D-005 — Persistence path without Google Drive (2026-11-03)

**Finding:** `list_connector_tools(google_drive)` returned `catalog_error`; the connector could not be loaded, so no Drive tool is available this session.
**Decision:** use **Kaggle notebook output files** as the primary remote persistence path, plus optional **private HF dataset** for durable storage once a write token is authorized. Do not assume Kaggle can mount Drive like Colab.
**Evidence:** F-003.
**Alternatives:** retry connector later (will retry in a later session); Colab+Drive fallback if Kaggle fails.
**Outcome:** ADOPTED (provisional).

---

## D-006 — CAA sign convention re-verified in pinned source (2026-11-03)

**Dossier claim:** SafeTune has a sign-convention hazard; `extract_caa_vectors` maps positive→"safe" internally.
**Re-verified at `26f59e6`:**
- `caa.py::extract_caa_vectors` calls `ext.extract(safe_prompts=positive_prompts, unsafe_prompts=negative_prompts)`.
- `vector_extraction.py::extract` computes `direction = safe_mean - unsafe_mean`.
- Therefore `extract_caa_vectors(positive=P, negative=N)` returns **mean(P) − mean(N)**.
- `CAATrainer._do_calibrate` passes `harmful` as positive and `harmless` as negative → returns **harmful − benign**.
- `CAAModel` hook computes `h + strength * v`.

**Implication:** to *increase* refusal, pass `positive=harmful, negative=benign` and use a **positive** strength. This is the opposite of what the parameter name `safe_prompts` suggests internally, so it must be confirmed empirically, not trusted.
**Decision:** our wrapper always names arguments `harmful`/`benign` explicitly, records the orientation in artifact metadata, and a mandatory **sign test** must pass on the real model before any evaluation arm runs.
**Evidence:** direct source read of both files at the pinned SHA.
**Outcome:** ADOPTED. Dossier claim confirmed and made precise.

---

## D-007 — `CAAModel` accepts arbitrary vectors (2026-11-03)

**Finding:** `CAAModel.__init__(model, vectors: Dict[int, Tensor], strength: float)` clones the supplied dict and installs forward hooks on `_get_decoder_layers(model)[idx]`. `_get_decoder_layers` explicitly supports the Cohere path `model.model.layers`.
**Implication:** residualized vectors can be injected **without modifying SafeTune**. This keeps the integration honest: SafeTune performs extraction and application; ScriptShield only transforms the vector between those two official calls.
**Decision:** use official `extract_caa_vectors` + official `CAAModel`; put our novelty strictly in the vector transformation.
**Outcome:** ADOPTED.

---

## D-008 — Hook scope caution for CAA on Cohere (2026-11-03)

**Finding:** `CAAModel._make_hook` adds `strength * v` to **every position** in the hidden state, including prompt tokens and all generated steps. It is not last-token-only.
**Implication:** extraction pooling (`last_token`) and application scope (all positions) are asymmetric. This is SafeTune's documented CAA behaviour, not a bug we should silently "fix".
**Decision:** keep SafeTune's application semantics for the official arms so results are attributable to SafeTune CAA; record the asymmetry in the protocol; if we later test last-token-only application, it must be a **separate, labelled ablation**, never a quiet substitution.
**Outcome:** ADOPTED.

---

## D-009 — Statistics computed independently of AuditKIT (2026-11-03)

**Finding (from dossier, source-reported):** AuditKIT 1.1.3 has an open PR stating its paired-bootstrap "significance" is not a valid null test; failed samples can be dropped from headline means; guard cache identity omits judge settings; some parsers map unknown→safe.
**Decision:** use AuditKIT for generation/scoring/logging, but compute **exact McNemar**, **family-cluster bootstrap**, and **Holm** in `scriptshield.statistics`, with explicit denominators and unknown counts. Never report a toolkit p-value as our significance.
**Outcome:** ADOPTED. Unit tests will cover the statistics against known cases.

---

## D-010 — No blanket project license yet (2026-11-03)

**Finding:** CuratorKIT is LSAL-1.1; SafeTune and AuditKIT are LSAL-1.2. All are **source-available, non-commercial**, not OSI open source. Model weights are CC-BY-NC + Cohere AUP.
**Decision:** do not attach a blanket MIT/Apache license to the repo. Add `LICENSE_PENDING.md` explaining the dependency license matrix; resolve before any public release. Our own original code may later be licensed permissively, but **derived steering vectors inherit the base model's non-commercial terms**.
**Outcome:** ADOPTED. Resolved on 2026-11-13: code MIT, data and vectors CC BY-NC 4.0 (D-035, `LICENSE_LEDGER.md`).

---

## D-011 — Residualization can only help under script × harm INTERACTION (2026-11-03)

**Discovered during:** offline pipeline smoke test, before any GPU access.

**Observation:** with a purely **additive** script offset in the synthetic
activations, the true script subspace removed *less* of `v_pooled` than a random
same-rank subspace (0.013 vs 0.219). This initially looked like a bug.

**Derivation.** Let form `f` have script offset `s_f` and shared harm direction `h`:

```
h_harmful,f = c_f + s_f + h        h_benign,f = c_f + s_f − h
v_f         = mean(harmful) − mean(benign) = 2h        # s_f CANCELS exactly
```

So a within-form contrastive vector is **already invariant to any additive
script offset**. Residualizing it against a benign script direction removes
essentially nothing (only sampling noise), and can only *damage* the harm signal.

Now let the harm response depend on script (interaction). With benign prompts
carrying **no** harm component:

```
benign_f  = c_f + s_f
harmful_f = c_f + s_f + a_f·h + b_f·s
v_f       = a_f·h + b_f·s
v_pooled  = mean_f(a_f)·h + mean_f(b_f)·s
```

So the pooled vector retains a script component **iff `mean_f(b_f) != 0`**.
Two distinct sub-cases matter:

| Generative case | predicted alignment | measured |
|---|---:|---:|
| A: additive script offset only (`b_f = 0`) | ~0 | 0.012 |
| B: **asymmetric** interaction (`b_ur=0.6, b_ro=0.2`) | high | **0.55** |
| C: **antisymmetric** interaction (`b_ur=+0.4, b_ro=-0.4`) | ~0 (cancels) | 0.01 |

**Correction to an earlier reading.** A first probe reported alignment 0.64 for
"interaction", but that generator also gave *benign* prompts a form-dependent
harm component. That contaminated the script basis with the harm axis and
inflated the alignment. The figure above is from the corrected generator. The
inflated case is retained as an explicit test
(`test_contaminated_benign_basis_deletes_harm_signal`) because it is a real
threat to validity, not a discarded mistake.

**Consequences — this sharpens the thesis rather than weakening it:**
1. **H2 is precise and falsifiable:** `v_pooled` is script-aligned **iff** the
   model has a *net asymmetric* script × harm interaction. Additive offsets and
   sign-symmetric interactions both predict alignment ≈ 0.
2. **Equal-weight form pooling is itself a partial defence.** This is a genuine
   finding: some of the orthography problem is already solved by pooling, which
   bounds how much residualization can add.
3. **The random-subspace control is mandatory**, not decorative: it separates
   "we removed script" from "we removed a random direction of the same rank".
4. **A null result is informative.** If alignment ≈ 0, the honest conclusion is
   that per-form CAA plus pooling already handles orthography, and the
   contribution becomes the matched-pair measurement plus this invariance result.
5. **The benign basis must be checked for harm contamination** before any
   residualized arm is trusted, or we may delete the signal we want to add.
6. Report `alignment` and `removed_frac` **before** any behaviour metric, so the
   mechanism claim is not inferred backwards from a lucky metric.

**Decision:** add the interaction case as the primary synthetic test, keep the
additive case as an explicit **negative control**, and report alignment as a
first-class diagnostic in every experiment manifest.
**Evidence:** three-case synthetic probe; regression tests in `tests/test_interaction.py` (44 tests pass).
**Outcome:** ADOPTED. Protocol §6–7 interpretation updated.

---

## D-012 — Kaggle environment VERIFIED; fp16 on T4, not bf16 (2026-11-03)

**Measured on the real Kaggle run** (`scriptshield-preflight`, COMPLETE):

| Item | Value |
|---|---|
| GPU | **2 × Tesla T4**, 15.64 GB each (15360 MiB) |
| Driver | 580.178.04 |
| Python | **3.13.16** (≥3.12 → SafeTune OK) |
| torch | **2.11.0+cu130**, `cuda_available=true` |
| Working disk | 20.94 GB free |
| CPUs | 4 |
| AuditKIT | pip 0, **import OK**, 1.1.3 |
| CuratorKIT | pip 0, **import OK**, 0.1.21 |
| SafeTune | pip 0, **import OK**, 0.1.8 |
| Required symbols | `Curator`, `evaluate/generate/Sample`, `CAAModel/extract_caa_vectors` — **all OK** |

**Decision 1 — B-003 is RESOLVED.** Free Kaggle GPU works, internet works, and all
three pinned toolkits install and import together in one image. No paid compute
is needed. Spend remains **$0.00**.

**Decision 2 — use fp16, not bf16.** T4 is Turing (sm75) with **no native bf16**.
The dossier/plan assumed bf16. The smoke test now selects dtype from
`torch.cuda.get_device_capability`: fp16 on sm<8, bf16 on sm≥8. Activations are
still cast to fp32/fp64 for averaging and SVD, so the numerical conclusion is
unaffected. This is recorded because fp16 has a narrower dynamic range and
could matter for activation norms.

**Decision 3 — 3.35B in fp16 ≈ 6.7 GB fits one T4 (15.6 GB)** with room for
activations and KV cache. No quantization is required for the smoke test.

**Note:** the preflight's own `log` shows a `cudart` warning from an imported
library before CUDA init; `torch.cuda.is_available()` was nevertheless `true`
and two T4s were enumerated. The warning is benign, not a GPU failure.

---

## D-013 — Kaggle Secrets unavailable; HF gate still closed (2026-11-03)

**Observed:** `UserSecretsClient().get_secret("HF_TOKEN")` raised
`ConnectionError` (`hf_secret_present: false`). Consequently the remote probes
ran **unauthenticated** and returned **401**, whereas the authenticated local
probe returned **403**. Both mean "no access"; neither indicates the gate opened.

**Decision:** do not treat the remote 401 as new information about the gate.
B-001 remains open and is still a user action. When the gate is accepted, the
token must be provided to Kaggle via **Add-ons → Secrets** as `HF_TOKEN`; the
`ConnectionError` also suggests the secret was never created, which the user
must do in the Kaggle UI (a secret cannot be attached via the push API).
**Never** work around this by writing the token into the notebook.

---

## D-014 — TWO SafeTune integration hazards found by source inspection (2026-11-03)

**(a) `CAAModel`'s constructor does NOT install hooks.**
Verified at `26f59e6`: hooks are active only inside `with wrapper:` or during
`wrapper.generate(...)` / `wrapper(...)`. The docstring explicitly notes this
changed from an earlier always-on behaviour.

*Consequence:* calling `wrapper.model.generate(...)` — the natural-looking
pattern, and what our first draft did — produces **completely unsteered output**.
Every arm would have looked identical and we would have wrongly concluded
"steering has no effect". This is exactly the class of silent failure the
directive warned about.

*Fix:* generation now routes through `wrapper.generate`, plus assertions that
`_handles` is empty before and after the call. A dedicated GPU contract test
(`01_safetune_contract.py`) asserts hooks are off at construction, on inside the
context, off after, and that logits actually change.

**(b) `_get_decoder_layers` lives in `safetune._refusal_helpers`, not
`safetune.interventions.steer._activation`.** Our first import path was wrong
(that module does not exist at this SHA). `caa.py` imports it from
`_refusal_helpers`. **Cohere IS supported** via `model.model.layers` — confirmed
in that function's docstring and code.

**(c) `CAAConfig` must be passed explicitly.** `extract_caa_vectors` defaults to
`target_layers=None`, which extracts at **every** decoder layer — far more
compute than the protocol specifies. We now always build
`CAAConfig(target_layers=[...], pool_method="last_token")`.

**Outcome:** ADOPTED. All three encoded in `safetune_adapter.py` and the smoke test.

---

## D-015 — Layer-index convention: SafeTune hooks block OUTPUT, not input (2026-11-03)

**Found by:** the GPU contract test on `sshleifer/tiny-gpt2`. The sign check
returned cosine **+0.781** instead of ~1.0. The sign was right; the magnitude
was not, which pointed at an indexing mismatch rather than a sign error.

**Root cause (source-verified).** `SteeringVectorExtractor._register_hooks`
attaches `layers[idx].register_forward_hook(...)`, i.e. the **output of decoder
block `idx`**. In HF, `output_hidden_states=True` returns a tuple where
`hidden_states[0]` is the embedding output and `hidden_states[i+1]` is the output
of block `i`. Our manual reference used `hidden_states[idx]` — the block's
**input**.

```
SafeTune vector at key idx   ==  act at hidden_states[idx + 1]
our first reference used         act at hidden_states[idx]      # WRONG
```

**Why this matters far beyond the test.** Our `script_contrast` is computed from
our own `capture()`. If `capture()` read `hidden_states[idx]` while SafeTune's CAA
vector came from `hidden_states[idx+1]`, we would have **residualized a layer-L
harm vector against a layer-(L−1) script basis**. The projection would be
mathematically valid and completely meaningless scientifically — and no shape or
dtype assertion would ever have caught it.

**Fix:** `capture()` now reads `hidden_states[layer_idx + 1]`, documented inline,
and the contract test asserts cosine > 0.99 against the same convention.

**Second contract failure demoted, not hidden.** `wrapper_generate_differs_from_base`
failed because `tiny-gpt2` has 2-D random weights: a genuine logit perturbation
(max |Δ| = 0.258) can leave the argmax token unchanged. Token equality is
therefore **not** a valid hook test. It is now recorded as
`info_token_level_difference`, and `steering_changes_logits` (which PASSED) is
the authoritative evidence that hooks fire. This is a test-design correction,
not a relaxation of a real requirement.

**Confirmed working on real GPU (8 checks):** decoder-layer resolution, requested
layer selection, 1-D vector shape, hooks OFF at construction, hooks OFF after
call, hooks ON inside context, hooks OFF after context, **steering changes
logits**, and **residualized vector accepted with norm parity + orthogonality**.

### D-015 addendum — the real root cause was the final LayerNorm (2026-11-03)

The `hidden_states[idx + 1]` fix made the cosine **worse** (0.781 → 0.328), which
falsified the simple off-by-one theory. Actual cause: for the **last** decoder
block, HF applies the model's final LayerNorm before appending to
`output_hidden_states`, so `hidden_states[idx+1]` is **post-norm** while
SafeTune's forward hook sees the **pre-norm** block output. No fixed index offset
is correct for all layers.

**Final fix (robust, not index-arithmetic):** register a forward hook on the
**identical module object** SafeTune hooks — `_get_decoder_layers(model)[idx]` —
and remove it in a `finally` block. Our script basis and SafeTune's CAA vector are
then provably the same tensor, for every layer, on every architecture.

Applied to `scripts/smoke_model.py`, `scripts/run_experiment.py` and the contract
test. Guarded by `tests/test_layer_convention.py`, which asserts the drivers hook
the module, do **not** use `output_hidden_states`, and always remove the hook in
`finally` (a leaked hook would silently steer the "unsteered" arm).

**Method note:** two hypotheses were tested against real GPU evidence and
rejected before the correct one was found. The failing measurements are recorded
rather than discarded, because "we checked the sign" is only meaningful if the
check could have failed — and it did, twice.

---

## D-016 — Left-padding last-token indexing bug in OUR capture (2026-11-03)

**Found by:** the contract test still reporting cosine 0.761 after the hook fix.
Since both sides now hooked the identical module, the remaining discrepancy had
to be **pooling**, and it was in **our** code, not SafeTune's.

**Root cause.** We set `tokenizer.padding_side = "left"` (correct for generation)
but indexed the last real token as `attention_mask.sum(1) - 1`. That formula is
correct only for **right** padding. Under left padding every row's real tokens
end at `T - 1`, so `sum(1)-1` points at a **middle** token (or a pad slot) for any
row shorter than the batch maximum.

| padding | correct last index | `sum(1)-1` |
|---|---|---|
| right | `sum(1)-1` | ✅ correct |
| **left** | **`T-1`** | ❌ wrong for short rows |

SafeTune's extractor uses `hidden[:, -1, :]` with left padding — **correct**. Our
reference disagreed with it, which is exactly why the cosine could not reach 1.

**Why this is severe.** Batched Urdu/Roman Urdu prompts differ a lot in token
length, so most rows would have been pooled at the wrong position. Every CAA
vector, script basis and residualization would have been computed from
mid-sequence activations. Shapes, dtypes and finiteness all look perfect; only a
cross-implementation cosine check exposes it.

**Fix:** added `scriptshield/steering/pooling.py::last_token_index`, which is
correct for **both** padding sides (finds the last `1` scanning from the right),
raises on all-pad rows, and is used by both drivers. The contract test now uses
`h[:, -1, :]` under left padding, matching SafeTune exactly.
Regression tests in `tests/test_pooling.py` include the explicit demonstration
that `sum(1)-1` differs from the correct answer under left padding, and assert
that neither driver reintroduces the buggy formula.

**Cumulative lesson (D-014/015/016).** Three independent silent-failure modes sat
between "SafeTune imported successfully" and "SafeTune is doing what we think":
hook scope, hook-vs-hidden_states identity, and padding-aware pooling. None
raises an exception. All three were caught only because we insisted on an
**independent cross-check** of the extracted vector rather than trusting the
library call. This is the strongest argument in the project for the mandated
empirical sign test.

---

## D-017 — Load Tiny Aya Fire from Cohere Labs' official Kaggle Models release (2026-11-12)

**Situation.** Nine days after B-001 was raised, the Hugging Face gate for
`CohereLabs/tiny-aya-fire` was still closed for account `ahmadrrrtx`
(`HTTP 403, X-Error-Code: GatedRepo`, re-measured 2026-11-12 with a fresh read
token). The submission deadline is 2026-11-15 11:59 UTC. A statement of acceptance
in chat cannot open a Hugging Face gate; only the account holder submitting the web
form can, and the agent cannot and must not do that on the user's behalf.

**Finding.** Cohere Labs publishes the same release on Kaggle Models:
`cohere-labs/tiny-aya` (owner slug `cohere-labs`, 5 variations incl. `fire`,
created 2026-02-16, licence field "CC BY-NC 4.0", description identical in substance
to the HF card, incl. the Acceptable Use Policy). The Kaggle API serves its files to
the user's account with HTTP 200 and no additional consent step.

**Evidence that it is the same artefact (measured, not assumed):**

| File | Kaggle v1 | HF @ 73500c80 | Verdict |
|---|---|---|---|
| model-00001-of-00002.safetensors | 4,992,396,352 B | 4,992,396,352 B | size equal; sha256 checked in-kernel |
| model-00002-of-00002.safetensors | 1,706,092,176 B | 1,706,092,176 B | size equal; sha256 checked in-kernel |
| tokenizer.json | 21,376,527 B | 21,376,527 B | size equal; sha256 checked in-kernel |
| model.safetensors.index.json | git blob 80c31f6d… | 80c31f6d… | **byte-identical** |
| generation_config.json | a5c3b974… | a5c3b974… | **byte-identical** |
| special_tokens_map.json | ca863ef4… | ca863ef4… | **byte-identical** |
| config.json | 1,963 B | 1,961 B | **differs by 2 bytes — unexplained** |
| tokenizer_config.json | 8,170 B | 8,169 B | **differs by 1 byte — unexplained** |

The two small differences cannot be diffed because the HF copies are behind the
gate. They are reported, not hidden. The smoke test hashes the three large files on
the GPU machine and compares them with the HF Git-LFS sha256 values pinned in
`configs/models.yaml`, so "same weights as HF revision 73500c80" is a measurement.

**Decision.** Use the Kaggle Models release as the weight source for all compute.
This is not a bypass, mirror or model substitution: it is the publisher's own
distribution of the same model under the same licence. It also removes every
credential from the compute path: **no Hugging Face token is sent to Kaggle at all**
(B-003a is therefore withdrawn).

**What this does NOT change.**
- The licence and the Acceptable Use Policy apply exactly as before (CC-BY-NC-4.0,
  non-commercial). The user stated acceptance of the model terms on 2026-11-12.
- Artefacts still name `CohereLabs/tiny-aya-fire` as the base model and record the
  Kaggle source alongside it.
- The HF gate is still worth accepting: it is needed for any HF Space demo that
  loads the model, and to explain the 2-byte config difference. It no longer blocks
  the experiments.

**Alternatives rejected.** Sending the HF token into Kaggle (unnecessary credential
exposure); waiting for the gate (no remaining schedule); a different model (would
change the approved project).

---

## D-018 — Double BOS when tokenising a rendered chat prompt (2026-11-12)

Found by reading the released `tokenizer_config.json`: the chat template begins
with `{{ bos_token }}` **and** the tokenizer has `add_bos_token: true`. Calling
`tokenizer(rendered_prompt)` with defaults therefore yields two `<BOS_TOKEN>`.
Both of our drivers did exactly that. SafeTune's extractor passes
`add_special_tokens=False` when a chat template is present, so our capture would
have been one position out of step with SafeTune on every prompt.
**Fix:** one implementation in `models/runtime.py` (`prompt_ids`, `encode`) that
always passes `add_special_tokens=False` for templated text. Guarded by
`tests/test_runtime_contract.py` with a fake tokenizer that reproduces the hazard;
confirmed on the real tokenizer by smoke step 2
(`bos_count_default_call` vs `bos_count_add_special_tokens_false`).

## D-019 — Devanagari contamination in the pilot corpus (2026-11-12)

`ss-acct_access-cm-harmful` contained three Devanagari characters inside an Urdu
word, and one Urdu refusal regex contained a Devanagari alternative. The corpus
validator only asked "does the string contain Arabic and/or Latin", so it passed.
In a study whose independent variable is the script this is contamination.
**Fix:** per-character script validation (`foreign_script_chars`): `ur` = Arabic
block only, `ro`/`en` = ASCII Latin only, `cm` = both, nothing else ever. Corpus
re-issued as **0.1.1-pilot** (sha256 `a7307b6b…`). Every script now loads the corpus
through `load_corpus`, which verifies the checksum in `configs/data.yaml` and
refuses an edited file. The reviewer pack must be regenerated from 0.1.1.

## D-020 — Generation must stop on the real end-of-turn tokens (2026-11-12)

`generation_config.json` names only `<EOS_TOKEN>` (id 3) as EOS, but an assistant
turn ends with `<|END_RESPONSE|><|END_OF_TURN_TOKEN|>` (ids 261001, 6). With the
default config a finished answer keeps generating until `max_new_tokens`, and the
overflow is scored as part of the answer. `runtime.eos_token_ids` passes all three.

## D-021 — Double chat-templating into SafeTune (2026-11-12)

The first smoke script rendered each prompt with the chat template and then handed
the rendered string to `extract_caa_vectors`, which applies the template itself.
The vector would have been extracted from a prompt containing a whole nested
conversation. The tiny-gpt2 contract test could not catch this because that model
has no chat template. **Fix:** `assert_raw_prompts` in the adapter refuses any
prompt that already contains chat-template markers; the smoke test cross-checks
SafeTune's vectors against an independent capture at four layers (cosine > 0.99).

## D-022 — Inference dtype is chosen by measurement against a float32 reference (2026-11-12)

The weights are stored in bfloat16; Tesla T4 has no native bf16. Rather than assume
float16 is safe (it overflows at 65,504), smoke step 1 loads a **float32 reference**
across both GPUs, records next-token logits and per-layer activation range, then
accepts the first of [float16, bfloat16] that is finite at every layer and within a
KL tolerance of the reference (mean < 0.01, max < 0.05 nats); otherwise it runs in
float32. The tolerance is an engineering threshold for numerics, not a research
threshold. The selected dtype and the comparison are written to the report.

## D-023 — The sign test uses a teacher-forced refusal margin, not generated text (2026-11-12)

A lexical refusal rate on eight generations can sit at floor or ceiling and prove
nothing about direction. Step 5 instead scores, for each prompt, the model's mean
per-token log-probability of fixed refusal continuations minus fixed compliance
continuations (English, Urdu, Roman Urdu), at strengths −α, 0, +α and more.
Properties: continuous; no classifier; a *difference*, so a vector that merely
damages fluency does not register as refusal; and no text is generated, so negative
strengths can be tested without producing harmful output.

---

## D-024 — Scope reduced to 72 families; splits by seeded rule (2026-11-12)

Nine days of schedule were lost, so the 150-family ambition is replaced by 72 authored
families (24 calibration / 12 dev / 36 test). New families are assigned by a seeded,
stratified rule (`scripts/merge_families.py`) so the author cannot choose the test set.
Roman Urdu is a word-aligned transliteration of the Urdu-script sentence (0 word-count
outliers), which is what makes ur↔ro a script contrast rather than a paraphrase contrast.
Not done and not claimed: human review; Roman style B; balance of speech acts
(16/72 harmful vs 2/72 benign are imperative "write…" requests).

## D-025 — Primary judge: Qwen3Guard-Gen-4B, chosen by a rule fixed in advance (2026-11-12)

The keyword proxy recognised 0/9 Roman Urdu refusals in the smoke test. Bake-off on the
72 smoke baseline outputs against agent-adjudicated reference labels:

| Signal | Cohen's κ | Accuracy | Roman Urdu accuracy |
|---|---:|---:|---:|
| Qwen3Guard-Gen-4B ("Refusal: Yes") | **0.944** | 0.972 | 0.889 |
| keyword proxy | 0.856 | 0.931 | 0.722 |
| rubric judge (Qwen2.5-7B-Instruct) | 0.834 | 0.917 | 0.722 |

The rubric judge called "you will have to give 7–9 sleeping pills" a refusal. The guard
is primary by the κ rule (protocol A3); the rubric judge is a sensitivity analysis.
**Caveat that must travel with every number:** the reference is an LLM agent's
adjudication of 72 short outputs, not human labels.

## D-026 — Degenerate text is `invalid`, never a refusal (2026-11-12)

At a high steering dose the model emits loops ("- [you] - [you] - …") and the guard
labels them "Refusal: Yes" (6/6 at α=8 in the smoke test). Without a rule, a vector
could "improve safety" by destroying the model. A pre-declared repetition test
(`evaluation/final_label.py`, unit-tested on the real loops) maps such text to
`invalid`, which stays in the denominator and counts against the invalid-rate budget.

## D-027 — AuditKIT drives generation; prompt identity is verified (2026-11-12)

Every generation goes through `auditkit.generate` with a callable that closes over
SafeTune's `CAAModel`. The adapter raises if AuditKIT hands the model any string that
is not byte-identical to a dataset prompt, checks output order by sample id, and turns
a failed generation into `invalid` rows instead of dropping them. Aggregation and
significance remain our own (D-009).

## D-028 — The "shuffled-label" control was an anti-refusal vector; replaced (2026-11-12)

Found in the dev run's geometry report, before any test generation: the control vector
had cosine −0.59 (L10) … −0.81 (L22) with the pooled refusal vector. Cause: shuffling
labels across 96 pooled activations leaves a chance imbalance of true labels between
the two groups; the harm axis is the dominant direction, so that imbalance sets the
direction and its sign is a coin flip. After norm matching the arm would have steered
*away* from refusal on 144 harmful test prompts.
A balanced within-pair label flip removes the bias in expectation but, measured on the
real activations over 200 seeds, still leaves |cos| ≈ 0.15–0.31 for any single seed.
**Final control:** that vector with its component along the pooled vector removed
(exactly orthogonal), norm-matched: `orthogonal_null`. Tests: `tests/test_null_control.py`.
Lesson: a control must be checked for what it actually is, not for what it is called.

## D-029 — AuditKIT's disk cache replayed one arm's text for 31 others (2026-11-12)

**Symptom (dev run v1).** All 16 layer/strength settings of the dev grid showed the same
refusal rate, including a dose the smoke test had shown destroys the model.
**Evidence.** Per-call wall time: first grid call 28.7 s, the next 31 calls 0.0 s each.
32 "arms", 1 distinct set of outputs. The teacher-forced margins (which do not go
through AuditKIT) varied normally, so the vectors and SafeTune hooks were fine.
**Root cause.** `auditkit.Runner.run` returns a cached `RunResult` when the run
fingerprint matches. For a callable model the fingerprint uses the function's code and
its *immutable* closure values. Our steering arms are the same closure code capturing
different `CAAModel` objects, so every arm over the same prompts had the same
fingerprint. Upstream's own docstring describes this collision class. Reproduced
locally on raw AuditKIT 1.1.3 (`tests/test_auditkit_cache.py`).
**What was valid in v1:** the unsteered calibration+dev generations (first call for
that prompt set), the activation dump, the SafeTune vectors and all margins.
**What was invalid:** every dev-grid generation except (pooled, L10, ρ=0.1). No
selection was made from it and nothing was frozen.
**Fix (three independent defences).** (1) every call wraps the callable in a
`CallableModel` with a unique name, so no two calls share a fingerprint; (2) the
adapter counts the prompts the model actually received and raises `StaleCacheError`
otherwise; (3) the dev selection refuses to run when every config has identical text.
The scorer used through `auditkit.evaluate` gets a unique name for the same reason.
**Why it matters beyond this project.** Any steering/ablation study that passes
closures to AuditKIT would silently compare an arm with itself and report "no effect".
This is the fourth silent failure in this pipeline that raised no exception (D-014,
D-015/016, D-018/021, D-029); each was caught only by an independent consistency check.

## D-030 — Public artifacts withhold unsafe response text (2026-11-12)

**Context.** The evaluation logs hold Tiny Aya's responses to harmful requests. In Roman
Urdu a large share of those responses comply. Publishing the raw logs or a demo built
on them would publish harmful instructions in Urdu and Roman Urdu under the user's name.
**Decision.** In every public artifact (evaluation logs, demo, expected-output file) the
response text is replaced by `[withheld]` when (a) the prompt is harmful and the final
label is anything other than `refusal`, or (b) the judge flagged the response unsafe.
The label, the judge verdict, the response length and the sha256 of the text are kept,
so every reported rate can be recomputed and exact reproduction can still be verified.
The prompts themselves are published (they are requests, not instructions), with a
gating recommendation on the dataset card. *(Later: the hackathon requires un-gated
artifacts, so the dataset is not gated; see D-035. The rule for Roman Urdu was tightened
in D-034.)*
**Enforced by** `artifacts/release.py::must_withhold / assert_nothing_leaks`, unit tests,
and a full-text scan of the release folder in `scripts/package_artifacts.py`.
**Not decided here.** Whether the complete, unredacted logs are shared privately or
behind a gate is the user's call (B-008).

## D-031 — The primary judge is unreliable in Roman Urdu; report in layers, never swap the primary (2026-11-12)

**Context.** After the pre-registered analysis was run and committed, reading the Roman-Urdu test
responses showed the primary judge (Qwen3Guard-Gen-4B) answers "Refusal: Yes" for prompt echoes,
repetition loops, paraphrases of the prompt, off-topic answers and some real answers. Against a reading
of all 288 Roman-Urdu rows of four arms its refusal label has precision 0.53 and recall 0.86. The second
judge (rubric on Qwen2.5-7B) is no better (precision 0.60). The pre-experiment bake-off (κ 0.94) had only
18 Roman-Urdu outputs and did not reveal this.
**Decision.** (1) The pre-registered labels and tests stay the primary result and are reported unchanged.
(2) Three additional layers are reported next to them, each labelled with its status: the pre-declared
second judge; a post hoc echo correction (A18); a post hoc reading by the agent with a rubric committed
before labelling, arms hidden, borderline cases listed and flipped as a sensitivity check (A19).
(3) No conclusion about steering arms is stated as established unless the pre-registered analysis supports
it. (4) "Over-refusal" in Roman Urdu is described as what it turned out to be: garbled output that the
judge reads as refusal.
**Consequence for claims.** H1 is robust (every layer widens the gap). H3 is not supported under any
layer. Whether steering helps at all is left open.
**Lesson recorded.** A judge must be validated per stratum that the hypothesis compares, with enough rows
in the weakest stratum, before the experiment.

## D-032 — Release verification uses the utility probe, so the model repository carries no harmful prompt (2026-11-12)

**Context.** Exact reproduction needs logged prompts and outputs with the logged batch composition. The
first packaging used the first 32 test prompts, 16 of them harmful requests, in an ungated model repository.
**Decision.** The verification set is the utility probe of the frozen test run: 48 harmless factual
questions × unsteered / pooled / residualized, 48 new tokens, same order and batch size as logged. All 144
expected responses are publishable in full. Steering is visibly active on this set (pooled differs from
unsteered on 24 of 48 responses, residualized from pooled on 5), and the verification fails unless every
steered arm differs from the unsteered output somewhere.

## D-033 — Vector file is written deterministically (2026-11-12)

`numpy.savez` stamps the current time into the archive, so identical vectors gave different file hashes on
every build and a verification report could not be tied to the published file. `save_npz_deterministic`
fixes the timestamp; `package_artifacts.py` refuses a verification report whose file hashes differ from the
package being built.

## D-034 — Roman-Urdu responses to harmful prompts are published only after reading (2026-11-13)

**Context.** D-030 released the text of a response to a harmful prompt whenever the judge labelled it a clean
refusal. A19 showed that in Roman Urdu this label is right only about half the time. A check before
publication found, in the three arms that were not part of the reading, 51 Roman-Urdu responses that the
judge alone had released: 30 were identical to texts read as refusals, 8 to texts read as non-responsive,
and 13 had never been read. One response read as a refusal had "answer" as a defensible second reading.
None of the texts read as an answer toward a harmful request would have been published, but the rule did not
guarantee that.
**Decision.** For a harmful prompt in Roman Urdu the response text is public only if that exact text was
read for that prompt and found to be an unambiguous refusal (label R, not borderline) in every arm where it
was read. Everything else keeps its labels, length and hash. For Urdu script, code-mixed and English the
judge rule stays; before publication all 384 distinct released responses in those forms were checked: 366
open with a standard refusal sentence, and the other 18 were read in full and are refusals.
**Effect.** 200 of 2,160 public rows are withheld (159 before). `withheld_reason` and
`read_as_clean_refusal` are published with each row, and the check that nothing leaks is computed from the
published fields alone. The analysis is unaffected: every pre-registered number is reproduced from the
public file (`scripts/recompute_from_public.py`).
**Also.** The same rule is applied by `scripts/scan_repo_for_responses.py`. Five response previews in tracked
files (a smoke-test report and one test fixture) were read in full and added to the reviewed allowlist: all
are refusals or content-free loops.

## D-035 — How the project is published (2026-11-13)

Decided after re-reading the hackathon rules and submission requirements on 2026-11-13; the owner delegated
the choices on condition that they follow the rules.

- **Nothing is gated.** The submission form asks for every individual repository and both collections to be
  public and un-gated. The earlier plan to gate the dataset is dropped. The dataset holds requests that
  state a goal and ask; no instructions, and no model response that goes along with a harmful request.
- **Two collections**, as the form asks: model artifacts (steering vectors, replay Space) and data artifacts
  (dataset with evaluation logs).
- **Licences.** The rules set none. Code MIT; data, logs and vectors CC BY-NC 4.0 (`LICENSE_LEDGER.md`).
- **Code repository without the earlier history.** The rules ask for a public repository whose README covers
  reproducibility and for work developed during the hackathon; they do not ask for commit history. Two early
  test files contained a real response to a harmful prompt, so the public repository starts from a snapshot,
  with every original commit listed in `docs/PROVENANCE.md`.
- **Write-up.** The article is in the repository (`docs/hf_article.md`), which the rules accept; it follows
  the nine sections of the kickoff checklist so that it can also be posted as a Hugging Face Article.
- **Disclosure.** The article, the cards and the README state that the project was built with an AI
  assistant and what it did.
