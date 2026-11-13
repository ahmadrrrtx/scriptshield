#!/usr/bin/env python3
"""Record a dated baseline of everything that is public: one JSON file and one readable page.

For every Hugging Face repository the files are downloaded WITHOUT credentials at the given tag and hashed
locally, so the record does not depend on what the Hub reports. For the code repository the commit and
tree of the given git tag are recorded.

    python3 scripts/release_baseline.py --date 2026-11-13 --git-tag v0.1.0 \
        --model-tag v0.2.0 --dataset-tag v0.2.0 --space-tag v0.1.0

Needs `huggingface_hub` and network access. Writes docs/baselines/BASELINE_<date>.json and .md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKS = json.loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def hub_repo(kind: str, repo_id: str, tag: str) -> dict:
    from huggingface_hub import HfApi, snapshot_download
    api = HfApi(token=False)
    info = api.repo_info(repo_id, repo_type=kind, revision=tag)
    with tempfile.TemporaryDirectory(dir=Path.home() / ".cache") as tmp:
        d = Path(snapshot_download(repo_id, repo_type=kind, revision=tag, local_dir=tmp, token=False))
        files = {str(p.relative_to(d)): {"sha256": sha256(p), "bytes": p.stat().st_size}
                 for p in sorted(d.rglob("*")) if p.is_file() and ".cache" not in p.relative_to(d).parts}
    return {"repo_id": repo_id, "type": kind, "tag": tag, "commit": info.sha, "private": info.private,
            "gated": getattr(info, "gated", None), "url": f"https://huggingface.co/{'' if kind == 'model' else kind + 's/'}{repo_id}/tree/{tag}",
            "n_files": len(files), "files": files}


def git_repo(url: str, tag: str) -> dict:
    out = subprocess.run(["git", "ls-remote", "--tags", url, tag, tag + "^{}"], capture_output=True, text=True, check=True).stdout.split()
    refs = dict(zip(out[1::2], out[0::2]))
    commit = refs.get(f"refs/tags/{tag}^{{}}") or refs[f"refs/tags/{tag}"]
    with tempfile.TemporaryDirectory(dir=Path.home() / ".cache") as tmp:
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", tag, url, tmp], check=True,
                       env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin", "HOME": tmp})
        tree = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD^{tree}"], capture_output=True, text=True, check=True).stdout.strip()
        n = len(subprocess.run(["git", "-C", tmp, "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines())
    return {"url": url, "tag": tag, "commit": commit, "tree": tree, "n_files": n, "browse": f"{url}/tree/{tag}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--git-tag", required=True)
    ap.add_argument("--model-tag", required=True)
    ap.add_argument("--dataset-tag", required=True)
    ap.add_argument("--space-tag", required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    from huggingface_hub import HfApi
    base = {"date": a.date, "note": a.note, "code": git_repo(LINKS["github_repo"], a.git_tag),
            "model": hub_repo("model", LINKS["hf_model"]["repo_id"], a.model_tag),
            "dataset": hub_repo("dataset", LINKS["hf_dataset"]["repo_id"], a.dataset_tag),
            "space": hub_repo("space", LINKS["hf_space"]["repo_id"], a.space_tag), "collections": []}
    for key in ("hf_collection_models", "hf_collection_data"):
        c = HfApi(token=False).get_collection(LINKS[key]["url"].split("/collections/")[1])
        base["collections"].append({"title": c.title, "url": LINKS[key]["url"], "private": c.private,
                                    "items": [f"{i.item_type}:{i.item_id}" for i in c.items]})
    out = ROOT / "docs" / "baselines"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"BASELINE_{a.date}.json").write_text(json.dumps(base, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    md = [f"# Release baseline of {a.date}", "",
          "What was public on this date, recorded so that later changes can be compared with it. Every file of the",
          "Hugging Face repositories was downloaded without credentials at the tag shown and hashed locally; the full",
          f"list with SHA-256 checksums is in [`BASELINE_{a.date}.json`](BASELINE_{a.date}.json).", ""]
    if a.note:
        md += [a.note, ""]
    md += ["| Artifact | Tag | Commit | Files | Browse this exact version |", "|---|---|---|---|---|",
           f"| Code (GitHub) | `{base['code']['tag']}` | `{base['code']['commit'][:12]}` | {base['code']['n_files']} | <{base['code']['browse']}> |"]
    for k, label in (("dataset", "Dataset and evaluation logs"), ("model", "Steering-vector package"), ("space", "Replay demo (Space)")):
        r = base[k]
        md.append(f"| {label} | `{r['tag']}` | `{r['commit'][:12]}` | {r['n_files']} | <{r['url']}> |")
    md += ["", "Collections on that date:", ""]
    md += [f"- [{c['title']}]({c['url']}): {', '.join('`' + i + '`' for i in c['items'])}" for c in base["collections"]]
    md += ["", "## How to get exactly these versions", "", "```bash",
           f"git clone --branch {a.git_tag} {LINKS['github_repo']}",
           f"hf download {base['model']['repo_id']} --revision {a.model_tag} --local-dir vectors",
           f"hf download {base['dataset']['repo_id']} --repo-type dataset --revision {a.dataset_tag} --local-dir data_release",
           "```", "", "```python", "from datasets import load_dataset",
           f"ds = load_dataset(\"{base['dataset']['repo_id']}\", revision=\"{a.dataset_tag}\")", "```", "",
           "## Key checksums (SHA-256)", "", "| File | SHA-256 |", "|---|---|"]
    for k, names in (("model", ["steering_vectors.npz", "apply_steering.py", "manifest.json", "expected_outputs.jsonl", "frozen_selection.json"]),
                     ("dataset", ["data/scriptshield_v0.2.0.jsonl", "data/test.jsonl", "eval_logs/test_judged_public.jsonl", "eval_logs/test_analysis_guard.json"]),
                     ("space", ["index.html"])):
        for n in names:
            if n in base[k]["files"]:
                md.append(f"| `{base[k]['repo_id'].split('/')[1]}/{n}` | `{base[k]['files'][n]['sha256']}` |")
    (out / f"BASELINE_{a.date}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {out}/BASELINE_{a.date}.json and .md: code {base['code']['commit'][:10]}, "
          f"model {base['model']['commit'][:10]} ({base['model']['n_files']} files), dataset {base['dataset']['commit'][:10]} "
          f"({base['dataset']['n_files']} files), space {base['space']['commit'][:10]} ({base['space']['n_files']} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
