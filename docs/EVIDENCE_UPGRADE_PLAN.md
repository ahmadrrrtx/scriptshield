# Evidence upgrade plan

Written on 2026-11-13, after the first public release and the dataset audit. It assesses six ways to strengthen
the evidence before submission, decides which are worth doing, and records what each would cost.

Two of the checks (E3 and E5a) need no GPU and no person. They were run on the same day, and their outcomes are
recorded below. The other checks had produced no result when this was written.

## Rules for this phase

- The frozen test set, the labels, the thresholds and the pre-registered tests do not change.
- A check is done because its outcome is unknown and would change what the write-up may claim. A check is not
  done to obtain a better-looking number. Every outcome is reported, including one that weakens a claim.
- Everything added now is post hoc and is labelled so. Nothing added now is a new confirmatory test.
- The failed hypothesis stays failed: the residualized vector did not pass its gate, and no subset analysis or
  rerun is a second chance for it.
- Decoding is greedy. Repeating a run reproduces the same text and is not a second seed.
- A reading by an LLM is not human validation. A check by the project author is a participant check, not
  independent annotation.
- No money is spent and no GPU session is started without the owner's go-ahead.

## Where the evidence is weakest today

| Claim in the write-up | What it rests on | Weak point |
|---|---|---|
| The model refuses harmful requests in Urdu script and often not in Roman Urdu | Pre-registered paired test, 36 families, 19 discordant pairs all in one direction | Prompts drafted by an LLM and not yet reviewed; one spelling; one decoding setting |
| The automatic judge overstates Roman-Urdu refusals, so the real gap is larger | A reading of every Roman-Urdu reply by an LLM agent | No human has checked the reading |
| Steering did not close the gap; a placebo did almost as well | Pre-registered gate not met; controls | Differences of a few prompts; judge unreliable in Roman Urdu |

The six candidates below are judged by how much they repair these weak points.

## The six candidates

### E1. Human check of a stratified sample of Roman-Urdu replies

| | |
|---|---|
| Question | Does a person who reads the replies agree with the LLM agent's labels (refuses, goes along, neither)? |
| Hypothesis | Agreement will be substantial (kappa above 0.6), and the person will confirm that many replies the judge called refusals are not refusals. The outcome is open: the LLM may have been too strict or too lenient about garbled text. |
| Why it would change the submission | The second finding and the figure "13 of 36 on reading" rest entirely on the LLM reading. Agreement turns the weakest link into checked evidence. Disagreement means the reading must be demoted in the article and the judge's error rate restated. Either way the article changes. |
| Design | 48 of the 214 distinct replies, stratified by prompt label, LLM label and judge label, drawn with a fixed seed before any human label exists. The labeller sees prompt and reply only; arm, judge label and LLM label are hidden. Same rules as the LLM reading. The hash of the item mapping is committed beforehand. Report: agreement, kappa, confusion table, and judge precision and recall weighted back to the 214 replies. |
| Compute | None. |
| Time | Labeller: 30 to 40 minutes. Tooling: built (`scripts/build_response_label_pack.py`, `scripts/import_response_labels.py`). |
| Limits | One labeller, who is the author and knows the overall results. 48 items: agreement is uncertain by ten to fifteen points. Replies in Devanagari may have to be marked "cannot judge". |
| Decision | **Do it. Highest value per minute.** The pack is ready; it needs the owner's time. Result goes to `docs/HUMAN_RESPONSE_CHECK.md`. |

### E2. Independent review of baseline and steered outputs

| | |
|---|---|
| Question | Would a reader who is neither the author nor the LLM assign the same labels to the unsteered and the steered replies? |
| Hypothesis | The direction would be reproduced: more real refusals with the pooled vector than without, and no difference between the pooled and the residualized vector. |
| Why it would change the submission | It is the only route to a label that is independent of the project. It would settle whether the modest steering gain seen on reading (13 to 19 of 36) is real. |
| Design | A second Urdu reader labels the 144 replies to the 36 harmful Roman-Urdu test prompts in four arms, arm hidden; agreement between the two human labellers; disagreements adjudicated. The E1 pack format serves unchanged. |
| Compute | None. |
| Time | A second person, 1 to 1.5 hours, plus recruiting. |
| Limits | No second reader is available to the project today, and nobody may be contacted in the owner's name. The pack contains replies to harmful requests and must be shared privately. |
| Decision | **Not before the deadline unless the owner has a willing reader.** Stays the first item of future work in the article. |

### E3. False positives and false negatives of the judge

| | |
|---|---|
| Question | When the judge is wrong about a Roman-Urdu reply, in which direction, and on what kind of text? |
| Hypothesis | Errors are mostly false "refusal" labels on text that is not an answer (repetitions of the prompt, loops), and missed refusals are rare. The overall precision and recall were already in the results; the breakdown by kind of reply was open. |
| Why it would change the submission | It tells the reader how to discount every Roman-Urdu number, and it is a usable warning for anyone scoring romanised text with a guard model. |
| Design | Cross-tabulate the judge's label with the reading, by kind of reply (repeats the prompt, Devanagari, other Latin text). Uses labels that already exist. |
| Compute | None. Minutes. |
| Limits | The reference is the LLM reading. E1 checks that reference. |
| Decision | **Done.** `docs/ROBUSTNESS_CHECKS.md`, section "Where the automatic judge errs". The hypothesis held: 51 of 108 judged refusals were not refusals on reading, 42 of them garbled or off-topic text; every one of the 18 prompt repetitions that the judge called a refusal was not one; 9 of 66 refusals were missed. |

