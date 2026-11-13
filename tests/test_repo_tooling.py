"""The repository's own tooling: everything the Makefile calls exists and is tracked, the secret scanner
recognises token shapes, and the response scan does not report "clean" when it had nothing to compare."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tracked():
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True)
    return set(r.stdout.splitlines()) if r.returncode == 0 and r.stdout.strip() else None


def test_every_script_named_in_the_makefile_exists_and_is_tracked():
    named = sorted(set(re.findall(r"scripts/[\w./-]+\.(?:py|sh)", (ROOT / "Makefile").read_text(encoding="utf-8"))))
    assert len(named) >= 10
    missing = [n for n in named if not (ROOT / n).is_file()]
    assert not missing, f"the Makefile calls scripts that do not exist: {missing}"
    tracked = _tracked()
    if tracked is None:
        pytest.skip("not a git checkout: existence checked, tracking not checked")
    untracked = [n for n in named if n not in tracked]
    assert not untracked, f"the Makefile calls scripts that git does not track (ignored?): {untracked}"


def test_no_python_or_shell_script_is_hidden_by_gitignore():
    tracked = _tracked()
    if tracked is None:
        pytest.skip("not a git checkout")
    on_disk = {str(p.relative_to(ROOT)) for d in ("scripts", "src", "tests", "demo", "artifacts")
               for p in (ROOT / d).rglob("*") if p.suffix in {".py", ".sh", ".js"} and "__pycache__" not in p.parts}
    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--stdin"], input="\n".join(sorted(on_disk)),
                       capture_output=True, text=True)
    ignored = [x for x in r.stdout.splitlines() if x not in tracked]
    assert not ignored, f"source files ignored by .gitignore and therefore missing from every clone: {ignored}"


@pytest.mark.parametrize("prefix,body", [("hf_", "A1b2" * 9), ("ghp_", "Z9y8" * 9), ("github_pat_", "a_B3" * 10),
                                         ("KGAT_", "0aB1" * 8)])
def test_secret_scanner_recognises_token_shapes(prefix, body):
    scan = _load("scan_secrets")
    assert scan.find_token_shapes("x = " + prefix + body), prefix
    assert not scan.find_token_shapes("the prefix " + prefix + " alone is not a token")


def test_secret_scanner_ignores_git_hashes_and_checksums_but_not_32_hex():
    scan = _load("scan_secrets")
    assert not scan.find_token_shapes("commit " + "ab12" * 10 + " sha256 " + "cd34" * 16)
    assert scan.find_token_shapes("key " + "ef56" * 8)


def test_secret_scanner_reads_a_store_and_passes_on_this_repository(tmp_path, monkeypatch):
    scan = _load("scan_secrets")
    (tmp_path / "a.token").write_text("value-" + "q" * 20 + "\n", encoding="utf-8")
    (tmp_path / "short").write_text("abc", encoding="utf-8")
    assert scan.stored_secrets(tmp_path) == ["value-" + "q" * 20]
    assert scan.stored_secrets(tmp_path / "missing") == []
    if _tracked() is None:
        pytest.skip("not a git checkout")
    monkeypatch.setattr(scan, "SECRET_DIR", tmp_path / "missing")
    assert scan.main() == 0


def test_response_scan_says_not_run_when_there_are_no_raw_responses(tmp_path):
    """In a public clone there are no raw responses; the scan must not print 'clean'."""
    for d in ("src", "scripts", "data", "configs"):
        subprocess.run(["cp", "-r", str(ROOT / d), str(tmp_path / d)], check=True)
    (tmp_path / "experiments").mkdir()
    r = subprocess.run([sys.executable, str(tmp_path / "scripts" / "scan_repo_for_responses.py"), "--dir", "configs"],
                       capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "NOT RUN" in r.stdout and "clean" not in r.stdout


CFF_1_2_KEYS = {"abstract", "authors", "cff-version", "commit", "contact", "date-released", "doi", "identifiers",
                "keywords", "license", "license-url", "message", "preferred-citation", "references", "repository",
                "repository-artifact", "repository-code", "title", "type", "url", "version"}


def test_citation_file_is_valid_cff_1_2():
    """GitHub shows "Cite this repository" only for a valid file; the schema allows no other top-level key."""
    import yaml
    c = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert c["cff-version"] == "1.2.0"
    assert {"message", "title", "authors"} <= set(c), "required keys"
    assert not set(c) - CFF_1_2_KEYS, f"keys that CFF 1.2.0 does not allow: {sorted(set(c) - CFF_1_2_KEYS)}"
    assert c["type"] in {"software", "dataset"}
    assert all({"family-names", "given-names"} <= set(a) or "name" in a for a in c["authors"])
    links = __import__("json").loads((ROOT / "configs/public_links.json").read_text(encoding="utf-8"))
    assert c["repository-code"] == links["github_repo"] == c["url"]
    assert c["repository-artifact"] == links["hf_dataset"]["url"]
