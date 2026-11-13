"""The published steering package: manifest and vector file agree, and wrong inputs are refused.

Runs on CPU with numpy only. The tests build small fake packages and fake model folders; the real release
folder is checked too when it exists (it is not in git).
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "artifacts" / "steering_package"
RELEASE = ROOT / "release" / "hf_model"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PKG / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


loader = _load("apply_steering")
check = _load("check_base_model")


def make_package(tmp_path, dim=8, layer=3, **overrides):
    rng = np.random.default_rng(0)
    vectors = {"pooled": rng.normal(size=dim), "residualized": rng.normal(size=dim)}
    manifest = {"package_version": "test", "vector_file": "steering_vectors.npz", "orientation": "harmful_minus_benign",
                "layer": layer, "alpha": 0.1, "hidden_dim": dim,
                "arms": {k: {"sha256": loader.sha256_array(v), "norm": float(np.linalg.norm(v))} for k, v in vectors.items()},
                "base_model": {"hf_repo": "x/y", "hf_revision": "0" * 40, "weights_sha256": {}}}
    manifest.update(overrides.pop("manifest", {}))
    vectors.update(overrides.pop("vectors", {}))
    np.savez(tmp_path / "steering_vectors.npz", **vectors)
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


# ------------------------------------------------------------------ the loader (apply_steering.load_package)
def test_loader_accepts_an_intact_package(tmp_path):
    vectors, manifest = loader.load_package(make_package(tmp_path))
    assert set(vectors) == {"pooled", "residualized"} and vectors["pooled"].shape == (manifest["hidden_dim"],)


def test_loader_refuses_a_changed_vector(tmp_path):
    pkg = make_package(tmp_path)
    with np.load(pkg / "steering_vectors.npz") as z:
        v = {k: z[k].copy() for k in z.files}
    v["pooled"][0] += 1e-9
    np.savez(pkg / "steering_vectors.npz", **v)
    with pytest.raises(ValueError, match="checksum mismatch"):
        loader.load_package(pkg)


def test_loader_refuses_wrong_dimensions_missing_vectors_and_unknown_orientation(tmp_path):
    (tmp_path / "a").mkdir()
    a = make_package(tmp_path / "a", manifest={"hidden_dim": 16})
    with pytest.raises(ValueError, match="shape"):
        loader.load_package(a)
    (tmp_path / "b").mkdir()
    b = make_package(tmp_path / "b")
    m = json.loads((b / "manifest.json").read_text())
    m["arms"]["ghost"] = {"sha256": "0" * 64, "norm": 1.0}
    (b / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="missing from the file"):
        loader.load_package(b)
    (tmp_path / "c").mkdir()
    c = make_package(tmp_path / "c", manifest={"orientation": "benign_minus_harmful"})
    with pytest.raises(ValueError, match="orientation"):
        loader.load_package(c)


# ------------------------------------------------------------------ the compatibility check
def test_check_passes_on_an_intact_package_and_reports_each_kind_of_damage(tmp_path):
    (tmp_path / "ok").mkdir()
    assert check.package_problems(make_package(tmp_path / "ok")) == []
    (tmp_path / "extra").mkdir()
    extra = make_package(tmp_path / "extra", vectors={"unlisted": np.ones(8)})
    assert any("not in the manifest" in p for p in check.package_problems(extra))
    (tmp_path / "nan").mkdir()
    bad = np.ones(8)
    bad[2] = np.nan
    nan = make_package(tmp_path / "nan", vectors={"pooled": bad})
    assert any("NaN" in p for p in check.package_problems(nan))
    (tmp_path / "sums").mkdir()
    sums = make_package(tmp_path / "sums")
    (sums / "SHA256SUMS").write_text(f"{'0' * 64}  manifest.json\n")
    assert any("does not match SHA256SUMS" in p for p in check.package_problems(sums))


@pytest.mark.parametrize("config,expected", [
    ({"hidden_size": 8, "num_hidden_layers": 12}, None),
    ({"hidden_size": 16, "num_hidden_layers": 12}, "hidden size is 16"),
    ({"hidden_size": 8, "num_hidden_layers": 3}, "the model has 3 blocks"),
    ({"num_hidden_layers": 12}, "does not state the hidden size"),
    ({"hidden_size": 8}, "does not state the number of layers"),
    ({"d_model": 8, "n_layer": 4}, None),
])
def test_check_compares_the_model_shape_with_the_vectors(config, expected):
    problems = check.config_problems(config, {"hidden_dim": 8, "layer": 3})
    assert (problems == []) if expected is None else any(expected in p for p in problems), problems


def test_check_recognises_the_weights_by_checksum(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"the real weights")
    manifest = {"base_model": {"weights_sha256": {"model.safetensors": hashlib.sha256(b"the real weights").hexdigest(),
                                                  "tokenizer.json": "0" * 64}}}
    problems = check.weight_problems(tmp_path, manifest)
    assert problems == ["tokenizer.json is missing from the model folder"]
    (tmp_path / "model.safetensors").write_bytes(b"another model of the same shape")
    assert any("not the file the vectors were made from" in p for p in check.weight_problems(tmp_path, manifest))


def test_command_line_exit_codes(tmp_path, monkeypatch, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "model").mkdir()
    pkg = make_package(tmp_path / "pkg")
    (tmp_path / "model" / "config.json").write_text(json.dumps({"hidden_size": 8, "num_hidden_layers": 12}))
    monkeypatch.setattr("sys.argv", ["check", "--package", str(pkg), "--model-dir", str(tmp_path / "model"), "--quick"])
    assert check.main() == 0 and "NOT compared" in capsys.readouterr().out
    (tmp_path / "model" / "config.json").write_text(json.dumps({"hidden_size": 32, "num_hidden_layers": 12}))
    assert check.main() == 1 and "Do not steer" in capsys.readouterr().out
    monkeypatch.setattr("sys.argv", ["check", "--package", str(pkg), "--model-dir", str(tmp_path / "nowhere")])
    assert check.main() == 2


# ------------------------------------------------------------------ the real release, when it has been built
@pytest.mark.skipif(not (RELEASE / "manifest.json").exists(), reason="no local release folder")
def test_released_manifest_and_vector_file_agree():
    assert check.package_problems(RELEASE) == []
    vectors, manifest = loader.load_package(RELEASE)
    assert set(vectors) == set(manifest["arms"]) and manifest["hidden_dim"] == 2048 and manifest["layer"] == 18
    pooled = vectors["pooled"]
    for name, v in vectors.items():
        assert v.dtype == np.float64 and v.shape == (2048,)
        cos = float(v @ pooled / (np.linalg.norm(v) * np.linalg.norm(pooled)))
        assert abs(cos - manifest["arms"][name]["cos_to_pooled"]) < 1e-9, name
        assert abs(np.linalg.norm(v) - np.linalg.norm(pooled)) < 1e-6, "all arms are rescaled to the pooled norm"
    assert abs(manifest["alpha"] - manifest["rho"] * manifest["mean_activation_norm"] / manifest["norm_pooled"]) < 1e-9
    assert set(manifest["base_model"]["weights_sha256"]) == {"model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors",
                                                             "tokenizer.json"}
    assert manifest["base_model"]["included_in_package"] is False
    assert not list(RELEASE.glob("*.safetensors")), "no base weights in the package"
