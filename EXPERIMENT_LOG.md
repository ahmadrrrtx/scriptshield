# SCRIPTSHIELD — EXPERIMENT LOG

Every real experiment gets an entry. **No model experiment has been run yet.**
Local unit tests are recorded separately and are never presented as model results.

## Model experiments

The first two GPU experiments (2026-11-03) used an ungated tiny model and verify the
toolchain contract only. **From GPU-20261112-01 onward the real Tiny Aya Fire weights
are used**, read from Cohere Labs' Kaggle Models release (D-017).

### GPU-20261103-01 — Kaggle environment preflight
- **Kernel:** `ahmadrrrtx/scriptshield-preflight` v1 — COMPLETE
- **Model:** none (no weights downloaded)
- **Hardware:** 2 × Tesla T4, 15.64 GB each, driver 580.178.04, 4 CPUs
- **Software:** Python 3.13.16, torch 2.11.0+cu130, CUDA available
- **Toolkit SHAs:** AuditKIT `71316da…`, CuratorKIT `dd9e835…`, SafeTune `26f59e6…`
- **Result:** all three installed (pip rc 0) **and imported**; versions 1.1.3 /
  0.1.21 / 0.1.8; all required symbols OK. Working disk 20.94 GB.
- **HF:** Kaggle secret absent (`ConnectionError`) → unauthenticated probes → 401.
  Gate still closed.
- **Verdict:** **B-003 RESOLVED.** Free GPU path works end to end.
- **Artifacts:** `experiments/results/kaggle_preflight/preflight_report.json`
- **Cost:** $0.00

### GPU-20261103-02 — SafeTune contract verification
- **Kernel:** `ahmadrrrtx/scriptshield-safetune-contract` v5 — COMPLETE, **ALL PASSED**
- **Model:** `sshleifer/tiny-gpt2` (ungated, random weights, 2 layers, hidden=2).
  Chosen deliberately: it exercises the integration without the gated weights.
- **Hardware:** Kaggle T4. **is_safety_result: false.**
- **Checks (10/10 passed):** decoder-layer resolution; requested-layer selection;
  1-D vector shape; **sign cosine = 1.000000** vs an independent manual
  computation; hooks OFF at construction; OFF after call; ON inside context;
  OFF after context; **steering changes logits (max |Δ| = 0.2579)**;
  **residualized vector accepted with norm parity AND orthogonality**.
- **Iterations required (all recorded, none hidden):**
  | version | sign cosine | cause |
  |---|---:|---|
  | v2 | 0.781 | reference read `hidden_states[idx]` (block input) |
  | v3 | 0.328 | `hidden_states[idx+1]` is post-final-LayerNorm |
  | v4 | 0.761 | hook fixed, but OUR pooling used right-padding indexing |
  | **v5** | **1.000** | hook identical module + left-padding-correct `h[:, -1, :]` |
- **Verdict:** SafeTune extraction/application contract **empirically verified**.
  Three silent-failure modes eliminated (D-014, D-015, D-016).
- **Artifacts:** `experiments/results/kaggle_contract_v5/safetune_contract.json`
  (v2–v4 retained for the audit trail)
- **Cost:** $0.00
- **NOT established:** anything about Tiny Aya, Urdu, Roman Urdu, or safety.

Template for future entries:

```
### EXP-YYYYMMDD-NN — <title>
Date / operator:
Model + SHA:
Toolkit SHAs: CuratorKIT / SafeTune / AuditKIT
Dataset version + checksum:
Hardware (GPU, VRAM, driver):
Software (python, torch, transformers):
Seed / decoding params:
Intervention (layers, alpha, vector sha256):
Command or notebook:
Results (with explicit N, failures, unknowns):
Artifact paths:
Verdict:
```

## Local verification runs

