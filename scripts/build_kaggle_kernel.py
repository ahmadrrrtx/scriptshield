#!/usr/bin/env python3
"""Package the COMMITTED source into one self-contained Kaggle script kernel.

Why a single generated file instead of a mounted code dataset:
  * the kernel version itself contains the exact code it ran (commit + payload sha256),
  * no dataset-version race (a stale code mount silently runs old code),
  * no credentials are involved: the model is attached as a Kaggle Model source.

The build refuses a dirty working tree unless --allow-dirty (then the commit is
tagged "-dirty" so the result can never be mistaken for a clean-commit run).
Output goes to remote/_build/<name>/ (gitignored build artefact).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFETUNE_PIN = "26f59e6d1bdcacafe5f2be3b8d982fb214369659"
AUDITKIT_PIN = "71316da345784ff220d5ed59337441a59ab31526"
# Everything an entry script reads at run time must be listed here. A missing data file is
# only discovered minutes into a GPU session (it happened: data/utility, 2026-11-12), so
# tests/test_kernel_payload.py unpacks this exact file list and exercises every loader.
INCLUDE_PREFIXES = ("src/", "scripts/", "configs/", "data/schemas/", "data/utility/")
OWNER = "ahmadrrrtx"

TEMPLATE = r'''# ScriptShield - GENERATED KERNEL. Do not edit: built by scripts/build_kaggle_kernel.py
# kernel: __NAME__   code commit: __COMMIT__   payload sha256: __SHA__
# No credentials are used or needed: weights come from the attached Kaggle Model source.
import base64, hashlib, io, json, os, subprocess, sys, tarfile, time

T0 = time.time()
WORK = "/kaggle/working"
ROOT = "/tmp/scriptshield"
STATUS = {"kernel": "__NAME__", "code_commit": "__COMMIT__", "payload_sha256": "__SHA__",
          "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def sh(cmd, timeout=2400):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)[-3000:]


def save_status():
    STATUS["elapsed_seconds"] = round(time.time() - T0, 1)
    os.makedirs(WORK, exist_ok=True)
    with open(os.path.join(WORK, "kernel_status.json"), "w") as fh:
        json.dump(STATUS, fh, indent=1)


try:
    # 1. pinned toolkits (every Kaggle session is a fresh machine)
    for label, spec, extra in __PIP__:
        rc, out = sh([sys.executable, "-m", "pip", "install", "-q", *extra, spec])
        STATUS[f"pip_{label}_rc"] = rc
        print(f"pip {label}: rc={rc}", flush=True)
        if rc != 0:
            print(out, flush=True)
    # verify the IMPORT in a fresh interpreter, never pip's exit code
    rc, out = sh([sys.executable, "-c", __IMPORT_CHECK__])
    STATUS["import_rc"], STATUS["import_check"] = rc, out.strip()[-400:]
    print("import check:", rc, out.strip()[-400:], flush=True)

    # 2. unpack the embedded source and verify it
    blob = base64.b64decode(PAYLOAD)
    got = hashlib.sha256(blob).hexdigest()
    if got != "__SHA__":
        raise RuntimeError(f"payload checksum mismatch: {got}")
    os.makedirs(ROOT, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        tf.extractall(ROOT)
    with open(os.path.join(ROOT, "COMMIT.txt"), "w") as fh:
        fh.write("__COMMIT__\n")

    # 3. what did Kaggle mount?
    listing = []
    for base, dirs, files in os.walk("/kaggle/input"):
        if base.count(os.sep) > 8:
            dirs[:] = []
            continue
        for f in sorted(files)[:40]:
            p = os.path.join(base, f)
            listing.append([p, os.path.getsize(p)])
    STATUS["input_files"] = listing[:80]
    print("mounted inputs:", json.dumps(listing[:40]), flush=True)
    save_status()

    # 4. run the entry point in a fresh interpreter (isolates crashes; sees new packages)
    out_dir = os.path.join(WORK, "__NAME__")
    env = dict(os.environ, PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false",
               TRANSFORMERS_NO_ADVISORY_WARNINGS="1", HF_HOME="/tmp/hf_home", **__EXTRA_ENV__)
    cmd = [sys.executable, "-u", os.path.join(ROOT, "__ENTRY__"), "--out", out_dir] + __ARGS__
    print("RUN:", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=ROOT, env=env)
    STATUS["entry_rc"] = p.returncode
except Exception as e:
    import traceback
    STATUS["wrapper_error"] = f"{type(e).__name__}: {e}"
    traceback.print_exc()

save_status()
print("KERNEL_STATUS " + json.dumps(STATUS)[:3000], flush=True)
# Exit 0 on purpose: Kaggle discards output files of a failed version, and the
# evidence of a failure is exactly what we need to download. Pass/fail is in the report.
'''


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def payload_files(include_untracked: bool = False) -> list[str]:
    """Repo-relative files that go into a kernel: tracked files under INCLUDE_PREFIXES + the corpus."""
    import yaml
    corpus = yaml.safe_load((ROOT / "configs/data.yaml").read_text(encoding="utf-8"))["corpus"]
    files = [f for f in git("ls-files").splitlines() if f.startswith(INCLUDE_PREFIXES) or f == corpus]
    if include_untracked:   # so a dirty build is still self-consistent
        files += [f for f in git("ls-files", "--others", "--exclude-standard").splitlines()
                  if f.startswith(INCLUDE_PREFIXES) or f == corpus]
    return sorted(set(files))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attach", action="append", default=[],
                    help="extra repo-relative file or folder to embed even if git ignores it (repeatable)")
    ap.add_argument("--name", required=True, help="output folder name, e.g. smoke")
    ap.add_argument("--slug", required=True, help="kaggle kernel slug, e.g. scriptshield-fire-smoke")
    ap.add_argument("--title", required=True)
    ap.add_argument("--entry", required=True, help="repo-relative script to run")
    ap.add_argument("--args", default="", help="extra CLI args for the entry script")
    ap.add_argument("--model-source", action="append", default=[])
    ap.add_argument("--kernel-source", action="append", default=[], help="attach another kernel's output")
    ap.add_argument("--online", action="store_true", help="allow Hugging Face Hub downloads (public judge models)")
    ap.add_argument("--with-auditkit", action="store_true")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--allow-dirty", action="store_true")
    a = ap.parse_args()

    dirty = git("status", "--porcelain").strip()
    if dirty and not a.allow_dirty:
        print("REFUSING: working tree is dirty. Commit first, or pass --allow-dirty.\n" + dirty[:600])
        return 2
    commit = git("rev-parse", "HEAD").strip() + ("-dirty" if dirty else "")

    tracked = payload_files(include_untracked=bool(dirty))
    attached = {}
    for spec in a.attach:                       # files outside git (e.g. a release folder)
        src = (ROOT / spec).resolve()
        if not src.exists():
            print(f"--attach path does not exist: {spec}")
            return 2
        for fp in ([src] if src.is_file() else sorted(q for q in src.rglob("*") if q.is_file())):
            rel = str(fp.relative_to(ROOT))
            attached[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    tracked = sorted(set(tracked) | set(attached))
    if a.entry not in tracked:
        print(f"entry {a.entry} is not part of the payload")
        return 2
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tf:
        for f in sorted(tracked):
            p = ROOT / f
            if not p.is_file():
                continue
            info = tarfile.TarInfo(f)
            data = p.read_bytes()
            info.size, info.mtime, info.mode = len(data), 0, 0o644      # deterministic archive
            tf.addfile(info, io.BytesIO(data))
    blob = buf.getvalue()
    sha = hashlib.sha256(blob).hexdigest()
    b64 = base64.b64encode(blob).decode()
    payload = "PAYLOAD = '''\n" + "\n".join(b64[i:i + 120] for i in range(0, len(b64), 120)) + "\n'''\n"

    pip = [("safetune", f"git+https://github.com/Lexsi-Labs/SafeTune@{SAFETUNE_PIN}", [])]
    imports = "import safetune, torch, transformers; print('safetune', safetune.__version__, 'torch', torch.__version__, 'transformers', transformers.__version__)"
    if a.with_auditkit:
        pip.append(("auditkit", f"git+https://github.com/Lexsi-Labs/AuditKIT@{AUDITKIT_PIN}", ["--no-deps"]))
        imports = imports.replace("import safetune,", "import auditkit, safetune,")
    body = (TEMPLATE.replace("__NAME__", a.name).replace("__COMMIT__", commit).replace("__SHA__", sha)
            .replace("__ENTRY__", a.entry).replace("__ARGS__", repr(shlex.split(a.args)))
            .replace("__PIP__", repr(pip)).replace("__IMPORT_CHECK__", repr(imports))
            .replace("__EXTRA_ENV__", repr({} if a.online else {"HF_HUB_OFFLINE": "1"})))
    out = ROOT / "remote" / "_build" / a.name
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        old.unlink()
    (out / "kernel.py").write_text(payload + body, encoding="utf-8")
    meta = {"id": f"{OWNER}/{a.slug}", "title": a.title, "code_file": "kernel.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": not a.no_gpu,
            "enable_internet": True, "dataset_sources": [], "competition_sources": [],
            "kernel_sources": a.kernel_source, "model_sources": a.model_source}
    (out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out / "BUILD.json").write_text(json.dumps({
        "commit": commit, "payload_sha256": sha, "n_files": len(tracked), "payload_bytes": len(blob),
        "entry": a.entry, "args": a.args, "model_sources": a.model_source, "kernel": meta["id"],
        "attached_sha256": attached}, indent=2) + "\n")
    # A kernel must never carry a credential.
    text = (out / "kernel.py").read_text(encoding="utf-8")
    import re
    for pat in (r"hf_[A-Za-z0-9]{30,}", r"KGAT_[0-9a-f]{32}", r"ghp_[A-Za-z0-9]{30,}"):
        if re.search(pat, text) or re.search(pat, base64.b64decode(b64).decode("latin-1")):
            print("REFUSING: credential-shaped string found in kernel build")
            return 3
    print(f"built {out.relative_to(ROOT)}/kernel.py  commit={commit}  files={len(tracked)}  "
          f"payload={len(blob)/1024:.0f} KiB  sha256={sha[:16]}  kernel={meta['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
