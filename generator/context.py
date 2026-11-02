"""Context-anomaly set: the four documents agree (a three-way match passes) but company history
(the train split) or the wiki shows something is wrong. Plus benign look-alikes.

python3 -I generator/context.py     # writes data/dev_context.jsonl, data/test_context.jsonl,
                                    # data/context_manifest.json, then runs generator/context_check.py
"""
import collections
import copy
import datetime
import hashlib
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from world import (COMPANIES, ITEMS, SUPPLIERS, TEMPLATES, WIKI_SUPPLIER_PAGES, APPROVED_NEW_ITEMS,  # noqa: E402
                   GENERATOR_VERSION)
from noise import po_str, build_noise_cfg, NOISE_TYPES  # noqa: E402
from templates import render_document  # noqa: E402
from cases import SplitState, wchoice, c2f  # noqa: E402

SPLITS = {"dev_context": {"seed": 2102, "per_type": 4, "benign": 14},
          "test_context": {"seed": 3103, "per_type": 20, "benign": 70}}
PREFIX = {"dev_context": "DEVCTX", "test_context": "TESTCTX"}
ANOMALIES = ["new_item_for_supplier", "price_above_history", "pack_size_changed", "remit_to_changed",
             "near_duplicate_invoice", "quantity_spike", "ship_from_unusual"]
BENIGN = ["benign_price_within_band", "benign_qty_moderate", "benign_remit_reformatted",
          "benign_new_item_approved", "benign_near_match_other_po"]
NEXT = {"new_item_for_supplier": "investigate", "price_above_history": "dispute_with_supplier",
        "pack_size_changed": "dispute_with_supplier", "remit_to_changed": "investigate",
        "near_duplicate_invoice": "investigate", "quantity_spike": "investigate", "ship_from_unusual": "investigate"}
SAFE_NOISE = ["field_reorder", "date_format", "number_format", "po_ref_format", "vendor_alias"]
NO_NUMBER_NOISE = {"price_above_history", "pack_size_changed", "quantity_spike", "benign_price_within_band",
                   "benign_qty_moderate"}
NEW_PACK = {6: 5, 12: 10, 24: 20, 50: 40, 10: 8, 100: 80}
UNUSUAL_SITES = ["Riga, LV", "Lagos, NG", "Panama City, PA", "Bucharest, RO", "Manila, PH", "Almaty, KZ",
                 "Tbilisi, GE", "Limassol, CY", "Sofia, BG", "Lima, PE"]
ODD_BANKS = ["Baltic Trade Bank, IBAN LV80 **** 4471", "Meridian Offshore Bank, acct ****0932",
             "First Coastal Credit, acct ****7781", "Unity Commerce Bank, SWIFT UCBXXX ****2210"]
REGION_NAMES = {"NV": "Nevada", "DE": "Germany", "FL": "Florida", "TX": "Texas", "NL": "Netherlands",
                "CA": "California", "CN": "China", "GA": "Georgia", "NJ": "New Jersey", "TN": "Tennessee",
                "HK": "Hong Kong", "SE": "Sweden", "SC": "South Carolina"}
AS_OF_START = datetime.date(2026, 7, 1)
AS_OF_END = datetime.date(2026, 10, 30)


def bank_for(sid):
    h = int(hashlib.sha256(sid.encode()).hexdigest()[:6], 16)
    return "%s, acct ****%04d" % (["Wells Fargo", "Chase", "Deutsche Bank", "ABN AMRO", "Bank of America",
                                   "HSBC"][h % 6], h % 10000)


def reformat_site(site):
    """Same place, written differently: 'Hamburg, DE' -> 'Hamburg, Germany'."""
    city, rest = site.split(", ", 1)
    parts = rest.split(" ", 1)
    region = REGION_NAMES[parts[0]]
    return "%s, %s" % (city, region) + (" (%s)" % parts[1] if len(parts) > 1 else "")


# ------------------------------------------------------------ history from train gold

