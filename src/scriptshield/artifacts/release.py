"""Building blocks of the public release. Pure Python/numpy (unit-tested locally).

D-030 - WHAT IS WITHHELD. The evaluation logs contain model responses to harmful
requests. Some of those responses comply (that is the finding), so publishing the raw
text would publish harmful instructions in Urdu and Roman Urdu. In every PUBLIC
artifact a response text is therefore withheld when the prompt is harmful and the
response is not a clean refusal, or when the judge flagged the response unsafe. The
label, the judge verdict, the response length and a sha256 of the text stay, so every
reported number can still be recomputed and a holder of the private log can verify it.

D-034 - ROMAN URDU IS RELEASED ONLY AFTER READING. The judge's refusal label is wrong
about half the time for Roman-Urdu responses (protocol A19), so there it cannot decide
what is safe to publish. The text of a response to a harmful Roman-Urdu prompt is public
only if that exact text was read for that prompt and found to be an unambiguous refusal
(label R, not borderline). Everything else in that cell keeps its label and hash only.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np

WITHHELD = "[withheld]"
PUBLIC_FIELDS = ("id", "family_id", "pair_id", "form", "safety_label", "split", "harm_group", "set", "arm",
                 "layer", "rho", "alpha", "judge_label", "label_reason", "unsafe", "response_script",
                 "script_ok", "guard_refusal", "guard_safety", "guard_categories", "rubric_label", "proxy_label",
                 "is_echo", "echo_ratio", "adjudicated", "adjudicated_borderline", "read_as_clean_refusal")
# forms in which the automatic refusal label is too unreliable to release text on (protocol A19)
JUDGE_UNRELIABLE_FORMS = ("ro",)
ARM_DESCRIPTIONS = {
    "pooled": "mean of the Urdu-script and Roman-Urdu harmful-minus-benign CAA vectors (equal weight per form)",
    "residualized": "pooled vector with its component along the script direction (Urdu script vs Roman Urdu, "
                    "benign prompts) projected out, rescaled to the pooled norm",
    "random_subspace": "CONTROL: pooled vector with a random direction projected out, rescaled to the pooled norm",
    "orthogonal_null": "CONTROL: within-pair label-flip noise vector, exactly orthogonal to pooled, pooled norm",
    "ur_only": "CAA vector from Urdu-script prompts only, rescaled to the pooled norm",
    "ro_only": "CAA vector from Roman-Urdu prompts only, rescaled to the pooled norm",
}


def sha256_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_array(v: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(v, dtype=np.float64).tobytes()).hexdigest()


def clean_refusal_index(adjudication_rows: list[dict], response_rows: list[dict]) -> set[tuple[str, str]]:
    """(prompt id, exact response text) pairs that were READ and found to be an unambiguous refusal.

    ``adjudication_rows`` carry ``arm``, ``id``, ``adjudicated`` (R/A/N) and ``borderline``;
    ``response_rows`` carry ``arm``, ``id`` and ``output``. A text qualifies only if every reading of
    it for that prompt is R and not borderline.
    """
    verdict = {(r["arm"], r["id"]): (r["adjudicated"], bool(r.get("borderline"))) for r in adjudication_rows}
    seen: dict[tuple[str, str], set] = {}
    for r in response_rows:
        if r.get("set", "test") != "test":
            continue
        v = verdict.get((r.get("arm"), r.get("id")))
        if v is not None:
            seen.setdefault((r["id"], r.get("output") or ""), set()).add(v)
    return {k for k, vs in seen.items() if vs == {("R", False)}}


def attach_reading(rows: list[dict], adjudication_rows: list[dict]) -> int:
    """Adds ``adjudicated``, ``adjudicated_borderline`` and ``read_as_clean_refusal`` to labelled rows
    in place. Returns the number of rows that carry their own reading."""
    verdict = {(r["arm"], r["id"]): r for r in adjudication_rows}
    clean = clean_refusal_index(adjudication_rows, rows)
    n = 0
    for r in rows:
        hit = verdict.get((r.get("arm"), r.get("id"))) if r.get("set") == "test" else None
        r["adjudicated"] = hit["adjudicated"] if hit else None
        r["adjudicated_borderline"] = bool(hit["borderline"]) if hit else None
        n += hit is not None
        needs_reading = (r.get("set") == "test" and r.get("safety_label") == "harmful"
                         and r.get("form") in JUDGE_UNRELIABLE_FORMS)
        r["read_as_clean_refusal"] = ((r["id"], r.get("output") or "") in clean) if needs_reading else None
    return n


def withhold_reason(row: dict) -> str | None:
    """Why a response text must not appear in a public artifact, or None if it may (D-030, D-034)."""
    if row.get("unsafe") or row.get("guard_safety") == "unsafe":
        return "flagged_unsafe_by_judge"
    if row.get("safety_label") == "harmful":
        if row.get("judge_label") != "refusal":
            return "harmful_prompt_not_refused"
        # the judge's refusal label is unreliable in Roman Urdu (A19): where a response to a harmful
        # prompt was read and found not to be a refusal, the judge's "refusal" does not release it
        if row.get("adjudicated") in ("A", "N"):
            return "read_as_not_a_refusal"
        if row.get("form") in JUDGE_UNRELIABLE_FORMS and row.get("read_as_clean_refusal") is not True:
            return "roman_urdu_not_read_as_clean_refusal"
    return None


def must_withhold(row: dict) -> bool:
    """True when the response text must not appear in a public artifact."""
    return withhold_reason(row) is not None


def public_row(row: dict) -> dict:
    """A labelled row -> its public form. Never mutates the input."""
    out = {k: row[k] for k in PUBLIC_FIELDS if k in row}
    text = row.get("output") or ""
    out["output_chars"] = len(text)
    out["output_sha256"] = sha256_text(text)
    out["withheld_reason"] = withhold_reason(row)
    out["withheld"] = out["withheld_reason"] is not None
    out["output"] = WITHHELD if out["withheld"] else text
    return out


def assert_nothing_leaks(public_rows: list[dict]) -> None:
    """Fail loudly if a row that must be withheld still carries text. Recomputed from the public
    fields alone, so the rule cannot drift from what the published file lets a reader check."""
    for r in public_rows:
        if must_withhold(r) and r.get("output") != WITHHELD:
            raise AssertionError(f"row {r.get('id')} / {r.get('arm')} should be withheld ({withhold_reason(r)})")
        if "prompt" in r and r.get("safety_label") == "harmful" and r.get("set") == "utility":
            raise AssertionError("utility rows are benign by construction")


def repack_vectors(run_npz: str | Path, run_manifest: dict, layer: int, arm_names: list[str]) -> dict[str, np.ndarray]:
    """Run file (keys ``layer_{L*100+i}``) -> {arm name: vector} for one layer."""
    if run_manifest.get("key_scheme") != "layer*100 + arm_index" or list(run_manifest["arm_index"]) != list(arm_names):
        raise ValueError("unexpected key scheme in the run's vector manifest")
    out = {}
    with np.load(run_npz) as z:
        for i, name in enumerate(arm_names):
            out[name] = z[f"layer_{layer * 100 + i}"].astype(np.float64)
    return out


def save_npz_deterministic(path: str | Path, arrays: dict[str, np.ndarray]) -> None:
    """``np.savez`` stamps the current time into the zip, so two builds of identical vectors
    differ byte-for-byte. This writer fixes the timestamp: same arrays -> same file -> same sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for name in sorted(arrays):
            buf = io.BytesIO()
            np.lib.format.write_array(buf, np.ascontiguousarray(arrays[name], dtype=np.float64), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            zf.writestr(info, buf.getvalue())


def write_sums(folder: str | Path) -> dict[str, str]:
    """SHA256SUMS for every file in ``folder`` (recursive), sorted; returns the mapping."""
    folder = Path(folder)
    sums = {str(p.relative_to(folder)): sha256_file(p) for p in sorted(folder.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS"}
    (folder / "SHA256SUMS").write_text("".join(f"{h}  {n}\n" for n, h in sums.items()), encoding="utf-8")
    return sums


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
