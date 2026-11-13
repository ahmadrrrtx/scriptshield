#!/usr/bin/env bash
# Export the CURRENT tree, without history, for the public repository, together with a
# provenance list of every original commit. The full history stays in the private repository.
#
#   bash scripts/make_public_snapshot.sh [OUT_DIR]        (default: release/code_snapshot)
#
# Files marked export-ignore in .gitattributes (internal task lists and access notes) are left out.
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
OUT=${1:-$ROOT/release/code_snapshot}
if [ -n "$(git -C "$ROOT" status --porcelain)" ]; then echo "REFUSING: working tree is dirty"; exit 2; fi
rm -rf "$OUT"; mkdir -p "$OUT"
git -C "$ROOT" archive HEAD | tar -x -C "$OUT"
HEAD_SHA=$(git -C "$ROOT" rev-parse HEAD)
# first and last commit dates (the root commit is found without a pipe: `head` would break `pipefail`)
FIRST=$(git -C "$ROOT" log --max-parents=0 -1 --date=format:'%Y-%m-%d' --pretty=format:'%ad')
LAST=$(git -C "$ROOT" log -1 --date=format:'%Y-%m-%d' --pretty=format:'%ad')
{
  echo "# Provenance of this repository"
  echo
  echo "This public repository is a snapshot of a private working repository at commit \`$HEAD_SHA\`."
  echo "It was published without the earlier history for one reason. In early commits, two unit-test files"
  echo "used a real model response to a harmful prompt as a fixture. The fixture was replaced by a synthetic"
  echo "sentence before publication, but the old text would have stayed readable in the history. Publishing a"
  echo "snapshot keeps it out of the public record, in line with the rule that no such response is published"
  echo "(\`DECISIONS.md\`, D-030)."
  echo
  echo "The work was done between $FIRST and $LAST. Every original commit is listed below with its hash, time"
  echo "and subject. These are the hashes that the run reports under \`experiments/\` and the published"
  echo "artifacts refer to. The order of events is also recorded outside this repository: by the creation times"
  echo "of the Kaggle kernel versions that ran each stage (\`EXPERIMENT_LOG.md\`) and by the commit times of the"
  echo "Hugging Face repositories. The full history can be shown to the hackathon organizers on request."
  echo
  echo "Left out of the snapshot: internal task lists and access notes, a note of open questions for the"
  echo "organizers, a working note on how other public write-ups present their work, a local bootstrap script"
  echo "and an early, stale copy of the code that was once uploaded to"
  echo "Kaggle. A few documents still mention entries of those task lists by identifiers such as B-012; they"
  echo "are not needed to follow the study."
  echo
  echo "## Original commits (newest first: hash, author date, subject)"
  echo
  echo '```'
  git -C "$ROOT" log --date=iso-strict --pretty=format:'%H  %ad  %s'
  echo
  echo '```'
} > "$OUT/docs/PROVENANCE.md"
test -s "$OUT/docs/PROVENANCE.md" || { echo "FAILED: provenance file was not written"; exit 3; }
# Links between documents must still resolve once the internal files are left out.
PYTHONPATH="$ROOT/src" python3 - "$OUT" <<'PYEOF' || { echo "FAILED: dead relative links in the snapshot (listed above)"; exit 4; }
import sys
from pathlib import Path
from scriptshield.artifacts.linkcheck import unresolved_relative_links
root = Path(sys.argv[1])
dead = unresolved_relative_links(root, [f for f in sorted(root.rglob("*.md")) if not f.name.endswith(".template.md")])
for f, t in dead:
    print(f"  dead link in {f}: {t}")
sys.exit(1 if dead else 0)
PYEOF
echo "snapshot of $HEAD_SHA -> $OUT ($(find "$OUT" -type f | wc -l) files, $(git -C "$ROOT" rev-list --count HEAD) commits listed)"