def build_history(train_path):
    H = {"skus": collections.defaultdict(set), "inv_prices": collections.defaultdict(list),
         "po_prices": collections.defaultdict(list), "qty_max": collections.defaultdict(int),
         "remit": collections.defaultdict(set), "ship_from": collections.defaultdict(set),
         "company_skus": collections.defaultdict(set), "qtys": collections.defaultdict(list)}
    for line in open(train_path, encoding="utf-8"):
        c = json.loads(line)
        g = c["label"]["gold"]
        sid, co = c["supplier_id"], c["company"]

        def seen(sku, q):
            H["skus"][sid].add(sku)
            H["company_skus"][co].add(sku)
            H["qty_max"][(co, sid, sku)] = max(H["qty_max"][(co, sid, sku)], q)

        for l in g["po"]["lines"]:
            seen(l["sku"], l["qty"])
            H["po_prices"][(sid, l["sku"])].append(l["unit_price"])
            H["qtys"][(co, sid, l["sku"])].append(l["qty_open"])
        for l in g["invoice"]["lines"]:
            seen(l["sku"], l["qty"])
            H["inv_prices"][(sid, l["sku"])].append(l["unit_price"])
        if g["shipping_notice"]:
            for l in g["shipping_notice"]["lines"]:
                seen(l["sku"], l["qty_shipped"])
            H["ship_from"][sid].add(g["shipping_notice"]["ship_from"])
        if g["gr"]:
            for l in g["gr"]["lines"]:
                seen(l["sku"], max(l["qty_received"], l["qty_ordered"]))
        for h in g["billing_history"]:
            for l in h["lines"]:
                seen(l["sku"], l["qty"])
        for o in g["open_pos"]:
            for l in o["lines"]:
                seen(l["sku"], l["qty"])
        H["remit"][sid].add(g["invoice"]["remit_to"])
    return H


def load_wiki_history():
    out = {}
    d = os.path.join(ROOT, "wiki", "history")
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.startswith("SUP-"):
                with open(os.path.join(d, fn)) as f:
                    out[fn[:-5]] = json.load(f)
    return out


def mean(xs):
    return sum(xs) / len(xs)


class Ctx:
    def __init__(self, H, WH):
        self.H, self.WH = H, WH

    def price_means(self, sid, sku):
        ms = [mean(self.H["inv_prices"][(sid, sku)]), mean(self.H["po_prices"][(sid, sku)])]
        w = self.WH.get(sid, {}).get("unit_price_by_sku", {}).get(sku)
        if w:
            ms.append(w["mean"])
        return ms

    def n_obs(self, sid, sku):
        n = len(self.H["inv_prices"][(sid, sku)])
        w = self.WH.get(sid, {}).get("unit_price_by_sku", {}).get(sku)
        return min(n, w["n"]) if w else n

    def qty_maxes(self, co, sid, sku):
        ms = [self.H["qty_max"][(co, sid, sku)]]
        w = self.WH.get(sid, {}).get("qty_max_by_company_sku", {}).get("%s|%s" % (co, sku))
        if w:
            ms.append(w)
        w2 = self.WH.get(sid, {}).get("qty_by_sku", {}).get(sku)
        if w2:
            ms.append(w2["max"])
        return ms

    def hist_skus(self, sid):
        s = set(self.H["skus"][sid])
        s |= set(self.WH.get(sid, {}).get("unit_price_by_sku", {}).keys())
        return s


# ------------------------------------------------------------ case builder

