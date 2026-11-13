"""The static explorer page: structure of the template, and (when a release is built and node is installed)
the page-level check that recomputes every chart value from the logs embedded in the page."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (ROOT / "demo/template.html").read_text(encoding="utf-8")
PAGE = ROOT / "release/hf_space/index.html"


def test_template_states_what_the_page_is():
    assert "Recorded experiment explorer: no model runs on this page" in TEMPLATE
    assert "Evaluating Urdu and Roman Urdu Safety Behaviour in Cohere Tiny Aya Fire" in TEMPLATE
    for section in ("Research overview", "Results", "Explore the recorded replies", "Method and artifacts", "Limitations"):
        assert section in TEMPLATE, section


def test_template_loads_nothing_from_the_network():
    assert not re.search(r"<(?:script|link|img|iframe)[^>]+(?:src|href)\s*=\s*[\"']https?://", TEMPLATE)
    assert "@import" not in TEMPLATE and "fetch(" not in TEMPLATE and "XMLHttpRequest" not in TEMPLATE


def test_template_never_claims_a_live_model_or_a_safety_gain():
    low = TEMPLATE.lower()
    for phrase in ("live demo", "try the model", "generating", "makes the model safer", "state of the art", "production-ready"):
        assert phrase not in low, phrase
    assert "Nothing on this page shows that the steered model is safer" in TEMPLATE


def test_reply_text_is_inserted_as_text_not_as_html():
    assert "innerHTML" not in TEMPLATE and "insertAdjacentHTML" not in TEMPLATE and "document.write" not in TEMPLATE


@pytest.mark.skipif(not PAGE.exists() or shutil.which("node") is None, reason="needs a built release and node")
def test_built_page_passes_the_page_level_check():
    out = subprocess.run(["node", str(ROOT / "tests/js/demo_check.js"), str(PAGE)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout[-1500:] + out.stderr[-500:]
    assert "all checks passed" in out.stdout
