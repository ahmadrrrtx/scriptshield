"""Relative links in Markdown files must point at files that exist.

A document that is correct in the code repository can have dead links once it is copied into another
repository (the dataset repository has a different folder layout). This check runs on the repository and
on every release folder before anything is uploaded. It needs no network.
"""
from __future__ import annotations

import re
from pathlib import Path

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)|<(?:img|a)\b[^>]*?\b(?:src|href)=\"([^\"]+)\"")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", re.I)


def relative_links(markdown: str) -> list[str]:
    """Targets of all relative links and images. Links inside fenced code are ignored; a link whose text is
    inline code (``[`path`](path)``) is still a link, so inline code is not stripped before matching."""
    text = _FENCE.sub("", markdown)
    out = []
    for m in _LINK.finditer(text):
        target = m.group(1) or m.group(2)
        if target and not _EXTERNAL.match(target) and "{{" not in target:
            out.append(target)
    return out


def unresolved_relative_links(root: Path, files: list[Path] | None = None) -> list[tuple[str, str]]:
    """(file, target) for every relative link under ``root`` that points outside ``root`` or at nothing."""
    root = root.resolve()
    files = sorted(root.rglob("*.md")) if files is None else files
    bad = []
    for f in files:
        f = f.resolve()
        for target in relative_links(f.read_text(encoding="utf-8")):
            path = target.split("#", 1)[0].split("?", 1)[0]
            if not path:
                continue
            dest = (root / path.lstrip("/")) if path.startswith("/") else (f.parent / path)
            dest = dest.resolve()
            if root not in (dest, *dest.parents) or not dest.exists():
                bad.append((str(f.relative_to(root)), target))
    return bad
