#!/usr/bin/env python3
"""Family-level quality audit of the ScriptShield corpus.

Writes  data/quality/family_audit_v<version>.json  and  docs/DATASET_QUALITY_AUDIT.md.

Four kinds of evidence are kept apart:
  * automatic checks      rule-based and reproducible (this script);
  * LLM reading notes     data/quality/llm_audit_notes_v<version>.json, suggestions only;
  * human review          data/reviewer_pack/review_status.json, written by import_review.py;
  * outcome data          the public evaluation log, used for one descriptive table.
Nothing here changes a prompt.
"""
from __future__ import annotations

import collections
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import load_corpus  # noqa: E402

VERSION = "0.2.0"
SPLIT_ORDER = {"test": 0, "dev": 1, "calibration": 2}
# Urdu function words with one fixed Roman spelling in this corpus: used to detect a word that was
# replaced by a synonym (or dropped) when the Roman-Urdu version was written.
FUNCTION_WORDS = {"بغیر": ["baghair"], "تاکہ": ["takay"], "کیسے": ["kaise"], "اور": ["aur"], "نہیں": ["nahi"],
                  "اجازت": ["ijazat"], "چپکے": ["chupkay"], "پہلے": ["pehle"], "کبھی": ["kabhi"]}
RO_STOP = set("main mein kaise ke ki ka ko se par aur hoon sakta sakti karoon apne apni apna kisi woh us un is hai hain ho "
              "kar na mujhe mere meri mera to ya jo ek aik koi kya liye takay ne tak bhi hi usay isay pata chalay chal bina "
              "baghair chahiye sakay sakein jaye kab kahan".split())
# Pairs of DIFFERENT words that the spelling-insensitive key below would merge (checked by reading them).
DISTINCT_WORDS = [{"kar", "kaar"}, {"kam", "kaam"}, {"har", "haar"}, {"dar", "daar"}, {"hoon", "hon"}]


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s]


def speech_act(en: str) -> dict:
    """Sentence type of the English reference. `kind` is the type of the last sentence."""
    sents = sentences(en)
    last = sents[-1]
    if not last.endswith("?"):
        kind = "command"
    elif re.match(r"How (many|much)\b", last):
        kind = "how-much"
    elif last.startswith("How"):
        kind = "how"
    elif re.match(r"(What|Where|Which|When|Who)\b", last):
        kind = "what/where"
    else:
        kind = "other question"
    return {"kind": kind, "context_sentence": len(sents) > 1, "is_command": kind == "command",
            "label": ("situation + " if len(sents) > 1 else "") + kind}


def pair_form(h: dict, b: dict) -> str:
    if h["is_command"] != b["is_command"]:
        return "different"
    if h["kind"] == b["kind"] and h["context_sentence"] == b["context_sentence"]:
        return "same"
    return "similar"


def is_question(text: str) -> bool:
    return text.strip().endswith(("?", "؟"))


def ro_key(tok: str) -> str:
    """Spelling-insensitive key for a Roman-Urdu word (long vowels and the -ay ending are collapsed)."""
    t = tok.lower()
    t = re.sub(r"ay$", "e", t)
    t = t.replace("aa", "a").replace("ee", "i").replace("oo", "u").replace("ai", "e")
    return re.sub(r"on$", "un", t)


def tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+", text)


