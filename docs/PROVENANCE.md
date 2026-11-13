# Provenance of this repository

This public repository is a snapshot of a private working repository at commit `cda2079149c3375e82cf097f5d28bce2a7271365`.
It was published without the earlier history for one reason. In early commits, two unit-test files
used a real model response to a harmful prompt as a fixture. The fixture was replaced by a synthetic
sentence before publication, but the old text would have stayed readable in the history. Publishing a
snapshot keeps it out of the public record, in line with the rule that no such response is published
(`DECISIONS.md`, D-030).

The work was done between 2026-11-03 and 2026-11-13. Every original commit is listed below with its hash, time
and subject. These are the hashes that the run reports under `experiments/` and the published
artifacts refer to. The order of events is also recorded outside this repository: by the creation times
of the Kaggle kernel versions that ran each stage (`EXPERIMENT_LOG.md`) and by the commit times of the
Hugging Face repositories. The full history can be shown to the hackathon organizers on request.

Left out of the snapshot: internal task lists and access notes, a note of open questions for the
organizers, a local bootstrap script and an early, stale copy of the code that was once uploaded to
Kaggle. A few documents still mention entries of those task lists by identifiers such as B-012; they
are not needed to follow the study.

## Original commits (newest first: hash, author date, subject)

```
cda2079149c3375e82cf097f5d28bce2a7271365  2026-11-13T09:43:23Z  Docs: link the Lexsi toolkits and the models in the README and the write-up
f97bcbd65d5028d18a836b484db3b3e876114823  2026-11-13T09:38:14Z  Internal: record publication (2026-11-13), submission form values, updated blockers and status board
c27d92b5ded8fc77762d758f9d3b1b15048b3ae3  2026-11-13T09:31:51Z  Publish script: remove the Hub's template files from a new static Space
272c1325b03e7e657a96c2c72a30e61e3b6fe34f  2026-11-13T09:27:21Z  Snapshot script: no early-closing pipe under pipefail; fail loudly if the provenance file is missing
f3fa31c249ccb6faf524373760cf1a5b0d5e2b35  2026-11-13T09:26:45Z  Publication per the hackathon rules read on 2026-11-13: nothing gated, two collections, MIT code / CC BY-NC data; Roman-Urdu responses released only after reading (D-034); article follows the nine checklist sections; public README with reproduction notes; recomputation of the analysis from public logs; clean-environment fixes
fd22af6c61c0faba0693cacb6a905f0e71e5a766  2026-11-12T16:20:36Z  Ledger, checklist and README brought up to date (193 tests, A20, housekeeping, Drive status)
23ae9c2c8e9c0043d7995cdf602389b00729710c  2026-11-12T16:18:59Z  Post hoc reading check of the utility score (A20): all 144 answers read, 7 pattern scores disagree; reported next to the unchanged pre-registered numbers. Drive status and provenance wording in blockers
d4606a70fa80cc4a0f78c551210af83192e40b37  2026-11-12T16:07:37Z  Note: duplicate dev-v1 activation dump removed (identical to v2)
7a18ffd58fde2c050e454722f0fd0d698c06d3ff  2026-11-12T16:06:34Z  Experiment log: release verification and totals
f610405ebd7721210fb832a6187652edef583539  2026-11-12T16:06:11Z  Utility-pattern check recorded and reported; public-snapshot export with provenance list (option A of B-012)
894c07d698f4d8063fcbfd79d74d11a6418ffa9f  2026-11-12T16:04:17Z  Card p-value formatting; checklist and credits wording
5029b3bf96c7a19d4d5248e6b925d83570d8bdf4  2026-11-12T16:03:27Z  Docs brought to the final state: README, checklist, blockers (owner actions, B-012..B-014), ledger outcomes, plan board, licence proposals, with-more-credits; static Space folder; publish script (dry run by default); release-folder response scan
0989377e3e1bac7f834f4db8050247a8bb8414ba  2026-11-12T16:00:06Z  Repo scan for withheld response text (clean); synthetic fixture replaces a real answer to a harmful prompt; reviewed allowlist for two content-free loops
0df0b514eb1c4cf8359413bdfb92b8c97bc0dc7f  2026-11-12T15:57:17Z  Release verification PASSED on a fresh GPU session: 144/144 logged responses reproduced byte-for-byte from the released package alone
071d847f6124ae40fb21589a47656066d54e1600  2026-11-12T15:55:14Z  Article template + generator; experiment log through the test stage and post hoc analyses; D-031..D-033
93ecd6fa7abd57f258050ad1ffd03ac98b7fcc03  2026-11-12T15:52:02Z  Release packaging: adjudication-aware withholding, deterministic vector file, principled leak scan (+test), utility-based verification set (no harmful prompt in the model repo), cards state the negative result, demo shows judge label next to reading
c59626f330dd2915773da42f46799999a30ff702  2026-11-12T15:46:40Z  Exploratory dev grid for residualized / Roman-only / Urdu-only vectors judged and analysed; RESULTS.md regenerated
6d176019bfbc06805972301cac98f6858ba254f1  2026-11-12T15:34:42Z  RESULTS.md: layered report (pre-registered / pre-declared sensitivity / post hoc echo / post hoc adjudication); all statements computed from JSON
7608288166c82ca65252320c62aebd4df6127305  2026-11-12T15:29:13Z  Rubric judge (pre-declared sensitivity) on the test set; merged judged file; analyses for both judges, pre-registered and echo-corrected; adjudication report incl. rubric
104f11dbc56c1c9b9c02e5f0c6d01f6185fee93f  2026-11-12T15:22:11Z  A19 timestamp
160c32779b33efd93f483f2a55ef0e72375441f6  2026-11-12T15:22:03Z  POST HOC A19: agent adjudication unblinded (Roman Urdu, 4 arms); report script with borderline sensitivity; Urdu-script refusals verified by reading
f4d38f2db80e0ae7bc46036deb63ff8271b3256b  2026-11-12T15:20:57Z  Agent adjudication of 214 unique Roman-Urdu test responses (arms hidden): labels + borderline file. Not yet unblinded.
ce72017695e433dc9ec9b78ed73a47f6de0dd186  2026-11-12T15:16:58Z  Adjudication rubric (written before labelling) + blind sheet builder; unredacted sheet kept out of git (D-030)
f77a70cf5f0eea73f020b628d55698a207216c4a  2026-11-12T15:15:51Z  Exploratory dev grid (residualized, ro_only, ur_only) fetched, unjudged
cdf35d9904861a4224f742ed6e0d7dd7b5d57b64  2026-11-12T15:15:36Z  POST HOC A18: prompt-echo rule as a separately labelled sensitivity analysis; tests; echo-corrected test analysis
ecd3fef6e2f96b17a954c0b9e872b98e7a0da5b8  2026-11-12T15:11:18Z  Test stage judged by the primary judge; pre-registered analysis run (test_analysis_guard.json). H1 confirmed, H3 gate not met.
2e9c3f814b6ee2adc333cd70bcf6712ecf6ebb05  2026-11-12T14:46:50Z  Test stage v2 fetched: 7 arms x 288 prompts + utility, frozen L18 rho0.1, entry_rc 0, no identical-text calls (unjudged)
9881107534f0c097eca05ef2e6461ade50810e3d  2026-11-12T14:30:58Z  Replay demo: pure renderer + Gradio app + tests
29baeca78c73fe976384d3595792f413b3127046  2026-11-12T14:15:55Z  Card templates (model, dataset)
793f03769958ee0809905ede85cc96ca8fa37d36  2026-11-12T14:10:16Z  Packager, release verification driver, demo template (work in progress; cards pending results)
7dd0bfbc04dcbe706c6c23dd008f63b68f9e378b  2026-11-12T14:07:12Z  D-030 recorded
880e18fe7d3b5dfafe6d41a368e4113089519cde  2026-11-12T14:06:44Z  Release building blocks: withholding rule D-030, vector repack, standalone SafeTune loader with exact-reproduction verify mode; tests
47413dfa41c32fe0f5b555ba1d64838d40317c67  2026-11-12T14:04:09Z  Kernel payload: ship data/utility (test-stage launch 1 crashed before any generation); payload self-sufficiency test; --attach for release verification
2ef08e8769e23716e26163d9dd1def54f8047b70  2026-11-12T14:01:19Z  A17 timestamp corrected to the actual time
02e2b4eebd48b25b2a1dd41bef5d89a9efc8915e  2026-11-12T14:01:05Z  Secondary descriptive table (each arm vs unsteered, paired, with CIs) declared before unblinding (A17)
1618d1e719515d62102418663209444e21715908  2026-11-12T13:58:50Z  FREEZE: layer 18, rho 0.1 by rule A5 on the re-run dev grid (protocol A16); --grid-only flag for the exploratory dev grid
8ed04add46c87a8996dafa850534fbba94b63cf2  2026-11-12T13:47:06Z  Judge resolves utility prompts (would have aborted the test-stage judging); end-to-end rehearsal of the test-stage file flow with stub model + stub judge
8284709b5908e8f32d0f358f1b25ea1a316f978a  2026-11-12T13:45:26Z  Dev v2 fetched (cache fix verified: 17 configs, 17 distinct output sets, ~29 s per grid call)
b3ceb578db2391b398c53aeabe9e1086beebf8bb  2026-11-12T13:36:17Z  Docs: toolchain addendum, licence ledger (judges, Kaggle weight source), experiment log through dev v2
04260d7dfd5e18987e82ea3c9d1607db52332ee9  2026-11-12T13:09:55Z  make_report.py: render docs/RESULTS.md from analysis JSON
6f33db21146872e2de9bf8303aa028f82948b1f7  2026-11-12T13:08:33Z  Ledger: 2026-11-12 execution log
ea91d4b59ea96f6652d0dfc7f6b294cc9aa521f0  2026-11-12T13:08:00Z  D-029: AuditKIT disk cache replayed one arm's text for every other arm; fixed with unique model identity + StaleCacheError guard + analysis guard
c026694e592125ce5003f3cf627f9fbd747b34ad  2026-11-12T12:50:30Z  D-028: replace mis-specified shuffled-label control (cos -0.6..-0.8 to refusal vector) with an exactly orthogonal null direction; protocol A15
b47b5fe224fb4c363520a4e0ae038aba1bded058  2026-11-12T12:26:04Z  DECISIONS D-024..D-027
30776563e126cc62c97100ff2598f6d947294ca5  2026-11-12T12:10:28Z  Analysis: dev selection rule (A5) and pre-registered test analysis, unit-tested on synthetic judged rows (146 tests)
5a4df69e4edd9c1c6ce1544480de33029baf48f5  2026-11-12T12:07:55Z  Judge selected by pre-declared rule (Qwen3Guard-Gen-4B, kappa 0.944 vs reference); degenerate output = invalid (A14)
9a4cbde34411883f06984938e66c3f24e1a81757  2026-11-12T12:06:01Z  Pre-registration amendment A (before any dev/test result) + experiment driver
ab443719ae86976667e2d7cc2ff506514f03b838  2026-11-12T11:58:32Z  Judge runner: Qwen3Guard-Gen-4B + rubric judge (Qwen2.5-7B-Instruct), pinned revisions; builder supports kernel sources
96c7f9b3d3b2aafd02148094f58cc8dad414f8e9  2026-11-12T11:57:04Z  Dataset v0.2.0: 72 matched intent families (576 records), seeded stratified splits
05a554d8c5ff5d6d411c55b714181a25fb5c11bb  2026-11-12T10:20:36Z  Fire smoke test: all 8 steps PASS on real Tiny Aya Fire (Kaggle 2xT4, float16 validated vs float32)
ef07144a10e81c8aaa54e0d01d1b277df2879713  2026-11-12T10:06:41Z  Real-model path: Kaggle Models source for Tiny Aya Fire, shared runtime, smoke v2
37ee4f77cb79ea0f417f674cc0ce9db7022594e1  2026-11-03T01:19:46Z  Update submission checklist with verified-vs-claimed audit
46cacc1bc31daa3b350ebeb9ded5fdb22639bd8a  2026-11-03T01:19:31Z  SafeTune contract VERIFIED on GPU: 10/10 checks, sign cosine 1.000
aae757ec3a722ff02d02486df1e0ad67af905bad  2026-11-03T01:08:30Z  Kaggle verified (2x T4, all toolkits import); fix critical CAAModel hook-scope trap
b08f6a2ad8d163fd18f3fb4300137cb430b87c52  2026-11-03T00:58:23Z  Phase 0: control docs, core math, real CuratorKIT+AuditKIT integration, 44 passing tests
```