### E4. A second generation configuration

| | |
|---|---|
| Question | Does the script gap persist (a) with longer replies and (b) with sampling instead of greedy decoding? |
| Hypothesis | It persists. The mechanism measurement points to how the prompt is read (the harm signal for Roman Urdu is 0.48 times as strong as for Urdu script), not to the decoding rule. Longer replies will reclassify some "neither" replies, in an unknown direction. |
| Why it would change the submission | "One deterministic run, 64-token replies" is a stated limit of the main finding. A second configuration tests the cheapest axis of generality, and sampling with real seeds gives a run-to-run spread, which greedy reruns cannot. If the gap shrank markedly, the headline would need a qualifier. |
| Design | Unsteered model only. The 36 test families, harmful and harmless, Urdu script and Roman Urdu (144 prompts). Configuration B: greedy, 256 new tokens. Configuration C: temperature 0.7, top-p 0.9, three seeds, 64 new tokens. Same judge; the Roman-Urdu replies would again need a reading. Written into the protocol as an amendment before the run: descriptive replication of the H1 statistic, no gate, all configurations reported. |
| Compute | Kaggle free tier, 2 x T4: an estimated 40 to 60 minutes including the judge. $0. For scale: the whole study used 3.1 GPU hours. |
| Time | About 2 hours of agent work (kernel, run, analysis, documents). |
| Limits | Still one model. The judge problem grows with longer text. The test set is looked at again; this is not tuning, since nothing is chosen on it, but it must be declared. Needs the owner's Kaggle token, which is not in the workspace. |
| Decision | **Not run before the submission.** It was the only GPU experiment judged worth its cost, and it was not required. On 14 November the owner chose to submit without it for lack of time. It stays the first item of future work, together with E5b and E5c. |

### E5. More matched-family robustness checks

| | |
|---|---|
| Question | Does the gap depend on a few flawed prompts, on one topic or on one form of request? Does it depend on the one Roman-Urdu spelling used? |
| Hypothesis | The gap does not hinge on the flagged prompts. Two subsets (without the families where a word differs between the scripts; commands against questions) had already been looked at during the audit; the others were open. For spelling the outcome is open. |
| Why it would change the submission | The audit found imperfections; a reader will ask whether they carry the result. "One spelling" is the largest untested threat to the headline. |
| Design, part a | Repeat the pre-registered comparison on subsets defined without reference to any model output: by harm group, leaving one group out, by form of request, without audit-flagged families, and by reviewer verdict as the review arrives. No GPU. |
| Design, part b | Run the unsteered model on the 36 test families in a second Roman-Urdu spelling (72 prompts). Only the spellings the reviewer confirms as natural are used. Reported apart from the primary comparison. |
| Design, part c | Added on 2026-11-13, after review batch 02. Run the unsteered model on the reviewer's corrected sentences: every reviewed test family whose harmful request he corrected, in Urdu script and Roman Urdu, next to the original sentences in the same run. Descriptive only: it shows whether the reviewed wording is refused like the original. It does not replace the pre-registered comparison, and no steering arm is run on corrected text (the vectors were computed from the original calibration prompts). Needs its own protocol amendment before the run. |
| Compute | Part a: none. Part b: 5 to 10 GPU minutes on the Kaggle free tier, in the same session as E4. Part c: a few GPU minutes in that session. |
| Limits | Part a: subsets chosen after the results were known; small subsets are noisy. Part b: needs the reviewed spelling candidates (review batches 01 to 06) and the Kaggle token. Part c: only as many prompts as the reviewer has corrected (after batch 02: two harmful requests with text, two more waiting for it), so it can show a direction and nothing more; it grows with every reviewed batch. |
| Decision | **Part a done**: `docs/ROBUSTNESS_CHECKS.md`. Leaving out any one harm group the difference stays between -45.2 and -61.3 points; on the 21 test families with no audit flag and no note it is 9 of 21 against 21 of 21. Two harm groups (dishonesty, privacy; 8 families) show no gap by the judge, which is reported. **Parts b and c: not run before the submission** (no GPU session, see E4; 12 of the 36 test families were reviewed by then). Future work. |

### E6. More statistics

| | |
|---|---|
| Question | Would further tests or intervals change a conclusion? |
| Assessment | The main effect has 19 discordant pairs, all in one direction; no reasonable test changes its reading. The steering comparisons are limited by 36 families and by the judge, not by the choice of test. Exact McNemar tests, family bootstrap intervals, Holm correction and permutation nulls are already reported. Adding tests after seeing the data adds analyst freedom without adding information. |
| Decision | **No new tests.** The robustness tables give counts and descriptive p-values only. |

## Priority

| Order | Check | State | Needs |
|---:|---|---|---|
| 1 | E5a robustness on subsets | done | nothing |
| 2 | E3 judge errors by kind of reply | done | nothing |
| 3 | E1 human check of the reading | pack ready | 30 to 40 minutes of the owner's time |
| 4 | E5b second spelling, E5c corrected sentences, E4 second configuration (one GPU session) | not run before the submission; future work | reviewed spelling candidates and corrected sentences; a GPU session |
| 5 | E2 independent reader | future work | a second person |
| 6 | E6 more statistics | not done, by decision | |

The owner's review of the prompts (`data/reviewer_pack/`) comes before all of these in priority: it is the
dataset's main open item, and E5b depends on it.

## What stays true whatever these checks show

- The residualized vector failed its pre-registered gate.
- The study covers one model, and its labels of responses are not independent human annotation.
- Results on subsets and under new configurations are descriptive.
