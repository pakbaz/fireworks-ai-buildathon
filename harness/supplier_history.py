"""Supplier history and anomaly flags.

Builds one profile per supplier from past, already-resolved invoices (the train split stands in for the
company's history), and compares a new invoice against its supplier's profile. Pure code, no model calls.

    python3 -m harness.supplier_history          # writes wiki/history/<supplier>.json and wiki/history/index.json
"""
import datetime, json, math, os, statistics as st
from . import config
from .domain import num, norm_sku, line_ea

HIST_DIR = os.path.join(config.REPO, "wiki", "history")

def _d(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None

def _stats(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None
    return {"n": len(xs), "mean": round(st.mean(xs), 4), "sd": round(st.pstdev(xs), 4), "min": min(xs), "max": max(xs)}

def build(history_path=None):
    path = history_path or os.path.join(config.DATA_DIR, "train.jsonl")
    sup = {}
    for line in open(path):
        c = json.loads(line); L = c["label"]; g = L["gold"]
        s = sup.setdefault(c["supplier_id"], {"supplier_id": c["supplier_id"], "invoices": 0, "companies": {}, "problems": {},
                                               "prices": {}, "qty": {}, "totals": [], "lead_days": [], "timeline": []})
        s["invoices"] += 1
        s["companies"][c["company"]] = s["companies"].get(c["company"], 0) + 1
        if L["real_discrepancy"]:
            s["problems"][L["reason_code"]] = s["problems"].get(L["reason_code"], 0) + 1
        for ln in (g.get("po") or {}).get("lines") or []:
            if (ln.get("uom") or "EA") == "EA" and ln.get("unit_price") is not None:
                s["prices"].setdefault(ln["sku"], []).append(ln["unit_price"])
                s["qty"].setdefault(ln["sku"], []).append(ln.get("qty"))
        inv = g.get("invoice") or {}
        if inv.get("total") is not None:
            s["totals"].append(inv["total"])
        asn, gr = g.get("shipping_notice"), g.get("gr")
        if asn and gr and _d(asn.get("ship_date")) and _d(gr.get("received_date")):
            s["lead_days"].append((_d(gr["received_date"]) - _d(asn["ship_date"])).days)
        s["timeline"].append({"date": inv.get("invoice_date") or c.get("as_of_date"), "invoice": inv.get("invoice_number"),
                              "outcome": L["reason_code"] if L["real_discrepancy"] else ("wait" if L["stratum"] == "in_transit" else "paid")})
    total_inv = sum(s["invoices"] for s in sup.values())
    total_prob = sum(sum(s["problems"].values()) for s in sup.values())
    overall = total_prob / total_inv if total_inv else 0.0
    os.makedirs(HIST_DIR, exist_ok=True)
    index = {"source": os.path.relpath(path, config.REPO), "overall_problem_rate": round(overall, 4), "suppliers": {}}
    for sid, s in sup.items():
        n_prob = sum(s["problems"].values())
        prof = {"supplier_id": sid, "built_from": index["source"], "invoices": s["invoices"], "companies": s["companies"],
                "problem_rate": round(n_prob / s["invoices"], 4), "problems_by_type": s["problems"],
                "relative_to_all_suppliers": round((n_prob / s["invoices"]) / overall, 3) if overall else None,
                "unit_price_by_sku": {k: _stats(v) for k, v in s["prices"].items()},
                "qty_by_sku": {k: _stats(v) for k, v in s["qty"].items()},
                "invoice_total": _stats(s["totals"]), "lead_days": _stats(s["lead_days"]),
                "timeline_last_20": sorted(s["timeline"], key=lambda e: str(e["date"]))[-20:]}
        json.dump(prof, open(os.path.join(HIST_DIR, f"{sid}.json"), "w"), indent=1)
        index["suppliers"][sid] = {"invoices": s["invoices"], "problem_rate": prof["problem_rate"]}
    json.dump(index, open(os.path.join(HIST_DIR, "index.json"), "w"), indent=1)
    return index

def load(supplier_id):
    p = os.path.join(HIST_DIR, f"{supplier_id}.json")
    return json.load(open(p)) if os.path.exists(p) else None

def supplier_weight(profile, policy):
    """Stricter dial for suppliers with more past problems; unknown suppliers count as slightly risky."""
    lo, hi = (policy or {}).get("supplier_weight_range", [0.5, 2])
    if profile is None:
        return float((policy or {}).get("new_supplier_weight", 1.5))
    r = profile.get("relative_to_all_suppliers")
    return 1.0 if r is None else min(hi, max(lo, r))

def anomalies(case, read, profile, wiki_items=None):
    """Informational flags: unusual for THIS supplier, even if every check passed."""
    out = []
    if profile is None:
        return [{"flag": "new_supplier", "detail": f"no history for {case.get('supplier_id')}"}]
    inv = (read or {}).get("invoice") or {}
    for il in inv.get("lines") or []:
        sku = il.get("sku"); qea = line_ea(il, "qty", sku, wiki_items)
        amt = num(il.get("amount"))
        unit = (amt / qea) if (amt and qea) else None
        hist = None
        for k, v in (profile.get("unit_price_by_sku") or {}).items():
            if norm_sku(k) == norm_sku(sku):
                hist = v
        if unit is not None and hist and hist["n"] >= 3:
            rel = abs(unit - hist["mean"]) / hist["mean"] if hist["mean"] else 0
            z = abs(unit - hist["mean"]) / hist["sd"] if hist["sd"] else (0 if rel < 1e-6 else 99)
            if z > 3 and rel > 0.02:
                out.append({"flag": "price_unusual", "detail": f"{sku}: {unit:,.2f}/EA vs usual {hist['mean']:,.2f} (z={min(z,99):.1f})"})
        qh = None
        for k, v in (profile.get("qty_by_sku") or {}).items():
            if norm_sku(k) == norm_sku(sku):
                qh = v
        if qea and qh and qh["n"] >= 3 and qea > 2 * qh["max"]:
            out.append({"flag": "quantity_unusual", "detail": f"{sku}: {qea:g} EA vs past max {qh['max']:g}"})
    tot = num(inv.get("total"))
    th = profile.get("invoice_total")
    if tot and th and th["n"] >= 5 and tot > th["mean"] + 3 * th["sd"]:
        out.append({"flag": "amount_unusual", "detail": f"total {tot:,.2f} vs usual {th['mean']:,.0f} ± {th['sd']:,.0f}"})
    asn, gr = (read or {}).get("shipping_notice") or {}, (read or {}).get("gr") or {}
    ld = profile.get("lead_days")
    if asn and gr and ld and ld["n"] >= 5 and _d(asn.get("ship_date")) and _d(gr.get("received_date")):
        days = (_d(gr["received_date"]) - _d(asn["ship_date"])).days
        if abs(days - ld["mean"]) > 3 * max(ld["sd"], 1):
            out.append({"flag": "delivery_time_unusual", "detail": f"{days} days vs usual {ld['mean']:.1f}"})
    if (profile.get("relative_to_all_suppliers") or 0) >= 1.5:
        out.append({"flag": "supplier_with_history_of_problems", "detail": f"problem rate {profile['problem_rate']:.0%}, {profile['relative_to_all_suppliers']:.1f}x the average"})
    return out

if __name__ == "__main__":
    idx = build()
    print(json.dumps(idx, indent=1))
