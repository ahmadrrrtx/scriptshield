#!/usr/bin/env python3
"""Before the repository is published: no TRACKED file may contain text that exists only in
model responses that must be withheld (D-030).

Withheld here = any response to a harmful prompt that is not a judged, clean refusal, plus anything a
judge flagged unsafe. Responses that were never judged (smoke test, bake-off) count as withheld when the
prompt is harmful. For Roman-Urdu prompts the judge's refusal label does not release a text (D-034): only
texts that were read and found to be unambiguous refusals do.
Sources: every generations/judged file on disk under experiments/results (git-ignored).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scriptshield.artifacts.release import JUDGE_UNRELIABLE_FORMS, clean_refusal_index  # noqa: E402
from scriptshield.data.schema import load_corpus  # noqa: E402
from scriptshield.evaluation.utility import load_utility  # noqa: E402

WIDTH, STEP = 40, 20


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="scan every file under this folder (e.g. release) instead of the git-tracked files")
    ap.add_argument("--show", action="store_true", help="print the matching windows (for review; may print response text)")
    a = ap.parse_args()
    recs, _ = load_corpus(ROOT)
    label_of = {r["id"]: r["safety_label"] for r in recs}
    form_of = {r["id"]: r["form"] for r in recs}
    adj_path = ROOT / "experiments/adjudication/test_ro_rows.jsonl"
    test_path = ROOT / "experiments/results/judge_test_merged/judged.jsonl"
    read_clean = set()
    if adj_path.exists() and test_path.exists():
        load = lambda q: [json.loads(x) for x in q.read_text(encoding="utf-8").splitlines() if x.strip()]  # noqa: E731
        read_clean = clean_refusal_index(load(adj_path), load(test_path))
    prompts = [r["text"] for r in recs] + [u["text"] for u in load_utility(ROOT)]
    for extra in sorted((ROOT / "data").rglob("*.jsonl")) + sorted((ROOT / "data").rglob("*.yaml")):
        prompts.append(extra.read_text(encoding="utf-8", errors="replace"))      # every authored prompt variant
    withheld, released, n_rows = set(), set(), 0
    for f in sorted((ROOT / "experiments").rglob("*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in ("output", "steered_output", "unsteered_output", "response"):
                out = r.get(key)
                if not isinstance(out, str) or not out.strip():
                    continue
                n_rows += 1
                harmful = (r.get("safety_label") or label_of.get(r.get("id"))) != "benign"      # unknown -> treat as harmful
                clean_refusal = r.get("guard_refusal") == "refusal" and r.get("guard_safety") != "unsafe"
                form = r.get("form") or form_of.get(r.get("id"))            # unknown form -> treated as Roman Urdu
                if harmful and (form is None or form in JUDGE_UNRELIABLE_FORMS):
                    clean_refusal = clean_refusal and (r.get("id"), out) in read_clean
                unsafe = r.get("guard_safety") == "unsafe"
                (withheld if (unsafe or (harmful and not clean_refusal)) else released).add(out)
    withheld -= released
    allow = json.loads((ROOT / "configs/response_scan_allowlist.json").read_text(encoding="utf-8"))["entries"]
    allowed = {t for t in withheld if any(e["text_contains"] in t for e in allow)}
    withheld -= allowed
    released |= allowed
    released_blob = "\n".join(prompts) + "\n" + "\n".join(released)
    windows = {}
    for text in withheld:
        for i in range(0, max(1, len(text) - WIDTH + 1), STEP):
            w = text[i:i + WIDTH]
            if len(w.strip()) >= 30 and w not in released_blob:
                windows.setdefault(w, None)
    if a.dir:
        tracked = sorted(str(q.relative_to(ROOT)) for q in (ROOT / a.dir).rglob("*") if q.is_file())
    else:
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
    hits = {}
    for name in tracked:
        p = ROOT / name
        if not p.is_file() or p.stat().st_size > 8_000_000:
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        blob = raw + "\n" + raw.replace("\\n", "\n").replace('\\"', '"')
        if "\\u" in raw:                                    # JSON written with ensure_ascii=True
            try:
                blob += "\n" + raw.encode("utf-8").decode("unicode_escape", errors="ignore")
            except Exception:
                pass
        found = [w for w in windows if w in blob]
        if found:
            hits[name] = len(found)
            if a.show:
                for w in found:
                    print(f"  [{name}] {w!r}")
    print(f"response texts seen: {n_rows} rows | withheld-only texts: {len(withheld)} | unique windows: {len(windows)} "
          f"| files scanned: {len(tracked)} ({a.dir or 'git-tracked'}) | allowlisted after review: {len(allowed)} texts ({len(allow)} rules)")
    if hits:
        print("FILES CONTAINING WITHHELD-ONLY RESPONSE TEXT:")
        for k, v in sorted(hits.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>5} windows  {k}")
        return 1
    print("clean: no scanned file contains withheld-only response text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
