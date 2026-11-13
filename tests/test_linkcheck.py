"""Relative links: the checker itself, and the repository's own documents."""
import subprocess
from pathlib import Path

from scriptshield.artifacts.linkcheck import relative_links, unresolved_relative_links

ROOT = Path(__file__).resolve().parents[1]


def test_relative_links_are_found_and_external_ones_ignored():
    md = """
[a](docs/A.md) [b](https://example.org/x) [c](#section) [d](mailto:x@example.org) ![img](figures/f.png "title")
<img src="figures/g.png" width="10"> <a href="B.md">b</a> <a href="https://example.org">x</a>
[`code as link text`](scripts/run.py) [template]({{URL_X}})
"""
    assert relative_links(md) == ["docs/A.md", "figures/f.png", "figures/g.png", "B.md", "scripts/run.py"]


def test_links_inside_fenced_code_are_not_links():
    md = "text\n```bash\necho [x](not/a/link.md)\n```\n[y](real.md)\n"
    assert relative_links(md) == ["real.md"]


def test_unresolved_links_are_reported(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/A.md").write_text("[ok](B.md) [ok dir](../data/) [anchor](B.md#part) [dead](C.md) [up](../../outside.md)\n", encoding="utf-8")
    (tmp_path / "docs/B.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path.parent / "outside.md").write_text("exists, but outside the repository\n", encoding="utf-8")
    assert unresolved_relative_links(tmp_path) == [("docs/A.md", "C.md"), ("docs/A.md", "../../outside.md")]


def test_the_fault_this_check_was_written_for(tmp_path):
    """A document copied into a repository with another layout: its `../data/...` link no longer resolves."""
    (tmp_path / "quality").mkdir()
    (tmp_path / "quality/AUDIT.md").write_text("[data](../data/quality/x.json)\n", encoding="utf-8")
    (tmp_path / "quality/x.json").write_text("{}\n", encoding="utf-8")
    assert unresolved_relative_links(tmp_path) == [("quality/AUDIT.md", "../data/quality/x.json")]


def test_documents_of_this_repository_link_only_to_existing_tracked_files():
    """Every relative link in a tracked Markdown file points at a tracked file or a folder with tracked files.
    (A file that exists only on the author's disk would be a dead link for everyone else.)"""
    try:
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        tracked = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()]
    tracked = {t for t in tracked if t}
    folders = {str(Path(t).parents[i]) for t in tracked for i in range(len(Path(t).parents) - 1)}
    docs = [ROOT / t for t in sorted(tracked) if t.endswith(".md") and not t.endswith(".template.md")
            and not t.startswith(("remote/", "research_")) and (ROOT / t).exists()]
    assert len(docs) > 20
    assert unresolved_relative_links(ROOT, docs) == []
    not_tracked = []
    for f in docs:
        for target in relative_links(f.read_text(encoding="utf-8")):
            path = target.split("#", 1)[0]
            if not path:
                continue
            rel = str((f.parent / path).resolve().relative_to(ROOT))
            if rel not in tracked and rel not in folders and rel != ".":
                not_tracked.append((str(f.relative_to(ROOT)), target))
    assert not_tracked == []
