"""A second Roman-Urdu spelling convention ("style B") for spelling-robustness checks.

The corpus is written in one convention ("style A"): *kaise, nahi, hoon*, long vowels doubled, final *-ay*.
People also write the same words as *kese, nahin, hun* with a final *-e*. ``to_style_b`` rewrites a style-A
sentence in that second convention, word by word:

* only the spelling of a word changes, never the word itself or the word order;
* only common function words and two regular endings are touched; content words keep their spelling;
* every changed word is returned, so that a reviewer can see exactly what was done.

The output is a CANDIDATE. It is drafted by rule, not by a speaker, and must be confirmed by a human
reviewer before it is used in any experiment or published as data.
"""
from __future__ import annotations

import re

# whole-word respellings (style A -> style B)
WORD_MAP = {
    "kaise": "kese", "aisa": "esa", "aisi": "esi", "aisay": "ese", "nahi": "nahin", "aik": "ek", "woh": "wo",
    "kya": "kia", "bohat": "bohot", "zyada": "ziada", "takay": "taake", "lay": "le", "day": "de",
    # style A writes "main" for I and "mein" for in; the other widespread habit is the reverse
    "main": "mein", "mein": "main",
}
# words that end in -ay / -oon but are left alone: the respelling would look like another word, or the
# word is English, or it is a noun and the -oon rule is meant for verb endings
KEEP = {"usay", "isay", "cameray", "namay", "motorway", "beroon", "bairoon", "pursukoon"}


def respell_word(word: str) -> str:
    low = word.lower()
    if low in KEEP:
        return word
    if low in WORD_MAP:
        new = WORD_MAP[low]
    elif len(low) >= 4 and low.endswith("oon"):
        new = low[:-3] + "un"
    elif len(low) >= 4 and low.endswith("ay"):
        new = low[:-2] + "e"
    else:
        return word
    return new.capitalize() if word[0].isupper() else new


def to_style_b(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(respelled sentence, [(old word, new word), ...]) for a style-A Roman-Urdu sentence."""
    changes: list[tuple[str, str]] = []

    def sub(m: re.Match) -> str:
        old = m.group(0)
        new = respell_word(old)
        if new != old:
            changes.append((old, new))
        return new

    return re.sub(r"[A-Za-z]+", sub, text), changes
