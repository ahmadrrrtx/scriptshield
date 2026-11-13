"""A kernel payload must contain every file its entry scripts read at run time.

Regression for the first test-stage launch (2026-11-12): data/utility/ was not in the
payload, so the GPU session crashed after loading the model and BEFORE generating
anything. This test unpacks the exact payload file list into an empty directory and
runs every torch-free loader there, with the repo itself out of reach.
"""
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _is_git_checkout() -> bool:
    try:
        top = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    except OSError:
        return False
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT.resolve()


# a kernel payload is defined by the git index, so these checks need a git checkout (not a zip download)
pytestmark = pytest.mark.skipif(not _is_git_checkout(), reason="needs a git checkout of the repository")

PROBE = r'''
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "src"))
from scriptshield.config import load_yaml
from scriptshield.data.schema import load_corpus
from scriptshield.evaluation.utility import load_utility
recs, corpus = load_corpus(root)
util = load_utility(root)
for name in ("steering", "models", "evaluation", "data"):
    load_yaml(root / f"configs/{name}.yaml")
import importlib.util
spec = importlib.util.spec_from_file_location("run_judge", root / "scripts/run_judge.py")
rj = importlib.util.module_from_spec(spec); spec.loader.exec_module(rj)
index, _ = rj.prompt_index(root)
for script in ("run_experiment.py", "run_judge.py", "smoke_model.py"):
    compile((root / "scripts" / script).read_text(encoding="utf-8"), script, "exec")
print(json.dumps({"records": len(recs), "utility": len(util), "prompts": len(index),
                  "frozen": (root / "configs/frozen_selection.json").exists()}))
'''


def _builder():
    spec = importlib.util.spec_from_file_location("build_kaggle_kernel", ROOT / "scripts/build_kaggle_kernel.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_payload_is_self_sufficient(tmp_path):
    files = _builder().payload_files(include_untracked=True)
    assert "data/utility/utility_v0.1.yaml" in files
    for f in files:
        dest = tmp_path / f
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / f, dest)
    probe = tmp_path / "_probe.py"
    probe.write_text(PROBE, encoding="utf-8")
    run = subprocess.run([sys.executable, str(probe), str(tmp_path)], capture_output=True, text=True,
                         cwd=str(tmp_path), env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""})
    assert run.returncode == 0, run.stderr[-2500:]
    out = __import__("json").loads(run.stdout.strip().splitlines()[-1])
    assert out["records"] == 576 and out["utility"] == 48 and out["prompts"] == 624


def test_every_data_path_named_in_src_is_in_the_payload():
    """Any 'data/...' path literal used by library code must be shipped."""
    import re
    files = set(_builder().payload_files(include_untracked=True))
    shipped_dirs = {str(Path(f).parent) for f in files}
    missing = []
    for py in (ROOT / "src").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(r'Path\("data"\)\s*/\s*"([\w.-]+)"', text):
            d = f"data/{m.group(1)}"
            if not any(s == d or s.startswith(d + "/") for s in shipped_dirs):
                missing.append((py.name, d))
    assert not missing, f"library code reads data paths that are not in the kernel payload: {missing}"