def build_context_case(split, seed, idx, cid, kind, company, st, C):
    rng = random.Random(seed * 1000003 + idx)
    rng_ocr = random.Random(seed * 1000003 + idx + 500000000)
    H = C.H
    sups = [s for s in SUPPLIERS if not SUPPLIERS[s]["test_only"] and company in SUPPLIERS[s]["companies"]
            and H["skus"][s]]

    def normal_skus(sid):
        return sorted(k for k in H["skus"][sid] if ITEMS[k]["company"] == company and C.n_obs(sid, k) >= 5)

    # ---- choose supplier and the line carrying the context signal
    special = None  # sku of the line carrying the signal
    if kind in ("new_item_for_supplier", "benign_new_item_approved"):
        if kind == "benign_new_item_approved":
            cands = [(s, k) for s, ks in APPROVED_NEW_ITEMS.items() for k in ks
                     if company in SUPPLIERS[s]["companies"] and ITEMS[k]["company"] == company]
        else:
            cands = [(s, k) for s in sups for k in sorted(H["company_skus"][company])
                     if k not in C.hist_skus(s) and k not in APPROVED_NEW_ITEMS.get(s, [])
                     and any(k in H["skus"][o] for o in sups if o != s)]
        sid, special = rng.choice(sorted(cands))
    elif kind == "pack_size_changed":
        cands = [(s, k) for s in sups if SUPPLIERS[s]["bills_in_packs"] for k in normal_skus(s)
                 if ITEMS[k]["pack"] and ITEMS[k]["pack"]["unit"] == "CS"]
        sid, special = rng.choice(cands)
    else:
        sid = rng.choice(sups)
        special = rng.choice(normal_skus(sid))
    sup, co = SUPPLIERS[sid], COMPANIES[company]

    others = [k for k in normal_skus(sid) if k != special]
    n_extra = 0 if kind == "pack_size_changed" else rng.choice([0, 0, 1])
    skus = [special] + rng.sample(others, min(n_extra, len(others)))
    rng.shuffle(skus)

    # ---- quantities and prices (normal = inside history)
    lines = []
    for k in skus:
        if (co_hist := H["qtys"].get((company, sid, k))):
            q = rng.choice(co_hist)
        else:  # new item for this supplier: a typical qty from other suppliers' history
            pool = [q for (c2, s2, k2), qs in H["qtys"].items() if c2 == company and k2 == k for q in qs]
            q = rng.choice(sorted(pool))
        if k in H["skus"][sid]:
            p = int(round(mean(H["po_prices"][(sid, k)]) * 100 * rng.uniform(0.99, 1.01)))
        else:
            p = int(round(ITEMS[k]["unit_value_cents"] * rng.uniform(0.98, 1.02)))
        lines.append({"sku": k, "qty": q, "price": p})
    L = next(l for l in lines if l["sku"] == special)
    basis = ""
    at_risk_c = 0
    hist_mean = None
    if kind in ("price_above_history", "benign_price_within_band"):
        ms = C.price_means(sid, special)
        if kind == "price_above_history":
            lo, hi = max(ms) * 1.16, min(ms) * 1.39
            L["price"] = int(round(rng.uniform(lo, hi) * 100))
        else:
            L["price"] = int(round(mean(ms) * rng.uniform(0.985, 1.015) * 100))
        hist_mean = mean(H["inv_prices"][(sid, special)])
        pct = (L["price"] / 100.0 / hist_mean - 1) * 100
        basis = ("Unit price %.2f for %s is %+.1f%% vs this supplier's train mean %.2f over %d invoices"
                 % (L["price"] / 100.0, special, pct, hist_mean, C.n_obs(sid, special)))
        if kind == "price_above_history":
            at_risk_c = int(round((L["price"] / 100.0 - hist_mean) * L["qty"] * 100))
            basis += " (15-40% above history)."
        else:
            basis += " (inside the normal band)."
    if kind in ("quantity_spike", "benign_qty_moderate"):
        mx = C.qty_maxes(company, sid, special)
        pack = ITEMS[special]["pack"]
        step = pack["size"] if pack else 1
        if kind == "quantity_spike":
            q = int(max(mx) * rng.uniform(5.2, 8.0))
        else:
            lo, hi = max(mx) * 1.3, min(mx) * 2.0
            if hi < lo:
                lo, hi = min(mx) * 1.3, min(mx) * 2.0
            q = int(rng.uniform(lo, hi))
        q = max(step, (q // step) * step)
        if kind == "benign_qty_moderate" and q < 1.3 * max(mx):
            q += step
        L["qty"] = q
        if kind == "quantity_spike":
            at_risk_c = (q - H["qty_max"][(company, sid, special)]) * L["price"]
        basis = ("%s quantity %d is %.1fx the largest quantity %s ever ordered of it from this supplier in "
                 "train (%d)." % (special, q, q / H["qty_max"][(company, sid, special)], COMPANIES[company]["name"],
                                  H["qty_max"][(company, sid, special)]))
    pack_new = None
    if kind == "pack_size_changed":
        s = ITEMS[special]["pack"]["size"]
        s2 = NEW_PACK[s]
        mx = H["qty_max"][(company, sid, special)]
        k = max(1, rng.randint(max(1, (mx // 4) // s), max(1, mx // s)))
        L["qty"] = k * s
        L["price"] = max(1, int(round(L["price"] / s2))) * s2  # per-EA PO price, multiple of new pack
        pack_new = {"unit": "CS", "size": s2, "wiki_size": s, "cases": k}
        at_risk_c = (k * s - k * s2) * L["price"]
        basis = ("Wiki item page says 1 CS = %d EA, but the notice and invoice state %d CS (%d EA): %d EA short "
                 "for the PO amount." % (s, k, k * s2, k * s - k * s2))

    # ---- dates
    as_of = AS_OF_START + datetime.timedelta(days=rng.randint(0, (AS_OF_END - AS_OF_START).days))
    received = as_of - datetime.timedelta(days=rng.randint(1, 15))
    ship = received - datetime.timedelta(days=max(1, sup["lead_days"] + rng.randint(-1, 1)))
    po_date = ship - datetime.timedelta(days=rng.randint(3, 20))
    inv_date = min(as_of, ship + datetime.timedelta(days=rng.randint(0, 3)))

    remit = sup["sites"][0]
    remit_bank = bank_for(sid)
    ship_from = sup["sites"][0]
    if kind == "remit_to_changed":
        remit = rng.choice(UNUSUAL_SITES)
        remit_bank = rng.choice(ODD_BANKS)
        basis = ("Invoice remit-to '%s' differs from every remit-to this supplier used in train (%s)."
                 % (remit, "; ".join(sorted(H["remit"][sid]))))
    elif kind == "benign_remit_reformatted":
        remit = reformat_site(sup["sites"][0])
        basis = ("Remit-to '%s' is the same place as the train remit-to '%s', written differently."
                 % (remit, sup["sites"][0]))
    if kind == "ship_from_unusual":
        ship_from = rng.choice(UNUSUAL_SITES)
        basis = ("Shipping notice ship-from '%s' was never used by this supplier in train (%s)."
                 % (ship_from, "; ".join(sorted(H["ship_from"][sid]))))
    if kind == "new_item_for_supplier":
        basis = ("%s has never been supplied by %s in train (company buys it from %s) and is not approved on its "
                 "wiki page." % (special, sid, ", ".join(sorted(o for o in sups if special in H["skus"][o]))))
    if kind == "benign_new_item_approved":
        basis = ("%s is new for %s versus train, but the supplier wiki page lists it under approved_new_items."
                 % (special, sid))

    # ---- gold documents (all agree)
    po_n = st.new_po(rng)
    inv_no = st.new_invoice(rng, sid, inv_date.year % 100)
    d0 = lambda k: ITEMS[k]["descriptions"][0]  # noqa: E731
    d1 = lambda k: ITEMS[k]["descriptions"][min(1, len(ITEMS[k]["descriptions"]) - 1)]  # noqa: E731
    po_lines = [{"line": i + 1, "sku": l["sku"], "description": d0(l["sku"]), "qty": l["qty"],
                 "qty_previously_billed": 0, "qty_open": l["qty"], "uom": "EA", "unit_price": c2f(l["price"]),
                 "amount": c2f(l["qty"] * l["price"])} for i, l in enumerate(lines)]
    gold_po = {"po_number": po_str(po_n), "po_date": po_date.isoformat(), "revision": 1, "prior_invoice": None,
               "company": company, "buyer": rng.choice(co["buyers"]), "supplier_id": sid,
               "supplier_name": sup["name"], "currency": "USD", "lines": po_lines,
               "total": c2f(sum(l["qty"] * l["price"] for l in lines))}

    def true_ea(l):
        return pack_new["cases"] * pack_new["size"] if (pack_new and l["sku"] == special) else l["qty"]

    gold_asn = {"asn_number": sup["asn_fmt"].format(n5="%05d" % rng.randint(1, 99999), n6="%06d" % rng.randint(1, 999999)),
                "po_number": po_str(po_n), "ship_date": ship.isoformat(), "ship_from": ship_from,
                "carrier": rng.choice(["UPS Freight", "FedEx Ground", "XPO Logistics", "DHL Express"]),
                "tracking": "1Z%010d" % rng.randint(0, 9999999999), "cartons": rng.randint(1, 12),
                "lines": [{"sku": l["sku"], "description": d1(l["sku"]), "qty_shipped": true_ea(l), "uom": "EA"}
                          for l in lines]}
    gold_gr = {"gr_number": "%s-%06d" % (co["gr_prefix"], rng.randint(1, 999999)), "po_number": po_str(po_n),
               "received_date": received.isoformat(), "received_by": rng.choice(co["clerks"]), "dock": rng.randint(1, 6),
               "lines": [{"sku": l["sku"], "description": d0(l["sku"]), "qty_ordered": l["qty"],
                          "qty_received": true_ea(l), "uom": "EA"} for l in lines]}
    inv_lines = []
    for i, l in enumerate(lines):
        amt = l["qty"] * l["price"]
        q = true_ea(l)
        inv_lines.append({"line": i + 1, "sku": l["sku"], "description": d1(l["sku"]), "qty": q, "uom": "EA",
                          "unit_price": c2f(amt // q) if amt % q == 0 else round(amt / q / 100.0, 4),
                          "amount": c2f(amt)})
    total_c = sum(l["qty"] * l["price"] for l in lines)
    gold_inv = {"invoice_number": inv_no, "invoice_date": inv_date.isoformat(),
                "due_date": (inv_date + datetime.timedelta(days=30)).isoformat(), "po_number": po_str(po_n),
                "supplier_id": sid, "remit_to": remit, "remit_bank": remit_bank, "currency": "USD",
                "lines": inv_lines, "subtotal": c2f(total_c), "tax": 0.0, "total": c2f(total_c)}
    if pack_new:
        for doc in (gold_asn, gold_inv):
            for l in doc["lines"]:
                if l["sku"] == special:
                    l["stated_pack"] = {"unit": "CS", "size": pack_new["size"], "cases": pack_new["cases"]}
        line_gr = next(l for l in gold_gr["lines"] if l["sku"] == special)
        line_gr["counted_cases"] = pack_new["cases"]

    # ---- billing history
    history = []

    def near(num):
        digits = [i for i, ch in enumerate(num) if ch.isdigit()]
        while True:
            m = rng.choice(["suffix", "transpose", "change"])
            if m == "suffix":
                out = num + rng.choice(["A", "B", "-1"])
            elif m == "transpose":
                pairs = [i for i in digits if i + 1 in digits and num[i] != num[i + 1]]
                if not pairs:
                    continue
                i = rng.choice(pairs)
                out = num[:i] + num[i + 1] + num[i] + num[i + 2:]
            else:
                i = rng.choice(digits[-4:])
                out = num[:i] + str((int(num[i]) + rng.randint(1, 9)) % 10) + num[i + 1:]
            if out != num and st.inv_free(out):
                st.claim(out)
                return out, m

    if kind == "near_duplicate_invoice":
        nn, how = near(inv_no)
        history.append({"invoice_number": nn, "po_number": po_str(po_n),
                        "invoice_date": (inv_date - datetime.timedelta(days=rng.randint(3, 20))).isoformat(),
                        "lines": [{"sku": l["sku"], "qty": l["qty"], "amount": l["amount"]} for l in inv_lines],
                        "status": "paid"})
        at_risk_c = total_c
        basis = ("Billing history has paid invoice %s on the same PO with identical lines and amount; its number "
                 "differs from %s only by a %s." % (nn, inv_no, {"suffix": "suffix", "transpose": "transposed pair",
                                                                  "change": "single changed digit"}[how]))
    other = [k for k in sorted(H["skus"][sid]) if ITEMS[k]["company"] == company and k not in skus]
    if kind == "benign_near_match_other_po" or (other and rng.random() < 0.25):
        ks = rng.sample(other, min(len(other), rng.randint(1, 2)))
        hl = []
        for k in ks:
            q = rng.choice(H["qtys"][(company, sid, k)] or [10])
            hl.append({"sku": k, "qty": q, "amount": c2f(q * int(round(mean(H["po_prices"][(sid, k)]) * 100)))})
        if kind == "benign_near_match_other_po":
            num, _ = near(inv_no)
        else:
            num = st.new_invoice(rng, sid, (as_of.year - 1) % 100)
        pn = st.new_po(rng, avoid=[po_n])
        history.append({"invoice_number": num, "po_number": po_str(pn),
                        "invoice_date": (as_of - datetime.timedelta(days=rng.randint(30, 150))).isoformat(),
                        "lines": hl, "status": "paid"})
        if kind == "benign_near_match_other_po":
            basis = ("History invoice %s looks like %s but is on a different PO (%s) with different lines and amount."
                     % (num, inv_no, po_str(pn)))
    history.sort(key=lambda h: (h["invoice_date"], h["invoice_number"]))
    if kind in ("new_item_for_supplier", "remit_to_changed", "ship_from_unusual"):
        at_risk_c = total_c

    gold = {"po": gold_po, "shipping_notice": gold_asn, "gr": gold_gr, "invoice": gold_inv,
            "billing_history": history, "open_pos": []}
    present = ["po", "shipping_notice", "gr", "invoice"]

    # ---- light noise, never on the anomaly-critical field
    allowed = [t for t in SAFE_NOISE if not (t == "number_format" and kind in NO_NUMBER_NOISE)]
    types = sorted(rng.sample(allowed, rng.choice([0, 1, 1, 2])), key=NOISE_TYPES.index)
    cfg = build_noise_cfg(rng, types, sid, present)
    tpl = {"po": wchoice(rng, co["po_tpl_w"]), "gr": wchoice(rng, co["gr_tpl_w"]),
           "invoice": wchoice(rng, sup["inv_tpl_w"]), "shipping_notice": wchoice(rng, sup["asn_tpl_w"])}
    ctx = {"company": company, "supplier_id": sid}
    texts, tokens = {}, []
    for d in ("po", "shipping_notice", "gr", "invoice"):
        g_render, c_doc = gold, cfg[d]
        saved = None
        if pack_new and d in ("shipping_notice", "invoice"):
            c_doc = dict(cfg[d], pack="paren")
            saved = ITEMS[special]["pack"]["size"]
            ITEMS[special]["pack"]["size"] = pack_new["size"]
            if d == "invoice":  # render price per CS = PO per-EA price x wiki pack size
                g_render = copy.deepcopy(gold)
                for l in g_render["invoice"]["lines"]:
                    if l["sku"] == special:
                        l["unit_price"] = c2f(int(round(L["price"] * pack_new["wiki_size"] / pack_new["size"])))
        elif pack_new and d == "gr":  # receiving counted cases and wrote 'k CS'
            c_doc = dict(cfg[d], pack="bare")
            g_render = copy.deepcopy(gold)
            for l in g_render["gr"]["lines"]:
                if l["sku"] == special:
                    l["qty_received"] = l["qty_ordered"]
        try:
            t, toks = render_document(d, tpl[d], g_render, ctx, c_doc, {}, rng_ocr)
        finally:
            if saved:
                ITEMS[special]["pack"]["size"] = saved
        texts[d] = t
        tokens += toks

    anomaly = kind in ANOMALIES
    label = {
        "stratum": "context_anomaly" if anomaly else "context_benign",
        "real_discrepancy": anomaly,
        "reason_code": kind if anomaly else "none",
        "benign_type": None if anomaly else kind,
        "next_step": NEXT[kind] if anomaly else "pay",
        "at_risk_usd": c2f(at_risk_c) if anomaly else 0.0,
        "leg": None,
        "noise_types": types,
        "context_basis": basis,
        "signal_sku": special,
        "gold": gold,
        "render_meta": {"doc_cfg": cfg, "tokens": tokens, "hist_mean": hist_mean},
    }
    return {
        "case_id": cid, "split": split, "company": company, "supplier_id": sid, "as_of_date": as_of.isoformat(),
        "documents": texts, "billing_history": history, "open_pos": [],
        "wiki_refs": {"supplier": ("wiki/suppliers/%s.json" % sid) if sid in WIKI_SUPPLIER_PAGES else None,
                      "items": ["wiki/items/%s.json" % k for k in sorted(skus)], "policy": "wiki/policy.json"},
        "template_ids": tpl, "heldout": {"template": False, "supplier": False}, "label": label,
    }


class CtxState(SplitState):
    def inv_free(self, s):
        from cases import ocr_key
        return ocr_key(s) not in self.inv_keys

    def claim(self, s):
        from cases import ocr_key
        self.inv_keys.add(ocr_key(s))


def plan(name):
    cfg = SPLITS[name]
    slots = []
    for kind in ANOMALIES:
        for i in range(cfg["per_type"]):
            slots.append((kind, "northside" if i % 2 == 0 else "caseworks"))
    for i in range(cfg["benign"]):
        slots.append((BENIGN[i % len(BENIGN)], "northside" if (i // len(BENIGN)) % 2 == 0 else "caseworks"))
    # balance companies inside each benign type
    by = collections.defaultdict(list)
    for j, (k, c) in enumerate(slots):
        by[k].append(j)
    n = 0
    for k in BENIGN:  # one running alternation: balanced inside each type and overall
        for j in by[k]:
            slots[j] = (k, "northside" if n % 2 == 0 else "caseworks")
            n += 1
    rng = random.Random(cfg["seed"])
    rng.shuffle(slots)
    return slots


def feasible(kind, company):
    if kind == "benign_new_item_approved":
        return any(company in SUPPLIERS[s]["companies"] and ITEMS[k]["company"] == company
                   for s, ks in APPROVED_NEW_ITEMS.items() for k in ks)
    return True


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    H = build_history(os.path.join(ROOT, "data", "train.jsonl"))
    C = Ctx(H, load_wiki_history())
    manifest = {"generator_version": GENERATOR_VERSION, "entry_command": "python3 -I generator/context.py",
                "history_source": "data/train.jsonl", "splits": {}, "files": {}}
    for name, cfg in SPLITS.items():
        st = CtxState()
        # keep context invoice/PO numbers clear of train ones
        for line in open(os.path.join(ROOT, "data", "train.jsonl"), encoding="utf-8"):
            c = json.loads(line)
            st.po_numbers.add(int(c["label"]["gold"]["po"]["po_number"][3:]))
        cases = []
        for i, (kind, company) in enumerate(plan(name)):
            cases.append(build_context_case(name, cfg["seed"], i, "%s-%04d" % (PREFIX[name], i + 1), kind, company, st, C))
        path = os.path.join(ROOT, "data", name + ".jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for c in cases:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        cnt = collections.Counter((c["label"]["reason_code"] if c["label"]["real_discrepancy"]
                                   else c["label"]["benign_type"], c["company"]) for c in cases)
        manifest["splits"][name] = {
            "seed": cfg["seed"], "n": len(cases),
            "by_stratum": dict(collections.Counter(c["label"]["stratum"] for c in cases)),
            "by_type_company": {"%s/%s" % k: v for k, v in sorted(cnt.items())},
            "by_company": dict(collections.Counter(c["company"] for c in cases)),
        }
        print(name, len(cases), manifest["splits"][name]["by_stratum"], flush=True)
    for rel in ["data/dev_context.jsonl", "data/test_context.jsonl"] + \
            ["wiki/suppliers/%s.json" % s for s in sorted(APPROVED_NEW_ITEMS)]:
        manifest["files"][rel] = {"sha256": sha256(os.path.join(ROOT, rel)),
                                  "bytes": os.path.getsize(os.path.join(ROOT, rel))}
    with open(os.path.join(ROOT, "data", "context_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "context_check.py")])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
