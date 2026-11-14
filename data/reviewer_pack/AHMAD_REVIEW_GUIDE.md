# Review guide for Ahmad

Thank you for doing this. It is the one thing in the project that only a person who reads Urdu can do.

## What you are checking

The dataset has 72 **matched sets**. Each set has one harmful request and one harmless request about the same
topic, and each request exists in Urdu script and in Roman Urdu. The whole study rests on one assumption: the
Urdu-script sentence and the Roman-Urdu sentence say **the same thing**, and both read like something a person
would actually write. An LLM wrote the first drafts, so nobody has confirmed this yet.

You are not asked to be a linguist. Your review is recorded as **one participant-provided review by the project
author, a native Urdu / Roman Urdu speaker**. It is never described as an independent expert panel, a professional
translation certification or a consensus of several reviewers.

## What to do for each request

Read the Urdu-script sentence and the Roman-Urdu sentence, then answer:

| Field | Question | Answer |
|---|---|---|
| `ur` | Is the Urdu natural? کیا کوئی واقعی ایسے لکھے گا؟ | 1 to 5, or `U` if you cannot judge |
| `ro` | Is the Roman Urdu natural? Would someone type it like this? | 1 to 5, or `U` |
| `same` | Do the Urdu and the Roman Urdu mean the same thing? | `y`, `n` or `?` |
| `label` | Is the label right? "harmful" = an assistant should refuse; "harmless" = an assistant should help | `y`, `n` or `?` |
| `alt` | (test sets only, optional) Is the "other spelling" also a normal way to write it? | `y`, `n` or `?` |
| `pair` | (once per set) Do the harmful and the harmless request fit together as a pair on the same topic? | `y`, `n` or `?` |

Scale for `ur` and `ro`: 5 = completely natural, 4 = fine, 3 = understandable but a bit odd, 2 = awkward,
1 = wrong or not understandable.

If a sentence should be different, write the sentence you would use. For Roman Urdu, write it the way you
would type it yourself; that is exactly what is needed.

## Three rules

1. **Do not make a harmful request more detailed.** The harmful requests only say what someone wants. If you
   improve the language, keep it just as vague.
2. **Do not change what is being asked.** If you think the request itself or its label is wrong, say so in a
   note. Do not rewrite it into a different request. One exception: if the harmless request does not fit the
   harmful one (`pair=n`), you may propose another harmless request. Give it in English, Urdu and Roman Urdu
   (`fix <family> B en: ...`, `ur: ...`, `ro: ...`). It is recorded as a replacement, and the set stays out of
   comparisons between harmful and harmless requests until the replacement has been reviewed on its own.
3. **A blank means "not reviewed".** Nothing counts as approved unless you say so. If you are unsure, write `?`.
4. **Write the corrected sentence itself, in the same message as the ratings.** If you say that a sentence should
   change but the new sentence does not arrive, the pair is recorded as "correction pending", the original
   sentence stays, and nothing is written in its place.

## How to send your answers

**Easiest:** open a batch file, copy the answer block at its end, fill in the blanks and paste it into the chat.

```
ddos_site H  ur=5  ro=4  same=y  label=y  alt=y
ddos_site B  ur=5  ro=5  same=y  label=y  alt=y
ddos_site pair=y
fix ddos_site H ro: <the Roman Urdu sentence you would write>
note ddos_site: <anything else>
```

If a whole set is fine in every respect, one line is enough: `ddos_site: all good`.

**Or:** edit `AHMAD_REVIEW.csv` in a spreadsheet (the columns from `ur_naturalness_1to5_or_U` to `comments`)
and send the file back.

## Order and time

| Batches | Families | Why in this order |
|---|---|---|
| 01 to 06 | the 36 test families | the main result is measured on these |
| 07 and 08 | the 12 development families | used to choose the steering layer and strength |
| 09 to 12 | the 24 calibration families | used to compute the steering vectors |

Each batch has 6 sets (12 requests) and takes about 10 to 15 minutes. Batches 01 to 04 already cover 24 sets;
every batch you finish makes the dataset claim stronger, and you can stop at any point.

## What happens to your answers

Each request gets one status: **accepted**, **corrected**, **correction pending** (you announced a correction, its
text has not arrived), **rejected**, **uncertain** or **unable to judge**.

- The published dataset (v0.2.0) is never edited. Your ratings and corrections go into a **review revision**: a
  separate file ([`data/revisions/`](../revisions/README.md)) that keeps, for every pair you reviewed, the
  original sentence, your sentence, your ratings, the date, the reason and your name next to each other.
- A correction is applied to the revision when you say it should be. A corrected harmful request that reads
  more detailed than the original is held back, and you are asked first.
- If a correction would change whether a request is harmful, it is set aside and discussed separately. A
  replacement of a harmless request is recorded as a replacement, not as a wording fix.
- If you improve the wording of a request and also give its English sentence in the new wording, say that it is
  a wording change ("improve the wording"). Without that, a changed English sentence is recorded as a replacement
  of the request.
- Every answer you send starts a new review revision (`0.3.0-draft.1`, `0.3.0-draft.2`, ...). The one before it is
  kept unchanged. The ledger of everything you have sent is `REVIEW_LEDGER.md`.
- Your Urdu and Roman-Urdu sentences are stored exactly as you wrote them, and nobody else writes Urdu or Roman
  Urdu in your name. If you replace a request and send it in Urdu and Roman Urdu only, the maintainer writes the
  English sentence and the one-line meaning that go with it, shows them to you, and the record says that those two
  are the maintainer's and not yours. Your own English, if you send it, takes their place.
- The results already published stay tied to v0.2.0 and its original sentences. A corrected sentence has not
  been run through the model, and no published number is described as if it had been.

## Files

| File | What it is |
|---|---|
| `AHMAD_REVIEW_BATCH_01.md` to `_12.md` | the batches, six sets each, with the answer block |
| `AHMAD_REVIEW.csv` | all 144 requests in one sheet, same order |
| `returns/` | your answers are saved here exactly as you sent them (a message is kept as it arrived, with a line-by-line transcription next to it) |
| `review_status.json` | the status of every request (written by `scripts/import_review.py`) |
| [`../revisions/`](../revisions/README.md) | the review revisions built from your answers (written by `scripts/build_dataset_revision.py`) |
| `review_sheet.csv`, `review_template.jsonl`, `INSTRUCTIONS.md` | the original reviewer pack, kept unchanged |
