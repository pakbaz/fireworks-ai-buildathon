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
                                               "prices": {}, "qty": {}, "totals": [], "lead_days": [], "timeline": [],
                                               "remit_to": set(), "ship_from": set(), "qty_max": {}})
        s["invoices"] += 1
        s["companies"][c["company"]] = s["companies"].get(c["company"], 0) + 1
        if L["real_discrepancy"]:
            s["problems"][L["reason_code"]] = s["problems"].get(L["reason_code"], 0) + 1
        for ln in (g.get("po") or {}).get("lines") or []:
            if (ln.get("uom") or "EA") == "EA" and ln.get("unit_price") is not None:
                s["prices"].setdefault(ln["sku"], []).append(ln["unit_price"])
                s["qty"].setdefault(ln["sku"], []).append(ln.get("qty"))
        for ln in (g.get("po") or {}).get("lines") or []:
            k = f"{c['company']}|{ln['sku']}"
            if ln.get("qty") is not None:
                s["qty_max"][k] = max(s["qty_max"].get(k, 0), ln["qty"])
        inv = g.get("invoice") or {}
        if inv.get("remit_to"): s["remit_to"].add(str(inv["remit_to"]))
        if (g.get("shipping_notice") or {}).get("ship_from"): s["ship_from"].add(str(g["shipping_notice"]["ship_from"]))
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
                "remit_to": sorted(s["remit_to"]), "ship_from": sorted(s["ship_from"]), "qty_max_by_company_sku": s["qty_max"],
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

COUNTRY = {"de": "germany", "nl": "netherlands", "us": "usa", "cn": "china", "uk": "united kingdom", "gb": "united kingdom",
           "ca": "canada", "mx": "mexico", "jp": "japan", "kr": "korea", "tw": "taiwan", "fr": "france", "it": "italy", "in": "india"}

def _place_tokens(s):
    import re
    toks = [t for t in re.split(r"[^a-z]+", str(s or "").lower()) if len(t) > 1]
    return {COUNTRY.get(t, t) for t in toks}

def _place_known(value, known):
    """A place matches history if it shares its city token with any known value (formatting may differ)."""
    v = _place_tokens(value)
    if not v:
        return True
    for k in known or []:
        kt = _place_tokens(k)
        city = [t for t in kt if t not in COUNTRY.values() and len(t) > 2][:1]
        if city and city[0] in v:
            return True
        if len(v & kt) >= 2:
            return True
    return False

def context_issues(case, read, profile, supplier_page, wiki_items=None):
    """Things that are wrong only in light of history: returns (code, next_step, detail, at_risk_usd) tuples.
    These escalate, unlike the informational flags in anomalies()."""
    out = []
    if profile is None:
        return out
    inv = (read or {}).get("invoice") or {}
    approved = {norm_sku(x) for x in ((supplier_page or {}).get("approved_new_items") or [])}
    known_skus = {norm_sku(k) for k in (profile.get("unit_price_by_sku") or {})}
    total = num(inv.get("total")) or sum(num(l.get("amount")) or 0 for l in inv.get("lines") or [])
    for il in inv.get("lines") or []:
        sku = il.get("sku"); ns = norm_sku(sku)
        qea = line_ea(il, "qty", sku, wiki_items); amt = num(il.get("amount"))
        unit = (amt / qea) if (amt and qea) else None
        if ns and ns not in known_skus and ns not in approved:
            out.append(("new_item_for_supplier", "investigate", f"{sku}: never supplied by {case.get('supplier_id')} before", total))
            continue
        hist = next((v for k, v in (profile.get("unit_price_by_sku") or {}).items() if norm_sku(k) == ns), None)
        if unit and hist and hist["n"] >= 5 and unit > hist["mean"] * 1.10:
            out.append(("price_above_history", "dispute_with_supplier", f"{sku}: {unit:,.2f}/EA vs usual {hist['mean']:,.2f} from this supplier", (unit - hist["mean"]) * qea))
        qmax = next((v for k, v in (profile.get("qty_max_by_company_sku") or {}).items() if k.split("|")[0] == case.get("company") and norm_sku(k.split("|", 1)[1]) == ns), None)
        if qea and qmax and qea > 3 * qmax:
            out.append(("quantity_spike", "investigate", f"{sku}: {qea:g} EA vs at most {qmax:g} ever ordered", (qea - qmax) * (unit or 0)))
    if inv.get("remit_to") and profile.get("remit_to") and not _place_known(inv["remit_to"], profile["remit_to"]):
        out.append(("remit_to_changed", "investigate", f"pay to '{inv['remit_to']}' but this supplier is always paid at {', '.join(profile['remit_to'][:2])}", total))
    asn = (read or {}).get("shipping_notice") or {}
    if asn.get("ship_from") and profile.get("ship_from") and not _place_known(asn["ship_from"], profile["ship_from"]):
        out.append(("ship_from_unusual", "investigate", f"shipped from '{asn['ship_from']}', never seen for this supplier", total))
    return out

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
