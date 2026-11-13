#!/usr/bin/env python3
"""Publish the release folders on the Hugging Face Hub, in steps that can each be checked.

  python scripts/publish_hf.py plan      # default: verify the local folders, print what would happen
  python scripts/publish_hf.py upload    # create the repositories PRIVATE, upload, compare every remote file's sha256
  python scripts/publish_hf.py publish   # make them public and un-gated, fill the two collections, make those public
  python scripts/publish_hf.py verify    # WITHOUT a token: everything reachable, un-gated, byte-identical

Repository and collection names come from configs/public_links.json. The token is read from HF_TOKEN or
from --token-file and is never printed. What this script will not do: upload base-model weights (there are
none in release/), upload anything outside release/, or proceed if a checksum in a release folder is wrong.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = (".safetensors", ".bin", ".pt", ".pth", ".gguf", ".ckpt")
HUB_OWN_FILES = {".gitattributes"}                 # created by the Hub in every repository


def targets(links: dict) -> list[dict]:
    return [{"folder": "hf_model", "repo_type": "model", "repo_id": links["hf_model"]["repo_id"],
             "url": links["hf_model"]["url"], "collection": "hf_collection_models"},
            {"folder": "hf_dataset", "repo_type": "dataset", "repo_id": links["hf_dataset"]["repo_id"],
             "url": links["hf_dataset"]["url"], "collection": "hf_collection_data"},
            {"folder": "hf_space", "repo_type": "space", "repo_id": links["hf_space"]["repo_id"],
             "url": links["hf_space"]["url"], "collection": "hf_collection_models"}]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_folder(folder: Path) -> dict[str, str]:
    """{relative path: sha256} of the files to upload, after verifying SHA256SUMS. Raises on any mismatch."""
    sums = {}
    for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    files = sorted(str(p.relative_to(folder)) for p in folder.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    if sorted(sums) != files:
        raise SystemExit(f"{folder.name}: file list differs from SHA256SUMS; re-run scripts/package_artifacts.py")
    for name, digest in sums.items():
        if sha256(folder / name) != digest:
            raise SystemExit(f"{folder.name}/{name}: checksum mismatch; re-run scripts/package_artifacts.py")
        if name.endswith(FORBIDDEN_SUFFIXES):
            raise SystemExit(f"{folder.name}/{name}: looks like model weights; refusing")
    return {**sums, "SHA256SUMS": sha256(folder / "SHA256SUMS")}


def compare_remote(api, item: dict, local: dict[str, str], folder: Path, token) -> list[str]:
    """Downloads every remote file and compares it with the local one. Returns a list of problems."""
    from huggingface_hub import hf_hub_download
    remote = set(api.list_repo_files(item["repo_id"], repo_type=item["repo_type"], token=token)) - HUB_OWN_FILES
    problems = [f"missing on the Hub: {f}" for f in sorted(set(local) - remote)]
    problems += [f"unexpected on the Hub: {f}" for f in sorted(remote - set(local))]
    with tempfile.TemporaryDirectory() as tmp:
        for name in sorted(remote & set(local)):
            got = hf_hub_download(item["repo_id"], name, repo_type=item["repo_type"], token=token,
                                  cache_dir=tmp, force_download=True)
            if sha256(Path(got)) != local[name]:
                problems.append(f"content differs: {name}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", nargs="?", default="plan", choices=["plan", "upload", "publish", "verify"])
    ap.add_argument("--release", default="release")
    ap.add_argument("--token-file", default=None, help="file holding the write token (default: HF_TOKEN)")
    ap.add_argument("--update", action="store_true",
                    help="upload: the repositories already exist; replace their content with the release folders")
    a = ap.parse_args()
    rel = ROOT / a.release
    links = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))
    summary = json.loads((rel / "RELEASE_SUMMARY.json").read_text(encoding="utf-8"))
    if summary["leak_scan"]["leaks"] != 0 or not summary.get("verify_report_included"):
        raise SystemExit("release is not clean or not verified: " + json.dumps(summary["leak_scan"]))
    plan = targets(links)
    local = {t["folder"]: check_folder(rel / t["folder"]) for t in plan}
    for t in plan:
        t["files"] = len(local[t["folder"]])
        t["bytes"] = sum((rel / t["folder"] / f).stat().st_size for f in local[t["folder"]])
    print(json.dumps({"step": a.step, "packaged_at_commit": summary["packaged_at_commit"],
                      "collections": {k: links[k]["url"] for k in ("hf_collection_models", "hf_collection_data")},
                      "repositories": [{k: t[k] for k in ("repo_type", "repo_id", "files", "bytes", "collection")} for t in plan]},
                     indent=1))
    if a.step == "plan":
        print("\nPLAN ONLY. Nothing was uploaded.")
        return 0

    from huggingface_hub import HfApi
    if a.step == "verify":                                   # deliberately anonymous
        api, bad = HfApi(token=False), []
        for t in plan:
            info = api.repo_info(t["repo_id"], repo_type=t["repo_type"], token=False)
            state = {"private": info.private, "gated": getattr(info, "gated", False)}
            problems = compare_remote(api, t, local[t["folder"]], rel / t["folder"], False)
            if state["private"] or state["gated"]:
                problems.append(f"not open: {state}")
            print(f"{t['repo_type']:8s} {t['repo_id']}: {state}, {t['files']} files "
                  + ("identical to the release folder" if not problems else f"PROBLEMS {problems[:5]}"))
            bad += problems
        for key in ("hf_collection_models", "hf_collection_data"):
            col = api.get_collection(links[key]["slug"], token=False)
            have = sorted((i.item_type, i.item_id) for i in col.items)
            want = sorted((t["repo_type"], t["repo_id"]) for t in plan if t["collection"] == key)
            ok = have == want and not col.private
            print(f"collection {col.title!r}: private={col.private}, items={have}" + ("" if ok else f"  EXPECTED {want}"))
            bad += [] if ok else [key]
        print("\nVERIFIED without a token: every repository and both collections are public, un-gated and identical "
              "to the release folders." if not bad else f"\nNOT VERIFIED: {len(bad)} problem(s).")
        return 0 if not bad else 1

    token = os.environ.get("HF_TOKEN") or (Path(a.token_file).expanduser().read_text().strip() if a.token_file else None)
    if not token:
        raise SystemExit("no token: set HF_TOKEN or pass --token-file")
    api = HfApi(token=token)
    me = api.whoami()["name"]
    owners = {t["repo_id"].split("/")[0] for t in plan}
    if owners != {me}:
        raise SystemExit(f"the token belongs to {me!r} but the plan publishes under {sorted(owners)}")

    if a.step == "upload":
        for t in plan:
            kw = {"repo_id": t["repo_id"], "repo_type": t["repo_type"]}
            exists = api.repo_exists(**kw)
            if exists and not a.update:
                raise SystemExit(f"{t['repo_id']} already exists; inspect it, then re-run with --update")
            if not exists:
                api.create_repo(private=True, exist_ok=False, **({**kw, "space_sdk": "static"} if t["repo_type"] == "space" else kw))
            # a new static Space starts with template files of the Hub (e.g. style.css): remove what is not ours
            api.upload_folder(folder_path=str(rel / t["folder"]),
                              delete_patterns=["*"] if (exists or t["repo_type"] == "space") else None,
                              commit_message=f"ScriptShield release (code commit {summary['packaged_at_commit'][:8]})", **kw)
            problems = compare_remote(api, t, local[t["folder"]], rel / t["folder"], token)
            info = api.repo_info(**kw)
            print(f"{t['repo_type']:8s} {t['repo_id']}: private={info.private}, {t['files']} files uploaded, "
                  + ("every remote file identical to the local one" if not problems else f"PROBLEMS: {problems[:5]}"))
            if problems:
                return 1
        print("\nUploaded PRIVATE and verified. Review, then run the `publish` step.")
        return 0

    # ---- publish: public, un-gated, collections filled and public
    for t in plan:
        kw = {"repo_id": t["repo_id"], "repo_type": t["repo_type"]}
        problems = compare_remote(api, t, local[t["folder"]], rel / t["folder"], token)
        if problems:
            raise SystemExit(f"{t['repo_id']} differs from the release folder, not publishing: {problems[:5]}")
        # a Space cannot be gated; for models and datasets gating is switched off explicitly
        api.update_repo_settings(private=False, **({} if t["repo_type"] == "space" else {"gated": False}), **kw)
        api.add_collection_item(links[t["collection"]]["slug"], item_id=t["repo_id"], item_type=t["repo_type"], exists_ok=True)
        print(f"public: {t['url']}")
    for key in ("hf_collection_models", "hf_collection_data"):
        api.update_collection_metadata(links[key]["slug"], private=False)
        print(f"public: {links[key]['url']}")
    print("\nPublished. Run the `verify` step (it uses no token).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