def main() -> int:
    check = "--check" in sys.argv[1:]            # compare with the committed files, write nothing
    stale: list[str] = []

    def emit(path: Path, text: str) -> None:
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    recs, _ = load_corpus(ROOT)
    fam: dict = collections.defaultdict(dict)
    for r in recs:
        fam[r["family_id"]][(r["safety_label"], r["form"])] = r
    notes_doc = json.loads((ROOT / f"data/quality/llm_audit_notes_v{VERSION}.json").read_text(encoding="utf-8"))
    status_path = ROOT / "data/reviewer_pack/review_status.json"
    review = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    human = review.get("rows", {})
    pair_verdicts = review.get("pair_verdicts", {})

    def human_detail(row_id: str) -> dict | None:
        r = human.get(row_id)
        if not r:
            return None
        return {k: r[k] for k in ("ur", "ro", "same", "label", "alt", "correction_kind", "pending_fields", "review_date", "review_batch",
                                  "maintainer_fields") if k in r}

    # ---------------------------------------------------------------- per family
    out: dict = {}
    for f in sorted(fam, key=lambda x: (SPLIT_ORDER[fam[x][("harmful", "ur")]["split"]], fam[x][("harmful", "ur")]["harm_group"], x)):
        g = fam[f]
        sa = {lab: speech_act(g[(lab, "en")]["text"]) for lab in ("harmful", "benign")}
        flags = []
        for lab in ("harmful", "benign"):
            q = {form: is_question(g[(lab, form)]["text"]) for form in ("ur", "ro", "cm", "en")}
            if len(set(q.values())) > 1:
                flags.append({"type": "sentence_type_differs_between_forms", "label": lab, "detail": json.dumps(q)})
            ur, ro = g[(lab, "ur")]["text"], g[(lab, "ro")]["text"].lower()
            for word, romans in FUNCTION_WORDS.items():
                n_ur = len(re.findall(rf"(?<![\u0600-\u06FF]){word}(?![\u0600-\u06FF])", ur))
                n_ro = sum(len(re.findall(rf"\b{x}\b", ro)) for x in romans)
                if n_ur != n_ro:
                    flags.append({"type": "word_differs_between_scripts", "label": lab,
                                  "detail": f"Urdu script has '{word}' {n_ur}x, Roman Urdu has '{romans[0]}' {n_ro}x"})
        out[f] = {"family_id": f, "split": g[("harmful", "ur")]["split"], "harm_group": g[("harmful", "ur")]["harm_group"],
                  "speech_act": sa, "pair_form": pair_form(sa["harmful"], sa["benign"]), "automatic_flags": flags,
                  "llm_notes": notes_doc["notes"].get(f, []),
                  "human_review": {lab: human.get(f"{f}-{lab}", {}).get("status", "unreviewed") for lab in ("harmful", "benign")},
                  "human_review_detail": {"harmful": human_detail(f"{f}-harmful"), "benign": human_detail(f"{f}-benign"),
                                          "pair_comparable": pair_verdicts.get(f)}}

    # ---------------------------------------------------------------- corpus level
    sa_counts = {lab: collections.Counter(v["speech_act"][lab]["kind"] for v in out.values()) for lab in ("harmful", "benign")}
    ctx_counts = {lab: sum(v["speech_act"][lab]["context_sentence"] for v in out.values()) for lab in ("harmful", "benign")}
    cmd_by_split = {s: {lab: [sum(v["speech_act"][lab]["is_command"] for v in out.values() if v["split"] == s),
                              sum(1 for v in out.values() if v["split"] == s)] for lab in ("harmful", "benign")}
                    for s in ("calibration", "dev", "test")}
    pair_counts = collections.Counter(v["pair_form"] for v in out.values())
    pair_by_split = {s: collections.Counter(v["pair_form"] for v in out.values() if v["split"] == s) for s in ("test", "dev", "calibration")}

    variants: dict = collections.defaultdict(collections.Counter)
    where: dict = collections.defaultdict(set)
    for r in recs:
        if r["form"] == "ro":
            for t in tokens(r["text"]):
                variants[ro_key(t)][t.lower()] += 1
                where[t.lower()].add(r["family_id"])
    spelling = sorted(((k, dict(v)) for k, v in variants.items()
                       if len(v) > 1 and len(k) > 2 and set(v) not in DISTINCT_WORDS), key=lambda kv: -sum(kv[1].values()))

    def content(f, lab="harmful"):
        return {ro_key(t) for t in tokens(fam[f][(lab, "ro")]["text"]) if t.lower() not in RO_STOP and len(t) > 2}
    sims = []
    for a, b in itertools.combinations(sorted(fam), 2):
        sa_, sb_ = out[a]["split"], out[b]["split"]
        if (sa_ == "test") != (sb_ == "test"):
            ca, cb = content(a), content(b)
            j = len(ca & cb) / len(ca | cb)
            sims.append((round(j, 3), a if sa_ != "test" else b, b if sa_ != "test" else a, sorted(ca & cb)))
    sims.sort(reverse=True)

    norm_texts = [" ".join(r["text"].split()).lower() for r in recs]
    n_duplicates = len(norm_texts) - len(set(norm_texts))

    lengths = {form: {lab: round(sum(len(fam[f][(lab, form)]["text"].split()) for f in fam) / len(fam), 1)
                      for lab in ("harmful", "benign")} for form in ("ur", "ro", "en")}

    summary = {"version": VERSION, "n_families": len(out), "speech_act_counts": {k: dict(v) for k, v in sa_counts.items()},
               "context_sentence_counts": ctx_counts, "commands_by_split": cmd_by_split, "pair_form_counts": dict(pair_counts),
               "pair_form_by_split": {k: dict(v) for k, v in pair_by_split.items()},
               "n_word_differs_between_scripts": sum(1 for v in out.values() for x in v["automatic_flags"] if x["type"] == "word_differs_between_scripts"),
               "n_sentence_type_differs": sum(1 for v in out.values() for x in v["automatic_flags"] if x["type"] == "sentence_type_differs_between_forms"),
               "exact_duplicate_texts": n_duplicates, "roman_spelling_variants": spelling[:40], "cross_split_similarity_top": sims[:10], "mean_words": lengths,
               "human_review_counts": dict(collections.Counter(s for v in out.values() for s in v["human_review"].values())),
               "llm_note_counts": dict(collections.Counter(n["type"] for v in out.values() for n in v["llm_notes"]))}
    emit(ROOT / f"data/quality/family_audit_v{VERSION}.json",
         json.dumps({"summary": summary, "families": out}, indent=1, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------------- report
    hr = summary["human_review_counts"]
    n_rev = sum(v for k, v in hr.items() if k != "unreviewed")
    cal = cmd_by_split["calibration"]
    W = []
    A = W.append
    A("# Dataset quality audit: ScriptShield corpus v" + VERSION)
    A("")
    A("_Generated by `scripts/audit_dataset.py`; do not edit by hand. Machine-readable version:_")
    A(f"_[`data/quality/family_audit_v{VERSION}.json`](../data/quality/family_audit_v{VERSION}.json)._")
    A("")
    A("This audit looks at all 72 intent families of the published corpus. It does not change any prompt: the")
    A("published version stays as it is. What the human reviewer says is recorded in")
    A("[`data/reviewer_pack/`](../data/reviewer_pack/), and corrected sentences go into a separate review revision")
    A("([`data/revisions/`](../data/revisions/README.md)) that keeps the original text.")
    A("")
    A("## 1. How to read the findings")
    A("")
    A("Each finding belongs to exactly one class of evidence.")
    A("")
    A("| Class | What it means | Where it comes from |")
    A("|---|---|---|")
    A("| **Confirmed (automatic)** | A rule-based check that anyone can re-run; the finding is a fact about the text | this script |")
    A("| **LLM suggestion** | An LLM agent read the prompts and noted a possible problem. Not a human judgement | `data/quality/llm_audit_notes_v" + VERSION + ".json` |")
    A("| **Needs human review** | Cannot be settled without a speaker of Urdu: naturalness, register, meaning | review pack |")
    A("| **Human-confirmed** | The reviewer checked it | `data/reviewer_pack/review_status.json` |")
    A("")
    reviewed_fams = [f for f, v in out.items() if v["human_review"]["harmful"] != "unreviewed" and v["human_review"]["benign"] != "unreviewed"]
    words = {"accepted": "accepted as they are", "corrected": "corrected", "correction_pending": "to be corrected (text not yet received)",
             "rejected": "rejected", "uncertain": "uncertain", "unable_to_judge": "not judged"}
    A(f"**Human review so far: {n_rev} of {2 * len(out)} prompt pairs reviewed ({len(reviewed_fams)} of {len(out)} families).** "
      + ("No finding below is human-confirmed yet." if n_rev == 0 else
         "One reviewer, the project author, a native Urdu / Roman Urdu speaker: a participant review, not an independent expert panel, "
         "not a professional translation certification, not a consensus of several reviewers. Result: "
         + ", ".join(f"{hr[k]} {words[k]}" for k in words if hr.get(k)) + ". Details in section 9. "
         "Everything else in this audit is still not human-confirmed."))
    A("")
    A("## 2. Summary")
    A("")
    A("| # | Finding | Class | Size | Does it affect the main result? |")
    A("|---|---|---|---|---|")
    A(f"| 1 | Harmful requests are more often commands (\"Write ...\"), harmless ones are almost always questions | Confirmed (automatic) | "
      f"{sa_counts['harmful']['command']} of 72 harmful vs {sa_counts['benign']['command']} of 72 harmless | Not the script gap (same sentence in both scripts). "
      f"It can affect the steering vector, which is harmful minus harmless on the calibration families ({cal['harmful'][0]} of {cal['harmful'][1]} harmful and "
      f"{cal['benign'][0]} of {cal['benign'][1]} harmless calibration prompts are commands) |")
    A(f"| 2 | Harmless requests more often start with a sentence describing a situation | Confirmed (automatic) | "
      f"{ctx_counts['benign']} of 72 harmless vs {ctx_counts['harmful']} of 72 harmful | Same as 1 |")
    A(f"| 3 | Sentence form of the harmful and the harmless request of a family | Confirmed (automatic) | same {pair_counts['same']}, similar {pair_counts['similar']}, "
      f"different {pair_counts['different']} of 72 | Same as 1 |")
    A(f"| 4 | A function word differs between the Urdu-script and the Roman-Urdu version | Confirmed (automatic) | {summary['n_word_differs_between_scripts']} prompts | "
      "Negligible: a synonym was used; listed in section 4 |")
    A(f"| 5 | Roman-Urdu spelling is not fully uniform | Confirmed (automatic) | {len(spelling)} words occur in more than one spelling | "
      "Negligible for the gap; relevant to the claim of one spelling convention |")
    A("| 6 | Calibration and test families are different families but share topics | Confirmed (automatic) | closest pairs in section 6 | "
      "By design; no text is shared across splits |")
    A(f"| 7 | Roman Urdu is a word-for-word transliteration of fairly formal Urdu | LLM suggestion, needs human review | {summary['llm_note_counts'].get('register', 0)} notes | "
      "Possibly: the measured gap is for this register; colloquial Roman Urdu was not tested |")
    A(f"| 8 | English reference and Urdu wording differ slightly | LLM suggestion, needs human review | {summary['llm_note_counts'].get('meaning_drift', 0)} notes | "
      "Not the script gap; touches the English row only |")
    A(f"| 9 | Exact duplicates among the 576 prompt texts | Confirmed (automatic) | {n_duplicates} | No |")
    pair_no = sorted(f for f in reviewed_fams if out[f]["human_review_detail"]["pair_comparable"] == "no")
    with_corr = [(f, lab) for f in reviewed_fams for lab in ("harmful", "benign") if (out[f]["human_review_detail"][lab] or {}).get("correction_kind")]
    if n_rev:
        A(f"| 10 | The reviewer wants some prompt pairs changed (the wording, or the request itself) | Human-confirmed | {len(with_corr)} of {n_rev} reviewed prompt pairs | "
          "Not known until the corrected sentences have been run. The reported numbers belong to the original sentences |")
        A(f"| 11 | The harmful and the harmless request of a family do not fit together as a pair | Human-confirmed | {len(pair_no)} of {len(reviewed_fams)} reviewed families | "
          "Not the script gap, which compares a harmful request with itself in two scripts. It weakens the harmless request as a matched control; "
          "see the robustness checks |")
    A("")
    A("## 3. Sentence form: commands and questions")
    A("")
    A("Each English reference was classified by the form of its last sentence. The Urdu-script, Roman-Urdu and")
    A(f"code-mixed versions were checked to end as the same kind of sentence (question or not): {summary['n_sentence_type_differs']} disagreements"
      + ("." if not summary['n_sentence_type_differs'] else ", all in the code-mixed version, which is not part of the main comparison: "
         + ", ".join(f"`{f}` ({x['label']})" for f, v in out.items() for x in v["automatic_flags"] if x["type"] == "sentence_type_differs_between_forms") + "."))
    A("")
    kinds = ["how", "how-much", "what/where", "other question", "command"]
    A("| Form of the request | Harmful (of 72) | Harmless (of 72) |")
    A("|---|---|---|")
    for k in kinds:
        A(f"| {k} | {sa_counts['harmful'].get(k, 0)} | {sa_counts['benign'].get(k, 0)} |")
    A(f"| starts with a sentence describing a situation | {ctx_counts['harmful']} | {ctx_counts['benign']} |")
    A("")
    A("| Split | Harmful commands | Harmless commands | Pair form: same / similar / different |")
    A("|---|---|---|---|")
    for s in ("calibration", "dev", "test"):
        p = pair_by_split[s]
        A(f"| {s} | {cmd_by_split[s]['harmful'][0]} of {cmd_by_split[s]['harmful'][1]} | {cmd_by_split[s]['benign'][0]} of {cmd_by_split[s]['benign'][1]} | "
          f"{p['same']} / {p['similar']} / {p['different']} |")
    A("")
    A("\"Same\": same kind of sentence and both with or both without a situation sentence. \"Similar\": both questions (or")
    A("both commands) of different kinds. \"Different\": one is a command and the other a question.")
    A("")
    A("**Why it matters.** The steering vector is the mean activation of harmful prompts minus that of harmless")
    A("prompts. If harmful prompts are more often commands, part of that difference is \"command versus question\" and")
    A("not \"harmful versus harmless\". This was not controlled for and is a limitation of the vector. It does not touch")
    A("the script gap, which compares the same harmful sentence in two scripts.")
    A("")
    A("Whether the measured script gap differs between commands and questions, and whether it depends on the families")
    A("flagged in this audit, is examined in [ROBUSTNESS_CHECKS.md](ROBUSTNESS_CHECKS.md) (post hoc, from the public")
    A("evaluation logs). This audit itself uses no model output: it is computed from the corpus, the LLM reading notes")
    A("and the review status, and can be regenerated in any clone.")
    A("")
    A("## 4. Differences between the Urdu-script and the Roman-Urdu version")
    A("")
    A("The Roman-Urdu version is meant to be the same sentence in Latin letters. For nine common function words with")
    A("one fixed Roman spelling in this corpus, the two versions were compared word by word.")
    A("")
    rows4 = [(f, x) for f, v in out.items() for x in v["automatic_flags"] if x["type"] == "word_differs_between_scripts"]
    if rows4:
        A("| Family | Split | Prompt | Difference |")
        A("|---|---|---|---|")
        for f, x in rows4:
            A(f"| `{f}` | {out[f]['split']} | {x['label']} | {x['detail']} |")
        A("")
        if all("'بغیر'" in x["detail"] and re.search(r"\bbina\b", fam[f][(x["label"], "ro")]["text"].lower()) for f, x in rows4):
            A("In each case the Roman-Urdu version uses the synonym *bina* where the Urdu script has *baghair* (both mean")
            A("\"without\"). The meaning is unchanged. These are candidates for correction in the next version.")
    else:
        A("No difference found.")
    A("")
    A("This check covers function words only. Whether every content word matches needs a human reader.")
    A("")
    A("## 5. Roman-Urdu spelling")
    A("")
    A("The corpus was written in one spelling style (*kaise, nahi, mein, hoon*, long vowels doubled, final *-ay*).")
    A("Words that nevertheless occur in more than one spelling (after collapsing doubled vowels and the *-ay* ending):")
    A("")
    A("| Spellings found (occurrences) | Families using the rarer spelling |")
    A("|---|---|")
    for k, v in spelling[:25]:
        forms = sorted(v.items(), key=lambda kv: -kv[1])
        rare = sorted(set().union(*[where[t] for t, _ in forms[1:]]))
        A(f"| {', '.join(f'{t} ({n})' for t, n in forms)} | {', '.join('`' + x + '`' for x in rare[:6])}{' ...' if len(rare) > 6 else ''} |")
    A("")
    A("Most of the rarer spellings come from the 24 pilot families, which were written first. A second, deliberately")
    A("different spelling style has been drafted for the 36 test families and waits for the reviewer")
    A("(`roman_urdu_alt_candidate` in the review sheet). It is not part of any published result.")
    A("")
    A("## 6. Topic overlap between splits")
    A("")
    A("Splits are by family, so no prompt text is shared. Families in different splits can still be about similar")
    A("things. The closest pairs of harmful prompts (calibration or development versus test), by shared content words:")
    A("")
    A("| Overlap | Calibration / development family | Test family | Shared words |")
    A("|---|---|---|---|")
    for j, a, b, sh in sims[:8]:
        A(f"| {j:.2f} | `{a}` ({out[a]['split']}) | `{b}` | {', '.join(sh[:8])} |")
    A("")
    A("The steering vector is meant to generalise across topics, so some overlap is expected. No pair shares more")
    A(f"than {max(len(x[3]) for x in sims[:8])} content words.")
    A("")
    A("## 7. Length")
    A("")
    A("| Mean words per prompt | Harmful | Harmless |")
    A("|---|---|---|")
    for form, name in (("ur", "Urdu script"), ("ro", "Roman Urdu"), ("en", "English")):
        A(f"| {name} | {lengths[form]['harmful']} | {lengths[form]['benign']} |")
    A("")
    A("## 8. LLM reading notes (suggestions for the reviewer)")
    A("")
    A(notes_doc["coverage"])
    A("")
    A("| Type | Notes | Meaning |")
    A("|---|---|---|")
    for t, n in sorted(summary["llm_note_counts"].items(), key=lambda kv: -kv[1]):
        A(f"| {t} | {n} | {notes_doc['types'][t]} |")
    A("")
    A("The most general note is about **register**. The Roman-Urdu prompts keep the wording of the Urdu-script")
    A("prompts so that only the script differs. That makes the comparison clean, but some Roman-Urdu sentences use")
    A("formal Urdu words where a person texting would use the English word. Whether the gap is as large for")
    A("colloquial Roman Urdu is not known.")
    A("")
    A("## 9. Human review so far")
    A("")
    if not n_rev:
        A("No prompt pair has been reviewed yet.")
        A("")
    else:
        dates = sorted({d["review_date"] for f in reviewed_fams for d in (out[f]["human_review_detail"]["harmful"], out[f]["human_review_detail"]["benign"])
                        if d and d.get("review_date")})
        A(f"Reviewed: {n_rev} of {2 * len(out)} prompt pairs, in {len(reviewed_fams)} of {len(out)} families "
          f"({', '.join(str(sum(1 for f in reviewed_fams if out[f]['split'] == sp)) + ' ' + sp for sp in ('test', 'dev', 'calibration'))}). "
          + (f"Review date: {', '.join(dates)}. " if dates else "")
          + "Reviewer: the project author, a native Urdu / Roman Urdu speaker. This is one participant-provided review. It is not an")
        A("independent expert panel, not a professional translation certification and not a consensus of several reviewers.")
        A("")
        A("Ratings are 1 to 5 (5 = completely natural). \"Same\" = the Urdu-script and the Roman-Urdu sentence mean the same. \"Label\" = the")
        A("harmful or harmless label is right. \"2nd spelling\" = the second Roman-Urdu spelling drafted by rule is also natural. \"Pair\" = the")
        A("harmful and the harmless request fit together as a pair on the same topic.")
        A("")
        A("| Batch | Family | Request | Urdu | Roman Urdu | Same | Label | 2nd spelling | Status | Pair |")
        A("|---|---|---|---:|---:|---|---|---|---|---|")
        for f in sorted(reviewed_fams, key=lambda x: (out[x]["human_review_detail"]["harmful"].get("review_batch", ""), reviewed_fams.index(x))):
            for lab, tag in (("harmful", "H"), ("benign", "B")):
                d = out[f]["human_review_detail"][lab]
                A(f"| {d.get('review_batch', '')} | `{f}` | {tag} | {d.get('ur', '')} | {d.get('ro', '')} | {d.get('same', '')} | {d.get('label', '')} | "
                  f"{d.get('alt', '')} | {words[out[f]['human_review'][lab]]} | {out[f]['human_review_detail']['pair_comparable'] or ''} |")
        A("")
        details = [out[f]["human_review_detail"][lab] for f in reviewed_fams for lab in ("harmful", "benign")]
        urs, ros = [d["ur"] for d in details if isinstance(d.get("ur"), int)], [d["ro"] for d in details if isinstance(d.get("ro"), int)]
        A("**What the reviewer confirmed.**")
        A("")
        A(f"- Same meaning in both scripts: {sum(1 for d in details if d.get('same') == 'yes')} of {len(details)} reviewed prompt pairs. "
          "This is the property the script comparison rests on.")
        A(f"- Label right: {sum(1 for d in details if d.get('label') == 'yes')} of {len(details)}.")
        if urs and ros:
            A(f"- Naturalness: Urdu script {sum(urs) / len(urs):.1f} on average (lowest {min(urs)}), Roman Urdu {sum(ros) / len(ros):.1f} (lowest {min(ros)}).")
        alts = [d["alt"] for d in details if "alt" in d]
        if alts:
            A(f"- Second Roman-Urdu spelling natural: {sum(1 for x in alts if x == 'yes')} of {len(alts)} that he judged. These spellings belong to the "
              "original sentences; no result uses them yet.")
        A("")
        A("**What the reviewer wants changed.**")
        A("")
        if with_corr:
            waiting = [(f, lab) for f, lab in with_corr if out[f]["human_review_detail"][lab].get("pending_fields")]
            repl = [(f, lab) for f, lab in with_corr if out[f]["human_review_detail"][lab]["correction_kind"] == "replacement"]
            A(f"- He asked for changes to {len(with_corr)} prompt pairs: "
              + ", ".join(f"`{f}` {'H' if lab == 'harmful' else 'B'}" + (" (replacement of the request)" if (f, lab) in repl else "") for f, lab in with_corr) + ".")
            if waiting:
                A(f"- The corrected text of {len(waiting)} of them has not been received. Nothing was written in its place: the original sentences stand, "
                  "and the review revision lists these corrections as waiting.")
            if len(waiting) < len(with_corr):
                A(f"- The corrected sentences of {len(with_corr) - len(waiting)} of them are recorded in the review revision, next to the originals. "
                  "They have not been run through a model.")
            A("- A replacement changes what is asked. It is recorded as a new request, never as a wording fix.")
            drafted = [(f, lab) for f, lab in with_corr if out[f]["human_review_detail"][lab].get("maintainer_fields")]
            if drafted:
                A("- Every changed Urdu and Roman-Urdu sentence is the reviewer's own, character for character. For "
                  + ", ".join(f"`{f}` {'H' if lab == 'harmful' else 'B'}" for f, lab in drafted)
                  + " the English-language description that goes with his replacement ("
                  + " and ".join({"en": "the English sentence", "meaning": "the one-line intended meaning"}[k]
                                 for f, lab in drafted for k in out[f]["human_review_detail"][lab]["maintainer_fields"])
                  + ") was written by the maintainer and is marked so in the revision.")
            by_label = {lab: [(f, x) for f, x in with_corr if x == lab] for lab in ("harmful", "benign")}
            low = [(f, lab) for f in reviewed_fams for lab in ("harmful", "benign")
                   if any(isinstance(out[f]["human_review_detail"][lab].get(k), int) and out[f]["human_review_detail"][lab][k] <= 3 for k in ("ur", "ro"))]
            A(f"- By kind of request: of {len(reviewed_fams)} reviewed harmful requests he asked for a change in {len(by_label['harmful'])} "
              f"({sum(1 for x in by_label['harmful'] if x in repl)} of them a replacement); of {len(reviewed_fams)} reviewed harmless requests in "
              f"{len(by_label['benign'])} ({sum(1 for x in by_label['benign'] if x in repl)} of them a replacement). "
              + (f"Naturalness of 3 or lower: {len(low)} prompt pairs (" + ", ".join(f"`{f}` {'H' if lab == 'harmful' else 'B'}" for f, lab in low)
                 + f"), {'all' if all(x in with_corr for x in low) else 'not all'} of which he corrected." if low else "No rating of 3 or lower."))
            A(f"- These rates come from {len(reviewed_fams)} families. They are the only estimate there is for the {len(out) - len(reviewed_fams)} families "
              "that have not been reviewed, and a rough one.")
        else:
            A("- No correction so far.")
        if pair_no:
            A(f"- Pairing not comparable: {', '.join('`' + f + '`' for f in pair_no)}. A family with this verdict is left out of every comparison between harmful and "
              "harmless requests on revised data, also if its harmless request is replaced, until a comparable replacement has been reviewed separately.")
        A("")
        batch_notes = {b: v["reviewer_note"] for b, v in sorted(review.get("batches", {}).items()) if v.get("reviewer_note")}
        if batch_notes:
            A("**The reviewer's own summary, by batch.**")
            A("")
            for b, text in batch_notes.items():
                A(f"- Batch {b}: \"{text}\"")
            A("")
        A("**How this compares with the automatic checks and the LLM notes** (reviewed prompt pairs only).")
        A("")
        noted = [(f, lab) for f in reviewed_fams for lab in ("harmful", "benign") if any(n["label"] == lab for n in out[f]["llm_notes"])]
        flagged = [(f, lab) for f in reviewed_fams for lab in ("harmful", "benign")
                   if any(x["label"] == lab and x["type"] == "word_differs_between_scripts" for x in out[f]["automatic_flags"])]
        A(f"- Prompt pairs with an LLM note: {len(noted)}. The reviewer announced a correction for {sum(1 for x in noted if x in with_corr)} of them"
          f" and for {sum(1 for x in with_corr if x not in noted)} prompt pair(s) without a note.")
        A(f"- Prompt pairs where the automatic check found a different function word in the two scripts: {len(flagged)}. "
          f"The reviewer judged the meaning the same in {sum(1 for f, lab in flagged if out[f]['human_review_detail'][lab].get('same') == 'yes')} of them.")
        forms = collections.Counter((out[f]["pair_form"], out[f]["human_review_detail"]["pair_comparable"]) for f in reviewed_fams)
        A("- Sentence form of the pair (automatic) against the reviewer's pair verdict: "
          + "; ".join(f"form {a}, verdict {b or 'none'}: {n}" for (a, b), n in sorted(forms.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))) + ".")
        A("")
        A("**What this does and does not establish.** The reviewed families are " + f"{len(reviewed_fams)} of {len(out)}" + "; the other families are still")
        A("unreviewed, and one reviewer who is also the author is not independent validation. The reported results were computed")
        A("on the original sentences and stay with dataset version " + VERSION + ". No corrected sentence has been run through a model.")
        A("")
    A("## 10. All 72 families")
    A("")
    A("H = harmful request, B = harmless request. \"Auto\" counts automatic flags, \"LLM\" counts reading notes.")
    A("")
    A("| Family | Split | Topic group | H form | B form | Pair form | Auto | LLM | Human review (H / B) |")
    A("|---|---|---|---|---|---|---|---|---|")
    for f, v in out.items():
        A(f"| `{f}` | {v['split']} | {v['harm_group']} | {v['speech_act']['harmful']['label']} | {v['speech_act']['benign']['label']} | {v['pair_form']} | "
          f"{len(v['automatic_flags'])} | {len(v['llm_notes'])} | {v['human_review']['harmful'].replace('_', ' ')} / {v['human_review']['benign'].replace('_', ' ')} |")
    A("")
    A("## 11. What this audit did not check")
    A("")
    A("- Whether the Urdu is natural, and whether a speaker would phrase a request this way: needs a human (section 9 for the families reviewed so far).")
    A("- Whether every content word of the Roman-Urdu version matches the Urdu-script version: only nine function words were compared automatically.")
    A("- The Urdu-script text of the calibration and development families was not read by the LLM agent in this pass.")
    A("- The code-mixed and English versions beyond the sentence-type check.")
    A("")
    A("## 12. Reproduce")
    A("")
    A("```bash")
    A("python3 scripts/audit_dataset.py            # rewrites this file and the JSON")
    A("python3 scripts/audit_dataset.py --check    # only compares; exit code 1 if the committed files are stale")
    A("```")
    emit(ROOT / "docs/DATASET_QUALITY_AUDIT.md", "\n".join(W) + "\n")
    if check:
        print("stale: " + ", ".join(stale) if stale else "audit outputs are up to date")
        return 1 if stale else 0
    print(f"audit written: {len(out)} families | pair form {dict(pair_counts)} | commands harmful/benign "
          f"{sa_counts['harmful']['command']}/{sa_counts['benign']['command']} | script word differences {summary['n_word_differs_between_scripts']} | "
          f"spelling variants {len(spelling)} | human-reviewed pairs {n_rev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
