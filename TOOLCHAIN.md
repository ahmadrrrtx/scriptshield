# SCRIPTSHIELD — TOOLCHAIN

Two strictly separated environments. Last verified 2026-11-03.

## Environment A — local coding agent (this machine)

| Item | Value |
|---|---|
| OS | Linux, 2 CPU |
| RAM | 1982 MB total (~1424 MB available) |
| Disk | 20 GB free on `/`; `/tmp` tmpfs 992 MB |
| Python | **3.13.16** |
| pip | 26.2.2 |
| git | 2.47.3 |
| uv | not installed (not required) |
| GPU | none |

**Installed and used:** numpy 2.3.5, scipy 1.17.1, pandas 2.2.3, PyYAML 6.0.3, jsonschema 4.26.0, pytest 9.0.3, requests 2.33.0.

**Deliberately NOT installed:** torch, transformers, datasets, accelerate, peft, bitsandbytes, trl, safetune, auditkit, curatorkit, kaggle CLI.

**Why:** the binding constraint is RAM (~2 GB), not disk. A 3.35B model cannot be served here. Local work is schema validation, JSONL, numpy linear algebra, statistics, and unit tests. All heavy imports are guarded so the package imports cleanly without torch.

Local commands:

```bash
cd scriptshield
python3 -m pytest -q                      # unit tests, no GPU, no network
python3 scripts/validate_config.py        # config sanity
python3 scripts/validate_dataset.py       # schema + leakage checks
python3 scripts/inspect_environment.py    # writes a redacted env report
```

## Environment B — remote GPU (Kaggle first, Colab fallback)

| Item | Plan |
|---|---|
| Platform | Kaggle Notebooks (user `ahmadrrrtx`) |
| GPU | T4×2 or P100 (whichever is allocated; recorded per run) |
| Auth | **Kaggle Secrets** only — never notebook literals |
| Persistence | notebook output files; optional private HF dataset later |
| Status | token verified; **GPU quota unverified** (B-003) |

### Pinned toolkit revisions (verified from local clones)

| Toolkit | Commit | Version | License |
|---|---|---|---|
| CuratorKIT | `dd9e835301fcddc74a37501d9e207a5a060d209f` | 0.1.21 (version reported by the installed package; an earlier note said 0.1.22, which was wrong) | LSAL-1.1 |
| SafeTune | `26f59e6d1bdcacafe5f2be3b8d982fb214369659` | 0.1.8 | LSAL-1.2 |
| AuditKIT | `71316da345784ff220d5ed59337441a59ab31526` | 1.1.3 | LSAL-1.2 |

### Model revisions (HF API metadata; weights read from Kaggle Models, see D-017)

| Model | SHA | Params | Gate |
|---|---|---:|---|
| `CohereLabs/tiny-aya-fire` | `73500c80fcb6c8bea3e830c21d5d2920249a0e1a` | 3,349,227,520 | HF gate still 403 for this token (2026-11-12). **Used via Kaggle Models `cohere-labs/tiny-aya/transformers/fire/1`**; sha256 of both weight shards and `tokenizer.json` equals the HF LFS objects at this revision |
| `CohereLabs/tiny-aya-global` | `af89d219b53ed9b13b8a4645f9c8028973510324` | 3,349,227,520 | HF gate 403; available on Kaggle Models; **not run** (dropped for time, D-024) |

### Known dependency conflicts (from pinned pyproject files)

- **SafeTune** requires `transformers>=5.15,<6`, `torch>=2.7`, `trl>=0.12,<1.15`, plus a large tail (lm-eval, wandb, tensorboard, bitsandbytes…). Installing `safetune[all]`-style extras is unnecessary and risky.
- **AuditKIT** core has **zero required dependencies**; its `transformers` extra also pins `transformers>=5.15,<6`. Compatible with SafeTune.
- **CuratorKIT** core needs only pydantic/typer/tqdm/pyyaml. Its `trl` extra pulls `transformers>=5.15,<6`; its `pdf` extra pulls AGPL MinerU — **avoid**.
- SafeTune requires **Python ≥3.12**; Kaggle images are typically 3.11/3.12 — the preflight notebook must record the actual version and fail loudly if <3.12.