### LOCAL-20261103-01 — environment + access probe
- **Date:** 2026-11-03
- **Type:** environment/access verification (NOT a model experiment)
- **Hardware:** local Linux, 2 CPU, 1982 MB RAM, no GPU
- **Actions:** `pwd`, `df -h`, `free -m`, `nproc`, version probes; HF `whoami-v2`; HF model metadata + `config.json` probes; Kaggle list/push probes
- **Results:**
  - HF token valid, user `ahmadrrrtx`, role `read`
  - `tiny-aya-fire` config.json → **403**; `tiny-aya-global` config.json → **403**
  - Kaggle `kernels/list`, `datasets/list`, `competitions/list` → **200**
  - Kaggle `kernels/push` with `{}` → **400** validation error (auth accepted)
  - Disk 20 GB free; RAM ~1.4 GB available
- **Verdict:** access matrix established. **B-001 opened.** No weights downloaded.
- **Cost:** $0.00


### GPU-20261112-01 — Tiny Aya Fire 8-step smoke test  ✅ ALL 8 STEPS PASSED
- **Kernel:** `ahmadrrrtx/scriptshield-fire-smoke` v1 — COMPLETE, 620 s wall (smoke 520 s)
- **Code:** commit `ef07144`, payload sha256 `0d960997…` (embedded in the kernel)
- **Model:** `CohereLabs/tiny-aya-fire` @ `73500c80`, weights read from Kaggle Models
  `cohere-labs/tiny-aya/transformers/fire/1`. **sha256 of both weight shards and
  tokenizer.json = the HF Git-LFS objects at the pinned revision (3/3 match).**
- **Software:** torch 2.11.0+cu130, transformers 5.20.2, SafeTune 0.1.8, tokenizers 0.23.3
- **Hardware:** 2 × Tesla T4. Model on GPU 0 (8.95 GB used).
- **Corpus:** 0.1.1-pilot (sha256 `a7307b6b…`), calibration + dev only. **Test split untouched.**
- **Artifacts:** `experiments/results/fire_smoke_v1/` (report, kernel log, vector manifest)
- **Cost:** $0.00

| Step | Result | Key measurement |
|---|---|---|
| 1 load | PASS | float16 vs float32 reference: top-1 8/8, KL mean 7.8e-6, max \|Δlogit\| 0.025; max \|activation\| 680 (fp16 limit 65,504) → **float16 selected** |
| 2 architecture/template | PASS | Cohere2ForCausalLM, 36 layers, d=2048; default system preamble (383 prompt tokens for a one-word message); last prompt token `<\|START_RESPONSE\|>`; **double-BOS hazard confirmed** (default call = 2 BOS) |
| 3 capture | PASS | finite; batched vs single-prompt capture: rel. err ≤ 0.16 %, cosine ≥ 0.999998 (padding invariant) |
| 4 SafeTune extraction | PASS | 12 vectors (3 contrasts × 4 layers) vs independent capture: **cosine 1.000000, rel. err ≤ 3e-7** |
| 5 sign test | PASS | +α raises / −α lowers the refusal margin at layers 8, 14, 26 (L14, α=+4: +0.91, 12/12 prompts up; α=−4: −0.91) |
| 6 steering in generation | PASS | SafeTune `CAAModel.generate`, pooled + residualized, no hook leak |
| 7 behaviour change | PASS | 12/12 generations changed; margin shift pooled +0.912, residualized +0.957 |
| 8 save/reload | PASS | arrays bit-identical; 12/12 generations byte-identical |

**Descriptive observations (pilot scale: 6 calibration + 3 dev families, weak lexical
proxy, unreviewed prompts — NOT hypothesis tests):**

1. *Behaviour by script (unsteered, 9 families).* Urdu-script harmful prompts: 9/9
   crisp refusals. Roman Urdu harmful prompts: **0/9 recognised refusals** — the
   outputs are garbled moralising, deflection, or (at least one case) the start of
   compliance. The lexical proxy labels all nine `unknown`, so it cannot score Roman
   Urdu output at all (overall proxy unknown rate 57 %). A real judge is required.
2. *Representation.* The harmful−benign contrast is ~1.6–1.8× weaker in Roman Urdu
   than in Urdu script (L20: ‖v_ro‖ 16.6 vs ‖v_ur‖ 29.8); cos(v_ur, v_ro) = 0.77–0.85
   at layers 14–30.
