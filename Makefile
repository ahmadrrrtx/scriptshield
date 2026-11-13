# ScriptShield: common tasks.
#
#   In a fresh clone (CPU only, no model):
#     make test        unit tests
#     make validate    dataset validator, config validator, secret scan
#     make recompute   recompute the pre-registered analysis from the public logs (downloads them if needed)
#     make audit       rewrite the dataset quality audit from the corpus
#     make robustness  the script gap on subsets of the test set, from the public logs
#     make review      import the reviewer's answers, then refresh the audit and the robustness checks
#     make figures     redraw the figures (needs matplotlib: pip install -e ".[figures]")
#
#   With the raw outputs of a GPU run under experiments/results/ (they are not published, see README):
#     make analysis report article package scan
.PHONY: test validate analysis report article package scan recompute snapshot all audit robustness review figures demo-check
J ?= experiments/results/judge_test_merged/judged.jsonl
M ?= experiments/results/fire_test_v2/fire_test/margins.jsonl
V ?= experiments/results/verify_release_v1/verify_release/verify_report.json

test:
	python3 -m pytest -q
validate:
	python3 scripts/validate_dataset.py && python3 scripts/validate_config.py && python3 scripts/scan_secrets.py
analysis:
	for j in guard rubric; do python3 scripts/analyze.py test --judged $(J) --margins $(M) --out experiments/results/test_analysis --judge $$j; \
	  python3 scripts/analyze.py test --judged $(J) --margins $(M) --out experiments/results/test_analysis --judge $$j --echo-corrected; done
	python3 scripts/adjudication.py report --judged $(J)
	python3 scripts/utility_reading.py --judged $(J)
	python3 scripts/analyze_devx.py
report:
	python3 scripts/make_report.py
article: report
	python3 scripts/make_article.py
package: report
	python3 scripts/package_artifacts.py --test-run experiments/results/fire_test_v2/fire_test --judged $(J) --verify-report $(V)
scan:
	python3 scripts/scan_secrets.py && python3 scripts/scan_repo_for_responses.py && python3 scripts/scan_repo_for_responses.py --dir release
recompute:
	@if [ -d release/hf_dataset/eval_logs ]; then python3 scripts/recompute_from_public.py --logs release/hf_dataset/eval_logs; \
	  else python3 scripts/recompute_from_public.py --download; fi
audit:
	python3 scripts/audit_dataset.py
robustness:
	@if [ -d release/hf_dataset/eval_logs ]; then python3 scripts/robustness_checks.py; \
	  else python3 scripts/robustness_checks.py --download; fi
review:
	python3 scripts/import_review.py && python3 scripts/import_response_labels.py && python3 scripts/audit_dataset.py
	$(MAKE) robustness
figures:
	python3 scripts/make_figures.py
demo-check:
	node tests/js/demo_check.js release/hf_space/index.html
snapshot:
	bash scripts/make_public_snapshot.sh
all: test validate report article package demo-check scan recompute
