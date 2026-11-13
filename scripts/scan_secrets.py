#!/usr/bin/env python3
"""Fail if any credential material appears in the tracked files of the repository.

Two checks, both on the files that git tracks:

1. token-shaped strings (Hugging Face, GitHub and Kaggle tokens, hard-coded keys);
2. the literal values held in a local secret store, if there is one. They are compared in memory and
   never printed.

The secret store is a folder outside the repository with one secret per file. Its default location is
``~/.cache/scriptshield-secrets``; set ``SCRIPTSHIELD_SECRET_DIR`` to use another folder. Without a store
only the first check runs. Exit code 1 on any hit.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_DIR = Path(os.environ.get("SCRIPTSHIELD_SECRET_DIR", Path.home() / ".cache" / "scriptshield-secrets"))
PATTERNS = [
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "Hugging Face token"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{30,}"), "GitHub fine-grained token"),
    (re.compile(r"KGAT_[A-Za-z0-9]{20,}"), "Kaggle token"),
    # 40-hex git hashes and 64-hex checksums are legitimate; a lone 32-hex string may be a Kaggle key
    (re.compile(r"\b[a-f0-9]{32}\b"), "32-hex string (possible Kaggle key)"),
    (re.compile(r"KAGGLE_KEY\s*=\s*['\"][^'\"]{8,}"), "hard-coded Kaggle key"),
    (re.compile(r"(?:api_key|token|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"), "hard-coded secret"),
]
SKIP_NAMES = {".gitignore"}
SKIP_SUFFIXES = {".png", ".jpg", ".npz", ".pdf"}


def find_token_shapes(text: str) -> list[tuple[str, int]]:
    """(label, offset) of every token-shaped string in ``text``."""
    return [(label, m.start()) for pat, label in PATTERNS for m in pat.finditer(text)]


def stored_secrets(folder: Path = SECRET_DIR) -> list[str]:
    if not folder.is_dir():
        return []
    values = (p.read_text(encoding="utf-8", errors="replace").strip() for p in sorted(folder.iterdir()) if p.is_file())
    return [v for v in values if len(v) >= 12]


def main() -> int:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    secrets = stored_secrets()
    hits = []
    for rel in files:
        p = ROOT / rel
        if p.name in SKIP_NAMES or p.suffix in SKIP_SUFFIXES or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(s in text for s in secrets):
            hits.append(f"{rel}: LITERAL SECRET VALUE FROM THE STORE")
        hits += [f"{rel}: {label} at offset {offset}" for label, offset in find_token_shapes(text)]
    if hits:
        print("SECRET SCAN FAILED:")
        for h in hits[:40]:
            print("  ", h)
        return 1
    store = f"{len(secrets)} stored value(s) compared" if secrets else "no local secret store, pattern checks only"
    print(f"secret scan clean: {len(files)} tracked files, 0 hits ({store})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