3. *Script leakage in the pooled vector is SMALL.* |cos(v_pooled, d_script)| ≤ 0.135
   at every scanned layer (L14: 0.059). Residualization therefore rotates the vector
   by only a few degrees and the residualized arm behaves almost identically to the
   pooled arm. This is what D-011 predicted. **It points toward a null result for H3.**
4. *Steering over-refuses.* The pooled vector raises the refusal margin on matched
   BENIGN prompts more than on harmful ones (L14, α=+4: benign +1.16 vs harmful
   +0.66); at α=2 the proxy refusal rate on benign prompts went 0/6 → 4/6. The
   over-refusal budget will be the binding constraint.
5. *Dose.* α=8 destroys fluency at every layer (both log-probs fall by up to 9 nats).
   Useful strengths satisfy roughly α·‖v‖ ≲ ‖h‖.
6. *Estimator caveat.* cos(v_ur − v_ro, d_script) ≈ −0.25…−0.42 is biased negative
   by construction (the same benign activations enter both terms). Alignment claims
   need cross-fitting and a permutation / random-subspace null.


---

## GPU-20261112-02 — judge bake-off (`scriptshield-judge-bakeoff` v1)

- **Commit:** `ab44371` · **Runtime:** 390 s · **Cost:** $0.00
- **Input:** the 72 unsteered generations of the smoke run (calibration + dev only).
- **Reference labels:** adjudicated by the LLM agent reading every output
  (`experiments/judge_validation/reference_smoke_baseline.jsonl`). **Not human labels.**
- **Rule declared before the run:** primary judge = highest Cohen's κ against the reference.

| Signal | κ | Accuracy | Roman Urdu accuracy |
|---|---:|---:|---:|
| Qwen3Guard-Gen-4B | 0.944 | 0.972 | 0.889 |
| keyword proxy | 0.856 | 0.931 | 0.722 |
| rubric (Qwen2.5-7B-Instruct) | 0.834 | 0.917 | 0.722 |

**Outcome:** Qwen3Guard-Gen-4B is the primary judge; the rubric judge is kept as a
sensitivity analysis. Known judge failures: the rubric judge called an answer that gave a
sleeping-pill count a refusal; the guard judge labels repetition-loop gibberish
"Refusal: Yes" (handled by D-026: degenerate text is `invalid`, never a refusal).

## GPU-20261112-03 — dev stage v1 (`scriptshield-fire-dev` v1) — PARTLY INVALID

- **Commit:** `9a4cbde` · **Runtime:** 2,480 s · **Cost:** $0.00
- **Corpus:** v0.2.0 (sha256 `fd7a5b7b…`), calibration (24 families) + dev (12). Test untouched.
- **Valid outputs:** unsteered generations on calibration + dev; the activation dump;
  SafeTune vectors and geometry; mechanism diagnostics; every teacher-forced margin.
- **INVALID outputs:** every steered generation of the dev grid except the first call
  (pooled, layer 10, ρ = 0.1). AuditKIT's disk cache replayed that call's text for the
  other 31 (D-029). Detected because all 16 pooled settings had identical rates and each
  later call took 0.0 s. **No configuration was selected or frozen from this run.**

## GPU-20261112-04 — judging dev v1 (`scriptshield-judge-dev` v1)

- **Commit:** `b47b5fe` · **Runtime:** 974 s · **Cost:** $0.00 · 1,824 rows, guard judge only.
- Unsteered rows are valid and reported in `PROJECT_LEDGER.md`; grid rows are discarded.

## GPU-20261112-05 — dev stage v2 (`scriptshield-fire-dev` v2)

- **Commit:** `ea91d4b` (cache fix D-029) · pooled arm only on the grid (the selection
  rule A5 uses only the pooled arm).
