"""Build web/compare.json: the three arms scored on the same invoices, from saved runs. No model calls.

    python3 web/build_compare.py

The answer key is used only to score the arms. The two claims are tested with the rules in CLAIM_RULES, whatever the runs say.
"""
import json, math, os, statistics as st
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "web", "compare.json")

ARMS = [
    {"key": "kimi_alone", "run": "kimi_alone", "name": "Kimi K3 alone", "role": "Frontier model, one call", "model": "kimi-k3"},
    {"key": "kimi_harness_wiki", "run": "kimi_harness_wiki", "name": "Kimi K3 + our harness", "role": "Same checks, frontier reader", "model": "kimi-k3"},
    {"key": "glm_harness_wiki", "run": "glm_harness_wiki_low", "name": "GLM 5.3 Flash + our harness", "role": "Same checks, low-cost reader, low reasoning", "model": "glm-5p3-flash"},
]
ALL_ARMS = ("kimi_alone", "kimi_harness_wiki", "glm_harness_wiki")
# "requires" sets the invoices: the ones every listed arm finished. Kimi K3 + harness ran on the first 300 document invoices.
SETS = [
    {"key": "test_context", "split": "test_context", "requires": ALL_ARMS, "name": "History problems", "blurb": "All four documents agree, and only the supplier's history shows something is wrong."},
    {"key": "test_300", "split": "test", "requires": ALL_ARMS, "name": "Document problems", "blurb": "The PO, shipping notice, goods receipt and invoice disagree, on messy documents. All three arms."},
    {"key": "test_1000", "split": "test", "requires": ("kimi_alone", "glm_harness_wiki"), "name": "Document problems", "blurb": "The full document test. Kimi K3 + harness has not run on all of it."},
]
# Fixed before reading the outcome of the Kimi + harness document run.
CLAIM_RULES = {
    "level": "Catch rate within 1 point of Kimi K3 alone, and false alarm rate no more than 1 point above it.",
    "beats": "Catches at least as many and raises no more false alarms than Kimi K3 alone, and is strictly better on one of the two.",
}
TYPE_NAMES = {"short_shipped": "Shipped short", "lost_in_transit": "Lost in transit", "qty_mismatch": "Quantity mismatch", "price_mismatch": "Price above PO",
              "wrong_po": "Wrong PO cited", "duplicate_invoice": "Duplicate invoice", "near_duplicate_invoice": "Near-duplicate invoice",
              "new_item_for_supplier": "New item for supplier", "price_above_history": "Price above history", "pack_size_changed": "Pack size changed",
              "remit_to_changed": "Payment address changed", "quantity_spike": "Quantity spike", "ship_from_unusual": "Unusual ship-from"}
LEAD_CASE = "TESTCTX-0149"
# Arms' fields a person needs to judge a decision. `read` is large and stays in runs/.
SHOWN = ("action", "reason_code", "next_step", "risk", "at_risk_usd", "evidence", "issues", "calls", "cost_usd", "latency_ms")

def read_jsonl(path):
    full = os.path.join(REPO, path)
    return {r["case_id"]: r for r in (json.loads(l) for l in open(full) if l.strip())} if os.path.exists(full) else {}

def is_err(p):
    return p.get("action") == "ERROR" or p.get("reason_code") == "error"

def want(label):
    if label["real_discrepancy"]:
        return "ESCALATE"
    return "WAIT" if label["stratum"] == "in_transit" else "PAY"

def group(label):
    if label["real_discrepancy"]:
        return TYPE_NAMES.get(label["reason_code"], label["reason_code"])
    return {"in_transit": "Goods in transit", "context_benign": "Benign look-alike", "clean": "Clean"}.get(label["stratum"], "Messy but correct")

def mcnemar(a_right, b_right):
    """Exact two-sided McNemar p-value on paired right and wrong answers."""
    b = sum(x and not y for x, y in zip(a_right, b_right))
    c = sum(y and not x for x, y in zip(a_right, b_right))
    n = b + c
    if n == 0:
        return {"only_a": b, "only_b": c, "p": 1.0}
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return {"only_a": b, "only_b": c, "p": min(1.0, 2 * tail)}

def score(ids, cases, preds, raw):
    real = [i for i in ids if cases[i]["label"]["real_discrepancy"]]
    transit = [i for i in ids if cases[i]["label"]["stratum"] == "in_transit"]
    fine = [i for i in ids if not cases[i]["label"]["real_discrepancy"] and cases[i]["label"]["stratum"] != "in_transit"]
    caught = [i for i in real if preds[i]["action"] == "ESCALATE"]
    lat = sorted(preds[i]["latency_ms"] / 1000 for i in ids if preds[i].get("latency_ms"))
    n = len(ids)
    return {
        "status": "run", "cases": n, "errors": sum(is_err(p) for p in raw.values()),
        "real": len(real), "caught": len(caught), "fine": len(fine), "false_alarms": sum(preds[i]["action"] == "ESCALATE" for i in fine),
        "in_transit": len(transit), "wait_ok": sum(preds[i]["action"] == "WAIT" for i in transit),
        "reason_ok": sum(preds[i]["reason_code"] == cases[i]["label"]["reason_code"] for i in caught),
        "cost_total": round(sum(preds[i]["cost_usd"] for i in ids), 4), "cost_per_100": round(100 * sum(preds[i]["cost_usd"] for i in ids) / n, 4),
        "calls_per_invoice": round(sum(preds[i]["calls"] for i in ids) / n, 3),
        "latency_p50_s": round(st.median(lat), 2) if lat else None, "latency_p95_s": round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else None,
    }

