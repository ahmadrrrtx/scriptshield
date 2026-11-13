# ScriptShield — Bilingual Reviewer Pack
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
