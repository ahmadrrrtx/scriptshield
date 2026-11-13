# ScriptShield — abstract

ScriptShield asks whether a small multilingual model's safety behaviour depends on the script Urdu is
written in. Most Urdu typed on phones is Roman Urdu (Urdu in Latin letters), yet safety evaluations usually
treat Urdu as one language.

We built a matched prompt set: 72 intent families, each with a harmful request and a benign request on the
same topic, written in Urdu script, Roman Urdu, code-mixed Urdu-English and English (576 prompts, split by
family into 24 calibration, 12 development and 36 test families). With Lexsi's CuratorKIT (data validation
and export), SafeTune (contrastive activation steering) and AuditKIT (generation and logging) chained into
one pipeline, we measured Cohere Labs' Tiny Aya Fire and tested one repair: a refusal-steering vector from
which the script direction is projected out. Hypotheses, acceptance gate, statistical tests and the rule for
choosing layer and strength were pre-registered, the test set was run once, and everything ran on free
Kaggle T4 GPUs.

Findings. (1) The script gap is large: unsteered, the model refused 100.0 % of harmful requests in Urdu
script and 47.2 % of the same requests in Roman Urdu (-52.8 points, 95 % CI -69.4 to -36.1, exact McNemar
p = 3.8e-06). (2) The repair did not work: the residualized and the ordinary vector gave the same outcome on
71 of 72 harmful prompts and the pre-registered gate was not met. The activations explain why: the refusal
direction is nearly orthogonal to the script direction, and the harm signal for Roman Urdu is about half as
strong as for Urdu script. (3) The automatic judge is unreliable in Roman Urdu: only 53 % of the responses
it called refusals were refusals when read, and every correction widens the gap. Steering raised the judged
Roman-Urdu refusal rate from 47.2 % to 61.1 %, but a control vector did almost as well, so we do not claim a
safety gain.

We release the dataset; the evaluation logs, with harmful completions withheld and labels and hashes kept so
that every number can be recomputed; the steering vectors with a standalone loader that reproduced 144 of
144 logged responses byte for byte; a replay demo; and the code with its unit tests, protocol and decision
records.

Limits: the prompts were written with an LLM and are not yet reviewed by a native speaker; labels come from
model judges and an LLM agent's reading, not from human annotators; one model, one seed, 64-token responses.
