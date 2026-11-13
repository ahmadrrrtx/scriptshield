"""HTML rendering for the replay demo. Pure Python: no gradio, no model.

Every string that came from a model or a dataset is escaped. Withheld responses are never
rendered (the data file does not contain them in the first place).
"""
from __future__ import annotations

import html

FORMS = (("ur", "Urdu script"), ("ro", "Roman Urdu"), ("cm", "Code-mixed"), ("en", "English"))
CHIP = {"refusal": "#1b7a4e;background:#e3f3ea", "compliance": "#a23b2a;background:#fbe9e5",
        "invalid": "#7a5b00;background:#fbf1cf", "unknown": "#4b4f58;background:#e9e9ec"}
CELL = "padding:9px 11px;border-bottom:1px solid #dcdad2;vertical-align:top;text-align:left"
READ_AS = {"R": "refusal", "A": "answer", "N": "non-responsive"}


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.1f} %"


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


def family_choices(data: dict) -> list[str]:
    return [f"{f['family_id']}  ·  {f.get('harm_group') or ''}" for f in data["families"]]


def summary_html(data: dict) -> str:
    cols = (("ur/harmful", "Harmful · Urdu script", "#1f5f8b"), ("ro/harmful", "Harmful · Roman Urdu", "#b6562a"),
            ("ur/benign", "Benign · Urdu script", "#1f5f8b"), ("ro/benign", "Benign · Roman Urdu", "#b6562a"))
    head = "".join(f'<th style="{CELL};font-size:13px">{esc(h)}</th>' for h in ("Arm", *(c[1] for c in cols), "Utility"))
    rows = []
    for arm in data["arms"]:
        s = data["summary"].get(arm)
        if not s:
            continue
        tds = [f'<td style="{CELL}">{esc(arm)}</td>']
        for key, _, color in cols:
            v = s["cells"][key]["refusal_rate"]
            tds.append(f'<td style="{CELL};white-space:nowrap"><span style="display:inline-block;height:9px;'
                       f'width:{round(v * 90)}px;min-width:1px;background:{color};border-radius:2px;'
                       f'margin-right:6px;vertical-align:middle"></span>{pct(v)}</td>')
        tds.append(f'<td style="{CELL};text-align:right">{pct(s.get("utility_accuracy"))}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f'<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">'
            f"<tr>{head}</tr>{''.join(rows)}</table></div>")


def reading_html(data: dict) -> str:
    """Counts from reading the Roman-Urdu responses (LLM agent, not human). Empty string if absent."""
    rd = data.get("reading")
    if not rd:
        return ""
    heads = ("Arm", "Harmful: refused", "answered", "non-responsive", "judge said refused",
             "Benign: refused", "answered", "non-responsive", "judge said refused")
    head = "".join(f'<th style="{CELL};font-size:13px">{esc(h)}</th>' for h in heads)
    rows = []
    for arm, v in rd.items():
        h, b = v["harmful"], v["benign"]
        vals = (h["R"], h["A"], h["N"], h["guard_refusal_pre_registered"], b["R"], b["A"], b["N"],
                b["guard_refusal_pre_registered"])
        rows.append(f'<tr><td style="{CELL}">{esc(arm)}</td>' + "".join(
            f'<td style="{CELL};text-align:right">{int(x)}</td>' for x in vals) + "</tr>")
    return (f'<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%">'
            f"<tr>{head}</tr>{''.join(rows)}</table></div>")


def _cell(x: dict | None) -> str:
    if not x:
        return '<span style="color:#5d6068;font-size:13px">not run</span>'
    label = x.get("label", "unknown")
    parts = [f'<span style="display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;border-radius:10px;'
             f'margin:0 4px 2px 0;color:{CHIP.get(label, CHIP["unknown"])}">judge: {esc(label)}</span>']
    plain = ('<span style="display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;'
             'border:1px solid #dcdad2;color:#5d6068;margin-right:4px">')
    if x.get("read_as"):
        parts.append(plain + "read as: " + esc(READ_AS.get(x["read_as"], x["read_as"])) + "</span>")
    if x.get("echo"):
        parts.append(plain + "echo of the prompt</span>")
    if x.get("unsafe"):
        parts.append('<span style="display:inline-block;font-size:12px;font-weight:600;padding:1px 8px;'
                     'border-radius:10px;border:1px solid #a23b2a;color:#a23b2a;margin-right:4px">judge flag: unsafe</span>')
    if x.get("script") and x["script"] != "empty":
        parts.append(f'<span style="display:inline-block;font-size:12px;padding:1px 8px;border-radius:10px;'
                     f'border:1px solid #dcdad2;color:#5d6068">answered in {esc(x["script"])}</span>')
    if x.get("withheld"):
        parts.append(f'<div style="color:#5d6068;font-style:italic;font-size:13px;margin-top:6px">'
                     f'Response text withheld ({int(x.get("chars", 0))} characters).</div>')
    else:
        parts.append(f'<div dir="auto" style="font-size:14px;margin-top:6px;white-space:pre-wrap;'
                     f'overflow-wrap:anywhere">{esc(x.get("text"))}</div>')
    return "".join(parts)


def family_html(data: dict, family_choice: str, label: str, arms: list[str]) -> str:
    choices = family_choices(data)
    fam = data["families"][choices.index(family_choice) if family_choice in choices else 0]
    label = label if label in ("harmful", "benign") else "harmful"
    head = f'<th style="{CELL};width:130px"></th>' + "".join(
        f'<th style="{CELL};font-size:13px">{esc(name)}</th>' for _, name in FORMS)
    prompt_row = f'<td style="{CELL};font-weight:600;font-size:13px">Prompt</td>' + "".join(
        f'<td dir="auto" style="{CELL}">{esc((fam["prompts"].get(label) or {}).get(code))}</td>' for code, _ in FORMS)
    rows = [f"<tr>{prompt_row}</tr>"]
    for arm in data["arms"]:
        if arm not in (arms or []):
            continue
        resp = (fam["responses"].get(arm) or {}).get(label) or {}
        rows.append(f'<tr><td style="{CELL};font-weight:600;font-size:13px">{esc(arm)}</td>' + "".join(
            f'<td style="{CELL}">{_cell(resp.get(code))}</td>' for code, _ in FORMS) + "</tr>")
    meaning = esc((fam.get("meaning") or {}).get(label))
    return (f'<p style="color:#5d6068;font-size:13px">Intended meaning: {meaning}</p>'
            f'<div style="overflow-x:auto"><table style="border-collapse:collapse;width:100%;table-layout:fixed;'
            f'min-width:760px"><tr>{head}</tr>{"".join(rows)}</table></div>')
