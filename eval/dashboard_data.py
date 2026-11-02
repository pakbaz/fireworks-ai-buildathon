"""Build the comparison dashboard's data files from saved predictions (docs/results/dashboard/*.json).

Each test set is compared on the cases that every included system has finished, so every row sees the same invoices.
    python3 eval/dashboard_data.py
"""
import json, os, statistics as st
SETS = [("test", "Document problems"), ("test_context", "History problems")]
SYSTEMS = [("kimi_alone", "Kimi K3 alone"), ("kimi_harness_wiki", "Kimi K3 + our checks"), ("glm_harness_wiki", "Our harness (GLM + wiki)"),
           ("kimi_alone_v1_no_history_instruction", "Kimi K3 alone, not told to check history (original run)"),
           ("glm_alone", "GLM 5.3 Flash alone"), ("glm_harness", "GLM + harness, no wiki")]
REVIEW = 10.0
TYPE_NAMES = {"short_shipped": "Shipped short", "lost_in_transit": "Lost in transit", "qty_mismatch": "Quantity mismatch",
              "price_mismatch": "Price above PO", "wrong_po": "Wrong PO cited", "duplicate_invoice": "Duplicate invoice",
              "near_duplicate_invoice": "Near-duplicate invoice", "new_item_for_supplier": "New item for supplier",
              "price_above_history": "Price above history", "pack_size_changed": "Pack size changed",
              "remit_to_changed": "Payment address changed", "quantity_spike": "Quantity spike", "ship_from_unusual": "Unusual ship-from"}
def load(p):
    return {json.loads(l)["case_id"]: json.loads(l) for l in open(p)} if os.path.exists(p) else {}
summary, by_type, per_case = [], [], []
for split, set_name in SETS:
    cases = {json.loads(l)["case_id"]: json.loads(l) for l in open(f"data/{split}.jsonl")}
    raw = {k: load(f"runs/{k}/{split}.jsonl") for k, _ in SYSTEMS}
    is_err = lambda p: p.get("reason_code") == "error" or p.get("action") == "ERROR"
    preds = {k: {i: p for i, p in v.items() if not is_err(p)} for k, v in raw.items()}
    core = [k for k in ("kimi_alone", "glm_harness_wiki") if preds[k]]
    if len(core) < 2: continue
    common = set(cases)
    for k in core: common &= set(preds[k])
    for k, name in SYSTEMS:
        P = preds[k]
        if not P or not common <= set(P): continue
        ids = sorted(common)
        real = [i for i in ids if cases[i]["label"]["real_discrepancy"]]
        transit = [i for i in ids if cases[i]["label"]["stratum"] == "in_transit"]
        fine = [i for i in ids if not cases[i]["label"]["real_discrepancy"] and cases[i]["label"]["stratum"] != "in_transit"]
        caught = [i for i in real if P[i]["action"] == "ESCALATE"]; missed = [i for i in real if P[i]["action"] != "ESCALATE"]
        fp = [i for i in fine if P[i]["action"] == "ESCALATE"]
        wait_ok = sum(P[i]["action"] == "WAIT" for i in transit)
        reason_ok = sum(P[i]["reason_code"] == cases[i]["label"]["reason_code"] for i in caught)
        lat = sorted(P[i]["latency_ms"] / 1000 for i in ids if P[i].get("latency_ms"))
        cost = sum(P[i]["cost_usd"] for i in ids); calls = sum(P[i]["calls"] for i in ids)
        escal = sum(P[i]["action"] == "ESCALATE" for i in ids)
        missed_usd = sum(cases[i]["label"]["at_risk_usd"] or 0 for i in missed)
        n = len(ids)
        summary.append({"set": set_name, "system": name, "key": k, "attempted": len(raw[k]), "completed": len(P), "errors": len(raw[k]) - len(P), "cases": n, "real": len(real), "caught": len(caught), "missed": len(missed),
                        "fine": len(fine), "false_escalations": len(fp), "true_pays": len(fine) - len(fp), "in_transit": len(transit), "wait_correct": wait_ok,
                        "catch_rate": round(len(caught) / len(real), 4) if real else None,
                        "false_escalation_rate": round(len(fp) / len(fine), 4) if fine else None,
                        "reason_correct_rate": round(reason_ok / len(caught), 4) if caught else None,
                        "model_cost_per_100": round(100 * cost / n, 4), "calls_per_invoice": round(calls / n, 3),
                        "latency_p50_s": round(st.median(lat), 2) if lat else None, "latency_p95_s": round(lat[int(0.95 * (len(lat) - 1))], 2) if lat else None,
                        "reviews_per_100": round(100 * escal / n, 2), "missed_dollars": round(missed_usd, 2),
                        "review_cost_per_100": round(100 * escal * REVIEW / n, 2), "missed_dollars_per_100": round(100 * missed_usd / n, 2)})
        groups = {}
        for i in ids:
            L = cases[i]["label"]
            t = TYPE_NAMES.get(L["reason_code"], L["reason_code"]) if L["real_discrepancy"] else ("Goods in transit" if L["stratum"] == "in_transit" else ("Benign look-alike" if L["stratum"] == "context_benign" else ("Clean" if L["stratum"] == "clean" else "Messy but correct")))
            want = "ESCALATE" if L["real_discrepancy"] else ("WAIT" if L["stratum"] == "in_transit" else "PAY")
            g = groups.setdefault(t, [0, 0, L["real_discrepancy"]]); g[1] += 1; g[0] += P[i]["action"] == want
            per_case.append({"set": set_name, "system": name, "case_id": i, "latency_s": round(P[i]["latency_ms"] / 1000, 2) if P[i].get("latency_ms") else None,
                             "cost_usd": round(P[i]["cost_usd"], 6), "correct": int(P[i]["action"] == want)})
        for t, (ok, tot, is_real) in sorted(groups.items()):
            by_type.append({"set": set_name, "system": name, "type": t, "problem": "Real problem" if is_real else "No problem", "cases": tot, "correct": ok, "rate": round(ok / tot, 4)})
os.makedirs("docs/results/dashboard", exist_ok=True)
for name, rows in (("summary", summary), ("by_type", by_type), ("per_case", per_case)):
    json.dump(rows, open(f"docs/results/dashboard/{name}.json", "w"))
for r in summary:
    print(f"{r['set']:18} {r['system']:28} n={r['cases']:4} caught {r['caught']}/{r['real']} FP {r['false_escalations']}/{r['fine']} wait {r['wait_correct']}/{r['in_transit']} ${r['model_cost_per_100']}/100 p50 {r['latency_p50_s']}s")
