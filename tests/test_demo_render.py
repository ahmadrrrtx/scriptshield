"""Demo rendering: escapes everything, never shows withheld text, tolerates missing cells."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render", ROOT / "demo/render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

DATA = {
    "arms": ["unsteered", "pooled"], "layer": 18, "rho": 0.1, "note": "n", "arm_descriptions": {"pooled": "p"},
    "summary": {a: {"cells": {k: {"refusal_rate": 0.5} for k in ("ur/harmful", "ro/harmful", "ur/benign", "ro/benign")},
                    "utility_accuracy": None if a == "pooled" else 0.75} for a in ("unsteered", "pooled")},
    "families": [{
        "family_id": "fam<script>", "harm_group": "cyber", "meaning": {"harmful": "m & m"},
        "prompts": {"harmful": {"ur": "سوال", "ro": "<img src=x onerror=alert(1)>"}},
        "responses": {"unsteered": {"harmful": {
            "ur": {"label": "refusal", "unsafe": False, "script": "arabic", "text": "معذرت <b>", "chars": 9, "withheld": False,
                   "read_as": "R", "echo": False},
            "ro": {"label": "compliance", "unsafe": True, "script": "latin", "text": "[withheld]", "chars": 321, "withheld": True}}}},
    }],
}


def test_everything_is_escaped_and_withheld_text_is_not_rendered():
    choice = render.family_choices(DATA)[0]
    h = render.family_html(DATA, choice, "harmful", ["unsteered", "pooled"])
    assert "<img" not in h and "&lt;img src=x" in h          # prompt escaped
    assert "معذرت &lt;b&gt;" in h                             # response escaped
    assert "Response text withheld (321 characters)" in h and "[withheld]" not in h
    assert "judge flag: unsafe" in h and "not run" in h       # pooled has no rows; cm/en missing
    assert "read as: refusal" in h and "judge: compliance" in h
    assert "m &amp; m" in h


def test_summary_and_bad_inputs():
    s = render.summary_html(DATA)
    assert "50.0 %" in s and "n/a" in s and "75.0 %" in s
    h = render.family_html(DATA, "no such family", "weird", None)   # falls back, does not raise
    assert "Prompt" in h


def test_reading_table_is_optional():
    assert render.reading_html(DATA) == ""
    cell = {"R": 13, "A": 6, "N": 17, "guard_refusal_pre_registered": 17}
    h = render.reading_html({**DATA, "reading": {"unsteered": {"harmful": cell, "benign": cell}}})
    assert "<td" in h and ">13<" in h and ">17<" in h
