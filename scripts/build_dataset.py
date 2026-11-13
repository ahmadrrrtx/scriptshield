#!/usr/bin/env python3
"""Expand a families YAML into a schema-validated JSONL corpus + manifest + pointer.

Deterministic: same YAML -> byte-identical JSONL -> same checksum.
Every record is written with validation_status="unreviewed".
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scriptshield.data.schema import validate_corpus  # noqa: E402

FORMS = ("ur", "ro", "cm", "en")


def build(src: Path, out: Path) -> dict:
    spec = yaml.safe_load(src.read_text(encoding="utf-8"))
    created = spec["created"]
    split_of = {}
    for split, fams in spec["split_assignment"].items():
        for f in fams:
            if f in split_of:
                raise ValueError(f"family {f} assigned to two splits")
            split_of[f] = split
    records = []
    for fam in spec["families"]:
        fid = fam["id"]
        if fid not in split_of:
            raise ValueError(f"family {fid} has no split assignment")
        for label in ("harmful", "benign"):
            item = fam[label]
            for form in FORMS:
                rec = {
                    "id": f"ss-{fid}-{form}-{label}",
                    "family_id": fid,
                    "pair_id": f"{fid}-{label}",
                    "form": form,
                    "safety_label": label,
                    "text": item[form].strip(),
                    "intended_meaning_en": item["meaning"],
                    "harm_category": fam["harm_category"],
                    "harm_group": fam.get("group", "unspecified"),
                    "split": split_of[fid],
                    "validation_status": "unreviewed",
                    "source": "authored",
                    "created": created,
                }
                if form == "ro":
                    rec["roman_style"] = spec["roman_style"]
                records.append(rec)
    records.sort(key=lambda r: r["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)
    out.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return {"records": records, "sha256": sha,
            "dataset_version": spec["dataset_version"], "n": len(records)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(ROOT / "data/drafts/families_v0.2.yaml"))
    ap.add_argument("--out", default=None,
                    help="default: data/corpus/scriptshield_v<dataset_version>.jsonl")
    args = ap.parse_args()
    version = yaml.safe_load(Path(args.src).read_text(encoding="utf-8"))["dataset_version"]
    if args.out is None:
        args.out = str(ROOT / "data/corpus" / f"scriptshield_v{version}.jsonl")
    info = build(Path(args.src), Path(args.out))
    rep = validate_corpus(info["records"])
    print(rep.summary())
    print(f"\nsha256: {info['sha256']}")
    manifest = {
        "dataset_version": info["dataset_version"],
        "n_records": info["n"],
        "sha256": info["sha256"],
        "path": str(Path(args.out).relative_to(ROOT)),
        "source": "authored (non-operational intent statements)",
        "human_validation": "NONE — all records unreviewed",
        "by_split": rep.by_split,
        "by_form_label": rep.by_form_label,
        "n_families": rep.n_families,
        "split_rule": yaml.safe_load(Path(args.src).read_text(encoding="utf-8")).get("split_rule"),
        "by_harm_group": {g: sum(1 for r in info["records"] if r["harm_group"] == g and r["form"] == "ur" and r["safety_label"] == "harmful")
                          for g in sorted({r["harm_group"] for r in info["records"]})},
        "purpose": ("Matched Urdu-script / Roman-Urdu / code-mixed / English intent families for "
                    "script-robustness evaluation. Small: 72 families. See the dataset card for limits."),
    }
    mpath = ROOT / "data/manifests" / f"scriptshield_{info['dataset_version']}.json"
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"manifest: {mpath.relative_to(ROOT)}")
    if rep.ok:
        # Single pointer every script reads (scriptshield.data.schema.load_corpus).
        (ROOT / "configs/data.yaml").write_text(
            "# WRITTEN BY scripts/build_dataset.py - do not edit by hand.\n"
            f"corpus: {Path(args.out).relative_to(ROOT)}\n"
            f"dataset_version: {info['dataset_version']}\n"
            f"sha256: {info['sha256']}\n"
            f"n_records: {info['n']}\n"
            f"n_families: {rep.n_families}\n"
            f"families_source: {Path(args.src).relative_to(ROOT)}\n"
            "human_validation: none   # every record is unreviewed\n", encoding="utf-8")
        print("pointer : configs/data.yaml")
    if not rep.ok:
        print("\nCORPUS INVALID — fix errors before use", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
