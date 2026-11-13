#!/usr/bin/env python3
"""Execute the CuratorKIT stage on the pilot corpus and verify pair integrity."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import load_corpus, load_records, validate_corpus
from scriptshield.curation.curatorkit_adapter import curate_corpus

def main() -> int:
    recs, corpus = load_corpus(ROOT)
    print(f"input records: {len(recs)}")
    out = curate_corpus(recs, ROOT / "data/generated/curated_pilot")
    print(f"CuratorKIT {out.curatorkit_version}: passed={out.n_passed} rejected={out.n_rejected} "
          f"({out.wall_clock_seconds:.2f}s)")
    print("stage counts:", json.dumps(out.stage_counts, ensure_ascii=False))
    if out.rejected:
        for r in out.rejected[:5]:
            print("  REJECTED", r["id"], r["reason"])
    rep = validate_corpus(out.passed)
    print("\npost-curation corpus check:")
    print(rep.summary())
    # Text must be unchanged: any silent normalisation of Urdu would break the contrast.
    before = {r["id"]: r["text"] for r in recs}
    changed = [r["id"] for r in out.passed if before.get(r["id"]) != r["text"]]
    print(f"\ntext changed by curation: {len(changed)}")
    if changed:
        for rid in changed[:3]:
            print("  ", rid, repr(before[rid]), "->",
                  repr(next(r["text"] for r in out.passed if r["id"] == rid)))
    dest = ROOT / "data/generated/curated_pilot/curated.jsonl"
    dest.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                            for r in sorted(out.passed, key=lambda x: x["id"])), encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")
    return 0 if rep.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