### Remote install strategy

1. Preflight notebook records Python/GPU/disk and **does not install anything heavy**.
2. Smoke notebook installs the three toolkits from **pinned git commits**, no extras beyond what is needed, and **imports every required symbol** before claiming success.
3. Never blind-upgrade torch/transformers in a Kaggle image; prefer the image's existing torch and install only what is missing.
4. Every install is followed by an import + a functional smoke assertion. `pip` exit code 0 is **not** evidence of success.

### Remote install commands (to be executed in notebook, not locally)

```bash
pip install --no-deps "git+https://github.com/Lexsi-Labs/AuditKIT@71316da345784ff220d5ed59337441a59ab31526"
pip install --no-deps "git+https://github.com/Lexsi-Labs/CuratorKIT@dd9e835301fcddc74a37501d9e207a5a060d209f"
pip install "git+https://github.com/Lexsi-Labs/SafeTune@26f59e6d1bdcacafe5f2be3b8d982fb214369659"
```

`--no-deps` is used for AuditKIT/CuratorKIT because their cores are dependency-light and we supply what we need explicitly; SafeTune is installed with deps because it genuinely needs the ML stack. Any missing import discovered by the smoke test is added explicitly and recorded here.

## Reproduction contract

Every experiment record must contain: model SHA, toolkit SHAs, dataset version + checksum, hardware, Python/torch/transformers versions, seed, decoding params, layer list, alpha, vector checksum, and the exact command/notebook that produced it.


---

## Addendum 2026-11-12 — what actually ran on the GPU

| Item | Value (measured in the Kaggle session, not assumed) |
|---|---|
| Hardware | 2 × Tesla T4 (free Kaggle), model on GPU 0 |
| torch / transformers | 2.11.0+cu130 / 5.20.2 |
| SafeTune / AuditKIT | 0.1.8 / 1.1.3, pip-installed inside each session from the pinned commits |
| Model dtype | float16, chosen by measurement against a float32 reference (D-022) |
| Judges | `Qwen/Qwen3Guard-Gen-4B` @ `6ec42827…` (primary), `Qwen/Qwen2.5-7B-Instruct` @ `a09a3545…` (rubric, sensitivity) |
| Kernel packaging | `scripts/build_kaggle_kernel.py` embeds the repo at a clean commit into one file; the commit SHA is printed in every run report |
| Local environment | no torch, no weights; numpy/scipy/pytest + CuratorKIT 0.1.21 + AuditKIT 1.1.3 only |

Toolkit behaviours we had to work around (each with a regression test and a decision record):
D-014/D-015/D-016 (hook position and padding), D-018 (double BOS), D-021 (double chat
template through SafeTune), D-029 (AuditKIT disk cache replays one arm's text for another).

## Clean-environment check (2026-11-13)

The CPU part was repeated in a fresh virtual environment, outside the working repository, from the files of
the public snapshot:

| Package | Version | How |
|---|---|---|
| Python | 3.13.18 | |
| numpy / PyYAML / jsonschema / pytest | 2.5.4 / 6.0.3 / 4.26.0 / 9.2.0 | `pip install -e ".[dev]"` |
| AuditKIT | 1.1.3 @ `71316da345784ff220d5ed59337441a59ab31526` | `pip install --no-deps git+https://github.com/Lexsi-Labs/AuditKIT@…` |
| CuratorKIT | 0.1.21 @ `dd9e835301fcddc74a37501d9e207a5a060d209f` | `pip install --no-deps git+https://github.com/Lexsi-Labs/CuratorKIT@…` |
| pydantic / tqdm / typer | 2.14.3 / 4.70.1 / 0.29.1 | `pip install -e ".[curation]"` (pydantic and tqdm are imported by CuratorKIT's curation stage; typer is its declared CLI dependency) |

Results: the unit tests pass (those that need AuditKIT are skipped without it, those that need a git checkout
are skipped in a plain copy); `scripts/run_curation.py` sends 576 records through CuratorKIT and gets 576 back
with no text changed.
