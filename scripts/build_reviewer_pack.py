#!/usr/bin/env python3
"""Build the bilingual Urdu / Roman Urdu reviewer package (approved Change 4).

Produces:
  data/reviewer_pack/review_sheet.csv   — one row per matched set, easy to edit
  data/reviewer_pack/INSTRUCTIONS.md    — bilingual instructions
  data/reviewer_pack/review_template.jsonl — machine-readable return format

Nothing here claims validation happened. Every record starts 'unreviewed'.
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import load_corpus, load_records

OUT = ROOT / "data/reviewer_pack"
OUT.mkdir(parents=True, exist_ok=True)
recs, CORPUS = load_corpus(ROOT)
by_pair = defaultdict(dict)
meta = {}
for r in recs:
    by_pair[r["pair_id"]][r["form"]] = r["text"]
    meta[r["pair_id"]] = r

rows = []
for pair in sorted(by_pair):
    m = meta[pair]
    rows.append({
        "pair_id": pair, "family_id": m["family_id"], "safety_label": m["safety_label"],
        "split": m["split"], "intended_meaning_en": m["intended_meaning_en"],
        "ur_script": by_pair[pair].get("ur",""), "roman_urdu": by_pair[pair].get("ro",""),
        "code_mixed": by_pair[pair].get("cm",""), "english_reference": by_pair[pair].get("en",""),
        # --- reviewer fills these ---
        "ur_naturalness_1to5": "", "ro_naturalness_1to5": "", "cm_naturalness_1to5": "",
        "semantic_equivalence_1to5": "", "safety_label_correct_yes_no": "",
        "roman_spelling_style_A_or_B": "", "corrected_ur": "", "corrected_ro": "",
        "corrected_cm": "", "reviewer_id": "", "notes": "",
    })
with (OUT / "review_sheet.csv").open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

(OUT / "review_template.jsonl").write_text("".join(json.dumps({
    "pair_id": r["pair_id"], "reviewer_id": None,
    "ur_naturalness": None, "ro_naturalness": None, "cm_naturalness": None,
    "semantic_equivalence": None, "safety_label_correct": None,
    "roman_style": None, "corrected_ur": None, "corrected_ro": None,
    "corrected_cm": None, "verdict": "pending", "notes": "",
}, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

(OUT / "INSTRUCTIONS.md").write_text("""# ScriptShield — Bilingual Reviewer Pack
# جائزہ لینے والوں کے لیے ہدایات

**Status: NOT YET REVIEWED. No language-quality claim is made until this pack is returned.**

Thank you / شکریہ. You are checking whether our Urdu and Roman Urdu prompts are
natural and whether they mean the same thing. You are **not** being asked to
produce harmful content — the harmful items are deliberately vague requests.

## What each row contains
- `intended_meaning_en` — what the item is supposed to mean
- `ur_script` — Urdu in Perso-Arabic script / اردو رسم الخط
- `roman_urdu` — the same request in Roman Urdu
- `code_mixed` — Urdu-English mixed / اردو انگریزی ملا کر
- `english_reference` — English reference (not part of the primary comparison)

## What to fill in / آپ کو کیا بھرنا ہے

1. **Naturalness (1–5)** for `ur`, `ro`, `cm` separately.
   قدرتی پن: کیا کوئی مقامی بولنے والا واقعی ایسے کہے گا؟
   - 1 = unnatural / غیر فطری, 5 = completely natural / بالکل فطری
2. **Semantic equivalence (1–5)** — do all forms ask the *same* thing?
   معنوی مطابقت: کیا سب شکلیں ایک ہی بات پوچھ رہی ہیں؟
   - 1 = different meaning, 5 = identical meaning
3. **Safety label correct? (yes/no)** — `harmful` should deserve a refusal;
   `benign` should deserve a helpful answer.
   حفاظتی لیبل درست ہے؟
4. **Roman spelling style** — A (e.g. "kaise", "nahi", "mein") or
   B (e.g. "kese", "nai", "mai"). Mark whichever the row actually uses.
5. **Corrections** — if a form is wrong, type the corrected text in
   `corrected_ur` / `corrected_ro` / `corrected_cm`. Leave blank if fine.
6. **reviewer_id** — your name or a pseudonym you consent to us crediting.

## Important / اہم
- Please **do not** make harmful items more specific or actionable. If an item
  is too explicit, flag it in `notes` and we will soften it.
  برائے مہربانی نقصان دہ درخواستوں کو مزید واضح یا قابلِ عمل نہ بنائیں۔
- If you are unsure, write `unsure` in `notes` rather than guessing.
- Blank cells mean "not reviewed", never "approved".

## How to return
Edit `review_sheet.csv` and send it back, or fill `review_template.jsonl`.
We will import your judgments, set `validation_status`, and credit you.
""", encoding="utf-8")
print(f"reviewer pack: {len(rows)} matched sets -> {OUT.relative_to(ROOT)}")
print("files: review_sheet.csv, review_template.jsonl, INSTRUCTIONS.md")
print("STATUS: unreviewed. No validation claimed.")
