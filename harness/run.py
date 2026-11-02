"""Run one row over a split and write runs/<row>/<split>[_images].jsonl.

python3 -m harness.run --row glm_harness_wiki --split dev --limit 50 [--images] [--workers 32]
"""
import argparse, concurrent.futures as cf, json, os, sys, time
from . import config, rows

def run_case(row, case, use_images):
    spec = config.ROWS[row]
    try:
        if spec["kind"] == "alone":
            out = rows.alone(case, spec["model"], use_images, frontier=(row == "kimi_alone"))
        else:
            out = rows.harness(case, spec["model"], use_images, spec["wiki"])
    except Exception as e:
        out = dict(model=spec["model"], action="ERROR", model_action=None, risk=None, at_risk_usd=None,
                   reason_code="error", next_step="investigate", evidence=str(e)[:300], features=None, read=None, issues=None, dial=None,
                   calls=0, tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)
    return {"case_id": case["case_id"], "row": row, **out}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--row", required=True, choices=list(config.ROWS))
    ap.add_argument("--split", required=True)
    ap.add_argument("--data", default=None, help="path to a cases .jsonl (default data/<split>.jsonl)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--images", action="store_true", help="only cases with images, read from the images")
    ap.add_argument("--workers", type=int, default=32)
    a = ap.parse_args()
    path = a.data or os.path.join(config.DATA_DIR, f"{a.split}.jsonl")
    cases = [json.loads(l) for l in open(path) if l.strip()]
    if a.images:
        cases = [c for c in cases if c.get("images")]
    if a.limit:
        cases = cases[: a.limit]
    os.makedirs(os.path.join(config.RUNS_DIR, a.row), exist_ok=True)
    out_path = os.path.join(config.RUNS_DIR, a.row, f"{a.split}{'_images' if a.images else ''}.jsonl")
    t0 = time.time(); results = []
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(run_case, a.row, c, a.images): c for c in cases}
        for i, f in enumerate(cf.as_completed(futs), 1):
            results.append(f.result())
            if i % 25 == 0 or i == len(cases):
                print(f"{a.row} {i}/{len(cases)} ${sum(r['cost_usd'] for r in results):.3f} {time.time()-t0:.0f}s", flush=True)
    order = {c["case_id"]: i for i, c in enumerate(cases)}
    results.sort(key=lambda r: order[r["case_id"]])
    with open(out_path, "w") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    lab = {c["case_id"]: c.get("label", {}) for c in cases}
    n = len(results); err = sum(r["reason_code"] == "error" for r in results)
    real = [r for r in results if lab[r["case_id"]].get("real_discrepancy")]
    agree = [r for r in results if lab[r["case_id"]].get("stratum") in ("clean", "messy")]
    print(json.dumps({"row": a.row, "split": a.split, "images": a.images, "n": n, "errors": err,
        "real_escalated": f"{sum(r['action']=='ESCALATE' for r in real)}/{len(real)}",
        "agreeing_escalated": f"{sum(r['action']=='ESCALATE' for r in agree)}/{len(agree)}",
        "calls": sum(r["calls"] for r in results), "cost_usd": round(sum(r["cost_usd"] for r in results), 4),
        "wall_s": round(time.time() - t0, 1), "out": os.path.relpath(out_path, config.REPO)}))

if __name__ == "__main__":
    main()