def pct(a, b):
    return 100 * a / b if b else 0

def judge(claim, arm_key, base, arm, right):
    subject = next(a["name"] for a in ARMS if a["key"] == arm_key)
    title = subject + (" performs at Kimi K3's level" if claim == "level" else " outperforms Kimi K3")
    out = {"id": claim, "arm": arm_key, "title": title, "rule": CLAIM_RULES[claim]}
    if arm["status"] != "run":
        return {**out, "status": "not_tested", "detail": "This arm has no saved run on this set yet."}
    d_catch = pct(arm["caught"], arm["real"]) - pct(base["caught"], base["real"])
    d_false = pct(arm["false_alarms"], arm["fine"]) - pct(base["false_alarms"], base["fine"])
    if claim == "level":
        holds = d_catch >= -1 and d_false <= 1
    else:
        holds = arm["caught"] >= base["caught"] and arm["false_alarms"] <= base["false_alarms"] and (arm["caught"] > base["caught"] or arm["false_alarms"] < base["false_alarms"])
    m = mcnemar(right["kimi_alone"], right[arm_key])
    detail = f"Caught {arm['caught']}/{arm['real']} vs {base['caught']}/{base['real']}. False alarms {arm['false_alarms']}/{arm['fine']} vs {base['false_alarms']}/{base['fine']}."
    return {**out, "status": "holds" if holds else "falls_short", "detail": detail, "mcnemar": m}

def build_set(spec):
    cases = read_jsonl(f"data/{spec['split']}.jsonl")
    raw = {a["key"]: read_jsonl(f"runs/{a['run']}/{spec['split']}.jsonl") for a in ARMS}
    preds = {k: {i: p for i, p in v.items() if not is_err(p)} for k, v in raw.items()}
    common = set(cases)
    for k in spec["requires"]:
        common &= set(preds[k])
    # An arm is compared only when it finished every one of these invoices, so all columns see the same invoices.
    ran = [a["key"] for a in ARMS if common and common <= set(preds[a["key"]])]
    ids = sorted(common)
    arms = {a["key"]: score(ids, cases, preds[a["key"]], raw[a["key"]]) if a["key"] in ran else {"status": "not_run", "partial": len(preds[a["key"]])} for a in ARMS}
    right = {k: [preds[k][i]["action"] == want(cases[i]["label"]) for i in ids] for k in ran}

    types = {}
    for i in ids:
        L = cases[i]["label"]
        t = types.setdefault(group(L), {"type": group(L), "real": L["real_discrepancy"], "cases": 0, "arms": {k: 0 for k in ran}})
        t["cases"] += 1
        for k in ran:
            t["arms"][k] += preds[k][i]["action"] == want(L)

    claims = [judge("level", "glm_harness_wiki", arms["kimi_alone"], arms["glm_harness_wiki"], right),
              judge("beats", "kimi_harness_wiki", arms["kimi_alone"], arms["kimi_harness_wiki"], right)]

    featured = []
    for i in ids:
        answers = [preds[k][i]["action"] for k in ran]
        if i == LEAD_CASE or len(set(answers)) > 1:
            c, L = cases[i], cases[i]["label"]
            featured.append({
                "id": i, "split": spec["split"], "set": spec["name"], "company": c["company"], "supplier": c["supplier_id"],
                "group": group(L), "want": want(L), "documents": {k: v for k, v in c["documents"].items() if v},
                "arms": {k: {f: preds[k][i].get(f) for f in SHOWN} for k in ran},
            })
    featured.sort(key=lambda f: (f["id"] != LEAD_CASE, f["id"]))
    spec = {k: v for k, v in spec.items() if k != "requires"}
    return {**spec, "cases": len(ids), "total": len(cases), "arms": arms, "types": sorted(types.values(), key=lambda t: (not t["real"], t["type"])), "claims": claims, "featured": featured}

def build():
    out = {"arms": ARMS, "rules": CLAIM_RULES, "sets": [build_set(s) for s in SETS]}
    with open(OUT, "w") as fh:
        json.dump(out, fh, ensure_ascii=False)
        fh.write("\n")
    for s in out["sets"]:
        print(f"{s['name']}: {s['cases']} of {s['total']} invoices, {len(s['featured'])} featured")
        for k, a in s["arms"].items():
            print(f"  {k}: " + (f"caught {a['caught']}/{a['real']}, false alarms {a['false_alarms']}/{a['fine']}, errors {a['errors']}, ${a['cost_per_100']}/100, p50 {a['latency_p50_s']}s" if a["status"] == "run" else "not run"))
        for c in s["claims"]:
            print(f"  [{c['status']}] {c['title']}: {c['detail']}" + (f" McNemar p={c['mcnemar']['p']:.2g}" if c.get("mcnemar") else ""))

if __name__ == "__main__":
    build()