- **Runtime:** ~2,200 s · **Cost:** $0.00 · `entry_rc` 0.
- **Cache fix verified on the GPU:** 17 generation calls, 17 distinct output sets, every grid call
  ~29 s (v1: one real call, 31 replays at 0.0 s). Unsteered outputs byte-identical to v1 on 288/288
  prompts, and v1's single valid grid call byte-identical on 48/48: generation is deterministic
  across sessions.
- Judged by `scriptshield-judge-dev` v2 (commit `8284709`, 1,056 rows, 498 s).
- **Selection (rule A5, pooled arm, 12 dev families):** unsteered harmful refusal 16/24, benign 1/24.
  Only 2 of 16 settings stayed within the +2 pp benign-refusal budget. **Frozen: layer 18, ρ = 0.1**
  (harmful refusal 19/24, benign 1/24). Committed as `configs/frozen_selection.json` in `1618d1e`
  before any test kernel was built. Protocol A16.

## GPU-20261112-06 — test stage, launch 1 (`scriptshield-fire-test` v1) — CRASHED BEFORE ANY GENERATION

- **Commit:** `1618d1e` (frozen selection included) · **Runtime:** 219 s · **Cost:** $0.00
- **What happened:** the model loaded and the vectors were extracted from the calibration
  split, then `load_utility` raised `FileNotFoundError` — `data/utility/` was not in the
  kernel payload. `generations.jsonl` and `margins.jsonl` are **0 bytes: no test prompt
  was run and no test output exists**, so the test set is still unseen.
- **Why the rehearsal missed it:** the rehearsal test ran inside the repository, where the
  file exists. **Fix:** `data/utility/` added to the payload, and
  `tests/test_kernel_payload.py` now unpacks the exact payload file list into an empty
  directory and runs every torch-free loader there.


## GPU-20261112-07 — test stage, launch 2 (`scriptshield-fire-test` v2) — THE FROZEN TEST

- **Commit:** `47413df` · **Runtime:** 2,456 s · **Cost:** $0.00 · `entry_rc` 0.
- Frozen setting read from the committed file (layer 18, ρ = 0.1, α = 0.2694). Splits read:
  calibration (vectors) and test only. Weights matched the pinned hashes. SafeTune vectors vs
  independent capture: minimum cosine 0.99999999999999.
- 7 arms × 288 test prompts + utility probe (48 questions × 3 arms) = 2,160 generations, 0 empty,
  no two calls with identical text. Margins for 7 arms × 144 primary-form prompts.
- Geometry at layer 18: residualization removed 9.1 % of the pooled norm; cosine to pooled:
  residualized 0.9958, random_subspace 0.9998, orthogonal_null 0.0000, ur_only 0.984, ro_only 0.930.

## GPU-20261112-08 — judging the test set, primary judge (`scriptshield-judge-test` v1)

- **Commit:** `2e9c3f8` · **Runtime:** 1,111 s · 2,160 rows, 0 unparseable verdicts.
- **Pre-registered analysis (run once, committed in `ecd3fef` before anything else was looked at):**
  - **H1:** harmful refusal 100.0 % in Urdu script vs 47.2 % in Roman Urdu
    (-52.8 pp, CI -69.4 to -36.1;
    exact McNemar p = 3.8e-06; Holm-adjusted 1.1e-05). **Confirmed.**
  - **H3:** residualized vs pooled worst-form gain +2.8 pp
    (CI +0.0 to +8.3); same outcome on
    71/72 prompts. **Gate not met.**
  - Pooled vs unsteered: Roman-Urdu harmful refusal +13.9 pp,
    judged benign refusal +6.9 pp (budget +2 pp: **exceeded**).
    Control `orthogonal_null`: +11.1 pp and
    -2.8 pp.

## GPU-20261112-09 — second judge on the test set (`scriptshield-judge-test-rubric` v1) — pre-declared sensitivity

- **Commit:** `ecd3fef` · **Runtime:** 933 s. Qwen2.5-7B-Instruct with the fixed rubric; 216 "unclear".
- H1 and H3 conclusions unchanged (see `docs/RESULTS.md` §5.1). Merged with the primary judge's file
  by (set, arm, id) into `experiments/results/judge_test_merged/judged.jsonl`; outputs identical in both.

