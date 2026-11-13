# If we had more compute / credits

Spent so far: **$0.00**. Every run used free Kaggle T4 time. Estimates below use published Hugging Face Jobs
rates (T4 $0.40/h, L4 $0.80/h, A10G $1.00/h). **Nothing here is authorized or spent.**

What we learned changes the order. The measurement, not the compute, is the bottleneck.

## Priority 1 — human labels (people, not GPUs; cost is annotator time, not estimated here)

The automatic judges call echoes, loops and off-topic text "refusals" in Roman Urdu (precision 0.53 and 0.60
against a reading of the responses). Until people label the responses, every steering comparison in Roman Urdu
is uncertain. Needed: two native Urdu speakers, a three-way label (refusal / answer / non-responsive) on the
2,016 test responses, plus review of the 576 prompts with the pack already prepared. This single purchase
would turn the post hoc reading into a result.

## Priority 2 — statistical power (~$4–8)

36 test families settle the script gap but not steering effects of 10–15 points. Four times as many families
(about 150 in test) at seven arms is roughly 8,400 generations plus judging: three to four hours on one T4, or
an hour on an A10G.

## Priority 3 — is it Tiny Aya Fire, or everyone? (~$3–6)

The same protocol on Tiny Aya Global and on one model from another family. If the Roman-Urdu harm signal is
weak everywhere, the finding is about training data for romanized text, not about one model.

## Priority 4 — fix the cause rather than steer around it (~$10–25)

The mechanism result says the model forms a harm signal half as strong for Roman Urdu. Steering adds a fixed
vector and cannot make the model recognise what it does not recognise. More promising: a small LoRA on
romanized refusal data, or a per-script strength schedule, evaluated with the same frozen test and human labels.

## Priority 5 — longer responses and adversarial prompts (~$2–4)

Responses were capped at 64 tokens. With 256 tokens some "non-responsive" Roman-Urdu answers may turn into real
compliance. Also a second Roman-Urdu spelling convention and simple jailbreak wrappers.

## What we would not buy

- Larger models for their own sake: the question is about a language, and Tiny Aya is the family with
  documented coverage of it.
- More runs on the current test set. It was run once; rerunning it to chase an effect would defeat its purpose.
- A serving stack or dashboard. The replay demo shows the recorded evidence, which is the point.
