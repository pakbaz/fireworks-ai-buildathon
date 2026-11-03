"""Build web/cases.json for the review site from saved files. No model calls.

    python3 web/build_data.py

Sources: dashboard/located.json (cases, highlight boxes, Kimi K3 risk and dollars), data/test.jsonl (counts, partial
billing), runs/kimi_alone/test.jsonl (the dial numbers), wiki/policy.json (review cost, category weights).
"""
import json, os
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "web", "cases.json")

# Held back from the queue until someone picks "Try a sample".
SAMPLES = {"TEST-00721", "TEST-00950"}
# Pack sizes the reader has to convert, written on the scans. located.json does not record these.
NOTES = {("TEST-00037", "gr"): "Written as 165 boxes", ("TEST-00037", "invoice"): "Written as 194 boxes"}

def read_jsonl(path):
    return [json.loads(l) for l in open(os.path.join(REPO, path)) if l.strip()]

def page_note(case_id, mark, gold_po, sku):
    """The note under a zoomed-in value: pack size, handwriting, or what is left to bill on a partly billed PO."""
    if (case_id, mark["doc"]) in NOTES:
        return NOTES[(case_id, mark["doc"])]
    if mark["hand"]:
        return "Handwritten"
    if mark["doc"] == "po":
        for line in gold_po.get("lines") or []:
            if line["sku"] == sku and line.get("qty_previously_billed"):
                return f"{line['qty_previously_billed']:,} already billed, {line['qty_open']:,} open"
    return ""

def build_case(x, label, pred):
    docs = {}
    for doc, size in x["docs"].items():
        url = f"data/images/{x['id']}/{doc}.png"
        if not os.path.exists(os.path.join(REPO, url)):
            raise SystemExit(f"Missing scan: {url}")
        docs[doc] = {"w": size["w"], "h": size["h"], "url": "../" + url}
    gold_po = label.get("gold", {}).get("po", {})
    paid = [h["invoice_date"] for h in x["history"] if h["invoice_number"] == x["inv"]]
    return {
        "id": x["id"], "co": x["company"], "sup": x["supplier"], "inv": x["inv"], "po": x["po"], "rc": x["reason"], "car": x["carrier"],
        "risk": x["risk"], "atRisk": x["atRisk"], "loss": x["loss"], "paid": paid[0] if paid else None, "sample": x["id"] in SAMPLES,
        "docs": docs,
        "marks": [{"doc": m["doc"], "says": m["says"], "bad": m["bad"], "box": m["box"], "note": page_note(x["id"], m, gold_po, x["sku"])} for m in x["marks"]],
        "model": {"reason": x["modelReason"], "evidence": x["evidence"], "keyAtRisk": x["goldAtRisk"], "reviewCost": pred["dial"]["expected_cost_of_review_usd"]},
    }

def build():
    located = json.load(open(os.path.join(REPO, "dashboard", "located.json")))
    policy = json.load(open(os.path.join(REPO, "wiki", "policy.json")))
    with_scans = [c for c in read_jsonl("data/test.jsonl") if c.get("images")]
    labels = {c["case_id"]: c["label"] for c in with_scans}
    preds = {p["case_id"]: p for p in read_jsonl("runs/kimi_alone/test.jsonl")}
    flagged = {x["id"] for x in located}
    if flagged != {i for i, l in labels.items() if l["real_discrepancy"]}:
        raise SystemExit("located.json no longer matches the real problems in data/test.jsonl: rerun dashboard/locate_disputes.py")

    def count(company, *strata):
        return sum(c["company"] == company and c["label"]["stratum"] in strata for c in with_scans)

    review = policy["review_cost_usd"]
    weights = policy["category_weights"]
    companies = {
        "northside": {
            "name": "Northside Hospital Supply", "suggested": review / 5, "gate": True,
            "passed": count("northside", "clean", "messy"), "waiting": count("northside", "in_transit"),
            "posture": "Patient-care goods. Prove it to me.",
            "why": [{"label": "A review costs", "value": f"${review}"}, {"label": "Caution margin (proposed)", "value": "÷5"},
                    {"label": "Medical device dollar", "value": f"×{weights['medical_device']}"},
                    {"label": "Consumable dollar", "value": f"×{weights['medical_consumable']}"}],
        },
        "caseworks": {
            "name": "Caseworks", "suggested": review, "gate": False,
            "passed": count("caseworks", "clean", "messy"), "waiting": count("caseworks", "in_transit"),
            "posture": "Low-cost goods. Don’t waste a person on a few dollars.",
            "why": [{"label": "A review costs", "value": f"${review}"}, {"label": "Caution margin", "value": "None"},
                    {"label": "Consumer goods dollar", "value": f"×{weights['consumer']}"}],
        },
    }
    cases = [build_case(x, labels[x["id"]], preds[x["id"]]) for x in located]
    with open(OUT, "w") as fh:
        json.dump({"companies": companies, "cases": cases}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {os.path.relpath(OUT, REPO)}: {len(cases)} cases")

if __name__ == "__main__":
    build()