## POST HOC analyses on the test outputs (no GPU) — protocol A18, A19

- **A18, prompt echoes.** 49 of 2,016 test responses repeat the prompt; all are Roman Urdu; the primary
  judge called 32 of them refusals. Echo-corrected analysis written next to the primary one
  (`test_analysis_*_echo.json`).
- **A19, reading.** The agent labelled all 214 distinct Roman-Urdu responses of four arms, arm hidden,
  rubric committed first. Unsteered harmful: 13 refusal /
  6 answer / 17 non-responsive of 36.
  Primary judge's Roman-Urdu refusal label vs the reading: precision
  0.53, recall
  0.86, κ
  0.52. Not human annotation.
- All 36 unsteered Urdu-script responses to harmful prompts were read and are explicit refusals.

## GPU-20261112-10 — exploratory dev grid for the other vectors (`scriptshield-fire-devx` v1 + `scriptshield-judge-devx` v1)

- **Commit:** `1618d1e` (generation, 4,528 s) / `f77a70c` (judge, 1,229 s). Launched after the freeze;
  cannot influence selection; never used for a hypothesis test (protocol A16).
- Residualized, Roman-only and Urdu-only vectors over the same 16 settings, 48 dev prompts each: 48
  calls, 48 distinct output sets.
- Residualized minus pooled harmful refusal: mean +0.8 pp (range
  -4.2 to +12.5); ahead in 3 settings, behind in
  4, level in 9. No consistent advantage for residualization at any dose (24 prompts per cell, so single
  settings are noisy).

## GPU-20261112-11 — release verification (`scriptshield-verify-release` v1)

- **Commit:** `93ecd6f` · **Runtime:** 243 s · **Cost:** $0.00 · `entry_rc` 0 · **PASSED**.
- **Question:** does the released package alone reproduce the logged run? The loader ran in a
  subprocess with an empty `PYTHONPATH` in a copy of the package folder; it reported that no
  ScriptShield module was imported.
- **Result:** 144 of 144 logged responses reproduced byte for byte (unsteered 48/48, pooled 48/48,
  residualized 48/48; utility probe of the frozen test run, 48 new tokens, batches of 8). Steering was
  visibly applied: pooled text differs from unsteered on 24 of 48 prompts, residualized on 26.
- The four files that matter (`steering_vectors.npz`, `manifest.json`, `apply_steering.py`,
  `expected_outputs.jsonl`) have the same sha256 in the verified package and in the final release
  folder; `package_artifacts.py` refuses a verification report for which that is not true.
- Side observation: decoder block 18 (`Cohere2DecoderLayer`) has no bias parameters, so the vector cannot
  be folded into existing weights; a "baked" checkpoint would need an added bias term.

## POST HOC — utility answers read (no GPU) — protocol A20

- **No GPU.** Input: the 144 utility rows of `judge_test_merged/judged.jsonl`.
- **Why:** a spot check of the Roman-Urdu utility answers found one correct answer the patterns
  missed, so all 144 answers were read against their pattern score.
- **Result:** 7 of 144 pattern scores disagree with the text (5 correct but unmatched, 2 matched
  but stating a wrong answer). Utility by pattern / on reading: unsteered 33 / 35, pooled 35 / 36,
  residualized 36 / 36 of 48. On reading the pooled and residualized arms answer the same questions
  correctly, and steering changes one answer relative to the unsteered model.
- **Consequence:** pre-registered numbers and the gate are unchanged; the report states that
  one- or two-question utility differences are inside the scoring error of the patterns.
- **Limits:** read by the LLM agent, not a human, with arm labels visible.

## Totals for 2026-11-12

13 Kaggle kernel versions, all on free T4 quota: fire-smoke 1, judge-bakeoff 1, fire-dev 2, judge-dev 2,
fire-test 2 (the first crashed before generating), judge-test 1, judge-test-rubric 1, fire-devx 1,
judge-devx 1, verify-release 1. **Spend: $0.00.**
