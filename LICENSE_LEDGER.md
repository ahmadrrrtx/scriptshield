# SCRIPTSHIELD — LICENSE LEDGER

Status: **release terms decided on 2026-11-13** (see "Release terms" at the end): code MIT; data, logs and
steering vectors CC BY-NC 4.0. Third-party terms below were verified on 2026-11-03 by reading the
`LICENSE.md` headers and `pyproject.toml` in the pinned local clones.

## Lexsi toolkits (all six reviewed; three used)

| Toolkit | License | Used? | Notes |
|---|---|---|---|
| CuratorKIT | **LSAL-1.1** (Lexsi Labs Source Available) | ✅ | Non-commercial research/education/audit grant; notices must be preserved; no relicensing/rebranding |
| SafeTune | **LSAL-1.2** | ✅ | Same family; covers library + any released checkpoints |
| AuditKIT | **LSAL-1.2** | ✅ | Same family |
| AlignTune | repo license + mixed deps | ❌ | Not in pipeline |
| AgentTune | LSAL-1.1 | ❌ | Not in pipeline |
| CircuitKIT | LSAL-1.2 + unlicensed upstream parts | ❌ | Not in pipeline |

**LSAL is NOT OSI open source.** It is source-available with non-commercial conditions. Vendoring any toolkit code requires preserving the full license and notices. We currently **import** rather than vendor.

## Models

| Model | License | Consequence |
|---|---|---|
| `CohereLabs/tiny-aya-fire` | CC-BY-NC + Cohere Labs AUP; gated | Non-commercial only. **Derived steering vectors are treated as inheriting these terms.** |
| `CohereLabs/tiny-aya-global` | CC-BY-NC + Cohere Labs AUP; gated | Same |
| `Qwen/Qwen3Guard-Gen-4B` @ `6ec42827da0c1ff11e7a49dc269d2e810d27e108` (**primary judge**) | Apache-2.0 (HF API, ungated) | Used for inference only; no weights redistributed. Chosen by a pre-declared agreement rule (κ 0.944 vs an agent-adjudicated reference, n = 72; **not** human labels) |
| `Qwen/Qwen2.5-7B-Instruct` @ `a09a35458c702b33eeacc393d103063234e8bc28` (rubric judge, sensitivity only) | Apache-2.0 (HF API, ungated) | Inference only. Weak on Roman Urdu (accuracy 0.72 on that form) |
| `Qwen/Qwen3Guard-Gen-8B` | Apache-2.0 | Evaluated on paper only; **not run** |

**We will not upload base model weights.** Only vectors + config + loader.

### Where the Tiny Aya weights came from (added 2026-11-12, D-017)

The Hugging Face repos are gated and still returned 403 to the project's read token on
2026-11-12. The experiments therefore read the weights from **Cohere Labs' own public
Kaggle Models release** `cohere-labs/tiny-aya` (variation `transformers/fire/1`), whose
licence field is "CC BY-NC 4.0" plus the Cohere Labs Acceptable Use Policy. The files
were served to the user's Kaggle account without an extra consent step. The sha256 of
both weight shards and of `tokenizer.json` equals the Hugging Face LFS objects at
revision `73500c80…` (hashes recorded in `configs/models.yaml`), so this is the same
model. The user stated in chat on 2026-11-12 that they accept the model terms; the HF
web form itself has not been completed (B-001, now low priority). No weights were
downloaded to the local machine or redistributed.

## Datasets

| Dataset | License | Use |
|---|---|---|
| ScriptShield paired corpus (ours) | **CC BY-NC 4.0** | Original authored content; no third-party prompt was copied |
| XSTest | CC-BY-4.0 (prompts) | Optional over-refusal subset; attribution required |
| MultiJail | repo MIT; HF card license not explicit | **Not used until clarified** |
| Belebele | CC-BY-SA-4.0 (eval set) | Optional utility; share-alike would infect derivatives — keep separate |
| BanglaShield | CC-BY-NC-4.0 | Reference only, not ingested |

**Rule:** third-party material is never merged under a blanket new license. Separate configs/files per source license.

## Third-party libraries

numpy (BSD-3), scipy (BSD-3), pandas (BSD-3), PyYAML (MIT), jsonschema (MIT), pytest (MIT), matplotlib (PSF-based licence; only for redrawing the figures), requests (Apache-2.0), torch (BSD-3), transformers (Apache-2.0). Remote-only ML stack does not change our repo obligations, but SafeTune's dependency tail must be recorded per run.

## Questions that were open, and how they were settled

1. *May derived steering vectors be published?* The hackathon asks for model artifacts on the Hub, and
   CC BY-NC 4.0 allows sharing adapted material non-commercially with attribution. The vectors are
   published under CC BY-NC 4.0 with a note that their use is also subject to the Cohere Labs Acceptable Use
   Policy. No base weights are redistributed.
2. *Does LSAL allow a hackathon submission?* The toolkits are the hackathon's own stack and the event is run
   by their authors. They are imported, never copied or re-licensed.
3. *What licence for our own code, given LSAL imports?* MIT. It covers only the code written for this
   project; anyone running the pipeline must still follow LSAL for the toolkits and CC BY-NC + AUP for the
   model.

## Release terms (decided 2026-11-13)

The hackathon rules (read on 2026-11-13) set no licence. They require every artifact repository and both
collections to be public and un-gated, and say that projects, datasets and findings stay open. The owner
delegated the choice; these terms were chosen as the most open ones that respect the upstream licences.

| Artifact | Licence | Reason |
|---|---|---|
| Steering vectors + loader (Hub model repository) | CC BY-NC 4.0, use also subject to the Cohere Labs AUP | derived from CC BY-NC weights; cannot be more permissive than the base |
| Corpus, splits, utility probe, reviewer pack (Hub dataset repository, `data/`) | CC BY-NC 4.0, **not gated** | original authored text; one set of terms for all project data. The rules require un-gated artifacts; the prompts ask and do not instruct |
| Evaluation logs (Hub dataset repository) | CC BY-NC 4.0 | contain Tiny Aya outputs; unsafe response text is withheld (D-030, D-034) |
| Code (`src/`, `scripts/`, `tests/`, `demo/`, `remote/`, the loader) | MIT | original code; imports LSAL toolkits, vendors none |
| Documents and result files in the repository | CC BY-NC 4.0 | same terms as the data they describe |

The owner holds the rights to the original material and can additionally release the corpus under more
permissive terms later; a licence already granted cannot be withdrawn.
