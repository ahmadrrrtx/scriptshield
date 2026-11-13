# ScriptShield: abstract

**Track 2, AI Red Teaming, Safety and Alignment. Problem 4, multilingual and code-mixed safety, with problem 8,
inference-time safety steering.**

Most Urdu typed on phones is Roman Urdu: Urdu in Latin letters. Safety evaluations usually treat Urdu as one
language. ScriptShield asks whether the safety behaviour of Cohere Labs' Tiny Aya Fire depends on the script,
and tests one way to close the gap it finds.

**What was built.** A matched prompt set of 72 intent families. Each family has a harmful request and a
harmless request on the same topic, written word for word in Urdu script and in Roman Urdu, with code-mixed
and English references (576 prompts; 24 families for calibration, 12 for development, 36 for the test).
Lexsi's CuratorKIT (validation and export), SafeTune (contrastive activation steering) and AuditKIT
(generation and logging) run as one pipeline. The hypotheses, the acceptance gate, the statistical tests and
the rule for choosing layer and strength were written down beforehand. The test set was run once. Everything
ran on free Kaggle T4 GPUs.

**Findings.**

1. The script gap is large. Without steering, the model refused 100.0 % of harmful requests in Urdu script and
   47.2 % of the same requests in Roman Urdu (-52.8 points, 95 % CI -69.4 to -36.1, exact McNemar
   p = 3.8e-06). The gap stays between -45 and -61 points when any one topic group is left out.
2. The automatic judge overstates Roman-Urdu refusals. Only 53 % of the replies it called refusals were
   refusals when read; most of the others were garbled text or repetitions of the question. On reading, 13 of
   36 harmful Roman-Urdu requests were refused.
3. The repair did not work. A steering vector with the script direction projected out gave the same outcome as
   the ordinary vector on 71 of 72 harmful prompts, and the pre-registered gate was not met. The activations
   explain why: the refusal direction is nearly orthogonal to the script direction, and the harm signal for
   Roman Urdu is about half as strong as for Urdu script. Steering raised the judged Roman-Urdu refusal rate
   from 47.2 % to 61.1 %, but a placebo vector did almost as well, so no safety gain is claimed.

**Released.** The dataset with a family-level quality audit; the evaluation logs, with harmful completions
withheld and labels and hashes kept, so that every number can be recomputed; the steering vectors with a
standalone loader that reproduced 144 of 144 logged replies byte for byte; an explorer of the recorded
outputs; and the code with its tests, protocol and decision records.

**Limits.** The prompts were drafted with an LLM; the author's own review of them is published per prompt
pair as it proceeds. Labels of replies come from model judges and from an LLM agent's reading, not from human
annotators. One model, one deterministic run, one Roman-Urdu spelling, 64-token replies.
