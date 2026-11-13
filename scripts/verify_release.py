#!/usr/bin/env python3
"""Release verification. REMOTE GPU.

Question: does the PUBLISHED package alone (vectors + manifest + loader) reproduce the
logged outputs of the frozen test run?

The loader is executed in a subprocess whose working directory is a copy of the package
and whose PYTHONPATH is empty, so it cannot import any ScriptShield code. The criterion
is exact: sha256 of every regenerated response equals the logged one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--package", default=str(ROOT / "release/hf_model"))
    ap.add_argument("--model-dir", default=None)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    import torch

    from scriptshield.config import load_yaml
    from scriptshield.models import runtime as rt

    report: dict = {"kind": "release_verification", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "code_commit": (ROOT / "COMMIT.txt").read_text().strip() if (ROOT / "COMMIT.txt").exists() else None,
                    "hardware": ", ".join(torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())) or "cpu",
                    "torch": torch.__version__}

    def save():
        report["elapsed_seconds"] = round(time.time() - t0, 1)
        (out / "verify_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    model_dir = Path(a.model_dir) if a.model_dir else rt.find_local_model_dir()
    if model_dir is None:
        report["error"] = "no mounted model"
        save()
        return 3
    mcfg = load_yaml(ROOT / "configs/models.yaml")["primary"]
    integrity = rt.verify_files(model_dir, mcfg["lfs_sha256"])
    report["base_model"] = {"dir": str(model_dir), "weights_match_hf_lfs_sha256": integrity["all_match"]}
    if not integrity["all_match"]:
        report["error"] = "mounted weights do not match the pinned hashes"
        save()
        return 4

    pkg = Path("/tmp/scriptshield_release_pkg")
    if pkg.exists():
        shutil.rmtree(pkg)
    shutil.copytree(a.package, pkg)
    report["package_files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(pkg.iterdir()) if p.is_file()}
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update({"PYTHONPATH": "", "PYTHONUNBUFFERED": "1", "TOKENIZERS_PARALLELISM": "false", "HF_HUB_OFFLINE": "1"})
    cmd = [sys.executable, "-u", str(pkg / "apply_steering.py"), "--model-dir", str(model_dir), "--package", str(pkg),
           "--verify", str(pkg / "expected_outputs.jsonl"), "--describe-layer",
           "--report", str(out / "loader_report.json")]
    print("RUN (isolated):", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, cwd=str(pkg), env=env)
    report["loader_rc"] = p.returncode
    if (out / "loader_report.json").exists():
        lr = json.loads((out / "loader_report.json").read_text(encoding="utf-8"))
        report["verify"] = lr.get("verify")
        report["layer_modules"] = lr.get("layer_modules")
        report["loader_imported_scriptshield"] = lr.get("scriptshield_imported")
        report["layer"], report["alpha"] = lr.get("layer"), lr.get("alpha")
    diff = (report.get("verify") or {}).get("steered_differs_from_unsteered") or {}
    report["steering_visibly_applied"] = bool(diff) and all(v > 0 for v in diff.values())
    ok = bool(report.get("verify", {}) and report["verify"].get("all_identical")) and \
        report.get("loader_imported_scriptshield") is False and report["steering_visibly_applied"]
    report["passed"] = ok
    save()
    print("\nRELEASE VERIFICATION:", "PASSED" if ok else "FAILED", json.dumps(report.get("verify", {}).get("arms")))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
