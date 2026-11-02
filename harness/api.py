"""One-call API for apps: analyze a single case with any row.

    from harness.api import analyze
    result = analyze(case_dict, row="glm_harness_wiki", images=False)

Or from the shell:
    python3 -m harness.api examples/preview/cases.jsonl PREVIEW-03 --row glm_harness_wiki
"""
import argparse, json, sys
from .run import run_case
from . import config

def analyze(case, row="glm_harness_wiki", images=False):
    """Return the prediction dict for one case (format: docs/work-split.md and docs/app-guide.md)."""
    if row not in config.ROWS:
        raise ValueError(f"row must be one of {list(config.ROWS)}")
    return run_case(row, case, images)

def load(path, case_id):
    for line in open(path):
        if line.strip():
            c = json.loads(line)
            if c["case_id"] == case_id:
                return c
    raise SystemExit(f"{case_id} not found in {path}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cases"); ap.add_argument("case_id")
    ap.add_argument("--row", default="glm_harness_wiki", choices=list(config.ROWS))
    ap.add_argument("--images", action="store_true")
    a = ap.parse_args()
    print(json.dumps(analyze(load(a.cases, a.case_id), a.row, a.images), indent=1))
