#!/usr/bin/env python3
"""Run the Kaggle CLI with the token injected from the out-of-repo secret store.

The token is passed to the child process through its environment only. It is never
written to the repo, never placed on a command line, and is redacted from any output
before printing. Usage:  python3 scripts/kaggle_cli.py kernels status <owner>/<slug>
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

STORE = pathlib.Path(os.environ.get("SCRIPTSHIELD_SECRETS", str(pathlib.Path.home() / ".cache/scriptshield-secrets")))
USER = os.environ.get("SCRIPTSHIELD_KAGGLE_USER", "ahmadrrrtx")


def run(args: list[str], timeout: int = 600) -> tuple[int, str]:
    token_file = STORE / "kaggle_api.token"
    if not token_file.exists():
        return 97, f"kaggle token missing from secret store ({STORE}); a sandbox reset wipes it"
    tok = token_file.read_text().strip()
    env = dict(os.environ, KAGGLE_API_TOKEN=tok, KAGGLE_USERNAME=USER, KAGGLE_KEY=tok)
    try:
        r = subprocess.run([sys.executable, "-m", "kaggle", *args], capture_output=True, text=True,
                           env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 98, "kaggle CLI timed out"
    out = ((r.stdout or "") + (r.stderr or "")).replace(tok, "<REDACTED>")
    return r.returncode, out


if __name__ == "__main__":
    rc, out = run(sys.argv[1:])
    sys.stdout.write(out)
    raise SystemExit(rc)
